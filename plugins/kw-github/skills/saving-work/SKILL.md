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

1. 이번에 바뀐 파일을 `${CLAUDE_PLUGIN_ROOT}/data_security_checklist.md` 의 점검표로 검토한다. 해당하는 것이 있으면 commit 하기 전에 고친다. 비밀값은 `.env` 로 옮기고 코드에서는 환경 변수로 읽게 하며, 업무 데이터와 개인정보는 코드에서 빼고, ipynb 출력 셀은 지운다. 고친 내용을 개발자에게 한 줄로 알린다. 단, 「배포할 수 없는 코드」 항목은 commit 하기 전에 고치지 않는다. 고치려면 코드를 다시 짜거나 AX팀 쿼리 승인을 기다려야 해서 작업 저장이 끊기기 때문이다. 이 항목은 commit 을 그대로 진행하고, 개발자에게 "AX팀이 배포할 수 없는 코드가 있습니다: `<파일:줄>`. 배포를 요청하기 전에 기능 코드 규칙의 방식으로 바꿔야 합니다." 라고 알린다.
2. 현재 작업 branch가 `feat/session-` 으로 시작하면 먼저 `git branch -m <새 이름>` 으로 이름을 작업 내용에 맞게 바꾼다. 세션 시작 훅이 이름을 정할 수 없어 붙인 이름이다.
3. 이번에 한 일을 한국어 한 줄로 적고 아래 명령을 실행한다. "출금요청서를 엑셀로 바꾸는 화면 추가" 처럼 쓴다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" commit --repo "<작업 폴더>" --message "<한 줄 설명>" --branch <종류>/<영문 요약>
   ```

   `--branch` 는 새 작업 branch가 필요할 때 쓰는 이름이다. 종류는 `feat/`(기능)·`fix/`(버그)·`refactor/`(정리)·`docs/`(문서) 중 하나이고, 영문 요약은 `fund-list-screen` 처럼 소문자와 하이픈으로 쓴다. 이미 이어 쓸 작업 branch가 있으면 스크립트가 그 branch를 쓰고 `--branch` 는 무시한다. 첫 commit 은 `main` 에 들어간다.

4. 결과를 「결과 처리」 절에 따라 처리한다. 결과의 `unpushed` 가 참이면 이어서 「push 질문」 절에 따라 묻는다.

## 결과 처리

결과 JSON 의 `message` 를 개발자에게 그대로 전한다. `detail` 은 전하지 않는다. `detail` 은 Claude 가 읽고 처리할 설명이다.

`status` 가 `needs-author` 면 「commit 명의」 절에 따라 처리한다.

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
- **규칙 파일 오류다.** 규칙 파일을 직접 고치지 않는다. `detail` 이 AX팀 문의를 안내하라고 하면 개발자에게 "kw-github 의 저장 규칙 파일에 문제가 있어 저장이 동작하지 않습니다. AX팀에 문의해 주세요." 라고 알리고 끝낸다. 이 kw-github 버전에서 이미 다시 설치해 보았다는 뜻이다. 그 밖에는 `claude plugin update kw-github@kiwoom-ax` 를 실행한다. 출력이 새 버전으로 업데이트했다고 하면 개발자에게 "저장 규칙 파일을 읽지 못해 kw-github 를 업데이트했습니다. Claude Code 를 재시작한 뒤 같은 요청을 해 주세요." 라고 알린다. 출력이 이미 최신 버전이라고 하면 설치한 파일이 빠졌거나 깨졌을 수 있다. `claude plugin uninstall kw-github@kiwoom-ax` 와 `claude plugin install kw-github@kiwoom-ax` 를 차례로 실행하고, 개발자에게 "저장 규칙 파일을 읽지 못해 kw-github 를 다시 설치했습니다. Claude Code 를 재시작한 뒤 같은 요청을 해 주세요." 라고 알린다. install 이 실패하면 kw-github 가 빠진 상태이므로 개발자에게 "kw-github 를 다시 설치하지 못했습니다. 사내 설치기 kw_install 을 다시 실행해 주세요." 라고 알린다. update 명령이 실패하면 AX팀 문의 문장을 알린다. 재설치는 버전마다 한 번만 안내되므로, 재시작한 뒤 같은 오류가 나면 `detail` 이 AX팀 문의를 안내한다.
- **git 이나 gh 를 찾지 못했거나 GitHub 로그인이 필요하다.** 개발자에게 사내 설치기 `kw_install` 을 다시 실행하거나, 터미널에서 `gh auth login --web --git-protocol https --skip-ssh-key --clipboard` 를 한 번 실행하라고 안내한다.
- **그 밖의 오류다.** `detail` 에 포함된 명령 출력을 읽고 원인을 고친 뒤 다시 실행한다. 두 번 고쳐도 실패하면 멈추고 `message` 만 전한다.

## commit 명의

결과의 `status` 가 `needs-author` 면 git 설정에 commit 에 남길 이름과 메일이 없어 commit 하지 않은 것이다. `message` 를 그대로 전하고, 선택 창(AskUserQuestion)을 열지 않고 글로 이름과 메일을 묻는다. 개발자가 답한 값으로 아래 두 명령을 실행한 뒤 멈춘 명령을 다시 실행한다.

```
git config --global user.name "<이름>"
git config --global user.email "<메일>"
```

대화 맥락이나 GitHub 계정에서 이름과 메일을 추정해 채우지 않는다. 개발자가 답한 값만 쓴다.

## push 질문

commit 결과나 세션 시작 알림이 GitHub 에 올리지 않은 commit 이 있다고 하면 개발자에게 묻는다. 글로 묻지 않고 AskUserQuestion 선택 창 하나에 질문 두 개를 넣어 묻는다. 개발자가 버튼으로 바로 답하게 하기 위해서다.

첫째 질문의 머리(header)는 "GitHub 업로드" 이고, 질문 문장은 아래를 그대로 쓴다. 선택지는 "올리기" 와 "나중에" 다.

> 지금까지 작업을 GitHub에 올릴까요? 올리면 회사 GitHub(KiwoomAX)에 저장됩니다.

결과의 `first_push` 가 참이고 `history_reset` 이 `hit` 이면 "예전 기록에 올리면 안 되는 파일이 있어 지금 파일만 올립니다." 를, `timeout` 이면 "예전 기록을 끝까지 확인하지 못해 지금 파일만 올립니다." 를 질문 문장 뒤에 덧붙인다. 올릴 작업에 「배포할 수 없는 코드」가 남아 있으면 "AX팀이 배포할 수 없는 코드가 남아 있습니다. 올릴 수는 있지만 배포를 요청하기 전에 바꿔야 합니다." 를 덧붙인다. 이 항목 때문에 업로드를 멈추지 않는다.

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

   `team_shared` 가 거짓이면 저장 스크립트가 이미 한 번 다시 시도했고, 다음 업로드 준비 때도 다시 시도한다. 개발자에게 "`<repo>` 를 `<team>` 팀이 볼 수 있게 설정하지 못했습니다. 이유: `<이유>`. 다음에 올릴 때 다시 시도합니다. 계속되면 이 문장을 AX팀에 그대로 전해 주세요." 라고 알린다. `<이유>` 는 `team_reason` 에 따라 정한다. `no-team` 이면 "GitHub 에서 그 팀을 찾지 못함(팀 이름이 틀렸거나 이 계정이 그 팀을 볼 수 없음)", `no-permission` 이면 "이 GitHub 계정에 팀 공유를 설정할 권한이 없음", `timeout` 이면 "GitHub 가 제한 시간 안에 응답하지 않음", `failed` 면 "GitHub 오류: `<team_error>`" 다. 같은 이름의 레포가 이미 있어 `failed` 면 개발자에게 "같은 이름의 GitHub 코드 저장소가 이미 있어 이 이름은 쓸 수 없습니다." 라고 알리고, 다른 이름을 정해 표식 파일의 `name` 을 고친 뒤 다시 실행한다. 결과의 `feature_issue` 가 기능 이슈 번호다.

   `status` 가 `main-branch` 면 아래 「기본 branch 맞추기」 절에 따라 처리한 뒤 `prepare-upload` 를 다시 실행한다.

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

   공유 대시보드 레포의 충돌은 이 단계를 쓰지 않고 「공유 대시보드 레포」의 「최신 main 합치기」 절을 따른다.

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

## 기본 branch 맞추기

회사 레포의 기본 branch 는 `main` 이다(사용자 결정, 2026-10-28). 저장 스크립트가 개발자에게 묻지 않고 맞춘다. 기능 레포에서는 `commit` 이 이 PC 의 `master` 를 `main` 으로 바꾸고, `prepare-upload` 가 GitHub 의 기본 branch 까지 바꾼다. 공유 대시보드 레포에서는 세션 시작 훅이 맞춘다.

Claude 는 아래 상황에서만 할 일이 있다. 이 절의 결과는 `prepare-upload` 결과의 `main_branch` 칸이나 아래 명령의 결과다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" normalize-main --repo "<작업 폴더>"
```

