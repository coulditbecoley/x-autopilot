"""Config, secrets, state and logging. Standard library only."""
import contextlib
import datetime as dt
import json
import os
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_env(path=os.path.join(ROOT, '.env')):
    """Read KEY=value lines from .env into os.environ. Real environment variables win."""
    if not os.path.exists(path):
        return
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def secret(name, required=True):
    v = os.environ.get(name, '').strip()
    if required and not v:
        raise RuntimeError(f'{name} is not set. Add it to .env (see .env.example).')
    return v


def load_config(path=None):
    path = path or os.environ.get('XAUTO_CONFIG') or os.path.join(ROOT, 'config.json')
    if not os.path.exists(path):
        raise RuntimeError(f'No config at {path}. Copy config.example.json to config.json, or run SETUP.md with your AI.')
    cfg = json.load(open(path, encoding='utf-8'))
    paths = cfg.setdefault('paths', {})
    for key, default in (('state_dir', 'state'), ('output_dir', 'output')):
        p = os.path.expanduser(paths.get(key) or default)
        paths[key] = p if os.path.isabs(p) else os.path.join(ROOT, p)
        os.makedirs(paths[key], exist_ok=True)
    return cfg


def now():
    # ponytail: machine local time; run the scheduler on a machine set to your timezone
    return dt.datetime.now()


def read_json(cfg, name, default):
    p = os.path.join(cfg['paths']['state_dir'], name)
    if not os.path.exists(p):
        return default
    try:
        return json.load(open(p, encoding='utf-8'))
    except ValueError:
        # Fail closed: an empty history would let old stories and angles post again.
        raise RuntimeError(f'{p} is corrupt. Fix or delete it by hand, then rerun.') from None


def write_json(cfg, name, data):
    p = os.path.join(cfg['paths']['state_dir'], name)
    tmp = p + '.tmp'
    json.dump(data, open(tmp, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    os.replace(tmp, p)


@contextlib.contextmanager
def run_lock(cfg, wait_s=900):
    """One job at a time per state folder, so two overlapping runs can never both post.
    An OS file lock: the operating system releases it when the process exits, even after a crash."""
    f = open(os.path.join(cfg['paths']['state_dir'], 'run.lock'), 'a+')
    start = time.time()
    while True:
        try:
            if os.name == 'nt':
                import msvcrt
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError:
            if time.time() - start > wait_s:
                f.close()
                raise RuntimeError('another run has been holding state/run.lock for 15 minutes')
            time.sleep(5)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            if os.name == 'nt':
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def log(cfg, job, line):
    stamp = now().strftime('%Y-%m-%d %H:%M:%S')
    out = f'{stamp} [{job}] {line}'
    print(out)
    with open(os.path.join(cfg['paths']['state_dir'], 'run.log'), 'a', encoding='utf-8') as f:
        f.write(out + '\n')


def in_posting_hours(cfg, t=None):
    start, end = cfg.get('posting_hours', [8, 21])
    h = (t or now()).hour
    return start <= h < end
