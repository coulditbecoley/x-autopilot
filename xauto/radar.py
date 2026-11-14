"""News lane and reply queue.

news     scrape the watched accounts, keep fast-moving originals, let the model pick at most one
         real story, gate it, shorten if needed, humanize, publish. Most scans post nothing.
replies  once a morning: the fastest-moving big posts from the last 24 hours, one drafted reply
         each, written to output/replies/<date>.md. NEVER posted automatically: X requires its
         written approval for automated replies, and accounts get suspended for it.
"""
import datetime as dt
import email.utils
import json
import os
import re
import urllib.parse
import urllib.request

from . import gates, llm, prompts
from .core import in_posting_hours, log, now, read_json, secret, write_json
from .publish import publish

DEFAULT_ACTOR = 'kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest'


def scrape(cfg, handles, since_epoch, max_items):
    """One Apify run for every handle, waits for it and returns the items."""
    actor = cfg.get('scraper', {}).get('apify_actor', DEFAULT_ACTOR)
    url = f'https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items?clean=true&format=json'
    body = {'searchTerms': [f'from:{h} since_time:{since_epoch}' for h in handles],
            'maxItems': max_items, 'queryType': 'Latest'}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': 'Bearer ' + secret('APIFY_TOKEN')})
    with urllib.request.urlopen(req, timeout=330) as r:
        return json.loads(r.read())


def originals(items, sector_by_handle, cutoff_epoch, min_eng):
    """Original posts only (no reposts, replies or quotes), recent, above the engagement floor,
    deduped (the scraper returns some posts twice), sorted by engagement per hour."""
    out, seen, t_now = [], set(), now().timestamp()
    for t in items:
        text = (t.get('text') or t.get('fullText') or '').strip()
        if not text or t.get('isRetweet') or t.get('isReply') or t.get('isQuote') or re.match(r'RT @|@', text):
            continue
        created = _epoch(t.get('createdAt') or t.get('created_at'))
        if not created or created < cutoff_epoch:
            continue
        author = t.get('author') or {}
        handle = author.get('userName') or author.get('username') or t.get('username') or ''
        sector = sector_by_handle.get(handle.lower())
        likes = t.get('likeCount') or t.get('favoriteCount') or 0
        reposts = t.get('retweetCount') or 0
        if not sector or likes + reposts < min_eng:
            continue
        pid = str(t.get('id') or t.get('id_str') or '')
        url = t.get('url') or t.get('twitterUrl') or (f'https://x.com/{handle}/status/{pid}' if pid else '')
        if (pid or url) in seen:
            continue
        seen.add(pid or url)
        hours = max((t_now - created) / 3600, 0.5)
        out.append({'handle': handle, 'sector': sector, 'text': text[:600], 'likes': likes,
                    'reposts': reposts, 'url': url, 'per_hour': round((likes + reposts) / hours),
                    'age_hours': round(hours)})
    return sorted(out, key=lambda c: -c['per_hour'])


def _epoch(value):
    if not value:
        return 0
    try:
        return dt.datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
    except ValueError:
        try:
            return email.utils.parsedate_to_datetime(value).timestamp()  # "Wed Oct 10 20:19:24 +0000 2018"
        except (TypeError, ValueError):
            return 0


def _json(text):
    m = re.search(r'\{.*\}', text, re.S)
    return json.loads(m.group(0)) if m else {}


def _sources(cfg, include_reply_only):
    rows = [s for s in cfg.get('sources', []) if s.get('active', True)]
    if not include_reply_only:
        rows = [s for s in rows if s['sector'] != 'reply']
    return {s['handle'].lower(): s['sector'] for s in rows}


