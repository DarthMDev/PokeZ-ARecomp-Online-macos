import os
from pathlib import Path
import tempfile
import unittest

import auto_prepare


@unittest.skipIf(os.name == 'nt', 'POSIX isolated startup capture')
class LinuxCaptureTest(unittest.TestCase):
    def test_snapshot_and_version_from_live_log(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            exe = root / 'fake-launcher'
            exe.write_text("#!/bin/sh\n"
                           "echo '[violetmp][gate] hooks installed: 0 address misses'\n"
                           "echo '[lumiose test] wrote local module snapshots'\n"
                           "echo '[update] this build is 1.3.11 build 0 (platform 2, channel 0)'\n"
                           "echo '[ui] HUD size: 1280x720'\n"
                           "sleep 20\n")
            exe.chmod(0o755)
            args = (exe, root, root, root / 'mod', root / 'module.so', root / 'game.so', 'a' * 40)
            auto_prepare.capture(*args, snapshot=True, secs=5)
            self.assertEqual(auto_prepare.capture(*args, snapshot=False, secs=5), [1, 3, 11, 0])

if __name__ == '__main__':
    unittest.main()