- `needs-decision`: 예전 기본 branch(`old_branch`)에 `main` 에 없는 commit 이 있다. AskUserQuestion 으로 묻는다. 질문 문장은 "예전 기본 branch `<old_branch>` 에 main 에 없는 작업이 있습니다: `<commits 를 쉼표로>`. 이 작업을 main 에 반영할까요?" 이고, 선택지는 "반영" 과 "버리기" 다. 반영이면 `--merge-old <old_branch>`, 버리기면 `--discard-old <old_branch>` 를 붙여 위 명령을 실행한다. 버린 작업은 되살릴 수 없다고 선택지 설명에 적는다.
- `conflict`: 반영하다 충돌했다. 아무것도 지우지 않았다. 개발자에게 "예전 기본 branch 의 작업이 main 과 충돌해 자동으로 반영하지 못했습니다." 라고 알리고, 버릴지 그대로 두고 AX팀에 문의할지 묻는다. 버리기면 `--discard-old <old_branch>` 로 실행한다.
- `failed` 이고 `reason` 이 `no-permission`: "`<레포>` 의 기본 branch 가 `<old_branch>` 로 되어 있습니다. 이 GitHub 계정(`<account>`)에는 이 설정을 바꿀 관리자 권한이 없습니다. AX팀에 이 코드 저장소의 기본 branch 를 main 으로 바꿔 달라고 요청해 주세요." 라고 알리고 올리지 않는다. `prepare-upload` 결과면 `message` 가 이 문장이다. 그 밖의 `failed` 는 「결과 처리」 절의 「그 밖의 오류」대로 한다.

