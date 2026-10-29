# DSi에서 낸드 추출(덤프)하기

이 프로그램은 DSi에서 추출한 **nand.bin** 과 **nand.bin.sha1** 파일을 수정합니다.

DSi에서 낸드를 추출하기 위해 먼저 해당하는 DSi에 Unlaunch를 설치 해야 됩니다.

DSi에 Unlaunch를 설치하는 방법은 인터넷에도 있지만, [dsi.cfw.guide](https://dsi.cfw.guide/ko_KR/) 사이트에서 절차에 맞게 진행한 후,
[Choosing a Menu](https://dsi.cfw.guide/ko_KR/choosing-a-menu.html) 목차에서 [Unlaunch Standalone](https://dsi.cfw.guide/ko_KR/installing-unlaunch-standalone.html) 방법을 따르는 가이드도 있습니다.

## 준비물

- Unlaunch가 설치된 DSi
- SD 카드 (낸드 파일 약 240MB + 여유 공간)
- [SafeNANDManager](https://github.com/DS-Homebrew/SafeNANDManager/releases/latest) 최신 버전

---

## 방법

1. SafeNANDManager를 내려받아 SD 카드에 복사합니다.
2. SD 카드를 DSi에 꽂고, Unlaunch 와 같은 홈브류에서 SafeNANDManager를 실행합니다.

![SafeNANDManager 첫 실행화면](images/screen1.png)

3. SafeNANDManager를 실행하면 다음과 같은 화면이 나올것입니다. 
4. 해당 화면에서 A를 눌러 낸드를 SD카드에 덤프합니다.
5. 덤프 과정이 끝날 때까지 기다립니다. 도중에 전원을 끄지 마세요.
6. 완료되었으면 SD카드를 PC에 연결합니다.
7. SD카드 루트에 **DT**로 시작하는 폴더 안에 **nand.bin** 과 **nand.bin.sha1** 이 생겼는지 확인합니다.
8. 해당 파일들은 DSi에서 추출된 낸드 파일입니다. 본 프로그램을 통해 수정하기 전, 안전한 저장소에 따로 백업 해 두는것을 권장드립니다.