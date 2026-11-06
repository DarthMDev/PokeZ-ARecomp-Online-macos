import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('auto_launch', Path(__file__).with_name('auto_launch.py'))
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.install = self.root / 'install'
        self.mod = self.install / 'lumiose'
        self.mod.mkdir(parents=True)
        for name in ('subsdk9', 'lumiose.dll', 'lasgame.dll'):
            (self.mod / name).write_bytes(('old ' + name).encode())
        (self.mod / 'lasgame.dll.id').write_text('game-id')
        self.download = self.install / 'save/sdcard/atmosphere/contents/0100F43008C44000/exefs/subsdk9'
        self.download.parent.mkdir(parents=True)
        self.download.write_bytes(b'old download')
        self.state = self.mod / 'update-state.json'
        self.initial = {'build_id': 'a' * 40, 'version': [1, 3, 9, 1], 'download_hash': launcher.digest(self.download),
                        'active_hashes': {n: launcher.digest(self.mod / n)
                                          for n in ('subsdk9', 'lumiose.dll', 'lasgame.dll')}}
        launcher.write_state(self.state, self.initial)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({'install': str(self.install), 'reference': 'ref', 'vanilla': 'vanilla',
                                           'zig': 'zig', 'cache': 'cache', 'server': 'example:1'}))

    def tearDown(self): self.tmp.cleanup()

    def test_no_update_launches_active_version(self):
        with patch.object(launcher.subprocess, 'Popen') as launch:
            launcher.launch(self.config)
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(json.loads(self.state.read_text()), self.initial)

    def test_download_matching_active_module_is_not_rebuilt(self):
        self.download.write_bytes((self.mod / 'subsdk9').read_bytes())
        with patch.object(launcher.subprocess, 'run') as prepare, patch.object(launcher.subprocess, 'Popen') as launch:
            launcher.launch(self.config)
            prepare.assert_not_called()
            launch.assert_called_once()
            self.assertEqual(json.loads(self.state.read_text())['download_hash'], launcher.digest(self.download))

    def test_retagged_module_is_rebuilt_when_download_matches(self):
        self.download.write_bytes((self.mod / 'subsdk9').read_bytes())
        self.initial['force_rebuild_same_module'] = True
        launcher.write_state(self.state, self.initial)
        with patch.object(launcher.subprocess, 'run') as prepare, patch.object(launcher.subprocess, 'Popen') as launch:
            prepare.return_value.returncode = 1
            with self.assertRaisesRegex(RuntimeError, 'could not be prepared'):
                launcher.launch(self.config)
            prepare.assert_called_once()
            launch.assert_not_called()
            self.assertEqual(json.loads(self.state.read_text()), self.initial)

    def test_failed_preparation_blocks_launch_and_preserves_state(self):
        self.download.write_bytes(b'new download')
        with patch.object(launcher.subprocess, 'run') as run, patch.object(launcher.subprocess, 'Popen') as launch:
            run.return_value.returncode = 1
            with self.assertRaisesRegex(RuntimeError, 'could not be prepared'):
                launcher.launch(self.config)
            launch.assert_not_called()
            self.assertEqual(json.loads(self.state.read_text()), self.initial)

    def test_success_activates_complete_matching_set(self):
        self.download.write_bytes(b'new download')
        def prepare(cmd, **kwargs):
            work = Path(cmd[cmd.index('--work') + 1])
            staged = work / 'input/exefs/subsdk9'
            staged.parent.mkdir(parents=True)
            staged.write_bytes(self.download.read_bytes())
            (work / 'lumiose.dll').write_bytes(b'new module')
            (work / 'lasgame.dll').write_bytes(b'new game code')
            (work / 'prepared.json').write_text(json.dumps({'build_id': 'b' * 40, 'version': [1, 3, 10, 0]}))
            return type('Result', (), {'returncode': 0})()
        with patch.object(launcher.subprocess, 'run', side_effect=prepare), patch.object(launcher.subprocess, 'Popen') as launch:
            launcher.launch(self.config)
            self.assertEqual(launch.call_count, 1)
            state = json.loads(self.state.read_text())
            self.assertEqual(state['download_hash'], launcher.digest(self.download))
            self.assertEqual(state['build_id'], 'b' * 40)
            self.assertTrue((self.mod / 'versions' / state['version_dir'] / 'lasgame.dll').is_file())

    def test_older_download_is_not_activated(self):
        self.download.write_bytes(b'older download')
        def prepare(cmd, **kwargs):
            work = Path(cmd[cmd.index('--work') + 1])
            staged = work / 'input/exefs/subsdk9'
            staged.parent.mkdir(parents=True)
            staged.write_bytes(self.download.read_bytes())
            (work / 'prepared.json').write_text(json.dumps({'build_id': 'b' * 40, 'version': [1, 3, 8, 0]}))
            return type('Result', (), {'returncode': 0})()
        with patch.object(launcher.subprocess, 'run', side_effect=prepare), patch.object(launcher.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(RuntimeError, 'not newer'):
                launcher.launch(self.config)
            launch.assert_not_called()
            self.assertEqual(json.loads(self.state.read_text()), self.initial)


if __name__ == '__main__': unittest.main()
