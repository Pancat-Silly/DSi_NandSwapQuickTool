"""외부 도구(ninfs + WinFsp, OSFMount) 탐지 및 자동 설치."""

import glob
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Callable, List, Optional

from . import config, winutil
from .downloader import DownloadError, download, fetch_json

Log = Callable[[str], None]


@dataclass
class ToolStatus:
    name: str
    found: bool
    path: Optional[str] = None
    detail: str = ""


# ---------------------------------------------------------------------------
# 탐지
# ---------------------------------------------------------------------------
def find_ninfs(custom: Optional[str] = None) -> Optional[List[str]]:
    """ninfs 실행 명령(리스트)을 반환. 못 찾으면 None.

    우선순위: 사용자가 지정한 경로 → 설치 프로그램 레지스트리 → %LOCALAPPDATA%\\ninfs → PATH
    """
    candidates = []
    if custom:
        candidates.append(custom)
    reg_dir = winutil.reg_read("HKCU", r"Software\ninfs", "")
    if reg_dir:
        candidates.append(os.path.join(reg_dir, "ninfs.exe"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, "ninfs", "ninfs.exe"))
    for c in candidates:
        if c and os.path.isfile(c):
            # GUI 버전(ninfsw.exe)을 골랐으면 콘솔 버전으로 바꿔준다
            if os.path.basename(c).lower() == "ninfsw.exe":
                alt = os.path.join(os.path.dirname(c), "ninfs.exe")
                if os.path.isfile(alt):
                    c = alt
            return [c]
    which = shutil.which("ninfs")
    if which:
        return [which]
    return None


def find_winfsp() -> Optional[str]:
    if not winutil.IS_WINDOWS:
        return "(non-Windows)"
    d = winutil.reg_read("HKLM", r"SOFTWARE\WinFsp", "InstallDir")
    if d and os.path.isdir(d):
        return d
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base and os.path.isdir(os.path.join(base, "WinFsp")):
            return os.path.join(base, "WinFsp")
    return None


def find_osfmount(custom: Optional[str] = None) -> Optional[str]:
    """OSFMount.com (명령줄 버전) 경로."""
    candidates = []
    if custom:
        if os.path.isdir(custom):
            candidates.append(os.path.join(custom, "OSFMount.com"))
        else:
            candidates.append(custom)
            if custom.lower().endswith(".exe"):
                candidates.append(os.path.join(os.path.dirname(custom), "OSFMount.com"))
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"),
                 os.environ.get("ProgramFiles(x86)")):
        if base:
            candidates.append(os.path.join(base, "OSFMount", "OSFMount.com"))
    for name, loc, icon in winutil.iter_uninstall_entries() or []:
        if name and "osfmount" in str(name).lower():
            if loc:
                candidates.append(os.path.join(loc, "OSFMount.com"))
            if icon:
                candidates.append(os.path.join(os.path.dirname(str(icon).split(",")[0].strip('"')),
                                               "OSFMount.com"))
    for c in candidates:
        if c and os.path.isfile(c) and c.lower().endswith(".com"):
            return c
    which = shutil.which("OSFMount.com")
    return which


def check_all(ninfs_custom=None, osf_custom=None) -> List[ToolStatus]:
    ninfs = find_ninfs(ninfs_custom)
    winfsp = find_winfsp()
    osf = find_osfmount(osf_custom)
    return [
        ToolStatus("ninfs", bool(ninfs), ninfs[0] if ninfs else None),
        ToolStatus("WinFsp", bool(winfsp), winfsp),
        ToolStatus("OSFMount", bool(osf), osf),
    ]


# ---------------------------------------------------------------------------
# 설치
# ---------------------------------------------------------------------------
def _installer_dir() -> str:
    d = os.path.join(tempfile.gettempdir(), config.APP_ID, "installers")
    os.makedirs(d, exist_ok=True)
    return d


def _ninfs_installer_url(log: Log) -> str:
    try:
        data = fetch_json(config.NINFS_RELEASES_API)
        for a in data.get("assets", []):
            n = a.get("name", "").lower()
            if n.endswith("installer.exe") and "win" in n:
                log(f"ninfs 최신 릴리스: {data.get('tag_name')} / {a['name']}")
                return a["browser_download_url"]
        log("최신 릴리스에서 설치 파일을 찾지 못해 v2.0 설치 파일을 사용합니다.")
    except Exception as e:  # API 제한 등
        log(f"GitHub API 조회 실패({e}), v2.0 설치 파일을 사용합니다.")
    return config.NINFS_FALLBACK_INSTALLER_URL


def install_ninfs(log: Log, progress=None) -> bool:
    """ninfs 공식 Windows 설치 파일(WinFsp 포함)을 받아 조용히 설치."""
    if not winutil.IS_WINDOWS:
        log("Windows 가 아니므로 'pip install ninfs' 로 직접 설치하세요.")
        return False
    url = _ninfs_installer_url(log)
    dest = os.path.join(_installer_dir(), os.path.basename(url))
    log(f"다운로드: {url}")
    download(url, dest, progress, log=log)
    log("ninfs 설치 중... (WinFsp 설치 진행 창이 잠깐 보일 수 있습니다)")
    rc = subprocess.call([dest, "/S"])
    log(f"설치 프로그램 종료 코드: {rc}")
    ok = find_ninfs() is not None and find_winfsp() is not None
    if not ok:
        log("자동 설치를 확인하지 못했습니다. 설치 창을 직접 띄웁니다. 안내에 따라 설치해 주세요.")
        subprocess.call([dest])
        ok = find_ninfs() is not None and find_winfsp() is not None
    cleanup_installers()
    return ok


def install_osfmount(log: Log, progress=None) -> bool:
    """PassMark 공식 사이트에서 OSFMount 설치 파일을 받아 설치."""
    if not winutil.IS_WINDOWS:
        log("OSFMount 는 Windows 전용입니다.")
        return False
    dest = os.path.join(_installer_dir(), "osfmount_setup.exe")
    log(f"다운로드: {config.OSFMOUNT_INSTALLER_URL}")
    download(config.OSFMOUNT_INSTALLER_URL, dest, progress, log=log)
    log("OSFMount 설치 중... (드라이버 설치 확인 창이 뜨면 '설치'를 눌러 주세요)")
    rc = subprocess.call([dest, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"])
    log(f"설치 프로그램 종료 코드: {rc}")
    ok = find_osfmount() is not None
    if not ok:
        log("자동 설치를 확인하지 못했습니다. 설치 창을 직접 띄웁니다. 안내에 따라 설치해 주세요.")
        subprocess.call([dest])
        ok = find_osfmount() is not None
    cleanup_installers()
    return ok


def cleanup_installers() -> None:
    for f in glob.glob(os.path.join(_installer_dir(), "*")):
        try:
            os.remove(f)
        except OSError:
            pass


__all__ = ["ToolStatus", "find_ninfs", "find_winfsp", "find_osfmount", "check_all",
           "install_ninfs", "install_osfmount", "cleanup_installers", "DownloadError"]
