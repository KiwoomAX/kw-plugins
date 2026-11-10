---
name: designing-kiwoom-frontend
description: Use when drawing any Kiwoom in-house web screen or its mockup (a 본부 · 팀 dashboard page or a standalone in-house web feature), including mockups shown during brainstorming before any code exists, and when choosing colors, type sizes, icons, layout, or decoration for such a screen. Gives the default design (color tokens, type scale, icons, layout, decorations to avoid), a ready dashboard mockup HTML template, and the token file. Triggers on 사내 웹 화면·화면 목업·대시보드 디자인·기능 화면 디자인·색 토큰·글자 크기·화면 초안.
---

# designing-kiwoom-frontend

사내 웹 화면의 기본 디자인이다. 처음 초안을 만들 때 이 디자인을 기본값으로 쓴다.

| 화면 | 이 디자인의 힘 |
|---|---|
| 본부 · 팀 대시보드의 내용 구획 | 강한 권장. 다르게 하려면 사람에게 이유를 확인하고 진행한다 |
| 일반 사내 웹 기능 | 기본값. 사람이 다른 색이나 배치를 원하면 그대로 따른다 |

대시보드의 사이드바와 상태바는 셸 코드가 그리므로 이 스킬과 관계없다. 대시보드 작업 자체(메뉴 · 알림 서랍 ·
셸 규칙)는 `kw-dashboard` 의 `building-kiwoom-dashboard` 스킬이 맡는다.

## 목업 만들기

화면 코드를 쓰기 전에 목업을 먼저 만들어 사람에게 보인다. 목업은 HTML 파일 하나로 만든다. 첫 줄을
`<!doctype html>` 로 두면 더블클릭으로 열리고, brainstorming 의 목업 창에도 그 창의 테마로 감싸지지 않고 그대로 뜬다.

**대시보드 화면**은 [templates/dashboard-mockup.html](templates/dashboard-mockup.html) 을 복사해 만든다.
**사이드바와 상태바를 HTML 로 손수 그리지 않는다.** 손으로 옮기면 접기와 설정 판 같은 동작이 빠진다.

- 이 템플릿은 실제 셸 코드로 사이드바 · 상태바 · 알림 서랍을 그리고, 내용 구획만 비워 둔다.
- 고쳐도 되는 곳은 「목업 스타일」 과 「목업 내용」 표시 구간뿐이다. `mockup-config` JSON 에 조직 이름과 메뉴를
  적고, `<template data-path="…">` 하나에 화면 하나를 적는다. 적는 법은 파일 안 주석에 있다.
- 목업 스타일은 토큰 변수(`var(--bg-surface)` · `var(--text-secondary)` · `var(--border-light)` ·
  `var(--radius-md)` · `var(--accent)` 등)로 적고 선택자는 `.content` 아래로 묶는다. 목업은 Tailwind 를
  빌드하지 않으므로 Tailwind 클래스는 듣지 않는다.
- `<template>` 안의 `<script>` 는 실행되지 않는다. 목업은 모양을 정하는 데만 쓰고, 승인되면 실제 코드로 다시 만든다.
- 대시보드 repo 가 이미 있으면 그 repo 를 실행해 보이는 것도 된다. 셸이 실제 코드이므로 같은 결과다.

**일반 기능 화면**은 [templates/feature-mockup.html](templates/feature-mockup.html) 을 복사해 만든다. 이 템플릿은
토큰과 SUIT 서체를 파일 안에 포함하므로 HTML 파일 하나만 보내도 같은 모양으로 열린다. 파일 안의 서체와 토큰 구간은
읽거나 옮겨 적지 않는다. 고쳐도 되는 곳은 「목업 스타일」 과 「목업 내용」 표시 구간뿐이다.
사이드바와 상태바는 그리지 않는다. 이 목업도 Tailwind 를 빌드하지 않으므로 Tailwind 클래스는 듣지 않는다.
아래 「색」 표의 토큰 변수 열로 CSS 를 적는다. 나머지는 아래 규칙을 기본값으로 참고하면 된다.

