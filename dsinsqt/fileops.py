"""마운트된 twl_main 볼륨 위에서 수행하는 파일 작업 + SHA1 처리."""

import hashlib
import os
import shutil
from typing import Callable, Iterable, Optional

from . import winutil

Log = Callable[[str], None]


def _lower_set(names: Optional[Iterable[str]]) -> set:
    return {n.lower() for n in (names or ())}


def force_remove(path: str) -> None:
    """읽기 전용 속성이 있어도 파일/폴더를 지운다."""
    if os.path.isdir(path) and not os.path.islink(path):
        winutil.set_readonly(path, False)
        with os.scandir(path) as it:
            children = [e.path for e in it]
        for child in children:
            force_remove(child)
        os.rmdir(path)
    else:
        winutil.set_readonly(path, False)
        os.remove(path)


def clear_readonly_tree(root: str) -> None:
    winutil.set_readonly(root, False)
    if os.path.isdir(root):
        for dirpath, dirnames, filenames in os.walk(root):
            for n in dirnames + filenames:
                winutil.set_readonly(os.path.join(dirpath, n), False)


def remove_contents(root: str, skip_dirs: Iterable[str] = (), log: Log = print) -> int:
    """root 안의 모든 항목을 삭제 (root 자체는 남김). 삭제 개수 반환."""
    skip = _lower_set(skip_dirs)
    count = 0
    with os.scandir(root) as it:
        entries = list(it)
    for entry in entries:
        if entry.name.lower() in skip:
            log(f"  건너뜀: {entry.name}")
            continue
        force_remove(entry.path)
        count += 1
    return count


def copy_tree_merge(src: str, dst: str, skip_dirs: Iterable[str] = (), skip_files: Iterable[str] = (),
                    preserve_attrs: bool = True, log: Optional[Log] = None) -> int:
    """src 의 내용을 dst 에 병합 복사(같은 이름은 덮어쓰기). 복사한 파일 수 반환."""
    sd, sf = _lower_set(skip_dirs), _lower_set(skip_files)
    if os.path.exists(dst) and not os.path.isdir(dst):
        force_remove(dst)
    os.makedirs(dst, exist_ok=True)
    winutil.set_readonly(dst, False)
    count = 0
    with os.scandir(src) as it:
        entries = list(it)
    for entry in entries:
        target = os.path.join(dst, entry.name)
        if entry.is_dir(follow_symlinks=False):
            if entry.name.lower() in sd:
                continue
            count += copy_tree_merge(entry.path, target, skip_dirs, skip_files, preserve_attrs, log)
        else:
            if entry.name.lower() in sf:
                continue
            if os.path.isdir(target):
                force_remove(target)
            elif os.path.exists(target):
                winutil.set_readonly(target, False)
            shutil.copyfile(entry.path, target)
            st = entry.stat()
            try:
                os.utime(target, (st.st_atime, st.st_mtime))
            except OSError:
                pass
            if preserve_attrs:
                winutil.copy_attributes(entry.path, target)
            count += 1
            if log:
                log(f"  복사: {target}")
    if preserve_attrs:
        winutil.copy_attributes(src, dst)
    return count


def set_readonly_tree(root: str, include_root: bool = False) -> int:
    """root 아래 모든 하위 폴더와 파일을 읽기 전용으로. 처리 개수 반환."""
    count = 0
    # 깊은 것부터 처리 (폴더 속성 변경이 하위 작업에 영향 주지 않도록)
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for n in filenames + dirnames:
            winutil.set_readonly(os.path.join(dirpath, n), True)
            count += 1
    if include_root:
        winutil.set_readonly(root, True)
        count += 1
    return count


def find_child_ci(parent: str, name: str) -> Optional[str]:
    """대소문자 구분 없이 하위 항목 찾기 (FAT 은 원래 구분 안 하지만 테스트 환경 대비)."""
    if not os.path.isdir(parent):
        return None
    with os.scandir(parent) as it:
        for entry in it:
            if entry.name.lower() == name.lower():
                return entry.path
    return None


# ---------------------------------------------------------------------------
# SHA1
# ---------------------------------------------------------------------------
def sha1_file(path: str, progress=None) -> str:
    h = hashlib.sha1()
    total = os.path.getsize(path)
    done = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return h.hexdigest()


def write_sha1_sidecar(nand_path: str, digest_hex: str) -> str:
    """<nand>.sha1 파일의 0x00~0x27 (40바이트) 를 새 SHA1(hex 문자열)로 덮어쓴다.

    나머지 바이트(파일명 표기 등)는 그대로 둔다. 기존 값이 대문자였으면 대문자로 쓴다.
    파일이 없으면 해시 40자만 담아 새로 만든다.
    """
    assert len(digest_hex) == 40
    side = nand_path + ".sha1"
    digest = digest_hex.lower()
    if os.path.exists(side):
        winutil.set_readonly(side, False)
        with open(side, "rb") as f:
            data = bytearray(f.read())
        old = bytes(data[:40])
        if old.isupper():  # 예: b"3F2A..." → 대문자 유지
            digest = digest.upper()
        data[0:40] = digest.encode("ascii")
    else:
        data = bytearray(digest.encode("ascii"))
    with open(side, "wb") as f:
        f.write(data)
    return side
