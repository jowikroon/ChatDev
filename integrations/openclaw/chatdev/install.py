"""One-shot installer for the ChatDev skill on the Shadow PC (Windows). Started by INSTALL.bat.
  1. copies the client to C:\\AI\\chatdev-client
  2. writes ~/.openclaw/chatdev.env from the vault (_skill/adapters/.env), values never printed
  3. installs the skill into the OpenClaw skills folders it finds
  4. checks the connection (health + workflow list) and writes install-report.txt
"""
import datetime, glob, os, shutil, subprocess, sys

SRC = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser('~')
TARGET = os.environ.get('CHATDEV_CLIENT_DIR', r'C:\AI\chatdev-client' if os.name == 'nt' else os.path.join(HOME, 'AI', 'chatdev-client'))
OUT = os.path.join(HOME, 'Documents', 'ChatDev')
OC = os.path.join(HOME, '.openclaw')
ENV_OUT = os.path.join(OC, 'chatdev.env')
REPORT = []
# Which vault keys feed which client setting; the first one present wins.
KEYS = {'CHATDEV_CLIENT_ID': ('CHATDEV_CLIENT_ID', 'CF_ACCESS_CLAUDE_CLIENT_ID'),
        'CHATDEV_CLIENT_SECRET': ('CHATDEV_CLIENT_SECRET', 'CF_ACCESS_CLAUDE_CLIENT_SECRET'),
        'CHATDEV_URL': ('CHATDEV_URL',)}


def log(k, v):
    REPORT.append(f'{k}: {v}'); print(f'[{k}] {v}', flush=True)


def vault_env_files():
    roots = [os.environ.get('HANSOS_VAULT', '')]
    for docs in [os.path.join(HOME, 'Documents'), os.path.join(HOME, 'OneDrive', 'Documents')] + glob.glob(r'C:\Users\*\Documents'):
        roots.append(os.path.join(docs, 'SecondBrainVault'))
    seen = []
    for root in roots:
        path = os.path.join(root, '_skill', 'adapters', '.env') if root else ''
        if path and os.path.isfile(path) and path not in seen:
            seen.append(path)
    return seen


def read_env(path):
    values = {}
    for line in open(path, encoding='utf-8-sig', errors='replace'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def write_credentials():
    existing = read_env(ENV_OUT) if os.path.isfile(ENV_OUT) else {}
    found = {}
    for path in vault_env_files():
        vault = read_env(path)
        for out_key, sources in KEYS.items():
            for src in sources:
                if vault.get(src) and out_key not in found:
                    found[out_key] = vault[src]
        if 'CHATDEV_CLIENT_ID' in found and 'CHATDEV_CLIENT_SECRET' in found:
            log('credentials', f'service token read from {path}')
            break
    merged = {**existing, **found}
    if not (merged.get('CHATDEV_CLIENT_ID') and merged.get('CHATDEV_CLIENT_SECRET')):
        log('credentials', f'NOT FOUND. Put CHATDEV_CLIENT_ID and CHATDEV_CLIENT_SECRET in {ENV_OUT} '
                           '(or set HANSOS_VAULT to the vault folder) and run INSTALL.bat again')
        return False
    os.makedirs(OC, exist_ok=True)
    with open(ENV_OUT, 'w', encoding='utf-8') as fh:
        fh.write('# Written by the ChatDev skill installer. Keep private; never paste into a chat.\n')
        for k in ('CHATDEV_URL', 'CHATDEV_CLIENT_ID', 'CHATDEV_CLIENT_SECRET'):
            if merged.get(k):
                fh.write(f'{k}={merged[k]}\n')
    if os.name == 'nt':
        # Only the current user may read the token file.
        subprocess.run(['icacls', ENV_OUT, '/inheritance:r', '/grant:r', f'{os.environ.get("USERNAME", "")}:F'],
                       capture_output=True)
    log('credentials', f'written to {ENV_OUT} (values not shown)')
    return True


def install_skill():
    client = os.path.join(TARGET, 'scripts', 'chatdev.py')
    skill = open(os.path.join(SRC, 'SKILL.md'), encoding='utf-8').read()
    skill = skill.replace('{{CLIENT}}', client).replace('{{OUT}}', OUT)
    if not os.path.isdir(OC):
        log('OpenClaw', 'no ~/.openclaw folder found; skill not registered (client still works on its own)')
        return
    for d in (os.path.join(OC, 'workspace', 'skills'), os.path.join(OC, 'skills')):
        dst = os.path.join(d, 'chatdev')
        os.makedirs(dst, exist_ok=True)
        open(os.path.join(dst, 'SKILL.md'), 'w', encoding='utf-8').write(skill)
        log('OpenClaw skill installed', dst)
    log('OpenClaw', 'restart the OpenClaw gateway (or start a new session) so it loads the new skill')


def main():
    log('python', sys.version.split()[0])
    if os.path.normcase(os.path.realpath(SRC)) != os.path.normcase(os.path.realpath(TARGET)):
        shutil.rmtree(TARGET, ignore_errors=True)
        shutil.copytree(SRC, TARGET, ignore=shutil.ignore_patterns('__pycache__', 'install-report.txt'))
    # else: INSTALL.bat was started from the installed copy itself; keep it in place.
    os.makedirs(OUT, exist_ok=True)
    log('client', TARGET)
    has_creds = write_credentials()
    install_skill()
    if not has_creds:
        return finish(False)
    client = os.path.join(TARGET, 'scripts', 'chatdev.py')
    ok = True
    for cmd in ('health', 'workflows'):
        r = subprocess.run([sys.executable, client, cmd], capture_output=True, text=True)
        lines = (r.stdout or r.stderr).strip().splitlines()
        log(cmd, lines[0] if cmd == 'health' and lines else f'{len(lines)} workflows' if r.returncode == 0 else (r.stderr.strip() or 'failed'))
        ok = ok and r.returncode == 0
    return finish(ok)


def finish(ok):
    log('RESULT', 'INSTALL OK' if ok else 'INSTALL NOT COMPLETE, see lines above')
    path = os.path.join(TARGET if os.path.isdir(TARGET) else SRC, 'install-report.txt')
    open(path, 'w', encoding='utf-8').write(f'chatdev skill install {datetime.datetime.now():%Y-%m-%d %H:%M}\n' + '\n'.join(REPORT) + '\n')
    print('\nReport:', path)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
