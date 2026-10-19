"""레포 화면을 가짜 데이터로 띄워 기능마다 캡처한다. 백엔드는 실행하지 않는다.

    python capture.py <capture_plan.json> --out <capture_result.json>
    python capture.py <capture_plan.json> --out <결과> --fail front|noscreen   # 브라우저 없이 모든 장면에 문구만 적는다
    python capture.py --check

캡처는 uv run --no-project --with playwright 로 실행하고, PC 에 설치된 Chrome 을 쓴다.
장면의 steps(동작 목록, 동작 종류는 STEP_FIELDS)를 차례로 실행하고 결과 화면을 찍는다. 예전 형식의 click 은 클릭 동작 하나로 본다.
화면이 보내는 요청은 모두 가로챈다. 화면 파일은 레포에서 읽고, API 는 계획의 가짜 데이터로 응답하며,
Node 개발 서버를 띄운 때만 나머지 같은 주소 요청을 그 서버로 넘긴다. 그 밖의 요청은 끊는다.
"""
from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MSG_FRONT = "화면 코드를 실행하지 못해 화면을 만들 수 없습니다."
MSG_NOSCREEN = "이 레포에는 화면 코드가 없어 화면을 만들 수 없습니다."
MSG_STEP = "이 장면의 동작을 화면에서 따라 하지 못해 화면을 만들 수 없습니다."
FAIL_MSG = {"front": MSG_FRONT, "noscreen": MSG_NOSCREEN}
STATIC_ORIGIN = "http://code-flow.local"  # 정적 화면은 서버 없이 이 가짜 주소로 연다


def _mock_match(mock: dict, method: str, path: str, query: dict) -> bool:
    if mock.get("method", "GET").upper() not in ("*", method.upper()):
        return False
    if not (path.startswith(mock["path"]) if mock.get("prefix") else path == mock["path"]):
        return False
    # query 가 있는 가짜 응답은 그 값이 모두 요청에 있을 때만 맞는다(예: 검색어 「견적」)
    return all(str(v) in query.get(k, []) for k, v in (mock.get("query") or {}).items())


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
    query = parse_qs(u.query)
    # 조건이 있는 가짜 응답을 먼저 맞춘다. 그래야 검색어가 든 요청과 처음 목록 요청이 서로 다른 응답을 받는다
    for m in sorted(mocks, key=lambda m: not m.get("query")):
        if _mock_match(m, method, u.path, query):
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


def scene_steps(scene: dict) -> list[dict]:
    """장면의 사용자 동작 목록. 예전 형식(click 과 start)은 클릭 동작 하나로 바꾼다."""
    if scene.get("steps"):
        return scene["steps"]
    if scene.get("click") and scene.get("start"):
        return [{"action": "click", "target": scene["start"]}]
    return []


def split_steps(steps: list[dict]) -> tuple[list[dict], list[dict]]:
    """준비 동작(setup)과 장면 자신의 동작을 나눈다. 준비 동작은 공통 입력처럼 장면으로 보이지 않는 동작이다."""
    return [st for st in steps if st.get("setup")], [st for st in steps if not st.get("setup")]


# 동작마다 꼭 있어야 하는 칸이다. drag 는 이 밖에 to(놓을 대상) 나 by([가로, 세로] 이동량) 중 하나가 있어야 한다
STEP_FIELDS = {
    "type": ("target", "text"), "click": ("target",), "select": ("target", "value"), "wait": ("ms",),
    "rightclick": ("target",), "dblclick": ("target",), "hover": ("target",), "scroll": ("target",),
    "press": ("key",), "paste": ("target", "text"), "upload": ("target", "file"), "drag": ("target",),
}

# 브라우저의 붙여넣기 이벤트를 그 칸에 보낸다. 클립보드 권한 없이 엑셀에서 복사한 글을 붙여넣은 것과 같은 이벤트가 간다
_PASTE = """(el, text) => { el.focus(); const dt = new DataTransfer(); dt.setData('text/plain', text);
  el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); }"""


