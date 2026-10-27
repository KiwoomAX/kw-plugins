---
name: saving-work
description: 사내 개발자용 기능 레포(최상위 폴더에 .kiwoom-feature 가 있는 폴더)와 KiwoomAX 의 공유 대시보드 레포(이름이 dashboard 로 끝나는 레포)에서 기능 단위를 끝냈을 때 작업을 commit 하고, 개발자가 승인하면 회사 GitHub 에 올린다. 개발자가 "저장해줘", "올려줘"라고 말할 때, 결과를 보고 기능이 끝났다고 할 때, 세션 시작 알림이 업로드 질문이나 실패를 전했을 때도 쓴다.
---

# 작업 저장과 업로드

이 스킬은 기능 레포의 작업을 이 PC 에 commit 하고, 개발자가 승인한 작업만 회사 GitHub 에 push 한다. commit 과 push 는 언제나 `save_work.py` 로 한다. 저장 스크립트만 비밀값과 데이터 파일을 검사하므로 `git commit` 과 `git push` 를 직접 실행하지 않는다. 가드 훅도 그 명령을 거부한다.

개발자는 commit, push, branch 같은 개념에 익숙하지 않다고 본다. 개발자에게 하는 말은 `${CLAUDE_PLUGIN_ROOT}/git_terms.md` 를 따른다. commit·push·main·branch 만 영어로 쓰고 그 행동의 결과를 같은 문장에 붙인다. 나머지 git 용어는 쉬운 말로 바꾸거나 말하지 않는다. 예: "commit 해 두었습니다. 이 시점으로 코드를 되돌릴 수 있습니다."

아래에서 `<작업 폴더>` 는 지금 작업 중인 폴더이고, `<레포>` 는 push 절차 2단계의 `prepare-upload` 결과의 `repo` 다(예: `KiwoomAX/fund-list`). 이슈 제목의 `<name>` 은 `<레포>` 의 `/` 뒤 이름이다. 예전 방식 레포는 표식 파일에 `name` 이 없으므로 표식 파일에서 이 값을 읽지 않는다. 이슈 본문 파일은 기능 레포 밖의 임시 폴더에 쓴다. 레포 안에 쓰면 다음 commit 에 함께 들어간다.

## commit

기능 단위가 끝나면 개발자에게 묻지 않고 commit 한다. "저장해줘" 같은 요청을 기다리지 않는다. commit 은 이 PC 에만 남고 GitHub 에 올리지 않으므로 승인이 필요하지 않다. 기능 단위는 개발자가 요청한 기능 하나가 동작하는 상태가 된 때다. 화면 하나를 완성했을 때, 스크립트가 처음으로 끝까지 실행됐을 때, 버그 하나를 고쳤을 때가 그 예다. 한 세션에서 여러 번 commit 해도 된다.