예시 데이터를 쓰면 화면에 예시라고 적는다.

## 일반 기능 화면

일반 사내 웹 기능은 repo 이름과 구조를 자유롭게 정한다. 다만 나중에 대시보드에 페이지로 붙일 수 있게
아래를 지킨다.

- [templates/tokens.css](templates/tokens.css) 를 복사해 쓴다. Tailwind 를 쓰면 이 파일의 `@theme` 덕분에 아래
  「색」 의 이름(`bg-surface` 등)을 그대로 쓴다. Tailwind 를 쓰지 않으면 토큰 변수(`var(--bg-surface)`)로 쓴다.
- 사이드바와 상태바와 자체 머리글을 만들지 않는다. 내용만 그린다.
- `body` · `h1` · `table` 같은 태그 이름 규칙을 전역 CSS 에 적지 않는다. 대시보드에 붙이면 셸 모양까지 바뀐다.
- 서체는 SUIT 다. [templates/fonts/suit.css](templates/fonts/suit.css) 가 있는 `templates/fonts` 폴더를 복사해 `suit.css` 를 불러오고, 바탕 요소 하나에만
  `font-family: 'SUIT', 'Malgun Gothic', sans-serif` 를 준다. 화면마다 다시 주지 않는다. 폴더 안의 라이선스
  파일 `OFL.txt` 도 함께 복사한다.
- 내용 정렬은 화면마다 자유롭게 정한다. 제안값은 중앙 정렬(`mx-auto` · `margin: 0 auto`)이다. 폭 상한은 기능마다 정한다.
  대시보드에 붙이면 셸이 내용 폭을 정한다.
- 화면에서 부르는 API 는 `/api/<기능 이름>` 아래에 둔다. 대시보드에 붙일 때 주소를 바꾸지 않아도 된다.
- 대시보드에 붙이기 전에 그 대시보드에서 한 번 실행해 본다. 대시보드는 알림 서랍을 열면 내용 폭이 306px 좁아진다.

## 색

색은 아래 Tailwind 이름으로 쓴다. Tailwind 를 빌드하지 않는 HTML(목업 등)에서는 같은 줄의 토큰 변수를
`var(--bg-surface)` 처럼 쓴다. 값은 토큰이라 낮과 밤에 맞게 저절로 바뀐다.

| 쓰임 | Tailwind 이름 | 토큰 변수(Tailwind 없는 HTML) |
|---|---|---|
| 바탕과 면 | `bg-surface-app` · `bg-surface` · `bg-surface-sunken` · `bg-surface-hover` · `bg-surface-dialog` | `--bg-app` · `--bg-surface` · `--bg-sunken` · `--bg-hover` · `--bg-dialog` |
| 글자 | `text-on-surface` · `text-on-surface-variant` · `text-on-surface-tertiary` | `--text-primary` · `--text-secondary` · `--text-tertiary` |
| 선 | `border-outline` · `border-outline-strong` | `--border-light` · `--border-medium` |
| 내용 강조(칩 · 단추 · 막대) | `accent` · `on-accent` · `accent-weak` | `--accent` · `--on-accent` · `--accent-weak` |
| 셸 강조(사이드바 · 상태바) | `brand` · `on-brand` | `--brand` · `--on-brand` |
| 표 머리 | `bg-th` · `text-on-th` | `--th-bg` · `--th-ink` |
| 고른 행 | `bg-row-sel` | `--row-sel` |
| 상태(진행 중 · 확인 필요 · 마감 알림) | `status-ok` · `status-warn` · `status-bad` 와 각각의 `-weak`(옅은 면), 진한 면 `status-warn-fill` · `status-bad-fill`, 면 위 글자 `status-warn-ink` · `status-bad-ink`, 면 없는 안내문 글자 `status-warn-text` | `--ok` · `--warn` · `--bad` 와 각각의 `-weak`, `--warn-fill` · `--bad-fill`, `--warn-ink` · `--bad-ink`, `--warn-text` |
| 등락(상승은 붉은 계열 · 하락은 푸른 계열) | `rise` · `fall` · `rise-fill` · `fall-fill` · `rise-weak` · `fall-weak` | 같은 이름의 `--rise` · `--fall` 등 |
| 차트 | `chart-1`~`chart-4` · `chart-gray-1`~`chart-gray-3` · `grid` | `--chart-1`~`--chart-4` · `--chart-gray-1`~`--chart-gray-3` · `--grid-line` |
| 링크 · 포커스 · 비활성 | `text-link` · `outline-focus` · `text-disabled` | `--link` · `--focus` · `--disabled` |

