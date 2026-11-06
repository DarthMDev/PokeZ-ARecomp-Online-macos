"""Checks function discovery for modules without an exception-frame header."""
import struct
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze import eh_frame_functions


class EhFrameTests(unittest.TestCase):
    def test_empty_range_ignores_unrelated_bytes(self):
        image = bytearray(64)
        image[16:20] = b'\x10\x00\x00\x00'
        self.assertEqual(eh_frame_functions(SimpleNamespace(image=image, eh_start=16, eh_end=16)), [])

    def test_nonempty_header_still_discovers_functions(self):
        image = bytearray(64)
        image[16:20] = bytes((1, 3, 3, 3))
        struct.pack_into('<IIII', image, 20, 0, 1, 40, 0)
        self.assertEqual(eh_frame_functions(SimpleNamespace(image=image, eh_start=16, eh_end=36)), [40])


if __name__ == '__main__':
    unittest.main()
