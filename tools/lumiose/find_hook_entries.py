"""Find branch entry points in private before/after module snapshots."""
import json
import os
import struct
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tools'))
from nso import Nso

scratch = Path(os.environ['LUMIOSE_SCRATCH'])
exefs = Path(os.environ.get('LUMIOSE_GAME_ROOT', scratch / 'extracted')) / 'exefs'
patched = Path(os.environ.get('LUMIOSE_PATCHED_DIR', scratch / 'patched')) / 'exefs'
module = Path(os.environ.get('LUMIOSE_SOURCE_MODULE', root / 'tools' / 'lumiose' / 'Lumiose Online' / 'exefs' / 'subsdk9'))
names = [('main', 0x7000000000, exefs / 'main'), ('sdk', 0x7008000000, exefs / 'sdk'),
         ('lumiose', 0x7006200000, module)]
modules = []
for name, base, original in names:
    newname = 'subsdk9' if name == 'lumiose' else name
    old, new = Nso(str(original)), Nso(str(patched / newname))
    modules.append((name, base, old, new))

entries = {name: set() for name, *_ in modules}
# The mod's printf formatter uses a jump table with destinations spanning discovered functions.
mod = modules[2][3]
if os.environ.get('LUMIOSE_UPDATE_TABLES'):
    tables = json.loads(os.environ['LUMIOSE_UPDATE_TABLES'])
elif mod.build_id.startswith('88ff7042cd22eb82'):
    tables = [(0x57fe98, 91, 'h', 0x136ac4), (0x194c10, 123, 'h', 0x364cc),
              (0x212360, 14, 'b', 0xc1d14)]
elif mod.build_id.startswith('96f2b142853fa151'):
    tables = [(0x57fdc8, 91, 'h', 0x136c44), (0x194b40, 123, 'h', 0x364cc),
              (0x212290, 14, 'b', 0xc1d74)]
elif mod.build_id.startswith('c79129fe1eea7843'):
    tables = [(0x5800b8, 91, 'h', 0x136d84), (0x194e30, 123, 'h', 0x364cc),
              (0x212580, 14, 'b', 0xc1da4)]
elif mod.build_id.startswith('8e2ea6e5a60f5cd6'):
    tables = [(0x57ec38, 91, 'h', 0x1358e4), (0x193a40, 123, 'h', 0x364cc),
              (0x211190, 14, 'b', 0xc1c44)]
else:
    raise SystemExit('Unknown Lumiose build: no verified jump tables available')
for offset, count, fmt, target_base in tables:
    for v in struct.unpack_from(f'<{count}{fmt}', mod.image, offset):
        entries['lumiose'].add(target_base + v * 4)

for name, base, old, new in modules:
    start, size = old.text
    for off in range(start, start + size - 3, 4):
        before = old.image[off:off + 4]
        after = new.image[off:off + 4]
        if before == after:
            continue
        if name == 'lumiose' and 0x3000 <= off < 0x9000:
            # Hooks write small callable trampolines into this originally empty code area.
            entries[name].add(off)
        word = struct.unpack('<I', after)[0]
        # A hook's trampoline returns to the instruction immediately after the patched site.
        if name != 'lumiose':
            entries[name].add(off + 4)
        if word & 0x7c000000 != 0x14000000:
            continue
        imm = word & 0x03ffffff
        if imm & 0x02000000:
            imm -= 0x04000000
        target = base + off + imm * 4
        for target_name, target_base, target_old, _ in modules:
            lo, length = target_old.text
            if target_base + lo <= target < target_base + lo + length:
                entries[target_name].add(target - target_base)

path = Path(os.environ.get('LUMIOSE_ENTRY_FILE', root / 'tools' / 'lumiose' / 'hook-entries.json'))
path.write_text(json.dumps({name: sorted(offsets) for name, offsets in entries.items()}, indent=2))
print({name: len(offsets) for name, offsets in entries.items()})
