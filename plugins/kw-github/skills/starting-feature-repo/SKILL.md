---
name: starting-feature-repo
description: 사내 개발자가 새 기능·앱·화면·스크립트를 만들기 시작할 때 작업 폴더를 회사 GitHub(KiwoomAX)에 올릴 기능 레포로 준비한다. 표식과 첫 commit 을 대신하므로 개발자는 GitHub 을 몰라도 된다. 브레인스토밍이나 Artifact 게시보다 먼저 쓴다. 코드는 Artifact 나 임시 폴더가 아니라 작업 폴더에 만든다. 질문만 하거나 이미 있는 코드를 읽기만 하는 세션에서는 쓰지 않는다.
---

# 기능 레포 준비

이 스킬은 개발을 시작하는 폴더를 기능 레포로 준비한다. GitHub 에는 아무것도 만들지 않는다. 원격 레포와 기능 이슈는 개발자가 처음 push 를 승인할 때 `saving-work` 가 만든다.

개발자는 git 과 GitHub 에 익숙하지 않다고 본다. 개발자에게 하는 말은 `${CLAUDE_PLUGIN_ROOT}/git_terms.md` 를 따른다. commit·push·main·branch 만 영어로 쓰고 그 행동의 결과를 같은 문장에 붙인다. 나머지 git 용어는 쉬운 말로 바꾸거나 말하지 않는다. 예: "commit 해 두었어요. 이 시점으로 코드를 되돌릴 수 있어요."

아래에서 `<폴더>` 는 지금 작업 폴더다. 스크립트는 모두 `${CLAUDE_PLUGIN_ROOT}/scripts/` 아래에 있고 UTF-8 JSON 한 개를 출력한다.

## 레포 이름 규칙

영문 소문자와 숫자와 하이픈만 쓴다. 기능이 다루는 대상이 이름에 드러나야 한다. `pdf-to-excel` 은 쓰지 않고 `fund-withdrawal-pdf-to-excel` 처럼 짓는다. Claude 가 이름을 제안하고 개발자에게 확인받는다.

## 순서

1. **저장 규칙과 폴더를 확인한다.** 먼저 저장 규칙을 읽을 수 있는지 본다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/repo_setup.py" check-rules
   ```

   `ok` 가 `false` 면 아무것도 만들지 않고 멈춘다. 개발자에게 "저장 규칙을 읽지 못해 준비를 멈췄습니다. AX팀에 알려 주세요." 라고 알린다. 이어서 폴더를 확인한다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/repo_setup.py" check-folder --path "<폴더>"
   ```

   `ok` 가 `false` 면 이 폴더를 레포로 만들지 않는다. 사용자 홈, 바탕화면, 문서, 다운로드, OneDrive, 드라이브 최상위이기 때문이다. 3단계로 기능 이름과 레포 이름을 먼저 정한 뒤 `<폴더>` 아래에 레포 이름으로 하위 폴더를 만든다. 개발자에게 "새 폴더 `<경로>` 를 만들었습니다. 그 폴더에서 Claude Code 를 다시 열어 주세요." 라고 알리고 멈춘다. 세션 시작 commit 은 세션을 연 폴더에서만 실행되기 때문이다.

