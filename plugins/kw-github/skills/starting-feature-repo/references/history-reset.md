# 예전 기록 정리

이 파일은 `starting-feature-repo` 스킬의 참고 파일이다. 본문이 이 파일을 읽으라고 한 상황에서만 읽는다.

- `state` 가 `local-only` 이고 `has_commits` 가 `true` 면 예전 기록을 검사한다.

  ```
  python "${CLAUDE_PLUGIN_ROOT}/scripts/scan_history.py" --repo "<폴더>"
  ```

  `status` 가 `clean` 이면 기록을 그대로 둔다. `hits` 나 `timeout` 이면 개발자에게 묻지 않고 아래를 실행한다. 예전 기록은 이 PC 의 `local-history` 에 남고 GitHub 에는 올라가지 않는다. `local-history` 는 지우지 않는다.

  ```
  python "${CLAUDE_PLUGIN_ROOT}/scripts/reset_history.py" --repo "<폴더>"
  ```

  `scan_history.py` 의 `status` 가 `failed` 이고 `detail` 이 규칙 파일 오류면 `${CLAUDE_PLUGIN_ROOT}/skills/saving-work/references/rules-error.md` 대로 한다. 그 밖의 `failed` 면 한 번만 다시 실행한다. 다시 실행해도 `failed` 면 아래 「AX팀 문의 문장」을 알리고 멈춘다.

  `reset_history.py` 는 이미 있는 `local-history` 와 다른 branch 를 `local-history-<이름>` 으로 보관한 뒤 정리한다. branch 이름은 한 번에 함께 바뀌므로, 실패하면 하나도 바뀌지 않는다. 결과의 `status` 에 따라 아래대로 한다. 정리하지 않고 이어 가면 비밀값이 포함된 예전 기록이 첫 업로드 때 GitHub 에 올라가므로, `reset` 이 아니면 다음 단계로 가지 않는다.
  - `reset`: 정리를 마쳤다. 결과의 `kept` 가 비어 있지 않으면 개발자에게 "다른 branch 의 예전 작업은 이 PC 의 `<kept 의 새 이름들>` 에 보관했습니다. GitHub 에는 올리지 않습니다." 라고 알린다.
  - `failed`: 한 번만 다시 실행한다. 앞선 실행이 branch 를 옮긴 뒤 멈췄으면 다시 실행이 남은 단계를 마친다. 다시 실행해도 `reset` 이 아니면 「AX팀 문의 문장」을 알리고 멈춘다.
  - `refused` 이고 `reason` 이 `detached`: 지금 폴더가 어느 branch 의 끝도 아닌 예전 시점이다. AskUserQuestion 으로 "지금 폴더가 예전 시점의 파일입니다. 최신 작업으로 돌아간 뒤 정리할까요?" 라고 묻는다. 선택지는 `branches` 의 branch 마다 하나와 "멈추기" 다. branch 를 고르면 `git switch <branch>` 로 돌아간 뒤 `reset_history.py` 를 다시 실행한다. "멈추기" 면 「AX팀 문의 문장」을 알리고 멈춘다.
  - 그 밖의 `refused`: 스크립트가 아무것도 바꾸지 않았다. 다시 실행하지 않고 「AX팀 문의 문장」을 알리고 멈춘다. `reason` 이 `in-progress` 면 진행 중인 git 작업이 있고, `connected` 면 이미 GitHub 에 연결된 폴더다.

  「AX팀 문의 문장」은 "예전 기록을 정리하지 못해 GitHub 업로드 준비가 동작하지 않습니다. 작업은 이 PC 에 그대로 있습니다. AX팀에 문의해 주세요." 다. 이 문장과 함께 `detail` 의 원인을 AX팀에 전하라고 한다.
