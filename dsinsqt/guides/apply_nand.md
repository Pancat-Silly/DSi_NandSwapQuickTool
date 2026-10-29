# 수정한 낸드 DSi에 적용하기

이 프로그램을 이용하여 DSi에서 추출한 낸드가 성공적으로 패치되었다면, 수정된 낸드를 SafeNANDManager로 DSi에 적용시키는 작업입니다.

## 적용 전 확인

- 패치 로그에 오류 없이 "완료"가 표시되었는지 확인
- 수정 전 처음으로 덤프된 기기의 낸드파일 (nand.bin & nand.bin.sha1) 백업이 존재하는지 확인
- DSi 배터리가 충분히 충전되어 있는지 확인

---

## 방법
1. 본 프로그램으로 수정 작업이 성공적으로 완료된 **nand.bin** 과 **nand.bin.sha1** 을 SD카드에 있는 **DT** 로 시작하는 폴더에 덮어씌웁니다.
2. SD 카드를 DSi에 꽂고, Unlaunch에서 [SafeNANDManager](https://github.com/DS-Homebrew/SafeNANDManager/releases/latest)를 실행합니다.

![SafeNANDManager 첫 실행화면](images/screen1.png)

3. SafeNANDManager를 실행하면 다음과 같은 화면이 나올것입니다. 
4. 해당 화면에서 Y를 누릅니다.

![SafeNANDManager 낸드 복원화면](images/screen2.png)

4. 해당 화면에서 X와 Y를 동시에 눌러 낸드를 DSi에 적용시킵니다.
5. 적용 과정이 끝날 때까지 기다립니다. 도중에 전원을 끄지 마세요.

---

## 마치며

본 프로그램을 이용한 낸드 수정작업이 성공적으로 완료되었습니다. 여기서 현 상태 그대로 유지해도 되나, 작성자가 권장하는 작업이 한가지 더 있습니다.

해당 프로그램에서 낸드를 수정 및 적용했다면, **사막 배경의 Unlaunch**가 설치되어있을겁니다.
Unlaunch설치 파일이 들어있는 sd카드를 DSi에 삽입해 Unlaunch메뉴에서 실행 및 Unlaunch를 한번 더 설치를 진행해주세요.

또한, Unlaunch 설치를 진행할때 기본적으로 **Disable DSi menu H&S** 항목이 적용되어 있습니다.
해당 항목은 DSi를 부팅할때 하단 화면에 뜨는 **경고 - 건강과 안전을 위하여** 문구입니다.
만약 해당 항목을 순정상태로 유지하고싶다면, 기본적으로 적용되어있는 항목을 해제 시킬 수 있습니다.

만약 부팅할때마다 Unlaunch 화면으로 들어가지는게 불편하다면, **OPTIONS** 메뉴에 들어가 **NO BUTTONS** 항목에 **LAUNCHER**를 선택해 적용시키세요.

본 작업은 필수가 아닌 선택적 추가 작업임을 다시한번 알립니다.