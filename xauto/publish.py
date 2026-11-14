"""Where a finished post goes. Pick one with publisher.type in config.json.

drafts   nothing is posted; each post is written to output/drafts/<date>.md with a
         one-tap "Post on X" link. Safest way to start, and the default.
x        X API v2 directly (POST /2/tweets), OAuth 1.0a user context.
         Needs X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET.
zernio   Zernio (zernio.com), which holds the X connection for you.
         Needs ZERNIO_API_KEY and ZERNIO_ACCOUNT_ID.
webhook  POSTs {"text", "kind"} as JSON to WEBHOOK_URL: Buffer via Zapier or Make,
         n8n, your own app, anything that takes a webhook.

Adding another tool is one more branch in publish(); SETUP.md tells your AI how.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets as rnd
import time
import urllib.error
import urllib.parse
import urllib.request

from .core import now, secret

X_TWEETS = 'https://api.x.com/2/tweets'


def _enc(s):
    return urllib.parse.quote(str(s), safe='~')


def oauth1_header(method, url, ck, cs, tk, ts, params=None, nonce=None, stamp=None):
    """OAuth 1.0a HMAC-SHA1 header. A JSON body is not signed; form or query params are."""
    oauth = {'oauth_consumer_key': ck, 'oauth_nonce': nonce or rnd.token_hex(16),
             'oauth_signature_method': 'HMAC-SHA1', 'oauth_timestamp': str(stamp or int(time.time())),
             'oauth_token': tk, 'oauth_version': '1.0'}
    allp = {**(params or {}), **oauth}
    base_params = '&'.join(f'{k}={v}' for k, v in sorted((_enc(k), _enc(v)) for k, v in allp.items()))
    base = '&'.join([method.upper(), _enc(url), _enc(base_params)])
    key = f'{_enc(cs)}&{_enc(ts)}'.encode()
    oauth['oauth_signature'] = base64.b64encode(hmac.new(key, base.encode(), hashlib.sha1).digest()).decode()
    return 'OAuth ' + ', '.join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(oauth.items()))


def _send(url, body, headers, timeout=30, lenient=False):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                 headers={'Content-Type': 'application/json', **headers})
    host = urllib.parse.urlsplit(url).netloc  # never log the full URL: a webhook URL is often a secret
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'{host} returned HTTP {e.code}') from None
    except urllib.error.URLError as e:
        raise RuntimeError(f'could not reach {host}: {e.reason}') from None
    try:
        return json.loads(raw or b'{}')
    except ValueError:
        if lenient:
            return {}  # a webhook's plain-text "Accepted" is still a success
        raise RuntimeError(f'{host} answered with something that is not JSON; check whether it posted') from None


def intent_link(text):
    return 'https://x.com/intent/tweet?text=' + urllib.parse.quote(text)


def write_draft(cfg, text, kind):
    folder = os.path.join(cfg['paths']['output_dir'], 'drafts')
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, now().date().isoformat() + '.md')
    with open(path, 'a', encoding='utf-8') as f:
        f.write(f'## {now():%H:%M} {kind}\n\n[Post on X]({intent_link(text)})\n\n```text\n{text}\n```\n\n- [ ] Posted\n\n')
    return path


def publish(cfg, text, kind):
    """Publish one post now. Returns a short description of where it went."""
    kind_type = cfg.get('publisher', {}).get('type', 'drafts')

    if kind_type == 'drafts':
        return 'draft written to ' + write_draft(cfg, text, kind)

    if kind_type == 'x':
        auth = oauth1_header('POST', X_TWEETS, secret('X_API_KEY'), secret('X_API_SECRET'),
                             secret('X_ACCESS_TOKEN'), secret('X_ACCESS_TOKEN_SECRET'))
        r = _send(X_TWEETS, {'text': text}, {'Authorization': auth})
        pid = (r.get('data') or {}).get('id')
        if not pid:
            raise RuntimeError('X answered without a post id; check whether it posted')
        return 'posted to X, id ' + str(pid)

    if kind_type == 'zernio':
        # Idempotency-Key: a retry after a lost response returns the original post, never a second one.
        key = hashlib.sha256((now().date().isoformat() + text).encode()).hexdigest()[:40]
        r = _send('https://zernio.com/api/v1/posts',
                  {'content': text, 'publishNow': True,
                   'platforms': [{'platform': 'twitter', 'accountId': secret('ZERNIO_ACCOUNT_ID')}]},
                  {'Authorization': 'Bearer ' + secret('ZERNIO_API_KEY'), 'Idempotency-Key': key})
        pid = (r.get('post') or {}).get('_id') or r.get('_id')
        if not pid:
            raise RuntimeError('Zernio answered without a post id; check whether it posted')
        return 'sent to Zernio, ' + str(pid)

    if kind_type == 'webhook':
        _send(secret('WEBHOOK_URL'), {'text': text, 'kind': kind}, {}, lenient=True)
        return 'sent to webhook'

    raise RuntimeError(f'Unknown publisher.type "{kind_type}". Use drafts, x, zernio or webhook.')