## AX팀 변경 반영

기능 레포에서 세션 시작 훅은 GitHub main 을 받아온다. 올리지 않은 commit 이 없으면 훅이 묻지 않고 지금 branch 를 GitHub main 으로 옮긴다. 올리지 않은 commit 이 있으면 훅은 개발자에게 반영할지 물으라고 Claude 에게 알린다.

개발자가 동의하면 Claude 는 아래 명령을 실행한다. 공유 대시보드 레포에서는 아래 「공유 대시보드 레포」의 「최신 main 합치기」 절에 따라 쓴다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" sync-main --repo "<작업 폴더>"
```

결과의 `status` 에 따라 아래처럼 한다. `message` 는 개발자에게 그대로 전한다.

- `updated`·`nothing`: `message` 만 전한다.
- `conflict`: AX팀이 고친 코드와 지금 작업이 같은 줄을 고쳤다. 충돌한 파일은 `detail` 에 있다. 양쪽 동작이 같고 줄바꿈·공백·표기만 다르면 묻지 말고 풀어라. 동작이 다르면 개발자에게 'AX팀이 고친 코드' 와 '지금 PC 에 저장된 코드' 를 A 와 B 로 적어 묻는다. 풀고 `git add` 한 뒤 같은 명령에 `--continue` 를 붙여 실행한다. 묻지 않고 푼 파일 이름은 결과 보고에 적는다.
- `--continue` 결과가 다시 `conflict` 이면 `detail` 의 파일을 마저 푼다. `failed` 이고 `detail` 에 검사에서 빠질 파일이 있으면 그 파일에서 비밀값과 데이터를 빼고 다시 `--continue` 한다.
- 풀지 못하거나 개발자가 고르지 못하면 같은 명령에 `--abort` 를 붙여 실행하고 `message` 를 전한다. `message` 는 AX팀 문의를 안내한다.
- 그 밖의 `failed`: 「결과 처리」 절의 「그 밖의 오류」대로 한다.

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

## 검토 요청

검토 요청(PR)은 개발자가 원할 때와 아래 「공용 코드로 빼기」에서 올린다. 공유 레포와 기능 레포에 함께 쓴다.

공유 레포에서는 아래 「올리기 흐름」 3~6단계를 마친 뒤 연다.

먼저 PR 양식을 받아 각 절을 채운 본문을 레포 밖 임시 폴더에 파일로 쓴다. 양식의 안내 주석(`<!-- -->`)은 지운다.

```
gh api -H "Accept: application/vnd.github.raw" repos/KiwoomAX/.github/contents/.github/PULL_REQUEST_TEMPLATE.md
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" open-pr --repo "<작업 폴더>" --feature <기능> --title "[<기능>] <한 줄>" --body-file "<본문 파일>"
```

기능 레포에서는 `--feature` 없이 지금 작업 branch 로 연다. 첫 업로드 전에는 쓰지 않는다. `other-owner` 면 `detail` 대로 묻고, 동의하면 `--allow-other-owner` 를 붙여 다시 실행한다.

저장 스크립트는 공유 레포의 진행 중인 merge 를 취소하고, 비밀값·데이터 파일을 검사하고, 작업 branch 를 push 한 뒤 PR 을 만든다. 결과가 `pr-opened` 면 개발자에게 "검토 요청을 올렸습니다. Claude 가 검토한 뒤 반영합니다." 라고 알린다. `open-pr` 은 main 에 merge 하지 않는다. 기능 레포에서는 main 으로 옮기고 PC 의 작업 branch 를 지운다. commit 은 GitHub 에 남아 있다.

이어서 결과의 `url` 끝 숫자를 번호로 아래 「검토 요청 반영」 절에 따라 반영한다. 개발자가 다른 사람의 확인을 기다리겠다고 하면 반영하지 않고, 개발자가 반영을 요청할 때 반영한다.

`switch-feature`·`commit`·`upload` 결과의 `closed_prs` 에 branch 가 있으면 그 검토 요청이 반영되지 않고 닫혔다. 개발자에게 "검토 요청이 반영되지 않고 닫혔습니다. AX팀에 문의해 주세요." 라고 알린다. 같은 branch 는 한 번만 알린다.

### 검토 요청 반영

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" pr-merge --repo "<작업 폴더>" --number <번호> --task <작업 이슈 번호>
```

`--task` 는 「작업 이슈」 절에 따라 정한 작업 이슈 번호이고, 닫을 이슈가 더 있으면 번호마다 `--close <번호>` 를 넘긴다. 저장 스크립트는 검토 요청이 열려 있는지, 작성자가 지금 GitHub 계정이거나 지금 계정이 AX팀(`ax` 팀) 구성원인지, PC 에 올리지 않은 commit 이 없는지, 최신 GitHub main 을 포함하는지, 공유 레포이면 import 가 깨지지 않았는지를 차례로 확인한 뒤 GitHub 에서 merge 한다. `gh pr merge` 는 저장 가드가 거부하므로 쓰지 않는다. 결과의 `status` 에 따라 아래처럼 한다.

