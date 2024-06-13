커뮤니케이션 블록 코드입니다.

핀번호를 사용하고 있는 보드의 설정에 맞게 바꿔주세요. 호환이 되지 않으면 구동되지 않습니다.

Edge Impulse와 연결하는 코드는 실제 블록 구동 코드에는 들어가지 않지만, jaejin_work_final/edge_impulse 폴더 안의 boot.py 파일을 CommBlockCode/boot.py 파일과 바꿔주신 후 테스트 해보실 수 있습니다. 

[과정]
0. edge impulse 계정을 만들고, 빈 프로젝트를 하나 생성합니다.
1. edge-impulse-data-forwarder를 다운로드 받습니다.

(**주의 !! 2, 3, 4번은 반드시 순서대로 진행되어야 합니다. 나중에 수정하실 때 코드를 간단하게 읽어보시길 바랍니다.**)

2. 사용하지 않으시는 다른 모션 블록의 main_program/main.py 파일을 jaejin_work_final/edge_impulse/motion_block_replace_code 안의 main.py 파일로 교체하고, 이 모션 블록의 코드를 **먼저** 실행시킵니다.
3. boot.py 파일을 위에서 말한 대로 교체하고, 커뮤니케이션 블록을 부팅합니다. (boot.py에 있는 내용에서 적절히 바꾸면 좋은 부분은 while 문에서 시리얼 데이터를 보내는 주기를 정하는 sleep_ms(몇ms) 부분입니다.)
4. 2번에서 설정한 모션 블록을 버튼을 눌러 mode 3으로 이동시킵니다. 이 시점부터 ESPNow를 통해 모션블록이 커뮤니케이션 블록에 센서 데이터 메시지를 보내고, 커뮤니케이션 블록은 받은 센서 데이터를 시리얼 메시지로 컴퓨터에 보내게 됩니다.
5. 아래 그림과 같이 터미널에서 edge-impulse-data-forwarder를 입력합니다. baudrate = 115200 입니다.
   ![image](https://github.com/ArchMelow/espnow_timbo_robot/assets/100942304/d68be12b-1630-4595-8461-1ca43e598ff2)
6. 컴퓨터에서 ESP32에서 보낸 시리얼 메시지를 받아들이는 포트로 아래 그림에서 설정합니다. (원하는 포트를 위아래 키보드로 고르고, enter를 누르면 됩니다.)
   ![image](https://github.com/ArchMelow/espnow_timbo_robot/assets/100942304/08b413e4-f7af-4ba9-8a3b-d20185cf89b6)
7. 이제 어느 프로젝트로 시리얼 데이터를 샘플링할지 고르시면 됩니다.
   ![image](https://github.com/ArchMelow/espnow_timbo_robot/assets/100942304/97764318-19b7-4378-875d-8add00182c0d)
8. 성공적으로 프로젝트에 연결되면, 들어오는 시리얼 데이터의 개수에 맞게 콤마(',')로 데이터 필드 당 이름을 지어 줄 수 있습니다. 입력 후 enter를 누르면 됩니다.
   ![image](https://github.com/ArchMelow/espnow_timbo_robot/assets 이100942304/a832901f-e7c6-448b-96e9-f2ee12af1b0e)
9. 입력 후 인터넷에 접속해서 [Data Acquisition] 탭에 들어갑니다.
   ![image](https://github.com/ArchMelow/espnow_timbo_robot/assets/100942304/c5c8430c-f8e4-4fad-a11e-9dfef39de1ee)
10. 이제 다음과 같이 원하는 샘플링 기간동안 샘플링을 진행할 수 있으며, 머신러닝을 위한 데이터 레이블링도 지원합니다.
   ![image](https://github.com/ArchMelow/espnow_timbo_robot/assets/100942304/3d06bc1d-5fce-426c-a167-a1096b04e856)

[참고 사항] 
1. edge-impulse-data-forwarder 문서 : https://github.com/edgeimpulse/edge-impulse-cli/blob/master/README-data-forwarder.md
2. 모델 만드는 법은 인터넷에 찾아보면 잘 설명되어 있고, 만들어진 .tflite 파일을 컴퓨터에 저장해서 모션블록에서 사용하려면 아래와 같은 과정을 거치면 됩니다:
   1) 모델이 필요한 모션 블록을 Wi-Fi에 연결해야 합니다. 이를 위해 커뮤니케이션 블록에서 처음 부팅 시 자동으로 AP에 붙게 되는데, 이 AP에 연결하여 웹서버에
      접속해서 Wi-Fi 비밀번호를 입력하면 커뮤니케이션 블록의 Wi-Fi 설정이 완료됩니다. 커뮤니케이션 블록을 이제 Wi-Fi를 공유하고자 하는 ESPNow 그룹들과 그루
      핗 한 이후에 Queen에서 '테이블 배포'를 하고 나면, Entry에 연결하려고 USB를 연결하지 않는 이상 커뮤니케이션 블록은 AP 모드로 넘어가게 됩니다. AP에 연
      결하여 웹서버에 접속하면 SHARE-WIFI라는 버튼이 있는데, 이를 눌러주시면 그룹 내에 있는 모션 블록에 Wi-Fi 설정이 모두 공유되면서 다른 블록들도 Wi-Fi 에
      연결할 수 있게 됩니다. 커뮤니케이션 블록이 웹서버에서 나오려면 EXIT 버튼을 눌러 주시면 됩니다.

   2) 이제 모션 블록 쪽에서 버튼을 눌러서 mode 4 (웹서버 모드)에 진입한 이후에, 버튼을 충분히 길게 눌러 줍니다. 이렇게 하면 특별히 다른 기기에서 AP에 연결하
      지 않고도 만약 모션 블록과 동일한 이름의 와이파이를 사용하고 있다면 웹서버에 연결됩니다. 웹서버에 연결하는 방법은 Thonny 등의 IDE에서 모션 블록의 로그
      를 확인해봤을 때, 괄호 안에 들어가 있는 맨 마지막 출력 중 (첫번째 주소):80으로 접속하면 됩니다. 이렇게 하면 manual에서 설명하는 웹사이트에 접속할 수 있
      는데, model 부분에서 '파일 선택' 버튼을 누르고 올리고자 하는 model.tflite 파일을 선택하여 'Upload' 버튼을 누르면 원하는 모션 블록으로의 모델 파일 업로
      드가 성공적으로 완료됩니다.

   3) 이제 모션 블록 쪽에서 다시 버튼을 눌러서 mode 3 (AI 모드)로 진입한 이후에, 버튼을 충분히 길게 눌러 줍니다. 그러면 자동으로 model 파일을 읽어와서 현재 구
      현되어 있는 간단한 'Hello-World' 예제를 실행해줍니다. (https://github.com/mocleiri/tensorflow-micropython-examples/tree/main/examples/hello-world)
      만약 application을 추가로 구현하고 싶으신 부분이 있으시다면, ai/app_ai.py를 수정하시면 됩니다.