- 색은 기본값을 그대로 쓴다. 차트 1순위가 남색이고 2순위가 청록이며 상승이 빨강이다. 어느 색으로 할지 먼저
  묻지 않는다.
- 옛 대시보드가 쓰던 키움 남색과 핑크는 토큰에 `-kiwoom` 이름으로 함께 들어 있다. 키움 색을 쓰고 싶다는 말이
  나오면 토큰 파일을 고치지 말고, 자기 CSS 파일에 아래 토막을 적어 이름 5개를 되가리킨다. 그러면 화면 코드는
  `chart-1` · `rise` 를 그대로 쓰면서 색만 바뀐다. 바뀌는 토큰은 차트 1·2순위와 상승색까지 5개뿐이다. 한 화면
  안에서 색감 2가지를 섞지 않는다.

  ```css
  :root,
  :root[data-theme="dark"] {
    --chart-1: var(--chart-1-kiwoom);
    --chart-2: var(--chart-2-kiwoom);
    --rise: var(--rise-kiwoom);
    --rise-fill: var(--rise-fill-kiwoom);
    --rise-weak: var(--rise-weak-kiwoom);
  }

  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --chart-1: var(--chart-1-kiwoom);
      --chart-2: var(--chart-2-kiwoom);
      --rise: var(--rise-kiwoom);
      --rise-fill: var(--rise-fill-kiwoom);
      --rise-weak: var(--rise-weak-kiwoom);
    }
  }
  ```

  선택자를 토큰 파일과 같은 모양으로 맞춘다. `:root[data-theme="dark"]` 가 `:root` 보다 점수가 높아, 평범한
  `:root` 한 블록만 적으면 낮만 바뀌고 밤에는 기본 색이 그대로 나온다.
- 셸 강조 `brand` 는 사이드바와 상태바만 쓰고 내용은 `accent` 를 쓴다. 둘을 바꿔 쓰지 않는다.
- 상태 3색은 뜻이 정해져 있다. `status-ok` 는 진행 중, `status-warn` 은 확인 필요, `status-bad` 는 마감 알림과
  실패다. 초록과 노랑은 쓰지 않는다. 흰 면에서 맑은 노랑은 대비가 2.2 까지 떨어지고, 초록은 대비가 낮 3.09,
  밤 10.2 로 테마에 따라 눈에 띄는 정도가 크게 달라진다.
