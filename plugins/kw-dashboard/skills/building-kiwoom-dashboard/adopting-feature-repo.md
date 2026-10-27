# 기능 레포를 대시보드로 옮기기

SKILL.md 의 「기능 레포를 대시보드로 옮길 때」에서 연다.

개발자가 혼자 만든 기능 레포 하나를 본부 대시보드의 중앙 레포로 한 번 옮기고, 옮긴 뒤 기능 레포를 정리하는 절차다. 옮긴 뒤에는 중앙 레포가 그 기능의 기준 코드이고, 기능 레포에서 다시 가져오지 않는다. 기능 레포가 여럿이면 기능 레포마다 이 절차를 한 번씩 실행하라.

이 문서에서 쓰는 이름은 아래 뜻이다.

| 이름 | 뜻 |
|---|---|
| 기능 레포 | 개발자 혼자 쓰는 레포다. 최상위에 `frontend/` 와 `backend/` 를 두고, kw-github 의 표식 파일 `.kiwoom-feature` 가 있다 |
| 중앙 레포 | KiwoomAX 조직의 본부 대시보드 레포다. 이름이 `dashboard` 로 끝난다 |
| 기능 이름 | 기능 폴더의 이름이다. 기능 레포 이름을 그대로 쓴다 |
| 기능 폴더 | `src/frontend/src/features/<기능 이름>/` 와 `src/backend/features/<기능 이름>/` |
| 구조 파일 | `src/backend/feature_loader.py`, `src/backend/main.py`, `src/backend/tests/test_health.py`, `src/frontend/src/feature-menu.ts`, `src/frontend/src/routes.tsx` |
| 이전 branch | kw-github 기능 전환 명령으로 중앙 레포에 만드는 작업 branch 다 |
| 이전 commit | 기능 레포 파일을 기능 폴더로 들여오는 commit 하나다 |

## 명령을 실행하는 방법

이 스킬의 스크립트는 `python "${CLAUDE_SKILL_DIR}/scripts/<이름>.py"` 로 실행하라. 스크립트는 JSON 하나를 낸다. `status` 가 `ok` 이면 다음으로 가고, `stop` 이면 이 문서가 정한 대로 멈추고, `failed` 이면 `detail` 을 개발자에게 알리고 멈춰라.

kw-github 명령(저장 명령, 기능 전환 명령, 경계 검사, 업로드 명령, 이력 검사)은 Skill 도구로 kw-github 의 `saving-work` 스킬을 연 뒤, 그 스킬이 보여 주는 `save_work.py`·`scan_history.py` 경로와 인자 형식으로 실행하라. 이 문서에는 kw-github 의 경로를 적지 않는다.

이전 branch 의 commit 은 모두 저장 명령에 `--intake` 를 붙여 만들어라. 중앙 레포에서는 kw-github 가드가 직접 `git commit`·`git push` 를 거부한다. `git merge` 를 직접 실행할 때는 늘 `--no-commit` 을 붙여라. 가드는 merge 를 거부하지 않으므로 `--no-commit` 이 없으면 저장 명령의 검사 없이 commit 이 생긴다.

스킬은 기능 레포의 파일과 git 이력을 고치지 마라. 기능 레포에 필요한 일(저장, branch 합치기)은 개발자가 kw-github 로 하게 안내하라. 예외는 하나다. 2단계에서 PC 의 기본 branch 가 GitHub 보다 뒤처지기만 했으면, 개발자 동의를 받아 fast-forward 로 GitHub 위치에 맞춘다. 이력은 바뀌지 않는다.

## 시작 전: 필요한 값 모으기

이 절차의 스크립트에는 아래 값이 필요하다. 실행할 때마다 처음에 모아라.

| 값 | 얻는 방법 |
|---|---|
| 기능 레포 폴더 | 개발자에게 이 PC 의 기능 레포 폴더를 물어라 |
| 기능 레포 이름 | `git -C "<기능 레포 폴더>" remote get-url origin` 의 마지막 이름(`.git` 제외) |
| 중앙 레포 | 1단계 「중앙 레포 찾기」로 정한다 |
| 중앙 레포 폴더 | 개발자에게 이 PC 에 그 중앙 레포를 받아 둔 폴더가 있는지 물어라. 없으면 정한 폴더에 `gh repo clone KiwoomAX/<중앙 레포> "<폴더>"` 로 받아라. 다시 실행할 때는 같은 폴더를 써라 |
| 기능 이름 | 중앙 레포 폴더에서 `git config --get-regexp "^branch\..*\.kwfeature$"` 를 실행해, 이 기능 레포로 만든 이전 branch 가 있으면 그 값을 써라. 없으면 기능 레포 이름이다. 1단계에서 다른 이름을 받았으면 그 이름을 써라 |

## 시작 전: 다시 실행 판정

값을 모았으면 아래를 실행하라. 대화가 끊긴 뒤 다시 실행했는지 판정한다.