# ------------------------------------------------------------------ news
def run_news(cfg, dry=False):
    news = cfg.get('news', {})
    if not news.get('enabled', False):
        return log(cfg, 'news', 'SKIP news.enabled is false')
    sectors = news.get('sectors', {})
    t = now()
    if not dry and not in_posting_hours(cfg, t):
        return log(cfg, 'news', 'SKIP outside posting_hours')

    covered = [c for c in read_json(cfg, 'covered.json', []) if t.timestamp() - c['at'] < 14 * 86400]
    today = t.date().isoformat()
    left = news.get('max_posts_per_day', 3) - sum(1 for c in covered if c['day'] == today)
    if left <= 0 and not dry:
        return log(cfg, 'news', 'SKIP daily news cap reached')

    # Look back to the previous scan (so nothing is missed between runs), at least 3h, at most 24h.
    state = read_json(cfg, 'radar.json', {})
    last = state.get('last_news_scan', t.timestamp() - news.get('first_lookback_hours', 14) * 3600)
    since = int(max(min(last, t.timestamp() - 3 * 3600), t.timestamp() - 24 * 3600))

    by_handle = {h: s for h, s in _sources(cfg, False).items() if s in sectors}
    if not by_handle:
        raise RuntimeError('No active sources in a configured news sector. Check sources and news.sectors.')
    items = scrape(cfg, list(by_handle), since, news.get('max_items', 300))
    if not dry:
        write_json(cfg, 'radar.json', {**state, 'last_news_scan': t.timestamp()})
    cands = originals(items, by_handle, since, news.get('min_engagement', 50))
    # Top N per sector, so one loud sector (crypto, usually) can't fill the whole list.
    per = news.get('per_sector', 5)
    top = [c for s in sectors for c in [x for x in cands if x['sector'] == s][:per]]
    if not top:
        return log(cfg, 'news', f'SKIP no candidates ({len(items)} items scraped)')

    def covered_line(c):
        return f"{c['key']} ({c['sector']}, {'TODAY' if c['day'] == today else c['day']})"
    pools = {s: v.get('tags', []) for s, v in sectors.items()}
    user = ('Candidate posts:\n' + json.dumps([{k: c[k] for k in ('handle', 'sector', 'text', 'likes', 'reposts', 'per_hour')}
                                              for c in top], indent=1)
            + '\n\nAlready covered (last 14 days). TODAY means an earlier scan today posted it, and it is closed:\n'
            + ('\n'.join(map(covered_line, covered)) or '(none)'))
    verdict = _json(llm.complete(cfg, prompts.news_system(cfg, pools, max(left, 1)), user, 1200))
    story = verdict.get('story') if isinstance(verdict, dict) else None
    if not story or not story.get('post_body'):
        return log(cfg, 'news', f'QUIET no story picked from {len(top)} candidates')

    key = str(story.get('story_key') or 'story')[:80]
    if key in {c['key'] for c in covered}:
        return log(cfg, 'news', f'QUIET picked an already covered story ({key})')
    sector = story.get('sector', '')
    picked = {str(h).lstrip('@').lower() for h in story.get('source_handles') or []}
    # Figures must come from the story's own source posts, not from any candidate in the scan.
    source_text = ' '.join(c['text'] for c in top if c['handle'].lower() in picked)
    if not source_text:
        return log(cfg, 'news', f'SKIP story {key} names no watched source handle')
    fallback = sectors.get(sector, {}).get('fallback_tag') or (pools.get(sector) or ['#News'])[0]
    body, tags = gates.clamp_tags(str(story['post_body']), fallback)
    fails = gates.news_fails(body)
    if fails == ['too long']:  # the one failure worth a retry: compress once
        short = llm.complete(cfg, prompts.SHORTEN_SYSTEM,
                             'Compress this X post to under 240 characters INCLUDING the hashtags. Keep the '
                             'structure: hook, blank line, substance, blank line, closing question followed by '
                             'the hashtags on that same line.\n\n' + body, 600)
        long_body = body
        body, tags = gates.clamp_tags(short, fallback)
        fails = gates.news_fails(body) + gates.new_figures(body, long_body)
    fails += gates.unsourced_figures(body, source_text)
    if fails:
        return log(cfg, 'news', f'SKIP draft failed checks: {", ".join(fails)} | {body!r}')

    body = humanize(cfg, body, ' '.join(tags), 'Under 260 characters in total, hashtags included.',
                    lambda h: not gates.news_fails(h))
    if dry:
        return log(cfg, 'news', f'DRY would post ({len(body)} chars):\n{body}')
    if not in_posting_hours(cfg):  # a slow scrape can push a run past the window
        return log(cfg, 'news', 'SKIP posting window closed during the run')
    # Record the story BEFORE sending. If the send fails or the run dies, the story is not retried:
    # a missed post is cheap, a double post is not.
    entry = {'key': key, 'sector': sector, 'day': today, 'at': t.timestamp(), 'status': 'sending'}
    covered.append(entry)
    write_json(cfg, 'covered.json', covered)
    try:
        where = publish(cfg, body, 'news')
    except Exception:
        entry['status'] = 'failed'
        write_json(cfg, 'covered.json', covered)
        log(cfg, 'news', f'send failed for story {key}: check your account. It will not be retried.')
        raise
    entry['status'] = 'sent'
    write_json(cfg, 'covered.json', covered)
    log(cfg, 'news', f'OK {where}\n{body}')


