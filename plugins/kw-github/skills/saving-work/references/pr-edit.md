# PR 추가 수정

이 파일은 `saving-work` 스킬의 참고 파일이다. 본문이 이 파일을 읽으라고 한 상황에서만 읽는다. 「결과 처리」·「검토 요청 반영」 같은 절 이름은 `saving-work` 본문의 절이다.

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