- `merged`: `message` 를 전한다. 공유 레포이면 아래 「공용 파일 안내」대로 알린다.
- `not-allowed`: 다른 사람이 연 검토 요청이다. 고친 것이 있으면 `pr-push` 로 올리고 `message` 를 전한다. `message` 는 "다른 분이 연 검토 요청은 작성자나 AX팀이 반영합니다. 수정한 내용은 검토 요청에 올렸으니 작성자에게 반영을 요청해 주세요." 다.
- `head-moved`: PC 에 검토 요청에 올리지 않은 commit 이 있다. `pr-push` 로 올린 뒤 `pr-merge` 를 다시 실행한다.
- `main-moved`: 검토 요청이 최신 GitHub main 을 포함하지 않는다. 아래 「PR 추가 수정」대로 `pr-start` 로 옮겨 「올리기 흐름」 3~6단계를 한 뒤 `pr-push` 와 `pr-merge` 를 실행한다. 다시 한 뒤에도 `main-moved` 면 아래 「멈춤과 안내」대로 한다.
- `broken-import`: 다른 코드가 쓰는 파일이나 이름이 없어졌다. `pr-start` 로 옮겨 고친 뒤 `pr-push` 와 `pr-merge` 를 실행한다. 고치지 못하면 「멈춤과 안내」대로 한다.
- `secret-found`: 검토 요청에 비밀값이나 데이터 파일이 있다. `message` 를 전하고 끝낸다. 파일 이름은 `detail` 에 있다.
- `outside`: 검토 요청이 배포 설정 파일을 고쳤다. `message` 를 전하고 아래 「기능 폴더 밖 수정」의 배포 설정 절차를 따른다.
- `not-open` 과 그 밖의 `failed`: `message` 를 전하고 끝낸다.

## PR 추가 수정

개발자가 검토 요청의 번호나 주소를 주며 수정을 요청하면 이 절을 따른다. 공유 레포와 기능 레포에 같이 쓴다. 번호가 없으면 `gh pr list` 로 고르게 한다. 작업 전 변경은 평소 절차로 commit 한다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" pr-start --repo "<작업 폴더>" --number <번호>
```

`started` 면 PC 전용 branch `pr-review/<번호>` 로 옮겨졌다. 리뷰 코멘트는 `gh pr view <번호> --comments` 와 `gh api repos/<레포>/pulls/<번호>/comments` 로 읽는다. 고친 뒤 `--feature` 없이 `commit` 한다. 이 branch 에서는 기능 폴더 경계를 보지 않는다. 결과에 `pr_number` 가 있으면 "검토 요청 #N 에 올릴까요?" 라고 묻고, 동의하면 아래를 실행한다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" pr-push --repo "<작업 폴더>"
```

개발자가 이미 열린 검토 요청의 반영을 요청하면 `pr-start` 로 리뷰 branch 에 옮기고, 공유 레포이면 아래 「올리기 흐름」 3~6단계를 한다. 리뷰 branch 에서는 `switch-feature`·`check-boundary` 를 쓰지 않으므로 3단계는 `sync-main` 만, 4단계는 `check-imports` 만 실행한다. 고친 파일은 `--feature`·`--paths` 없이 `commit` 하고, 필요 없는 수정은 `revert-paths` 로 되돌린다. 셀프 리뷰어에 넘기는 기능 이름은 검토 요청이 고친 기능 폴더 이름이고, 리뷰 branch 라는 것도 함께 넘긴다. 고친 것이 있으면 `pr-push` 를 먼저 실행하고 그다음 위 「검토 요청 반영」대로 `pr-merge` 를 실행한다. 기능 레포에서는 3단계만 하고 셀프 리뷰는 생략한다.

`pr-start` 가 실패하면 리뷰 branch 로 옮겨지지 않았다. `message` 를 전하고 끝낸다. `remote-moved` 이고 `unpushed` 가 0 보다 크면 아래 질문을 한다.

`pr-push` 가 `other-owner` 면 `detail` 대로 묻고, 동의하면 `--allow-other-owner` 를 붙여 다시 실행한다. 이 동의는 그 push 한 번에만 유효하다.