중앙 레포에서 세션을 열 때 지금 branch 가 이전 branch 이면, kw-github 세션 시작 알림은 업로드 질문 대신 「다시 실행 판정부터 이어 가라」고 알린다. 그 알림대로 이 판정을 먼저 하라. 알림이 commit 하지 않은 변경을 기능마다 commit 하라고 하더라도, 지금 branch 가 이 기능의 이전 branch(`kwFeature` 가 이 기능 이름)이면 따르지 말고 이 판정을 먼저 하라. 그렇게 commit 하면 `Intake-From` 줄이 없는 commit 이 생겨 12단계가 이전 commit 을 찾지 못한다.

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/resume_state.py" --central "<중앙 레포 폴더>" --feature-repo-name <기능 레포 이름> --feature <기능 이름>
```

중앙 레포를 아직 정하지 않았으면 1단계의 「중앙 레포 찾기」를 먼저 하고 이 판정으로 돌아와라. `--clean` 을 실행했으면 출력의 `cleaned` 가 참일 때만 1단계로 가라.

| `row` | 상태 | 할 일 |
|---|---|---|
| 1 | 이전 commit 이 이미 `main` 에 있다 | 11단계로 가라 |
| 2 | 이전 branch 가 업로드되었다 | `pr_state` 가 `closed` 이면 AX팀 문의로 멈춰라. `open` 이면 「AX팀이 검토 요청을 확인하고 있습니다」라고 알리고 멈춰라. 그 밖에는 kw-github `saving-work` 의 이어 하기(`upload --continue`)를 따르라 |
| 3 | 로컬에만 이전 branch 가 있다 | `branch_commits` 를 개발자에게 보여 주고 「이 작업은 지우고 처음부터 다시 합니다」라고 알려라. `uncommitted` 가 비어 있으면 같은 명령에 `--clean` 을 붙여 실행하고 1단계부터 다시 하라. `uncommitted` 에 경로가 있으면 그 경로를 보여 주고 처분을 개발자와 정한 뒤 다시 판정하라 |
| 4 | 이전 흔적이 없다 | 1단계부터 하라 |

`status` 가 `failed` 이면 아무것도 지우지 말고 멈춰라.

## 1. 대상 확인

**중앙 레포 찾기.** 개발자가 볼 수 있는 KiwoomAX 레포 중 이름이 `dashboard` 로 끝나는 레포를 이름순으로 보여 주고 개발자가 고르게 하라. 이름은 대소문자와 `-`·`_` 를 구분하지 않고 비교한다. 후보마다 주소와 마지막 push 시각을 함께 보여 줘라.

```powershell
gh repo list KiwoomAX --limit 1000 --json name,url,pushedAt
```

맞는 후보가 없다고 하면 개발자에게 아래 중 하나를 고르게 하라.

- 그 본부의 대시보드가 이미 있는데 목록에 없으면 볼 권한이 없는 상태다. AX팀에 그 중앙 레포의 쓰기 권한을 요청하라고 안내하고 멈춰라.
- 그 본부의 대시보드가 아직 없으면 SKILL.md 「새 대시보드 시작」으로 중앙 레포를 만들고, 서버 배포(`deploying-kiwoom-service`)까지 마친 뒤 이 단계로 돌아와라. 서버 배포를 마쳐야 `Jenkinsfile` 이 생긴다.

**uv 확인.** 이 절차는 잠금 파일 `uv.lock` 을 다시 만들고 그 파일대로 설치하므로 `uv` 가 필요하다.

```powershell
uv --version
```

실패하면 `python -m pip install uv` 로 설치하고, 설치했다고 개발자에게 알린 뒤 `uv --version` 을 다시 확인하라. 다시 실패하면 멈춰라.

**kw-github 확인.** `save_work.py upload --help` 출력에 `--intake` 가 있는지 확인하라. 없으면 「kw-github 플러그인을 업데이트해야 합니다」라고 안내하고 멈춰라.

**기능 레포 확인.** 기능 레포 최상위에 `frontend/index.tsx` 와 `backend/router.py` 중 하나 이상이 있어야 한다. 2단계의 `check_feature.py` 가 확인한다.

**중앙 레포 전제 확인.**

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/check_central.py" --central "<중앙 레포 폴더>"
```

| 점검 | 통과하지 못하면 |
|---|---|
| `push` | 쓰기 권한이 없다. AX팀에 권한을 요청하라고 안내하고 멈춰라 |
| `jenkinsfile` | Jenkins 로 배포되지 않는 레포다. AX팀 문의로 멈춰라 |
| `feature-dirs` | 템플릿 구조로 이관되지 않은 대시보드다. 아래 고정 문장으로 멈춰라 |
| `shell` | 셸이 템플릿과 다르다. 아래 고정 문장으로 멈춰라 |
| `structure` | 대시보드에서 고친 구조 파일이 있다(`verdict` 가 `modified`). 아래 고정 문장으로 멈춰라 |

이 점검들로 멈출 때는 이 문장을 첫 문장으로 써라. 「이 대시보드는 구조가 템플릿과 맞지 않아 AX팀의 확인과 이전이 필요합니다. AX팀에 문의해 주세요.」

**기능 이름 정하기.** 기능 이름은 기능 레포 이름이다. kw-github 가 그 이름을 `invalid-feature` 로 거부하면(점이 든 이름, Windows 예약 이름 등) 개발자에게 다른 이름을 받아라. 그때도 `Intake-From` 에는 원래 레포 이름을 적는다.

**이전 branch 만들기.** kw-github 기능 전환 명령(`switch-feature`)에 기능 이름과 영문 요약, 그리고 `--intake` 를 넘겨 이전 branch 를 만들어라. `--intake` 를 넘기면 kw-github 가 그 branch 에 기능 이전 표시를 남기고, 그 branch 에서는 `--intake` 없는 commit 과 업로드를 거부한다. 넘기지 않으면 3단계의 이전 commit 전에 만드는 구조 commit 이 그 보호를 받지 못한다.

