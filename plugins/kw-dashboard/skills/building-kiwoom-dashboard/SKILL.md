---
name: building-kiwoom-dashboard
description: Use when working in a Kiwoom 본부 · 팀 dashboard repo made from KiwoomAX/dashboard-template, such as starting a new 본부 dashboard, adding a feature page or sidebar menu entry, filling the alert drawer, adding a backend API, or deciding how far a dashboard page may differ from the kw-design default look. Also use when moving an existing dashboard (such as an old dash-kit HTML one) into the template, and when reviewing such a change before it ships. Triggers on 본부 대시보드·대시보드 기능 추가·사이드바 메뉴·알림 서랍·dashboard-template·dash-kit 이전·대시보드 규칙.
---

# building-kiwoom-dashboard

본부 · 팀 대시보드는 `KiwoomAX/dashboard-template` repo 를 복제해 만든다. 화면은 구획 3개로 나뉜다.

| 구획 | 누가 그리나 | 규칙 |
|---|---|---|
| 사이드바 | 셸 | 강제 |
| 상태바(오른쪽 위) | 셸. 페이지는 값만 넘긴다 | 강제 |
| 내용 구획(오른쪽 아래) | 페이지 | 권장 |

셸은 `src/frontend/src/shell/` 이다. 셸 사용법은 repo 의 코드 주석과 타입과 콘솔 경고가 알려 준다.
이 스킬은 코드가 알려 주지 않는 것만 적는다.

## 강제: 사이드바와 상태바

- **`src/frontend/src/shell/` 과 `index.html` 의 셸 스크립트를 고치지 않는다.** AX 팀은 셸을 고치면 이 폴더를
  통째로 덮어써서 내보내므로, 대시보드에서 고친 내용은 그때 사라진다. 셸에 바꿀 것이 있으면 AX 팀에 요청한다.
- **전역 CSS 에 태그 이름 규칙을 적지 않는다.** `h1 { … }` · `table { … }` · `body { … }` 같은 규칙은 사이드바와
  상태바 모양까지 바꾼다. 모양은 요소마다 Tailwind 클래스로 준다.
- **셸이 쓰는 클래스 이름을 내용 구획 CSS 에 다시 정의하지 않는다.** `.shell` · `.rail` · `.topbar` · `.side` ·
  `.nav-item` · `.content` 같은 이름이다. 겹치면 이름을 바꾼다.

## 새 대시보드 시작

**repo 를 만들기 전에 이미 있는지 찾는다.** 담당자 PC 의 폴더를 먼저 보고, 없으면 조직을 본다. 찾지 않고
만들면 같은 본부의 대시보드가 2개가 된다. 그러면 조직 폴더가 같은 `Jenkinsfile` 로 Jenkins 잡을 2개 만들고,
두 잡이 같은 이름의 컨테이너를 서로 지운다.

1. **폴더 확인.** 담당자에게 이 본부의 대시보드를 만들던 폴더가 PC 에 있는지 묻는다. 있으면 그 폴더로 옮겨
   거기서 이어서 작업한다. 새로 받지 않는다. 그 폴더에 무엇이 있는지에 따라 갈 곳이 다르다.

   | 폴더에 있는 것 | 어디로 간다 |
   |---|---|
   | `src/frontend/src/shell/` 이 있다 | 템플릿으로 만든 대시보드다. 「조직 이름 적기」로 간다 |
   | `src/frontend/src/shell/` 이 없다 | 옛 대시보드다. 「이미 만든 대시보드를 옮길 때」로 간다 |

   폴더가 없다고 하면 「조직 repo 찾기」로 간다.

2. **조직 repo 찾기.** 조직의 repo 이름을 받아 이 본부의 대시보드가 있는지 본다. 대소문자와 `-`·`_` 차이는 무시한다.
   `Executive_dashboard` 와 `executive-dashboard` 는 같은 후보다.

   ```powershell
   gh repo list KiwoomAX --limit 1000 --json name,url,pushedAt
   ```

   `gh` 가 로그인 오류를 내면 멈추고 담당자에게 `gh auth login` 을 직접 실행하라고 알린다. **목록을 보지 못한
   채로 새 repo 를 만들지 않는다.**

   **배포까지 마친 대시보드는 포트 등록부에도 적혀 있다.** 담당자가 볼 권한이 없어 위 목록에 안 보이는 repo 를
   여기서 찾는다. `repo` 칸이 repo 이름이다. 등록부에 닿지 못하면 그것만 알리고 위 목록으로 판단한다.

   ```powershell
   $q = '{"query":"select port, container, repo from kw_deploy.port where service_type = ''dashboard'' order by port"}'
   Invoke-RestMethod -Uri 'http://192.7.9.45:8700/v1/query/all-dict' -Method Post -ContentType 'application/json' -Body $q
   ```