- 확인이 필요한 것만 굵은 글씨에 면을 준다. 상태 표시의 면은 `-fill`, 그 위의 글자는 `-ink` 를 쓴다. `-weak` 는 이전 화면이 쓰던 옅은 면이며, 그 위에는 `status-warn` · `status-bad` 글자를 쓴다.
- 화면 폭으로 넓게 보이는 안내문(저장 실패 · 확인 요청 등)에는 면과 테두리와 밑줄을 쓰지 않는다. 반드시 처리해야 하는 안내(저장 실패 · 마감 · 권한 문제 등)는 `--bad` 색 아이콘과 `status-bad` 글자로, 알아 두면 좋은 안내(확인 요청 · 주의 등)는 `--warn` 색 아이콘과 `status-warn-text` 글자로 적는다. 아이콘은 lucide 경고 아이콘을 쓰고, 글자는 굵게, 폭은 글자 길이만큼 둔다.
- `status-warn-text` 는 흰 면 대비가 약 3.1 이라 굵은 안내문 글자에만 쓴다. 본문 크기의 보통 굵기 글자에는 쓰지 않는다.
- 링크는 `text-link` 색에 밑줄(`underline underline-offset-3`)을 둔다. 링크 색이 하락색 `fall` 과 같아서, 밑줄이 없으면 링크 걸린 숫자가 하락값처럼 보인다. 진행과 완료는 보통 굵기에 면 없이 글자만 둔다.
- 색은 과하지 않게 쓴다. 한 화면에 색감은 2가지를 권장하고, 화면에 필요하면 3가지를 넘겨도 된다. 차트 안의
  계열은 이 셈에서 빼고 아래 차트 규칙으로 센다.
- 겹치지 않는 차트(도넛 · 단일 막대)는 `chart-1` · `chart-2` 와 회색 3개만 쓴다. 색감이 3가지 이상 필요하면
  이 스킬이 값을 주지 않으므로 어떤 색을 쓸지 사람에게 묻는다.
- 겹치는 차트(꺾은선 여럿)는 `chart-4` 까지 쓴다. 4개를 넘으면 색을 더 만들지 않고 「기타」로 묶거나 차트를
  나눈다.
- 막대 위에 선을 겹쳐 그리는 차트에서 그 선은 `chart-2-over` 를 쓴다. 낮에는 2순위와 같은 값이고 밤에는
  흰색이라, 어두운 화면에서 선이 막대에 묻히지 않는다.
- 도넛을 `stroke-dasharray` 로 그릴 때 마지막 조각의 시작 위치와 길이의 합이 둘레를 넘으면 그 조각이 첫
  조각 위로 올라타 한 곳만 간격이 사라진다. 조각 길이는 비율에서 계산하고 조각마다 간격만큼 뺀다.
- 등락에 `status-ok` · `status-bad` 를 빌려 쓰지 않는다. 상태와 등락은 뜻이 다르다. 자금 유입과 유출은
  등락이므로 `rise` · `fall` 을 쓴다.
- 면 색은 투명도로 만들지 않고 고정값으로 둔다. 그래야 대비를 계산할 수 있다.
- `#333` 이나 `red-500` 같은 값을 직접 쓰지 않는다. 새 색이 필요하면 자기 CSS 파일에 토큰을 정의한다. 낮
  (`:root`), OS 설정의 밤(`@media (prefers-color-scheme: dark)` 안의 `:root:not([data-theme="light"])`),
  사용자가 고른 밤(`:root[data-theme="dark"]`) 3곳에 모두 적는다. 그다음 `@theme inline` 에
  `--color-<이름>` 으로 이름을 붙인다. 마지막으로 그 파일을 불러온다. 대시보드는 `src/frontend/src/index.css` 에
  `@import` 하고, 일반 기능은 Tailwind 를 불러오는 CSS 파일에서 `@import` 한다. 불러오지 않으면 Tailwind 가
  새 이름의 클래스를 만들지 않는다. 위의 키움 색 되가리키기 토막도 같은 방법으로 불러온다.

## 글자 크기

| 쓰임 | 크기 | 적는 법 |
|---|---|---|
| 큰 수치(지표 값) | 17px | `text-metric` · `var(--fs-metric)` |
| 본문 · 표 내용 · 카드 제목(굵게) | 14px | `text-body` · `var(--fs-body)` |
| 부제 · 보조 설명 · 표 머리 | 13px | `text-sub` · `var(--fs-sub)` |
| 라벨 | 12px | `text-label` · `var(--fs-label)` |
| 뱃지 · 각주 | 11px | `text-badge` · `var(--fs-badge)` |
| 부가 설명 | 10px | `text-note` · `var(--fs-note)` |

