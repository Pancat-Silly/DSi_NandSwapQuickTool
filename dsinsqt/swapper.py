"""패치 전체 흐름.

1. 입력 확인
2. A 낸드 준비 (archive.org zip 다운로드 → nand.bin 추출, 또는 로컬 파일) → 작업용 사본
3. Unlaunch TMD 준비 (gbatemp zip 다운로드, 또는 로컬 zip/폴더)
4. B 낸드 백업
5. ninfs 로 A, B 를 쓰기 허용으로 임시 폴더에 마운트
6. 각 twl_main.img 를 OSFMount Direct Write 모드로 마운트
7. B 의 모든 파일 삭제 → A 의 모든 파일을 B 에 복사
8. title\\00030017 하위 전부 읽기 전용 → 484e4141 덮어쓰기 → 다시 읽기 전용
9. shared1\\TWLCFG0.dat, TWLCFG1.dat 삭제
10. OSFMount 전부 해제 → ninfs 전부 해제
11. B 낸드 SHA1 계산 → nand.bin.sha1 의 0x00~0x27 덮어쓰기
"""

import os
import shutil
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from . import config, fileops, winutil
from .downloader import DownloadError, download, extract_member, find_zip_member, safe_extract_all
from .mounts import MountError, NinfsMount, OsfMount
from .tools import find_ninfs, find_osfmount

Log = Callable[[str], None]
Progress = Callable[[str, Optional[float]], None]


class SwapError(Exception):
    pass


class SwapCancelled(Exception):
    pass


@dataclass
class SwapOptions:
    b_path: str
    a_source: str = "download"          # "download" | "local"
    a_local_path: str = ""
    tmd_source: str = "download"        # "download" | "local"
    tmd_local_path: str = ""            # zip 파일 또는 폴더
    a_console_id: str = ""
    b_console_id: str = ""
    make_backup: bool = True
    restore_on_fail: bool = True
    ninfs_path: Optional[str] = None
    osfmount_path: Optional[str] = None


