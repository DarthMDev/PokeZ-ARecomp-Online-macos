import unittest

from auto_prepare import smoke_version

GATE = '[violetmp][gate] hooks installed: 0 address misses\n'
VERSION = '[update] this build is 1.4.0 build 0 (platform 2, channel 0)\n'
TITLE = '[ui] renderer ready (font 512x256)\n[ui] present 3: index 0\n'


class SmokeReadinessTest(unittest.TestCase):
    def test_title_screen_with_no_hud_is_ready(self):
        self.assertEqual(smoke_version(GATE + VERSION + TITLE), [1, 4, 0, 0])

    def test_hud_remains_a_valid_readiness_signal(self):
        self.assertEqual(smoke_version(GATE + VERSION + '[ui] HUD size: 1920x1080\n'), [1, 4, 0, 0])

    def test_missing_hooks_or_frames_is_not_ready(self):
        self.assertIsNone(smoke_version(VERSION + TITLE))
        self.assertIsNone(smoke_version(GATE + VERSION + '[ui] renderer ready\n[ui] present 2: index 0\n'))

    def test_eden_build_and_crash_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'not the recomp version'):
            smoke_version(GATE + VERSION.replace('platform 2', 'platform 0') + TITLE)
        with self.assertRaisesRegex(RuntimeError, 'crash'):
            smoke_version(GATE + VERSION + TITLE + '[crash] stopped\n')


if __name__ == '__main__':
    unittest.main()