- 서체는 SUIT 이고 파일을 스킬과 대시보드 저장소에 함께 둔다. 대시보드는 셸이 정하므로 화면에서 `font-family` 를
  다시 주지 않는다. SUIT 에 없는 드문 한글은 맑은 고딕으로 그려진다. 굵기는 보통과 굵게 두 가지만 쓴다.
- 표에 없는 크기는 쓰지 않는다. 셸(사이드바 · 상태바 · 알림 배지)의 9px 와 15px 는 셸 전용 예외다. Tailwind 기본 크기 중 `text-base` · `text-lg` · `text-xl` · `text-2xl` 은 표에
  없는 크기다. 같은 쓰임은 화면이 달라도 같은 크기로 둔다.
- 표의 값은 CSS 에 적는 값이고 화면에도 그 크기로 보인다. 본문 14px 는 대시보드와 일반 기능 모두 14px 로 보인다.

## 간격과 그림자

- 여백과 간격은 `--sp-xs`(4) · `--sp-sm`(8) · `--sp-12`(12) · `--sp-md`(16) · `--sp-20`(20) · `--sp-lg`(24) · `--sp-xl`(32) 을 쓴다. Tailwind 에서는 `p-1` · `p-2` · `p-3` · `p-4` · `p-5` · `p-6` · `p-8` 이 같은 값이다.
- 그림자는 `--elev-sm` · `--elev-md` 두 가지만 쓴다. Tailwind 에서는 `shadow-sm` · `shadow-md` 다.

## 공용 컴포넌트

단추 · 입력칸 · 카드 · 대화상자는 새로 만들지 않고 공용 컴포넌트 `Button` · `Input` · `Card` · `Modal` 을 쓴다. 이 페이지 전용 단추를 만들지 않는다.

- 대시보드는 `src/frontend/src/shell/ui` 에서 불러온다. 셸 파일이므로 고치지 않는다.
- 일반 기능은 [templates/components/index.ts](templates/components/index.ts) 가 있는 `templates/components` 폴더를 `src/components/ui` 로 복사해 쓴다. 대시보드에 붙일 때 불러오는 주소를 `shell/ui` 로 바꾼다.
- 변형은 `variant`(`primary` · `outline` · `ghost`) 와 `size`(`md` · `sm`) 로 정한다. `primary` 는 상대에게 바로 나가는 동작에만 쓴다.
- 목업에서는 같은 모양의 클래스(`kw-btn kw-btn--outline kw-btn--md` · `kw-input` · `kw-card`)를 쓴다.
- 화면 컴포넌트에서 `fetch` 를 직접 호출하지 않는다. 데이터 호출은 기능 폴더의 별도 파일에 두고, 화면은 값과 상태를 props 로 받는다. 그래야 디자인을 바꿔도 데이터 호출 코드는 그대로다.

## 아이콘

- lucide-react 아이콘만 쓴다. 직접 그리지 않는다.
- 크기는 카드 머리 14 · 글자 옆 표시 12~13 · 증감 화살표 10 이다.
- 획 두께는 1.7 이다. 대시보드에서는 아이콘에 `className="ic"` 를 붙이면 셸 CSS 가 정하고, 일반 기능에서는
  `strokeWidth={1.7}` 을 넘긴다.

## 값이 없을 때와 숫자

값이 있을 때의 화면만 만들지 않는다. 아래 4가지 상태의 화면도 함께 만든다.

| 상태 | 어떻게 보이나 |
|---|---|
| 불러오는 중 | 그 구획의 크기를 유지하고 「불러오는 중입니다」를 보조 글자색 13px 로 적는다. 비워 두면 화면이 흔들린다 |
| 값이 없음 | 같은 구획에 「아직 값이 없습니다」를 보조 글자색 13px 로 적는다. 왜 없는지 아는 때는 한 줄로 덧붙인다 |
| 불러오지 못함 | 「색」의 넓은 안내문 중 반드시 처리해야 하는 안내 모양으로 적는다. 다시 받을 수 있으면 단추를 함께 둔다 |
| 권한이 없음 | 보조 글자색으로 적고 누구에게 물어야 하는지 함께 적는다 |

