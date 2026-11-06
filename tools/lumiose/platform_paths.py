"""Names and advisory locking shared by the Windows and Linux launchers."""
import os

WINDOWS = os.name == 'nt'
EXECUTABLE = 'lasrecomp.exe' if WINDOWS else 'lasrecomp'
GAME_LIBRARY = 'lasgame.dll' if WINDOWS else 'lasgame.so'
MODULE_LIBRARY = 'lumiose.dll' if WINDOWS else 'lumiose.so'
ZIG = 'zig.exe' if WINDOWS else 'zig'

def lock_file(file):
    if WINDOWS:
        import msvcrt
        file.seek(0)
        if not file.read(1):
            file.write(b'0')
            file.flush()
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
