from pathlib import Path
import os
scratch = Path(os.environ['LUMIOSE_SCRATCH'])
p = next(x for x in (scratch / 'generated/lumiose').glob('lumiose_*.c') if 'L_7006215368:;' in x.read_text())
s = p.read_text()
needle = '''L_7006215368:;
    { uint64_t ea = xr_20 + 0x0ull; uint64_t v = LD64(ea); c->x[0] = (uint64_t)(v); }'''
replacement = '''L_7006215368:;
    { extern uint64_t lumiose_camera_find(uint64_t, uint64_t);
      uint64_t next = lumiose_camera_find(xr_20, xr_28);
      if (!next) { xr_25 += xr_27 + (xr_28 - xr_20); xr_27 = 0; goto L_70062153f4; }
      xr_25 += xr_27 + (next - xr_20); xr_27 = 0; xr_20 = next; }
    { uint64_t ea = xr_20 + 0x0ull; uint64_t v = LD64(ea); c->x[0] = (uint64_t)(v); }'''
if s.count(needle) != 1:
    raise SystemExit('Expected camera scanner entry not found exactly once')
p.write_text(s.replace(needle, replacement))
print('Patched the camera scanner to use native signature search')
