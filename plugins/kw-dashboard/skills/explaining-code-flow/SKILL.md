---
name: explaining-code-flow
description: Use when someone wants to see how their repo works feature by feature (which button reads which DB, which server and AI it passes through, and what comes back), especially vibe coders who cannot read the code. Builds a moving guide page with screen captures (front end only, fed with example data) in the repo's docs/code-flow folder. Triggers on 코드 흐름·동작 흐름·어떻게 동작하는지·기능별 흐름·흐름 시각화·code flow.
---

# explaining-code-flow

이 스킬은 레포의 기능마다 「버튼을 누르면 자료가 어디로 오가는지」를 움직이는 그림과 화면 캡처로 보여 주는 HTML 을 만든다. 결과물은 레포의 `docs/code-flow/` 에 생기고 git 에서 제외된다. 읽는 사람은 바이브 코더이고 함수 이름과 API 개념을 모른다고 가정한다.

화면 캡처는 백엔드를 실행하지 않는다. 화면 코드만 실행하고, 화면이 보내는 요청에는 분석이 만든 가짜 데이터로 응답한다. 그래서 실제 데이터가 찍히지 않고, 아웃룩 · 사내 DB · 키 같은 실행 조건이 필요 없으며, 버튼을 눌러도 바깥에 아무 일도 일어나지 않는다. 서버 쪽 흐름은 코드 분석으로 그린 흐름 그림과 설명이 보여 준다.

## 절차

아래 순서로 진행한다. 사용자에게 묻는 곳은 결과 확인뿐이다.

| 단계 | 하는 일 |
|---|---|
| 레포 찾기 | 현재 폴더와 그 상위 폴더에서 이름이 같은 git 레포를 찾는다. 후보가 여럿이거나 없으면 경로를 묻는다. `git -C <레포> rev-parse --abbrev-ref HEAD` 와 `git -C <레포> rev-parse --short HEAD` 로 브랜치와 커밋을 기록한다 |
| 도구 확인 | 아래 「스크립트」의 `doctor` 를 실행한다. 「없음」 줄이 있으면 무엇이 없는지 알린다 |
| 기능 목록 | 메뉴 · 탭 · 라우트를 코드에서 읽어 사용자에게 보이는 기능 이름으로 나열해 알리고, 묻지 않고 모든 기능을 분석한다. 사용자가 빼라고 하면 뺀다 |
| 기능별 분석 | 기능마다 분석 서브에이전트를 동시에 실행한다. 프롬프트에 [analysis-prompt.md](analysis-prompt.md) 와 [tips-prompt.md](tips-prompt.md) 의 경로, 레포 경로, 맡을 기능 이름, `appZone` 이름을 넣는다 |
| 형식 검사 | 돌아온 결과가 JSON 하나로 읽히는지 확인한다. 읽히지 않으면 그 서브에이전트에 형식만 고쳐 다시 달라고 한다 |
| 근거 대조 | `evidence` · `tipsEvidence` · `mockEvidence` 의 `파일:줄` 이 실제로 있는지 모두 확인하고, 기능마다 문장 몇 개를 골라 근거 줄과 내용을 대조한다. 맞지 않는 문장은 고치거나 지운다 |
| 화면 실행 | 아래 「화면 실행」을 따른다 |
| 화면 캡처 | 캡처 이미지가 git 에 잡히지 않도록 `docs/code-flow/.gitignore` 를 먼저 만들고(「결과물」 절), 캡처 계획을 만들어 `capture.py` 를 실행한다. Node 화면이면 끝난 뒤 `stop` 을 반드시 실행한다 |
| JSON 합치기 | 아래 「JSON 합치기」를 따라 `docs/code-flow/flow.json` 을 만든다 |
| 렌더 | `render.py` 로 `docs/code-flow/index.html` 을 만들고 브라우저로 연다 |
| 보고 | 아래 「결과 알리기」를 따른다 |

`appZone` 은 레포 서비스가 실행되는 곳의 이름이다(예: 「홀세일 대시보드 (클라우드)」, 「메일 보관함 (내 PC)」).

## 스크립트

`<작업 폴더>` 는 레포 밖 임시 폴더다(예: 윈도우 `%TEMP%` 아래 `code-flow-<레포 이름>`). 상태 파일 · 로그 · 캡처 계획을 여기에 둔다.

