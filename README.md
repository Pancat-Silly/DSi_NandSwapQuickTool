# DSi Nand Swap Quick Tool

닌텐도 DSi 낸드 덤프(`nand.bin`)에 다른 DSi기기에서 덤프된 낸드의 내용을 옮기는 작업을
클릭 몇 번으로 자동화하는 Windows 프로그램입니다.

> ## ⚠ 시작하기 전에
> - 이 프로그램은 낸드 덤프를 **직접 수정**합니다. 잘못되면 DSi 가 벽돌이 될 수 있습니다.
> - 반드시 **Unlaunch가 설치되어 있는 상태의 낸드**를
>   [SafeNANDManager](https://github.com/DS-Homebrew/SafeNANDManager/releases/latest) 로 덤프 한 뒤 사용하세요.
> - 덤프한 `nand.bin` 과 `nand.bin.sha1` 원본은 다른 곳에 따로 백업해 두는것을 추천합니다.

## 필요한 것
- Windows 10/11 (64비트), 관리자 권한
- ninfs + WinFsp, OSFMount
  - 위 프로그램들은 해당 패치 프로그램에서 자동/수동 설치 할 수 있습니다.

## 사용법
1. `DSi_NSQT.exe` 또는, `Source code`에 있는 `main.py`실행
2. ninfs + WinFsp와 OSFMount가 설치되었는지 확인
3. 패치에 사용될 낸드(nand.bin) 선택
4. Unlaunch TMD 선택
5. 수정할 낸드(nand.bin)를 선택 후 `패치 시작`
6. 완료 후 수정된 `nand.bin` 을 SafeNANDManager로 DSi 에 복원(restore)

## 자동으로 하는 일
1. ninfs `nanddsi` 로 사용될/수정할 낸드를 **쓰기 허용**으로 각각 임시 폴더에 마운트
   (GUI 버전의 *New mount → Nintendo DSi NAND backup → Allow writing* 과 같은 동작)
2. 각 마운트 안의 `twl_main.img` 를 OSFMount **Direct Write 모드**(`-o rw`)로 마운트
3. 수정할 낸드의 `twl_main.img` 안에 있는 모든 파일 삭제 → 패치에 사용될 낸드의 모든 파일을 수정할 낸드로 복사
4. 수정할 낸드의 `title\00030017` 하위 폴더/파일을 전부 읽기 전용으로 만듦
5. unlaunch-tmd를 수정할 낸드에 덮어쓰기 후 읽기 전용으로 만듦
6. `shared1`폴더에 있는`TWLCFG0.dat`, `TWLCFG1.dat` 삭제
7. OSFMount 마운트 전부 해제 → ninfs 마운트 전부 해제
8. 수정할 낸드의 새 SHA1 을 `nand.bin.sha1` 에 재작성

안전장치: 작업 전 수정할 낸드 자동 백업(`nand.bin.<시각>.bak`), 실패 시 자동 복원, 오류가 나도 마운트는 항상 해제,
마운트 이후 단계는 취소 불가(중간에 끊겨 낸드가 깨지는 것 방지). 로그는 `%LOCALAPPDATA%\Dsi_NSQT\logs` 에 저장됩니다.

## 소스에서 실행 / 빌드
```bat
:: 실행 (표준 라이브러리만 사용)
python main.py

:: exe 빌드 → dist\DSi_NSQT.exe
build.bat
```

## 문제 해결
- **`CERTIFICATE_VERIFY_FAILED` / `self-signed certificate in certificate chain`**: 다운로드는 Windows 내장
  `curl.exe`(Windows 인증서 저장소 사용)로 하므로 브라우저에서 열리는 주소면 보통 받아집니다. 그래도 실패하면
  백신의 HTTPS(웹) 검사나 프록시를 확인하거나, 브라우저로 zip 을 직접 받아 '로컬' 옵션으로 선택하세요.
- **OSFMount 로그의 'Failed, forcing dismount...'**: 백신/검색 색인 등이 드라이브를 잡고 있으면 나오는 정상 메시지입니다.
  OSFMount 는 버퍼를 먼저 디스크에 기록(Flushing file buffers)한 뒤 강제로 해제하므로 데이터는 반영된 상태입니다.

## 프로젝트 구조
```
main.py                 진입점 (관리자 권한 재실행)
dsinsqt/config.py       URL, 경로 규칙 등 상수
dsinsqt/gui.py          tkinter 화면
dsinsqt/swapper.py      전체 작업 흐름
dsinsqt/mounts.py       ninfs / OSFMount 마운트·해제
dsinsqt/fileops.py      파일 삭제·복사·읽기전용·SHA1
dsinsqt/tools.py        도구 탐지·자동 설치
dsinsqt/downloader.py   다운로드·zip 처리
dsinsqt/winutil.py      Windows API (속성, 레지스트리, UAC)
```

## 라이선스
이 프로젝트의 소스 코드는 [MIT License](LICENSE) 입니다. ninfs, WinFsp, OSFMount, Unlaunch, 펌웨어 등
제3자 항목은 포함되어 있지 않으며 각자의 라이선스를 따릅니다. 자세한 내용은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 를 참고해주세요.

## 면책
본 패치의 설치 및 사용은 사용자의 판단과 책임하에 이루어집니다. 패치 적용 과정 또는 적용 이후 발생하는 오류, 데이터 손실 및 기타 불이익에 대하여 제작자는 책임을 지지 않습니다.

## 그 외
본 패치 프로그램은 AI의 도움을 받아 제작되었습니다.