- 숫자는 자릿수 정렬(`tabular-nums`)로 둔다. 대시보드는 셸이 화면 전체에 적용하고 표에 `font-kerning: none` 도
  적용한다. 일반 기능은 바탕 요소에 `tabular-nums` 를 주고, 금액 열이 있는 표에 클래스로 `font-kerning: none` 을
  준다. SUIT 는 자릿수를 맞춘 숫자에도 1 뒤의 간격을 넓히는 조정이 있어, 끄지 않으면 표의 금액 끝이 어긋난다.
  표 요소가 아닌 그리드로 금액 열을 만들면 그 열에도 `font-kerning: none` 을 준다.

## 배치

- 데스크톱 전용이다. 대시보드는 창이 1008px 보다 좁아지면 가로 스크롤이 생긴다. 좁은 창에서 내용을 어떻게 둘지는 페이지가
  정한다.
- 레이아웃 폭을 고정 px(`w-[800px]`)로 묶지 않는다. 대시보드는 알림 서랍이 열리면 내용 구획이 306px
  좁아지고, 사이드바를 접으면 180px 넓어진다. 그리드 비율과 `minmax` 로 폭을 나눈다. 너무 넓어지지 않게
  `max-w-*` 로 상한을 두는 것은 괜찮다.
- 내용 정렬은 화면마다 자유롭게 정하고, 사람에게 이유를 확인하지 않는다. 제안값은 중앙 정렬이다. 대시보드는
  셸이 내용 구획을 제안값인 중앙에 두고, 페이지가 `DashboardLayout` 에 `contentAlign="left"` 나 `"right"` 를 넘겨
  위치를 바꾼다. 목업은 `<template data-align="left" …>` 처럼 적는다. 구획 안쪽 내용의 정렬도 페이지가 자유롭게 정한다.
- 모서리는 `rounded-sm`(6px)과 `rounded-md`(10px)를 쓴다. 표는 `rounded-table`(12px), 오른쪽 상세 패널은
  `rounded-panel`(18px)를 쓴다. 토큰 값으로 풀린다. Tailwind 를 빌드하지 않는 HTML 에서는 `var(--radius-md)` ·
  `var(--table-radius)` · `var(--panel-radius)` 처럼 쓴다.
- 모서리 반경과 테두리는 같은 요소에 준다. `rounded-md overflow-hidden` 상자 안에 테두리 있는 표를 넣으면
  모서리 4곳에서 선이 잘린다.
- 2개 이상의 화면이 같은 부품(카드 · 표 · 상태 점)을 쓰게 되면 한 곳으로 옮겨 같이 쓴다. 화면마다 다시 만들면
  크기와 여백이 화면끼리 달라진다.
- 「동작 줄이기」 설정을 받아 전환과 애니메이션을 끈다. 대시보드는 셸이 하므로 다시 적지 않는다.
- 눌러서 내용이 바뀌는 구획은 최소 높이를 두어 페이지 높이가 내용 길이로 변하지 않게 한다. 화면 자동 이동은
  0.7초 정도로 둔다.

## 표와 목록

- 목록 표는 바깥 카드로 감싸지 않고 표 자체를 상자로 쓴다. 모서리는 `rounded-table`(12px)다.
- 둥근 표의 첫 칸 왼쪽은 20px, 마지막 칸 오른쪽은 16px 여백을 둔다. 첫 글자가 둥근 모서리에 붙어 보이지 않게 한다.
- 탭이나 필터로 행이 바뀌는 표는 열마다 기본 폭을 두고, 제목 열만 남는 폭을 쓴다. 내용 길이로 폭을 계산하면
  탭을 바꿀 때 열 위치가 움직인다.
