"""Reuse a local translation when only external Lumiose branches changed.

All cached game data is generated locally from the player's own game. Any
unrecognized change returns False so the caller performs a full translation.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile

FILE = Path(__file__).resolve()
ROOT = FILE.parents[2] if FILE.parent.name == 'lumiose' else FILE.parents[1]
SOURCE = ROOT if FILE.parent.name == 'lumiose' else ROOT / 'zarecomp-source'
sys.path.insert(0, str(SOURCE / 'tools'))
from nso import Nso

MODULE_BASE = 0x7006200000
BASES = {'main': 0x7000000000, 'sdk': 0x7008000000}
GENERATOR_FILES = ('gen.py', 'nso.py', 'analyze.py', 'lifter.py', 'flagfuse.py',
                   'regpromote.py', 'simd_c.py', 'passes.py', 'patches.py',
                   'za_patches.py', 'game_addresses.py')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def fingerprint():
    import capstone
    import unicorn
    h = hashlib.sha256()
    h.update(f'lumiose-retarget-v1;python={sys.version_info[:2]};simd=c;'.encode())
    h.update(f'capstone={capstone.__version__};unicorn={unicorn.__version__}'.encode())
    files = [SOURCE / 'tools' / name for name in GENERATOR_FILES]
    files += [SOURCE / 'tools/rando/patch_variants.json', SOURCE / 'runtime/hle/hle_symbols.txt']
    for f in files:
        h.update(str(f.relative_to(SOURCE)).encode())
        h.update(bytes.fromhex(digest(f)))
    return h.hexdigest()


def external_branch_target(word, pc, module):
    # Only unconditional B is accepted: no changes to calls, instruction
    # boundaries, jump tables, or the game's internal control flow.
    if word >> 26 != 0b000101: raise ValueError('Not an unconditional branch')
    off = word & 0x3ffffff
    if off & 0x2000000: off -= 0x4000000
    target = pc + off * 4
    start, length = module.text
    if not MODULE_BASE + start <= target < MODULE_BASE + start + length:
        raise ValueError('Branch does not target Lumiose text')
    return target


def retarget(cache, work):
    """Produce work/generated/{main,sdk} or return False; never edit cache."""
    cache, work = Path(cache), Path(work)
    try:
        meta = json.loads((cache / 'manifest.json').read_text())
        if meta['fingerprint'] != fingerprint(): return False
        for name, wanted in meta['inputs'].items():
            if digest(cache / name) != wanted: return False
        previous = json.loads((cache / 'entries.json').read_text())
        current = json.loads((work / 'entries.json').read_text())
        if any(previous[k] != current[k] for k in BASES): return False
        old_mod = Nso(str(cache / 'patched/exefs/subsdk9'))
        new_mod = Nso(str(work / 'patched/exefs/subsdk9'))
        changes = {}
        for name, base in BASES.items():
            old = Nso(str(cache / 'patched/exefs' / name))
            new = Nso(str(work / 'patched/exefs' / name))
            if old.build_id != new.build_id or old.text != new.text or old.size != new.size: return False
            start, length = old.text
            if (old.image[:start] != new.image[:start] or
                    old.image[start + length:] != new.image[start + length:]): return False
            edits = {}
            for off in range(start, start + length, 4):
                a = struct.unpack_from('<I', old.image, off)[0]
                b = struct.unpack_from('<I', new.image, off)[0]
                if a == b: continue
                pc = base + off
                old_target = external_branch_target(a, pc, old_mod)
                new_target = external_branch_target(b, pc, new_mod)
                marker = f'L_{pc:x}:;'.encode()
                before = f'c->pc = 0x{old_target:x}ull; __attribute__((musttail)) return rt_dispatch(c);'.encode()
                after = f'c->pc = 0x{new_target:x}ull; __attribute__((musttail)) return rt_dispatch(c);'.encode()
                edits[marker] = (before, after)
            changes[name] = edits
        staging = Path(tempfile.mkdtemp(prefix='retarget-', dir=work))
        seen = {name: set() for name in BASES}
        for name in BASES:
            srcdir = cache / 'generated' / name
            outdir = staging / name
            outdir.mkdir()
            expected = meta['files'][name]
            actual = {p.name for p in srcdir.glob('*.c')}
            if actual != set(expected): raise ValueError('Cache files changed')
            for filename, wanted in expected.items():
                src = srcdir / filename
                data = src.read_bytes()
                if hashlib.sha256(data).hexdigest() != wanted: raise ValueError('Cache integrity check failed')
                touched = False
                for marker, (before, after) in changes[name].items():
                    at = data.find(marker)
                    if at < 0: continue
                    if marker in seen[name] or data.find(marker, at + len(marker)) >= 0:
                        raise ValueError('Hook label is ambiguous')
                    address = marker[2:-2]
                    nl = b'\r\n' if data[at - 2:at] == b'\r\n' else b'\n'
                    prefix = b'void f_' + address + b'(Cpu *c) {' + nl + b'    FN_ENTER(0x' + address + b'ull);' + nl
                    if data[max(0, at - len(prefix)):at] != prefix:
                        # Only function-entry hooks are accepted.
                        raise ValueError('Hook is not at a function entry')
                    line_end = data.find(b'\n', at)
                    line_next = data.find(b'\n', line_end + 1)
                    if line_end < 0 or line_next < 0 or data[line_end + 1:line_next].strip() != before:
                        raise ValueError('Hook translation changed')
                    line = data[line_end + 1:line_next]
                    data = data[:line_end + 1] + line.replace(before, after) + data[line_next:]
                    seen[name].add(marker)
                    touched = True
                dest = outdir / filename
                if touched:
                    dest.write_bytes(data)
                else:
                    try: os.link(src, dest)
                    except OSError: shutil.copy2(src, dest)
        if any(seen[name] != set(changes[name]) for name in BASES):
            raise ValueError('Not all changed hooks were found')
        output = work / 'generated'
        output.mkdir(exist_ok=True)
        if any((output / name).exists() for name in BASES): raise ValueError('Generated output already exists')
        moved = []
        for name in BASES:
            os.replace(staging / name, output / name)
            moved.append(output / name)
        staging.rmdir()
        print('Reused verified game translation; updated', sum(map(len, changes.values())), 'mod hooks.', flush=True)
        return True
    except Exception:
        print('Cached translation cannot be reused; performing a full translation.', flush=True)
        if 'moved' in locals():
            for path in moved:
                if path.parent == work / 'generated': shutil.rmtree(path, ignore_errors=True)
        if 'staging' in locals() and staging.exists(): shutil.rmtree(staging, ignore_errors=True)
        return False


def save_cache(cache_root, work):
    """Save a successful translation without moving or altering the work files."""
    cache_root, work = Path(cache_root), Path(work)
    cache_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='cache-', dir=cache_root))
    try:
        manifest = {'fingerprint': fingerprint(), 'files': {}}
        for name in BASES:
            dest = stage / 'generated' / name
            dest.mkdir(parents=True)
            checksums = {}
            for src in sorted((work / 'generated' / name).glob('*.c')):
                target = dest / src.name
                try: os.link(src, target)
                except OSError: shutil.copy2(src, target)
                checksums[src.name] = digest(src)
            if not checksums: raise ValueError('No generated game files')
            manifest['files'][name] = checksums
        target = stage / 'patched/exefs'
        target.mkdir(parents=True)
        for name in ('main', 'sdk', 'subsdk9'):
            shutil.copy2(work / 'patched/exefs' / name, target / name)
        shutil.copy2(work / 'entries.json', stage / 'entries.json')
        manifest['inputs'] = {name: digest(stage / name) for name in
                              ('entries.json', 'patched/exefs/main', 'patched/exefs/sdk', 'patched/exefs/subsdk9')}
        (stage / 'manifest.json').write_text(json.dumps(manifest))
        pointer = cache_root / 'current.json'
        previous = json.loads(pointer.read_text()).get('directory') if pointer.exists() else None
        tmp = cache_root / 'current.tmp'
        tmp.write_text(json.dumps({'directory': stage.name}))
        os.replace(tmp, pointer)
        if previous and previous != stage.name and Path(previous).name == previous:
            old = cache_root / previous
            if old.is_dir() and old.resolve().parent == cache_root.resolve() and previous.startswith('cache-'):
                shutil.rmtree(old, ignore_errors=True)
        print('Saved local game-translation cache for future updates.', flush=True)
    except Exception:
        if stage.exists(): shutil.rmtree(stage, ignore_errors=True)
        raise


def current_cache(cache_root):
    try:
        root = Path(cache_root)
        name = json.loads((root / 'current.json').read_text())['directory']
        if Path(name).name != name or not name.startswith('cache-'): return None
        path = root / name
        if path.resolve().parent != root.resolve() or not path.is_dir(): return None
        return path
    except (OSError, ValueError, KeyError, TypeError):
        return None
