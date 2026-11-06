import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import setup


class InitialModTests(unittest.TestCase):
    def test_setup_prepares_bundled_mod_with_original_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game = root / 'extracted'
            mod = root / 'lumiose'
            tools = root / 'tools/lumiose'
            zig = root / 'zig'
            for directory in (game, mod, tools, zig, root / 'build'):
                directory.mkdir(parents=True, exist_ok=True)
            reference = mod / 'subsdk9'; reference.write_bytes(b'old reference')
            bundled = tools / 'prepackaged.subsdk9'; bundled.write_bytes(b'new mod')
            (root / setup.EXECUTABLE).write_bytes(b'executable')
            (game / setup.GAME_LIBRARY).write_bytes(b'game library placeholder')
            (game / (setup.GAME_LIBRARY + '.id')).write_text('id')
            (zig / setup.ZIG).write_bytes(b'zig')
            if setup.WINDOWS: (root / 'build/lasrecomp.dll.a').write_bytes(b'import library')
            def prepare(cmd, cwd):
                args = dict(zip(cmd[2::2], cmd[3::2]))
                self.assertEqual(Path(args['--reference']), reference)
                self.assertEqual(Path(args['--candidate']), bundled)
                work = Path(args['--work'])
                (work / 'input/exefs').mkdir(parents=True)
                (work / 'input/exefs/subsdk9').write_bytes(bundled.read_bytes())
                (work / setup.MODULE_LIBRARY).write_bytes(b'module')
                (work / setup.GAME_LIBRARY).write_bytes(b'local game library')
                (work / 'prepared.json').write_text(json.dumps({'build_id': 'a' * 40, 'version': [1, 4, 0, 0]}))
                return mock.Mock(returncode=0)
            with mock.patch.object(setup, 'ROOT', root), mock.patch.object(setup.subprocess, 'run', side_effect=prepare), \
                 mock.patch.object(sys, 'argv', ['setup.py', '--install', str(root), '--zig', str(zig), '--server', '127.0.0.1:1']):
                setup.main()
            state = json.loads((mod / 'update-state.json').read_text())
            self.assertEqual(state['version'], [1, 4, 0, 0])
            self.assertEqual(state['active_hashes']['subsdk9'], setup.sha(bundled))
            self.assertEqual(reference.read_bytes(), b'old reference')


if __name__ == '__main__': unittest.main()