def plan_errors(plan_doc: dict) -> list[str]:
    errs = []
    for f in plan_doc.get("features", []):
        for s in f.get("scenes", []):
            for i, st in enumerate(scene_steps(s)):
                where = f"{s.get('id')} 동작 {i}"
                need = STEP_FIELDS.get(st.get("action"))
                if need is None:
                    errs.append(f"{where}: {st.get('action')!r} 는 없는 동작입니다({' · '.join(STEP_FIELDS)})")
                    continue
                errs += [f"{where}: {st['action']} 에 {k} 가 없습니다" for k in need if k not in st]
                if st["action"] == "drag" and "to" not in st and "by" not in st:
                    errs.append(f"{where}: drag 에 to 나 by 가 없습니다")
                if st["action"] == "upload" and not (isinstance(st.get("file"), dict) and st["file"].get("name")):
                    errs.append(f"{where}: upload 의 file 은 {{\"name\": …, \"text\": …}} 형태여야 합니다")
    ids = {s.get("id") for f in plan_doc.get("features", []) for s in f.get("scenes", [])}
    for t in plan_doc.get("tour", []):
        if t.get("scene") not in ids:
            errs.append(f"둘러보기 {t.get('key')}: 장면 {t.get('scene')!r} 가 계획에 없습니다")
        for i, a in enumerate(t.get("areas", [])):
            if not all(isinstance(x, dict) for x in area_targets(a)) or not a.get("target"):
                errs.append(f"둘러보기 {t.get('key')} 항목 {i}: target 이 없습니다")
    return errs


def _run(page, steps, part, after=None):
    for i, st in enumerate(steps):
        try:
            _step(page, st)
        except Exception as e:  # 어느 동작에서 멈췄는지 결과에 남겨, 계획의 대상을 고칠 수 있게 한다
            first = (str(e).strip().splitlines() or [""])[0][:160]
            raise RuntimeError(f"{part} 동작 {i + 1}번째({st['action']})에서 멈췄습니다: {first}") from e
        if after:
            after(i, st)


def frame_points(own: list[dict]) -> list[int]:
    """동작 이미지를 찍을 동작의 위치. 사람 동작(기다리기가 아닌 동작) 중 마지막을 뺀다. 마지막 동작 뒤 화면은 결과 화면이다."""
    return [i for i, st in enumerate(own) if st["action"] != "wait"][:-1]


def select_scenes(plan_doc: dict, ids: list[str]) -> dict:
    """고른 장면만 남긴 캡처 계획. 장면 · 화면 대조에서 고친 장면만 다시 캡처할 때 쓴다."""
    want = set(ids)
    out = copy.deepcopy(plan_doc)
    out["features"] = [dict(f, scenes=[s for s in f["scenes"] if s["id"] in want]) for f in out["features"]]
    out["features"] = [f for f in out["features"] if f["scenes"]]
    out["tour"] = [t for t in out.get("tour", []) if t["scene"] in want]
    return out


