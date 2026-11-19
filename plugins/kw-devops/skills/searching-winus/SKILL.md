---
name: searching-winus
description: 사내 운용 데이터(WINUS·위너스)를 조회하거나 그 데이터를 읽어 오는 코드를 쓸 때 언제나 먼저 연다. 펀드·순자산·수탁고·설정원본·기준가·가용자금·매매내역·벤치마크 대비 성과처럼 운용 데이터를 바로 물을 때, WINUS 화면 이름이나 화면 번호(FS852001 같은 번호)로 데이터를 찾을 때, 사용자가 가진 SQL을 DBGateway 등록 쿼리로 바꿀 때, "게이트웨이로 조회"·"쿼리 id로 요청"·"DBGateway 호출 코드"·"winus/query"·"이 SQL을 게이트웨이로 바꿔" 같은 말이 나올 때, DBGateway 접근 키(KIWOOM_ACCESS_KEY)가 없거나 거절될 때 연다. 데이터를 바꾸는 작업에는 쓰지 않는다.
---

# searching-winus

등록된 쿼리는 모두 조회라 이 스킬로는 데이터를 바꾸지 못한다. 인자를 요청 본문에 넣어 `POST`로 보내도 조회다. DBGateway는 쿼리 id로 등록된 SQL을 찾아 인자를 바인딩해 실행한다. 클로드는 쿼리를 고르려고 등록된 SQL을 읽을 수 있지만, 사용자 코드나 문서에는 SQL을 옮겨 적지 않고 쿼리 id로만 요청하게 한다. 여러 쿼리를 잇는 일(앞 결과를 뒤 인자로 넘기기)은 호출하는 쪽이 한다.

```
[클라이언트 코드] --POST /winus/query/{id} + 접근 키 + 본문의 인자--> [DBGateway] --등록된 SQL + 인자--> [WINUS]
```

## 매니페스트

요청할 수 있는 쿼리 목록이 매니페스트다. 목차와 쿼리별 상세 두 층이다.

```
python "${CLAUDE_SKILL_DIR}/scripts/fetch_manifest.py"
python "${CLAUDE_SKILL_DIR}/scripts/fetch_manifest.py" --query <id> [<id> …]
```

첫째 명령은 목차를 낸다. 목차는 표 두 개이고, 행마다 id·이름·화면·설명·사용 테이블을 싣는다.

- **승인 쿼리**: 무엇을 계산하는지 정해 둔 쿼리.
- **테이블 쿼리**: WINUS 테이블 하나를 가공하지 않고 그대로 읽는 쿼리. 종류(`WINUS`·`WFS`) 칸이 더 있고, 부를 때 받을 컬럼·조건·최대 행 수를 더할 수 있다.

화면은 그 쿼리가 쓰이는 시스템의 화면(시스템·화면 번호·화면 이름)이고, 화면을 등록하지 않은 쿼리는 비어 있다. 사용 테이블은 그 쿼리가 읽는 테이블·뷰·함수다. 설명은 무엇을 계산하는지 적고, 인자 값의 뜻과 결과의 단위까지 적은 것도 있다.

둘째 명령은 적은 id마다 이름·설명·사용 테이블·화면·인자·등록된 SQL을 낸다. 인자 줄은 인자 이름과 종류(`스칼라`·`목록`)이고, 등록 담당이 적어 둔 인자에는 형식(`형식 yyyymmdd`처럼)과 설명이 붙는다. 테이블 쿼리면 `기간` 줄(시작일·종료일 인자와 최대 일수)과 `출력 컬럼` 줄이 더 나온다.

- **매니페스트는 이 스크립트의 출력으로만 읽는다.** 등록된 SQL과 출력 컬럼은 `--query`로 고른 쿼리만 받는다.
- **상세에 `부를 수 없음` 줄이 있으면 그 쿼리를 부르지 않는다.** 등록이 잘못된 쿼리라 DBGateway가 보내기 전에 막는다. 그 줄을 그대로 사용자에게 알리고 AX팀에 등록 수정을 요청하라고 안내한다.
- **상세에 `SQL 해석` 줄이 있으면 DBGateway가 SQL을 끝까지 읽지 못한 것이다.** `구문 분석 실패`면 인자가 모두 `스칼라`로 나온다. 설명이 목록을 받는다고 적었는데 인자 줄에 `목록`이 없으면 그 차이를 사용자에게 알리고, 인자 줄을 따른다. `SELECT 아님`이면 부르지 않고 AX팀에 알리라고 안내한다.
- **첫 줄의 경고는 사용자에게 알리고 작업을 이어 간다.** 매니페스트가 최신이 아닐 수 있다는 뜻이다.

