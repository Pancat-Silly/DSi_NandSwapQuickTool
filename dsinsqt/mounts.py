"""ninfs(nanddsi) 마운트와 OSFMount 마운트를 다루는 클래스."""

import os
import re
import signal
import subprocess
import threading
import time
from typing import Callable, List, Optional

from . import winutil

Log = Callable[[str], None]


class MountError(Exception):
    pass


# ---------------------------------------------------------------------------
# ninfs
# ---------------------------------------------------------------------------
class NinfsMount:
    """`ninfs nanddsi <nand> -f <mountpoint>` 를 백그라운드 프로세스로 실행.

    - GUI 의 "Nintendo DSi NAND backup (nand_dsi.bin)" + "Allow writing" 과 동일
      (ninfs 는 --ro 를 주지 않으면 쓰기 허용으로 마운트한다)
    - WinFsp 는 폴더에 마운트할 때 그 폴더가 '존재하지 않아야' 한다.
    - 해제는 ninfs GUI 와 같은 방식(CTRL_BREAK_EVENT)으로 정상 종료시켜 변경 내용을 기록한다.
    """

    def __init__(self, ninfs_cmd: List[str], nand_path: str, mountpoint: str,
                 console_id: Optional[str] = None, label: str = "", log: Log = print):
        self.cmd = list(ninfs_cmd)
        self.nand_path = os.path.abspath(nand_path)
        self.mountpoint = os.path.abspath(mountpoint)
        self.console_id = (console_id or "").strip() or None
        self.label = label or os.path.basename(nand_path)
        self.log = log
        self.proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self.output: List[str] = []

    @property
    def twl_main(self) -> str:
        return os.path.join(self.mountpoint, "twl_main.img")

    # 이 프로그램에서는 정상인 안내 문구들 (로그에서 한 줄로 요약)
    _NOISE = ("should *not* be run as an administrator", "The mount will not be normally accessible",
              "should be run from a non-administrator", "Failed to do AttachConsole",
              "most likely isn't the cause of any other issues")

    def _read_output(self):
        assert self.proc and self.proc.stdout
        noted = False
        for line in self.proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            self.output.append(line)
            if any(n in line for n in self._NOISE):
                if not noted:
                    noted = True
                    self.log(f"  [ninfs {self.label}] (관리자 권한 실행 안내 - 이 프로그램은 OSFMount 도 관리자 "
                             "권한으로 쓰므로 정상입니다)")
                continue
            self.log(f"  [ninfs {self.label}] {line}")

    def mount(self, timeout: float = 120) -> str:
        parent = os.path.dirname(self.mountpoint)
        os.makedirs(parent, exist_ok=True)
        if os.path.isdir(self.mountpoint):
            try:
                os.rmdir(self.mountpoint)  # WinFsp: 마운트 폴더는 없어야 함
            except OSError as e:
                raise MountError(f"마운트 폴더가 비어있지 않습니다: {self.mountpoint}") from e
        if not winutil.IS_WINDOWS:
            os.makedirs(self.mountpoint, exist_ok=True)  # FUSE 는 반대로 폴더가 있어야 함

        args = self.cmd + ["nanddsi", self.nand_path]
        if self.console_id:
            args += ["--console-id", self.console_id]
        args += ["-f", self.mountpoint]

        env = dict(os.environ)
        popen_opts = {}
        if winutil.IS_WINDOWS:
            # 자식은 이 프로그램의 (숨겨진) 콘솔을 그대로 물려받으므로 AttachConsole 용 변수는 필요 없다
            popen_opts["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        env.pop("NINFS_GUI_PARENT_PID", None)
        env["PYTHONUNBUFFERED"] = "1"  # ninfs 출력이 해제 때 몰아서 나오지 않도록
        self.log(f"ninfs 마운트 ({self.label}): {subprocess.list2cmdline(args)}")
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                                     env=env, **popen_opts)
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

        deadline = time.time() + timeout
        while time.time() < deadline:
            if os.path.isfile(self.twl_main):
                self.log(f"ninfs 마운트 완료 ({self.label}) → {self.mountpoint}")
                return self.twl_main
            if self.proc.poll() is not None:
                self._reader.join(2)
                raise MountError(
                    f"ninfs 마운트 실패 ({self.label}), 종료 코드 {self.proc.returncode}\n"
                    + "\n".join(self.output[-15:])
                )
            time.sleep(0.5)
        self.unmount()
        raise MountError(f"ninfs 마운트 시간 초과 ({self.label})")

    def unmount(self, timeout: float = 30) -> bool:
        if not self.proc:
            return True
        if self.proc.poll() is None:
            self.log(f"ninfs 마운트 해제 ({self.label})")
            try:
                if winutil.IS_WINDOWS:
                    self.proc.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    subprocess.call(["fusermount", "-u", self.mountpoint])
            except Exception as e:
                self.log(f"  해제 신호 전송 실패: {e}")
            try:
                self.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                self.log(f"  [경고] ninfs ({self.label}) 가 응답하지 않아 강제 종료합니다.")
                self.proc.kill()
                self.proc.wait(10)
                return False
        if self._reader:
            self._reader.join(2)
        if os.path.isdir(self.mountpoint):
            try:
                os.rmdir(self.mountpoint)
            except OSError:
                pass
        self.proc = None
        return True