1. 이번에 바뀐 파일을 `${CLAUDE_PLUGIN_ROOT}/data_security_checklist.md` 의 점검표로 검토한다. 해당하는 것이 있으면 commit 하기 전에 고친다. 비밀값은 `.env` 로 옮기고 코드에서는 환경 변수로 읽게 하며, 업무 데이터와 개인정보는 코드에서 빼고, ipynb 출력 셀은 지운다. 고친 내용을 개발자에게 한 줄로 알린다.
2. 현재 작업 branch가 `feat/session-` 으로 시작하면 먼저 `git branch -m <새 이름>` 으로 이름을 작업 내용에 맞게 바꾼다. 세션 시작 훅이 이름을 정할 수 없어 붙인 이름이다.
3. 이번에 한 일을 한국어 한 줄로 적고 아래 명령을 실행한다. "출금요청서를 엑셀로 바꾸는 화면 추가" 처럼 쓴다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" commit --repo "<작업 폴더>" --message "<한 줄 설명>" --branch <종류>/<영문 요약>
   ```

   `--branch` 는 새 작업 branch가 필요할 때 쓰는 이름이다. 종류는 `feat/`(기능)·`fix/`(버그)·`refactor/`(정리)·`docs/`(문서) 중 하나이고, 영문 요약은 `fund-list-screen` 처럼 소문자와 하이픈으로 쓴다. 이미 이어 쓸 작업 branch가 있으면 스크립트가 그 branch를 쓰고 `--branch` 는 무시한다. 첫 commit 은 `main` 에 들어간다.

4. 결과를 「결과 처리」 절에 따라 처리한다. 결과의 `unpushed` 가 참이면 이어서 「push 질문」 절에 따라 묻는다.

## 결과 처리

결과 JSON 의 `message` 를 개발자에게 그대로 전한다. `detail` 은 전하지 않는다. `detail` 은 Claude 가 읽고 처리할 설명이다.

`excluded` 에 든 파일은 `reason` 에 따라 처리한다.
- `secret-content` 는 코드에 비밀번호나 키 같은 값이 적힌 파일이다. 이번 commit 에서만 빠졌다. 그 값을 `.env` 파일로 옮기고 코드에서는 환경 변수로 읽게 고치자고 개발자에게 제안한다. 개발자가 동의하면 고친 뒤 다시 commit 한다. `.env` 는 올라가지 않는다.
- `secret-content-tracked` 는 이미 GitHub 에 올라간 코드에 비밀값이 든 파일이다. 위와 같이 `.env` 로 옮기자고 제안하고, 그 비밀값은 이미 밖에 나갔으므로 폐기하고 새로 발급받으라고 알린다.
- `secret-filename` 은 `.env` 나 키 파일처럼 이름만으로 비밀값 파일로 판정된 파일이다. 저장 스크립트가 이미 제외 목록에 넣었으므로 할 일이 없다.
- `secret-filename-tracked` 는 예전에 올라간 비밀값 파일이다. 저장 스크립트가 올리기를 멈췄지만 예전 기록에는 남아 있다. 그 파일의 비밀값을 폐기하고 새로 발급받으라고 알린다.
- `data` 는 데이터 파일이다. 데이터는 레포에 올리지 않는다. 저장 스크립트가 이미 제외 목록에 넣었으므로 `message` 만 전한다.

`status` 가 `failed` 면 `detail` 을 읽고 아래대로 처리한 뒤 다시 실행한다. 개발자에게 물을 수 있는 것은 동작이 다른 충돌과 어느 작업을 먼저 올릴지뿐이다. 나머지는 묻지도 설명하지도 않는다.
- **진행 중인 merge 가 있다.** 앞선 업로드가 충돌로 멈췄다. 「push 절차」 5단계대로 충돌을 풀고 `upload --continue` 로 마친다.
- **미반영 commit 이 있는 작업 branch 가 둘 이상이다.** `detail` 이 정한 대로 한다. 개발자에게 두 작업을 쉬운 말로 적어 어느 쪽을 먼저 올릴지 묻고, `git switch <branch>` 로 그 branch 로 옮겨 「push 절차」대로 올린 뒤 다시 commit 한다. branch 를 `git merge` 로 합치거나 지우지 않고, `git reset` 으로 commit 을 버리지 않는다.
- **새 작업 branch의 이름이 없다.** 이번 작업에 맞는 이름을 정해 `--branch` 로 다시 실행한다.
- **제한 시간을 넘겼다.** 한 번만 다시 실행한다. 또 실패하면 `message` 만 전하고 넘어간다.
- **규칙 파일 오류다.** 고치지 않는다. `message` 만 전한다. AX팀이 고칠 일이다.
- **git 이나 gh 를 찾지 못했거나 GitHub 로그인이 필요하다.** 개발자에게 사내 설치기 `kw_install` 을 다시 실행하거나, 터미널에서 `gh auth login --web --git-protocol https --skip-ssh-key --clipboard` 를 한 번 실행하라고 안내한다.
- **그 밖의 오류다.** `detail` 에 포함된 명령 출력을 읽고 원인을 고친 뒤 다시 실행한다. 두 번 고쳐도 실패하면 멈추고 `message` 만 전한다.

## push 질문

commit 결과나 세션 시작 알림이 GitHub 에 올리지 않은 commit 이 있다고 하면 개발자에게 묻는다. 글로 묻지 않고 AskUserQuestion 선택 창 하나에 질문 두 개를 넣어 묻는다. 개발자가 버튼으로 바로 답하게 하기 위해서다.

첫째 질문의 머리(header)는 "GitHub 업로드" 이고, 질문 문장은 아래를 그대로 쓴다. 선택지는 "올리기" 와 "나중에" 다.

> 지금까지 작업을 GitHub에 올릴까요? 올리면 회사 GitHub(KiwoomAX)에 저장됩니다.

결과의 `first_push` 가 참이고 `history_reset` 이 `hit` 이면 "예전 기록에 올리면 안 되는 파일이 있어 지금 파일만 올립니다." 를, `timeout` 이면 "예전 기록을 끝까지 확인하지 못해 지금 파일만 올립니다." 를 질문 문장 뒤에 덧붙인다.

둘째 질문의 머리는 "기능 마무리" 이고, 질문 문장은 "이 기능은 여기서 마무리할까요?" 다. 선택지는 "계속 개발" 과 "마무리" 다. 기능 이슈를 닫을지 정하기 위해서다. 개발자가 "계속 개발" 을 고르면 같은 기능 단위에서는 마무리 여부를 다시 묻지 않는다. "마무리" 는 개발자가 고른 때에만 기능 이슈를 닫는 근거로 쓴다. "계속 개발" 을 골랐으면 바뀐 것이 없으므로 업로드 뒤 따로 알리지 않는다. "마무리" 를 골라 기능 이슈를 닫았으면 "이 기능을 마무리했습니다." 한 줄만 알린다.

**승인 규칙.** push 질문에 대한 동의나 개발자가 먼저 한 "올려줘" 같은 요청을 승인으로 본다. 승인은 받은 세션 안에서 그 push 한 번을 마칠 때까지 유효하다. 충돌 해결이나 로그인 때문에 멈췄다 이어 가도 다시 묻지 않는다. 세션이 바뀌면 다시 묻는다. 개발자가 "나중에" 라고 하면 이 세션에서는 다시 묻지 않는다. 승인 없이 `prepare-upload` 나 `upload` 를 실행하지 않는다.

## push 절차

승인되면 아래를 차례로 한다.

1. `gh auth token` 으로 로그인을 확인한다. 로그인이 안 되어 있으면 위의 로그인 안내를 하고, 개발자가 로그인하면 이어 간다.
2. 원격 레포와 기능 이슈를 맞춘다. 표식 파일에 `issue=` 줄이 없으면 이번에 기능 이슈가 새로 생긴다. 그때는 먼저 기능 요청 템플릿을 받아 각 `##` 절을 이 기능의 내용으로 채운다. 템플릿의 frontmatter(`---` 블록)와 안내 주석(`<!-- -->`)은 지운다. 채운 본문은 기능 레포 밖의 임시 폴더에 파일로 쓰고 `--body-file` 로 넘긴다. 빈 절로 이슈를 만들지 않는다.

   ```
   gh api -H "Accept: application/vnd.github.raw" repos/KiwoomAX/.github/contents/.github/ISSUE_TEMPLATE/03_feature_request.md
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" prepare-upload --repo "<작업 폴더>" --body-file "<본문 파일>"
   ```

   표식 파일에 `issue=` 줄이 있으면 `--body-file` 없이 실행한다.

   `team_shared` 가 거짓이면 개발자에게 "팀 공유는 설정하지 못했습니다. AX팀에 요청해 주세요." 라고 알린다. 같은 이름의 레포가 이미 있어 `failed` 면 개발자에게 "같은 이름의 GitHub 코드 저장소가 이미 있어 이 이름은 쓸 수 없습니다." 라고 알리고, 다른 이름을 정해 표식 파일의 `name` 을 고친 뒤 다시 실행한다. 결과의 `feature_issue` 가 기능 이슈 번호다.

   `status` 가 `other-owner` 면 올리려는 곳이 회사 GitHub(KiwoomAX)가 아니다. 개발자에게 `detail` 의 주소를 보여 주고 "올리려는 곳이 회사 GitHub(KiwoomAX)가 아닙니다. `<주소>` 에 올려도 될까요?" 라고 묻는다. 개발자가 동의하면 `prepare-upload` 와 4단계의 `upload` 에 모두 `--allow-other-owner` 를 붙여 실행한다. 이 동의는 그 push 한 번에만 유효하다. 동의하지 않으면 올리지 않고 멈춘다. `upload` 가 `other-owner` 를 내도 같은 방법으로 묻는다.

