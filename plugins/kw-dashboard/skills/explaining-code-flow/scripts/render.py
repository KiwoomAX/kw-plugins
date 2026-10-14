"""흐름 JSON 을 검사하고 템플릿에 넣어 안내 화면 HTML 한 장을 만든다.

    python render.py <flow.json> --out <index.html>
    python render.py --check     # 붙박이 예제로 자체 검사
"""
from __future__ import annotations

import argparse
import copy
import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
KINDS = {"screen", "server", "db", "ai", "web", "local", "officepc", "code", "clock"}
ZONES = {"office", "app", "ax", "winus", "fund", "external"}
ICONS = {"file", "path", "ask", "card", "list", "stack", "bundle", "answer", "check", "table"}
STAGE_W, STAGE_H, SHOT_W, SHOT_H = 960, 520, 1440, 1000

SAMPLE = {
    "title": "예제 대시보드, 움직이며 보기", "repo": "example (main abc1234)", "appZone": "예제 서비스",
    "features": [{
        "key": "home", "name": "홈", "summary": "고정 카드", "screenImg": "screens/home.png",
        "nodes": [
            {"id": "pc", "name": "내 PC", "kind": "screen", "zone": "office", "x": 110, "y": 170},
            {"id": "data", "name": "샘플 데이터", "kind": "code", "zone": "app", "x": 360, "y": 80},
        ],
        "scenes": [
            {"title": "홈을 열면 카드가 그려집니다", "tips": ["금액 단위는 억원입니다."],
             "screen": {"startName": "「홈」 메뉴 클릭", "endName": "카드 표시", "start": [12, 77, 185, 40]},
             "actions": [{"from": "pc", "to": "data", "icon": "ask", "text": "카드 요청", "say": "화면이 샘플 데이터를 읽습니다."}]},
            {"title": "공고 목록", "tips": [],
             "screen": {"startName": "「공고」 탭 클릭", "endName": "목록 표시",
                        "unavailable": "실행에 필요한 데이터가 없어 화면을 만들 수 없습니다."},
             "actions": [{"from": "data", "to": "pc", "icon": "list", "text": "목록", "say": "목록이 화면으로 갑니다."}]},
        ],
    }],
}


def validate(data: dict) -> list[str]:
    errs: list[str] = []

    def need(obj, keys, where):
        for k in keys:
            if not isinstance(obj, dict) or obj.get(k) in (None, ""):
                errs.append(f"{where}.{k} 가 없습니다")

    def rect_ok(r):
        return (isinstance(r, list) and len(r) == 4 and all(isinstance(v, (int, float)) for v in r)
                and 0 <= r[0] <= SHOT_W and 0 <= r[1] <= SHOT_H)

    need(data, ["title", "repo", "appZone", "features"], "flow")
    for fi, f in enumerate(data.get("features") or []):
        fw = f"features[{fi}]"
        need(f, ["key", "name", "summary", "nodes", "scenes"], fw)
        ids = set()
        for ni, n in enumerate(f.get("nodes") or []):
            nw = f"{fw}.nodes[{ni}]"
            need(n, ["id", "name", "kind", "x", "y"], nw)
            ids.add(n.get("id"))
            if n.get("kind") not in KINDS:
                errs.append(f"{nw}.kind 값 {n.get('kind')!r} 는 명칭표에 없습니다")
            if "zone" in n and n["zone"] not in ZONES:
                errs.append(f"{nw}.zone 값 {n['zone']!r} 는 구역 목록에 없습니다")
            x, y = n.get("x"), n.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)) and not (0 <= x <= STAGE_W and 0 <= y <= STAGE_H):
                errs.append(f"{nw} 좌표 ({x}, {y}) 가 960×520 무대 밖입니다")
        for si, s in enumerate(f.get("scenes") or []):
            sw = f"{fw}.scenes[{si}]"
            need(s, ["title", "actions"], sw)
            if not isinstance(s.get("tips"), list):
                errs.append(f"{sw}.tips 목록이 없습니다")
            scr = s.get("screen") or {}
            need(scr, ["startName", "endName"], f"{sw}.screen")
            shot = bool(scr.get("startImg") or f.get("screenImg"))
            if scr.get("unavailable") and (scr.get("start") or scr.get("startImg")):
                errs.append(f"{sw}.screen 에 캡처와 실패 문구가 함께 있습니다")
            if not shot and not scr.get("unavailable"):
                errs.append(f"{sw}.screen 에 캡처도 실패 문구도 없습니다")
            for key in ("start", "end"):
                if key in scr and not rect_ok(scr[key]):
                    errs.append(f"{sw}.screen.{key} 는 1440×1000 안의 [x, y, 폭, 높이] 여야 합니다")
            for ai, a in enumerate(s.get("actions") or []):
                aw = f"{sw}.actions[{ai}]"
                need(a, ["from", "to", "icon", "text", "say"], aw)
                for end in ("from", "to"):
                    if a.get(end) and a[end] not in ids:
                        errs.append(f"{aw}.{end} 값 {a[end]!r} 인 노드가 없습니다")
                if a.get("icon") and a["icon"] not in ICONS:
                    errs.append(f"{aw}.icon 값 {a['icon']!r} 는 아이콘 목록에 없습니다")
    return errs


def render(data: dict, template: str = "movie_template.html") -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = (HERE / template).read_text(encoding="utf-8")
    return page.replace("__TITLE__", html.escape(data["title"])).replace("__DATA__", payload)


def _check() -> int:
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(("PASS  " if cond else "FAIL  ") + label)
        ok = ok and cond

    expect("예제가 검사를 통과한다", validate(SAMPLE) == [])
    page = render(SAMPLE)
    expect("렌더 결과에 자리표시 문자열이 남지 않는다", "__DATA__" not in page and "__TITLE__" not in page)
    expect("렌더 결과에 제목이 들어간다", "<title>예제 대시보드, 움직이며 보기</title>" in page)

    bad = copy.deepcopy(SAMPLE)
    f = bad["features"][0]
    f["nodes"][0]["kind"] = "browser"
    f["scenes"][0]["actions"][0]["to"] = "nowhere"
    del f["scenes"][1]["screen"]["unavailable"]
    del f["screenImg"]
    errs = validate(bad)
    expect("명칭표에 없는 kind 를 잡는다", any("kind" in e and "browser" in e for e in errs))
    expect("없는 노드로 가는 동작을 잡는다", any("nowhere" in e for e in errs))
    expect("캡처도 실패 문구도 없는 장면을 잡는다", any("features[0].scenes[1]" in e and "캡처" in e for e in errs))

    norect = copy.deepcopy(SAMPLE)
    del norect["features"][0]["scenes"][0]["screen"]["start"]
    expect("버튼 사각형이 없는 장면도 통과한다", validate(norect) == [])
    return 0 if ok else 1


def main() -> int:
    # PYTHONUTF8=1 을 준 것과 같은 결과다. 그 값이 없는 윈도우 PC 에서도 한국어 출력이 깨지지 않는다
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("flow", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return _check()
    if not a.flow or not a.out:
        ap.error("흐름 JSON 경로와 --out 이 필요합니다")
    data = json.loads(Path(a.flow).read_text(encoding="utf-8"))
    errs = validate(data)
    if errs:
        print("흐름 JSON 을 고쳐야 합니다:")
        for e in errs:
            print("  - " + e)
        return 1
    Path(a.out).write_text(render(data), encoding="utf-8")
    print(a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