**구조 commit.** `structure` 판정에 `add` 나 `update` 가 있으면 아래를 실행하고, 바뀐 파일(`applied`)을 개발자에게 알린 뒤 저장 명령 `--intake` 로 commit 하라. 구조 commit 은 다른 변경과 섞지 마라.

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/check_central.py" --central "<중앙 레포 폴더>" --apply-structure
```

## 2. 기능 레포 점검

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/check_feature.py" --feature-repo "<기능 레포 폴더>"
```

| 결과 | 할 일 |
|---|---|
| `dirty` 에 경로가 있다 | commit 하지 않은 변경이다. 개발자에게 kw-github 로 먼저 저장하라고 안내하고, 저장이 끝나면 이 단계를 다시 하라 |
| `entry` 가 둘 다 거짓 | 기능 레포 규칙을 따르지 않는다. AX팀 문의로 멈춰라 |
| `sync` 의 `ahead` 가 0 이 아니다 | PC 의 기본 branch 에 GitHub 에 올리지 않은 commit 이 있다. 개발자에게 kw-github 로 올리게 안내하고, 올린 뒤 이 단계를 다시 하라 |
| `sync` 의 `ahead` 가 0 이고 `behind` 가 0 이 아니다 | GitHub 에만 있는 commit 이 있다(GitHub 웹에서 고쳤거나 다른 PC 에서 올렸다). `dirty` 가 비어 있으면 「GitHub 의 최신 내용을 이 PC 의 기능 레포로 받겠습니다」라고 동의를 받고, 기능 레포 폴더에서 `git merge --ff-only origin/<default_branch>` 를 실행한 뒤 이 단계를 다시 하라. 동의하지 않으면 멈춰라 |
| `other_branches` 에 항목이 있다 | branch 이름과 마지막 commit 설명을 보여 주고 이전에 포함할지 물어라. `origin/` 으로 시작하는 이름은 GitHub 에만 있는 branch 다. 포함하려면 개발자가 kw-github 로 그 branch 를 기본 branch 에 합친 뒤 이 단계를 다시 하라. 포함하지 않으면 그 작업은 기능 레포를 지우면 사라진다고 알려라 |
| `status` 가 `failed` | 기본 branch 를 알 수 없다. `detail` 을 알리고 멈춰라 |

**이력 검사.** kw-github `scan_history.py` 에 `--ref <default_branch>` 를 넘겨 기본 branch 만 검사하라. PC 전용 branch `local-history` 는 가져오지 않는다. 결과의 파일 내용은 열지 마라.

| 결과 | 처분 |
|---|---|
| `clean` | 이력을 가져온다(`--history yes`) |
| `hits`, 원인에 `secret-filename` 이나 `secret-content` 가 있다 | 이력 없이 가져온다. 검출된 파일 경로와 규칙 이름을 보여 주고, 그 파일에 든 키를 폐기하고 새로 발급받으라고 안내하라 |
| `hits`, 원인이 모두 `data` | 이력 없이 가져온다. 「데이터 파일이 이력에 있어 마지막 코드만 옮깁니다」라고 알려라 |
| `timeout` | 이력 없이 가져온다 |
| `failed` | 멈춰라 |

이 검사는 파일 이름 규칙과 알려진 키 형식과 데이터 파일 규칙만 찾는다. 검사를 통과해도 안전이 보장되지 않는다는 사실을 개발자에게 한 번 알려라.

**데이터 원천.** 기능 코드가 데이터를 어디서 읽는지 찾아 아래로 판정하라. 대시보드는 Jenkins 가 만든 Docker 이미지로 서버에서 실행되므로, 개발자 PC 의 파일이나 직접 연결로 읽던 데이터는 그대로 동작하지 않는다.

| 기능 코드가 읽는 데이터 | 할 일 |
|---|---|
| 사내 공용폴더(`\\cifs\...`, `//<서버>/<공유 이름>/...`)의 파일 | 「공용폴더를 읽는 기능은 AX팀이 한 번 이관 작업을 해 줍니다. AX팀에 문의해 주세요.」라고 알리고 멈춰라 |
| 엑셀·CSV·SQLite 같은 데이터 파일(공용폴더 밖) | 「이 데이터는 PostgreSQL 로 옮겨야 합니다. AX팀에 문의해 주세요.」라고 알리고 멈춰라 |
| WINUS 직접 조회(`oracledb`, `cx_Oracle`, `winus-manager` 등) | 무엇을 바꿔야 하는지 한 문단으로 알리고 「`searching-winus` 스킬로 바꾼 뒤 다시 진행해 주세요」라고 안내한 뒤 멈춰라. 개발자는 기능 레포에서 바꾼 뒤 이 절차를 처음부터 다시 실행한다 |
| 이미 Query Gateway 나 사내 표준 SDK 로 읽는다 | 그대로 간다 |

## 3. 이전 commit