3. 작업 이슈를 정한다. 「작업 이슈」 절에 따라 한다.
4. 올린다. 고친 버그의 번호와, 개발자가 기능을 마무리하기로 했으면 기능 이슈 번호를 번호마다 `--close <번호>` 로 넘긴다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" upload --repo "<작업 폴더>" --task <작업 이슈 번호> --title "<작업 이슈 제목>"
   ```

   스크립트는 작업 branch를 push 한 뒤 GitHub 에서 `main` 에 merge 하고, merge 된 작업 branch는 이 PC 와 GitHub 에서 지운다. 그사이 다른 PC 가 올린 작업과 충돌하면 이 PC 에서 `main` 을 합쳐 다시 올린다. GitHub 가 반영하지 못하면 "작업을 GitHub 에 push(업로드)했지만 팀이 함께 보는 main 에 반영하지 못했습니다. 잠시 뒤 다시 올려 주세요. 계속되면 AX팀에 문의해 주세요." 를 `message` 로 낸다. 잠시 뒤 `upload --continue` 로 이어 간다. merge commit의 `closes` 줄이 작업 이슈와 `--close` 로 넘긴 이슈를 닫는다. 결과를 「결과 처리」 절에 따라 처리한다. `status` 가 `nothing` 이면 올릴 commit 이 없다는 뜻이다. 이때 기능을 마무리하기로 했으면 `gh issue close <기능 이슈 번호> -R <레포>` 로 닫는다.

5. `upload` 가 충돌로 멈추면 충돌한 파일을 연다. 두 곳에서 같은 줄을 다르게 고쳤다. 양쪽의 동작이 같고 줄바꿈·공백·표기만 다르면 개발자에게 묻지 않고 푼다. 양쪽의 동작이 다를 때만 묻는다. 질문에는 "GitHub에 올라온 것"과 "지금 PC에 저장된 것"이라는 표현을 쓴다. 두 쪽이 각각 어떻게 동작하는지 A 와 B 로 적고, 차이가 의도한 변경인지와 어느 쪽으로 갈지를 고르게 한다. 고친 뒤 `git add <파일>` 을 하고 아래를 실행한다. 이어서 하는 업로드는 다시 승인받지 않는다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" upload --repo "<작업 폴더>" --continue
   ```