- 열 폭을 조절하게 할 때는 머리에 마우스를 올려 세로선을 보이고 끌어서 바꾼다. 새로고침하면 기본 폭으로 돌아간다.
- 처리가 끝난 행은 면을 바꾸지 않고 글자색을 한 단 낮춘다.
- 목록을 보는 범위는 표 위 탭으로 나누고 탭마다 건수를 적는다. 필터와 검색은 탭 줄 오른쪽에 둔다.

## 상세와 입력

- 상세는 페이지 이동이 기본이다. 여러 건을 이어서 처리하는 목록은 목록을 유지한 채 오른쪽 패널로 여는 방식을
  권장하며, 강제하지 않는다.
- 패널이 열려 표가 좁아지면 고르는 데 필요한 열만 남기고 나머지는 숨긴다.
- 패널은 X 아이콘, Esc, 같은 행 다시 누르기로 닫는다. 전체화면 아이콘은 X 왼쪽에 두고, 전체화면에서는 우상단
  X 만 둔다. 모서리는 `rounded-panel`(18px)다.
- 패널과 알림 서랍은 같은 오른쪽을 쓰므로 하나를 열면 다른 하나를 닫는다. 대시보드는 셸의 `useDrawer()` 로 서랍
  상태를 읽는다. 패널을 열 때 `open` 이 참이면 `toggle()` 로 서랍을 닫고, `open` 이 참으로 바뀌면 패널을 닫는다.
  셸 파일을 고치지 않는다.
- 상세를 전체 화면으로 열면 왼쪽 위 화살표로 돌아가고, 보던 목록 위치를 복원한다.
- 상세 화면에서 입력하는 항목에는 면을 두지 않고, 상대가 보낸 내용에만 면을 준다.
- 인용이나 관련 내용이 있을 때만 본문 위에 접어 두고, 펼치면 내용 전체를 보인다.
- 함께 고치는 항목은 스크롤과 무관하게 보이는 우하단 「저장」 하나로 저장하는 것이 기본이다. 사람이 항목별 저장을
  원하면 따른다.
- 상대에게 바로 나가는 동작만 강조 단추를 쓴다. 내부 저장은 테두리 단추로 낮춘다.
- 저장하지 않은 변경이 있으면 다른 건으로 옮기거나 닫기 전에 확인한다.

## 쓰지 않는 장식

AI 가 기본값으로 만드는 장식이다. 정보를 더하지 않고 화면을 만든 사람이 아무것도 고르지 않았다는 인상만
남긴다. 목록의 출처는 https://github.com/yetone/kill-ai-slop 이다.

이 목록은 스스로 고를 때의 기본값이다. 사람이 아래 장식을 직접 요청하면 한 번만 묻는다. 「AI 가 흔히 쓰는
디자인이라 규칙에서 지양하고 있습니다. 그래도 쓰시겠습니까?」 같은 대화에서 같은 장식은 다시 묻지 않는다.

- 쓰겠다고 하면 요청한 장식을 만들되 AI 기본값은 피한다. 그라데이션은 남색→보라 대신 토큰 색(`accent` ·
  `chart-1` 등)으로 만든다
- 이모지와 배지처럼 기본값과 다른 모양이 따로 없는 장식은 요청대로 만든다
- 쓰지 않겠다고 하면 장식 없이 만든다

- **왼쪽 세로 띠를 붙이지 않는다.** 카드 · 표의 행 · 안내문 · 알림 항목 어디에도 `border-left` 같은
  색 띠를 두지 않는다. 고른 행과 강조 카드와 안내문은 면 색과 글자색으로만
  나타낸다. 타임라인 선처럼 색 없는 회색 구분선은 이 항목에 해당하지 않는다.