`pr-push` 가 `remote-moved` 이거나 `message` 가 검토 요청을 확인하지 못했거나 닫혔다는 문장이면 그 `message` 를 전하고 `pr-leave` 로 나온다. `pr-leave` 는 무관한 작업을 시작할 때도 쓴다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" pr-leave --repo "<작업 폴더>"
```

`pr-leave` 결과의 `unpushed` 가 0 보다 크면 올리지 않은 commit 이 남았다. 선택 창으로 "올리지 못한 수정이 PC 에 남아 있습니다. 지울까요?" 라고 묻는다. 지우기를 고르면 `pr-leave --repo "<작업 폴더>" --discard --number <번호>` 를 실행한다. 남기기를 고르면 AX팀에 확인을 요청하라고 안내한다.

`excluded` 에 추적 파일이 있으면 위 「결과 처리」 대로 알린다. 그 수정은 PR 에 올라가지 않고 `pr-push` 뒤 작업 폴더에 남는다. 되돌리지 못하면 `detail` 대로 처리한다.

`outside` 로 멈춘 upload 가 남아 `pr-start` 가 `failed` 면 그 upload 를 끝내거나 `open-pr` 로 올린 뒤 다시 실행한다.

push 결과에 "이전 기록을 지우는 push(업로드)는 차단됩니다." 가 나오면 다시 시도하지 말고 그 문장을 전한다.

## 남은 임시 보관

세션 시작 안내나 `pr-push`·`pr-leave` 의 `detail` 이 남은 stash 를 알리면 이 절을 따른다. 끊긴 올리기가 보관해 둔 개발자의 수정이다.

리뷰 branch 에서는 정리하지 않는다. PR 작업을 끝내고 `pr-push` 나 `pr-leave` 로 나온 뒤에 정리한다. 이 정리만을 위해 `pr-leave` 를 실행하지 않는다.

안내가 올리기를 이어 갈지 물으라고 하면 먼저 묻는다. 이어 가면 `upload --continue` 가 stash 를 되돌리므로 이 절을 끝낸다.

안내에 적힌 stash 만 다룬다. 다른 작업 폴더의 stash 가 함께 보일 수 있기 때문이다. PowerShell 은 `@{}` 를 해석하므로 `'stash@{0}'` 처럼 작은따옴표로 감싼다. `git stash show --include-untracked -p '<stash>'` 로 내용을 읽고, 어떤 파일이 어떻게 바뀌었는지 쉬운 말로 알린 뒤 선택 창으로 "앞선 올리기에서 임시 보관한 수정이 남아 있습니다. 어떻게 할까요?" 라고 묻는다. 선택지는 작업 폴더로 되돌리기, 버리기다.

- 되돌리기를 고르면 `git stash pop '<stash>'` 를 실행한다. 성공하면 stash 는 없어진다. 실패하면 stash 는 남는다. 원인을 처리하고, 위에서 읽은 내용이 작업 폴더에 모두 있는지 확인한 뒤에만 `git stash drop '<stash>'` 한다.
- 버리기를 고르면 `git stash drop '<stash>'` 를 실행한다. 되살릴 수 없으므로 개발자가 고르지 않으면 실행하지 않는다.

## 공유 대시보드 레포

origin 이 `KiwoomAX/<이름>` 이고 이름이 `dashboard` 로 끝나는 레포는 여러 개발자가 기능별 폴더로 나누어 함께 쓰는 공유 대시보드 레포다(`dashboard-template` 은 아니다). 표식 파일이 없어도 이 절을 따른다. 위의 commit·push 절차 대신 아래를 쓴다. 공유 레포에서는 개발자에게 main 을 "공유 코드" 라고 하고, merge 는 "반영", PR 은 "검토 요청" 이라고 한다. 이슈는 말하지 않는다.

기능 폴더는 `src/frontend/src/features/<기능>/`, `src/backend/features/<기능>/`, `docs/<기능>.pdf`·`docs/<기능>.docx` 다. 한 기능의 작업 branch 에는 그 기능 폴더만 고친다. 기능 이름은 개발자가 고치는 기능 폴더 이름이다. 모르면 묻는다.

### 결과의 `status`

- `unsupported` 면 개발자에게 "이 대시보드는 아직 기능별 폴더 구조로 옮겨지지 않아 공유 코드에 반영할 수 없습니다. AX팀에 기능별 폴더 구조로 전환을 요청해 주세요." 라고 알리고 멈춘다.
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

결과의 `other_features` 에 다른 기능이 있으면 그 기능의 변경은 commit 되지 않았다. `switch-feature` 로 그 기능으로 옮겨 따로 commit 한다. 기능별로 따로 올리기를 권한다. 개발자가 그 수정을 함께 올리기로 정했으면 같은 명령에 `--include-others` 를 붙여 다시 commit 한다. 검토 요청을 기다리는 branch 에 commit 하려 하면 `failed` 다. `switch-feature` 로 새 작업 branch 를 만든다.

Claude 가 리뷰 결과로 고친 파일은 고친 파일만 `--paths` 로 지정해 commit 한다. 개발자가 다른 기능 폴더에서 아직 끝내지 않은 작업을 commit 에 넣지 않기 위해서다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" commit --repo "<작업 폴더>" --feature <기능> --include-others --message "<한 줄 설명>" --paths <경로> <경로>
```

### 올리기 흐름

개발자가 올리기에 동의하면 기능마다 아래를 차례로 한다. 승인 규칙은 위 「push 질문」 절과 같다. Claude 가 최신 공유 코드를 합친 상태에서 기존 동작이 깨지지 않는지 확인하고 직접 반영한다. 기능 이전은 아래 「기능 이전 업로드」 절과 kw-dashboard 의 기능 이전 절차를 따른다.