6. **업로드 뒤 점검.** `upload` 가 `uploaded` 로 끝나면 아래를 실행해 결과를 차례로 처리한다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" review-upload --repo "<작업 폴더>"
   ```

   - `uploaded` 가 거짓이면 이번 업로드가 GitHub 의 `main` 에 없다. 다른 PC 에서 올린 작업이 있다는 뜻이므로 개발자에게 알린다.
   - `leaked` 에 파일이 있으면 GitHub 의 `main`에 올라가면 안 되는 파일이 이미 올라가 있다. 파일과 `reason` 을 개발자에게 알리고, 비밀값이면 폐기하고 새로 발급받으라고 안내한다. 지우는 일은 개발자의 동의를 받은 뒤 commit 과 업로드로 한다.
   - 이슈는 개발자에게 말하지도 묻지도 않는다(사용자 결정, 2026-10-21). `issues` 중 `ours` 가 참인 이슈만 Claude 가 정리하고, `ours` 가 거짓인 이슈는 다른 사람이 만든 이슈이므로 손대지 않고 알리지 않는다.
   - `ours` 인 기능 이슈와 작업 이슈 중 만들다 만 이슈(`template_only` 가 참)와 기록이 빠진 이슈(이번 merge 까지 올라간 commit 이 본문의 commit 목록에 없음)는 본문을 고쳐 채운다. 이 기능과 이번 작업에서 아는 내용과 `git log` 의 commit 으로 각 절을 채워 레포 밖 임시 파일에 쓰고 `gh issue edit <번호> -R <레포> --body-file "<본문 파일>"` 로 고친다. 모르는 절은 "확인 필요" 로 적는다.
   - `ours` 이고 `template_only` 인데 기능 이슈도 아니고 어느 commit 과도 이어지지 않은 이슈는 오류로 생긴 빈 이슈다. 다음 작업 이슈를 만들 때 다시 쓸 수 있으므로 하나는 남겨 두고, 그보다 많으면 `gh issue delete <번호> -R <레포> --yes` 로 지운다. 삭제 권한이 없어 실패하면 `gh issue close <번호> -R <레포> --reason "not planned"` 로 닫는다.
   - `ours` 이고 `no_assignee` 가 참인 이슈는 `gh issue edit <번호> -R <레포> --add-assignee '@me'` 로 담당자를 지정한다.
   - `ours` 이고 `feature` 가 참인 이슈는 진행 중인 기능 이슈이므로 그대로 둔다. 그 밖에 열려 있는 `ours` 작업 이슈와 Bug 이슈는 Claude 가 판단한다. 이번 업로드까지의 commit 으로 끝난 일이면 `gh issue close <번호> -R <레포>` 로 닫고, 아직 남은 일이면 그대로 둔다.

   점검 결과는 `leaked` 가 있거나 `uploaded` 가 거짓일 때만 개발자에게 알린다. 이슈를 정리한 일은 알리지 않는다.

기능을 끝내는 방법은 개발자의 답에 따른다.
- 개발자가 끝났다고 하면 4단계에서 기능 이슈 번호를 `--close` 로 넘긴다.
- 개발자가 일부만 하고 나머지는 하지 않겠다고 하면 위와 같이 닫고, 하지 않기로 한 기능을 기능 이슈에 댓글로 남긴다.
- 개발자가 중단하겠다고 하면 남은 작업을 올린 뒤 `gh issue close <기능 이슈 번호> -R <레포> --reason "not planned" --comment "<중단 사유>"` 로 닫는다. `--close` 는 쓰지 않는다. 완료로 닫히기 때문이다.
- 닫은 뒤 같은 기능에 작업이 이어지면 다시 열지 않는다.

## 작업 이슈

push 한 번마다 작업 이슈 하나를 정한다. 무엇을 언제 올렸는지 이슈 목록으로 남기기 위해서다. 제목은 `[<name>] <이번에 한 일을 쉬운 말로 한 줄>` 이다. 본문에는 `기능 이슈: #<기능 이슈 번호>` 와, 올릴 commit 목록을 적는다. commit 목록은 `prepare-upload` 결과의 `commits` 를 그대로 쓴다. 첫 push 에는 `origin/main` 이 없어 `git log` 로 직접 계산할 수 없기 때문이다.

