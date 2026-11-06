"""Translate private patched snapshots into local-only C source files."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import os
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
scratch = Path(os.environ['LUMIOSE_SCRATCH'])
source = root
entries = json.loads(Path(os.environ.get('LUMIOSE_ENTRY_FILE', root / 'tools' / 'lumiose' / 'hook-entries.json')).read_text())
patched = Path(os.environ.get('LUMIOSE_PATCHED_DIR', scratch / 'patched'))
generated = Path(os.environ.get('LUMIOSE_GAME_GEN', scratch / 'generated'))
env = os.environ.copy()
env['PYTHONPATH'] = str(root / 'python-deps') + os.pathsep + env.get('PYTHONPATH', '')
for name, offsets in entries.items():
    env['LUMIOSE_TEST_ENTRIES_' + name.upper()] = ','.join(hex(x) for x in offsets)
python = sys.executable
jobs = [('main', 'main', '0x7000000000'), ('sdk', 'sdk', '0x7008000000'),
        ('lumiose', 'subsdk9', '0x7006200000')]
if os.environ.get('LUMIOSE_SKIP_GAME_GENERATION') == '1':
    jobs = [job for job in jobs if job[0] == 'lumiose']

def generate(job):
    name, nso, base = job
    out = generated / name
    out.mkdir(parents=True, exist_ok=True)
    cmd = [python, str(source / 'tools' / 'gen.py'), name, str(patched / 'exefs' / nso),
           base, str(out), '--simd', 'c']
    if name == 'sdk':
        cmd.extend(['--hle', str(source / 'runtime' / 'hle' / 'hle_symbols.txt')])
    with (scratch / ('generate-' + name + '.log')).open('w') as log:
        result = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    return name, result.returncode

with ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(generate, jobs))
for name, code in results:
    print(f'{name}: exit {code}')
if any(code for _, code in results):
    sys.exit(1)
