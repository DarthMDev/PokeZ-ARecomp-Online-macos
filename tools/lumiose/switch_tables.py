"""Find bounded byte-indexed AArch64 switch targets in a mod snapshot."""
import re
import struct
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN


def discover_byte_switches(image, base, text_size):
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    decoder.skipdata = True
    instructions = list(decoder.disasm_lite(bytes(image[:text_size]), base))
    # A validated unsigned bound immediately before a branch to the dispatcher.
    bounds = {}
    for prev, ins in zip(instructions, instructions[1:]):
        if prev[2] != 'cmp' or ins[2] != 'b.ls': continue
        cmp = re.fullmatch(r'w(\d+), #(0x[0-9a-f]+|\d+)', prev[3])
        dst = re.fullmatch(r'#(0x[0-9a-f]+|\d+)', ins[3])
        if cmp and dst:
            count = int(cmp.group(2), 0) + 1
            if 1 <= count <= 128:
                bounds.setdefault(int(dst.group(1), 0), set()).add((cmp.group(1), count))
    found = []
    targets = set()
    for i in range(len(instructions) - 5):
        seq = instructions[i:i + 6]
        if [x[2] for x in seq] != ['adrp', 'add', 'ldrb', 'adr', 'add', 'br']: continue
        page = re.fullmatch(r'x(\d+), #(0x[0-9a-f]+|\d+)', seq[0][3])
        if not page: continue
        reg, page_addr = page.group(1), int(page.group(2), 0)
        add = re.fullmatch(r'x' + reg + r', x' + reg + r', #(0x[0-9a-f]+|\d+)', seq[1][3])
        load = re.fullmatch(r'w' + reg + r', \[x' + reg + r', w(\d+), uxtw\]', seq[2][3])
        adr = re.fullmatch(r'x(\d+), #(0x[0-9a-f]+|\d+)', seq[3][3])
        if not add or not load or not adr: continue
        if seq[4][3] != f'x{reg}, x{adr.group(1)}, w{reg}, sxtb #2' or seq[5][3] != f'x{reg}': continue
        options = {count for index_reg, count in bounds.get(seq[0][0], set()) if index_reg == load.group(1)}
        if len(options) != 1: continue
        count = options.pop()
        table = page_addr + int(add.group(1), 0) - base
        target_base = int(adr.group(2), 0) - base
        if table < 0 or table + count > len(image): continue
        offsets = struct.unpack_from(f'<{count}b', image, table)
        values = {target_base + value * 4 for value in offsets}
        if any(value < 0 or value >= text_size or value % 4 for value in values): continue
        targets.update(values)
        found.append((seq[0][0] - base, count, len(values)))
    return targets, found