열린 `Task` 이슈 중 본문의 commit 목록이 이번 `commits` 를 모두 포함한 이슈가 있으면 새로 만들지 않고 그 이슈를 쓴다. 앞선 push 가 끊긴 상황이다. 그런 이슈가 없고, 제목이 `[<name>] ` 으로 시작하는데 본문이 양식뿐이고 어느 commit 과도 이어지지 않은 빈 이슈가 열려 있으면 새로 만들지 않는다. 오류로 생긴 빈 이슈이므로 `gh issue edit <번호> -R <레포> --title "<제목>" --body-file "<본문 파일>" --add-assignee '@me'` 로 이번 작업 이슈를 거기에 적어 다시 쓴다. 둘 다 없으면 새로 만든다. 어느 쪽이든 Type 을 `Task` 로 정한다.

```
gh issue create -R <레포> --title "[<name>] <한 줄>" --body-file "<본문 파일>" --assignee '@me'
gh api -X PATCH repos/<레포>/issues/<새 번호> -f type=Task
```

`gh issue create` 가 출력한 주소의 끝 숫자가 새 번호다. 이 번호를 `upload` 의 `--task` 로 넘긴다.

## 기능 이슈에 남기는 기록

기능 레포에는 그 기능을 대표하는 기능 이슈가 하나 있고, 번호는 `.kiwoom-feature` 의 `issue=` 줄에 있다. 첫 push 때 `prepare-upload` 가 만들고 적는다. merge commit에 `#<기능 이슈 번호>` 줄이 붙으므로 올린 작업은 이슈 화면에 저절로 나타난다. 이슈 기록은 개발자에게 묻지 않고 Claude 가 남긴다. 기능 이슈 번호가 아직 없으면 기록을 생략한다.

- **버그를 찾았을 때.** 찾을 때마다 Bug 이슈를 따로 만든다. 본문 끝에 `기능 이슈: #<기능 이슈 번호>` 를 적어 연결한다. 고친 버그는 그 버그를 올리는 `upload` 의 `--close` 로 닫는다.

  ```
  gh issue create -R <레포> --title "[<name>] <버그를 쉬운 말로 한 줄>" --body-file "<본문 파일>" --assignee '@me'
  gh api -X PATCH repos/<레포>/issues/<새 번호> -f type=Bug
  ```

