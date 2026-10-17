"""가짜 마운트로 전체 흐름을 검증하는 테스트 (Windows/OSFMount/ninfs 없이 실행 가능).

    python -m pytest tests
"""

import hashlib
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dsinsqt import config, fileops, winutil  # noqa: E402
from dsinsqt.swapper import SwapOptions, NandSwapper  # noqa: E402


def _w(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def _make_nand(path):
    with open(path, "wb") as f:
        f.truncate(config.MIN_NAND_SIZE)


class FakeNinfs:
    def __init__(self, cmd, nand, mountpoint, cid, label, log):
        self.mountpoint, self.label = mountpoint, label
        self.twl_main = os.path.join(mountpoint, "twl_main.img")

    def mount(self):
        _w(self.twl_main, self.label.encode())
        return self.twl_main

    def unmount(self):
        return True


def make_fake_osf(volumes):
    class FakeOsf:
        def __init__(self, exe, image, label, log):
            self.label = label

        def mount(self):
            return volumes[self.label]

        def unmount(self):
            return True
    return FakeOsf


def test_full_pipeline(tmp_path):
    t = str(tmp_path)
    vol_a, vol_b = os.path.join(t, "volA"), os.path.join(t, "volB")
    # A 볼륨 (한글판)
    _w(os.path.join(vol_a, "title", "00030017", "484e414b", "content", "title.tmd"), b"KOR")
    _w(os.path.join(vol_a, "title", "00030017", "484e4141", "content", "00000001.app"), b"APP")
    _w(os.path.join(vol_a, "shared1", "TWLCFG0.dat"), b"c0")
    _w(os.path.join(vol_a, "shared1", "TWLCFG1.dat"), b"c1")
    _w(os.path.join(vol_a, "sys", "HWINFO_S.dat"), b"hw")
    os.makedirs(os.path.join(vol_a, "System Volume Information"))
    # B 볼륨 (기존 파일, 일부 읽기 전용)
    _w(os.path.join(vol_b, "old", "junk.bin"), b"old")
    winutil.set_readonly(os.path.join(vol_b, "old", "junk.bin"), True)
    _w(os.path.join(vol_b, "title", "00030017", "484e4141", "content", "title.tmd"), b"OLD")

    # unlaunch zip (.DS_Store 포함)
    tmd_zip = os.path.join(t, "unlaunch-tmd.zip")
    with zipfile.ZipFile(tmd_zip, "w") as z:
        z.writestr("00030017/484e4141/content/title.tmd", b"UNLAUNCH")
        z.writestr("00030017/484e4141/.DS_Store", b"mac")
        z.writestr("00030017/.DS_Store", b"mac")

    a_nand, b_nand = os.path.join(t, "a", "nand.bin"), os.path.join(t, "b", "nand.bin")
    os.makedirs(os.path.dirname(a_nand))
    os.makedirs(os.path.dirname(b_nand))
    _make_nand(a_nand)
    _make_nand(b_nand)
    _w(b_nand + ".sha1", b"0" * 40 + b" *nand.bin\r\n")

    opts = SwapOptions(b_path=b_nand, a_source="local", a_local_path=a_nand,
                        tmd_source="local", tmd_local_path=tmd_zip)
    logs = []
    p = NandSwapper(opts, log=logs.append, ninfs_factory=FakeNinfs,
                osf_factory=make_fake_osf({"A": vol_a, "B": vol_b}),
                ninfs_cmd=["ninfs"], osfmount_exe="OSFMount.com",
                work_root=os.path.join(t, "work"), cache_dir=os.path.join(t, "cache"))
    assert p.run(), "\n".join(logs)

    # B 의 예전 파일은 사라짐
    assert not os.path.exists(os.path.join(vol_b, "old"))
    # A 의 파일이 복사됨, SVI 는 건너뜀
    assert open(os.path.join(vol_b, "sys", "HWINFO_S.dat"), "rb").read() == b"hw"
    assert not os.path.exists(os.path.join(vol_b, "System Volume Information"))
    launcher = os.path.join(vol_b, "title", "00030017")
    tmd = os.path.join(launcher, "484e4141", "content", "title.tmd")
    assert open(tmd, "rb").read() == b"UNLAUNCH"
    # 병합 덮어쓰기: 기존 .app 는 유지
    assert os.path.exists(os.path.join(launcher, "484e4141", "content", "00000001.app"))
    # .DS_Store 는 복사하지 않음
    assert not os.path.exists(os.path.join(launcher, "484e4141", ".DS_Store"))
    # 00030017 하위 전부 읽기 전용
    for dp, dns, fns in os.walk(launcher):
        for n in dns + fns:
            assert winutil.is_readonly(os.path.join(dp, n)), n
    # TWLCFG 삭제
    assert not os.path.exists(os.path.join(vol_b, "shared1", "TWLCFG0.dat"))
    assert not os.path.exists(os.path.join(vol_b, "shared1", "TWLCFG1.dat"))
    # sha1 사이드카: 앞 40바이트만 교체
    side = open(b_nand + ".sha1", "rb").read()
    expect = hashlib.sha1(open(b_nand, "rb").read()).hexdigest().encode()
    assert side[:40] == expect and side[40:] == b" *nand.bin\r\n"
    # 백업 생성
    assert p.backup_path and os.path.isfile(p.backup_path)
    # 작업 폴더 정리
    assert not os.path.exists(os.path.join(t, "work"))

    # 정리 (읽기 전용 해제)
    fileops.clear_readonly_tree(launcher)


def test_sha1_sidecar_uppercase_and_new(tmp_path):
    nand = os.path.join(str(tmp_path), "nand.bin")
    _w(nand, b"hello")
    digest = hashlib.sha1(b"hello").hexdigest()
    fileops.write_sha1_sidecar(nand, digest)
    assert open(nand + ".sha1", "rb").read() == digest.encode()
    _w(nand + ".sha1", b"ABCDEF0123" * 4 + b"\n")
    fileops.write_sha1_sidecar(nand, digest)
    assert open(nand + ".sha1", "rb").read() == digest.upper().encode() + b"\n"


if __name__ == "__main__":
    import tempfile
    import pathlib
    with tempfile.TemporaryDirectory() as d:
        test_full_pipeline(pathlib.Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_sha1_sidecar_uppercase_and_new(pathlib.Path(d))
    print("OK")
