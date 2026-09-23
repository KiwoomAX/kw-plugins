---
name: building-kiwoom-dashboard
description: Use when working in a Kiwoom 본부 · 팀 dashboard repo made from KiwoomAX/dashboard-template — starting a new 본부 dashboard, adding a feature page or sidebar menu entry, filling the alert drawer, adding a backend API, or choosing colors, type sizes, icons, or layout in the content area. Also use when moving an existing dashboard (such as an old dash-kit HTML one) into the template, and when reviewing such a change before it ships. Triggers on 본부 대시보드·대시보드 기능 추가·사이드바 메뉴·알림 서랍·dashboard-template·dash-kit 이전·대시보드 규칙.
---

# building-kiwoom-dashboard

본부 · 팀 대시보드는 `KiwoomAX/dashboard-template` 레포를 복제해 만든다. 화면은 세 구획이다.

| 구획 | 누가 그리나 | 규칙 |
|---|---|---|
| 사이드바 | 셸 | 강제 |
| 상태바(오른쪽 위) | 셸. 페이지는 값만 넘긴다 | 강제 |
| 내용 구획(오른쪽 아래) | 페이지 | 권장 |

셸은 `src/frontend/src/shell/` 이다. 셸 사용법은 레포의 코드 주석과 타입과 콘솔 경고가 알려 준다.
이 스킬은 코드가 알려 주지 않는 것만 적는다.

## 강제 — 사이드바와 상태바

- **`src/frontend/src/shell/` 과 `index.html` 의 셸 스크립트를 고치지 않는다.** AX 팀은 셸을 고치면 이 폴더를
  통째로 덮어써서 내보내므로, 대시보드에서 고친 내용은 그때 사라진다. 셸에 바꿀 것이 있으면 AX 팀에 요청한다.
- **전역 CSS 에 태그 이름 규칙을 적지 않는다.** `h1 { … }` · `table { … }` · `body { … }` 같은 규칙은 사이드바와
  상태바 모양까지 바꾼다. 모양은 요소마다 Tailwind 클래스로 준다.
- **셸이 쓰는 클래스 이름을 내용 구획 CSS 에 다시 정의하지 않는다.** `.shell` · `.rail` · `.topbar` · `.side` ·
  `.nav-item` · `.content` 같은 이름이다. 겹치면 이름을 바꾼다.

## 새 대시보드 시작

1. GitHub 의 `KiwoomAX/dashboard-template` 에서 「Use this template」로 `KiwoomAX/<본부 영문 이름>-dashboard`
   비공개 레포를 만든다.
2. `src/frontend/src/dashboard.config.ts` 의 `org` 를 조직도에 적힌 이름 그대로 적는다. 이름이 「본부」로 끝나면
   사이드바 무리 이름이 「본부 기능」이 되고, 「팀」으로 끝나면 「팀 기능」이 된다.
3. `others` 에는 실제로 화면이 있는 다른 본부 대시보드만 적는다. 비어 있으면 본부 전환 목록을 달지 않는다.
4. 레포 폴더에서 `docker compose up -d --build` 로 실행하고 `http://localhost:3000` 을 연다. 사내망에서는 빌드하기
   전에 사내 인증서 번들(`kw_install` 이 사용자 환경변수 `SSL_CERT_FILE` 에 적어 둔 파일)을 `certs/ePrism.crt` 로
   복사해 둔다. 이 파일은 레포에 올리지 않는다.
5. 서버 배포는 `deploying-kiwoom-service` 스킬로 한다.

## 기능 붙이기

기능 하나는 페이지 하나와 메뉴 줄 하나다.

1. 페이지 컴포넌트를 만들고 내용을 `DashboardLayout` 으로 감싼다. 상태바에 보일 값은 이 컴포넌트의 props 로만
   넘긴다(아래 「상태바 값」).
2. `src/frontend/src/routes.tsx` 의 메뉴 목록에 줄을 추가한다. 줄 모양과 카테고리 규칙은 그 파일 주석에 있고,
   규칙을 어기면 브라우저 콘솔에 `[shell]` 경고가 나온다.
   **대표 기능 하나는 `path: '/'` 로 둔다.** 그 기능이 대시보드의 첫 화면이 된다. `/` 를 맡은 기능이 없으면
   주소 `/` 로 들어온 사람은 템플릿의 빈 첫 화면을 본다.
