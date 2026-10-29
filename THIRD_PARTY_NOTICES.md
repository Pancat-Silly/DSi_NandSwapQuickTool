# 제3자 소프트웨어 및 자료 고지

이 패치 파일에는 아래 항목이 **포함되어 있지 않습니다.** 프로그램은 사용자가 버튼을 눌렀을 때
각 공식 배포처에서 직접 내려받기만 합니다. 각 항목의 권리와 라이선스는 원저작자에게 있습니다.

| 항목 | 저작자 | 라이선스 | 받는 곳 |
|---|---|---|---|
| ninfs | Ian Burgwin (ihaveamac) | MIT | https://github.com/ihaveamac/ninfs |
| WinFsp (ninfs 설치 파일에 포함) | Bill Zissimopoulos | GPLv3 + FLOSS exception | https://github.com/winfsp/winfsp |
| OSFMount | PassMark Software | 프리웨어 (독점 라이선스, 재배포 불가로 간주) | https://www.osforensics.com/tools/mount-disk-images.html |
| SafeNANDManager | DS-Homebrew (zoogie/dumpTool 포크) | 저장소의 라이선스 확인 | https://github.com/DS-Homebrew/SafeNANDManager |
| Unlaunch / unlaunch TMD | nocash (Martin Korth) / gbatemp 게시자 | 별도 라이선스 없음 (재배포 허락 불명확) | https://gbatemp.net/attachments/unlaunch-tmd-zip.426330/ |

## 빌드 도구
- Python (PSF License) 과 표준 라이브러리 tkinter (Tcl/Tk: BSD 스타일) 가 exe 에 포함됩니다.
- PyInstaller 는 GPLv2 + 부트로더 예외 라이선스로, 이 예외 덕분에 만들어진 exe 는 어떤 라이선스로든 배포할 수 있습니다.