def _step(page, st):
    a, t = st["action"], st.get("target")
    if a == "wait":  # 화면이 정해 둔 지연 뒤에 바뀌는 장면(예: 완료 1.5초 뒤 창 열기)
        page.wait_for_timeout(st["ms"])
        return
    if a == "press" and not t:  # 대상 없이 누르는 키는 화면 전체에 보낸다(예: Escape 로 창 닫기)
        page.keyboard.press(st["key"])
        page.wait_for_timeout(1500)
        return
    el = _target(page, t)
    if a == "type":
        el.fill(st["text"], timeout=5000)
    elif a == "select":  # 목록에서 고르는 칸(select)은 입력으로 채울 수 없다
        el.select_option(st["value"], timeout=5000)
    elif a == "rightclick":
        el.click(button="right", timeout=5000)
    elif a == "dblclick":
        el.dblclick(timeout=5000)
    elif a == "hover":  # 마우스를 올려야 나타나는 단추 · 팝업
        el.hover(timeout=5000)
    elif a == "scroll":
        el.scroll_into_view_if_needed(timeout=5000)
    elif a == "press":
        el.press(st["key"], timeout=5000)
    elif a == "paste":
        el.evaluate(_PASTE, st["text"])
    elif a == "upload":  # 숨은 파일 칸에도 가짜 파일을 넣는다. 파일을 끌어 놓는 칸도 대개 이 칸으로 받는다
        name = st["file"]["name"]
        el.set_input_files({"name": name, "mimeType": mimetypes.guess_type(name)[0] or "application/octet-stream",
                            "buffer": st["file"].get("text", "").encode("utf-8")}, timeout=5000)
    elif a == "drag":
        if "to" in st:
            el.drag_to(_target(page, st["to"]), timeout=5000)
        else:
            box = el.bounding_box(timeout=5000)
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x + st["by"][0], y + st["by"][1], steps=12)
            page.mouse.up()
    else:
        el.click(timeout=5000)
    page.wait_for_timeout(1500)


# 요소의 가운데 점에서 실제로 보이는 맨 위 요소가 그 요소이거나 그 안의 요소일 때만 보이는 요소로 친다.
# 크기만 있고 투명하거나 다른 창에 가려진 요소(자동 높이용 숨은 textarea, 사라진 알림)를 고르지 않으려는 검사다
_SEEN = """el => { const r = el.getBoundingClientRect(); if (!r.width || !r.height) return false;
  if (getComputedStyle(el).opacity === '0') return false;
  const t = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
  return !!t && (t === el || el.contains(t) || t.contains(el)); }"""


def _candidates(page, target):
    if target.get("selector"):
        return [page.locator(target["selector"])]
    # 글자는 정확히 같은 요소를 먼저 찾고, 없으면 그 글자가 든 요소를 찾는다
    return [page.get_by_text(target["text"], exact=True), page.get_by_text(target["text"])]


def _target(page, target):
    groups = _candidates(page, target)
    for loc in groups:
        for el in loc.all()[:20]:
            try:
                if el.evaluate(_SEEN):
                    return el
            except Exception:
                continue
    return groups[-1].first  # 보이는 후보가 없으면 예전처럼 첫 요소를 쓴다(누르기는 Playwright 가 기다렸다 실패를 알린다)


def _locate(page, target):
    if not target:
        return None
    try:
        box = _target(page, target).bounding_box(timeout=3000)
    except Exception:
        return None  # 화면에서 찾지 못하면 사각형 없이 전체 화면으로 줌한다
    return [round(box["x"]), round(box["y"]), round(box["width"]), round(box["height"])] if box else None


def _locate_end(page, target):
    """끝 대상의 위치. 후보가 둘 이상 보이면 엉뚱한 칸을 확대하지 않도록 찾지 못함으로 둔다."""
    return _locate_one(page, target) if target else None


MSG_TOUR = "둘러보기 화면을 캡처하지 못했습니다."


def pick_unique(seen: list[bool], first: bool = False) -> int | None:
    """보이는 후보 중 하나를 고른다. 둘러보기 번호가 엉뚱한 칸에 찍히지 않도록 후보가 둘 이상이면 고르지 않는다."""
    idx = [i for i, v in enumerate(seen) if v]
    if not idx:
        return None
    if first:
        return idx[0]
    return idx[0] if len(idx) == 1 else None


def area_targets(area: dict) -> list[dict]:
    """항목의 찾는 방법 목록. 정보 칸 여럿을 묶은 항목은 target 이 목록이다."""
    t = area.get("target")
    return t if isinstance(t, list) else [t]


def _locate_area(page, area):
    """둘러보기 항목의 위치. 묶은 항목은 칸마다 찾아 찾은 칸만 감싼다. 경고 줄처럼 그 화면에 없는 칸이 섞여도 나머지로 위치를 정한다."""
    return union([_locate_one(page, t, area.get("first", False)) for t in area_targets(area)])


