"""레포 화면을 기능마다 캡처하고, 캡처하지 못한 장면에 이유 문구를 정한다.

    python capture.py <capture_plan.json> --out <capture_result.json>
    python capture.py <capture_plan.json> --out <결과> --fail run|noscreen   # 브라우저 없이 모든 장면에 문구만 적는다
    python capture.py --check

캡처는 uv run --no-project --with playwright 로 실행하고, PC 에 설치된 Chrome 을 쓴다.
버튼은 계획의 allowClick 이 참이고 장면의 click 이 참일 때만 누른다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

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


def fail_result(plan_doc: dict, msg: str) -> dict:
    return {"features": {f["key"]: {"scenes": {s["id"]: {"unavailable": msg} for s in f["scenes"]}}
                         for f in plan_doc["features"]}}


def _target(page, target):
    if target.get("selector"):
        return page.locator(target["selector"]).first
    return page.get_by_text(target["text"]).first


def _locate(page, target):
    if not target:
        return None
    try:
        box = _target(page, target).bounding_box(timeout=3000)
    except Exception:
        return None  # 화면에서 찾지 못하면 사각형 없이 전체 화면으로 줌한다
    return [round(box["x"]), round(box["y"]), round(box["width"]), round(box["height"])] if box else None


def capture(plan_doc: dict) -> dict:
    from playwright.sync_api import sync_playwright  # uv run --no-project --with playwright 로 들어온다
    out_dir = Path(plan_doc["outDir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"features": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)  # PC 에 설치된 Chrome 을 쓰고 내려받지 않는다
        for f in plan_doc["features"]:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            seen = {}
            page.on("response", lambda r: seen.__setitem__(urlparse(r.url).path, r))
            try:
                # 대시보드는 주기적으로 요청을 보내 networkidle 에 닿지 않을 수 있어 load 뒤 3초를 기다린다
                doc = page.goto(plan_doc["baseUrl"] + f["path"], wait_until="load", timeout=30000)
                page.wait_for_timeout(3000)
            except Exception:
                doc = None
            doc_status = doc.status if doc else 0
            final_path = urlparse(page.url).path
            img = f"{f['key']}.png"
            page.screenshot(path=str(out_dir / img))
            fr = {"screenImg": f"screens/{img}", "scenes": {}}
            for s in f["scenes"]:
                api = s.get("dataApi") or {}
                status, body = None, None
                if api.get("path"):
                    r = seen.get(api["path"])
                    status = r.status if r else 0
                    try:
                        body = r.json() if r else None
                    except Exception:
                        body = None
                msg = judge(doc_status, final_path, status, body, api.get("listField"))
                if msg:
                    fr["scenes"][s["id"]] = {"unavailable": msg}
                    continue
                sr = {k: v for k, v in (("start", _locate(page, s.get("start"))), ("end", _locate(page, s.get("end")))) if v}
                if s.get("click") and plan_doc.get("allowClick") and s.get("start"):
                    try:
                        _target(page, s["start"]).click(timeout=5000)
                        page.wait_for_timeout(3000)
                        end_img = f"{s['id']}_end.png"
                        page.screenshot(path=str(out_dir / end_img))
                        sr["endImg"] = f"screens/{end_img}"
                        end = _locate(page, s.get("end"))
                        if end:
                            sr["end"] = end
                    except Exception:
                        pass  # 클릭이 실패하면 시작 화면 안의 결과 위치로 줌한다
                fr["scenes"][s["id"]] = sr
            result["features"][f["key"]] = fr
            page.close()
        browser.close()
    return result


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

    plan_doc = {"features": [{"key": "a", "scenes": [{"id": "a-0"}, {"id": "a-1"}]}]}
    res = fail_result(plan_doc, MSG_RUN)
    expect("실행 실패는 모든 장면에 같은 문구를 적는다",
           res == {"features": {"a": {"scenes": {"a-0": {"unavailable": MSG_RUN}, "a-1": {"unavailable": MSG_RUN}}}}})
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
    if not a.plan or not a.out:
        ap.error("캡처 계획 경로와 --out 이 필요합니다")
    plan_doc = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    if a.fail:
        res = fail_result(plan_doc, MSG_RUN if a.fail == "run" else MSG_NOSCREEN)
    else:
        res = capture(plan_doc)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
