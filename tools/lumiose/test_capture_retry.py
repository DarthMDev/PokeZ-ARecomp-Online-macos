from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import auto_prepare


class FakeProcess:
    def __init__(self, text, output):
        self.running = True
        if text:
            output.write(text)
            output.flush()

    def poll(self): return None if self.running else 0
    def terminate(self): self.running = False
    def wait(self, timeout=None): return 0


class CaptureRetryTest(unittest.TestCase):
    def capture(self, text_by_attempt):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        attempts = []
        def start(*args, **kwargs):
            text = text_by_attempt[len(attempts)]
            attempts.append(text)
            return FakeProcess(text, kwargs['stdout'])
        with patch.object(auto_prepare.subprocess, 'Popen', side_effect=start), patch.object(auto_prepare.time, 'sleep'):
            auto_prepare.capture(root / 'app', root, root, root / 'mod', root / 'lib', root / 'game', 'a' * 40,
                                 snapshot=True, secs=0.05)
        return attempts

    def test_empty_start_is_retried_once(self):
        ready = '[violetmp][gate] hooks installed: 0 address misses\n[lumiose test] wrote local module snapshots\n'
        self.assertEqual(len(self.capture(['', ready])), 2)

    def test_reported_crash_is_not_retried(self):
        with self.assertRaisesRegex(RuntimeError, 'reported a crash'):
            self.capture(['[crash] failure\n'])

    def test_nonempty_stall_is_not_retried(self):
        with self.assertRaisesRegex(RuntimeError, 'did not finish'):
            self.capture(['[info] loading\n'])


if __name__ == '__main__':
    unittest.main()
