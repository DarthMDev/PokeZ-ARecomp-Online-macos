"""Start the packaged launcher, preparing Lumiose after initial game setup."""
import os
from pathlib import Path
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools' / 'lumiose'))
from auto_launch import launch
from platform_paths import EXECUTABLE, GAME_LIBRARY, lock_file


def desktop_notice(title, message, error=False):
    if os.name == 'nt': return
    command = shutil.which('kdialog') if error else shutil.which('notify-send')
    if command:
        args = [command, '--error', title + '\n\n' + message] if error else [command, title, message]
        try: subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError: pass


def main():
    os.chdir(ROOT)
    os.environ['PYTHONPATH'] = str(ROOT / 'python-deps') + os.pathsep + os.environ.get('PYTHONPATH', '')
    mod = ROOT / 'lumiose'
    config = mod / 'config.json'
    state = mod / 'update-state.json'
    if not state.exists():
        print('First-time setup: choose your own Pokémon Legends Z-A 2.0.2 game files in the launcher.', flush=True)
        print('When game setup finishes, Lumiose will be prepared automatically. Keep this window open.', flush=True)
        env = os.environ.copy()
        env['LARECOMP_DATA_ROOT'] = str(ROOT)
        env['LUMIOSE_FIRST_SETUP'] = '1'
        for key in ('LUMIOSE_TEST_MODULE', 'LUMIOSE_TEST_LIBRARY', 'LARECOMP_GAME_LIB',
                    'LARECOMP_NO_LAUNCHER', 'LUMIOSE_TEST_OFFLINE_CAPTURE'):
            env.pop(key, None)
        if os.environ.get('LUMIOSE_RELEASE_TEST_PREPARE_ONLY') != '1':
            env.pop('LARECOMP_HIDDEN', None)
        result = subprocess.run([str(ROOT / EXECUTABLE), str(ROOT / 'extracted')], cwd=ROOT, env=env)
        if result.returncode or not (ROOT / 'extracted' / (GAME_LIBRARY + '.id')).is_file():
            raise RuntimeError('Game setup was not completed. Start Lumiose Online again when you are ready.')
        cmd = [sys.executable, str(ROOT / 'tools/lumiose/setup.py'), '--install', str(ROOT),
               '--zig', str(ROOT / 'zig'), '--server', '135.148.167.226:27777']
        desktop_notice('Lumiose Online', 'Preparing the online mod. This may take several minutes.')
        if subprocess.run(cmd, cwd=ROOT).returncode:
            raise RuntimeError('Lumiose preparation did not finish; see the message above.')
    if not config.is_file():
        raise RuntimeError('Lumiose configuration is missing. Your save files have not been changed.')
    # Rewrite paths when the player moves the installed folder.
    import json
    cfg = json.loads(config.read_text(encoding='utf-8'))
    cfg.update(install=str(ROOT), reference=str(ROOT / 'lumiose/subsdk9'),
               vanilla=str(ROOT / 'extracted' / GAME_LIBRARY), zig=str(ROOT / 'zig'),
               cache=str(ROOT / 'extracted/.gamebuild'))
    config.write_text(json.dumps(cfg, indent=2) + '\n', encoding='utf-8')
    launch(config, prepare_only=os.environ.get('LUMIOSE_RELEASE_TEST_PREPARE_ONLY') == '1')


if __name__ == '__main__':
    if os.name != 'nt' and not sys.stderr.isatty():
        log_dir = ROOT / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        log = (log_dir / 'lumiose-launch.log').open('a', encoding='utf-8', buffering=1)
        sys.stdout = sys.stderr = log
    try:
        lock_path = ROOT / 'lumiose' / 'update.lock'
        with lock_path.open('a+b') as lock:
            try: lock_file(lock)
            except OSError: raise RuntimeError('Another Lumiose launcher is already preparing an update')
            main()
    except Exception as e:
        print('\nLumiose could not start:', e, file=sys.stderr, flush=True)
        desktop_notice('Lumiose Online could not start', str(e) + '\nDetails: logs/lumiose-launch.log', error=True)
        if sys.stdin.isatty(): input('Press Enter to close this window. ')
        sys.exit(1)
