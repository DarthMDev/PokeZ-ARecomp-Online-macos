"""Turn the supplied launcher artwork into a C include for the executable."""
from pathlib import Path
import sys

data = Path(sys.argv[1]).read_bytes()
out = Path(sys.argv[2])
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('w', encoding='ascii', newline='\n') as f:
    f.write('static const unsigned char lumiose_background_png[] = {\n')
    for start in range(0, len(data), 24):
        f.write(','.join(f'0x{x:02x}' for x in data[start:start + 24]) + ',\n')
    f.write('};\n')
