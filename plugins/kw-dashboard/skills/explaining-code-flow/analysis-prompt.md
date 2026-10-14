# 기능 분석 지침

이 지침은 분석 서브에이전트가 기능 하나의 코드를 읽어 장면과 동작을 JSON 으로 돌려주는 방법을 정한다. 주 세션은 기능마다 서브에이전트 하나를 실행하고, 이 파일과 `tips-prompt.md` 의 경로와 맡을 기능 이름과 레포 경로를 프롬프트에 넣는다.

## 맡은 일

서브에이전트는 맡은 기능의 화면 코드에서 시작해 서버 · 저장소 · 외부 서비스까지 따라가며, 사용자가 버튼을 누른 뒤 자료가 어디로 오가는지를 장면과 동작으로 나눈다. 파일은 읽기만 하고 고치지 않는다. 장면마다 「알아 둘 점」은 `tips-prompt.md` 에 따라 함께 찾는다.

- 장면: 버튼 하나를 누른 뒤 화면이 바뀔 때까지의 흐름, 또는 사람이 누르지 않고 정해진 시각에 실행되는 흐름 하나
- 동작: 한 노드가 다른 노드로 무엇인가를 보내는 한 번의 이동

## 문장 규칙

읽는 사람은 바이브 코더이고 함수 이름과 API 개념을 모른다. 아래 규칙은 `say` · `title` · `text` · `tips` 에 모두 적용한다.

| 규칙 | 이유 |
|---|---|
| 함수 이름 대신 「누가 무엇을 어디에 보낸다」는 서술형으로 쓴다 | 바이브 코더는 함수 이름을 모른다 |
| 버튼 하나를 누른 뒤 일어나는 일을 장면으로 나누고, 화면 표기는 「홈」 메뉴 클릭처럼 버튼 이름으로 쓴다 | 「누를 곳으로 확대」 같은 표기는 어색하다 |
| 동시 처리 건수 제한 같은 내부 수치는 넣지 않는다 | 사용자가 알 필요가 없다 |
| 코드가 하지 않는 동작은 그리지 않고, 값을 하나씩 따로 가져오면 따로 그린다 | 정보를 한 묶음으로 모아 보내는 그림은 코드와 달라 거짓이 된다 |
| 예시 값은 「샘플 데이터」라고 밝힌다 | 실제 집계로 오해한다 |

문장은 「~합니다」체로 쓰고 긴 줄표를 쓰지 않는다.

## 고정 명칭표

노드의 `kind` 와 `zone` 은 아래 표의 값만 쓴다. 노드 이름(`name`)과 설명(`sub`)은 레포에 맞게 짓되, 표의 「노드 이름 예」가 맞으면 그 이름을 그대로 쓴다.

| kind | 템플릿 고정 라벨 | 노드 이름 예 |
|---|---|---|
| `screen` | 사람이 보는 화면 | 내 PC (브라우저) |
| `server` | 서버 · 프로그램 | 대시보드 서버 · ESG 서버 |
| `db` | 저장소 · DB | Redis 저장소 · AX팀 DB · WINUS |
| `ai` | AI 모델 | Claude · Gemini |
| `web` | 외부 사이트 | 크롤링 대상 사이트 이름 |
| `local` | 팀 공용폴더 | 팀 공용폴더 (Y: 드라이브) |
| `officepc` | 담당자 PC | 담당자 PC |
| `code` | 샘플 데이터 | 샘플 데이터 |
| `clock` | 정해진 시각 자동 실행 | 자동 실행 |

MDB · RDB · 파일 서버는 노드 하나로 묶어 「AX팀 DB」로 부른다.

| zone | 표시 이름 |
|---|---|
| `office` | 내 PC · 사무실 |
| `app` | 레포의 서비스(주 세션이 정한 `appZone`) |
| `ax` | AX팀 서버 |
| `winus` | WINUS (회사 DW) |
| `fund` | 우리펀드서비스 |
| `external` | 외부 서비스 |

