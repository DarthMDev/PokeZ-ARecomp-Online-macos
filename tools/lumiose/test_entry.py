import importlib.util
import json
import os
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('lumiose_entry', Path(__file__).with_name('entry.py'))
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class EntryTests(unittest.TestCase):
    def test_entry_version_matches_launcher(self):
        source = (Path(__file__).resolve().parents[2] / 'runtime/ui/launcher.mm').read_text(encoding='utf-8')
        version = re.search(r'^#define LARECOMP_VERSION "([^"]+)"', source, re.M)
        self.assertIsNotNone(version)
        self.assertEqual(entry.LAUNCHER_VERSION, version.group(1))

    def test_first_setup_prepares_mod_before_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'lumiose').mkdir()
            (root / 'extracted').mkdir()
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                if len(calls) == 1:
                    self.assertEqual(kwargs['env']['LUMIOSE_FIRST_SETUP'], '1')
                    (root / 'extracted' / (entry.GAME_LIBRARY + '.id')).write_text('game-id')
                    Path(kwargs['env']['LUMIOSE_SETUP_DONE']).write_text('ready')
                else:
                    (root / 'lumiose/config.json').write_text(json.dumps({'server': '127.0.0.1:1'}))
                    (root / 'lumiose/update-state.json').write_text('{}')
                return type('Result', (), {'returncode': 0})()
            cwd = os.getcwd()
            try:
                with patch.object(entry, 'ROOT', root), patch.object(entry.subprocess, 'run', side_effect=run), \
                     patch.object(entry, 'desktop_notice'), patch.object(entry, 'launch') as launch:
                    entry.main()
                self.assertEqual(len(calls), 2)
                self.assertEqual(Path(calls[1][1]).name, 'setup.py')
                launch.assert_called_once()
            finally:
                os.chdir(cwd)

    def test_existing_install_rechecks_once_and_marks_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'lumiose').mkdir(); (root / 'extracted').mkdir()
            (root / 'lumiose/update-state.json').write_text('{}')
            (root / 'lumiose/config.json').write_text(json.dumps({'server': '127.0.0.1:1'}))
            (root / 'extracted' / (entry.GAME_LIBRARY + '.id')).write_text('new-game-id')
            def run(command, **kwargs):
                Path(kwargs['env']['LUMIOSE_SETUP_DONE']).write_text('ready')
                return type('Result', (), {'returncode': 0})()
            cwd = os.getcwd()
            try:
                with patch.object(entry, 'ROOT', root), patch.object(entry.subprocess, 'run', side_effect=run) as preflight, \
                     patch.object(entry, 'launch') as launch:
                    entry.main(); entry.main()
                    preflight.assert_called_once(); self.assertEqual(launch.call_count, 2)
                    self.assertEqual((root / 'lumiose/launcher-code-revision.txt').read_text().strip(), entry.GAME_CODE_REVISION)
            finally:
                os.chdir(cwd)

    def test_closed_setup_does_not_accept_an_old_id(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'lumiose').mkdir(); (root / 'extracted').mkdir()
            (root / 'lumiose/update-state.json').write_text('{}')
            (root / 'extracted' / (entry.GAME_LIBRARY + '.id')).write_text('old-id')
            cwd = os.getcwd()
            try:
                with patch.object(entry, 'ROOT', root), patch.object(entry.subprocess, 'run') as preflight, \
                     patch.object(entry, 'launch') as launch:
                    preflight.return_value.returncode = 0
                    with self.assertRaisesRegex(RuntimeError, 'not completed'): entry.main()
                    launch.assert_not_called()
                    self.assertFalse((root / 'lumiose/launcher-code-revision.txt').exists())
            finally:
                os.chdir(cwd)

if __name__ == '__main__':
    unittest.main()