먼저 무엇을 옮길지 보고, `ask` 에 든 항목을 개발자에게 보여 주며 기능 폴더로 옮길 항목을 고르게 하라.

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/import_feature.py" --central "<중앙 레포 폴더>" --feature-repo "<기능 레포 폴더>" --feature <기능 이름> --branch <default_branch> --history yes --plan
```

`move` 는 기능 폴더로 옮기는 항목이다. `frontend/`, `backend/`, `tests/`(백엔드가 있을 때), `README.md` 다. `skip` 은 옮기지 않는 항목이다. PC 단독 실행용 파일, 의존성 파일(5단계에서 내용만 옮긴다), `.env`, 표식 파일이 여기에 든다. 기능 레포의 데이터 파일은 옮기지 않는다. 코드가 읽는 데이터 파일이면 개발자에게 알려라.

그다음 들여와라. 개발자가 고른 `ask` 항목은 `--extra` 로, 이력 검사에서 검출된 파일은 `--exclude` 로 넘겨라.

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/import_feature.py" --central "<중앙 레포 폴더>" --feature-repo "<기능 레포 폴더>" --feature <기능 이름> --branch <default_branch> --history <yes|no> --extra <항목> --exclude <경로>
```

| 결과 | 할 일 |
|---|---|
| `status` 가 `ok` 이고 `outside_clean` 이 참 | 저장 명령 `--intake --message` 로 commit 하라. 메시지 끝에 아래 세 줄을 둬라. `Intake-Head` 는 출력의 `head` 다 |
| `status` 가 `stop` | 중앙 레포에 commit 하지 않은 변경이 있거나 같은 이름의 기능 폴더가 이미 있다. `detail` 을 알리고 AX팀 문의로 멈춰라 |
| `status` 가 `failed` | 스크립트가 들여온 것을 되돌렸다. 이전 branch 를 지우고(「다시 실행 판정」의 `--clean`) 멈춰라 |

```
Intake-From: KiwoomAX/<기능 레포 이름>
Intake-Head: <head>
Intake-History: yes | no
```

이력을 가져왔으면 기능 폴더의 파일 하나를 `git log -m --follow -- <경로>` 로 조회해 기능 레포 시절 commit 이 보이는지 확인하라. `-m` 이 없으면 merge commit 너머의 이력이 보이지 않는다.

## 4. 연결 맞추기

기능 폴더 안 파일만 고쳐 기능이 대시보드의 자동 등록에 붙게 하라.

**개발자에게 묻는 항목.** 메뉴 이름을 물어라. 이어서 중앙 레포에 있는 카테고리 목록을 보여 주고 이 기능을 넣을 카테고리를 물어라. 고르지 않으면 낱개 기능이 된다.

**메뉴 구성 규칙.** 템플릿 `feature-menu.ts` 의 `buildMenu` 가 사이드바를 아래 순서로 만든다. 이 규칙은 바꾸지 말고 결과만 개발자에게 설명하라.

1. `routes.tsx` 의 `manualMenu` 에 적은 낱개 항목이 적은 순서대로 먼저 온다.
2. 카테고리가 없는 기능이 폴더 이름순으로 온다. 첫 화면 기능(`path: '/'`)은 그중 맨 앞에 온다.
3. 카테고리가 있는 기능은 카테고리 묶음 안에 폴더 이름순으로 들어간다. 새 카테고리는 맨 뒤에 붙는다.

첫 화면 기능이 카테고리에 들면 사이드바 맨 앞에 오지 않는다. 이 사실을 알리고 첫 화면 기능에는 카테고리를 두지 않기를 권하라.

**고치고 결과만 알리는 항목.**

- 프론트 기능 폴더에 `menu.ts` 를 만들어라(`name`, `page`, 필요하면 `path`·`cat`).
- 중앙 레포 `main` 에 `path: '/'` 를 쓰는 기능이 없으면 이 기능의 `menu.ts` 에 `path: '/'` 를 적어라.
- 화면을 `DashboardLayout` 으로 감싸는 화면 파일을 프론트 기능 폴더 안에 만들고 `menu.ts` 의 `page` 가 그 파일을 가리키게 하라. 기능 레포의 `frontend/index.tsx` 는 고치지 말고 새 화면 파일이 import 하게 하라.
- 기능 코드의 절대 import(`from backend.xxx`)를 기능 폴더 안 상대 import 로 고쳐라.
- 시험 코드의 import 는 `importlib.import_module("src.backend.features.<기능 이름>.<모듈>")` 형태로 고치고, PC 실행용 앱(`dev_app` 등) 대신 중앙 레포 앱(`src.backend.main:app`)을 쓰게 고쳐라. 기능 이름에 하이픈이 들 수 있어 import 문으로는 기능 폴더를 가리킬 수 없다.
- 화면 코드의 API 주소가 `/api/<기능 이름>/` 으로 시작하지 않으면 그 주소로 고쳐라.

백엔드만 있는 기능에는 `menu.ts` 를 만들지 말고 「API 만 붙고 사이드바 메뉴는 생기지 않습니다」라고 알려라. 프론트만 있는 기능에는 백엔드 기능 폴더를 만들지 마라.

이 단계의 변경은 기능 폴더 안에만 있어야 한다. 기능 코드 구조가 자동 등록에 붙일 수 없는 형태이면 AX팀 문의로 멈춰라. 이 단계의 변경을 저장 명령 `--intake` 로 commit 하라.

## 5. 의존성과 환경 변수

기능 폴더 밖에서는 아래 파일만 고쳐라. 이 파일들을 주의 깊게 검토하고, 조금이라도 문제가 보이면 멈춰라.

| 파일 | 고치는 내용 |
|---|---|
| `pyproject.toml`, `uv.lock` | 백엔드 의존성을 추가한다. 시험 수집 설정이 없으면 추가한다 |
| `src/frontend/package.json`, `src/frontend/package-lock.json` | 프론트 의존성을 추가한다 |
| `docker-compose.yml` | 환경 변수 줄을 추가한다 |
| `Jenkinsfile` | 9단계에서 `envCredIds` 에 서비스 전용 자격증명을 추가한다 |

