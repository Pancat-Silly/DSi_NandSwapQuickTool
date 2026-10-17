"""프로그램 전역 상수 (URL, 경로 규칙 등)."""

APP_NAME = "DSi Nand Swap Quick Tool"
# %LOCALAPPDATA%\<APP_ID> (설정·로그·캐시), %TEMP%\<APP_ID> (작업 폴더) 이름
APP_ID = "Dsi_NSQT"
# 빌드되는 exe 파일 이름 (확장자 제외) — build.bat / build.yml 의 --name 과 같아야 함
EXE_NAME = "DSi_NSQT"
VERSION = "0.1.0"

USER_AGENT = f"{APP_ID}/{VERSION} (+https://github.com/)"

# --- 안내용 링크 -------------------------------------------------------------
SAFENANDMANAGER_URL = "https://github.com/DS-Homebrew/SafeNANDManager/releases/latest"

# --- A 낸드 (한글판 DSi 낸드) -------------------------------------------------
KOREAN_NAND_ZIP_URL = (
    "https://archive.org/download/korean-ds-firmware-korean-dsi-nand-firmware/"
    "Korean%20DS%20firmware%20%2B%20Korean%20DSi%20NAND%20%26%20firmware.zip"
)
KOREAN_NAND_ZIP_NAME = "Korean DS firmware + Korean DSi NAND & firmware.zip"
# zip 안에서 필요한 파일 (정확한 경로가 없으면 이름으로 검색)
KOREAN_NAND_ZIP_MEMBER = "Korean DS firmware + Korean DSi NAND & firmware/nand.bin"

# --- Unlaunch TMD ------------------------------------------------------------
UNLAUNCH_TMD_ZIP_URL = "https://gbatemp.net/attachments/unlaunch-tmd-zip.426330/"
UNLAUNCH_TMD_ZIP_NAME = "unlaunch-tmd.zip"

# 낸드 안의 경로 규칙
LAUNCHER_PARENT_DIR = "00030017"   # title\00030017
UNLAUNCH_TITLE_DIR = "484e4141"     # title\00030017\484e4141
UNLAUNCH_TMD_REL = ("content", "title.tmd")
TWLCFG_FILES = ("TWLCFG0.dat", "TWLCFG1.dat")
SHARED1_DIR = "shared1"
TITLE_DIR = "title"

# 복사 시 무시할 항목 (소문자로 비교)
SKIP_DIR_NAMES = {"system volume information", "__macosx", "$recycle.bin"}
SKIP_FILE_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}

# --- 외부 도구 ---------------------------------------------------------------
NINFS_RELEASES_API = "https://api.github.com/repos/ihaveamac/ninfs/releases/latest"
NINFS_FALLBACK_INSTALLER_URL = (
    "https://github.com/ihaveamac/ninfs/releases/download/v2.0/ninfs-2.0-win32-installer.exe"
)
NINFS_HOMEPAGE = "https://github.com/ihaveamac/ninfs"
# 수동 설치용: Windows 설치 파일(WinFsp 포함)이 올라오는 공식 릴리스 페이지
NINFS_RELEASES_URL = "https://github.com/ihaveamac/ninfs/releases/latest"
NINFS_LICENSE_URL = "https://github.com/ihaveamac/ninfs/blob/main/LICENSE.md"
WINFSP_HOMEPAGE = "https://winfsp.dev/rel/"
WINFSP_LICENSE_URL = "https://github.com/winfsp/winfsp/blob/master/License.txt"

OSFMOUNT_INSTALLER_URL = "https://www.osforensics.com/downloads/osfmount.exe"
OSFMOUNT_HOMEPAGE = "https://www.osforensics.com/tools/mount-disk-images.html"

# DSi 낸드 최소 크기 (ninfs 기준)
MIN_NAND_SIZE = 0xF000000