```text
python "${CLAUDE_SKILL_DIR}/scripts/run_repo.py" doctor
python "${CLAUDE_SKILL_DIR}/scripts/run_repo.py" start <레포> --state <작업 폴더>/state.json
python "${CLAUDE_SKILL_DIR}/scripts/run_repo.py" exec <레포> -- uv run --no-project --with playwright python "${CLAUDE_SKILL_DIR}/scripts/capture.py" <작업 폴더>/capture_plan.json --out <작업 폴더>/capture_result.json
python "${CLAUDE_SKILL_DIR}/scripts/run_repo.py" stop --state <작업 폴더>/state.json
python "${CLAUDE_SKILL_DIR}/scripts/render.py" <레포>/docs/code-flow/flow.json --out <레포>/docs/code-flow/index.html
```

- `exec` 는 사내 인증서 묶음을 `SSL_CERT_FILE` 로 준 채 명령을 실행한다. 윈도우 PC 에는 컨트롤 타워 설치기가 설정한 `SSL_CERT_FILE` 이 있어 그 값을 쓰고, 없을 때만 레포의 `certs/ePrism.crt` 로 묶음을 만든다. `uv` 가 Playwright 를 내려받을 때 사내 프록시를 통과하려면 `uv run` 을 반드시 `exec` 로 감싼다.
- `start` · `stop` 은 Node 화면에만 쓴다. `start` 는 의존성을 설치하고 개발 서버를 `127.0.0.1` 의 빈 포트로 실행한 뒤 `{"url": ...}` 를 출력한다. 서버가 `127.0.0.1` 밖의 주소에 열리면 바로 끄고 실패로 끝난다.
- `stop` 은 캡처가 실패해도 반드시 실행한다. 종료 코드가 3 이면 레포의 추적 파일이 바뀐 것이므로 출력된 파일 목록을 사용자에게 알린다.

## 화면 실행

화면 코드의 종류에 따라 실행 방법이 다르다.

| 화면 코드 | 실행 방법 | 캡처 계획 |
|---|---|---|
| Node(`package.json` 의 `dev`, Next.js · Vite) | `start` 로 개발 서버를 실행한다 | `baseUrl` 에 `start` 가 출력한 주소를 넣는다 |
| 정적 HTML · JS | 서버를 실행하지 않는다 | `static` 에 레포 경로와 주소 · 파일 대응을 넣는다. 대응은 레포의 서버 코드가 주소마다 어떤 파일을 내주는지 읽어 정한다 |

`start` 가 실패하거나 화면 파일을 찾지 못하면 `capture.py <계획> --out <결과> --fail front` 로 모든 장면에 「화면 코드를 실행하지 못함」 문구를 적는다. 레포에 화면 코드가 없으면 `--fail noscreen` 을 쓴다. 흐름 그림과 설명은 그대로 만든다.

## 캡처 계획

`<작업 폴더>/capture_plan.json` 은 분석 결과의 `capture` 와 `mocks` 를 모아 만든다. 장면 `id` 는 `<기능 key>-<장면 번호>` 로 짓고, 기능의 `mocks` 는 그 기능 아래에 둔다.

```json
{"outDir": "<레포>/docs/code-flow/screens",
 "static": {"root": "<레포>", "routes": [{"path": "/", "file": "src/web/index.html"}, {"prefix": "/static/", "dir": "src/web"}]},
 "features": [{"key": "search", "path": "/",
   "mocks": [{"method": "GET", "path": "/api/search", "json": {"rows": []}}],
   "scenes": [{"id": "search-0", "steps": [{"action": "type", "target": {"selector": "#q"}, "text": "견적"}], "end": {"selector": "#rows"}}]}]}
```

Node 화면은 `static` 대신 `"baseUrl": "<start 가 출력한 url>"` 을 넣는다. `capture.py` 는 가짜 데이터와 화면 파일에 없는 요청을 모두 끊으므로, 화면이 비어 보이면 빠진 가짜 응답을 분석 결과에서 찾아 넣는다.

## JSON 합치기

`flow.json` 의 최상위는 `title`(「<레포 이름>, 움직이며 보기」) · `repo`(`<레포> (<브랜치> <커밋>)`) · `appZone` · `features` 다. 기능마다 분석 결과의 `feature` 를 넣고, `capture_result.json` 의 값을 아래처럼 옮긴다.