> DBGateway는 PoC(0.1.0)다. 이 문서에 적힌 것과 실제 응답이 다르면 맞춰 넘기지 말고 사용자에게 알린다.

## 접근 키

DBGateway는 요청마다 접근 키로 요청한 사람을 확인하고, 그 사람에게 허용된 쿼리만 목차에 넣고 실행한다. 접근 키는 `kwam_`으로 시작하는 개인 키이고, 이 PC의 환경 변수 `KIWOOM_ACCESS_KEY`에 둔다. `fetch_manifest.py`와 요청 코드는 그 키를 `Authorization: Bearer <키>` 헤더로 보낸다.

`fetch_manifest.py`가 `접근 키 없음`·`DBGateway 신원 거절(401)`·`접근 키는 설정됨`·`새 접근 키가 설정됨`으로 멈추면 [access-key.md](access-key.md)를 읽고 그 순서대로 한다. 키가 등록될 때까지 조회를 진행하지 않는다.

- **키 원문을 대화·코드·문서에 적지 않는다.** 사용자가 키를 대화에 붙여 넣으려 하면 멈추게 하고, 클로드도 키 값을 출력하는 명령을 실행하지 않는다. 키가 설정됐는지는 `fetch_manifest.py`를 실행해 확인한다.
- **여러 사람이 쓰는 서버나 배포한 서비스에는 개인 키를 설정하지 않는다.** 그 서비스의 모든 요청이 키 주인의 권한으로 처리된다. 그런 코드를 요청받으면 개인 키로 진행하지 말고, 이 제한과 함께 서비스가 어떤 신원으로 부를지 AX팀에 문의하라고 알린다.

## 작업 순서

1. **쿼리를 고른다.** 아래 「쿼리 고르기」대로 한다.
2. **앞 쿼리의 결과가 인자로 필요한지 본다.** 기준일이나 비교 날짜를 만드는 쿼리가 따로 있어서 대부분 이 단계에 해당한다. 아래 「인자 채우기」의 쿼리 연결 규칙을 따른다.
3. **사용자가 데이터를 물었으면 직접 조회해 답한다.** 아래 「바로 조회」대로 한다.
4. **사용자가 코드를 원하면 요청 코드를 쓴다.** 아래 「코드」의 `fetch_retrying`을 쓰고, 쿼리를 잇는 예와 거절 처리는 [client-code.md](client-code.md)를 따른다. 등록된 SQL은 코드에 옮겨 적지 않는다.
5. **결과를 쓸 때 설명의 단위와 0행의 뜻을 반영한다.** 억 원·백만 원·원 단위가 쿼리마다 다르고, "0행이면 …"처럼 0행에 뜻이 있는 쿼리도 있다. 설명에 단위나 0행의 뜻이 없으면 모른다고 알린다.

## 쿼리 고르기

1. **목차의 두 표에서 후보를 고른다.**
   - 사용자가 화면 번호나 화면 이름을 주었으면 화면 칸에서 찾고, 화면 칸이 빈 쿼리는 설명에서 찾는다. 한 화면에 쿼리가 여럿이면 그 화면의 어떤 데이터인지 사용자에게 한 번 묻는다.
   - 사용자가 SQL을 주었으면 그 SQL이 읽는 테이블·뷰·함수를 목차의 사용 테이블과 대조한다.
   - 집계·계산·여러 테이블 연결이 필요하면 승인 쿼리를, 한 테이블의 행을 그대로 받거나 컬럼·조건으로 줄여 받으면 되면 테이블 쿼리를 먼저 찾는다.
