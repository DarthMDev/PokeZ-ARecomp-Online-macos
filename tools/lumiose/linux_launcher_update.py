"""Safely stage, verify and install a Linux launcher update from this fork."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import stat
import sys
import urllib.parse
import urllib.request
import zipfile

REPO = 'TheMagnumChad/PokeZ-ARecomp-Online'
ASSET = 'Lumiose-Online-linux-experimental.zip'
PREFIX = 'Lumiose Online Linux/'
MAX_BYTES = 4 * 1024**3
PROGRAM_DIRS = {'docs', 'gamelib-src', 'lasgen', 'python', 'python-deps', 'runtime', 'tools', 'zaimport', 'zaprompts', 'zig'}
PROGRAM_FILES = {'lasrecomp', 'icon.png', 'za-default.ini', 'LICENSE', 'README.md', 'README.pt-BR.md',
                 'README-Windows-reference.md', 'RNNOISE-LICENSE.txt', 'Baloo2-OFL.txt', 'Baloo2-SemiBold.ttf',
                 'BIZUDPGothic-OFL.txt', 'BIZUDPGothic-Regular.ttf', 'DejaVu-LICENSE.txt',
                 'DejaVuSans.ttf', 'DejaVuSans-Bold.ttf'}


def allowed(path):
    p = PurePosixPath(path)
    if p.parts in (('Lumiose Online',), ('READ ME.txt',)): return True
    if p.parts[:2] == ('usr', 'lib') and len(p.parts) > 2: return True
    if p.parts[:2] != ('usr', 'bin') or len(p.parts) < 3: return False
    if p.parts[2] in PROGRAM_DIRS: return len(p.parts) > 3
    if p.parts[2] == 'lumiose': return p.parts == ('usr', 'bin', 'lumiose', 'subsdk9')
    return len(p.parts) == 3 and p.parts[2] in PROGRAM_FILES


def safe_parent(root, rel):
    """Ensure no existing parent redirects writes outside the installation."""
    path = root
    for part in PurePosixPath(rel).parts[:-1]:
        path = path / part
        if path.is_symlink(): raise RuntimeError('An update path contains a symbolic-link directory')
        if path.exists() and not path.is_dir(): raise RuntimeError('An update directory is not a directory')


def stage_archive(archive, stage):
    files, seen, links, total = [], set(), set(), 0
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            name = info.filename
            if not name.startswith(PREFIX) or '\\' in name: raise RuntimeError('Unexpected archive path')
            raw = name[len(PREFIX):].rstrip('/')
            if not raw: continue
            parts = raw.split('/')
            if any(p in ('', '.', '..') for p in parts): raise RuntimeError('Unsafe archive path')
            if raw in seen: raise RuntimeError('Duplicate archive path')
            seen.add(raw)
            mode = info.external_attr >> 16
            if info.is_dir(): continue
            # Older installations also use this path as their active mod, so
            # never replace it as part of a launcher update.
            if raw == 'usr/bin/lumiose/subsdk9': continue
            if not allowed(raw): raise RuntimeError('Archive contains an unexpected or protected file: ' + raw)
            if not (stat.S_ISREG(mode) or stat.S_ISLNK(mode) or stat.S_IFMT(mode) == 0):
                raise RuntimeError('Archive contains an unsupported file type')
            total += info.file_size
            if total > MAX_BYTES or info.file_size > MAX_BYTES: raise RuntimeError('Update archive is too large')
            if stat.S_ISLNK(mode): links.add(raw)
            files.append((info, raw, mode))
        names = {name for _, name, _ in files}
        if not {'Lumiose Online', 'usr/bin/lasrecomp', 'usr/bin/python/bin/python3.12',
                'usr/bin/tools/lumiose/entry.py', 'usr/bin/tools/lumiose/linux_launcher_update.py'} <= names:
            raise RuntimeError('Update is missing required launcher files')
        for _, name, _ in files:
            parents = PurePosixPath(name).parents
            if any(str(p) in links for p in parents): raise RuntimeError('An archive file is inside a symbolic link')
        for info, name, mode in files:
            out = stage / name
            out.parent.mkdir(parents=True, exist_ok=True)
            if stat.S_ISLNK(mode):
                if info.file_size > 4096: raise RuntimeError('An update symbolic link is too long')
                target = z.read(info).decode('utf-8')
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), target))
                if target.startswith('/') or '\\' in target or resolved == '..' or resolved.startswith('../'):
                    raise RuntimeError('An update symbolic link escapes its package')
                os.symlink(target, out)
            else:
                with z.open(info) as src, out.open('xb') as dest: shutil.copyfileobj(src, dest, 1024 * 1024)
                os.chmod(out, (mode & 0o777) or 0o644)
    return [name for _, name, _ in files]


def write_journal(path, entries):
    tmp = path.with_suffix('.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump({'version': 1, 'entries': entries}, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def recover(root):
    root = Path(root).resolve()
    work = root / '.lumiose-update'
    journal = work / 'journal.json'
    if not journal.is_file(): return False
    data = json.loads(journal.read_text(encoding='utf-8'))
    if data.get('version') != 1 or not isinstance(data.get('entries'), list):
        raise RuntimeError('The update recovery record is invalid')
    for item in reversed(data['entries']):
        rel, existed = item['path'], item['existed']
        if not isinstance(rel, str) or not allowed(rel) or any(p in ('', '.', '..') for p in rel.split('/')):
            raise RuntimeError('The update recovery record contains an unsafe path')
        safe_parent(root, rel)
        dest, backup = root / rel, work / 'backup' / rel
        if existed:
            if not (backup.exists() or backup.is_symlink()): raise RuntimeError('An update backup is missing')
            dest.parent.mkdir(parents=True, exist_ok=True)
            # Copy instead of rename: recovery can safely retry if interrupted.
            temp = dest.with_name(dest.name + '.lumiose-restore')
            if temp.exists() or temp.is_symlink(): temp.unlink()
            if backup.is_symlink(): os.symlink(os.readlink(backup), temp)
            else: shutil.copy2(backup, temp)
            os.replace(temp, dest)
        elif dest.exists() or dest.is_symlink():
            if dest.is_dir() and not dest.is_symlink(): raise RuntimeError('An update destination is unexpectedly a directory')
            dest.unlink()
    journal.unlink()
    shutil.rmtree(work)
    return True


def install(root, archive, fail_after=None):
    root = Path(root).resolve()
    archive = Path(archive).resolve()
    work = root / '.lumiose-update'
    if (work / 'journal.json').exists(): recover(root)
    if work.exists(): shutil.rmtree(work)
    stage, backup = work / 'stage', work / 'backup'
    stage.mkdir(parents=True)
    try:
        files = stage_archive(archive, stage)
        entries = []
        for rel in files:
            safe_parent(root, rel)
            dest = root / rel
            if dest.is_dir() and not dest.is_symlink(): raise RuntimeError('An update file would replace a directory')
            existed = dest.exists() or dest.is_symlink()
            if existed:
                b = backup / rel
                b.parent.mkdir(parents=True, exist_ok=True)
                if dest.is_symlink(): os.symlink(os.readlink(dest), b)
                else: shutil.copy2(dest, b)
            entries.append({'path': rel, 'existed': existed})
        write_journal(work / 'journal.json', entries)
        # Install regular files before symlinks and the Python executable last.
        files.sort(key=lambda n: (n == 'usr/bin/python/bin/python3.12', (stage / n).is_symlink(), n))
        for index, rel in enumerate(files):
            safe_parent(root, rel)
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / rel, dest)
            if fail_after is not None and index + 1 == fail_after: raise RuntimeError('Simulated update failure')
        (work / 'journal.json').unlink()
        shutil.rmtree(work)
    except BaseException:
        if (work / 'journal.json').exists(): recover(root)
        elif work.exists(): shutil.rmtree(work)
        raise


def download_release(tag, dest):
    if not re.fullmatch(r'v\d+\.\d+\.\d+', tag): raise RuntimeError('Invalid release tag')
    headers = {'User-Agent': 'Lumiose-Online-Linux-Updater', 'Accept': 'application/vnd.github+json'}
    req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/releases/tags/{tag}', headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r: release = json.load(r)
    if release.get('tag_name') != tag or release.get('draft') or release.get('prerelease'):
        raise RuntimeError('The launcher release is not a stable release')
    matches = [a for a in release.get('assets', []) if a.get('name') == ASSET]
    if len(matches) != 1: raise RuntimeError('This release does not contain a Linux launcher update')
    asset = matches[0]
    digest = asset.get('digest', '')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest): raise RuntimeError('The update has no verifiable checksum')
    url = asset.get('browser_download_url', '')
    expected_url = f'https://github.com/{REPO}/releases/download/{tag}/{ASSET}'
    if url != expected_url: raise RuntimeError('The update download address is invalid')
    expected_size = asset.get('size')
    if not isinstance(expected_size, int) or expected_size <= 0 or expected_size > MAX_BYTES:
        raise RuntimeError('The update download size is invalid')
    h, size = hashlib.sha256(), 0
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as src, Path(dest).open('wb') as out:
        while block := src.read(1024 * 1024):
            size += len(block)
            if size > expected_size: raise RuntimeError('The update download was larger than expected')
            h.update(block)
            out.write(block)
    if size != expected_size or 'sha256:' + h.hexdigest() != digest:
        raise RuntimeError('The update download failed verification')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--tag')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.recover:
        if recover(root): print('Recovered the previous launcher after an interrupted update.')
        return
    if not args.tag: raise RuntimeError('A release tag is required')
    download = root / '.lumiose-update-download.zip'
    try:
        print('Downloading and verifying Linux launcher update...', flush=True)
        download_release(args.tag, download)
        print('Installing verified launcher update...', flush=True)
        install(root, download)
        print('Launcher update installed.', flush=True)
    finally:
        download.unlink(missing_ok=True)


if __name__ == '__main__':
    try: main()
    except Exception as e:
        print('Launcher update failed:', e, file=sys.stderr, flush=True)
        sys.exit(1)