| capture_result.json | flow.json |
|---|---|
| `features.<key>.screenImg` | 기능의 `screenImg` |
| `scenes.<id>.start` · `end` | 장면의 `screen.start` · `screen.end` |
| `scenes.<id>.endImg` | 장면의 `screen.endImg` |
| `scenes.<id>.unavailable` | 장면의 `screen.unavailable` |
| `scenes.<id>.typed` | 장면의 `screen.typed` |

`render.py` 가 고칠 곳을 출력하면 그 목록대로 `flow.json` 을 고친 뒤 다시 실행한다.

## 결과물

결과물은 레포의 `docs/code-flow/` 에 `index.html` · `screens/` · `flow.json` 으로 둔다. 같은 폴더에 내용이 `*` 한 줄인 `.gitignore` 를 만든다. 이 파일은 자기 자신을 포함한 폴더 전체를 git 에서 제외하므로, 레포 루트의 `.gitignore` 는 고치지 않는다. 렌더한 뒤 `git -C <레포> status --short docs/code-flow` 가 빈 출력인지 확인한다.

## 결과 알리기

결과를 알릴 때 아래를 함께 적는다.

- 결과물 경로(`docs/code-flow/index.html`)
- 캡처하지 못한 기능과 그 문구
- 분석 서브에이전트가 돌려준 `mismatches`(코드와 주석이 다른 곳). 고치지 않고 보고만 한다.
- 화면 캡처는 예시 데이터로 그린 화면이라는 점
- 다른 사람에게 줄 때는 `index.html` 과 `screens/` 폴더를 함께 줘야 한다는 점

## 화면과 문장 규칙

| 규칙 | 이유 |
|---|---|
| 함수 이름 대신 「누가 무엇을 어디에 보낸다」는 서술형으로 쓴다 | 바이브 코더는 함수 이름을 모른다 |
| 버튼 하나를 누른 뒤 일어나는 일을 장면으로 나누고, 화면 표기는 「홈」 메뉴 클릭처럼 버튼 이름으로 쓴다 | 「누를 곳으로 확대」 같은 표기는 어색하다 |
| 동시 처리 건수 제한 같은 내부 수치는 넣지 않는다 | 사용자가 알 필요가 없다 |
| 코드가 하지 않는 동작은 그리지 않고, 값을 하나씩 따로 가져오면 따로 그린다 | 한 묶음으로 모아 보내는 그림은 코드와 달라 거짓이 된다 |
| 예시 값은 「샘플 데이터」라고 밝힌다 | 실제 집계로 오해한다 |
| 버튼만이 아니라 검색어 입력 · 목록에서 고르기 같은 사용자 동작을 차례로 따라가고, 자료 이름에는 「"견적" 검색」처럼 예시 값을 쓴다 | 시연 영상처럼 실제 사용 순서가 보여야 이해된다 |
| 외부 프로그램 · 외부 시스템(아웃룩, 엑셀, WINUS, FAS, 외부 사이트)은 처음 쓰일 때 열리는 동작을 보여 준다(`launch`) | 바깥 프로그램에서 가져온다는 점이 보여야 한다 |
| 알아 둘 점은 장면마다 5개 안팎으로, 화면에서 직접 확인할 수 있는 규칙만 적는다 | 많으면 중요한 규칙이 묻힌다 |
| 노드 상자는 회색 테두리로 두고, 색은 구역 상자에만 쓴다 | 구역 색과 상자 색이 겹쳐 어지럽다 |
| 왼쪽 세로 띠를 쓰지 않고, 현재 줄은 회색 면으로 표시한다 | 대시보드 스킬의 강제 규칙과 같다 |
| 「알아 둘 점」은 남색 테두리와 큰 글자로 두고, 분홍 같은 튀는 색은 쓰지 않는다 | 중요한 정보지만 화려할 필요는 없다 |

노드 종류와 구역의 고정 명칭표는 [analysis-prompt.md](analysis-prompt.md) 의 「고정 명칭표」에 있다. 템플릿(`scripts/movie_template.html`)이 같은 명칭을 고정해 그리므로, 분석 결과의 `kind` · `zone` 은 그 표의 값만 쓴다.