2. **후보의 SQL을 받아 확인한다.** `--query`로 후보의 등록된 SQL을 받아 결과 열·조건·집계·인자가 요청과 맞는지 본다. 사용자가 SQL을 주었으면 그 SQL과 비교한다. 후보는 가능성이 높은 순서로 하나씩, 최대 세 개까지 확인한다. 목차만 보고 맞는 쿼리가 없다고 결론 내지 않는다.
3. **맞는 쿼리가 있으면 그것으로 조회하거나 코드를 쓴다.** 사용자가 준 SQL과 결과 열·조건이 다른 점이 있으면 함께 적는다.
4. **맞는 쿼리가 없으면 등록 요청 여부를 묻는다.** 다른 후보 중에서 고르라고 하지 않는다. 그 데이터를 읽는 쿼리가 아직 없으니 AX팀에 쿼리 등록을 요청할지 묻는다. 요청하기로 하면 받은 SQL(없으면 필요한 데이터 설명)·필요한 결과 열·관련 테이블과 확인한 쿼리 id를 정리한다. 사용자는 그 정리를 AX팀 요청에 그대로 쓴다.

## 요청 형식

| 항목 | 값 |
|---|---|
| 주소 | `http://192.7.9.45:9101` (사내망). 코드에서는 환경 변수 `QUERY_GATEWAY_URL`로 받고 이 주소를 기본값으로 둔다 |
| 메서드·경로 | `POST /winus/query/{id}`. id는 목차의 정수. 기존 코드가 주소 뒤에 인자를 붙여 GET으로 부르면 이전 방식이니, 지금 동작하더라도 POST로 바꾼다 |
| 본문 | `{"args": {이름: 값}}`. 인자가 없는 쿼리는 `{}`를 보낸다. 테이블 쿼리는 `columns`·`where`·`limit`을 더할 수 있다([table-query.md](table-query.md)) |
| 인증 | 헤더 `Authorization: Bearer <접근 키>` |

```
POST /winus/query/2    {"args": {"dt": "20260911", "cut": "200000000"}}
POST /winus/query/10   {"args": {"cls": "GT002", "codes": ["001", "002"]}}
```

### 인자 채우기

- **키는 `인자` 줄의 이름과 정확히 같아야 한다.** 설명에 `:dt`로 적힌 인자의 키는 `dt`다. 빠지거나 모르는 키가 섞이면 400으로 거절되고, `detail`이 빠진 것·모르는 것·필요한 것을 알려 준다.
- **값은 문자열이나 문자열 배열로만 보낸다.** 날짜는 `"20260911"`, 코드는 `"001"`처럼 맨 앞 0을 살린 문자열로 만든다. 숫자·`null`·`true`는 422로 거절된다.
- **종류가 `목록`인 인자는 배열로 보낸다.** 값이 하나여도 `["001"]`처럼 보내고, 빈 배열은 거절된다. `스칼라`에 배열을 보내도 거절된다. 인자 줄에 최대 개수가 있으면 그보다 많은 값은 나눠 부른다.
- **인자에 형식과 설명이 붙어 있으면 그대로 따른다.** 형식은 값의 모양이다. `yyyymmdd`는 8자리 날짜, `fund_code`는 4자리 펀드코드이고, `code`면 무슨 코드인지와 값의 뜻을 설명이 알린다. 형식이 없는 인자는 목차의 설명 문장을 본다.
- **설명이 다른 쿼리의 결과를 넣으라고 하면 그 쿼리를 먼저 불러 받은 값을 넘긴다.** 「`:d1`에는 기준일_비교일자(id 1)의 전일 결과를 넣는다」 같은 문장이 그 표시다.
- **테이블 쿼리면 [table-query.md](table-query.md)를 읽은 뒤 부른다.** 상세에 `기간`이나 `출력 컬럼` 줄이 있는 쿼리다.

## 응답

성공하면 200과 함께 봉투가 온다.

```json
{"query_id": 7, "query_name": "기준일", "columns": ["기준일"], "rows": [{"기준일": "20260914"}],
 "truncated": false, "cached": true, "produced_at": "…T09:02:11+09:00", "source": {…}}
```

