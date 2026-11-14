"""One function, three ways to reach a model. Pick one with llm.provider in config.json.

anthropic   Anthropic API, needs ANTHROPIC_API_KEY
openai      OpenAI API, needs OPENAI_API_KEY (the right choice for Codex users)
claude-cli  your logged-in Claude Code (`claude -p`) with every tool and MCP server off, no API key

The Codex CLI is not offered here: it has no tool-free mode, and these jobs feed it scraped posts,
which are untrusted text. Codex can still install and configure this repo through SETUP.md.
"""
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request

from .core import secret


def _post(url, headers, body, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method='POST',
                                 headers={'Content-Type': 'application/json', **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _cli(name):
    path = shutil.which(name) or shutil.which(name + '.cmd')
    if not path:
        raise RuntimeError(f'`{name}` is not on PATH. Install it or switch llm.provider.')
    return path


SECRET_VARS = ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'APIFY_TOKEN', 'X_API_KEY', 'X_API_SECRET',
               'X_ACCESS_TOKEN', 'X_ACCESS_TOKEN_SECRET', 'ZERNIO_API_KEY', 'ZERNIO_ACCOUNT_ID', 'WEBHOOK_URL')


def _run_isolated(cmd, prompt, timeout):
    """Scraped posts are untrusted text. The CLI gets an empty working folder and none of our keys."""
    env = {k: v for k, v in os.environ.items() if k not in SECRET_VARS}
    with tempfile.TemporaryDirectory() as cwd:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding='utf-8',
                           timeout=timeout, cwd=cwd, env=env)
    if r.returncode:
        raise RuntimeError(f'{os.path.basename(cmd[0])} exited {r.returncode}: {r.stderr.strip()[-300:]}')
    return r.stdout


def complete(cfg, system, user, max_tokens=1500):
    llm = cfg.get('llm', {})
    provider = llm.get('provider', 'anthropic')
    model = llm.get('model')

    if provider == 'anthropic':
        # ponytail: newer models think before answering and thinking spends max_tokens, so leave headroom
        max_tokens = min(max(max_tokens * 4, 4000), 16000)
        r = _post('https://api.anthropic.com/v1/messages',
                  {'x-api-key': secret('ANTHROPIC_API_KEY'), 'anthropic-version': '2023-06-01'},
                  {'model': model or 'claude-opus-5-5', 'max_tokens': max_tokens, 'system': system,
                   'messages': [{'role': 'user', 'content': user}]})
        return ''.join(c.get('text', '') for c in r.get('content', [])).strip()

    if provider == 'openai':
        r = _post('https://api.openai.com/v1/chat/completions',
                  {'Authorization': 'Bearer ' + secret('OPENAI_API_KEY')},
                  {'model': model or 'gpt-5', 'messages': [{'role': 'system', 'content': system},
                                                           {'role': 'user', 'content': user}]})
        return r['choices'][0]['message']['content'].strip()

    prompt = system + '\n\n---\n\n' + user
    if provider == 'claude-cli':
        # No built-in tools and no MCP servers: the model only turns text into text.
        cmd = [_cli('claude'), '-p', '--tools', '', '--strict-mcp-config'] + (['--model', model] if model else [])
        return _run_isolated(cmd, prompt, 600).strip()

    raise RuntimeError(f'Unknown llm.provider "{provider}". Use anthropic, openai or claude-cli.')
