import struct
import unittest
from switch_tables import discover_byte_switches


class ByteSwitchTests(unittest.TestCase):
    def image(self):
        # Synthetic AArch64: cmp w0,#10; b.ls dispatcher; an 11-way
        # signed-byte jump table at +0x100 and code targets based at +0x38.
        data = bytearray(0x200)
        for off in range(0, 0x100, 4): struct.pack_into('<I', data, off, 0xd503201f)  # nop
        words = {0: 0x7100281f, 4: 0x540000e9, 0x20: 0x90000001,
                 0x24: 0x91040021, 0x28: 0x38604821, 0x2c: 0x10000060,
                 0x30: 0x8b218801, 0x34: 0xd61f0020}
        for off, word in words.items(): struct.pack_into('<I', data, off, word)
        data[0x100:0x10b] = bytes(range(11))
        return data

    def test_finds_all_bounded_targets(self):
        targets, tables = discover_byte_switches(self.image(), 0x100000, 0x100)
        self.assertEqual(targets, {0x38 + 4*i for i in range(11)})
        self.assertEqual(tables, [(0x20, 11, 11)])

    def test_ignores_unbounded_or_out_of_range(self):
        data = self.image(); struct.pack_into('<I', data, 4, 0xd503201f)
        self.assertEqual(discover_byte_switches(data, 0x100000, 0x100)[0], set())
        data = self.image(); data[0x100] = 127
        self.assertEqual(discover_byte_switches(data, 0x100000, 0x100)[0], set())


if __name__ == '__main__': unittest.main()
