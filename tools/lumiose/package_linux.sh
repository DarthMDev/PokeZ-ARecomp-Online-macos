#!/bin/bash
# Assemble a portable Linux folder after tools/za/dist-linux.sh has built its AppDir.
# The player supplies their game files; no generated game code is packaged.
set -euo pipefail
cd "$(dirname "$0")/../.."
appdir="$PWD/build/linux/x86_64/za-AppDir"
out="$PWD/build/dist/Lumiose Online Linux"
test -x "$appdir/usr/bin/lasrecomp"
test -x "$appdir/usr/bin/zig/zig"
test -f lumiose/subsdk9
if [ -e "$out" ]; then echo "Refusing to overwrite $out" >&2; exit 1; fi
mkdir -p "$out"
cp -a "$appdir/usr" "$out/"
d="$out/usr/bin"
mkdir -p "$d/tools/lumiose" "$d/lumiose"
cp tools/*.py "$d/tools/"
cp tools/gamelib_entry.c tools/lumiose_test_entry.c "$d/tools/"
mkdir -p "$d/tools/rando"
cp tools/rando/patch_variants.json "$d/tools/rando/"
cp -a tools/lumiose/*.py "$d/tools/lumiose/"
cp -a runtime "$d/runtime"
cp lumiose/subsdk9 "$d/lumiose/subsdk9"
cp third_party/rnnoise/COPYING "$d/RNNOISE-LICENSE.txt"
cp LUMIOSE-RELEASE.md "$d/README-Windows-reference.md"
python3 -m venv "$PWD/build/linux/x86_64/lumiose-python-venv"
"$PWD/build/linux/x86_64/lumiose-python-venv/bin/pip" install --target "$d/python-deps" \
  capstone==5.0.9 unicorn==2.1.4 lz4==4.4.5
cat > "$out/Lumiose Online" <<'EOF'
#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$HERE/usr/bin"
exec python3 tools/lumiose/entry.py "$@"
EOF
chmod +x "$out/Lumiose Online"
cat > "$out/READ ME.txt" <<'EOF'
Lumiose Online for ZA Recomp - experimental Linux build

Extract the complete archive to a writable folder, including on an SD card.
Run "Lumiose Online" from that folder in Desktop Mode. Python 3 must be installed.
Choose your own game files, update 2.0.2, and DLC during first-time setup.
The game files and generated game code are not included.

This build has not yet been validated end to end on a Steam Deck.
EOF
# A Windows DLL from the mod or any game output must never enter the package.
if find "$out" -type f \( -iname 'lasgame.*' -o -iname 'main.nso' -o -iname 'main.npdm' -o -iname 'romfs.bin' -o -iname '*.nsp' -o -iname '*.xci' -o -iname '*.nca' \) | grep -q .; then
    echo 'Unexpected game data in Linux package' >&2; exit 1
fi
echo "Linux folder prepared at: $out"
