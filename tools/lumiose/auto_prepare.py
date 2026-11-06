"""Prepare a downloaded Lumiose NSO and its matching native game code.

This command operates only in --work; it never installs or changes a save.
The reference is the verified 1.3.9 recomp module used to locate signatures.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from nso import Nso

TABLES_139 = [(0x57fdc8, 91, 'h', 0x136c44), (0x194b40, 123, 'h', 0x364cc),
              (0x212290, 14, 'b', 0xc1d74)]


def unique(data, signature, description):
    pos = data.find(signature)
    if pos < 0 or data.find(signature, pos + 1) >= 0:
        raise RuntimeError(f'{description} changed or is ambiguous; this update needs compatibility work')
    return pos


def tables_for(reference, candidate):
    old, new = Nso(str(reference)), Nso(str(candidate))
    if not old.build_id.startswith('96f2b142853fa151'):
        raise RuntimeError('The 1.3.9 compatibility reference is missing or incorrect')
    data = bytes(new.image)
    for off in (0x15248, 0x152f0):
        # The BL destination can move; the return address and surrounding
        # camera-query instructions must retain the same meaning.
        if (bytes(old.image[off - 12:off - 4]) != bytes(new.image[off - 12:off - 4]) or
                bytes(old.image[off:off + 12]) != bytes(new.image[off:off + 12])):
            raise RuntimeError('Camera integration changed; this update needs compatibility work')
        def branch_target(module):
            word = struct.unpack_from('<I', module.image, off - 4)[0]
            if word >> 26 != 0b100101: raise RuntimeError('Camera query call changed')
            value = word & 0x3ffffff
            return off - 4 + (value - (1 << 26) if value & (1 << 25) else value) * 4
        a, b = branch_target(old), branch_target(new)
        if min(a, b) < 0 or a + 16 > old.text[1] or b + 16 > new.text[1] or \
                bytes(old.image[a:a + 16]) != bytes(new.image[b:b + 16]):
            raise RuntimeError('Camera query implementation changed')
    found = []
    for off, count, fmt, base in TABLES_139:
        table = bytes(old.image[off:off + count * struct.calcsize(fmt)])
        target = bytes(old.image[base:base + 32])
        noff = unique(data, table, 'Jump table')
        nbase = unique(data[:new.text[1]], target, 'Jump table destination')
        found.append((noff, count, fmt, nbase))
    return new, found


def run(command, env, log):
    step = Path(command[-1]).name if len(command) == 2 else Path(command[1]).name
    print('Preparing:', step, flush=True)
    with Path(log).open('w', encoding='utf-8') as f:
        p = subprocess.Popen(command, cwd=ROOT, env=env, stdout=f, stderr=subprocess.STDOUT)
        last = ''
        while True:
            try:
                p.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                pass
            progress_file = Path(log).parent / 'generate-main.log' if step == 'generate_patched.py' else Path(log)
            try:
                lines = progress_file.read_text(encoding='utf-8', errors='replace').splitlines()
                recent = next((line for line in reversed(lines) if 'progress ' in line or
                               line.startswith('Prepared ') or line.startswith('Compiled ')), '')
            except OSError:
                recent = ''
            if recent and recent != last:
                print('  ' + recent, flush=True)
                last = recent
    if p.returncode:
        raise RuntimeError(f'Preparation failed (see {log})')


def capture(exe, game, work, module, library, gamelib, build_id, *, snapshot, secs=60):
    env = os.environ.copy()
    env.update(LARECOMP_DATA_ROOT=str(work), LARECOMP_SAVE_DIR=str(work / 'isolated-save'),
               LARECOMP_NO_LAUNCHER='1', LARECOMP_HIDDEN='1', LARECOMP_NO_UPDATE_CHECK='1',
               LUMIOSE_TEST_MODULE=str(module), LUMIOSE_TEST_LIBRARY=str(library),
               LARECOMP_GAME_LIB=str(gamelib), LUMIOSE_TEST_OFFLINE_CAPTURE='1',
               LUMIOSE_PREPARE_BUILD_ID=build_id)
    for key in ('LARECOMP_INPUT', 'LUMIOSE_TEST_NETWORK', 'LUMIOSE_TEST_DROP_FILE', 'LARECOMP_REBOOT_AT'):
        env.pop(key, None)
    if snapshot:
        env['LUMIOSE_TEST_DUMP'] = str(work)
    else:
        env.pop('LUMIOSE_TEST_DUMP', None)
    env['PATH'] = str(exe.parent) + os.pathsep + env.get('PATH', '')
    log = work / ('capture.log' if snapshot else 'smoke.log')
    with log.open('w', encoding='utf-8') as f:
        p = subprocess.Popen([str(exe), str(game), '--play'], cwd=str(exe.parent), env=env,
                             stdout=f, stderr=subprocess.STDOUT,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            start = time.monotonic()
            while time.monotonic() - start < secs:
                if p.poll() is not None:
                    raise RuntimeError(f'Isolated startup exited unexpectedly (see {log})')
                time.sleep(1)
                contents = log.read_text(errors='replace')
                if '[violetmp][gate] hooks installed: 0 address misses' not in contents:
                    continue
                if snapshot and '[lumiose test] wrote local module snapshots' in contents:
                    return
                if not snapshot and '[ui] HUD size:' in contents:
                    version = re.search(r'\[update\] this build is (\d+)\.(\d+)\.(\d+) build (\d+) \(platform (\d+), channel (\d+)\)', contents)
                    if not version:
                        raise RuntimeError('The updated mod did not identify its version')
                    if int(version.group(5)) != 2:
                        raise RuntimeError('The download is not the recomp version of Lumiose')
                    return [int(x) for x in version.groups()[:4]]
            raise RuntimeError(f'Isolated startup did not finish (see {log})')
        finally:
            p.terminate()
            try: p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill(); p.wait()


def patch_generated(work):
    root = work / 'generated' / 'lumiose'
    matches = [p for p in root.glob('lumiose_*.c') if 'void f_7006237cb0(Cpu *c) {' in p.read_text()]
    if len(matches) != 1:
        raise RuntimeError('Trainer-name compatibility code has changed')
    source = matches[0].read_text()
    targets = re.findall(r'c->x\[30\] = 0x7006237d80ull; (f_[0-9a-f]+)\(c\);', source)
    if len(targets) != 1:
        raise RuntimeError('Trainer-name compatibility call has changed')
    # The adjustment script checks each expected instruction before changing it.
    patch = (ROOT / 'tools' / 'lumiose' / 'preserve_name_139.py').read_text()
    patch = patch.replace('f_700632ce40(c)', targets[0] + '(c)')
    previous = os.environ.get('LUMIOSE_SCRATCH')
    os.environ['LUMIOSE_SCRATCH'] = str(work)
    try:
        exec(compile(patch, 'preserve_name_139.py', 'exec'), {})
        exec(compile((ROOT / 'tools' / 'lumiose' / 'optimize_camera_139.py').read_text(),
                     'optimize_camera_139.py', 'exec'), {})
    finally:
        if previous is None: os.environ.pop('LUMIOSE_SCRATCH', None)
        else: os.environ['LUMIOSE_SCRATCH'] = previous


def main():
    p = argparse.ArgumentParser()
    for arg in ('candidate', 'reference', 'game', 'vanilla', 'exe', 'zig', 'cache', 'work'):
        p.add_argument('--' + arg, type=Path, required=True)
    a = p.parse_args()
    for name in ('candidate', 'reference', 'game', 'vanilla', 'exe', 'zig', 'cache', 'work'):
        setattr(a, name, getattr(a, name).resolve())
    a.work.mkdir(parents=True, exist_ok=True)
    if any(a.work.iterdir()): raise RuntimeError('Work folder must be empty')
    candidate, tables = tables_for(a.reference, a.candidate)
    if len(candidate.build_id) != 40: raise RuntimeError('Invalid module build ID')
    print('Preparing Lumiose build', candidate.build_id, flush=True)
    staged = a.work / 'input' / 'exefs'
    staged.mkdir(parents=True)
    shutil.copy2(a.candidate, staged / 'subsdk9')
    shutil.copy2(a.game / 'exefs' / 'main', staged / 'main')
    env = os.environ.copy()
    env.update(PYTHONPATH=str(ROOT / 'python-deps') + os.pathsep + os.environ.get('PYTHONPATH', ''), LUMIOSE_SCRATCH=str(a.work),
               LUMIOSE_SOURCE_MODULE=str(staged / 'subsdk9'), LUMIOSE_GAME_ROOT=str(a.game),
               LUMIOSE_ENTRY_FILE=str(a.work / 'entries.json'), LUMIOSE_ZIG_DIR=str(a.zig),
               LUMIOSE_GAME_CACHE=str(a.cache), LUMIOSE_UPDATE_TABLES=json.dumps(tables),
               LUMIOSE_GAME_ID_FILE=str(a.vanilla) + '.id')
    entries = set()
    for off, count, fmt, base in tables:
        entries.update(base + v * 4 for v in struct.unpack_from(f'<{count}{fmt}', candidate.image, off))
    env['LUMIOSE_TEST_ENTRIES_LUMIOSE'] = ','.join(hex(x) for x in entries)
    bootstrap = a.work / 'generated' / 'bootstrap'
    bootstrap.mkdir(parents=True)
    py = sys.executable
    gen = ROOT / 'tools' / 'gen.py'
    run([py, str(gen), 'lumiose', str(staged / 'subsdk9'), '0x7006200000', str(bootstrap), '--simd', 'c'],
        env, a.work / 'bootstrap-generation.log')
    env.update(LUMIOSE_GENERATED_DIR=str(bootstrap), LUMIOSE_MODULE_OBJECT_DIR=str(a.work / 'bootstrap-objects'),
               LUMIOSE_LIBRARY_OUTPUT=str(a.work / 'bootstrap.dll'))
    run([py, str(ROOT / 'tools' / 'lumiose' / 'build_module.py')], env, a.work / 'bootstrap-build.log')
    capture(a.exe, a.game, a.work, staged / 'subsdk9', a.work / 'bootstrap.dll', a.vanilla,
            candidate.build_id, snapshot=True)
    for script in ('prepare_patched_modules.py', 'find_hook_entries.py', 'generate_patched.py'):
        run([py, str(ROOT / 'tools' / 'lumiose' / script)], env, a.work / (script + '.log'))
    patch_generated(a.work)
    env.update(LUMIOSE_GENERATED_DIR=str(a.work / 'generated' / 'lumiose'),
               LUMIOSE_MODULE_OBJECT_DIR=str(a.work / 'module-objects'),
               LUMIOSE_LIBRARY_OUTPUT=str(a.work / 'lumiose.dll'),
               LUMIOSE_GAME_OUTPUT=str(a.work / 'lasgame.dll'))
    for script in ('build_module.py', 'build_patched_game.py'):
        run([py, str(ROOT / 'tools' / 'lumiose' / script)], env, a.work / (script + '.log'))
    version = capture(a.exe, a.game, a.work, staged / 'subsdk9', a.work / 'lumiose.dll', a.work / 'lasgame.dll',
                      candidate.build_id, snapshot=False)
    (a.work / 'prepared.json').write_text(json.dumps({'build_id': candidate.build_id, 'version': version}) + '\n')
    print('Update prepared and startup verified.', flush=True)


if __name__ == '__main__':
    try: main()
    except Exception as e:
        print('Update preparation failed:', e, file=sys.stderr)
        sys.exit(1)
