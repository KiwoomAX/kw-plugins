"""레포 화면을 가짜 데이터로 띄워 기능마다 캡처한다. 백엔드는 실행하지 않는다.

    python capture.py <capture_plan.json> --out <capture_result.json>
    python capture.py <capture_plan.json> --out <결과> --fail front|noscreen   # 브라우저 없이 모든 장면에 문구만 적는다
    python capture.py --check

캡처는 uv run --no-project --with playwright 로 실행하고, PC 에 설치된 Chrome 을 쓴다.
화면이 보내는 요청은 모두 가로챈다. 화면 파일은 레포에서 읽고, API 는 계획의 가짜 데이터로 응답하며,
Node 개발 서버를 띄운 때만 나머지 같은 주소 요청을 그 서버로 넘긴다. 그 밖의 요청은 끊는다.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path
from urllib.parse import urlparse

MSG_FRONT = "화면 코드를 실행하지 못해 화면을 만들 수 없습니다."
MSG_NOSCREEN = "이 레포에는 화면 코드가 없어 화면을 만들 수 없습니다."
FAIL_MSG = {"front": MSG_FRONT, "noscreen": MSG_NOSCREEN}
STATIC_ORIGIN = "http://code-flow.local"  # 정적 화면은 서버 없이 이 가짜 주소로 연다


def _mock_match(mock: dict, method: str, path: str) -> bool:
    if mock.get("method", "GET").upper() not in ("*", method.upper()):
        return False
    return path.startswith(mock["path"]) if mock.get("prefix") else path == mock["path"]


def _mock_response(mock: dict) -> dict:
    if "json" in mock:
        body, ctype = json.dumps(mock["json"], ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8"
    else:
        body, ctype = str(mock.get("body", "")).encode("utf-8"), mock.get("contentType", "text/plain; charset=utf-8")
    return {"status": mock.get("status", 200), "body": body, "contentType": ctype}


def _static_file(static: dict, path: str) -> Path | None:
    root = Path(static["root"]).resolve()
    for r in static.get("routes", []):
        if "file" in r and path == r["path"]:
            target = (root / r["file"]).resolve()
        elif "dir" in r and path.startswith(r["prefix"]):
            target = (root / r["dir"] / path[len(r["prefix"]):]).resolve()
        else:
            continue
        # 레포 밖 파일(../)은 내주지 않는다
        if target.is_file() and root in target.parents:
            return target
        return None
    return None


def respond(url: str, method: str, plan_doc: dict, mocks: list[dict]) -> tuple:
    """요청 하나를 어떻게 처리할지 정한다. ("fulfill", 응답) · ("continue",) · ("abort",) 중 하나다."""
    u = urlparse(url)
    base = urlparse(plan_doc.get("baseUrl") or STATIC_ORIGIN)
    if (u.scheme, u.netloc) != (base.scheme, base.netloc):
        return ("abort",)  # 외부 서비스로 나가는 요청은 끊는다
    for m in mocks:
        if _mock_match(m, method, u.path):
            return ("fulfill", _mock_response(m))
    if plan_doc.get("static"):
        f = _static_file(plan_doc["static"], u.path)
        if f:
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            return ("fulfill", {"status": 200, "body": f.read_bytes(), "contentType": ctype})
        return ("fulfill", {"status": 404, "body": b"", "contentType": "text/plain"})
    return ("continue",)  # Node 개발 서버가 화면 파일을 내준다


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
    base = plan_doc.get("baseUrl") or STATIC_ORIGIN
    result = {"features": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)  # PC 에 설치된 Chrome 을 쓰고 내려받지 않는다
        for f in plan_doc["features"]:
            mocks = f.get("mocks", []) + plan_doc.get("mocks", [])  # 기능의 가짜 데이터가 공통 가짜 데이터보다 먼저다

            def handle(route, request):
                r = respond(request.url, request.method, plan_doc, mocks)
                if r[0] == "fulfill":
                    route.fulfill(status=r[1]["status"], body=r[1]["body"], content_type=r[1]["contentType"])
                elif r[0] == "continue":
                    route.continue_()
                else:
                    route.abort()

            def fresh():
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.route("**/*", handle)
                doc = page.goto(base + f["path"], wait_until="load", timeout=30000)
                page.wait_for_timeout(1500)
                return page, (doc.status if doc else 0)

            try:
                page, status = fresh()
            except Exception:
                status = 0
            if status >= 400 or status == 0:
                result["features"][f["key"]] = {"scenes": {s["id"]: {"unavailable": MSG_FRONT} for s in f["scenes"]}}
                continue
            img = f"{f['key']}.png"
            page.screenshot(path=str(out_dir / img))
            fr = {"screenImg": f"screens/{img}", "scenes": {}}
            for s in f["scenes"]:
                sr = {k: v for k, v in (("start", _locate(page, s.get("start"))), ("end", _locate(page, s.get("end")))) if v}
                if s.get("click") and s.get("start"):
                    # 앞 장면의 클릭이 남긴 상태를 지우려고 장면마다 화면을 새로 연다. 응답이 가짜라 눌러도 바깥에 아무 일도 없다
                    cp, _ = fresh()
                    try:
                        _target(cp, s["start"]).click(timeout=5000)
                        cp.wait_for_timeout(1500)
                        end_img = f"{s['id']}_end.png"
                        cp.screenshot(path=str(out_dir / end_img))
                        sr["endImg"] = f"screens/{end_img}"
                        end = _locate(cp, s.get("end"))
                        if end:
                            sr["end"] = end
                    except Exception:
                        pass  # 버튼을 찾지 못하면 시작 화면 안의 결과 위치로 줌한다
                    cp.close()
                fr["scenes"][s["id"]] = sr
            result["features"][f["key"]] = fr
            page.close()
        browser.close()
    return result


def fail_result(plan_doc: dict, msg: str) -> dict:
    return {"features": {f["key"]: {"scenes": {s["id"]: {"unavailable": msg} for s in f["scenes"]}}
                         for f in plan_doc["features"]}}


def _check() -> int:
    import tempfile
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(("PASS  " if cond else "FAIL  ") + label)
        ok = ok and cond

    with tempfile.TemporaryDirectory() as t:
        root = Path(t) / "repo"; (root / "src" / "web").mkdir(parents=True)
        (root / "src" / "web" / "index.html").write_text("<h1>보관함</h1>", encoding="utf-8")
        (root / "src" / "web" / "app.js").write_text("var a=1;", encoding="utf-8")
        (Path(t) / "secret.txt").write_text("비밀", encoding="utf-8")
        static_plan = {"static": {"root": str(root), "routes": [{"path": "/", "file": "src/web/index.html"},
                                                                 {"prefix": "/static/", "dir": "src/web"}]}}
        mocks = [{"method": "GET", "path": "/api/search", "json": {"rows": [{"subject": "예시 메일"}]}},
                 {"method": "GET", "path": "/body/", "prefix": True, "body": "<p>본문</p>", "contentType": "text/html; charset=utf-8"}]
        o = STATIC_ORIGIN
        r = respond(o + "/", "GET", static_plan, mocks)
        expect("정적 화면의 / 는 index.html 로 응답한다", r[0] == "fulfill" and r[1]["body"].decode("utf-8") == "<h1>보관함</h1>")
        r = respond(o + "/static/app.js", "GET", static_plan, mocks)
        expect("접두 경로는 폴더의 파일로 응답한다", r[0] == "fulfill" and r[1]["body"] == b"var a=1;" and "javascript" in r[1]["contentType"])
        r = respond(o + "/static/../../secret.txt", "GET", static_plan, mocks)
        expect("레포 밖 파일은 내주지 않는다", r[0] == "fulfill" and r[1]["status"] == 404)
        r = respond(o + "/api/search?q=견적", "GET", static_plan, mocks)
        expect("API 는 쿼리와 상관없이 가짜 데이터로 응답한다", r[0] == "fulfill" and json.loads(r[1]["body"]) == {"rows": [{"subject": "예시 메일"}]})
        r = respond(o + "/body/abc123", "GET", static_plan, mocks)
        expect("접두 가짜 응답은 하위 경로에도 쓴다", r[0] == "fulfill" and b"<p>" in r[1]["body"])
        r = respond(o + "/api/search", "POST", static_plan, mocks)
        expect("방식이 다른 요청은 가짜 데이터로 응답하지 않는다", r[0] == "fulfill" and r[1]["status"] == 404)
        expect("외부 서비스 요청은 끊는다", respond("https://fonts.googleapis.com/css", "GET", static_plan, mocks) == ("abort",))
        node_plan = {"baseUrl": "http://127.0.0.1:5173"}
        expect("Node 화면의 나머지 같은 주소 요청은 개발 서버로 넘긴다", respond("http://127.0.0.1:5173/src/main.tsx", "GET", node_plan, mocks) == ("continue",))
        r = respond("http://127.0.0.1:5173/api/search", "GET", node_plan, mocks)
        expect("Node 화면의 API 도 가짜 데이터로 응답한다", r[0] == "fulfill" and r[1]["status"] == 200)

    plan_doc = {"features": [{"key": "a", "scenes": [{"id": "a-0"}, {"id": "a-1"}]}]}
    expect("띄우지 못한 화면은 모든 장면에 같은 문구를 적는다",
           fail_result(plan_doc, MSG_FRONT) == {"features": {"a": {"scenes": {"a-0": {"unavailable": MSG_FRONT}, "a-1": {"unavailable": MSG_FRONT}}}}})
    return 0 if ok else 1


def main() -> int:
    # PYTHONUTF8=1 을 준 것과 같은 결과다. 그 값이 없는 윈도우 PC 에서도 한국어 출력이 깨지지 않는다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--fail", choices=sorted(FAIL_MSG))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return _check()
    if not a.plan or not a.out:
        ap.error("캡처 계획 경로와 --out 이 필요합니다")
    plan_doc = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    res = fail_result(plan_doc, FAIL_MSG[a.fail]) if a.fail else capture(plan_doc)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
