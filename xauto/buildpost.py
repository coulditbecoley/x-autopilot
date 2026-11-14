"""Personal lane: one post a day about what you actually built, written from your own notes or commits.

build  a short post (under 280), published through your publisher
long   a 600 to 2,200 character post written to output/long/<date>.md for you to post by hand
       (most posting tools cap X at 280, and anything this long deserves a human read)

Every draft goes: model draft -> humanizer -> privacy lint (code, not a model). If the humanized
version fails the lint, the plain draft is tried. If both fail, one redraft with the reasons.
Then the day is skipped. A skipped day is cheap. A leak is not.
"""
import datetime as dt
import json
import os
import re
import subprocess

from . import gates, llm, prompts
from .core import in_posting_hours, log, now, read_json, write_json
from .publish import intent_link, publish

SHORT = dict(max_len=280, min_len=0, size='Under 260 characters in total.')
LONG = dict(max_len=2200, min_len=600, size='Keep it between 900 and 1,800 characters in total.')


def notes_text(cfg, today):
    """The last N days of your work, newest first, from note files and/or git commits."""
    src = cfg['build_post'].get('notes', {})
    days = src.get('days', 3)
    parts = []
    for back in range(1, days + 1):
        day = today - dt.timedelta(days=back)
        label = 'yesterday' if back == 1 else f'{back} days ago'
        chunk = []
        if src.get('file_pattern'):
            p = os.path.expanduser(src['file_pattern'].format(
                date=day.isoformat(), year=day.year, month=f'{day.month:02d}', day=f'{day.day:02d}',
                month_name=day.strftime('%B')))
            try:
                text = open(p, encoding='utf-8').read()
                if src.get('sections'):
                    names = '|'.join(re.escape(s) for s in src['sections'])
                    found = re.findall(r'^#+ (' + names + r')\s*\n(.*?)(?=^#+ |\Z)', text, re.M | re.S)
                    text = '\n'.join(f'{h}:\n{b.strip()}' for h, b in found if b.strip())
                if text.strip():
                    chunk.append(text.strip())
            except OSError:
                pass
        for repo in src.get('git_repos', []):
            r = subprocess.run(['git', '-C', os.path.expanduser(repo), 'log', '--no-merges',
                                f'--since={day.isoformat()} 00:00', f'--until={day.isoformat()} 23:59',
                                '--pretty=format:- %s%n%b'], capture_output=True, text=True, encoding='utf-8')
            if r.returncode == 0 and r.stdout.strip():
                chunk.append(f'Commits in {os.path.basename(os.path.normpath(repo))}:\n' + r.stdout.strip())
        if chunk:
            parts.append(f'=== {day.isoformat()} ({label}) ===\n' + '\n\n'.join(chunk))
    return '\n\n'.join(parts)


def _json(text):
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        raise RuntimeError('model returned no JSON')  # output not echoed: it may quote private notes
    return json.loads(m.group(0))


def draft_and_check(cfg, notes, recent, long_mode):
    bp, mode = cfg['build_post'], LONG if long_mode else SHORT
    deny, names = gates.deny_terms(bp), bp.get('allowed_names', [])
    check = lambda p: gates.privacy_fails(p, notes, deny, names, mode['max_len'], mode['min_len'])
    system = prompts.build_system(cfg, long_mode)
    retry, fails, draft = '', [], ''
    for _ in (1, 2):
        d = _json(llm.complete(cfg, system, f'{retry}Recent posts (do not repeat these angles):\n{recent or "(none)"}\n\nWork log:\n{notes}', 3000))
        if d.get('skip'):
            return None, 'model skipped: ' + str(d.get('reason', ''))
        draft = str(d['post']).strip()
        tags = ' '.join(re.findall(gates.TAG, draft))
        human = draft
        if cfg.get('humanizer', {}).get('enabled', True):
            try:
                human = llm.complete(cfg, prompts.humanize_system(cfg, tags, mode['size']), draft, 3000).strip()
            except Exception as e:  # noqa: BLE001  the humanizer can never cost a post
                log(cfg, 'humanize', f'kept draft, call failed: {e}')
        for cand in (human, draft):
            fails = check(cand) + ([] if cand.endswith(tags) else ['hashtags changed'])
            if len(re.findall(gates.TAG, cand)) != len(tags.split()):
                fails.append('hashtag count changed')
            if not fails:
                alts = [h.strip() for h in d.get('alt_hooks') or []
                        if h.strip() and not check(h.strip() + (cand[cand.find('\n'):] if '\n' in cand else ''))]
                return {'post': cand, 'kind': d.get('kind'), 'angle': d.get('angle'), 'alts': alts}, ''
        retry = f'Your previous draft was rejected for: {"; ".join(fails)}. Write a new one that avoids all of these.\n\n'
    # The rejected draft is not logged: it failed the privacy check, so it may hold something private.
    return None, 'privacy lint failed twice: ' + '; '.join(fails)


