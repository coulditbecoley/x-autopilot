"""Mechanical checks. No model here: these run after every draft and decide what may go out.

A prompt can ask for 1 or 2 hashtags, no links and no dashes. Only code can promise it.
"""
import os
import re
from collections import Counter

TAG = r'#[A-Za-z][A-Za-z0-9_]*'   # needs a letter after '#', so "#1" and "bill #1234" stay prose
NUM = r'\d+(?:[.,]\d+)*'


def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


def clamp_tags(text, fallback_tag):
    """Keep the first two hashtags and move them to the very end. Add the fallback if there are none."""
    tags = re.findall(TAG, text)[:2] or [fallback_tag]
    body = re.sub(TAG, '', text)
    body = re.sub(r'[ \t]{2,}', ' ', body)
    body = re.sub(r'[ \t]+\n', '\n', body).strip()
    return body + ' ' + ' '.join(tags), tags


def prose_of(text):
    return re.sub(r'(\s*' + TAG + r')+\s*$', '', text).strip()


def news_fails(text, max_len=280):
    fails = []
    if len(text) > max_len:
        fails.append('too long')
    if re.search('[—–]', text):
        fails.append('em or en dash')
    if not prose_of(text).endswith('?'):
        fails.append('no closing question')
    if re.search(r'https?://', text):
        fails.append('link')
    if re.search(r'[A-Za-z0-9_\-]{24,}', prose_of(text).replace('@', ' ')):
        fails.append('token-like string')
    return fails


def new_figures(after, before):
    """Figures a rewrite introduced. Dropping one is fine; adding or changing one is not."""
    nums = lambda t: Counter(re.findall(NUM, re.sub(r'@[A-Za-z0-9_]+|' + TAG, ' ', t)))
    extra = nums(after) - nums(before)  # counts, so "2 tools, 999 people" can't become "999 tools, 999 people"
    return [f'figure {n} changed in the rewrite' for n in sorted(extra)]


def unsourced_figures(text, source):
    """Figures in the post (ignoring @handles and hashtags) that never appear in the source."""
    prose = re.sub(r'@[A-Za-z0-9_]+|' + TAG, ' ', text)
    src = set(re.findall(NUM, source))
    return [f'figure {n} is not in the source' for n in re.findall(NUM, prose) if n not in src]


def same_facts(a, b):
    """A rewrite may not add, drop or change a figure or an @handle."""
    nums = lambda t: sorted(re.findall(r'\d[\d,.]*\d|\d', t))
    handles = lambda t: sorted(re.findall(r'@[A-Za-z0-9_]+', t))
    return nums(a) == nums(b) and handles(a) == handles(b)


def deny_terms(bp):
    """Explicit deny terms plus every folder name under deny_from_folders (your private projects)."""
    allowed = {norm(n) for n in bp.get('allowed_names', [])}
    common = {norm(w) for w in bp.get('common_folder_words', [])}
    terms = {t.lower() for t in bp.get('deny_terms', [])}
    for root in bp.get('deny_from_folders', []):
        root = os.path.expanduser(root)
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            if not os.path.isdir(os.path.join(root, name)):
                continue
            for cand in {name, re.split(r'[-_ ]', name)[0]}:
                n = norm(cand)
                if len(n) >= 4 and n not in allowed and n not in common:
                    terms.add(n)
    return sorted(terms)


def privacy_fails(post, source_text, deny, allowed_names, max_len=280, min_len=0):
    """Reasons a personal post may not go out. Empty list means it may. Fails closed:
    a false positive costs a redraft, a false negative costs a leak."""
    fails = []
    if len(post) > max_len:
        fails.append(f'over {max_len} characters')
    if len(post) < min_len:
        fails.append(f'under {min_len} characters')
    if re.search('[—–]', post):
        fails.append('em or en dash')
    if re.search(r'https?://|www\.|\b[\w-]+\.(com|io|ai|app|dev|net|org|co|sh|xyz)\b', post, re.I):
        fails.append('link or domain')
    if '@' in post:
        fails.append('@ mention or email')
    if re.search(r'[A-Za-z]:\\|/Users/|/home/|~/|\.env\b', post):
        fails.append('file path')
    if re.search(r'\b[A-Z]{2,6}-\d+\b|#\d+\b|\bPR\s*\d+|\b(?=[0-9a-f]*\d)[0-9a-f]{7,40}\b', post):
        fails.append('ticket, PR or commit id')
    if re.search(r'[A-Za-z0-9_\-]{24,}', post):
        fails.append('token-like string')
    tags = re.findall(TAG, post)
    if not 1 <= len(tags) <= 2:
        fails.append('needs 1 or 2 hashtags')
    elif not re.search(r'(\s' + TAG + r'){%d}\s*$' % len(tags), ' ' + post):
        fails.append('hashtags not at the very end')
    prose = re.sub(TAG, '', post)
    # Deny terms are checked against the WHOLE post, hashtags included (#SecretClient is a leak too).
    flat, low = norm(post), ' ' + re.sub(r'[^a-z0-9]+', ' ', post.lower()) + ' '
    for t in deny:
        n = norm(t)
        if (len(n) >= 6 and n in flat) or f' {t} ' in low or f' {n} ' in low:
            fails.append(f'names a private project or client ({t})')
    known = {w.lower() for n in allowed_names for w in n.split()} | {
        'i', 'ai', 'x', 'api', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday',
        'sunday', 'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
        'september', 'october', 'november', 'december'}
    # Two capitalized words in a row that are not allowed names: probably a person, client or product.
    for a, b in re.findall(r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b', prose):
        if a.lower() not in known and b.lower() not in known:
            fails.append(f'possible name "{a} {b}"')
    # Anti-fabrication: every figure must already be in the source notes.
    src = set(re.findall(NUM, source_text))
    for num in re.findall(NUM, prose):
        if num not in src:
            fails.append(f'figure {num} is not in the notes')
    return fails