def humanize(cfg, body, tags, size, still_ok):
    """One humanizer pass. Any failure keeps the gated draft: the humanizer can never cost a post."""
    if not cfg.get('humanizer', {}).get('enabled', True):
        return body
    try:
        h = llm.complete(cfg, prompts.humanize_system(cfg, tags, size), body, 800).strip()
    except Exception as e:  # noqa: BLE001
        log(cfg, 'humanize', f'kept draft, call failed: {e}')
        return body
    if (h and h.endswith(tags) and len(re.findall(gates.TAG, h)) == len(tags.split())
            and gates.same_facts(h, body) and still_ok(h)):
        return h
    log(cfg, 'humanize', 'kept draft, rewrite broke a check')
    return body


# ------------------------------------------------------------------ replies
def run_replies(cfg, dry=False):
    rc = cfg.get('replies', {})
    if not rc.get('enabled', False):
        return log(cfg, 'replies', 'SKIP replies.enabled is false')
    t = now()
    path = os.path.join(cfg['paths']['output_dir'], 'replies', t.date().isoformat() + '.md')
    if os.path.exists(path) and not dry:
        return log(cfg, 'replies', 'SKIP already written today')
    by_handle = _sources(cfg, True)
    since = int(t.timestamp() - 24 * 3600)
    items = scrape(cfg, list(by_handle), since, rc.get('max_items', 1500))
    picks, per_acct, caps = [], {}, dict(rc.get('sector_caps', {}))
    for c in originals(items, by_handle, since, rc.get('min_engagement', 100)):
        if len(picks) == rc.get('max', 25):
            break
        k = c['handle'].lower()
        if per_acct.get(k, 0) >= rc.get('per_account', 2) or caps.get(c['sector'], 1) <= 0:
            continue
        per_acct[k] = per_acct.get(k, 0) + 1
        if c['sector'] in caps:
            caps[c['sector']] -= 1
        m = re.search(r'status/(\d+)', c['url'])
        picks.append({**c, 'i': len(picks) + 1, 'status_id': m.group(1) if m else ''})
    if not picks:
        return log(cfg, 'replies', f'SKIP no targets ({len(items)} items scraped)')

    drafts = {}
    for _ in range(2):  # second pass fills anything the first left out
        todo = [p for p in picks if p['i'] not in drafts]
        if not todo:
            break
        try:
            out = _json(llm.complete(cfg, prompts.reply_system(cfg),
                                     json.dumps([{'i': p['i'], 'handle': p['handle'], 'text': p['text']} for p in todo], indent=1),
                                     8000))
            for r in out.get('replies', []):
                if isinstance(r.get('reply'), str) and r['reply'].strip():
                    drafts[r['i']] = r
        except Exception as e:  # noqa: BLE001
            log(cfg, 'replies', f'draft pass failed: {e}')

    md = reply_note(cfg, t.date().isoformat(), picks, drafts)
    if dry:
        return log(cfg, 'replies', f'DRY {len(picks)} targets, {len(drafts)} drafts\n' + md[:1500])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'w', encoding='utf-8').write(md)
    log(cfg, 'replies', f'OK {len(picks)} targets, {len(drafts)} drafts -> {path}')


def clean_reply(text):
    """A draft that breaks a rule is repaired, never dropped."""
    t = re.sub(r'\s*[–—]\s*', ', ', text)
    t = re.sub(r'https?://\S+', '', t)
    t = re.sub(r'(^|\s)[#@]([A-Za-z0-9_]+)', r'\1\2', t)
    t = re.sub(r'\s+([,.?!])', r'\1', re.sub(r'\s{2,}', ' ', t)).strip()
    if len(t) > 280:
        t = re.sub(r'\s+\S*$', '', t[:280]).rstrip(',;:') + '.'
    return t


def reply_note(cfg, date, picks, drafts):
    out = [f'# X reply queue, {date}', '',
           f'{len(picks)} posts to reply to as @{cfg["persona"]["handle"]}. Nothing here posts automatically.', '',
           'Tap **Reply on X** to open the reply box with the draft filled in, edit it, and post. Then come back '
           'and answer anyone who replies to you: those back-and-forths count for more than the first reply.', '']
    for p in picks:
        r = drafts.get(p['i'])
        d = clean_reply(r['reply']) if r else ''
        link = f"https://x.com/intent/tweet?in_reply_to={p['status_id']}" + (f'&text={urllib.parse.quote(d)}' if d else '')
        out += [f"## {p['i']}. @{p['handle']}", '',
                f"{p['likes']} likes, {p['reposts']} reposts, {p['age_hours']}h old at scan time", '',
                f"**[Reply on X]({link})** | [Open post]({p['url']})", '',
                '\n'.join('> ' + l for l in p['text'][:400].split('\n')), '',
                f'```text\n{d}\n```' if d else '**Draft:** failed, write your own.',
                (f"Angle: {r.get('angle', '')}" if d else ''), '', '- [ ] Posted', '']
    return '\n'.join(out)