3. **찾은 repo 확인.** 찾은 repo 가 있으면 주소와 마지막 push 시각을 보여 주고 「이 본부의 대시보드가
   맞습니까」라고 묻는다. 맞다고 하면 받아서 그 폴더에서 이어서 작업한다. 받은 폴더에 `src/frontend/src/shell/`
   이 있으면 「조직 이름 적기」로 가고, 없으면 옛 대시보드이므로 「이미 만든 대시보드를 옮길 때」로 간다.

   ```powershell
   gh repo clone KiwoomAX/<찾은 이름>
   ```

   **포트 등록부에서만 찾았으면 받지 못한다.** `gh repo list` 에 안 보이고 등록부에만 있는 repo 는 담당자에게
   볼 권한이 없어 `gh repo clone` 이 `Could not resolve to a Repository` 로 실패한다. 등록부에는 마지막 push 시각도
   없다. 「GitHub 코드 저장소는 있으나 볼 권한이 없다」고 알리고 AX 팀에 권한을 요청하라고 한 뒤 멈춘다. 새로 만들지 않는다.

   **담당자가 모른다고 하면 만들지 않고 멈춘다.** 이 본부의 대시보드를 전에 만든 사람에게 GitHub 코드 저장소 주소를
   물어보라고 알린다. 확신 없이 만들면 둘이 된다.

   없으면 아래로 간다. 이름을 `<본부 영문 이름>-dashboard` 로 제안해 확인받은 뒤 만들고 바로 받는다. 이름은
   소문자와 하이픈으로 짓는다. **이름을 혼자 정하지 않는다.**

   ```powershell
   gh repo create KiwoomAX/<본부 영문 이름>-dashboard --template KiwoomAX/dashboard-template --private --clone
   ```

4. **조직 이름 적기.** `src/frontend/src/dashboard.config.ts` 의 `org` 를 조직도에 적힌 이름 그대로 적는다. 이름이 「본부」로 끝나면
   사이드바 무리 이름이 「본부 기능」이 되고, 「팀」으로 끝나면 「팀 기능」이 된다.
5. **다른 본부 목록.** `others` 에는 실제로 화면이 있는 다른 본부 대시보드만 적는다. 비어 있으면 본부 전환 목록을 달지 않는다.
6. **로컬에서 실행.** 백엔드와 화면을 실행하고 `http://localhost:3000` 을 연다. 백엔드가 8000번에서 답하고,
   화면 쪽이 `/api` 로 시작하는 요청을 그리로 넘긴다. PowerShell 창을 2개 열어 아래 블록 2개를 하나씩 실행한다.
   설치는 처음 한 번만 하면 되고, 그다음부터는 첫 블록의 마지막 줄과 `cd src/frontend; npm run dev` 만 실행한다.

   ```powershell
   python -m venv .venv
   .venv\Scripts\python -m pip install fastapi "uvicorn[standard]"
   .venv\Scripts\python -m uvicorn src.backend.main:app --reload
   ```

   ```powershell
   cd src/frontend; npm install; npm run dev
   ```

   설치할 목록은 `pyproject.toml` 의 `dependencies` 에 적혀 있다. 그 목록이 늘면 늘어난 것도 함께 설치한다.
7. **서버 배포.** 서버 배포는 `deploying-kiwoom-service` 스킬로 한다.

## 기능 붙이기

기능 하나는 페이지 하나와 메뉴 줄 하나다.

1. 페이지 컴포넌트를 만들고 내용을 `DashboardLayout` 으로 감싼다. 상태바에 보일 값은 이 컴포넌트의 props 로만
   넘긴다(아래 「상태바 값」).
