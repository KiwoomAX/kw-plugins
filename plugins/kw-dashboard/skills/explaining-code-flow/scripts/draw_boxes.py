"""장면 · 화면 대조용으로 캡처 이미지 사본에 화면 사각형을 그린다. 원본과 결과물은 고치지 않는다.

    python draw_boxes.py <capture_result.json> --screens <screens 폴더> --out <임시 폴더>
    python draw_boxes.py --check

그리기는 uv run --no-project --with pillow 로 실행한다. 사본 이름은 <장면id>_<순번>_<start|fN|end>.png 이고,
순번은 시작 화면 · 동작 이미지 · 결과 화면의 재생 순서다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def box_jobs(result: dict) -> list[tuple[str, list | None, str]]:
    """(원본 이미지 경로, 화면 사각형, 사본 이름) 목록. 시작 화면이 없는 장면은 시작을 건너뛴다."""
    jobs = []
    for fr in result.get("features", {}).values():
        for sid, sr in fr.get("scenes", {}).items():
            shots = []
            if sr.get("startImg"):
                shots.append((sr["startImg"], sr.get("start"), "start"))
            shots += [(f["img"], f.get("rect"), f"f{n}") for n, f in enumerate(sr.get("frames", []), 1)]
            if sr.get("endImg"):
                shots.append((sr["endImg"], sr.get("end"), "end"))
            jobs += [(img, rect, f"{sid}_{i}_{tag}.png") for i, (img, rect, tag) in enumerate(shots)]
    return jobs


def _check() -> int:
    ok = True

    def expect(label, cond):
        nonlocal ok
        print(("PASS  " if cond else "FAIL  ") + label)
        ok = ok and cond

    r = {"features": {"a": {"scenes": {"a-1": {"startImg": "screens/a-1_start.png", "start": [1, 2, 3, 4],
         "frames": [{"img": "screens/a-1_f1.png", "rect": [5, 6, 7, 8]}, {"img": "screens/a-1_f2.png"}],
         "endImg": "screens/a-1_end.png", "end": [9, 9, 9, 9]}}}}}
    expect("시작 · 동작 · 결과 순서로 사본을 만든다",
           [j[2] for j in box_jobs(r)] == ["a-1_0_start.png", "a-1_1_f1.png", "a-1_2_f2.png", "a-1_3_end.png"])
    expect("사각형이 없는 동작 이미지는 사각형 없이 복사한다", box_jobs(r)[2][1] is None)
    expect("시작 화면이 없는 장면은 시작을 건너뛴다",
           [j[2] for j in box_jobs({"features": {"a": {"scenes": {"a-0": {"endImg": "screens/a-0_end.png"}}}}})] == ["a-0_0_end.png"])
    return 0 if ok else 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("result", nargs="?")
    ap.add_argument("--screens")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return _check()
    if not (a.result and a.screens and a.out):
        ap.error("캡처 결과 경로와 --screens, --out 이 필요합니다")
    from PIL import Image, ImageDraw  # uv run --no-project --with pillow 로 들어온다
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = box_jobs(json.loads(Path(a.result).read_text(encoding="utf-8")))
    for img, rect, name in jobs:
        im = Image.open(Path(a.screens) / Path(img).name).convert("RGB")
        if rect:
            x, y, w, h = rect
            ImageDraw.Draw(im).rectangle([x, y, x + w, y + h], outline="#D33", width=3)
        im.save(out / name)
    print(f"{out} ({len(jobs)}장)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