1. 남은 변경을 기능별로 commit 한다. 이 단계 뒤에는 commit 하지 않은 변경이 없다.
2. 작업 이슈 제목을 `[<기능>] <이번에 한 일을 쉬운 말로 한 줄>` 로 정한다.
3. 그 기능의 작업 branch 로 옮긴 뒤 최신 GitHub main 을 합친다. 아래 「최신 main 합치기」 절에 따라 한다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" switch-feature --repo "<작업 폴더>" --feature <기능>
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" sync-main --repo "<작업 폴더>"
   ```

4. 경계와 import 를 확인한다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" check-boundary --repo "<작업 폴더>" --feature <기능>
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" check-imports --repo "<작업 폴더>"
   ```

   `check-boundary` 가 `unsupported`·`invalid-feature`·`failed` 면 여기서 멈춘다. `outside` 면 배포 설정 파일을 고쳤다는 뜻이므로 아래 「기능 폴더 밖 수정」의 배포 설정 절차를 따른다. `outside_files` 는 기능 폴더 밖에서 바뀐 파일 전체이고 8단계 안내에 쓴다. `check-imports` 가 `broken` 이면 `broken_imports` 의 파일과 이름이 없어졌다는 뜻이다. Claude 가 먼저 고쳐 `--paths` 로 commit 하고 이 단계를 다시 한다.
5. 셀프 리뷰를 한다. 개발자에게 "공유 코드에 반영하기 전에 다른 기능에 영향이 없는지 검토하고 있습니다. 잠시 기다려 주세요." 라고 알린다. 기능이 둘 이상이면 기능마다 "`<기능 이름>` 기능을 검토하고 있습니다." 라고 알린다. 그다음 `shared-repo-reviewer` 서브에이전트를 실행하고 결과를 기다린다. 기능이 둘 이상이면 차례로 실행한다. 넘기는 값은 레포 경로, 기능 이름, 4단계의 `check-boundary`·`check-imports` 결과 JSON, 개발자 요청 한 줄, 기능 이전 여부다.
   - 셀프 리뷰어가 끝나지 않거나 JSON 을 돌려주지 않으면 "검토를 끝내지 못해 공유 코드에 반영하지 않았습니다. 잠시 뒤 다시 올려 주세요." 라고 알리고 멈춘다.
   - `findings` 가 없으면 "검토를 마쳤습니다. 공유 코드에 반영합니다." 라고 알리고 7단계로 간다.
   - `findings` 가 있으면 "검토를 마쳤습니다. 반영하기 전에 확인할 점이 N개 있습니다." 라고 알린다(N 은 지적 수). 지적마다 무엇이 문제인지와 처리를 한 줄로 적고 6단계로 간다. 개발자에게 처리 방법을 묻지 않는다.
6. 리뷰 결과를 처리한다. 아래 「리뷰 결과 처리」 절에 따라 한다. 고친 것이 있으면 4단계부터 한 번 다시 한다. 다시 한 뒤에도 고칠 지적이 남으면 「멈춤과 안내」대로 한다.
7. 올린다. 위 「작업 이슈」 절에 따라 작업 이슈를 정해 번호를 넘긴다. 공유 레포에서는 `prepare-upload` 를 실행하지 않으므로 그 절의 값을 이렇게 바꿔 쓴다. `<레포>` 는 `git remote get-url origin` 의 `KiwoomAX/<이름>` 이고, 제목 앞머리는 `[<기능>] ` 이고, commit 목록은 4단계 `check-boundary` 결과의 `commits` 다. 본문에 `기능 이슈:` 줄은 쓰지 않는다. 공유 레포에는 기능 이슈가 없다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" upload --repo "<작업 폴더>" --feature <기능> --task <작업 이슈 번호> --title "[<기능>] <한 줄>"
   ```

   저장 스크립트는 올리기 전에 작업 branch 가 최신 GitHub main 을 포함하는지와 import 가 깨지지 않았는지 다시 확인하고, 배포 설정 파일을 고쳤는지 검사한다.
   - `main-moved` 면 `message` 를 전하고 3단계부터 한 번 다시 한다. 올리는 사이 다른 개발자가 공유 코드를 바꿨거나 GitHub 가 충돌(409)로 거부했다는 뜻이다. 저장 스크립트는 이 PC 에서 합치지 않았고 GitHub 의 작업 branch 는 남겨 두었다. 다시 한 뒤에도 `main-moved` 면 「멈춤과 안내」대로 한다.
   - `broken-import` 면 4단계의 `check-imports` 가 `broken` 일 때와 같이 고친 뒤 4단계부터 다시 한다.
   - `outside` 면 아래 「기능 폴더 밖 수정」의 배포 설정 절차를 따른다.
   - 403·404·422 나 시간 초과로 반영하지 못하면 "작업을 GitHub 에 push(업로드)했지만 공유 코드에 반영하지 못했습니다. 잠시 뒤 다시 올려 주세요. 계속되면 AX팀에 문의해 주세요." 라고 알린다. 잠시 뒤 `upload --continue` 로 이어 간다.
8. `uploaded` 로 끝나면 아래 「공용 파일 안내」대로 알리고 업로드 뒤 점검을 한다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" review-upload --repo "<작업 폴더>" --feature <기능>
   ```

   위 「push 절차」 6단계와 같이 처리한다. 다만 `uploaded` 가 거짓이면 그 기능의 마지막 업로드가 공유 코드에 없다는 뜻이다. `leaked` 는 그 기능 폴더 안 파일만 포함한다. `ours` 는 제목이 `[<기능>] ` 으로 시작하는 내 이슈다. `copies` 에 사본 작업 폴더가 남아 있으면 `detail` 의 남은 파일을 보고 개발자와 처리를 정한다.

