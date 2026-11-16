# 규칙 파일 오류

이 파일은 `saving-work` 스킬의 참고 파일이다. 본문이 이 파일을 읽으라고 한 상황에서만 읽는다. 「결과 처리」·「검토 요청 반영」 같은 절 이름은 `saving-work` 본문의 절이다.

규칙 파일을 직접 고치지 않는다. `detail` 이 AX팀 문의를 안내하라고 하면 개발자에게 "kw-github 의 저장 규칙 파일에 문제가 있어 저장이 동작하지 않습니다. AX팀에 문의해 주세요." 라고 알리고 끝낸다. 이 kw-github 버전에서 이미 다시 설치해 보았다는 뜻이다. 그 밖에는 `claude plugin update kw-github@kiwoom-ax` 를 실행한다. 출력이 새 버전으로 업데이트했다고 하면 개발자에게 "저장 규칙 파일을 읽지 못해 kw-github 를 업데이트했습니다. Claude Code 를 재시작한 뒤 같은 요청을 해 주세요." 라고 알린다. 출력이 이미 최신 버전이라고 하면 설치한 파일이 빠졌거나 깨졌을 수 있다. `claude plugin uninstall kw-github@kiwoom-ax` 와 `claude plugin install kw-github@kiwoom-ax` 를 차례로 실행하고, 개발자에게 "저장 규칙 파일을 읽지 못해 kw-github 를 다시 설치했습니다. Claude Code 를 재시작한 뒤 같은 요청을 해 주세요." 라고 알린다. install 이 실패하면 kw-github 가 빠진 상태이므로 개발자에게 "kw-github 를 다시 설치하지 못했습니다. 사내 설치기 kw_install 을 다시 실행해 주세요." 라고 알린다. update 명령이 실패하면 AX팀 문의 문장을 알린다. 재설치는 버전마다 한 번만 안내되므로, 재시작한 뒤 같은 오류가 나면 `detail` 이 AX팀 문의를 안내한다.
