"""DSi Nand Swap Quick Tool 진입점.

관리자 권한이 아니면 UAC 창을 띄워 관리자 권한으로 다시 실행한다.
(PyInstaller 빌드 시 --uac-admin 을 주면 처음부터 관리자 권한으로 실행된다)
"""

import sys

from dsinsqt import winutil


def main() -> int:
    if winutil.IS_WINDOWS and not winutil.is_admin() and "--no-elevate" not in sys.argv:
        if winutil.relaunch_as_admin():
            return 0
        # UAC 를 거부하면 그대로 실행하되 경고를 띄운다

    from dsinsqt.gui import run

    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
