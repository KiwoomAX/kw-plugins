# 기본 branch 맞추기

이 파일은 `saving-work` 스킬의 참고 파일이다. 본문이 이 파일을 읽으라고 한 상황에서만 읽는다. 「결과 처리」·「검토 요청 반영」 같은 절 이름은 `saving-work` 본문의 절이다.

기본 branch 가 `main` 이 아닌 레포(예: `master`)를 맞출 때 Claude 가 할 일이다. Claude 는 아래 상황에서만 할 일이 있다. 이 절의 결과는 `prepare-upload` 결과의 `main_branch` 칸이나 아래 명령의 결과다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" normalize-main --repo "<작업 폴더>"
```

- `needs-decision`: 예전 기본 branch(`old_branch`)에 `main` 에 없는 commit 이 있다. AskUserQuestion 으로 묻는다. 질문 문장은 "예전 기본 branch `<old_branch>` 에 main 에 없는 작업이 있습니다: `<commits 를 쉼표로>`. 이 작업을 main 에 반영할까요?" 이고, 선택지는 "반영" 과 "버리기" 다. 반영이면 `--merge-old <old_branch>`, 버리기면 `--discard-old <old_branch>` 를 붙여 위 명령을 실행한다. 버린 작업은 되살릴 수 없다고 선택지 설명에 적는다.
- `conflict`: 반영하다 충돌했다. 아무것도 지우지 않았다. `message` 를 전하고, 버릴지 그대로 두고 AX팀에 문의할지 묻는다. 버리기면 `--discard-old <old_branch>` 로 실행한다.
- `failed` 이고 `reason` 이 `no-permission`: "`<레포>` 의 기본 branch 가 `<old_branch>` 로 되어 있습니다. 이 GitHub 계정(`<account>`)에는 이 설정을 바꿀 관리자 권한이 없습니다. AX팀에 이 코드 저장소의 기본 branch 를 main 으로 바꿔 달라고 요청해 주세요." 라고 알리고 올리지 않는다. `prepare-upload` 결과면 `message` 가 이 문장이다. 그 밖의 `failed` 는 「결과 처리」 절의 「그 밖의 오류」대로 한다.