def _locate_one(page, target, first=False):
    """정확히 같은 글자(또는 선택자) 후보만 보고, 하나로 정해질 때만 사각형을 돌려준다."""
    try:
        els = _candidates(page, target)[0].all()[:20]
        seen = []
        for el in els:
            try:
                seen.append(bool(el.evaluate(_SEEN)))
            except Exception:
                seen.append(False)
        i = pick_unique(seen, first)
        box = els[i].bounding_box() if i is not None else None
    except Exception:
        return None
    return [round(box["x"]), round(box["y"]), round(box["width"]), round(box["height"])] if box else None


def tour_shot(sr: dict, screen_img: str | None) -> dict:
    """둘러보기에 쓸 장면 결과. 동작이 없어 결과 화면을 따로 찍지 않은 장면은 기능 첫 화면을 결과 화면으로 쓴다."""
    if sr.get("endImg") or sr.get("unavailable") or not screen_img:
        return sr
    return {**sr, "endImg": screen_img}


def capture_tour_result(tour_plan: list[dict], scene_results: dict, rects: dict) -> list[dict]:
    """둘러보기 화면마다 그 장면의 결과 화면과 찾은 항목 위치를 모은다. 장면 캡처가 실패했으면 실패 문구를 적는다."""
    out = []
    for t in tour_plan:
        sr = scene_results.get(t["scene"], {})
        if not sr.get("endImg"):
            out.append({"key": t["key"], "unavailable": MSG_TOUR})
            continue
        out.append({"key": t["key"], "img": sr["endImg"],
                    "rects": {str(i): r for i, r in (rects.get(t["scene"]) or {}).items() if r}})
    return out


def start_targets(own: list[dict], fallback=None) -> list[dict]:
    """시작 줌에 넣을 대상. 앞쪽에 이어진 입력 · 고르기 동작(예: 연도 고르기 → 월 고르기)의 대상을 모두 넣고,
    그런 동작이 없으면 첫 대상 하나를 넣는다. 사이의 기다리기는 건너뛴다."""
    lead = []
    for st in own:
        if st["action"] == "wait":
            continue
        if st["action"] not in ("type", "select", "paste", "upload") or "target" not in st:
            break
        lead.append(st["target"])
    if lead:
        return lead
    first = next((st["target"] for st in own if "target" in st), fallback)
    return [first] if first else []


def union(rects: list) -> list | None:
    rects = [r for r in rects if r]
    if not rects:
        return None
    x1, y1 = min(r[0] for r in rects), min(r[1] for r in rects)
    x2, y2 = max(r[0] + r[2] for r in rects), max(r[1] + r[3] for r in rects)
    return [x1, y1, x2 - x1, y2 - y1]