- **행은 `rows`에 있다.** 결과가 없으면 빈 목록이고, 0행의 뜻은 쿼리 설명을 따른다. `columns`는 열 이름을 결과 순서대로 담는다.
- **`cached`가 참이면 DBGateway가 저장해 둔 결과다.** 같은 쿼리를 같은 인자로 부르면 원본에서 받은 시각부터 10분 동안 그 결과로 답하고, 건너뛰는 옵션은 없다. `produced_at`은 원본이 결과를 낸 시각이다. 실시간 결과가 꼭 필요하다는 요청에는 AX팀에 그 쿼리의 예외를 요청하라고 안내한다.
- **결과가 3만 행을 넘으면 잘리지 않고 400으로 거절된다.** 범위 인자는 필요한 만큼만 쓰고, 넓으면 `detail`대로 기간이나 목록을 나눠 부른다.
- **행의 키는 SQL의 열 별칭이다.** 한글 별칭은 그대로, 영문 별칭은 대문자로 온다(`seq` → `SEQ`). 별칭이 없는 식은 식 자체가 키다(`COUNT(*)`).
- **값의 타입은 DB 열을 따른다.** 문자 열은 숫자처럼 보여도 `"10"`처럼 문자열로 오고 null도 올 수 있다. 숫자로 정렬하거나 계산하려면 변환하고 null을 처리한다.
- **응답 시간은 쿼리마다 다르다.** 타임아웃은 30초 이상으로 둔다.

**여러 번 부를 때는 순차로 보낸다.** DBGateway는 사람마다 대기 조회 수와 초당 요청 수를 제한하므로, 반복문을 스레드로 늘려 봐야 429만 늘어난다.

실패하면 `{"kind": "…", "code": "…", "detail": "…"}`가 온다. `detail`은 사용자에게 보일 문장이라 그대로 전한다.

- 401: 접근 키 문제. [access-key.md](access-key.md)의 순서를 안내한다.
- 400: 요청을 고쳐야 받는다. 같은 요청을 다시 보내지 않고 `detail`대로 고치거나 나눠 부른다.
- 422: 값이 문자열·문자열 배열이 아니다. 405: 이전 방식 GET으로 불렀다. 둘 다 위 「요청 형식」대로 고친다.
- 429·503: `fetch_retrying`이 정한 만큼만 다시 보낸다. 그래도 거절되면 `detail`과 할 일을 사용자에게 전한다.
- `code`별 뜻과 할 일은 [client-code.md](client-code.md)의 거절 표에 있다.

## 바로 조회

사용자가 코드가 아니라 데이터 자체를 물으면(예: 어제 기준 당사 ETF 순자산 상위 5개) 클로드가 직접 조회해 답한다.

- **답에는 데이터와 기준일·단위·결과 시각만 적는다.** 쿼리 id·SQL·열 이름은 사용자가 물을 때만 적는다. 단위가 설명에 없으면 모른다고 적는다. `cached`가 참이면 「N분 전(HH:MM) 결과」라고 적고, 여러 쿼리를 이어 부른 답이면 가장 이른 `produced_at`을 적는다. 잘린 결과(`truncated`)였으면 그것도 적는다.
- **아래 「코드」의 `fetch_retrying`을 쓴 스크립트 파일을 임시 폴더에 만들어 `uv run --with httpx <스크립트 파일>`로 실행하고, 답한 뒤 지운다.** 사용자의 작업 폴더에는 만들지 않는다. `uv`가 없으면 `python`에 `httpx`가 있을 때 `python <스크립트 파일>`로 실행하고, 둘 다 없으면 그 사실을 알린다.
- **스크립트 파일에 `# /// script` 의존성 블록을 넣지 않는다.** 그 블록이 있으면 uv가 서명 없는 자체 런처를 쓰고, 사내 PC의 V3가 그 런처를 차단한다.
- **스크립트 첫머리에서 `sys.stdout.reconfigure(encoding="utf-8")`를 호출한다.** Windows에서 출력이 파이프로 나가면 CP949로 쓰여 `−` 같은 문자에서 멈춘다.
- **PowerShell의 `Invoke-RestMethod`·`Invoke-WebRequest`와 `curl` 별칭을 쓰지 않는다.** 응답 헤더에 문자 인코딩이 없어 PowerShell 5가 한글을 깨뜨린다.