3. **화면이 아직 없는 기능은 메뉴에 넣지 않는다.** 화면이 생길 때 줄을 추가한다. `locked: true` 는 화면이 있는데
   권한이 없는 기능에만 쓴다. 툴팁이 「접근 권한이 없습니다」라서 화면이 없는 기능에 쓰면 뜻이 틀린다.
4. **카테고리 안 기능이 하나뿐이면 묶지 않고 낱개로 둔다.** 한 기능을 카테고리에 넣어 달라는 요청을 받으면
   낱개로 두고, 둘째 기능이 생길 때 묶는다고 알린다.
5. 기능 이름은 한글 13자 안쪽을 권장한다. 넘으면 두 줄로 접혀 그 줄만 키가 커진다.
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
페이지마다 알림을 따로 만들지 않는다. 서랍 안에도 아래 「권장 — 내용 구획」의 색과 글자 크기를 쓴다. 서랍은
1.12배로 확대하지 않으므로 같은 px 가 내용 구획보다 조금 작게 보인다.

## 사람이 지키는 것

- 사이드바 메뉴에 기능을 추가하려면 본부 승인이 있어야 한다.
- 권한 설정은 배포하기 전에 AX 팀에 요청한다. 누가 어느 대시보드와 기능을 보는지는 AX 팀이 정한다.
- 메뉴에 붙인 기능마다 설명 문서를 레포의 `docs/` 에 둔다. 형식은 PDF 나 Word 이고 PDF 를 권장한다. 파일
  이름은 API 와 같은 기능 이름으로 짓는다(`/api/kpi` → `docs/kpi.pdf`). 화면 목적 · 데이터 출처와 갱신 주기 ·
  지표 정의(계산식) · 문의처를 적는다. 화면을 고치면 문서도 고친다.
- 설명 문서는 사람이 쓴다. 에이전트는 데이터 출처나 문의처를 지어내지 않고, 문서가 없으면 없다고 알린다.

## 권장 — 내용 구획

아래는 **새로 만드는 화면**에 적용한다. 이미 만든 대시보드에서 옮겨 온 화면은 옛 모양대로 두고 옮기는 동안
고치지 않는다.

### 색

색은 아래 Tailwind 이름으로 쓴다. 값은 셸 토큰이라 낮과 밤에 맞게 저절로 바뀐다.

| 쓰임 | 이름 |
|---|---|
| 바탕과 면 | `bg-surface-app` · `bg-surface` · `bg-surface-sunken` · `bg-surface-hover` |
| 글자 | `text-on-surface` · `text-on-surface-variant` · `text-on-surface-tertiary` |
| 선 | `border-outline` · `border-outline-strong` |
| 상태(정상 · 지연 · 위험) | `status-ok` · `status-warn` · `status-bad` |
| 등락(상승은 붉은 계열 · 하락은 푸른 계열) | `rise` · `fall` |
| 차트 선과 격자 | `chart-1` · `grid` |
| 강조 | `brand` · `on-brand` |

- 색 계열은 상태 세 가지를 쓰기를 권장한다. 색이 보이면 뜻이 있어야 한다.
- 등락에 `status-ok` · `status-bad` 를 빌려 쓰지 않는다. 상태와 등락은 뜻이 다르다.
- `#333` 이나 `red-500` 같은 값을 직접 쓰지 않는다. 새 색이 필요하면 셸 밖에 자기 CSS 파일을 만들어 토큰을
  정의한다. 낮(`:root`), OS 설정의 밤(`@media (prefers-color-scheme: dark)` 안의 `:root:not([data-theme="light"])`),
  사용자가 고른 밤(`:root[data-theme="dark"]`) 세 곳에 모두 적는다. 그다음 `@theme inline` 에 `--color-<이름>` 으로
  이름을 붙이고, 그 파일을 `src/frontend/src/index.css` 에 `@import` 한다.

### 글자 크기

