"""PyInstaller --version-file 용 Windows 버전 정보 파일 생성.

exe 속성 → 자세히 탭에 제품명/버전이 표시된다 (백신 오탐을 약간 줄이는 효과도 있음).
사용: python scripts/make_version_info.py build/version_info.txt
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dsinsqt.config import APP_NAME, EXE_NAME, VERSION  # noqa: E402

TEMPLATE = """# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver},
    prodvers={ver},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('041204b0', [
        StringStruct('CompanyName', '{company}'),
        StringStruct('FileDescription', '{name}'),
        StringStruct('FileVersion', '{vs}'),
        StringStruct('InternalName', '{exe_name}'),
        StringStruct('LegalCopyright', 'MIT License'),
        StringStruct('OriginalFilename', '{exe_name}.exe'),
        StringStruct('ProductName', '{name}'),
        StringStruct('ProductVersion', '{vs}')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [0x0412, 1200])])
  ]
)
"""


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "build/version_info.txt"
    parts = [int(p) for p in VERSION.split(".") if p.isdigit()][:4]
    parts += [0] * (4 - len(parts))
    company = os.environ.get("GITHUB_REPOSITORY_OWNER", APP_NAME)
    text = TEMPLATE.format(ver=tuple(parts), vs=VERSION, name=APP_NAME, exe_name=EXE_NAME, company=company)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"wrote {out} ({VERSION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