구역 밖에 두는 노드만 `zone` 을 생략한다.

## 좌표

`x` · `y` 는 폭 960, 높이 520 무대에서 노드 중심의 좌표다. 왼쪽(`x` 110 부근)에는 `office` 노드를, 중간(`x` 360 ~ 600)에는 `app` · `ax` 노드를, 오른쪽(`x` 830 부근)에는 `external` 노드를 둔다. 같은 구역의 노드는 세로로 120 이상 띄워 겹치지 않게 한다.

## 화면 표기

장면의 `screen.startName` 은 사람이 누르는 버튼 이름(예: 「공고」 탭 클릭)이고, `screen.endName` 은 결과가 나타나는 곳의 이름(예: 공고 목록 표시)이다. 사람이 누르지 않는 장면(정해진 시각 자동 실행)은 `startName` 을 「자동 실행」으로 둔다.

## 캡처 계획

캡처는 백엔드를 실행하지 않고 화면 코드만 띄워, 화면이 보내는 요청에 가짜 데이터로 응답한 상태를 찍는다. `capture` 는 주 세션이 캡처 계획을 만드는 데 쓴다. `capture.scenes` 는 `feature.scenes` 와 같은 순서다.

- `path`: 이 기능 화면을 여는 주소의 경로(예: `/#notices`)
- `start` · `end`: 버튼과 결과 요소를 찾는 방법. 화면에 보이는 글자는 `{"text": "새로고침"}`, 글자가 없으면 `{"selector": "CSS 선택자"}` 로 적는다. 사람이 누르지 않는 장면은 `start` 를 생략한다.
- `click`: 결과 화면을 보려면 버튼을 눌러야 하는 장면만 `true` 로 둔다. 응답이 가짜라 눌러도 바깥에 아무 일도 일어나지 않는다. 탭 이동만으로 결과가 보이면 `false` 다.

## 가짜 데이터

`mocks` 에는 이 기능 화면이 보내는 요청마다 가짜 응답을 하나씩 적는다. 화면 코드에서 요청(`fetch` 등)을 찾고, 그 요청을 받는 백엔드 코드에서 응답 형태를 읽어 같은 형태로 만든다.

- `method` · `path`: 요청 방식과 경로. 쿼리는 적지 않는다. `/body/<id>` 처럼 뒤가 바뀌는 경로는 `"path": "/body/", "prefix": true` 로 적는다.
- `json`: JSON 응답의 본문. JSON 이 아닌 응답은 `body` 와 `contentType` 으로 적는다.
- 값: 실제 사람 이름 · 회사 메일 주소 · 고객 정보를 쓰지 않고 「홍길동」 · `user@example.com` · 「예시 회사」 같은 예시 값을 쓴다. 레포의 테스트나 샘플 파일에 실제처럼 보이는 값이 있어도 옮기지 않는다.
- 분량: 목록은 화면이 그럴듯해 보이도록 5개 안팎을 넣고, 화면이 쓰는 필드는 빠짐없이 채운다.
- 근거: `mockEvidence` 에 `"<method> <path>"` 마다 응답 형태를 읽은 `파일:줄` 을 적는다.

## 근거와 불일치

`evidence` 는 `"<장면 번호>.<동작 번호>"` 마다 근거 `파일:줄` 목록이다. 모든 동작에 근거가 있어야 하고, 근거를 찾지 못한 동작은 그리지 않는다.

`mismatches` 에는 주석과 동작이 다르거나 쓰이지 않는 경로처럼 코드와 설명이 다른 곳을 적는다. 고치지 않고 주 세션에 보고만 한다.

## 출력

JSON 하나만 돌려준다. 아래는 wholesale-dashboard 의 공고 기능을 줄인 예시다.