- **실측한 결과가 있을 때.** 기능 이슈에 댓글로 남긴다. 무엇을 어떤 조건에서 측정했고 결과가 무엇인지 적는다.
- **개발자에게 설명이 필요했던 지점이 있을 때.** 기능 이슈에 댓글로 남긴다. 개발자 본인과 조직 멤버가 읽으므로 사람을 평가하는 표현은 쓰지 않는다. "설명이 필요했던 지점: 업로드 충돌 안내" 처럼 Claude 가 설명한 주제만 적는다.

  ```
  gh issue comment <기능 이슈 번호> -R <레포> --body-file "<본문 파일>"
  ```

이슈는 `upload` 의 `--task` 와 `--close` 로만 닫고, commit 메시지에 닫기 키워드를 직접 쓰지 않는다.

## 공유 대시보드 레포

origin 이 `KiwoomAX/<이름>` 이고 이름이 `dashboard` 로 끝나는 레포는 여러 개발자가 기능별 폴더로 나누어 함께 쓰는 공유 대시보드 레포다(`dashboard-template` 은 아니다). 표식 파일이 없어도 이 절을 따른다. 위의 commit·push 절차 대신 아래를 쓴다. 공유 레포에서는 개발자에게 main 을 "공유 코드" 라고 하고, merge 는 "반영", PR 은 "검토 요청" 이라고 한다. 이슈는 말하지 않는다.

기능 폴더는 `src/frontend/src/features/<기능>/`, `src/backend/features/<기능>/`, `docs/<기능>.pdf`·`docs/<기능>.docx` 다. 한 기능의 작업 branch 에는 그 기능 폴더만 고친다. 기능 이름은 개발자가 고치는 기능 폴더 이름이다. 모르면 묻는다.

### 결과의 `status`

- `unsupported` 면 개발자에게 "이 대시보드는 아직 기능별 폴더로 나뉘지 않아 공유 코드에 반영할 수 없습니다. AX팀에 문의해 주세요." 라고 알리고 멈춘다.
- `invalid-feature` 면 "어느 기능을 고치는지 확인하지 못했습니다. 기능 이름을 다시 알려 주세요." 라고 알리고, 개발자에게 받은 이름으로 다시 실행한다.
- `failed` 는 위 「결과 처리」 절에 따라 처리한다. `reason` 이 있으면 「기능 이전 업로드」 절에 따라 처리한다.

### 기능 전환과 사본 작업 폴더

commit 하기 전에 그 기능의 작업 branch 로 옮긴다. 없으면 만든다. 영문 요약은 `fund-chart` 처럼 소문자와 하이픈으로 쓴다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" switch-feature --repo "<작업 폴더>" --feature <기능> --summary <영문 요약>
```

결과의 `new_feature` 가 참이면 공유 코드에 아직 없는 새 기능이다. 이때는 개발자에게 선택 창으로 "새 기능은 대시보드 레포가 아니라 별도 기능 레포에서 개발하고, 어느 정도 구현되면 대시보드에 합치기를 권장합니다. 그래도 이 대시보드에서 바로 개발할까요?" 라고 묻는다. 별도 기능 레포를 고르면 starting-feature-repo 스킬로 새 폴더에 기능 레포를 만든다. 바로 개발하기를 고르면 기능 폴더 구조를 지켜 개발한다. kw-dashboard 의 기능 이전 절차가 실행하는 중에는 이 질문을 하지 않는다.

한 기능을 마무리하지 않았는데 다른 기능을 고치려 하면 "두 기능을 동시에 고치면 수정이 섞일 수 있습니다. 지금 기능을 먼저 마무리하길 권장합니다. 두 기능을 함께 하려면 두 번째 기능용 사본 작업 폴더를 만들어 드립니다. 어떻게 할까요?" 라고 묻는다. 먼저 마무리하기를 고르면 지금 기능을 올린 뒤 `switch-feature` 로 옮긴다. 함께 하기를 고르면 사본 작업 폴더를 만든다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" add-copy --repo "<작업 폴더>" --feature <기능> --summary <영문 요약>
```

결과의 `path` 가 사본 작업 폴더다. 그 기능의 commit 과 업로드는 그 폴더를 `--repo` 로 넘겨 실행한다. 사본 작업 폴더는 업로드나 검토 요청이 끝나면 저장 스크립트가 지운다. commit 하지 않은 변경이나 비밀값·데이터 파일이 남아 지우지 못하면 `detail` 에 남은 파일이 적힌다. 그 파일의 처리를 개발자와 정한다.