### 최신 main 합치기

공유 레포의 작업 branch 와 리뷰 branch 에서 `sync-main` 을 쓴다. 기능 이전 branch 와 main 에서는 `failed` 다. 결과의 `status` 는 위 「AX팀 변경 반영」 절과 같다. `nothing` 은 합칠 변경이 없었다는 뜻이고 `updated` 는 합쳤다는 뜻이다.

`conflict` 면 Claude 는 양쪽 변경의 뜻을 모두 살리는 방향으로 푼다. 공유 레포에서는 개발자에게 A/B 로 묻지 않는다. 풀고 `git add` 한 뒤 `sync-main --repo "<작업 폴더>" --continue` 를 실행한다. 양쪽이 같은 동작을 서로 다르게 바꿔서 양쪽 뜻을 함께 살릴 수 없으면 `sync-main --repo "<작업 폴더>" --abort` 로 합치기를 취소하고 「멈춤과 안내」의 해결하지 못한 큰 문제로 간다.

### 리뷰 결과 처리

- `unneeded`: 필요 없는 수정은 개발자에게 묻지 않고 commit 으로 되돌리고, 8단계에서 알린다. 파일의 수정이 모두 필요 없으면 아래를 실행한다. 지정한 파일을 공유 코드의 상태로 되돌리는 commit 이 생기고, 공유 코드에 없던 파일은 지워진다. 이번 기능 폴더 안 파일도 되돌린다.

  ```
  python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" revert-paths --repo "<작업 폴더>" --feature <기능> --paths <경로> <경로>
  ```

  필요한 수정이 섞여 있으면 그 줄만 `origin/main` 의 내용으로 고쳐 「공유 레포에서 commit」의 `--paths` commit 으로 남긴다.
- `breaking`·`broken`·`structure`: 셀프 리뷰어가 고치지 못한 지적은 Claude 가 고칠 수 있으면 고친다. 이번 기능 폴더 밖과 다른 기능 폴더도 고칠 수 있다. 다른 기능 폴더는 그 기능의 동작을 바꾸지 않는 수정(바뀐 이름·경로 따라가기)만 한다. 고친 파일은 `--paths` 로 commit 한다.
- `security`: 셀프 리뷰어가 고치지 못했으면 Claude 가 고친다. 고치지 못하면 「멈춤과 안내」대로 한다.

### 멈춤과 안내

아래 조건이면 올리지 않고 멈춘다. 멈춘 작업은 작업 branch 에 남는다. 개발자가 다른 개발자와 정한 뒤 다시 올리면 1단계부터 한다.

- 해결하지 못한 큰 문제(충돌을 풀지 못했거나 `breaking`·`broken` 을 고치지 못함)와 import 확인 실패(Claude 가 고친 뒤에도 `broken_imports` 가 남음): "이대로 반영하면 `<기능>` 의 `<동작>` 이 깨집니다. 깨지는 코드를 작성한 `<이름>` 님과 이야기해 보셔야 합니다." 라고 알린다. import 확인 실패면 `<동작>` 은 깨진 import 의 파일과 이름이다.
- 템플릿 구조 훼손(`structure` 를 되돌리거나 고치지 못함): "대시보드의 기본 구조(`<파일>`)를 바꾸는 수정이 있어 반영하지 않았습니다. 이 수정이 필요하면 AX팀에 문의해 주세요." 라고 알린다.
- 보안 점검표 위반(`security` 를 고치지 못했거나 저장 검사가 거부함): 위 「결과 처리」 절의 저장 검사 안내와 같다.
- 배포 설정 수정: 아래 「기능 폴더 밖 수정」의 배포 설정 절차를 따른다.
- 다시 한 뒤에도 남은 지적: 남은 지적의 조건에 맞는 위 안내를 한다.
- 다시 한 뒤에도 `main-moved`: "공유 코드가 계속 바뀌고 있어 반영하지 못했습니다. 잠시 뒤 다시 올려 주세요." 라고 알린다.

`<이름>` 은 깨지는 코드 줄을 `origin/main` 에서 마지막으로 고친 사람이다. 그 사람이 AX팀원이어도 그대로 쓴다. `git blame origin/main -L <줄>,<줄> -- <파일>` 로 그 줄의 commit 을 찾는다. 그 commit 이 merge commit 이면 충돌을 푼 줄이므로 `git log origin/main --no-merges -1 --format=%an -L <줄>,<줄>:<파일>` 의 작성자를 쓴다.

### 공용 파일 안내