**의존성 판단.** 버전은 주 버전(점 앞 첫 숫자)으로 비교하라. 주 버전이 0 인 패키지와 Python 은 둘째 숫자까지 비교하라.

| 상황 | 할 일 |
|---|---|
| 기능이 쓰는 패키지가 중앙 레포에 없다 | 기능 레포가 쓰던 버전으로 추가한다 |
| 같은 패키지이고 비교한 버전이 같다 | 중앙 레포 버전을 유지하고 8단계에서 동작을 본다 |
| 같은 패키지이고 비교한 버전이 다르다 | 개발자에게 알리고 묻는다. 기본안은 중앙 레포 버전 유지다. 그 버전에서 동작하지 않으면 8단계에서 멈춘다 |
| Python, React, FastAPI, Vite, TypeScript 중 하나의 비교한 버전이 다르다 | 멈춘다 |

의존성을 고친 뒤 `uv lock` 과 `src/frontend` 의 `npm install` 로 잠금 파일을 다시 만들어라. 잠금 파일에서 기존 패키지의 비교한 버전이 바뀌면 다른 기능이 깨질 수 있으므로 멈춰라.

**시험 수집 설정.** `pyproject.toml` 의 `[tool.pytest.ini_options]` 에 아래 두 설정이 없으면 추가하라. `testpaths` 에 다른 경로가 있으면 지우지 말고 `src/backend/features` 만 추가하라.

```toml
testpaths = ["src/backend/tests", "src/backend/features"]
addopts = "--import-mode=importlib"
```

**환경 변수.** 기능 코드에서 환경 변수를 읽는 곳(`os.getenv`, `os.environ`, 설정 클래스)을 찾아 키 이름 목록을 만들어라. 키 이름은 코드에서만 얻고 값 파일 `.env` 는 열지 마라. 키마다 비밀인지 개발자에게 확인받아라.

| 키 종류 | `docker-compose.yml` 에 적는 방법 |
|---|---|
| 비밀이 아닌 키 | `environment:` 에 `${키:-기본값}` |
| 기능이 반드시 필요로 하는 비밀 키 | `${키:?메시지}`. 메시지 문구는 배포 스킬 `compose-and-env.md` 의 규칙을 따른다 |
| 없어도 되는 비밀 키 | `${키:-}` |

비밀 키 이름이 중앙 레포 `docker-compose.yml` 에 이미 있으면 같은 값을 쓰는 키인지 확인받아라. 같은 값이면 다시 등록 요청하지 않는다. 다른 값이면 같은 이름에 두 값을 쓸 수 없으므로 멈춰라.

이 단계의 변경을 저장 명령 `--intake` 로 commit 하라.

## 6. 화면 맞추기

「기존 디자인 유지」와 「대시보드 디자인에 맞춤」 중 하나를 한 번 물어라. 기본안은 기존 디자인 유지다. 맞추기로 하면 색 토큰과 글자 크기를 `designing-kiwoom-frontend` 의 권장 값으로 바꿔라. 유지하기로 하면 그 사실을 이 단계의 commit 설명에 적어라.

셸 침범 규칙은 묻지 말고 고치고, 고친 위치를 알려라.

| 셸 침범 규칙 | 예 |
|---|---|
| 태그 이름에 적용하는 전역 CSS 규칙 | `h1`, `table`, `body` 선택자 |
| 셸 CSS(`src/frontend/src/shell/shell.css`)가 정의한 클래스를 다시 정의하는 규칙 | `.main`, `.shell`, `.rail`, `.topbar`, `.side`, `.nav-item`, `.content`. `shell.css` 의 클래스 목록을 읽어 대조하라 |
| 화면 크기에 고정한 크기 | `w-screen`, `h-screen`, `100vw`, `100vh` |
| 화면에 고정한 위치 | `position: fixed` |

이 단계의 변경을 저장 명령 `--intake` 로 commit 하라.

## 7. 설명 문서

현행 규칙은 메뉴에 붙인 기능마다 설명 문서를 두게 하고, 설명 문서는 사람이 쓴다. 개발자에게 설명 문서 파일을 물어라. 받으면 `docs/<기능 이름>.pdf` 나 `.docx` 로 두어라. 10MiB 를 넘으면 줄여 달라고 안내하라. 문서를 두었으면 저장 명령 `--intake` 로 commit 하라. 없으면 그 사실을 다음 commit 설명에 적고, 나중에 kw-github 로 추가하라고 안내하라. 내용을 지어내지 마라.

## 8. PC 확인

개발자 PC 에서 이전 branch 를 실행해 확인하라. 중앙 레포 폴더에서 시험과 빌드를 먼저 하라.

```powershell
uv sync
uv run pytest
npm --prefix src/frontend ci
npm --prefix src/frontend test
npm --prefix src/frontend run build
```

백엔드와 화면 개발 서버는 끝나지 않는 명령이므로 각각 백그라운드로 실행하고, 확인을 마치면 꺼라. 백엔드를 실행할 때 기능 레포의 `.env` 경로를 환경 파일로만 넘기고, 그 파일을 열거나 중앙 레포로 복사하지 마라. `.env` 가 없으면 `--env-file` 을 빼라.

```powershell
uv run --env-file "<기능 레포 폴더>\.env" uvicorn src.backend.main:app --port 8000
npm --prefix src/frontend run dev
```

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