# ---------------------------------------------------------------------------
# OSFMount
# ---------------------------------------------------------------------------
_CREATED_RE = re.compile(r"Created device\s+\d+\s*:\s*([A-Za-z]):", re.I)


class OsfMount:
    """`OSFMount.com -a -t file -f <img> -m #: -o rw` (Direct Write 모드) 로 마운트."""

    def __init__(self, osfmount_com: str, image_path: str, label: str = "", log: Log = print):
        self.exe = osfmount_com
        self.image = os.path.abspath(image_path)
        self.label = label
        self.log = log
        self.drive: Optional[str] = None  # 'X'

    @property
    def root(self) -> str:
        return f"{self.drive}:\\"

    def _run(self, args, timeout=120) -> subprocess.CompletedProcess:
        cp = subprocess.run([self.exe] + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL, timeout=timeout,
                            creationflags=winutil.no_window_flags())
        enc = "mbcs" if winutil.IS_WINDOWS else "utf-8"
        out = cp.stdout.decode(enc, errors="replace")
        for line in out.splitlines():
            if line.strip():
                self.log(f"  [OSFMount {self.label}] {line.strip()}")
        cp.stdout = out
        return cp

    def mount(self, timeout: float = 60) -> str:
        before = winutil.list_drive_letters()
        self.log(f"OSFMount 마운트 ({self.label}, Direct Write): {self.image}")
        cp = self._run(["-a", "-t", "file", "-f", self.image, "-m", "#:", "-o", "rw"])
        m = _CREATED_RE.search(cp.stdout or "")
        drive = m.group(1).upper() if m else None
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not drive:
                new = sorted(winutil.list_drive_letters() - before)
                if new:
                    drive = new[0]
            if drive and os.path.isdir(f"{drive}:\\"):
                self.drive = drive
                self.log(f"OSFMount 마운트 완료 ({self.label}) → {drive}:")
                return self.root
            time.sleep(0.5)
        if drive:
            self.drive = drive
            self.unmount()
        raise MountError(f"OSFMount 마운트 실패 ({self.label}), 종료 코드 {cp.returncode}\n{cp.stdout}")

    def unmount(self) -> bool:
        if not self.drive:
            return True
        letter = f"{self.drive}:"
        self.log(f"OSFMount 마운트 해제 ({self.label}) {letter}")
        # 백신/검색 색인 등이 드라이브를 계속 잡고 있어 일반 해제(-d)가 거부되는 경우가 많으므로
        # 처음부터 강제 해제(-D)를 쓴다. -D 도 먼저 버퍼를 비우고(Flushing file buffers) 일반 해제를
        # 시도한 뒤, 실패할 때만 강제로 뗀다 → 기록된 데이터는 이미지에 반영된 상태.
        for attempt in range(2):
            try:
                self._run(["-D", "-m", letter])
            except subprocess.TimeoutExpired:
                self.log("  OSFMount 응답 없음")
            for _ in range(10):
                if self.drive not in winutil.list_drive_letters():
                    self.drive = None
                    return True
                time.sleep(0.5)
            if attempt == 0:
                self.log("  해제 확인이 안 되어 한 번 더 시도합니다.")
        self.log(f"  [경고] {letter} 해제 실패")
        return False