```json
{
  "feature": {
    "key": "notices", "name": "공고",
    "summary": "금융투자협회 게시판에서 운용사 선정 공고를 매일 모아 접수 현황을 보여 줍니다.",
    "nodes": [
      {"id": "pc", "name": "내 PC", "sub": "공고 탭", "kind": "screen", "zone": "office", "x": 110, "y": 170},
      {"id": "server", "name": "대시보드 서버", "sub": "공고 수집과 정리", "kind": "server", "zone": "app", "x": 360, "y": 260},
      {"id": "store", "name": "Redis 저장소", "sub": "공고 목록", "kind": "db", "zone": "app", "x": 590, "y": 440},
      {"id": "web", "name": "금융투자협회", "sub": "안내사항 게시판", "kind": "web", "zone": "external", "x": 830, "y": 80},
      {"id": "cron", "name": "자동 실행", "sub": "매일 한 번", "kind": "clock", "zone": "app", "x": 600, "y": 260}
    ],
    "scenes": [
      {"title": "매일 자동 수집 시작", "tips": [],
       "screen": {"startName": "자동 실행", "endName": "공고 목록에 반영"},
       "actions": [
         {"from": "cron", "to": "server", "icon": "ask", "text": "공고 수집 시작", "say": "매일 한 번 정해진 시각에 정기 실행이 서버에 공고 수집을 요청합니다."},
         {"from": "server", "to": "web", "icon": "ask", "text": "목록 2페이지까지", "say": "서버는 게시판 목록을 최대 2페이지까지 읽고, 지난번에 읽은 글을 만나면 멈춥니다."}]},
      {"title": "공고 탭을 열면 목록을 읽어 옵니다", "tips": [],
       "screen": {"startName": "「공고」 탭 클릭", "endName": "공고 목록 표시"},
       "actions": [
         {"from": "pc", "to": "server", "icon": "ask", "text": "공고 목록 요청", "say": "공고 탭을 열면 화면이 서버에 공고 목록을 요청합니다."},
         {"from": "server", "to": "store", "icon": "ask", "text": "저장된 공고", "say": "서버는 외부 사이트에 다시 접속하지 않고 저장소에 모아 둔 목록만 읽습니다."}]}
    ]
  },
  "capture": {
    "path": "/#notices",
    "scenes": [
      {"end": {"text": "공고 현황"}, "click": false},
      {"start": {"text": "공고"}, "end": {"text": "공고 현황"}, "click": false}
    ]
  },
  "mocks": [
    {"method": "GET", "path": "/api/notices",
     "json": {"notices": [{"id": "kofia-notice:1001", "sourceId": "kofia-notice", "url": "https://example.com/notice/1001",
                           "title": "예시 공제회 위탁운용사 선정 공고", "institution": "예시 공제회", "institutionKey": "예시공제회",
                           "postedAt": "<YYYY-MM-DD 날짜>", "category": "운용사선정", "applyPeriod": {"end": "<YYYY-MM-DD 날짜>"},
                           "needsReview": false, "requirementSummary": "수탁 200억 이상"}],
              "meta": {"fetchedAt": null, "lastSeqBySource": {}, "backfillPageBySource": {}, "failures": []}}}
  ],
  "mockEvidence": {"GET /api/notices": ["app/api/notices/route.ts:9-12", "lib/notice/types.ts:123-142", "lib/notice/types.ts:145-151"]},
  "evidence": {"0.0": ["vercel.json:2-5"], "0.1": ["app/api/cron/notices/route.ts:29-32"],
               "1.0": ["components/tabs/NoticeTab.tsx:21"], "1.1": ["app/api/notices/route.ts:9-10"]},
  "mismatches": []
}
```

「새로고침」 버튼처럼 눌러야 결과가 보이는 장면은 `click` 을 `true` 로 두고, 버튼이 보내는 요청(예: `POST /api/notices`)의 가짜 응답도 `mocks` 에 넣는다.

출력은 JSON 하나로 읽혀야 한다. 객체를 닫은 뒤에 다른 필드나 설명 문장을 붙이지 않는다.