2. `src/frontend/src/routes.tsx` 의 메뉴 목록에 줄을 추가한다. 줄 모양과 카테고리 규칙은 그 파일 주석에 있고,
   규칙을 어기면 브라우저 콘솔에 `[shell]` 경고가 나온다.
   **대표 기능 하나는 `path: '/'` 로 둔다.** 그 기능이 대시보드의 첫 화면이 된다. `/` 를 맡은 기능이 없으면
   주소 `/` 로 들어온 사람은 템플릿의 빈 첫 화면을 본다.
3. **화면이 아직 없는 기능은 메뉴에 둘지 사람에게 묻는다.** 두겠다고 답하면 줄을 추가한다. 답하지 않았거나 두지
   않겠다고 답하면 화면이 생길 때 줄을 추가한다. `locked: true` 는 화면이 있는데
   권한이 없는 기능에만 쓴다. 툴팁이 「접근 권한이 없습니다」라서 화면이 없는 기능에 쓰면 뜻이 틀린다.
4. **카테고리에 들지 않은 낱개 기능은 카테고리 앞이나 뒤에 모아 둔다.** 홈처럼 첫 화면이 되는 기능은 카테고리
   앞에 둔다. 카테고리 사이에 끼우면 콘솔에 경고가 나온다. 카테고리 안 기능이 하나뿐이어도 된다.
5. 기능 이름은 한글 13자 안쪽을 권장한다. 넘으면 2줄로 접혀 그 줄만 키가 커진다.
6. 백엔드 API 는 `src/backend` 에 라우터로 만들어 `/api/<기능 이름>` 아래에 붙인다. 기능 이름은 영문 소문자와
   하이픈으로 짓고(`/api/kpi`), 알림 서랍은 `/api/alerts` 를 쓴다. nginx 가 `/api/` 로 시작하는 요청만 백엔드로
   넘긴다. 다른 서버의 키나 토큰이 필요한 호출은 브라우저에서 하지 않고 백엔드가 한다.

## 상태바 값

| 값 | 언제 주나 |
|---|---|
| `title` | 늘 준다. 메뉴 이름과 같게 둔다 |
| `asof` | 데이터를 받은 뒤, 그 데이터가 언제 기준인지(배치가 만든 시각 등)를 문구로 준다(「2026.08.26 08:40 기준 데이터」). 요소마다 기준 시각이 달라 한 시각으로 말할 수 없으면 `"-"` 를 주고, 각 요소(카드 머리 등)에 자기 시각을 적는다. 시각이 뜻이 없는 화면은 주지 않는다 |
| `cycle` | 갱신 주기 문구(「매일 자정 자동 갱신」). 기준 시각 앞 시계의 툴팁이 된다 |
| `refresh` | **하루 안에 값이 바뀌는 화면에만** 새로고침 함수를 준다. 하루 한 번 갱신되는 화면에 달면 눌러도 값이 그대로라 고장으로 읽힌다 |
| `actions` | 화면 고유 단추. 이름과 lucide 아이콘과 실행할 함수만 넘긴다. 모양은 셸이 정한다 |

## 알림 서랍

알림은 대시보드 전체 기능이다. 모든 페이지의 종이 같은 서랍을 연다. 서랍 안 내용은
`src/frontend/src/alerts.tsx` 한 곳에 적고, 종의 건수 배지는 그 파일에서 `useAlertCount(건수)` 로 알린다.
페이지마다 알림을 따로 만들지 않는다. 서랍 안에도 `designing-kiwoom-frontend` 의 색과 글자 크기를 쓴다. 서랍은
1.12배로 확대하지 않으므로 같은 px 가 내용 구획보다 조금 작게 보인다.

## 사람이 지키는 것

- 권한 설정은 배포하기 전에 AX 팀에 요청한다. 누가 어느 대시보드와 기능을 보는지는 AX 팀이 정한다.
- 메뉴에 붙인 기능마다 설명 문서를 repo 의 `docs/` 에 둔다. 형식은 PDF 나 Word 이고 PDF 를 권장한다. 파일
  이름은 API 와 같은 기능 이름으로 짓는다(`/api/kpi` → `docs/kpi.pdf`). 화면 목적 · 데이터 출처와 갱신 주기 ·
  지표 정의(계산식) · 문의처를 적는다. 화면을 고치면 문서도 고친다.