### 공유 레포에서 commit

기능 단위가 끝나면 묻지 않고 commit 한다. 위 「commit」 절 1단계의 점검을 먼저 한다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" commit --repo "<작업 폴더>" --feature <기능> --message "<한 줄 설명>"
```

결과의 `other_features` 에 다른 기능이 있으면 그 기능의 변경은 commit 되지 않았다. `switch-feature` 로 그 기능으로 옮겨 따로 commit 한다. 검토 요청을 기다리는 branch 에 commit 하려 하면 `failed` 다. `switch-feature` 로 새 작업 branch 를 만든다.

### 올리기 흐름

개발자가 올리기에 동의하면 기능마다 아래를 차례로 한다. 승인 규칙은 위 「push 질문」 절과 같다.

1. 남은 변경을 기능별로 commit 한다.
2. 작업 이슈 제목을 `[<기능>] <이번에 한 일을 쉬운 말로 한 줄>` 로 정하고 경계 검사를 실행한다. 기능 이전이면 `--intake` 를 함께 넘긴다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" check-boundary --repo "<작업 폴더>" --feature <기능>
   ```

   `unsupported`·`invalid-feature`·`failed` 면 여기서 멈춘다.
3. 리뷰 시작 전에 개발자에게 "공유 코드에 반영하기 전에 다른 기능에 영향이 없는지 검토하고 있습니다. 잠시 기다려 주세요." 라고 알린다. 기능이 둘 이상이면 기능마다 "`<기능 이름>` 기능을 검토하고 있습니다." 라고 알린다. 그다음 `shared-repo-reviewer` 서브에이전트를 실행하고 결과를 기다린다. 기능이 둘 이상이면 차례로 실행한다. 넘기는 값은 레포 경로, 기능 이름, 2단계 결과 JSON, 개발자 요청 한 줄, 기능 이전 여부다.
4. 셀프 리뷰어 결과를 "공유 코드에 반영하기 전에 확인할 점" 으로 보여 준다. `fixed` 가 있으면 고친 내용 목록을 먼저 보여 준다.
   - `findings` 가 없으면 "검토를 마쳤습니다. 공유 코드에 반영합니다." 라고 알리고 5단계로 간다.
   - `findings` 가 있으면 "검토를 마쳤습니다. 반영하기 전에 확인할 점이 N개 있습니다." 라고 알린다(N 은 지적 수). 지적마다 무엇이 문제인지와 권장안을 적고, 설명이 필요한 항목은 하나씩 논의한다. 정한 수정을 commit 한다. `outside` 지적은 아래 「기능 폴더 밖 수정」 대로 처리한다.
   - 셀프 리뷰어가 끝나지 않거나 JSON 을 돌려주지 않으면 "검토를 끝내지 못해 공유 코드에 반영하지 않았습니다. 잠시 뒤 다시 올려 주세요." 라고 알리고 멈춘다.
5. 올린다. 위 「작업 이슈」 절에 따라 작업 이슈를 정해 번호를 넘긴다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" upload --repo "<작업 폴더>" --feature <기능> --task <작업 이슈 번호> --title "[<기능>] <한 줄>"
   ```

   저장 스크립트는 먼저 기능 폴더 경계를 다시 검사한다. 경계를 벗어났으면 아무것도 올리지 않고 `outside` 로 멈춘다. 통과하면 작업 branch 를 push 하고 GitHub 에서 main 에 merge 한다. 충돌로 멈추면 위 「push 절차」 5단계대로 풀고 `upload --continue` 로 이어 간다. 403·404·422 나 시간 초과로 반영하지 못하면 "작업을 GitHub 에 push(업로드)했지만 공유 코드에 반영하지 못했습니다. 잠시 뒤 다시 올려 주세요. 계속되면 AX팀에 문의해 주세요." 라고 알린다. 잠시 뒤 `upload --continue` 로 이어 간다.
6. `uploaded` 로 끝나면 업로드 뒤 점검을 한다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" review-upload --repo "<작업 폴더>" --feature <기능>
   ```

   위 「push 절차」 6단계와 같이 처리한다. 다만 `uploaded` 가 거짓이면 그 기능의 마지막 업로드가 공유 코드에 없다는 뜻이다. `leaked` 는 그 기능 폴더 안 파일만 포함한다. `ours` 는 제목이 `[<기능>] ` 으로 시작하는 내 이슈다. `copies` 에 사본 작업 폴더가 남아 있으면 `detail` 의 남은 파일을 보고 개발자와 처리를 정한다.