| 확인 항목 | 통과 기준 |
|---|---|
| 프론트 시험과 빌드 | `npm test` 와 `npm run build` 가 성공한다 |
| 백엔드 시험 | `uv run pytest` 가 성공한다 |
| 백엔드 기동 | 백엔드가 뜨고, `/api/health` 의 `failed_features` 에 이 기능이 없다 |
| 기능 API | `/api/<기능 이름>/` 아래 주소 하나가 기능 레포에서와 같은 응답을 낸다 |
| 기능 화면 | 개발자가 사이드바에서 메뉴를 눌러 화면이 기능 레포에서와 같다고 답한다 |
| 기존 기능 | 이전 전부터 있던 기능의 메뉴가 그대로 열린다 |
| 낮·밤 화면 | 아래 「낮·밤 점검」을 마쳤다 |

다른 기능이 쓰는 키는 개발자 PC 에 없을 수 있다. 그래서 다른 기능이 불러오기에 실패해도 이 단계의 통과에는 영향이 없다.

실패 원인이 기능 폴더 안 파일에 있으면 4~7단계 중 그 파일을 다루는 단계로 돌아가라. 원인이 기능 폴더 밖(구조 commit, 의존성과 잠금 파일, 코드가 읽는 데이터 파일)에 있으면 멈춰라.

**낮·밤 점검.** 기능 폴더에서 색을 직접 적은 곳(`#fff` 같은 색 값, `bg-white`·`text-black` 같은 고정 색 클래스)을 찾아라. 찾으면 낮 화면과 밤 화면을 각각 캡처해 보라. 셸은 저장된 테마가 없으면 브라우저 설정을 따르므로, 새 프로필로 실행하고 `preferredColorScheme` 을 `0`(밤)과 `1`(낮)로 바꿔 캡처하라.

```powershell
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
Remove-Item -Recurse -Force "$env:TEMP\kw-intake-chrome" -ErrorAction SilentlyContinue
& $chrome --headless=new --disable-gpu --user-data-dir="$env:TEMP\kw-intake-chrome" --blink-settings=preferredColorScheme=0 --window-size=1600,1000 --screenshot="$env:TEMP\kw-intake-dark.png" "http://localhost:3000/<화면 주소>"
```

찾는 문제는 배경과 같은 색이라 읽을 수 없는 글씨와 밤 화면에 남은 흰 배경이다. 문제가 있으면 위치를 보여 주고 고칠지는 개발자가 정하게 하라. 고치지 않기로 하면 그 사실을 다음 commit 설명에 적어라. 고쳤으면 저장 명령 `--intake` 로 commit 하라.

셸에는 오류 경계(React Error Boundary)가 없어, 기능 화면 하나가 렌더 중 오류를 내면 그 화면을 연 동안 대시보드 전체가 빈 화면이 된다. 기능 화면 확인을 건너뛰지 마라.

## 9. 환경 변수 등록 요청

비밀 키를 대시보드의 Jenkins 자격증명에 등록하도록 AX팀에 요청한다. 비밀 키가 없거나, 모두 이미 등록된 같은 값의 키이면 이 단계를 생략하라.

**자격증명 이름.** 중앙 레포 `Jenkinsfile` 의 `envCredIds` 를 읽어라. `global-env`, `env-ax`, `env-am` 이 아닌 항목이 서비스 전용 자격증명이다. 없으면 배포 스킬의 규칙대로 짧은 서비스 이름을 개발자와 정하고, `env-<서비스 이름>` 을 `envCredIds` 끝에 추가해 저장 명령 `--intake` 로 commit 하라.

**메일 전 질문.** 메일을 보내기 전에 늘 두 가지를 물어라. 「`<중앙 레포>` 의 `<자격증명>` 에 키 등록 요청 메일을 이미 보냈습니까?」와 「그 요청에 AX팀 회신을 받았습니까?」다. 이미 보냈다고 하면 다시 보내지 마라.

**메일.** 배포 스킬 `deploying-kiwoom-service` 의 「AX 팀에 등록 요청 보내기」 절차로 보내라. 저장소 칸은 중앙 레포, 자격증명 칸은 위 이름, 키 칸은 비밀 키 목록과 어느 기능의 키인지, 값 파일 칸은 기능 레포의 `.env` 다.

**대기.** 메일을 보낸 뒤 「AX팀의 등록 완료 회신이 오면 알려 주세요」라고 안내하고 멈춰라. 회신 전에는 10단계로 가지 마라. 그때까지의 변경은 PC 의 이전 branch 에만 있으므로 배포가 멈추지 않는다.

## 10. 반영

업로드 전에 원격 최신 `main` 을 합친 상태에서 확인한다. 직접 `git push` 하거나 검토 요청을 병합하지 마라.

