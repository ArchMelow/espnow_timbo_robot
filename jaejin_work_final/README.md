# Jaejin's Final TimboRobot Work & Manual

구현 상세 및 구체적인 구동 방법은 manual 을 확인 바랍니다.

실행 하는 방법입니다.
1. ./MotionBlockCode 안에 있는 파일들을 그대로 모션 블록 저장소에 옮겨 넣습니다.
2. ./CommBlockCode 안에 있는 파일들을 그대로 커뮤니케이션 블록 저장소에 옮겨 넣습니다.

아직 다소 미흡한 부분입니다.
1. 웹서버 모드 (mode 4) 에서 Thonny IDE에서의 출력값을 보지 않고는 사용자가 접속해야 하는 웹주소를 확인할 방법이 없음 -> AP 서버를 잠깐 열어서 사용자에게
   웹 서버 사이트 상의 HTML 파일로 보여주는 방법이 있을 것 같음.
   ![image](https://github.com/ArchMelow/espnow_timbo_robot/assets/100942304/13b8a102-4b15-4950-a510-663a4660246d)

2. AI 모드 (mode 3) 의 애플리케이션 쪽은 더 개발이 필요함. -> 모델 입력/출력은 model_input_cb, model_output_cb로 해결할 수 있음을 참조.
3. 커뮤니케이션 블록의 AP 모드 상 개방되는 웹서버에서 Reverse Play 버튼을 누르고 다시 Play 버튼을 누르면 다시 플레이 순서가 정방향으로 돌아가지 않음.
   -> Reverse play 모드를 따로 다른 모드로 만들면 해결될 것 같은데, 구현이 어려울 수 있음.
4. LED 의 색깔이 각각 초록색, 빨간색 LED 값의 출력을 적절히 섞어서 사용하고 있으므로 다양한 색깔 표현이 어려움. -> 표현할 수 있는 LED 색을 더 다양하게 하려면
   LED 핀을 더 많이 사용하는 것을 추천함.