| 쓰임 | 크기 | 적는 법 |
|---|---|---|
| 큰 수치(지표 값) | 17px | `text-[17px]` |
| 본문 · 표 내용 · 카드 제목(굵게) | 14px | `text-[14px]` |
| 부제 · 보조 설명 | 13px | `text-[13px]` |
| 라벨 · 표 머리 | 12px | `text-[12px]` |
| 뱃지 · 각주 | 11px | `text-[11px]` |
| 부가 설명 | 10px | `text-[10px]` |

- 표에 없는 크기는 쓰지 않는다. Tailwind 기본 크기 가운데 `text-base` · `text-lg` · `text-xl` · `text-2xl` 은 표에
  없는 크기다. 같은 쓰임은 화면이 달라도 같은 크기로 둔다.
- 셸이 내용 구획을 1.12배로 확대한다. 표의 값은 CSS 에 적는 값이고 확대는 셸이 한다.

### 아이콘

- lucide-react 아이콘만 쓴다. 직접 그리지 않는다.
- 크기는 카드 머리 14 · 글자 옆 표시 12~13 · 증감 화살표 10 이다.
- 획 두께는 셸과 같게 `strokeWidth={1.7}` 을 넘긴다.

### 배치

- 데스크톱 전용이다. 창이 1120px 보다 좁아지면 가로 스크롤이 생긴다. 좁은 창에서 내용 구획을 어떻게 둘지는
  페이지가 정한다.
- 레이아웃 폭을 고정 px(`w-[800px]`)로 묶지 않는다. 알림 서랍이 열리면 내용 구획이 340px 좁아지고, 사이드바를
  접으면 200px 넓어진다. 그리드 비율과 `minmax` 로 폭을 나눈다. 너무 넓어지지 않게 `max-w-*` 로 상한을 두는 것은
  괜찮다. 내용 구획이 가장 좁은 상태는 사이드바를 편 채 알림 서랍을 연 상태다.
- 모서리는 `rounded-sm`(6px)과 `rounded-md`(10px)를 쓴다. 셸 토큰 값으로 풀린다.
- 둘 이상의 화면이 같은 부품(카드 · 표 · 상태 점)을 쓰게 되면 한 곳으로 옮겨 같이 쓴다. 화면마다 다시 만들면
  크기와 여백이 화면끼리 달라진다.

## 이미 만든 대시보드를 옮길 때

[moving-existing-dashboard.md](moving-existing-dashboard.md) 를 끝까지 읽고 옮긴다. 옛 값을 템플릿의 어디로
옮기는지와, 옮기다 끊기는 연결을 어떻게 잇는지가 그 파일에 있다.

옮길 때는 옛 대시보드가 이 스킬의 권장 규칙보다 앞선다. 기능 이름과 카테고리와 화면 안 모양은 옛 것 그대로
옮기고, 규칙과 상충하면 고치지 말고 사람에게 묻는다. 옮기기 시작하기 전에 주요 변경점을 목업으로 보여 주고
승인을 받는다.

## 내보내기 전 확인

브라우저 확인은 `docker compose up -d --build` 로 실행한 뒤 `http://localhost:3000` 에서 한다. 이 PC 에서 3000번을
다른 프로그램이 쓰고 있으면 `docker-compose.yml` 의 `3000:80` 에서 왼쪽 값을 잠시 바꿔 확인하고 되돌린다.

- [ ] `src/frontend` 에서 `npm test`(타입 검사와 테스트)가 통과한다
- [ ] 브라우저 개발자 도구의 Console 탭에 `[shell]` 경고와 오류가 없다
- [ ] `git diff --stat -- src/frontend/src/shell src/frontend/index.html` 이 비어 있다
- [ ] 낮과 밤에서 모두 보인다. 사이드바를 편 채 알림 서랍을 연 상태에서도 내용 구획이 깨지지 않는다
- [ ] 새로 만든 화면의 글자 크기가 표 안의 값이고, 색은 토큰 이름이다. 옮겨 온 화면은 옛 모양 그대로다
- [ ] 화면이 없는 기능이 메뉴에 없고, 대표 기능 하나가 `path: '/'` 다
- [ ] `docs/` 에 새 기능의 설명 문서가 있다. 없으면 사람에게 알린다
