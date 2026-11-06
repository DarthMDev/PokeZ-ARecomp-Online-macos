from pathlib import Path
import os
root=Path(os.environ['LUMIOSE_SCRATCH'])/'generated/lumiose'
p=next(x for x in root.glob('lumiose_*.c') if 'void f_7006237cb0(Cpu *c) {' in x.read_text())
s=p.read_text()
a=s.index('void f_7006237cb0(Cpu *c) {')
b=s.index('\nvoid f_7006237f50(Cpu *c) {',a)
part=s[a:b]
part=part.replace('c->x[1] = (uint64_t)(0x7006807cc0ull);  // Preserve the trainer name already in the mod client.', 'c->x[1] = (uint64_t)(0x700634d000ull);')
needle='''    c->x[2] = (uint64_t)(0x0ull);
    (void)(logic64(c, c->x[3] & 0xfull));'''
repl='''    c->x[2] = (uint64_t)(0x0ull);
    { const char *name = (const char *)(uintptr_t)0x70068088d8ull;
      size_t len = strnlen(name, 23);
      if (len && !(len == 4 && !memcmp(name, "Eden", 4))) {
          xr_20 = len; xr_19 += 0x480ull; goto L_137_name_ready;
      }
    }
    (void)(logic64(c, c->x[3] & 0xfull));'''
tail='''    c->x[30] = 0x7006237d80ull; f_700632ce40(c);
    c->x[2] = (uint64_t)(0x700634d000ull);'''
tailnew='''    c->x[30] = 0x7006237d80ull; f_700632ce40(c);
L_137_name_ready:;
    c->x[2] = (uint64_t)(0x700634d000ull);'''
if part.count(needle)!=1 or part.count(tail)!=1: raise SystemExit('Expected name initialization sites not found')
part=part.replace(needle,repl).replace(tail,tailnew)
s=s[:a]+part+s[b:]
a=s.index('void f_7006237f50(Cpu *c) {')
b=s.index('\nvoid f_7006237f80(Cpu *c) {',a)
part=s[a:b]
old='    c->x[3] = (uint64_t)(0x700634d000ull);\n    c->x[3] = (uint64_t)(c->x[3] + 0xc18ull);'
new='    c->x[3] = (uint64_t)(0x70068088d8ull);  // current trainer name'
if part.count(old)!=1: raise SystemExit('Expected initial name getter not found')
p.write_text(s[:a]+part.replace(old,new)+s[b:])
p=next(x for x in root.glob('lumiose_*.c') if 'c->x[30] = 0x700622ad4cull; f_7006237500(c);' in x.read_text())
s=p.read_text()
old='    c->x[30] = 0x700622ad4cull; f_7006237500(c);'
new=old+'\n    { extern void lumiose_mark_trainer_ready(void); lumiose_mark_trainer_ready(); }'
if s.count(old)!=1: raise SystemExit('Expected trainer-name update call not found')
p.write_text(s.replace(old,new))
print('Preserved the loaded trainer name during network initialization')