1. 중앙 레포에 commit 하지 않은 변경이 없는지 확인하라. 있으면 그 변경을 다룬 단계로 돌아가 commit 하라. 이어서 중앙 레포를 fetch 하라. 이전 branch 를 만든 뒤 `main` 에 새 commit 이 있으면 `git merge --no-commit origin/main` 으로 합치고 저장 명령 `--intake` 로 끝내라. 충돌이 나면 AX팀 문의로 멈춰라.
2. 최신 `main` 을 합쳤으면 `uv lock --check` 와 `src/frontend` 의 `npm ci` 로 잠금 파일이 맞는지 확인하라. 맞지 않으면 멈춰라.
3. kw-github `saving-work` 의 공유 레포 「올리기 흐름」에 따라 작업 이슈 제목을 정하고, `check-boundary --intake` 를 실행하고, 셀프 리뷰를 서브에이전트로 실행하고, 지적을 개발자와 논의하라. 셀프 리뷰어가 `docker-compose.yml`·`Jenkinsfile` 의 허용되지 않은 줄을 지적하고 개발자가 되돌리기로 하면, 그 줄만 중앙 레포 `main` 의 내용으로 고쳐 저장 명령 `--intake` 로 commit 하라. kw-github 가 검토 요청(PR)으로 전환하면 멈춰라.
4. 1번에서 `main` 을 합쳤거나 3번에서 코드가 바뀌었으면 8단계를 다시 하라. 9단계는 다시 하지 마라. 8단계가 4~7단계로 돌려보내면 고친 뒤 3번부터 다시 하라.
5. 업로드 명령에 `--intake` 를 넘겨 실행하라. 허용 경로는 넘기지 마라.
6. 반영되면 `review-upload --intake` 를 실행하라. 로컬 이전 branch 는 업로드 명령이 지운다.

업로드 명령이 `failed` 로 멈추면 `detail` 대신 `reason` 으로 처분을 골라라.

| `reason` | 할 일 |
|---|---|
| `intake-conflict` | 그사이 다른 반영과 충돌했다. 이 목록의 1번부터 다시 하라. 같은 실행에서 두 번째이면 AX팀 문의로 멈춰라 |
| `history-hits` | 업로드 직전 이력 검사가 비밀값이나 데이터 파일을 검출했다. AX팀 문의로 멈춰라 |
| `template-unavailable` | 템플릿을 조회하지 못했다. 멈춰라 |

이전 도중 템플릿의 구조 파일이 바뀌면 kw-github 가 그 구조 파일을 경계 위반으로 낸다. 그때는 「시작 전: 다시 실행 판정」의 3행대로 이전 branch 를 지우고 1단계부터 다시 하라.

반영에는 중앙 레포 관리자의 승인 단계가 없다. 기술 검토는 kw-github 셀프 리뷰가 맡는다.

## 11. 배포 확인

개발자에게 Jenkins 에서 중앙 레포 잡의 `main` 을 수동 빌드(Build Now)하라고 안내하라. 빌드가 성공하면 배포된 대시보드 주소에서 아래를 확인하게 하고 답을 받아라.

| 확인 항목 | 통과 기준 |
|---|---|
| 기능 화면 | 사이드바에서 메뉴를 눌러 화면이 PC 확인 때와 같다 |
| 첫 화면 | 대시보드 주소 `/` 에 첫 화면 기능 하나가 보인다 |
| 기존 기능 | 이전 전부터 있던 기능의 메뉴가 그대로 열린다 |

빌드가 실패하거나 하나라도 맞지 않으면 멈춰라. 실패 단계와 로그 위치는 배포 스킬의 `jenkins-logs.md` 대로 안내하라. 이때 `main` 에는 이미 이전 commit 이 있지만 되돌리지 마라. 복구는 AX팀이 판단한다. AX팀에 전할 문단에 실패한 빌드 단계나 맞지 않은 항목, 로그 위치, 이전 commit 해시를 넣어라.

## 12. 기능 레포 정리