class NandSwapper:
    def __init__(self, opts: SwapOptions, log: Log = print, progress: Optional[Progress] = None,
                 ninfs_factory=NinfsMount, osf_factory=OsfMount, ninfs_cmd: Optional[List[str]] = None,
                 osfmount_exe: Optional[str] = None, work_root: Optional[str] = None,
                 cache_dir: Optional[str] = None):
        self.o = opts
        self.log = log
        self._progress = progress or (lambda text, frac: None)
        self.ninfs_factory = ninfs_factory
        self.osf_factory = osf_factory
        self.ninfs_cmd = ninfs_cmd
        self.osfmount_exe = osfmount_exe
        self.cancel_event = threading.Event()
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.work = work_root or os.path.join(tempfile.gettempdir(), config.APP_ID, f"work-{stamp}")
        self.cache = cache_dir or os.path.join(winutil.app_data_dir(config.APP_ID), "cache")
        self.stamp = stamp
        self.backup_path: Optional[str] = None
        self.backup_sha1_path: Optional[str] = None
        self._b_touched = False
        self._cancellable = True
        self._unmount_ok = True

    # ------------------------------------------------------------------ utils
    def cancel(self):
        self.cancel_event.set()

    def _check_cancel(self):
        # 마운트 이후에는 중간에 끊으면 낸드가 망가질 수 있으므로 취소를 받지 않는다
        if self._cancellable and self.cancel_event.is_set():
            raise SwapCancelled("사용자가 취소했습니다.")

    def _step(self, n: int, total: int, text: str):
        self.log("")
        self.log(f"===== [{n}/{total}] {text} =====")
        self._progress(text, None)

    def _bytes_progress(self, label: str):
        def cb(done, total):
            self._check_cancel()
            if total:
                self._progress(f"{label} {done / 1048576:.1f} / {total / 1048576:.1f} MB", done / total)
            else:
                self._progress(f"{label} {done / 1048576:.1f} MB", None)
        return cb

    # ------------------------------------------------------------------ steps
    def _validate(self):
        o = self.o
        if not o.b_path or not os.path.isfile(o.b_path):
            raise SwapError("패치할 nand.bin을 선택해 주세요.")
        if os.path.getsize(o.b_path) < config.MIN_NAND_SIZE:
            raise SwapError("패치할 낸드 파일이 너무 작습니다. 올바른 DSi 낸드 덤프인지 확인하세요.")
        if o.a_source == "local":
            if not o.a_local_path or not os.path.isfile(o.a_local_path):
                raise SwapError("패치에 사용될 로컬 낸드를 선택해 주세요.")
            if os.path.abspath(o.a_local_path).lower() == os.path.abspath(o.b_path).lower():
                raise SwapError("패치에 사용될 낸드와 패치할 낸드가 같은 파일입니다.")
        if o.tmd_source == "local" and (not o.tmd_local_path or not os.path.exists(o.tmd_local_path)):
            raise SwapError("Unlaunch TMD zip(또는 폴더)을 선택해 주세요.")

        if self.ninfs_cmd is None:
            self.ninfs_cmd = find_ninfs(o.ninfs_path)
        if not self.ninfs_cmd:
            raise SwapError("ninfs 를 찾을 수 없습니다. '필수 도구'에서 설치하거나 경로를 지정하세요.")
        if self.osfmount_exe is None:
            self.osfmount_exe = find_osfmount(o.osfmount_path)
        if not self.osfmount_exe:
            raise SwapError("OSFMount 를 찾을 수 없습니다. '필수 도구'에서 설치하거나 경로를 지정하세요.")
        self.log(f"ninfs: {self.ninfs_cmd[0]}")
        self.log(f"OSFMount: {self.osfmount_exe}")
        self.log(f"패치할 낸드: {o.b_path}")

    def _prepare_a(self) -> str:
        os.makedirs(self.work, exist_ok=True)
        dest = os.path.join(self.work, "A_nand.bin")
        local = self.o.a_local_path if self.o.a_source == "local" else ""
        if local and not zipfile.is_zipfile(local):
            self.log(f"패치에 사용될 로컬 낸드 사용: {local}")
            self.log("원본 보호를 위해 작업용 사본을 만들어 그 사본을 마운트합니다.")
            self._copy_with_progress(local, dest, "패치에 사용될 낸드 복사")
        else:
            zip_path = local or os.path.join(self.cache, config.KOREAN_NAND_ZIP_NAME)
            if local:
                self.log(f"로컬 zip 사용: {local}")
            elif os.path.isfile(zip_path) and zipfile.is_zipfile(zip_path):
                self.log(f"캐시된 zip 사용: {zip_path}")
            else:
                self.log(f"archive.org 에서 한글판 낸드 zip 다운로드: {config.KOREAN_NAND_ZIP_URL}")
                download(config.KOREAN_NAND_ZIP_URL, zip_path, self._bytes_progress("다운로드"),
                         expect_zip=True, log=self.log)
            with zipfile.ZipFile(zip_path) as zf:
                member = find_zip_member(zf, config.KOREAN_NAND_ZIP_MEMBER, "nand.bin")
            self.log(f"zip 에서 추출: {member}")
            extract_member(zip_path, member, dest, self._bytes_progress("추출"))
        if os.path.getsize(dest) < config.MIN_NAND_SIZE:
            raise SwapError("패치에 사용될 낸드 파일이 너무 작습니다. 올바른 DSi 낸드인지 확인하세요.")
        if os.path.getsize(dest) != os.path.getsize(self.o.b_path):
            self.log("[참고] 패치에 사용될 낸드 와 패치할 낸드의 파일 크기가 다릅니다. (footer 유무 차이일 수 있음)")
        return dest

    def _prepare_unlaunch(self) -> str:
        """484e4141 폴더 경로를 반환."""
        src = self.o.tmd_local_path
        extract_dir = os.path.join(self.work, "unlaunch_tmd")
        if self.o.tmd_source == "download":
            zip_path = os.path.join(self.cache, config.UNLAUNCH_TMD_ZIP_NAME)
            if not (os.path.isfile(zip_path) and zipfile.is_zipfile(zip_path)):
                self.log(f"Unlaunch TMD zip 다운로드: {config.UNLAUNCH_TMD_ZIP_URL}")
                try:
                    download(config.UNLAUNCH_TMD_ZIP_URL, zip_path, self._bytes_progress("다운로드"),
                             expect_zip=True, log=self.log)
                except DownloadError as e:
                    raise SwapError(
                        f"{e}\n\ngbatemp 는 로그인한 사용자만 첨부파일을 받을 수 있는 경우가 있습니다. "
                        "브라우저로 unlaunch-tmd.zip 을 직접 받은 뒤 '로컬 zip/폴더'로 선택하세요."
                    ) from e
            else:
                self.log(f"캐시된 zip 사용: {zip_path}")
            safe_extract_all(zip_path, extract_dir)
            search_root = extract_dir
        elif os.path.isfile(src):
            if not zipfile.is_zipfile(src):
                raise SwapError("선택한 Unlaunch TMD 파일이 zip 이 아닙니다.")
            safe_extract_all(src, extract_dir)
            search_root = extract_dir
        else:
            search_root = src

        found = self._find_unlaunch_dir(search_root)
        if not found:
            raise SwapError(
                f"'{config.LAUNCHER_PARENT_DIR}\\{config.UNLAUNCH_TITLE_DIR}\\content\\title.tmd' 구조를 "
                "찾지 못했습니다. 올바른 unlaunch-tmd.zip 인지 확인하세요."
            )
        self.log(f"Unlaunch TMD 폴더: {found}")
        return found

    @staticmethod
    def _find_unlaunch_dir(root: str) -> Optional[str]:
        target = config.UNLAUNCH_TITLE_DIR.lower()
        best: Optional[Tuple[int, str]] = None
        if os.path.basename(os.path.normpath(root)).lower() == target:
            candidates = [root]
        else:
            candidates = []
            for dirpath, dirnames, _ in os.walk(root):
                dirnames[:] = [d for d in dirnames if d.lower() != "__macosx"]
                for d in dirnames:
                    if d.lower() == target:
                        candidates.append(os.path.join(dirpath, d))
        for c in candidates:
            if os.path.isfile(os.path.join(c, *config.UNLAUNCH_TMD_REL)):
                depth = c.count(os.sep)
                if best is None or depth < best[0]:
                    best = (depth, c)
        return best[1] if best else None

    def _backup_b(self):
        if not self.o.make_backup:
            self.log("[경고] 백업을 건너뜁니다 (옵션 꺼짐).")
            return
        b = self.o.b_path
        self.backup_path = f"{b}.{self.stamp}.bak"
        self.log(f"패치할 낸드 백업: {self.backup_path}")
        self._copy_with_progress(b, self.backup_path, "백업")
        side = b + ".sha1"
        if os.path.isfile(side):
            self.backup_sha1_path = f"{side}.{self.stamp}.bak"
            shutil.copyfile(side, self.backup_sha1_path)
            self.log(f"SHA1 파일 백업: {self.backup_sha1_path}")

    def _copy_with_progress(self, src: str, dst: str, label: str):
        total = os.path.getsize(src)
        done = 0
        cb = self._bytes_progress(label)
        with open(src, "rb") as fi, open(dst, "wb") as fo:
            while True:
                chunk = fi.read(4 * 1024 * 1024)
                if not chunk:
                    break
                fo.write(chunk)
                done += len(chunk)
                cb(done, total)

    def _modify_b(self, a_root: str, b_root: str, unlaunch_dir: str):
        skip_dirs = config.SKIP_DIR_NAMES
        skip_files = config.SKIP_FILE_NAMES

        self.log("패치할 낸드의 모든 파일/폴더 삭제 중...")
        self._b_touched = True
        n = fileops.remove_contents(b_root, skip_dirs, self.log)
        self.log(f"  {n}개 항목 삭제")

        self.log("패치에 사용될 낸드의 모든 파일을 패치할 낸드로 복사 중...")
        n = fileops.copy_tree_merge(a_root, b_root, skip_dirs, skip_files, preserve_attrs=True)
        self.log(f"  {n}개 파일 복사")

        title = fileops.find_child_ci(b_root, config.TITLE_DIR)
        if not title:
            raise SwapError("패치할 낸드에 title 폴더가 없습니다. 패치에 사용될 낸드가 올바른지 확인하세요.")
        launcher = fileops.find_child_ci(title, config.LAUNCHER_PARENT_DIR)
        if not launcher:
            launcher = os.path.join(title, config.LAUNCHER_PARENT_DIR)
            self.log(f"[참고] {launcher} 가 없어 새로 만듭니다.")
            os.makedirs(launcher)

        self.log(f"{launcher} 하위 폴더/파일 전부 읽기 전용 설정...")
        n = fileops.set_readonly_tree(launcher)
        self.log(f"  {n}개 항목")

        dest = fileops.find_child_ci(launcher, config.UNLAUNCH_TITLE_DIR) or \
            os.path.join(launcher, config.UNLAUNCH_TITLE_DIR)
        self.log(f"Unlaunch TMD 덮어쓰기 → {dest}")
        if os.path.isdir(dest):
            fileops.clear_readonly_tree(dest)
        fileops.copy_tree_merge(unlaunch_dir, dest, skip_dirs, skip_files, preserve_attrs=False,
                                log=self.log)

        self.log(f"{launcher} 하위 폴더/파일 다시 읽기 전용 설정...")
        n = fileops.set_readonly_tree(launcher)
        self.log(f"  {n}개 항목")

        shared1 = fileops.find_child_ci(b_root, config.SHARED1_DIR)
        for name in config.TWLCFG_FILES:
            p = fileops.find_child_ci(shared1, name) if shared1 else None
            if p:
                fileops.force_remove(p)
                self.log(f"삭제: {p}")
            else:
                self.log(f"[참고] {config.SHARED1_DIR}\\{name} 가 없어 삭제를 건너뜁니다.")

        # 마운트 중 Windows 가 만들었을 수 있는 폴더 정리 (A 에서는 복사하지 않음)
        for junk in ("System Volume Information", "$RECYCLE.BIN"):
            p = fileops.find_child_ci(b_root, junk)
            if p:
                try:
                    fileops.force_remove(p)
                    self.log(f"Windows 가 만든 폴더 삭제: {p}")
                except OSError as e:
                    self.log(f"[참고] {p} 를 지우지 못했습니다 (DSi 동작에는 영향 없음): {e}")

        # 검증
        tmd_src = os.path.join(unlaunch_dir, *config.UNLAUNCH_TMD_REL)
        tmd_dst = os.path.join(dest, *config.UNLAUNCH_TMD_REL)
        with open(tmd_src, "rb") as f1, open(tmd_dst, "rb") as f2:
            if f1.read() != f2.read():
                raise SwapError("검증 실패: 패치할 낸드의 title.tmd 가 Unlaunch TMD 와 다릅니다.")
        if not winutil.is_readonly(tmd_dst):
            raise SwapError("검증 실패: title.tmd 가 읽기 전용이 아닙니다.")
        self.log("검증 완료: title.tmd 일치 + 읽기 전용 확인")

    # ------------------------------------------------------------------ main
    def run(self) -> bool:
        total = 9
        unmounters: List[Tuple[str, Callable[[], bool]]] = []
        ok = False
        unmount_ok = True
        try:
            self._step(1, total, "입력 및 도구 확인")
            self._validate()

            self._step(2, total, "패치에 사용될 낸드 준비")
            a_nand = self._prepare_a()
            self._check_cancel()

            self._step(3, total, "Unlaunch TMD 준비")
            unlaunch_dir = self._prepare_unlaunch()
            self._check_cancel()

            self._step(4, total, "패치할 낸드 백업")
            self._backup_b()
            self._check_cancel()

            self._step(5, total, "ninfs 로 패치에 사용될/할 낸드 마운트 (쓰기 허용)")
            self._cancellable = False
            self.log("(이 단계부터는 낸드 보호를 위해 취소할 수 없습니다)")
            mnt_root = os.path.join(self.work, "mnt")
            na = self.ninfs_factory(self.ninfs_cmd, a_nand, os.path.join(mnt_root, "A"),
                                    self.o.a_console_id, "A", self.log)
            na.mount()
            unmounters.append(("ninfs A", na.unmount))
            nb = self.ninfs_factory(self.ninfs_cmd, self.o.b_path, os.path.join(mnt_root, "B"),
                                    self.o.b_console_id, "B", self.log)
            nb.mount()
            unmounters.append(("ninfs B", nb.unmount))

            self._step(6, total, "OSFMount 로 twl_main.img 마운트 (Direct Write)")
            oa = self.osf_factory(self.osfmount_exe, na.twl_main, "A", self.log)
            a_root = oa.mount()
            unmounters.append(("OSFMount A", oa.unmount))
            ob = self.osf_factory(self.osfmount_exe, nb.twl_main, "B", self.log)
            b_root = ob.mount()
            unmounters.append(("OSFMount B", ob.unmount))

            self._step(7, total, "패치할 낸드 파일 작업")
            self._modify_b(a_root, b_root, unlaunch_dir)
            ok = True
        except SwapCancelled as e:
            self.log(f"[취소] {e}")
        except (SwapError, MountError, DownloadError) as e:
            self.log(f"[오류] {e}")
        except Exception as e:  # 예상 못한 오류도 반드시 마운트 해제
            import traceback
            self.log(f"[오류] 예상하지 못한 오류: {e!r}")
            self.log(traceback.format_exc())
        finally:
            self._step(8, total, "모든 마운트 해제 (OSFMount → ninfs)")
            for name, fn in reversed(unmounters):
                try:
                    if not fn():
                        unmount_ok = False
                        self.log(f"[경고] {name} 해제가 정상적으로 끝나지 않았습니다.")
                except Exception as e:
                    unmount_ok = False
                    self.log(f"[경고] {name} 해제 중 오류: {e!r}")
            if not unmounters:
                self.log("해제할 마운트가 없습니다.")

        self._cancellable = False
        self._unmount_ok = unmount_ok
        if ok and not unmount_ok:
            ok = False
            self.log("[오류] 마운트 해제가 깔끔하게 되지 않아 패치할 낸드가 손상되었을 수 있습니다.")

        if not ok:
            self._maybe_restore()
            self._cleanup_work()
            self._progress("실패", 0.0)
            return False

        try:
            self._step(9, total, "패치할 낸드 SHA1 계산 및 nand.bin.sha1 갱신")
            digest = fileops.sha1_file(self.o.b_path, self._bytes_progress("SHA1"))
            side = fileops.write_sha1_sidecar(self.o.b_path, digest)
            self.log(f"새 SHA1: {digest}")
            self.log(f"기록 완료: {side} (0x00~0x27)")
        except Exception as e:
            self.log(f"[오류] SHA1 처리 실패: {e!r}")
            self._cleanup_work()
            return False

        self._cleanup_work()
        self.log("")
        self.log("모든 작업이 완료되었습니다!")
        if self.backup_path:
            self.log(f"원래 패치할 낸드 백업: {self.backup_path}")
        self._progress("완료", 1.0)
        return True

    def _maybe_restore(self):
        if not self._b_touched:
            self.log("패치할 낸드는 수정되지 않았습니다.")
            return
        if self.o.restore_on_fail and self.backup_path and os.path.isfile(self.backup_path):
            self.log("패치할 낸드를 백업에서 복원합니다...")
            try:
                self._copy_with_progress(self.backup_path, self.o.b_path, "복원")
                if self.backup_sha1_path:
                    shutil.copyfile(self.backup_sha1_path, self.o.b_path + ".sha1")
                self.log("복원 완료.")
            except Exception as e:
                self.log(f"[오류] 복원 실패: {e!r}  → 직접 {self.backup_path} 를 원래 이름으로 바꿔 주세요.")
        else:
            self.log("[경고] 패치할 낸드가 일부 수정된 상태일 수 있습니다. 백업으로 직접 복원하세요.")

    def _cleanup_work(self):
        if not self._unmount_ok:
            self.log(f"마운트가 남아있을 수 있어 작업 폴더를 지우지 않았습니다: {self.work}")
            return
        try:
            shutil.rmtree(self.work, ignore_errors=True)
        except Exception:
            pass
