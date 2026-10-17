"""HTTP 다운로드 + zip 추출 유틸리티.

다운로드는 Windows 내장 curl.exe 를 우선 사용한다.
- Windows 10(1803+)/11 에 기본 포함, Windows 자체 TLS(schannel)와 Windows 인증서 저장소를 사용
  → 백신 HTTPS 검사/프록시 환경에서도 브라우저와 똑같이 인증서를 확인한다.
- curl.exe 가 없을 때만 Python(urllib) 으로 받는다.
- 인증서 검증을 끄는 일은 하지 않는다.
"""

import json
import os
import shutil
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
from typing import Callable, Optional

from .config import USER_AGENT

ProgressCB = Optional[Callable[[int, int], None]]
LogCB = Optional[Callable[[str], None]]

CERT_HINT = ("백신의 'HTTPS/웹 검사' 기능이나 프록시가 원인일 수 있습니다. "
             "브라우저로 직접 받은 뒤 '로컬 파일' 옵션으로 선택해 주세요.")


class DownloadError(Exception):
    pass


def _request(url: str, accept: str = "*/*") -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})


def _is_cert_error(e: BaseException) -> bool:
    seen = set()
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        if isinstance(e, ssl.SSLError) or "CERTIFICATE_VERIFY_FAILED" in str(e):
            return True
        nxt = getattr(e, "reason", None) if isinstance(e, urllib.error.URLError) else None
        if not isinstance(nxt, BaseException):
            nxt = getattr(e, "__cause__", None) or getattr(e, "__context__", None)
        e = nxt
    return False


def fetch_json(url: str, timeout: int = 30):
    curl = _find_curl()
    if curl:
        out = subprocess.run([curl, "-sSL", "--fail", "--ssl-revoke-best-effort", "-A", USER_AGENT,
                              "-H", "Accept: application/json", url],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                             creationflags=_no_window())
        if out.returncode == 0:
            return json.loads(out.stdout.decode("utf-8"))
    with urllib.request.urlopen(_request(url, "application/json"), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def download(url: str, dest: str, progress: ProgressCB = None, expect_zip: bool = False,
             timeout: int = 60, log: LogCB = None) -> str:
    """url 을 dest 로 내려받는다. 중간 파일(.part)에 받은 뒤 완료되면 이름을 바꾼다."""
    log = log or (lambda s: None)
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    tmp = dest + ".part"
    _silent_remove(tmp)
    curl = _find_curl()
    try:
        if curl:
            _download_curl(curl, url, tmp, progress)
        else:
            log("curl.exe 가 없어 Python 으로 다운로드합니다.")
            _download_urllib(url, tmp, progress, timeout)
    except BaseException as e:
        _silent_remove(tmp)
        if isinstance(e, DownloadError) or not isinstance(e, Exception) \
                or e.__class__.__name__ == "SwapCancelled":
            raise
        hint = f"\n\n인증서 확인에 실패했습니다. {CERT_HINT}" if _is_cert_error(e) else ""
        raise DownloadError(f"다운로드 실패: {url}\n{e}{hint}") from e

    if expect_zip and not zipfile.is_zipfile(tmp):
        _silent_remove(tmp)
        raise DownloadError(
            "받은 파일이 zip 이 아닙니다. 로그인/보안 확인 페이지가 대신 내려왔을 수 있습니다.\n"
            f"브라우저로 직접 받은 뒤 '로컬 파일' 옵션으로 선택해 주세요.\nURL: {url}"
        )
    os.replace(tmp, dest)
    return dest


def _download_urllib(url, tmp, progress, timeout):
    with urllib.request.urlopen(_request(url), timeout=timeout) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)


def _find_curl() -> Optional[str]:
    if os.name != "nt":
        return None
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    p = os.path.join(sysroot, "System32", "curl.exe")
    return p if os.path.isfile(p) else shutil.which("curl.exe")


def _no_window() -> int:
    return 0x08000000 if os.name == "nt" else 0


def _download_curl(curl, url, tmp, progress):
    # 전체 크기를 먼저 알아낸다 (진행률 표시용, 실패해도 무시)
    total = 0
    try:
        head = subprocess.run([curl, "-sIL", "--ssl-revoke-best-effort", "-A", USER_AGENT, url],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60,
                              creationflags=_no_window())
        for line in head.stdout.decode("latin-1").splitlines():
            if line.lower().startswith("content-length:"):
                total = int(line.split(":", 1)[1].strip() or 0)  # 리다이렉트 후 마지막 값
    except Exception:
        pass

    args = [curl, "-L", "--fail", "--silent", "--show-error", "--retry", "3",
            "--ssl-revoke-best-effort", "-A", USER_AGENT, "-o", tmp, url]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            creationflags=_no_window())
    try:
        while proc.poll() is None:
            if progress:
                done = os.path.getsize(tmp) if os.path.exists(tmp) else 0
                progress(done, total)
            time.sleep(0.5)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    err = proc.stderr.read().decode("utf-8", "replace").strip() if proc.stderr else ""
    if proc.returncode != 0:
        raise DownloadError(f"다운로드 실패 (curl 종료 코드 {proc.returncode}): {url}\n{err}\n\n{CERT_HINT}")
    if progress:
        done = os.path.getsize(tmp)
        progress(done, total or done)


def find_zip_member(zf: zipfile.ZipFile, exact: Optional[str], basename: str) -> str:
    """정확한 경로가 있으면 그것을, 없으면 파일명이 같은 항목(가장 얕은 것)을 찾는다."""
    names = zf.namelist()
    if exact:
        for n in names:
            if n.replace("\\", "/") == exact:
                return n
    candidates = [n for n in names
                  if n.replace("\\", "/").rsplit("/", 1)[-1].lower() == basename.lower()
                  and not n.replace("\\", "/").lower().startswith("__macosx/")]
    if not candidates:
        raise DownloadError(f"zip 안에서 '{basename}' 파일을 찾지 못했습니다.")
    candidates.sort(key=lambda n: n.count("/"))
    return candidates[0]


def extract_member(zip_path: str, member: str, dest: str, progress: ProgressCB = None) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        info = zf.getinfo(member)
        total = info.file_size
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        with zf.open(info) as src, open(dest, "wb") as dst:
            done = 0
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    return dest


def safe_extract_all(zip_path: str, dest_dir: str) -> str:
    """경로 탈출(zip slip)을 막으면서 전체 압축 해제."""
    dest_dir = os.path.abspath(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            target = os.path.abspath(os.path.join(dest_dir, info.filename))
            if not (target == dest_dir or target.startswith(dest_dir + os.sep)):
                raise DownloadError(f"zip 안에 잘못된 경로가 있습니다: {info.filename}")
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return dest_dir


def _silent_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
