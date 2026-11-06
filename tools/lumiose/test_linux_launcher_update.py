import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

import linux_launcher_update as update


@unittest.skipIf(os.name == 'nt', 'Linux installation and symbolic-link semantics')
class LinuxLauncherUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'install'
        self.root.mkdir()
        self.archive = Path(self.temp.name) / 'update.zip'
        self.essential = {
            'Lumiose Online': b'new starter',
            'usr/bin/lasrecomp': b'new executable',
            'usr/bin/python/bin/python3.12': b'new python',
            'usr/bin/tools/lumiose/entry.py': b'new entry',
            'usr/bin/tools/lumiose/linux_launcher_update.py': b'new updater',
        }
        for rel, data in {'Lumiose Online': b'old starter', 'usr/bin/lasrecomp': b'old executable',
                          'usr/bin/save/main': b'player save', 'usr/bin/larecomp.ini': b'player settings',
                          'usr/bin/lumiose/update-state.json': b'player mod state'}.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def tearDown(self): self.temp.cleanup()

    def package(self, additions=None, links=None):
        with zipfile.ZipFile(self.archive, 'w') as z:
            for rel, content in {**self.essential, **(additions or {})}.items():
                info = zipfile.ZipInfo(update.PREFIX + rel)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o755) << 16
                z.writestr(info, content)
            for rel, target in (links or {}).items():
                info = zipfile.ZipInfo(update.PREFIX + rel)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, target)

    def test_install_preserves_player_data_and_symlinks(self):
        self.package({'usr/lib/libexample.so.1': b'library'}, {'usr/lib/libexample.so': 'libexample.so.1'})
        update.install(self.root, self.archive)
        self.assertEqual((self.root / 'usr/bin/lasrecomp').read_bytes(), b'new executable')
        self.assertEqual((self.root / 'usr/bin/save/main').read_bytes(), b'player save')
        self.assertEqual((self.root / 'usr/bin/larecomp.ini').read_bytes(), b'player settings')
        self.assertEqual((self.root / 'usr/bin/lumiose/update-state.json').read_bytes(), b'player mod state')
        self.assertEqual(os.readlink(self.root / 'usr/lib/libexample.so'), 'libexample.so.1')
        self.assertTrue(os.access(self.root / 'Lumiose Online', os.X_OK))
        self.assertFalse((self.root / '.lumiose-update').exists())

    def test_failure_restores_previous_files(self):
        self.package()
        with self.assertRaisesRegex(RuntimeError, 'Simulated'):
            update.install(self.root, self.archive, fail_after=3)
        self.assertEqual((self.root / 'Lumiose Online').read_bytes(), b'old starter')
        self.assertEqual((self.root / 'usr/bin/lasrecomp').read_bytes(), b'old executable')
        self.assertFalse((self.root / 'usr/bin/python/bin/python3.12').exists())
        self.assertEqual((self.root / 'usr/bin/save/main').read_bytes(), b'player save')
        self.assertFalse((self.root / '.lumiose-update').exists())

    def test_interrupted_install_recovers(self):
        backup = self.root / '.lumiose-update/backup/usr/bin'
        backup.mkdir(parents=True)
        (backup / 'lasrecomp').write_bytes(b'old executable')
        (self.root / 'usr/bin/lasrecomp').write_bytes(b'partly updated')
        journal = self.root / '.lumiose-update/journal.json'
        journal.write_text(json.dumps({'version': 1, 'entries': [{'path': 'usr/bin/lasrecomp', 'existed': True}]}))
        self.assertTrue(update.recover(self.root))
        self.assertEqual((self.root / 'usr/bin/lasrecomp').read_bytes(), b'old executable')
        self.assertFalse(journal.exists())

    def test_rejects_protected_paths_before_changing_anything(self):
        self.package({'usr/bin/save/main': b'overwrite'})
        with self.assertRaisesRegex(RuntimeError, 'protected'):
            update.install(self.root, self.archive)
        self.assertEqual((self.root / 'usr/bin/save/main').read_bytes(), b'player save')
        self.assertEqual((self.root / 'usr/bin/lasrecomp').read_bytes(), b'old executable')

    def test_rejects_escaping_symlink_and_path(self):
        self.package(links={'usr/lib/unsafe': '../../../outside'})
        with self.assertRaisesRegex(RuntimeError, 'escapes'):
            update.install(self.root, self.archive)
        self.package({'usr/bin/tools/../../save/main': b'overwrite'})
        with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
            update.install(self.root, self.archive)
        self.assertEqual((self.root / 'usr/bin/save/main').read_bytes(), b'player save')

    def test_rejects_symlink_in_existing_parent(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (self.root / 'usr/bin/tools').symlink_to(outside, target_is_directory=True)
        self.package()
        with self.assertRaisesRegex(RuntimeError, 'symbolic-link'):
            update.install(self.root, self.archive)
        self.assertEqual(list(outside.iterdir()), [])

if __name__ == '__main__': unittest.main()
