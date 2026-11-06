// Windows entry point: the visible launcher and updater are shipped together.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command, int show) {
    (void)instance; (void)previous; (void)command; (void)show;
    wchar_t dir[32768], python[32768], script[32768], args[65536];
    DWORD n = GetModuleFileNameW(NULL, dir, 32768);
    if (!n || n >= 32768) return 1;
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (!slash) return 1;
    *slash = 0;
    if (swprintf(python, 32768, L"%ls\\python\\python.exe", dir) < 0 ||
        swprintf(script, 32768, L"%ls\\tools\\lumiose\\entry.py", dir) < 0 ||
        swprintf(args, 65536, L"\"%ls\" \"%ls\"", python, script) < 0) return 1;
    STARTUPINFOW si = {0};
    PROCESS_INFORMATION pi = {0};
    si.cb = sizeof si;
    if (!CreateProcessW(python, args, NULL, NULL, FALSE, CREATE_NEW_CONSOLE, NULL, dir, &si, &pi)) {
        MessageBoxW(NULL, L"The Lumiose launcher could not start its bundled tools. Extract the whole release zip and try again.",
                    L"Lumiose Online", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
