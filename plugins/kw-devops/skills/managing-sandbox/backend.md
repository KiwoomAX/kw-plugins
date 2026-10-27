# 서비스 백엔드에서 샌드박스 호출하기

대시보드 같은 서비스의 백엔드가 샌드박스 표를 읽고 쓰는 코드의 규칙과 예시다. 서비스의 모든 요청은 개발자의 접근 키로 처리되므로, 코드를 쓰기 전에 SKILL.md 「서비스 백엔드」의 알릴 점을 먼저 개발자에게 알린다.

## 코드 규칙

- **서비스에 필요한 표와 동작만 여는 함수로 쓴다.** "리테일_월별판매 표에 행 덧붙이기"처럼 표와 동작이 정해진 함수를 둔다. 받은 요청을 그대로 `/sandbox/*` 로 넘기는 중계 코드는 쓰지 않는다. 그런 코드가 있으면 서비스를 쓰는 누구나 개발자 권한으로 아무 표나 지울 수 있다.
- **화면 입력을 표 이름이나 `where` 로 그대로 넘기지 않는다.** 화면에서 받은 값은 정해진 컬럼의 값으로만 쓴다.
- **삭제 함수는 꼭 필요할 때만 둔다.** 행을 고쳐야 하면 `upsert` 나 조건이 정해진 `update` 로 쓴다. 한 기간분을 원본에서 다시 받아 통째로 올리려면 `rows/overwrite` 를 쓰되, 범위(`where`)는 함수 안에서 정하고 `"all": true` 는 쓰지 않는다. 보내지 않은 컬럼은 비워지므로 모든 컬럼을 보낸다.
- **화면별 접근을 서비스가 먼저 나눈다.** DBGateway 는 키 주인만 확인하므로, 화면을 누가 쓰는지는 서비스가 판정해야 한다. 쓰기 함수를 넣기 전에 그 서비스에 화면별 접근을 나누는 장치가 있는지 확인하고, 없으면 그 장치를 먼저 둔다.
- **키를 넣은 파일은 체크포인트에 넣지 않고, 요청 헤더는 기록에 남기지 않는다.**
- **`write_outcome_unknown`·`sandbox_undecided` 를 받으면 같은 요청을 다시 보내지 않는다.** 반영됐는지 모르는 상태이므로 조회로 확인한다.

## 예시

searching-winus 의 코드 예시처럼 `httpx` 를 쓴다. 서비스의 의존성 파일(`pyproject.toml` 의 `dependencies`)에 `httpx` 를 추가한다.

```python
import os

import httpx

GATEWAY_URL = os.environ.get("QUERY_GATEWAY_URL", "http://192.7.9.45:9101")
# 키 원문은 코드에 적지 않고 환경 변수로만 받는다. 앞뒤 공백·줄바꿈이 섞이면 헤더가 깨지므로 지운다.
ACCESS_KEY = os.environ.get("KIWOOM_ACCESS_KEY", "").strip()
if not ACCESS_KEY:
    raise SystemExit("접근 키 없음: 서버 환경 변수 KIWOOM_ACCESS_KEY")

SCHEMA, TABLE = "BS", "리테일_월별판매"


class SandboxRefused(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def _post(path: str, body: dict) -> dict:
    r = httpx.post(f"{GATEWAY_URL}/sandbox/{path}", json=body,
                   headers={"Authorization": f"Bearer {ACCESS_KEY}"}, timeout=30)
    if r.status_code == 200:
        return r.json()
    try:
        refusal = r.json()
    except ValueError:
        r.raise_for_status()
    if refusal.get("code") in ("write_outcome_unknown", "sandbox_undecided"):
        # 반영 여부를 모른다. 다시 보내면 같은 행이 두 번 들어갈 수 있다.
        raise SandboxRefused(refusal["code"], "반영 여부 모름: 다시 보내지 말고 조회로 확인")
    raise SandboxRefused(refusal.get("code", f"http_{r.status_code}"), str(refusal.get("detail")))


def add_monthly_sales(rows: list[dict]) -> int:
    """리테일_월별판매 표에 행을 덧붙인다. 이 서비스가 여는 쓰기는 이 함수 하나다."""
    return _post("rows/insert", {"schema": SCHEMA, "table": TABLE, "rows": rows, "mode": "append"})["row_count"]


def monthly_sales(since: str) -> list[dict]:
    """since(YYYYMM) 이후의 월별 판매. 결과의 소수와 날짜는 문자열이다."""
    page = _post("rows/select", {"schema": SCHEMA, "table": TABLE,
                                 "where": {"기준월": {">=": since}},
                                 "order_by": [{"column": "기준월"}, {"column": "상품코드"}], "limit": 1000})
    return [dict(zip(page["columns"], row)) for row in page["rows"]]
```

- `async def` 안에서는 `httpx.AsyncClient` 를 쓰고 앱이 끝날 때 닫는다. 동기 호출은 이벤트 루프를 차단한다.
- 결과가 1,000행을 넘으면 응답의 `truncated` 가 참이다. 그때는 `order_by` 를 그대로 두고 `offset` 을 늘려 다음 페이지를 받는다. `order_by` 에는 primary key 컬럼을 끝에 넣어 행의 순서가 하나로 정해지게 한다. 같은 값이 있는 컬럼으로만 정렬하면 페이지 사이에 행이 겹치거나 빠진다.
- 표의 컬럼과 primary key 는 `POST /sandbox/table/describe` 로 확인한다.