def capture(plan_doc: dict) -> dict:
    from playwright.sync_api import sync_playwright  # uv run --no-project --with playwright 로 들어온다
    out_dir = Path(plan_doc["outDir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    base = plan_doc.get("baseUrl") or STATIC_ORIGIN
    result = {"features": {}}
    tour_rects, tours_by_scene = {}, {}
    for t in plan_doc.get("tour", []):
        tours_by_scene.setdefault(t["scene"], []).append(t)
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
                steps = scene_steps(s)
                setup, own = split_steps(steps)
                firsts = start_targets(own, s.get("start"))
                sr = {} if setup else {k: v for k, v in (("start", union([_locate(page, t) for t in firsts])), ("end", _locate_end(page, s.get("end")))) if v}
                if steps:
                    # 앞 장면의 동작이 남긴 상태를 지우려고 장면마다 화면을 새로 연다. 응답이 가짜라 눌러도 바깥에 아무 일도 없다
                    cp, _ = fresh()
                    try:
                        if setup:
                            # 준비 동작을 마친 화면이 이 장면의 시작 화면이다. 장면 자신의 첫 동작 위치를 그 화면에서 찾는다
                            _run(cp, setup, "준비")
                            start_img = f"{s['id']}_start.png"
                            cp.screenshot(path=str(out_dir / start_img))
                            sr["startImg"] = f"screens/{start_img}"
                            sr.update({k: v for k, v in (("start", union([_locate(cp, t) for t in firsts])), ("end", _locate_end(cp, s.get("end")))) if v})
                        points, frames = frame_points(own), []
                        sr["frames"] = frames  # 중간 동작에서 멈춰도 그때까지 찍은 동작 이미지는 남는다

                        def after(i, st, cp=cp, sid=s["id"], points=points, frames=frames):
                            if i not in points:
                                return
                            img = f"{sid}_f{len(frames) + 1}.png"
                            cp.screenshot(path=str(out_dir / img))
                            # 동작 뒤에 잰다. 누르기로 창이 열려 대상이 가려지면 사각형 없이 전체 화면을 보인다
                            rect = _locate_one(cp, st["target"], first=True) if st.get("target") else None
                            frames.append({"img": f"screens/{img}", **({"rect": rect} if rect else {})})

                        _run(cp, own, "장면", after)
                        end_img = f"{s['id']}_end.png"
                        cp.screenshot(path=str(out_dir / end_img))
                        sr["endImg"] = f"screens/{end_img}"
                        # 둘러보기 화면으로 고른 장면이면 결과 화면에서 항목 위치를 측정한다
                        for t in tours_by_scene.get(s["id"], []):
                            tour_rects[s["id"]] = {i: _locate_area(cp, a) for i, a in enumerate(t["areas"])}
                        end = _locate_end(cp, s.get("end"))
                        if end:
                            sr["end"] = end
                        # 입력 연출은 시작 화면에 보이는 칸에 치는 장면만 한다. 앞 동작이 화면을 바꾼 뒤에 치는 칸은 시작 화면에 없다
                        # 시작 줌이 칸 여럿을 합친 사각형이면 어느 칸에 친 글자인지 흐려지므로 칸 하나일 때만 친다
                        if own and own[0].get("action") == "type" and "start" in sr and len(firsts) == 1:
                            sr["typed"] = own[0]["text"]
                    except Exception as e:
                        sr["failed"] = str(e)  # 대상을 찾지 못하면 시작 화면 안의 결과 위치로 줌하고, 멈춘 동작을 보고에 남긴다
                    cp.close()
                if not sr.get("frames"):
                    sr.pop("frames", None)
                if not steps:
                    # 동작 없이 주소로 바로 여는 장면은 기능 첫 화면이 결과 화면이다. 둘러보기 항목도 그 화면에서 잰다
                    for t in tours_by_scene.get(s["id"], []):
                        tour_rects[s["id"]] = {i: _locate_area(page, a) for i, a in enumerate(t["areas"])}
                if steps and not (sr.get("startImg") or sr.get("endImg")):
                    # 동작을 하나도 따라 하지 못한 장면이 기능의 첫 화면을 자기 화면처럼 보이지 않게 이유를 적는다
                    sr = {"unavailable": MSG_STEP, **{k: sr[k] for k in ("failed", "frames") if k in sr}}
                fr["scenes"][s["id"]] = sr
            result["features"][f["key"]] = fr
            page.close()
        browser.close()
    scene_results = {sid: tour_shot(r, fr.get("screenImg")) for fr in result["features"].values() for sid, r in fr["scenes"].items()}
    result["tour"] = capture_tour_result(plan_doc.get("tour", []), scene_results, tour_rects)
    return result


def fail_result(plan_doc: dict, msg: str) -> dict:
    return {"features": {f["key"]: {"scenes": {s["id"]: {"unavailable": msg} for s in f["scenes"]}}
                         for f in plan_doc["features"]},
            "tour": [{"key": t["key"], "unavailable": msg} for t in plan_doc.get("tour", [])]}


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

    qmocks = [{"path": "/api/search", "json": {"rows": ["전체"]}},
              {"path": "/api/search", "query": {"q": "견적"}, "json": {"rows": ["견적 메일"]}}]
    pick = lambda url: json.loads(respond(url, "GET", {"baseUrl": "http://127.0.0.1:5173"}, qmocks)[1]["body"])["rows"]
    expect("검색어 조건이 맞으면 그 가짜 응답을 쓴다", pick("http://127.0.0.1:5173/api/search?q=%EA%B2%AC%EC%A0%81&page=1") == ["견적 메일"])
    expect("검색어가 없거나 다르면 조건 없는 가짜 응답을 쓴다",
           pick("http://127.0.0.1:5173/api/search?page=1") == ["전체"] and pick("http://127.0.0.1:5173/api/search?q=회의") == ["전체"])
    expect("click 만 있는 옛 장면은 클릭 동작 하나로 바꾼다",
           scene_steps({"start": {"text": "통계"}, "click": True}) == [{"action": "click", "target": {"text": "통계"}}])

    y = {"action": "select", "target": {"selector": "#year"}, "value": "2026", "setup": True}
    q = {"action": "type", "target": {"selector": "#q"}, "text": "견적"}
    expect("준비 동작과 장면 자신의 동작을 나눈다", split_steps([y, q]) == ([y], [q]))
    m = {"action": "select", "target": {"selector": "#month"}, "value": "9"}
    c = {"action": "click", "target": {"text": "실행"}}
    expect("시작 줌에 앞쪽의 입력 · 고르기 대상을 모두 넣는다(기다리기는 건너뜀)",
           start_targets([y, {"action": "wait", "ms": 500}, m, c]) == [y["target"], m["target"]])
    expect("입력 · 고르기로 시작하지 않으면 첫 대상 하나만 넣는다", start_targets([c, q]) == [c["target"]])
    expect("사각형 여럿을 감싸는 사각형을 만든다", union([[10, 20, 30, 40], [50, 10, 20, 20], None]) == [10, 10, 60, 50])
    expect("사람 동작마다 마지막을 빼고 찍는다(기다리기는 건너뜀)", frame_points([m, {"action": "wait", "ms": 500}, m, c]) == [0, 2])
    expect("사람 동작이 하나면 찍지 않는다", frame_points([c, {"action": "wait", "ms": 3000}]) == [])
    expect("누르기 둘 뒤 기다리기면 첫 누르기만 찍는다", frame_points([c, c, {"action": "wait", "ms": 3000}]) == [0])
    sp = select_scenes({"features": [{"key": "a", "scenes": [{"id": "a-0"}, {"id": "a-1"}]}, {"key": "b", "scenes": [{"id": "b-0"}]}],
                        "tour": [{"key": "t", "scene": "b-0", "areas": []}]}, ["a-1"])
    expect("고른 장면만 남기고 장면 없는 기능과 둘러보기는 뺀다",
           sp["features"] == [{"key": "a", "scenes": [{"id": "a-1"}]}] and sp["tour"] == [])
    good = [{"action": "rightclick", "target": {"text": "소계"}}, {"action": "press", "key": "Escape"},
            {"action": "paste", "target": {"selector": "table"}, "text": "a\tb"}, {"action": "drag", "target": {"selector": ".bar"}, "by": [80, 0]},
            {"action": "upload", "target": {"selector": "input[type=file]"}, "file": {"name": "보고서.pdf", "text": "%PDF-1.4"}}]
    expect("새 동작 종류가 칸을 갖추면 계획 검사를 통과한다", plan_errors({"features": [{"scenes": [{"id": "x", "steps": good}]}]}) == [])
    bad = [{"action": "swipe", "target": {"text": "a"}}, {"action": "drag", "target": {"text": "a"}},
           {"action": "upload", "target": {"text": "a"}, "file": "a.pdf"}, {"action": "paste", "target": {"text": "a"}}]
    errs = plan_errors({"features": [{"scenes": [{"id": "x", "steps": bad}]}]})
    expect("없는 동작 · drag 의 to/by · upload 의 file · paste 의 text 누락을 잡는다",
           any("swipe" in e for e in errs) and any("to 나 by" in e for e in errs)
           and any("upload 의 file" in e for e in errs) and any("paste 에 text" in e for e in errs))

    expect("보이는 후보가 하나면 그 후보를 고른다", pick_unique([False, True, False]) == 1)
    expect("보이는 후보가 둘 이상이면 찾지 못함이다", pick_unique([True, True]) is None)
    expect("보이는 후보가 없으면 찾지 못함이다", pick_unique([False]) is None)
    expect("first 항목은 보이는 첫 후보를 고른다", pick_unique([False, True, True], first=True) == 1)
    tp = [{"key": "result", "scene": "result-1", "areas": [{"name": "a"}, {"name": "b"}]},
          {"key": "input", "scene": "input-4", "areas": [{"name": "c"}]}]
    sr = {"result-1": {"endImg": "screens/result-1_end.png"}, "input-4": {"unavailable": MSG_STEP}}
    got = capture_tour_result(tp, sr, {"result-1": {0: [1, 2, 3, 4], 1: None}})
    expect("둘러보기 화면은 그 장면의 결과 화면과 찾은 위치를 쓴다",
           got[0] == {"key": "result", "img": "screens/result-1_end.png", "rects": {"0": [1, 2, 3, 4]}})
    expect("동작 없는 장면은 기능 첫 화면을 둘러보기 화면으로 쓴다",
           tour_shot({}, "screens/a.png") == {"endImg": "screens/a.png"} and tour_shot({"unavailable": MSG_STEP}, "screens/a.png") == {"unavailable": MSG_STEP})
    expect("장면 캡처가 실패한 둘러보기 화면은 실패 문구를 적는다",
           got[1] == {"key": "input", "unavailable": MSG_TOUR})
    terr = plan_errors({"features": [{"scenes": [{"id": "a-0"}]}], "tour": [{"key": "x", "scene": "a-9", "areas": [{"name": "n"}]}]})
    expect("둘러보기가 없는 장면을 가리키거나 target 이 없으면 잡는다", any("a-9" in e for e in terr) and any("target" in e for e in terr))
    grp = {"name": "펀드 정보", "target": [{"text": "5002"}, {"text": "대체투자1팀"}]}
    expect("묶은 항목은 찾는 방법 목록을 그대로 쓴다", area_targets(grp) == grp["target"])
    gerr = plan_errors({"features": [{"scenes": [{"id": "a-0"}]}], "tour": [{"key": "x", "scene": "a-0", "areas": [grp, {"name": "b", "target": [{"text": "a"}, "글자"]}]}]})
    expect("묶은 항목의 target 목록은 받고, 목록 안이 객체가 아니면 잡는다", gerr == ["둘러보기 x 항목 1: target 이 없습니다"])

    plan_doc = {"features": [{"key": "a", "scenes": [{"id": "a-0"}, {"id": "a-1"}]}]}
    expect("띄우지 못한 화면은 모든 장면에 같은 문구를 적는다",
           fail_result(plan_doc, MSG_FRONT) == {"features": {"a": {"scenes": {"a-0": {"unavailable": MSG_FRONT}, "a-1": {"unavailable": MSG_FRONT}}}}, "tour": []})
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
    ap.add_argument("--scenes", help="이 장면 id 들만 캡처한다(쉼표로 구분)")
    a = ap.parse_args()
    if a.check:
        return _check()
    if not a.plan or not a.out:
        ap.error("캡처 계획 경로와 --out 이 필요합니다")
    plan_doc = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    errs = plan_errors(plan_doc)
    if errs:
        print("캡처 계획을 고쳐야 합니다:")
        print("\n".join("  - " + e for e in errs))
        return 1
    if a.scenes:
        plan_doc = select_scenes(plan_doc, a.scenes.split(","))
    res =fail_result(plan_doc, FAIL_MSG[a.fail]) if a.fail else capture(plan_doc)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
