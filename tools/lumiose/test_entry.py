import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('lumiose_entry', Path(__file__).with_name('entry.py'))
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class EntryTests(unittest.TestCase):
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

if __name__ == '__main__':
    unittest.main()