### 기능 폴더 밖 수정

`outside` 는 기능 폴더 밖의 파일을 고쳤다는 뜻이다. 개발자에게 "이번 수정 중 `<파일>` 은 내 기능 폴더 밖의 파일이라 공유 코드에 바로 반영할 수 없습니다." 라고 알리고 처리를 정한다.

- 공유 코드에 없던 새 파일이고 이 기능만 그 파일을 쓰면, 그 파일을 기능 폴더로 옮기는 안을 먼저 권한다. 동의하면 옮기고 import 를 고쳐 commit 한다.
- 되돌리기로 하면 아래를 실행한다. 지정한 파일을 공유 코드의 상태로 되돌리는 commit 이 생긴다. 공유 코드에 없던 파일은 지워진다.

  ```
  python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" revert-outside --repo "<작업 폴더>" --feature <기능> --paths <경로> <경로>
  ```

- 기능 이전에서 셀프 리뷰어가 줄 번호를 적어 낸 지적은 그 줄만 `origin/main` 의 내용으로 고쳐 `commit --feature <기능> --intake` 로 commit 한다. `revert-outside` 는 파일 전체를 되돌리므로 쓰지 않는다.
- 경계를 꼭 넘어야 하면 아래 「검토 요청」 절에 따라 한다.

### 검토 요청

경계를 꼭 넘어야 한다고 정했거나, 충돌을 개발자와 함께 풀어도 해결되지 않으면 검토 요청(PR)을 올린다. 먼저 PR 양식을 받아 각 절을 채운 본문을 레포 밖 임시 폴더에 파일로 쓴다. 양식의 안내 주석(`<!-- -->`)은 지운다.

```
gh api -H "Accept: application/vnd.github.raw" repos/KiwoomAX/.github/contents/.github/PULL_REQUEST_TEMPLATE.md
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" open-pr --repo "<작업 폴더>" --feature <기능> --title "[<기능>] <한 줄>" --body-file "<본문 파일>"
```

저장 스크립트는 진행 중인 merge 를 취소하고 작업 branch 를 push 한 뒤 PR 을 만든다. 결과가 `pr-opened` 면 개발자에게 "공유 코드에 바로 반영할 수 없어 검토 요청을 올렸습니다. AX팀에 문의해 주세요." 라고 알린다. main 에는 merge 하지 않는다.

`switch-feature`·`commit`·`upload` 결과의 `closed_prs` 에 branch 가 있으면 그 검토 요청이 반영되지 않고 닫혔다. 개발자에게 "검토 요청이 반영되지 않고 닫혔습니다. AX팀에 문의해 주세요." 라고 알린다. 같은 branch 는 한 번만 알린다.

### 기능 이전 업로드

kw-dashboard 의 기능 이전 절차는 `switch-feature --intake` 로 이전 branch 를 만들고, `commit`·`check-boundary`·`upload`·`review-upload` 에 모두 `--intake` 를 넘긴다. 이전 branch 에서는 `--intake` 없는 `commit`·`upload` 가 `failed` 로 멈춘다. 이때는 개발자에게 올릴지 묻지 않고 기능 이전 절차로 이어 간다. `upload --continue` 에는 넘기지 않는다. 진행 기록대로 기능 이전 규칙을 쓴다.

`upload --intake` 가 `failed` 이면 `reason` 에 따라 처리한다. 기능 이전 절차가 이 처분을 정한다.

- `intake-conflict`: 그사이 공유 코드가 바뀌어 충돌했다. 저장 스크립트가 GitHub 의 작업 branch 를 지웠다. 기능 이전 절차가 최신 main 을 다시 합친 뒤 올린다.
- `history-hits`: 기능 레포의 예전 commit 에 올리면 안 되는 파일이 있다. 아무것도 올리지 않았다. `detail` 의 파일을 기능 이전 절차에 넘긴다.
- `template-unavailable`: `KiwoomAX/dashboard-template` 을 읽지 못해 구조 파일을 확인하지 못했다. 잠시 뒤 다시 실행한다.