- 설명 문서는 사람이 쓴다. 에이전트는 데이터 출처나 문의처를 지어내지 않고, 문서가 없으면 없다고 알린다.

## 권장: 내용 구획

내용 구획의 색 · 글자 크기 · 아이콘 · 배치 · 쓰지 않는 장식과 목업 만드는 법은 `kw-design` 의
`designing-kiwoom-frontend` 스킬이 정한다. 화면을 그리기 전에 그 스킬을 읽는다.

- 대시보드에서는 그 기본 디자인을 따르기를 강하게 권장한다. 다르게 하려면 사람에게 이유를 확인하고 진행한다.
- **새로 만드는 화면**에 적용한다. 이미 만든 대시보드에서 옮겨 온 화면은 옛 모양대로 두고 옮기는 동안
  고치지 않는다.
- 셸이 내용 구획의 폭을 정하고 왼쪽에 붙인다. 페이지에서 `max-w-*` 로 상한을 줄 때 `mx-auto` 를 함께 쓰지 않는다.
  가운데로 옮기면 사이드바를 접거나 알림 서랍을 열 때마다 내용의 왼쪽 끝이 움직인다.
- 목업은 그 스킬의 대시보드 목업 템플릿으로 만들거나, 이 repo 를 실행해 보인다. 사이드바와 상태바를 HTML 로
  손수 그리지 않는다.

## 이미 만든 대시보드를 옮길 때

[migrating-existing-dashboard.md](migrating-existing-dashboard.md) 를 끝까지 읽고 옮긴다. 옛 값을 템플릿의 어디로
옮기는지와, 옮기다 끊기는 연결을 어떻게 잇는지가 그 파일에 있다.

옮길 때는 옛 대시보드가 이 스킬의 권장 규칙보다 앞선다. 기능 이름과 카테고리와 화면 안 모양은 옛 것 그대로
옮기고, 규칙과 상충하면 고치지 말고 사람에게 묻는다. 승인은 2번 받는다. 옮기기 시작하기 전에 주요 변경점을
목업으로 보여 주고 한 번, 옮기기가 끝난 뒤 공용 디자인을 적용할지 실제 화면 2개로 보여 주고 한 번이다.
화면을 두고 물을 때는 `designing-kiwoom-frontend` 의 「화면을 두고 물을 때」를 따른다.

## 내보내기 전 확인

브라우저 확인은 「새 대시보드 시작」의 「로컬에서 실행」대로 실행한 뒤 `http://localhost:3000` 에서 한다. 이 PC 에서 3000번을 다른
프로그램이 쓰고 있으면 화면 쪽이 3001번으로 올라가므로 콘솔에 찍힌 주소를 그대로 연다.
확인이 끝나면 사람이 볼 수 있게 그 주소를 브라우저로 열어 주고, 낮과 밤을 모두 보였는지 함께 적는다.

- [ ] `src/frontend` 에서 `npm test`(타입 검사와 테스트)가 통과한다
- [ ] 브라우저 개발자 도구의 Console 탭에 `[shell]` 경고와 오류가 없다
- [ ] `git diff --stat -- src/frontend/src/shell src/frontend/index.html` 이 비어 있다
- [ ] 낮과 밤에서 모두 보인다. 사이드바를 편 채 알림 서랍을 연 상태에서도 내용 구획이 깨지지 않는다
- [ ] 새로 만든 화면의 글자 크기가 `designing-kiwoom-frontend` 크기 표 안의 값이고, 색은 토큰 이름이다. 공용 디자인 적용을 승인받지 않았다면 옮겨 온 화면은 옛 모양 그대로다
- [ ] 새로 만든 화면에 `designing-kiwoom-frontend` 「쓰지 않는 장식」 의 장식이 없다. 사람이 요청한 장식은 예외다
- [ ] 화면이 없는 기능은 사람이 두겠다고 답한 것만 메뉴에 있고, 대표 기능 하나가 `path: '/'` 다
- [ ] `docs/` 에 새 기능의 설명 문서가 있다. 없으면 사람에게 알린다
