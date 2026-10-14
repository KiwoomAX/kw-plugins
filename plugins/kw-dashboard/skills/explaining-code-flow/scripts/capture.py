"""레포 화면을 기능마다 캡처하고, 캡처하지 못한 장면에 이유 문구를 정한다.

    python capture.py --check
"""
from __future__ import annotations

import argparse
import re
import sys

MSG_RUN = "이 PC 에서 레포를 실행하지 못해 화면을 만들 수 없습니다."
MSG_NOSCREEN = "이 레포에는 화면 코드가 없어 화면을 만들 수 없습니다."
MSG_AUTH = "접근 권한이 없어 화면을 만들 수 없습니다."
MSG_CONFIG = "실행에 필요한 설정이 없어 화면을 만들 수 없습니다."
MSG_DATA = "실행에 필요한 데이터가 없어 화면을 만들 수 없습니다."
LOGIN = re.compile(r"(login|signin|sso)", re.I)


def pick(body, dotted: str):
    for key in dotted.split("."):
        if not isinstance(body, dict):
            return None
        body = body.get(key)
    return body


def judge(doc_status, final_path, api_status, api_body, list_field):
    """위에서부터 처음 해당하는 조건의 문구를 돌려준다. 캡처해도 되면 None 이다.

    api_status 가 None 이면 그 장면에 데이터 API 가 없고, 0 이면 API 응답을 받지 못했다.
    """
    if doc_status in (401, 403) or LOGIN.search(final_path or ""):
        return MSG_AUTH
    if api_status is None:
        return None
    if api_status in (401, 403):
        return MSG_AUTH
    if api_status == 0 or api_status >= 500:
        return MSG_CONFIG
    if list_field:
        v = pick(api_body, list_field)
        if isinstance(v, list) and not v:
            return MSG_DATA
    return None


def _check() -> int:
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(("PASS  " if cond else "FAIL  ") + label)
        ok = ok and cond

    expect("정상 응답은 문구가 없다", judge(200, "/", 200, {"notices": [1]}, "notices") is None)
    expect("문서 요청 401 은 권한 문구", judge(401, "/", None, None, None) == MSG_AUTH)
    expect("로그인 화면 이동은 권한 문구", judge(200, "/auth/login", None, None, None) == MSG_AUTH)
    expect("데이터 API 403 은 권한 문구", judge(200, "/", 403, None, "notices") == MSG_AUTH)
    expect("로컬 전용 가드의 503 은 설정 문구", judge(200, "/", 503, {"error": "이 기능은 내 PC에서"}, None) == MSG_CONFIG)
    expect("API 를 부르지 않으면(0) 설정 문구", judge(200, "/", 0, None, "notices") == MSG_CONFIG)
    expect("객체 안의 빈 목록은 데이터 문구", judge(200, "/", 200, {"notices": [], "meta": {}}, "notices") == MSG_DATA)
    expect("점으로 이은 경로의 빈 목록도 데이터 문구", judge(200, "/", 200, {"data": {"items": []}}, "data.items") == MSG_DATA)
    expect("데이터 API 를 지정하지 않은 장면은 문구가 없다", judge(200, "/", None, None, None) is None)
    return 0 if ok else 1


def main() -> int:
    # PYTHONUTF8=1 을 준 것과 같은 결과다. 그 값이 없는 윈도우 PC 에서도 한국어 출력이 깨지지 않는다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--fail", choices=["run", "noscreen"])
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return _check()
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