올린 뒤 이번 기능 폴더 밖에서 바뀐 파일을 알린다. 파일 목록은 4단계 `check-boundary` 결과의 `outside_files` 다. 파일마다 "`<파일>` 은 다른 기능도 함께 쓰는 파일입니다. Claude 가 확인해 보니 기존 동작을 깨지 않아 함께 반영했습니다." 라고 알린다. 다른 기능의 코드를 고쳤으면 "`<기능>` 의 `<파일>` 도 함께 고쳤습니다. `<고친 내용>`" 을 추가한다. 6단계에서 되돌린 수정이 있으면 "필요 없는 수정이라 되돌렸습니다: `<파일>` `<내용>`" 을 추가한다.

### 공용 코드로 빼기

여러 기능에 같은 동작이 반복되는 코드를 발견하면 Claude 가 판단해 공용 코드로 빼자고 제안한다. 개발자가 동의하면 레포에 이미 있는 공용 폴더(`src/frontend/src/components/`, `src/backend/lib/` 등)에 넣는다. 없으면 `src/frontend/src/shared/` 와 `src/backend/shared/` 를 만들어 넣는다. `shell/` 은 대시보드 틀 코드이므로 넣지 않는다. 다른 기능의 코드까지 바뀌므로 commit 에 `--include-others` 를 쓴다. 그다음 「올리기 흐름」 3~6단계를 마치고 위 「검토 요청」 절에 따라 `open-pr` 로 연 뒤 이어서 `pr-merge` 를 실행한다.

### 기능 폴더 밖 수정

기능 폴더 밖 파일을 고쳐도 배포 설정 파일이 아니면 멈추지 않는다. Claude 가 「올리기 흐름」 4~6단계로 확인하고 함께 올린 뒤 「공용 파일 안내」대로 알린다.

- 배포 설정 파일을 고쳤으면 `check-boundary` 와 `upload` 가 `outside` 로 멈추고 `deploy` 에 그 파일을 적는다. `upload` 결과에는 `command` 가 있다. `command` 를 코드 블록으로 보여 주고 "이 명령을 복사해 터미널에서 직접 실행하고, 끝나면 결과를 알려 주세요." 라고 안내한다. Claude 는 이 명령을 실행하지 않는다. 동의는 실행마다 받으므로 `upload --continue` 도 `outside` 면 같은 절차를 다시 한다.
- 개발자가 끝났다고 알리면 `review-upload` 를 실행한다. 공유 코드에 들어갔으면 「올리기 흐름」 8단계를 따르고, 들어가지 않았으면 개발자가 전한 출력으로 처리한다.
- 기능 이전에서 공유 코드에 없던 새 파일이고 이 기능만 그 파일을 쓰면, 그 파일을 기능 폴더로 옮기는 안을 먼저 권한다. 동의하면 옮기고 import 를 고쳐 commit 한다.
- 기능 이전에서 셀프 리뷰어가 낸 `outside` 지적을 되돌리기로 하면 `revert-paths` 로 그 파일을 공유 코드의 상태로 되돌린다. 셀프 리뷰어가 줄 번호를 적어 낸 지적은 그 줄만 `origin/main` 의 내용으로 고쳐 `commit --feature <기능> --intake` 로 commit 한다. `revert-paths` 는 파일 전체를 되돌리므로 이때는 쓰지 않는다.

### 기능 이전 업로드

kw-dashboard 의 기능 이전 절차는 `switch-feature --intake` 로 이전 branch 를 만들고, `commit`·`check-boundary`·`upload`·`review-upload` 에 모두 `--intake` 를 넘긴다. 이전 branch 에서는 `--intake` 없는 `commit`·`upload` 가 `failed` 로 멈춘다. 이때는 「push 질문」을 하지 않고 기능 이전 절차로 이어 간다. 업로드 승인은 기능 이전 절차가 공유 코드에 반영하기 직전에 하는 질문으로 받는다. 승인 없이 `upload --intake` 를 실행하지 않는다. `upload --continue` 에는 넘기지 않는다. 진행 기록대로 기능 이전 규칙을 쓴다.

`upload --intake` 가 `failed` 이면 `reason` 을 기능 이전 절차에 넘긴다. 처분은 기능 이전 절차가 정한다. 각 값의 뜻은 다음과 같다.

- `intake-conflict`: 그사이 공유 코드가 바뀌어 GitHub 가 충돌로 거부했다. PC 에서 합치지 않았고, GitHub 의 작업 branch 는 남겨 두었다. 다시 올릴 때 그 branch 위에 이어서 push 한다.
- `history-hits`: 기능 레포의 예전 commit 이나 올릴 내용에 올리면 안 되는 파일이 있다. 아무것도 올리지 않았다. 파일은 `detail` 에 있다.
- `template-unavailable`: `KiwoomAX/dashboard-template` 을 읽지 못해 구조 파일을 확인하지 못했다.

기능 이전 절차가 기능 레포의 예전 commit 을 검사할 때는 아래 명령을 쓴다. `<branch>` 는 검사할 기능 레포 branch 다.

```
python "${CLAUDE_PLUGIN_ROOT}/scripts/scan_history.py" --repo "<폴더>" --ref <branch>
```