- **꾸미는 그라데이션을 쓰지 않는다.** 남색→보라 그라데이션과 그라데이션 글자(`bg-clip-text`)를 쓰지 않는다.
  카드 면과 배경을 꾸미는 그라데이션도 쓰지 않는다. 차트 채움과 색 척도처럼 값을 보이는 그라데이션은 쓴다.
- **배경 장식을 두지 않는다.** 카드를 반투명 블러(`backdrop-blur`)로 만들지 않고, 배경에 흐린 원(blob)과
  줄무늬를 두지 않는다. 대화상자 뒤를 어둡게 덮는 층은 `--scrim` 을 쓰며 이 항목과 관계없다.
- **장식으로 이모지를 붙이지 않는다.** 제목 · 단추 · 목록 · 안내문에 🚀 ✨ 💡 같은 이모지를 두지 않고, AI 기능
  단추에도 ✨ 를 붙이지 않는다. 표시가 필요하면 lucide 아이콘을 쓴다. 화면이 붙이는 장식만
  해당하고, 데이터 속 이모지(사람이 입력한 글 등)는 그대로 보인다.
- **장식 배지를 쓰지 않는다.** 「New」 · 「Beta」 같은 배지를 두지 않는다. 배지는 건수처럼 실제 값을 보일 때만 쓴다.
- **상태 점에 후광과 깜빡임을 주지 않는다.** `animate-pulse` · `animate-ping` 을 쓰지 않고, 점 옆에 상태 글자를
  함께 적는다. 실제로 바뀌는 상태가 없으면 점을 두지 않는다. 수집 중처럼 지금 진행 중인 상태는 깜빡여도 된다.
- **아이콘을 같은 색의 옅은 상자에 넣지 않는다.** 아이콘 색을 옅게 칠한 둥근 사각형 위에 아이콘을 놓지 않는다.
  상자가 꼭 필요하면 `bg-surface-sunken` 같은 면 토큰을 쓴다.
- **마우스를 올렸을 때 크기를 키우지 않는다.** `hover:scale-*` 와 `transition-all` 을 쓰지 않고, 바꾸는
  속성(배경색 등)만 전환한다.
- **성격이 다른 지표를 같은 모양 카드로 늘어놓지 않는다.** 라벨을 영문 대문자로 쓰지 않는다. 팀별 성과처럼
  같은 종류의 지표는 같은 크기 카드로 늘어놓아도 된다.
- **지어낸 수치를 실제 값처럼 두지 않는다.** 예시 데이터를 쓰면 화면에 예시라고 적는다. 「10,000+」 · 「99.9%」
  같은 둥근 수치를 채워 넣지 않는다.

## 화면을 두고 물을 때

**보이는 것을 정해야 하면 브라우저로 띄워 눈으로 고르게 하는 것이 기본이다.** 글로만 묻지 않는다. 캡처 파일
이름이나 경로만 적지도 않는다. 사람이 파일을 찾아 여는 동안 무엇을 묻는지 잊는다.

- CSS 속성 이름과 값으로 묻지 않는다. `zoom` 을 얼마로 둘지, `minmax` 를 어떻게 잡을지, 몇 px 로 할지는
  사람이 고를 것이 아니다. 고를 것은 화면의 모습이고, 값은 고른 모습에 맞춰 만드는 쪽이 정한다
- 후보를 한 화면에 모아 탭으로 갈아 끼우게 만들어 연다. 창을 2개 열어 번갈아 보게 하지 않는다. 코드 상태가
  둘이어서 한 화면에 모을 수 없을 때만 예외다. 옮긴 대시보드에 공용 디자인을 적용할지 정하는 단계가 그렇다
- 낮과 밤을 함께 물을 때도 같은 화면에서 전환하게 한다
- 한 번에 하나만 바꾸고 나머지는 고정한다. 한 화면에서 2가지 이상이 함께 바뀌면 무엇 때문에 달라 보이는지
  구분할 수 없다
- 화면과 함께 지금 모습과 제안을 한 줄로 적는다. 화면만 띄우고 고르라고 하지 않는다
