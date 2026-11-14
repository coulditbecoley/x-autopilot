"""x-autopilot command line.

  python run.py news      [--dry-run]   scan the watched accounts, post at most one real story
  python run.py replies   [--dry-run]   write today's reply queue (never posts)
  python run.py build     [--dry-run]   today's short personal post from your notes or commits
  python run.py long      [--dry-run]   today's long post, written to output/long for you to post by hand
  python run.py doctor                  check config, keys and the model connection
  python run.py selftest                offline checks of every gate (no keys, no network)

--dry-run drafts everything and prints it, posts nothing, writes no state.
--config PATH uses another config file (one per account).
"""
import argparse
import os
import sys
import traceback

from xauto import buildpost, core, gates, llm, radar
from xauto.publish import oauth1_header


def selftest():
    # Hashtags: clamp to two, move to the end, fall back when missing.
    body, tags = gates.clamp_tags('#AI Big news today.\n\nWhat changes for you? #LLM #Extra', '#AI')
    assert body == 'Big news today.\n\nWhat changes for you? #AI #LLM' and tags == ['#AI', '#LLM'], body
    assert gates.clamp_tags('No tags here?', '#WebDev')[0] == 'No tags here? #WebDev'
    assert gates.clamp_tags('Claude hit #1 today. Why? #AI', '#AI')[0] == 'Claude hit #1 today. Why? #AI'
    # News gates.
    assert gates.news_fails('Short and fine.\n\nWould you switch? #AI') == []
    assert 'no closing question' in gates.news_fails('A statement. #AI')
    assert 'link' in gates.news_fails('See https://x.com now? #AI')
    assert 'em or en dash' in gates.news_fails('It shipped — finally? #AI')
    assert 'too long' in gates.news_fails('x' * 281)
    assert 'token-like string' in gates.news_fails('Leaked sk-abcdefghijklmnopqrstuvwxyz12. Why? #AI')
    assert gates.unsourced_figures('Up 12% per @a99. Why? #Web3', 'rose 12% today') == []
    assert gates.unsourced_figures('Up 999%. Why? #AI', 'rose 2% today') == ['figure 999 is not in the source']
    assert gates.new_figures('2 tools shipped', '2 tools, 999 attendees') == []
    assert gates.new_figures('999 tools shipped', '2 tools shipped') == ['figure 999 changed in the rewrite']
    assert gates.new_figures('999 tools for 999 people', '2 tools for 999 people') == ['figure 999 changed in the rewrite']
    # A rewrite may not change facts.
    assert gates.same_facts('Up 12% per @a. Why? #AI', 'It rose 12% per @a. Why? #AI')
    assert not gates.same_facts('Up 12% per @a.', 'Up 15% per @a.')
    # Privacy lint.
    deny, names = ['secretclient', 'projectx'], ['Claude Code', 'Codex']
    src = 'Codex ran 8 rounds and 720 tests passed.'
    ok = 'Codex found bugs two reviews missed.\n\nIt took 8 rounds.\n\nHow many do you run? #AI #Codex'
    assert gates.privacy_fails(ok, src, deny, names) == [], gates.privacy_fails(ok, src, deny, names)
    for post, why in {'Shipped SecretClient today. #AI': 'deny', 'Shipped it. #SecretClient': 'deny tag', 'Ran 9 rounds. #AI': 'figure',
                      'See github.com/x. #AI': 'link', 'Fixed ABC-1482. #AI': 'ticket',
                      'Thanks to Jordan Example. #AI': 'name', 'Shipped it — finally. #AI': 'dash',
                      'No tags here.': 'tags', '#AI shipped it.': 'end', 'Key abcdefghijklmnopqrstuvwxyz0123 #AI': 'token'}.items():
        assert gates.privacy_fails(post, src, deny, names), f'{why}: expected a failure for {post!r}'
    long_ok = 'Codex found bugs two reviews missed.\n\n' + 'It took 8 rounds to get there. ' * 25 + '\n\n#AI #Codex'
    assert gates.privacy_fails(long_ok, src, deny, names, 2200, 600) == []
    assert any('under 600' in f for f in gates.privacy_fails(ok, src, deny, names, 2200, 600))
    # Reply cleanup repairs instead of dropping.
    assert radar.clean_reply('Fair — but see https://a.b #tag @bob') == 'Fair, but see tag bob'
    # Scraper filter: originals only, deduped, sorted by velocity.
    now = core.now().timestamp()
    iso = lambda h: __import__('datetime').datetime.fromtimestamp(now - h * 3600).astimezone().isoformat()
    items = [
        {'id': '1', 'text': 'Slow', 'createdAt': iso(10), 'likeCount': 100, 'author': {'userName': 'A'}},
        {'id': '2', 'text': 'Fast', 'createdAt': iso(1), 'likeCount': 100, 'author': {'userName': 'A'}},
        {'id': '2', 'text': 'Fast', 'createdAt': iso(1), 'likeCount': 100, 'author': {'userName': 'A'}},
        {'id': '3', 'text': 'RT @x hi', 'createdAt': iso(1), 'likeCount': 900, 'author': {'userName': 'A'}},
        {'id': '4', 'text': 'Reply', 'isReply': True, 'createdAt': iso(1), 'likeCount': 900, 'author': {'userName': 'A'}},
        {'id': '5', 'text': 'Old', 'createdAt': iso(30), 'likeCount': 900, 'author': {'userName': 'A'}},
        {'id': '6', 'text': 'Unwatched', 'createdAt': iso(1), 'likeCount': 900, 'author': {'userName': 'B'}},
        {'id': '7', 'text': 'Quiet', 'createdAt': iso(1), 'likeCount': 3, 'author': {'userName': 'A'}},
    ]
    got = radar.originals(items, {'a': 'ai'}, now - 24 * 3600, 50)
    assert [g['text'] for g in got] == ['Fast', 'Slow'], got
    assert radar._epoch('Wed Oct 10 20:19:24 +0000 2018') > 0
    # OAuth 1.0a signature: the worked example from X's "Creating a signature" docs.
    h = oauth1_header('POST', 'https://api.twitter.com/1.1/statuses/update.json',
                      'xvz1evFS4wEEPTGEFPHBog', 'kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw',
                      '370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb', 'LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE',
                      params={'status': 'Hello Ladies + Gentlemen, a signed OAuth request!', 'include_entities': 'true'},
                      nonce='kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg', stamp=1318622958)
    assert 'oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"' in h, h  # gitleaks:allow (public example from X's docs)
    print('selftest ok')


