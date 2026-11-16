# 기능 이전 업로드

이 파일은 `saving-work` 스킬의 참고 파일이다. 본문이 이 파일을 읽으라고 한 상황에서만 읽는다. 「결과 처리」·「검토 요청 반영」 같은 절 이름은 `saving-work` 본문의 절이다.

kw-dashboard 의 기능 이전 절차는 `switch-feature --intake` 로 이전 branch 를 만들고, `commit`·`check-boundary`·`upload`·`review-upload` 에 모두 `--intake` 를 넘긴다. 이전 branch 에서는 `--intake` 없는 `commit`·`upload` 가 `failed` 로 멈춘다. 이때는 「push 질문」을 하지 않고 기능 이전 절차로 이어 간다. 업로드 승인은 기능 이전 절차가 공유 코드에 반영하기 직전에 하는 질문으로 받는다. 승인 없이 `upload --intake` 를 실행하지 않는다. `upload --continue` 에는 넘기지 않는다. 진행 기록대로 기능 이전 규칙을 쓴다.

`upload --intake` 가 `failed` 이면 `reason` 을 기능 이전 절차에 넘긴다. 처분은 기능 이전 절차가 정한다. 각 값의 뜻은 다음과 같다.

- `intake-conflict`: 그사이 공유 코드가 바뀌어 GitHub 가 충돌로 거부했다. PC 에서 합치지 않았고, GitHub 의 작업 branch 는 남겨 두었다. 다시 올릴 때 그 branch 위에 이어서 push 한다.
- `history-hits`: 기능 레포의 예전 commit 이나 올릴 내용에 올리면 안 되는 파일이 있다. 아무것도 올리지 않았다. 파일은 `detail` 에 있다.
- `template-unavailable`: `KiwoomAX/dashboard-template` 을 읽지 못해 구조 파일을 확인하지 못했다.