개발자가 배포본을 확인했다고 답한 뒤에만 기능 레포 삭제를 안내하라. 원칙은 「데이터 파일은 반드시 개발자 확인을 받고, 확인받지 않은 파일이 사라질 위험이 있으면 삭제 안내를 멈춘다」이다.

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/cleanup_check.py" --central "<중앙 레포 폴더>" --feature-repo "<기능 레포 폴더>" --feature-repo-name <기능 레포 이름> --feature <기능 이름>
```

| 점검 | `action` 이 `pass` 가 아닐 때 할 일 |
|---|---|
| `new-commits` | 이전 뒤 기능 레포에 commit 이 생겼다. 삭제 안내를 멈춰라 |
| `unpushed` | branch 이름과 commit 설명을 보여 주고, 개발자가 버려도 된다고 답해야 통과다 |
| `pc-only` | PC 에만 있는 파일 목록을 보여 줘라 |
| `data-files` | 파일마다 「옮길 곳을 정했다」와 「버려도 된다」 중 하나를 개발자가 고르게 하라. 하나라도 고르지 않았으면 멈춰라 |
| `not-moved` | 이력 없이 옮겨 기능 레포에만 남는 파일이다. 파일마다 옮기지 않아도 되는지 확인받고, 확인받지 못한 파일이 있으면 멈춰라 |
| `issues` | 이슈마다 `body` 를 읽어 「이미 끝났는데 닫지 않은 일」과 「앞으로 할 일」로 나눠 보여 주고 처분을 받아라 |
| `prs` | 목록을 보여 주고, 합쳐지지 않은 작업은 삭제하면 사라진다고 알려라 |

`status` 가 `failed` 이면 조회가 실패한 점검을 통과로 보지 말고 멈춰라. `intake` 가 비어 있으면(`null`) `main` 에서 이전 commit 을 찾지 못한 상태다. `detail` 을 알리고 멈춰라.

**남은 배포 항목.** 기능 레포의 `docker-compose.yml` 에서 `container_name` 을 읽고 포트 등록부를 조회하라.

```powershell
$q = '{"query":"select port, container, repo from kw_deploy.port where repo = ''<기능 레포 이름>'' or container = ''<container_name>''"}'
Invoke-RestMethod -Uri 'http://192.7.9.45:8700/v1/query/all-dict' -Method Post -ContentType 'application/json' -Body $q
```

결과가 있거나, 개발자가 Jenkins 에서 기능 레포 이름의 잡을 찾으면 AX팀에 정리를 요청하라고 안내하라.

**이슈 처분.** kw-github 는 개발자에게 이슈를 말하지 않지만, 이 단계는 개발자가 직접 처분을 정해야 한다. 그래서 이 단계에서만 「GitHub 에 적어 둔 할 일 목록(이슈)」이라고 한 번 풀어 말하라. 「앞으로 할 일」 이슈는 중앙 레포로 옮기기(`gh issue transfer <번호> KiwoomAX/<중앙 레포> -R KiwoomAX/<기능 레포>`), 닫기, 레포와 함께 삭제하기 중 개발자가 고르게 하라. 옮겨도 이슈 타입은 유지된다.

**삭제 안내.** 기능 레포 웹 페이지에서 Settings, Danger Zone, Delete this repository 순서로 삭제하는 방법을 안내하고, 삭제하면 되돌릴 수 없다고 알려라. 무엇이 남는지는 이전 commit 의 `Intake-History` 로 알려라.

| `Intake-History` | 알릴 내용 |
|---|---|
| `yes` | 코드와 git 이력은 중앙 레포에 남는다 |
| `no` | 마지막 코드만 중앙 레포에 남는다. git 이력과 옮기지 않은 파일은 삭제하면 사라진다 |

PC 폴더 삭제도 안내하되, PC 에만 있는 파일을 다시 알리고 그 파일을 처리하기 전에는 PC 폴더를 지우지 말라고 안내하라. GitHub 레포와 PC 폴더 어느 쪽도 대신 지우지 마라. 개발자가 삭제하지 않기로 하면 그대로 끝내라.

## 개발자와의 대화

결정이 필요한 항목과 개발자가 알아야 하는 항목만 묻거나 알리고, 나머지 기술 처리는 스스로 한 뒤 결과만 알려라. 개발자에게 하는 말은 kw-github `git_terms.md` 를 따른다(merge 는 「반영」, PR 은 「검토 요청」).

| 구분 | 항목 |
|---|---|
| 묻는 항목 | 중앙 레포 선택, 맞는 중앙 레포가 없을 때의 길, 다른 branch 작업 포함 여부, `ask` 항목 중 옮길 것, 메뉴 이름과 카테고리, 의존성 버전 차이, 환경 변수의 비밀 여부, 겹친 키 이름의 값 일치, 서비스 이름, 디자인 유지 여부, 설명 문서 파일, 낮·밤 문제 수정 여부, 메일 발송 여부, 회신 수신 여부, 배포본 확인 결과, 데이터 파일마다의 처분, 옮기지 않은 파일의 확인, 열린 이슈의 처분, 기능 레포 삭제 여부 |
| 알리는 항목 | `uv` 를 설치한 사실, 구조 commit 으로 바꾼 파일, 이력 검사의 한계, 이력 없이 가져온 사실과 폐기할 키, 이전되지 않는 작업과 파일, 코드가 읽는 데이터 파일, 첫 화면 기능과 카테고리의 관계, 고친 파일 목록, 낮·밤 점검 결과, 메일 발송 사실, 삭제하면 사라지는 항목 |
| 처리하고 결과만 알리는 항목 | 구조 파일 맞추기, 파일 이동, 단독 실행 파일 제외, `menu.ts` 와 화면 파일 생성, import 와 API 주소 수정, 셸 침범 규칙 수정, 잠금 파일 다시 만들기, 첫 화면 지정, 이전 branch 정리 |

## AX팀 문의로 멈출 때

멈출 때는 무엇을 확인했고 왜 멈췄는지를 한 문단으로 써라. 개발자가 그 문단을 AX팀에 그대로 전달할 수 있게 써라. 1단계 구조 점검으로 멈출 때는 그 절의 고정 문장을 첫 문장으로 써라.

| 단계 | 상황 |
|---|---|
| 1 | 전제 조건 중 하나를 만족하지 않는다. 중앙 레포를 볼 권한이 없다 |
| 2 | 이력 검사 결과가 `failed` 다. 기능 코드가 사내 공용폴더를 읽는다. 기능의 데이터를 PostgreSQL 로 옮겨야 한다. 기능 레포가 규칙을 따르지 않는다 |
| 3 | 같은 이름의 기능 폴더가 `main` 에 이미 있다. 이전 commit 을 만들지 못했다 |
| 4 | 기능 코드 구조가 자동 등록에 붙일 수 없는 형태다 |
| 5 | 이전 허용 파일의 변경에서 문제가 보인다. 의존성 판단 기준이 멈춤을 정했다. 같은 키 이름에 다른 값이 필요하다 |
| 8 | 실패 원인이 기능 폴더 밖에 있다 |
| 10 | 최신 `main` 합치기에서 충돌이 났다. 잠금 파일 확인이 실패했다. kw-github 가 검토 요청으로 전환했다. 업로드 직전 이력 검사가 검출했다. 충돌이 두 번 났다 |
| 11 | Jenkins 빌드가 실패했다. 배포본 확인 항목 중 하나가 맞지 않는다 |
| 다시 실행 | 검토 요청이 반영되지 않고 닫혔다 |