def doctor(cfg):
    ok = True
    def say(good, line):
        nonlocal ok
        ok &= good
        print(('  ok   ' if good else '  FIX  ') + line)
    p = cfg.get('persona', {})
    say(bool(p.get('name') and p.get('handle') and p.get('handle') != 'yourhandle'), 'persona name and handle set')
    pub = cfg.get('publisher', {}).get('type', 'drafts')
    need = {'x': ['X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET'],
            'zernio': ['ZERNIO_API_KEY', 'ZERNIO_ACCOUNT_ID'], 'webhook': ['WEBHOOK_URL'], 'drafts': []}.get(pub)
    say(need is not None, f'publisher.type = {pub}')
    for k in need or []:
        say(bool(os.environ.get(k)), f'{k} present')
    if cfg.get('news', {}).get('enabled') or cfg.get('replies', {}).get('enabled'):
        say(bool(os.environ.get('APIFY_TOKEN')), 'APIFY_TOKEN present (news and replies scrape with it)')
        say(any(s.get('active', True) for s in cfg.get('sources', [])), 'at least one active source')
    if cfg.get('build_post', {}).get('enabled'):
        n = buildpost.notes_text(cfg, core.now().date())
        say(bool(n), f'build_post finds notes or commits in the lookback window ({len(n)} chars)')
    try:
        reply = llm.complete(cfg, 'Reply with the single word: ready', 'Are you there?', 20)
        say('ready' in reply.lower(), f"model answers ({cfg.get('llm', {}).get('provider', 'anthropic')}): {reply[:40]!r}")
    except Exception as e:  # noqa: BLE001
        say(False, f'model call failed: {e}')
    print('\nAll good.' if ok else '\nFix the FIX lines, then run doctor again.')
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=['news', 'replies', 'build', 'long', 'doctor', 'selftest'])
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--config')
    a = ap.parse_args()
    if a.command == 'selftest':
        return selftest()
    core.load_env()
    cfg = core.load_config(a.config)
    try:
        if a.command == 'doctor':
            sys.exit(0 if doctor(cfg) else 1)
        with core.run_lock(cfg):
            {'news': lambda: radar.run_news(cfg, a.dry_run), 'replies': lambda: radar.run_replies(cfg, a.dry_run),
             'build': lambda: buildpost.run(cfg, a.dry_run), 'long': lambda: buildpost.run(cfg, a.dry_run, True)}[a.command]()
    except Exception as e:  # noqa: BLE001  every failure lands in state/run.log
        core.log(cfg, a.command, f'FAIL {type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}')
        sys.exit(1)


if __name__ == '__main__':
    main()
