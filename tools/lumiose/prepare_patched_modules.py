"""Build private NSO test inputs from local snapshots; never modify installed files."""
import hashlib
import os
import struct
import sys
from pathlib import Path

import lz4.block

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tools'))
from nso import Nso

scratch = Path(os.environ['LUMIOSE_SCRATCH'])
original = Path(os.environ.get('LUMIOSE_GAME_ROOT', scratch / 'extracted')) / 'exefs'
mod = Path(os.environ.get('LUMIOSE_SOURCE_MODULE', root / 'tools' / 'lumiose' / 'Lumiose Online' / 'exefs' / 'subsdk9'))
out = Path(os.environ.get('LUMIOSE_PATCHED_DIR', scratch / 'patched')) / 'exefs'
out.mkdir(parents=True, exist_ok=True)

for name, src in [('main', original / 'main'), ('sdk', original / 'sdk'), ('subsdk9', mod)]:
    raw = src.read_bytes()
    nso = Nso(str(src))
    image = (scratch / (name + '.image')).read_bytes()
    off, length = nso.text
    replacement = image[off:off + length]
    before = bytes(nso.image[off:off + length])
    changed = sum(a != b for a, b in zip(before, replacement))
    header = bytearray(raw[:0x100])
    flags = struct.unpack_from('<I', header, 0xc)[0]
    segments = []
    for i in range(3):
        file_offset, memory_offset, size = struct.unpack_from('<III', header, 0x10 + i * 0x10)
        compressed_size = struct.unpack_from('<I', header, 0x60 + i * 4)[0]
        data = raw[file_offset:file_offset + compressed_size]
        if i == 0:
            data = lz4.block.compress(replacement, store_size=False) if flags & 1 else replacement
            header[0xa0:0xc0] = hashlib.sha256(replacement).digest()
        segments.append(data)
    pos = len(header)
    for i, data in enumerate(segments):
        struct.pack_into('<I', header, 0x10 + i * 0x10, pos)
        struct.pack_into('<I', header, 0x60 + i * 4, len(data))
        pos += len(data)
    (out / name).write_bytes(header + b''.join(segments))
    check = Nso(str(out / name))
    assert check.image[off:off + length] == replacement
    print(f'{name}: {changed} changed text bytes')
