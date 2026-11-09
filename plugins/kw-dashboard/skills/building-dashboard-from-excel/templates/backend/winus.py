"""등록 쿼리를 번호로 한 번 호출한다. 실패해도 다시 호출하지 않는다."""
import os

import httpx

TIMEOUT = 60


class WinusStopped(RuntimeError):
    """쿼리가 끝나지 않았다(시간 초과 · 혼잡 · 응답 이상). 호출한 쪽은 작업을 멈춘다."""


class WinusRefused(RuntimeError):
    """접근 키가 거절됐다. 다시 올려도 풀리지 않는다."""


def fetch(query_id, args, *, timeout=TIMEOUT, client=None):
    """쿼리 결과의 행 목록. 값은 모두 글자로 보낸다."""
    own = client is None
    c = client or httpx.Client(base_url=os.environ["QUERY_GATEWAY_URL"], timeout=timeout,
                               headers={"Authorization": f"Bearer {os.environ['KIWOOM_ACCESS_KEY'].strip()}"})
    try:
        r = c.post(f"/winus/query/{query_id}", json={"args": args})
    except httpx.HTTPError as e:
        raise WinusStopped(f"쿼리 {query_id}: 연결 오류") from e
    finally:
        if own:
            c.close()
    if r.status_code in (401, 403):
        raise WinusRefused(f"쿼리 {query_id}: 권한 없음")
    if r.status_code != 200:
        raise WinusStopped(f"쿼리 {query_id}: 응답 {r.status_code}")
    body = r.json()
    if body.get("truncated"):
        raise WinusStopped(f"쿼리 {query_id}: 결과가 잘렸습니다")
    return body["rows"]