2. **폴더 상태를 확인한다.**

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/repo_setup.py" inspect --path "<폴더>"
   ```

   `state` 에 따라 처리한다. `inspect` 는 표식 파일로 기능 레포를 판정하고, 원격이 있는지는 `has_remote` 로 따로 알린다.
   - `feature` 는 이미 기능 레포라는 뜻이다. 개발자에게 "이 폴더는 이미 작업 폴더로 준비되어 있습니다." 라고만 알리고 끝낸다.
   - `company-no-marker` 는 대시보드 레포처럼 회사의 다른 레포다. 멈추고 "이 폴더는 회사의 다른 프로젝트 폴더라 여기서는 새 기능을 준비하지 않습니다. 새 기능은 새 폴더에서 시작해 주세요." 라고 알린다.
   - `other-remote` 는 회사 밖 주소와 연결된 폴더다. 멈추고 "이 폴더는 회사 GitHub이 아닌 곳과 연결되어 있어 작업 폴더로 준비하지 않았습니다." 라고 알린다.
   - `not-git` 과 `local-only` 는 다음 단계로 간다. 다만 `top` 이 `<폴더>` 와 다르면 위쪽 폴더가 이미 레포라는 뜻이므로, 멈추고 개발자에게 어느 폴더에서 작업할지 묻는다.

3. **기능 이름과 레포 이름을 정한다.** "어떤 기능을 만드시나요? 한국어로 짧게 알려 주세요." 라고 한 번만 묻는다. 규칙에 맞는 레포 이름을 제안하고 확인받는다. 그다음 `gh repo view KiwoomAX/<이름> --json name` 을 실행한다. 성공하면 같은 이름의 레포가 이미 있으므로 "같은 이름으로 등록된 기능이 있습니다. 이어서 작업하던 기능인가요?" 라고 묻는다.
   - 그렇다고 하면 새로 준비하지 않는다. `<폴더>` 옆에 새 폴더를 정해 `gh repo clone KiwoomAX/<이름> "<새 폴더>"` 로 내려받고, 그 폴더에서 Claude Code 를 다시 열라고 안내하고 끝낸다.
   - 아니라고 하면 다른 이름을 제안한다.

   볼 권한이 없는 같은 이름의 레포는 여기서 찾지 못한다. 그런 레포가 있으면 첫 GitHub 업로드 때 `prepare-upload` 가 멈추고, `saving-work` 가 다른 이름을 정해 표식 파일의 `name` 을 고친다.

4. **팀 공유를 묻는다.** 개발자가 속한 팀(본부)을 확인한다.

   ```
   gh api user/teams --jq '.[] | select(.organization.login=="KiwoomAX") | "\(.slug) \(.name)"'
   ```

   팀이 있으면 "같은 본부(<팀 이름>) 팀원도 볼 수 있도록 추가할까요?" 라고 한 번 묻는다. 팀이 여럿이면 팀 이름을 모두 보여 주고 고르게 한다. 팀이 없으면 묻지 않는다. 권한은 첫 GitHub 업로드 때 `prepare-upload` 가 준다.

5. **이 폴더의 기록을 준비한다.**
   - `state` 가 `not-git` 이면 `git init -b main` 을 실행한다.
   - `state` 가 `local-only` 이고 `has_commits` 가 `true` 면 예전 기록을 검사한다.

     ```
     python "${CLAUDE_PLUGIN_ROOT}/scripts/scan_history.py" --repo "<폴더>"
     ```

     `status` 가 `clean` 이면 기록을 그대로 둔다. `hits` 나 `timeout` 이면 개발자에게 묻지 않고 아래를 실행한다. 예전 기록은 이 PC 의 `local-history` 에 남고 GitHub 에는 올라가지 않는다. `local-history` 는 지우지 않는다.

     ```
     python "${CLAUDE_PLUGIN_ROOT}/scripts/reset_history.py" --repo "<폴더>"
     ```

     `scan_history.py` 나 `reset_history.py` 의 `status` 가 `failed` 면 멈추고 개발자에게 "저장 규칙을 읽지 못해 준비를 멈췄습니다. AX팀에 알려 주세요." 라고 알린다.
   - 마지막으로 현재 브랜치 이름을 확인한다. `reset_history.py` 를 실행했으면 이미 `main` 이다. 아니면 2단계 결과의 `branch` 가 `main` 이 아닐 때 `git branch -m main` 으로 이름을 바꾼다.

6. **표식 파일과 `.gitignore` 를 만든다.** 최상위 폴더에 `.kiwoom-feature` 를 만들고 줄마다 `<키>=<값>` 을 적는다.

   ```
   name=<레포 이름>
   title=<한국어 기능 이름>
   team=<팀 slug>
   history-reset=<hit 또는 timeout>
   ```

   `name=` 과 `title=` 줄은 언제나 적는다. `team=` 줄은 4단계에서 공유하기로 했을 때만 적는다. `history-reset=` 줄은 5단계에서 `reset_history.py` 를 실행했을 때만 적는다. 검사가 `hits` 였으면 `hit`, `timeout` 이었으면 `timeout` 이다.

   `.gitignore` 가 없으면 아래 다섯 줄로 만든다. 마지막 줄은 Claude 가 만드는 설계 문서를 올리지 않기 위한 줄이다. 있으면 그대로 둔다. 저장 스크립트도 없을 때 같은 다섯 줄로 만들고, 있으면 마지막 줄이 빠졌을 때만 그 줄을 추가한다.

   ```
   .env
   .venv/
   node_modules/
   __pycache__/
   docs/superpowers/
   ```

7. **첫 commit 을 한다.** `main` 에 커밋이 아직 없으면 이 commit 은 `main` 에 들어간다.

   ```
   python "${CLAUDE_PLUGIN_ROOT}/scripts/save_work.py" commit --repo "<폴더>" --message "작업 폴더 준비"
   ```

   예전 기록 검사가 `clean` 이어서 커밋이 이미 있는 폴더면 위 명령에 `--branch feat/<영문 요약>` 을 붙인다. 이 commit 은 그 작업 브랜치에 들어간다.

8. **개발자에게 알린다.** 7단계의 `status` 가 `committed` 일 때만 "이 폴더를 `<기능 이름>` 작업 폴더로 준비했습니다. 작업이 끝나면 GitHub에 올릴지 여쭙겠습니다." 라고 알린다. 다른 결과면 준비를 마쳤다고 알리지 않고 `saving-work` 스킬의 「결과 처리」 절대로 처리한다.

9. **개발을 이어 간다.** 개발자가 처음에 요청한 기능을 만든다. 기능 단위가 끝나면 개발자에게 묻지 않고 commit 한다. 방법은 `saving-work` 스킬의 「commit」 절에 있다. "저장해줘" 같은 요청을 기다리지 않는다. commit 결과의 `unpushed` 가 참이면 같은 스킬의 「push 질문」 절대로 선택 창을 열어 묻는다.