def run(cfg, dry=False, long_mode=False):
    job = 'long' if long_mode else 'build'
    bp = cfg.get('build_post', {})
    if not bp.get('enabled'):
        return log(cfg, job, 'SKIP build_post.enabled is false')
    t = now()
    today = t.date()
    history = read_json(cfg, 'build_log.json', [])
    if not dry and any(h['day'] == today.isoformat() and (h['kind'] == 'long') == long_mode for h in history):
        return log(cfg, job, 'SKIP already done today')
    if not long_mode and not dry and not in_posting_hours(cfg, t):
        return log(cfg, job, 'SKIP outside posting_hours')
    notes = notes_text(cfg, today)
    if not notes:
        return log(cfg, job, 'SKIP no notes or commits in the lookback window')
    recent = '\n'.join(f"{h['day']} {h['kind']}: {h['angle']}" for h in history[-30:])
    info, why = draft_and_check(cfg, notes, recent, long_mode)
    if not info:
        return log(cfg, job, 'SKIP ' + why)
    if dry:
        return log(cfg, job, f"DRY ({len(info['post'])} chars)\n{info['post']}" +
                   ('\n\nALT HOOKS:\n' + '\n'.join(info['alts']) if info['alts'] else ''))
    if long_mode:
        folder = os.path.join(cfg['paths']['output_dir'], 'long')
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, today.isoformat() + '.md')
        alts = '\n'.join(f'- {h}' for h in info['alts']) or '- (none passed the checks today)'
        open(path, 'w', encoding='utf-8').write(
            f"# Long post, {today.isoformat()}\n\nAngle: {info['angle']}\n\n[Post on X]({intent_link(info['post'])}) "
            "opens a new post with this text filled in (if it arrives cut off, copy from the box). "
            f"Post it live, then stay for the first hour and answer replies.\n\n```text\n{info['post']}\n```\n\n"
            f"## If it stalls\n\nBarely moving after 30 minutes? Repost with one of these first lines.\n\n{alts}\n\n- [ ] Posted\n")
        where = 'long draft written to ' + path
    # Record the day BEFORE sending, so a crash or a lost response can never lead to a second post.
    entry = {'day': today.isoformat(), 'kind': 'long' if long_mode else info.get('kind') or 'story',
             'angle': info.get('angle') or '', 'post': info['post'], 'status': 'written' if long_mode else 'sending'}
    history.append(entry)
    write_json(cfg, 'build_log.json', history[-200:])
    if not long_mode:
        if not in_posting_hours(cfg):
            entry['status'] = 'skipped'
            write_json(cfg, 'build_log.json', history[-200:])
            return log(cfg, job, 'SKIP posting window closed during the run')
        try:
            where = publish(cfg, info['post'], 'build')
        except Exception:
            entry['status'] = 'failed'
            write_json(cfg, 'build_log.json', history[-200:])
            log(cfg, job, "send failed: check your account. If it did not post, delete today's entry from "
                          'state/build_log.json and rerun.')
            raise
        entry['status'] = 'sent'
        write_json(cfg, 'build_log.json', history[-200:])
    log(cfg, job, f"OK {where}\n{info['post']}")
