"""새 구조를 PC 의 임시 저장소에서 실행하고 엑셀과 대조한다. 샌드박스에는 아무것도 쓰지 않는다.

첫 적재 파일을 임시 저장소에 넣고, 화면 서버 API 로 입력 양식을 내려받아 그대로 업로드한 뒤, 저장된 결과표를 엑셀 저장값과 셀 단위로 대조한다.
검토 기준일의 결과표는 업로드가 계산해 채운다. 등록 쿼리는 실제로 호출하고, 연결을 기다리는 표는 엑셀 저장값을 쓴다.

실행: python review_run.py run <엑셀> --plan table_plan.json --results explain_results.json --calc calc.py --base-date YYYY-MM-DD --dir <분석기 결과 폴더>/review
"""
import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "templates/backend"))
import initial_load  # noqa: E402
import table_plan  # noqa: E402
import verify_calc  # noqa: E402

HIDDEN = ("base_date", "base_time", "loaded_at")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def apply_requests(client, folder):
    """적재 파일을 이름 순서로 보낸다. 파일 이름의 overwrite 는 범위 교체, upsert · insert 는 행 넣기다."""
    for path in sorted(Path(folder).glob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        client.post("rows/overwrite" if "_overwrite_" in path.name else "rows/insert", body)


def _same_row(a, b):
    keys = (set(a) | set(b)) - set(HIDDEN)
    return all(verify_calc._same(a.get(k), b.get(k), None) for k in keys)


def _only(rows, others):
    """rows 중 others 에 짝이 없는 행 수. 행 순서는 보지 않고, 짝지은 행은 다시 쓰지 않는다."""
    left, count = list(others), 0
    for r in rows:
        hit = next((i for i, o in enumerate(left) if _same_row(r, o)), None)
        if hit is None:
            count += 1
        else:
            left.pop(hit)
    return count


def source_changes(plan, excel_rows, store, base_date):
    """등록 쿼리로 새로 받은 원천 표마다 엑셀 저장값과 새 응답 중 한쪽에만 있는 행 수. 엑셀 저장 뒤 원천 값이 바뀌었는지 알리는 근거다."""
    import upload
    out = []
    for t in upload.by_stage(plan, *upload.SOURCE_STAGES):
        if t["waiting_query"]:
            continue
        excel = [{k: v for k, v in r.items() if k not in HIDDEN} for r in excel_rows.get(t["name"], [])]
        fetched = [{k: v for k, v in r.items() if k not in HIDDEN} for r in store.read(t["name"], base_date)]
        out.append({"table": t["name"], "excel_rows": len(excel), "fetched_rows": len(fetched),
                    "only_excel": _only(excel, fetched), "only_fetched": _only(fetched, excel)})
    return out


def run_review(excel, plan, results, calculate, base_date, review_dir, winus):
    """{"upload": 업로드 결과, "report": 대조 보고서 또는 None, "source_changes": [...]}."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import api
    import store as store_module
    import upload
    from file_client import FileClient
    review_dir = Path(review_dir)
    for sub in ("store", "load"):
        shutil.rmtree(review_dir / sub, ignore_errors=True)
    book = initial_load.open_book(excel)
    initial_load.write_requests(book, plan, results, base_date, review_dir / "load", calculate, review=True)
    client = FileClient(review_dir / "store", plan)
    apply_requests(client, review_dir / "load")
    store = store_module.Store(client, plan["schema"], plan)
    app = FastAPI()
    app.include_router(api.make_router(plan, lambda request: store, winus, calculate, lambda request: "검토", review=True))
    http = TestClient(app)
    form = http.get("/form", params={"date": base_date})
    if form.status_code != 200:
        sys.exit(f"양식을 받지 못했습니다: {form.status_code}")
    got = http.post("/upload", files={"file": ("form.xlsx", form.content, XLSX)}, data={"date": base_date, "confirm": "true"}).json()
    if got["status"] != "saved":
        return {"upload": got, "report": None, "source_changes": []}
    defs = [d for d in results["definitions"] if not d.get("orphan")]
    excel_rows = {n: verify_calc.wire_values(r, next(t for t in plan["tables"] if t["name"] == n)["columns"])
                  for n, r in initial_load.rows(book, plan, defs, base_date).items()}
    inputs = {t["name"]: store.read(t["name"], base_date) for t in plan["tables"] if t["stage"].startswith("raw_")}
    inputs.update({t["name"]: store.read_all(t["name"]) for t in upload.by_stage(plan, "fixed")})
    computed = calculate(inputs, dt.date.fromisoformat(base_date))  # 통계 표 대상은 저장하지 않으므로 다시 계산해 대조한다
    stored = {t["name"].split("__", 2)[2]: store.read(t["name"], base_date) for t in plan["tables"] if t["stage"] == "calc"}
    compared = {**computed, **stored}
    row_map = {d["target"]: {i: r for i, r in enumerate(table_plan.data_rows(book, d), 1)} for d in defs if d["role"] == "결과"}
    digits = verify_calc.display_digits(excel, sorted({d["sheet"] for d in defs if d["role"] == "결과"}))
    report = verify_calc.compare(book, defs, compared, row_map, digits)
    return {"upload": got, "report": report, "source_changes": source_changes(plan, excel_rows, store, base_date)}


def _run_command(argv):
    ap = argparse.ArgumentParser(description="새 구조를 임시 저장소에서 실행하고 엑셀과 대조한다")
    ap.add_argument("excel")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--calc", required=True)
    ap.add_argument("--base-date", required=True)
    ap.add_argument("--dir", required=True, help="분석기 결과 폴더 아래 review 폴더")
    a = ap.parse_args(argv)
    import winus
    read = lambda p: json.loads(Path(p).read_text(encoding="utf-8-sig"))  # noqa: E731
    got = run_review(a.excel, read(a.plan), read(a.results), initial_load.load_calc(a.calc), a.base_date, a.dir, winus)
    sys.stdout.reconfigure(encoding="utf-8")
    if got["report"] is None:
        print(f"업로드 실패: {got['upload']['message']}")
        for e in got["upload"]["errors"]:
            print(f"- {e}")
        return 1
    out = Path(a.dir) / "verify_report.json"
    out.write_text(json.dumps({**got["report"], "source_changes": got["source_changes"]}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    r, ok = got["report"], verify_calc.passed(got["report"])
    print(f"{'합격' if ok else '불합격'}: 같은 셀 {r['same']}, 다른 셀 {len(r['diff'])}, 빠진 셀 {len(r['missing'])}, 남는 행 {len(r['extra'])}, "
          f"다른 소계 칸 {len(r['summary_diff'])}, 빠진 소계 행 {len(r['summary_missing'])}. 자세한 내용: {out}")
    return 0 if ok else 1


COMMANDS = {"run": _run_command}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        sys.exit(f"명령: {' | '.join(COMMANDS)}")
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