## 코드

```python
import os
import time

import httpx

GATEWAY_URL = os.environ.get("QUERY_GATEWAY_URL", "http://192.7.9.45:9101")
KEY_PAGE = "http://192.7.9.45:3000/#access-key"
# 키 원문은 코드에 적지 않고 환경 변수로만 받는다. 앞뒤 공백·줄바꿈이 섞이면 헤더가 깨지므로 지운다.
ACCESS_KEY = os.environ.get("KIWOOM_ACCESS_KEY", "").strip()
if not ACCESS_KEY:
    raise SystemExit(f"접근 키 없음: 환경 변수 KIWOOM_ACCESS_KEY. 설정했으면 창을 모두 닫고 다시 열기, 아니면 {KEY_PAGE} 에서 발급해 설정")

MAX_TRIES = 3
# 이보다 오래 기다려야 하면 다시 보내지 않는다.
MAX_WAIT_SECONDS = 10


class Refused(Exception):
    """DBGateway 의 400·429·503 거절. 무엇을 할지는 code 로 정하고, detail 은 사용자에게 그대로 전한다."""

    def __init__(self, query_id: int, status: int, body: dict, retry_after: str | None):
        super().__init__(f"쿼리 {query_id} {body.get('kind')}({status}, {body.get('code')}): {body.get('detail')}")
        self.status, self.kind, self.code = status, body.get("kind"), body.get("code")
        self.retry_after = float(retry_after) if retry_after else None


def fetch(query_id: int, args: dict[str, str | list[str]], **table) -> dict:
    """한 번 부른다. table 은 테이블 쿼리에만 주는 columns·where·limit 이다."""
    r = httpx.post(f"{GATEWAY_URL}/winus/query/{query_id}", json={"args": args, **table},
                   headers={"Authorization": f"Bearer {ACCESS_KEY}"}, timeout=30)
    if r.status_code == 401:
        raise PermissionError(f"DBGateway 신원 거절(401): {r.json()['detail']}. 새 키를 설정했으면 창을 모두 닫고 다시 열기, 아니면 {KEY_PAGE} 에서 재발급해 설정")
    if r.status_code == 422:
        names = sorted({e["loc"][2] for e in r.json()["detail"] if len(e["loc"]) > 2})
        raise ValueError(f"쿼리 {query_id} 형식 오류: 인자 {names}의 값이 문자열이나 문자열 배열이 아님")
    if r.status_code in (400, 429, 503):
        raise Refused(query_id, r.status_code, r.json(), r.headers.get("Retry-After"))
    r.raise_for_status()
    # 행과 함께 언제 결과인지(cached·produced_at), 잘렸는지(truncated)를 돌려준다. 답에 함께 적어야 한다.
    return r.json()


def wait_before_retry(e: Refused, tries: int) -> float | None:
    """거절 e 를 tries 번째로 받았을 때 다시 보내기 전에 기다릴 초. None 이면 다시 보내지 않고 거절을 그대로 올린다."""
    if e.status == 400 or e.code == "caller_stopped" or tries >= MAX_TRIES:
        return None
    if e.code == "source_time_exceeded":
        # 원본 사용 시간이 다시 찰 때까지는 늦춰 보내도 같은 답이다. 오래 걸리면 조용히 기다리지 않는다.
        return e.retry_after if e.retry_after and e.retry_after <= MAX_WAIT_SECONDS else None
    if e.kind == "판정 불능":
        return 5.0 if tries == 1 else None
    return e.retry_after or 5.0 * 2 ** (tries - 1)


def fetch_retrying(query_id: int, args: dict[str, str | list[str]], **table) -> dict:
    """혼잡 거절이면 wait_before_retry 가 정한 만큼 기다렸다 다시 보낸다. 그 밖의 거절은 그대로 올린다."""
    tries = 0
    while True:
        try:
            return fetch(query_id, args, **table)
        except Refused as e:
            tries += 1
            wait = wait_before_retry(e, tries)
            if wait is None:
                raise
            time.sleep(wait)


기준일 = fetch_retrying(7, {"오늘": "20260915"})["rows"][0]["기준일"]  # id 7 기준일: 실행일의 직전 영업일
```
