"""Launch Lumiose, preparing a newly downloaded update before starting it."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import msvcrt

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    if not path.is_file(): return None
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def write_state(path, state):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def launch(config_path, prepare_only=False):
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    install = Path(cfg['install']).resolve()
    game = install / 'extracted'
    mod_dir = install / 'lumiose'
    state_path = mod_dir / 'update-state.json'
    candidate = install / 'save' / 'sdcard' / 'atmosphere' / 'contents' / '0100F43008C44000' / 'exefs' / 'subsdk9'
    if not state_path.is_file():
        raise RuntimeError('Update setup is incomplete; no mod was started')
    state = json.loads(state_path.read_text(encoding='utf-8'))
    id_file = mod_dir / 'lasgame.dll.id'
    if not id_file.is_file():
        raise RuntimeError('The game-code identification file is missing')
    baseline = state.get('download_hash')
    current_hash = digest(candidate)
    active_name = state.get('version_dir')
    if active_name and Path(active_name).name != active_name:
        raise RuntimeError('Invalid active update path')
    active_module = (mod_dir / 'versions' / active_name if active_name else mod_dir) / 'subsdk9'
    if (current_hash and current_hash != baseline and not state.get('force_rebuild_same_module') and
            current_hash == state.get('active_hashes', {}).get('subsdk9')):
        if digest(active_module) != current_hash:
            raise RuntimeError('The active mod failed verification')
        state['download_hash'] = current_hash
        write_state(state_path, state)
        baseline = current_hash
    if current_hash and current_hash != baseline:
        print('A Lumiose update was downloaded. Preparing it for ZA Recomp...', flush=True)
        # Keep all generated files outside the active installation until verified.
        work_root = mod_dir / 'update-work'
        work_root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix='prepare-', dir=work_root))
        cmd = [sys.executable, str(ROOT / 'tools' / 'lumiose' / 'auto_prepare.py'),
               '--candidate', str(candidate), '--reference', cfg['reference'],
               '--game', str(game), '--vanilla', cfg['vanilla'], '--exe', str(install / 'lasrecomp.exe'),
               '--zig', cfg['zig'], '--cache', cfg['cache'], '--work', str(work)]
        if subprocess.run(cmd, cwd=ROOT).returncode:
            raise RuntimeError(f'The update could not be prepared. Details are in {work}')
        if digest(candidate) != current_hash:
            raise RuntimeError('The download changed while being prepared; please start the launcher again')
        if digest(work / 'input' / 'exefs' / 'subsdk9') != current_hash:
            raise RuntimeError('The downloaded file changed while it was being copied')
        result = json.loads((work / 'prepared.json').read_text())
        build_id = result['build_id']
        if len(build_id) != 40 or any(c not in '0123456789abcdef' for c in build_id):
            raise RuntimeError('The prepared update has an invalid build ID')
        version = result.get('version')
        if (not isinstance(version, list) or len(version) != 4 or
                any(not isinstance(x, int) or x < 0 for x in version)):
            raise RuntimeError('The prepared update has an invalid version')
        if tuple(version) <= tuple(state.get('version', [])):
            raise RuntimeError('The downloaded mod is not newer than the active version')
        versions = mod_dir / 'versions'
        versions.mkdir(exist_ok=True)
        name = build_id + '-' + current_hash[:16]
        target = versions / name
        files = ((work / 'input' / 'exefs' / 'subsdk9', 'subsdk9'),
                 (work / 'lumiose.dll', 'lumiose.dll'), (work / 'lasgame.dll', 'lasgame.dll'),
                 (id_file, 'lasgame.dll.id'))
        if target.exists():
            if any(digest(src) != digest(target / dst) for src, dst in files):
                raise RuntimeError('A different prepared version already exists; update was not activated')
        else:
            stage = Path(tempfile.mkdtemp(prefix=name + '-', dir=versions))
            for src, dst in files:
                shutil.copy2(src, stage / dst)
                if digest(src) != digest(stage / dst): raise RuntimeError('An update file failed verification')
            os.replace(stage, target)
        state = {'download_hash': current_hash, 'build_id': build_id, 'version': version, 'version_dir': name,
                 'active_hashes': {dst: digest(target / dst) for _, dst in files}}
        # The pointer is the only active-state change, after all three files exist.
        write_state(state_path, state)
        # This directory was created solely for this preparation attempt.
        try: shutil.rmtree(work)
        except OSError: pass  # A leftover build cache is safe to remove later.
        print('Lumiose update prepared and applied.', flush=True)
    version = state.get('version_dir')
    if version:
        if Path(version).name != version: raise RuntimeError('Invalid active update path')
        active = mod_dir / 'versions' / version
    else:
        active = mod_dir
    if active != mod_dir and not (active / 'lasgame.dll.id').is_file():
        # Repair versions produced by the earlier updater, which omitted this
        # launcher-side identification file even though the library was valid.
        shutil.copy2(id_file, active / 'lasgame.dll.id')
    if digest(active / 'lasgame.dll.id') != digest(id_file):
        raise RuntimeError('The active game-code identification does not match')
    for name in ('subsdk9', 'lumiose.dll', 'lasgame.dll'):
        if not (active / name).is_file(): raise RuntimeError(f'The active mod is missing {name}')
        if state.get('active_hashes', {}).get(name) != digest(active / name):
            raise RuntimeError(f'The active mod file {name} failed verification')
    env = os.environ.copy()
    env.update(LARECOMP_DATA_ROOT=str(install), LARECOMP_GAME_LIB=str(active / 'lasgame.dll'),
               LUMIOSE_TEST_MODULE=str(active / 'subsdk9'), LUMIOSE_TEST_LIBRARY=str(active / 'lumiose.dll'),
               LUMIOSE_TEST_NETWORK='1', LUMIOSE_TEST_SERVER=cfg['server'],
               LARECOMP_DISABLE_OCCLUSION_CULLING='1',
               LUMIOSE_PREPARE_BUILD_ID=state['build_id'])
    for key in ('LARECOMP_NO_LAUNCHER', 'LARECOMP_NO_UPDATE_CHECK', 'LARECOMP_HIDDEN', 'LUMIOSE_TEST_OFFLINE_CAPTURE',
                'LUMIOSE_TEST_DUMP', 'LUMIOSE_TEST_DROP_FILE'):
        env.pop(key, None)
    if not prepare_only:
        subprocess.Popen([str(install / 'lasrecomp.exe'), str(game)], cwd=str(install), env=env,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


if __name__ == '__main__':
    try:
        if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != '--prepare-only'):
            raise RuntimeError('Missing update configuration')
        config_path = Path(sys.argv[1]).resolve()
        cfg = json.loads(config_path.read_text(encoding='utf-8'))
        lock_path = Path(cfg['install']) / 'lumiose' / 'update.lock'
        with lock_path.open('a+b') as lock:
            lock.seek(0)
            if not lock.read(1): lock.write(b'0'); lock.flush()
            lock.seek(0)
            try: msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError: raise RuntimeError('Another Lumiose launcher is already preparing an update')
            launch(config_path, prepare_only=len(sys.argv) == 3)
    except Exception as e:
        print('\nLumiose could not start:', e, file=sys.stderr)
        print('Your save was not changed by the update preparation.', file=sys.stderr)
        sys.exit(1)
