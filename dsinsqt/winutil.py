"""Windows 전용 기능 모음 (관리자 권한, 파일 속성, 레지스트리, 콘솔).

Windows 가 아닌 환경(개발/테스트용)에서는 가능한 범위에서 대체 동작을 한다.
"""

import os
import stat
import subprocess
import sys

IS_WINDOWS = os.name == "nt"

FILE_ATTRIBUTE_READONLY = 0x0001
FILE_ATTRIBUTE_HIDDEN = 0x0002
FILE_ATTRIBUTE_SYSTEM = 0x0004
FILE_ATTRIBUTE_DIRECTORY = 0x0010
FILE_ATTRIBUTE_ARCHIVE = 0x0020
FILE_ATTRIBUTE_NORMAL = 0x0080
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF
# SetFileAttributesW 로 설정 가능한 비트
_SETTABLE_MASK = 0x0001 | 0x0002 | 0x0004 | 0x0020 | 0x0100 | 0x1000 | 0x2000

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetFileAttributesW.restype = wintypes.DWORD
    _kernel32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    _kernel32.SetFileAttributesW.restype = wintypes.BOOL


# ---------------------------------------------------------------------------
# 관리자 권한
# ---------------------------------------------------------------------------
def is_admin() -> bool:
    if not IS_WINDOWS:
        return os.geteuid() == 0 if hasattr(os, "geteuid") else True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """UAC 창을 띄워 관리자 권한으로 자기 자신을 다시 실행한다. 성공하면 True."""
    if not IS_WINDOWS:
        return False
    if getattr(sys, "frozen", False):
        exe = sys.executable
        params = subprocess.list2cmdline(sys.argv[1:])
    else:
        exe = sys.executable
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0])] + sys.argv[1:])
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    return ret > 32


def ensure_hidden_console() -> None:
    """ninfs 마운트를 CTRL_BREAK 로 안전하게 해제하려면 부모와 자식이 같은 콘솔을 공유해야 한다.

    ninfs 공식 GUI 와 같은 방식: 콘솔이 없으면(창 모드 exe) 하나 만들고 숨긴다.
    """
    if not IS_WINDOWS:
        return
    k32 = ctypes.windll.kernel32
    if not k32.GetConsoleWindow():
        if k32.AllocConsole():
            hwnd = k32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE


def enable_dpi_awareness() -> None:
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 파일 속성
# ---------------------------------------------------------------------------
def get_attributes(path: str) -> int:
    if IS_WINDOWS:
        attrs = _kernel32.GetFileAttributesW(path)
        if attrs == INVALID_FILE_ATTRIBUTES:
            raise ctypes.WinError(ctypes.get_last_error())
        return attrs
    st = os.stat(path)
    attrs = 0 if (st.st_mode & stat.S_IWUSR) else FILE_ATTRIBUTE_READONLY
    if stat.S_ISDIR(st.st_mode):
        attrs |= FILE_ATTRIBUTE_DIRECTORY
    return attrs


def set_attributes(path: str, attrs: int) -> None:
    if IS_WINDOWS:
        new = attrs & _SETTABLE_MASK
        if new == 0:
            new = FILE_ATTRIBUTE_NORMAL
        if not _kernel32.SetFileAttributesW(path, new):
            raise ctypes.WinError(ctypes.get_last_error())
        return
    set_readonly(path, bool(attrs & FILE_ATTRIBUTE_READONLY))


def set_readonly(path: str, readonly: bool) -> None:
    """파일/폴더의 읽기 전용 속성을 켜거나 끈다."""
    if IS_WINDOWS:
        attrs = get_attributes(path)
        new = (attrs | FILE_ATTRIBUTE_READONLY) if readonly else (attrs & ~FILE_ATTRIBUTE_READONLY)
        if new != attrs:
            set_attributes(path, new)
        return
    st = os.stat(path)
    mode = stat.S_IMODE(st.st_mode)
    write_bits = stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH
    if readonly:
        mode &= ~write_bits
    else:
        mode |= stat.S_IWUSR
    os.chmod(path, mode)


def is_readonly(path: str) -> bool:
    return bool(get_attributes(path) & FILE_ATTRIBUTE_READONLY)


def copy_attributes(src: str, dst: str) -> None:
    """숨김/시스템/읽기전용/보관 속성을 src 에서 dst 로 복사 (Windows 전용)."""
    if not IS_WINDOWS:
        return
    keep = FILE_ATTRIBUTE_READONLY | FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM | FILE_ATTRIBUTE_ARCHIVE
    src_attrs = get_attributes(src) & keep
    dst_attrs = get_attributes(dst)
    new = (dst_attrs & ~keep) | src_attrs
    if new != dst_attrs:
        set_attributes(dst, new)


# ---------------------------------------------------------------------------
# 레지스트리 / 경로
# ---------------------------------------------------------------------------
def reg_read(root_name: str, key_path: str, value_name: str = ""):
    """레지스트리 값을 읽는다. 없으면 None. 32/64비트 뷰를 모두 확인."""
    if not IS_WINDOWS:
        return None
    import winreg

    root = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}[root_name]
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ | view) as k:
                return winreg.QueryValueEx(k, value_name)[0]
        except OSError:
            continue
    return None


def iter_uninstall_entries():
    """설치된 프로그램 목록(제거 정보)을 (DisplayName, InstallLocation, DisplayIcon) 으로 순회."""
    if not IS_WINDOWS:
        return
    import winreg

    paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for root, path in paths:
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(root, path, 0, winreg.KEY_READ | view) as k:
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(k, i)
                        except OSError:
                            break
                        i += 1
                        try:
                            with winreg.OpenKey(k, sub) as sk:
                                def q(n):
                                    try:
                                        return winreg.QueryValueEx(sk, n)[0]
                                    except OSError:
                                        return None
                                yield q("DisplayName"), q("InstallLocation"), q("DisplayIcon")
                        except OSError:
                            continue
            except OSError:
                continue


def app_data_dir(app_id: str) -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    path = os.path.join(base, app_id)
    os.makedirs(path, exist_ok=True)
    return path


def list_drive_letters() -> set:
    if not IS_WINDOWS:
        return set()
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    return {chr(ord("A") + i) for i in range(26) if mask & (1 << i)}


def no_window_flags() -> int:
    return 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW


def open_url(url: str) -> None:
    import webbrowser

    webbrowser.open(url)

