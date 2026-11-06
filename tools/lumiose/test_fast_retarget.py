import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fast_retarget import MODULE_BASE, current_cache, external_branch_target, retarget


def branch(pc, target, opcode=0x14000000):
    return opcode | (((target - pc) // 4) & 0x3ffffff)


class FastRetargetTests(unittest.TestCase):
    def test_only_unconditional_branches_into_mod_are_accepted(self):
        pc = 0x7000001000
        module = SimpleNamespace(text=(0, 0x200000))
        target = MODULE_BASE + 0x1234
        self.assertEqual(external_branch_target(branch(pc, target), pc, module), target)
        with self.assertRaises(ValueError):
            external_branch_target(branch(pc, target, 0x94000000), pc, module)
        with self.assertRaises(ValueError):
            external_branch_target(branch(pc, pc + 0x100), pc, module)

    def test_invalid_or_changed_cache_falls_back_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, work = root / 'cache', root / 'work'
            cache.mkdir(); work.mkdir()
            (cache / 'manifest.json').write_text(json.dumps({'fingerprint': 'old'}))
            with patch('fast_retarget.fingerprint', return_value='new'):
                self.assertFalse(retarget(cache, work))
            self.assertFalse((work / 'generated').exists())

    def test_cache_pointer_cannot_escape_its_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'current.json').write_text(json.dumps({'directory': '../elsewhere'}))
            self.assertIsNone(current_cache(root))


if __name__ == '__main__': unittest.main()
