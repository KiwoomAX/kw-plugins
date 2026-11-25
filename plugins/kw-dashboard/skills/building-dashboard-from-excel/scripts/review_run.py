"""새 구조를 PC 의 임시 저장소에서 실행하고 엑셀과 대조한다. 샌드박스에는 아무것도 쓰지 않는다.

첫 적재 파일을 임시 저장소에 넣고, 화면 서버 API 로 입력 양식을 내려받아 그대로 업로드한 뒤, 저장된 결과표를 엑셀 저장값과 셀 단위로 대조한다.
검토 기준일의 결과표는 업로드가 계산해 채운다. 등록 쿼리는 실제로 호출하고, 연결을 기다리는 표는 엑셀 저장값을 쓴다.

검토 엑셀(review/<엑셀 영문 이름>-review.xlsx)에는 원천 · 결과 · 통계 표를 시트마다 쓴다. 담당자가 승인하면 그 저장소를 복사해 두고,
샌드박스 적재 요청은 그 복사본으로 만든다. 적재한 뒤에는 샌드박스에서 다시 읽은 값으로 검토 엑셀을 다시 써서 승인본과 비교한다.

실행: python review_run.py run <엑셀> --plan table_plan.json --results explain_results.json --calc calc.py --base-date YYYY-MM-DD --dir <분석기 결과 폴더>/review
      python review_run.py approve --dir review
      python review_run.py sandbox-requests --dir review/approved --plan table_plan.json --out sandbox_load
      python review_run.py check-sandbox --selected <폴더> --plan table_plan.json --calc calc.py --base-date YYYY-MM-DD --dir review
"""
import argparse
import datetime as dt
import json
import shutil
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "templates/backend"))
import initial_load  # noqa: E402
import table_plan  # noqa: E402
import verify_calc  # noqa: E402

HIDDEN = ("base_date", "base_time", "loaded_at")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


RAW_STAGES = ("raw_winus", "raw_wfs", "raw_manual", "raw_external", "fixed")
PREFIX = {**{s: "raw" for s in RAW_STAGES}, "calc": "cal", "stat": "stat"}
NUMBER = {"numeric", "integer", "bigint"}
SHEET_MAX = 31  # 엑셀 시트 이름 최대 길이


def _shown(t):
    """검토 엑셀에 시트로 쓰는 표. 날짜 표와 공통 표는 뺀다."""
    return t["stage"] in PREFIX and not (t["stage"] == "calc" and t["name"].endswith("_dates"))


def sheet_names(plan):
    """{표 이름: 시트 이름}. 원천 · 고정값은 raw_, 결과는 cal_, 통계는 stat_ 에 대상을 붙인다. 31자를 넘거나 겹치면 앞을 줄이고 _2 · _3 을 붙인다."""
    out, used = {}, set()
    for t in plan["tables"]:
        if not _shown(t):
            continue
        base = f"{PREFIX[t['stage']]}_{t['name'].split('__', 2)[2]}"
        name, n = base[:SHEET_MAX], 1
        while name in used:
            n += 1
            name = base[:SHEET_MAX - len(f"_{n}")] + f"_{n}"
        used.add(name)
        out[t["name"]] = name
    return out


def _cell(v, kind):
    if v in (None, "") or kind not in NUMBER:
        return v
    try:
        d = Decimal(str(v))
    except InvalidOperation:
        return v
    return int(d) if kind != "numeric" or d == d.to_integral_value() else d


def _order_key(row, names, kinds):
    """빈 값은 맨 뒤로, 숫자 열은 값의 크기로 비교한다. 저장소마다 다른 행 순서가 값 차이로 보이지 않게 한다."""
    key = []
    for n in names:
        v = row.get(n)
        if v in (None, ""):
            key.append((1, 0, ""))
        elif kinds.get(n) in NUMBER:
            try:
                key.append((0, Decimal(str(v)), ""))
            except InvalidOperation:
                key.append((0, 0, str(v)))
        else:
            key.append((0, 0, str(v)))
    return key


def _inputs(store, plan, base_date):
    """계산 코드에 넣는 표. 업로드처럼 원천 · 수기 입력은 그 기준일 행, 고정값은 모든 행이다."""
    out = {t["name"]: store.read(t["name"], base_date) for t in plan["tables"] if t["stage"].startswith("raw_")}
    out.update({t["name"]: store.read_all(t["name"]) for t in plan["tables"] if t["stage"] == "fixed"})
    return out


def write_review_excel(store, plan, calculate, base_date, path):
    """검토 엑셀을 쓴다. 시트 순서는 원천(고정값 포함), 결과, 통계다. 소계 행은 넣지 않는다.
    통계 표는 저장하지 않으므로 저장소의 입력 표로 계산 코드를 다시 실행해 얻는다."""
    import openpyxl
    names, computed = sheet_names(plan), calculate(_inputs(store, plan, base_date), dt.date.fromisoformat(base_date))
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for group in (RAW_STAGES, ("calc",), ("stat",)):
        for t in plan["tables"]:
            if t["name"] not in names or t["stage"] not in group:
                continue
            columns = [c for c in t["columns"] if c["name"] not in HIDDEN]
            kinds = {c["name"]: c["type"] for c in columns}
            if t["stage"] == "stat":
                rows = [{"row_seq": i, **r} for i, r in enumerate(computed.get(t["name"].split("__", 2)[2], []), 1)]
            elif t["stage"] == "fixed":
                rows = store.read_all(t["name"])
                if not rows:
                    continue
            else:
                rows = store.read(t["name"], base_date)
            order = ["row_seq"] if t["stage"] in ("calc", "stat") else (t["primary_key"] or [c["name"] for c in columns])
            rows = sorted(rows, key=lambda r: _order_key(r, order, kinds))
            dates = {}
            if t["stage"] == "calc" and f"{t['name']}_dates" in store.tables:
                found = store.read(f"{t['name']}_dates", base_date)
                dates = found[0] if found else {}
            ws = wb.create_sheet(names[t["name"]])
            ws.append([dates.get(c["name"]) or c["name"] for c in columns])  # 날짜 열은 t_plus_1 대신 그 기준일의 실제 날짜를 머리글로 쓴다
            for r in rows:
                ws.append([_cell(r.get(c["name"]), c["type"]) for c in columns])
    wb.save(path)


def _value_text(v):
    try:
        return ("number", Decimal(str(v))) if v is not None and not isinstance(v, bool) and str(v).strip() != "" else ("text", v)
    except InvalidOperation:
        return ("text", v)


def compare_workbooks(a, b):
    """시트 이름과 셀 값이 다른 곳 「시트!셀: a 값 ≠ b 값」 목록. 숫자는 Decimal 로 비교한다."""
    import openpyxl
    wa, wb_ = openpyxl.load_workbook(a, data_only=True), openpyxl.load_workbook(b, data_only=True)
    out = [f"시트 차이: {n} 이 {'뒤' if n in wa.sheetnames else '앞'} 파일에 없음" for n in sorted(set(wa.sheetnames) ^ set(wb_.sheetnames))]
    for name in [n for n in wa.sheetnames if n in wb_.sheetnames]:
        x, y = wa[name], wb_[name]
        for r in range(1, max(x.max_row, y.max_row) + 1):
            for c in range(1, max(x.max_column, y.max_column) + 1):
                u, v = x.cell(r, c), y.cell(r, c)
                if _value_text(u.value) != _value_text(v.value):
                    out.append(f"{name}!{u.coordinate}: {u.value} ≠ {v.value}")
    return out


def approve(review_dir):
    """검토 저장소와 검토 엑셀을 approved/ 로 복사한다. 샌드박스 적재는 이 복사본으로만 만든다."""
    review_dir = Path(review_dir)
    target = review_dir / "approved"
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    shutil.copytree(review_dir / "store", target / "store")
    for f in review_dir.glob("*-review.xlsx"):
        shutil.copy2(f, target / f.name)
    return target


def _write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")


def sandbox_requests(approved_dir, plan, out):
    """승인본 저장소로 샌드박스 요청 파일을 쓰고 이름 목록을 돌려준다. 번호가 실행 순서다. 통계 표는 넣지 않는다.
    적재 뒤 대조에 쓸 조회 요청도 out/select/ 에 쓴다."""
    from file_client import FileClient
    client, schema, out = FileClient(Path(approved_dir) / "store", plan), plan["schema"], Path(out)
    rows_of = lambda name: client._load(name)  # noqa: E731
    names = []
    for t in plan["tables"]:
        if t["stage"].startswith("raw_") or t["stage"] == "calc":
            for day in sorted({r["base_date"] for r in rows_of(t["name"])}):
                rows = [r for r in rows_of(t["name"]) if r["base_date"] == day]
                names.append(f"1_overwrite_{t['name']}_{day}.json")
                _write(out / names[-1], {"schema": schema, "table": t["name"], "where": {"base_date": day}, "rows": rows})
                _write(out / "select" / f"select_{t['name']}_{day}.json", {"schema": schema, "table": t["name"], "where": {"base_date": day}})
        elif (t["stage"] == "fixed" or t["name"] == "excel_registry") and rows_of(t["name"]):
            names.append(f"2_upsert_{t['name']}.json")
            _write(out / names[-1], {"schema": schema, "table": t["name"], "mode": "upsert", "rows": rows_of(t["name"])})
            if t["stage"] == "fixed":
                _write(out / "select" / f"select_{t['name']}.json", {"schema": schema, "table": t["name"]})
    done = [r for r in rows_of("excel_upload") if r.get("status") == "완료"]
    names.append("3_insert_excel_upload.json")
    _write(out / names[-1], {"schema": schema, "table": "excel_upload", "mode": "append", "rows": done})
    _write(out / "select" / "select_excel_upload.json", {"schema": schema, "table": "excel_upload", "where": {"excel": plan["excel"]}})
    return sorted(names)


def check_sandbox(selected, plan, calculate, base_date, review_dir):
    """샌드박스에서 다시 읽은 값으로 검토 엑셀을 다시 써서 승인본 검토 엑셀과 비교한다. 다른 곳 목록을 돌려준다.
    selected 의 파일은 조회 요청 파일 이름에서 select_ 를 뺀 이름(<표 이름>_<기준일>.json 또는 <표 이름>.json)이고 내용은 {"columns", "rows"} 다."""
    import store as store_module
    from file_client import FileClient
    review_dir = Path(review_dir)
    folder = review_dir / "sandbox-check"
    shutil.rmtree(folder, ignore_errors=True)
    (folder / "store").mkdir(parents=True)
    known = sorted((t["name"] for t in plan["tables"]), key=len, reverse=True)
    collected = {}
    for f in sorted(Path(selected).glob("*.json")):
        name = next((n for n in known if f.stem == n or f.stem.startswith(n + "_")), None)
        if name is None:
            sys.exit(f"설계에 없는 표의 조회 결과: {f.name}")
        body = json.loads(f.read_text(encoding="utf-8-sig"))
        collected.setdefault(name, []).extend(dict(zip(body["columns"], row)) for row in body["rows"])
    for name, rows in collected.items():
        (folder / "store" / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    path = folder / f"{plan['excel']}-review.xlsx"
    write_review_excel(store_module.Store(FileClient(folder / "store", plan), plan["schema"], plan), plan, calculate, base_date, path)
    return compare_workbooks(review_dir / "approved" / path.name, path)


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
    computed = calculate(_inputs(store, plan, base_date), dt.date.fromisoformat(base_date))  # 통계 표 대상은 저장하지 않으므로 다시 계산해 대조한다
    stored = {t["name"].split("__", 2)[2]: store.read(t["name"], base_date) for t in plan["tables"] if t["stage"] == "calc"}
    compared = {**computed, **stored}
    row_map = {d["target"]: {i: r for i, r in enumerate(table_plan.data_rows(book, d), 1)} for d in defs if d["role"] == "결과"}
    digits = verify_calc.display_digits(excel, sorted({d["sheet"] for d in defs if d["role"] == "결과"}))
    report = verify_calc.compare(book, defs, compared, row_map, digits)
    path = review_dir / f"{plan['excel']}-review.xlsx"
    write_review_excel(store, plan, calculate, base_date, path)
    return {"upload": got, "report": report, "source_changes": source_changes(plan, excel_rows, store, base_date), "excel": path}


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
    print(f"검토 엑셀: {got['excel']}")
    return 0 if ok else 1


def _approve_command(argv):
    ap = argparse.ArgumentParser(description="담당자가 승인한 검토 저장소와 검토 엑셀을 approved/ 로 복사한다")
    ap.add_argument("--dir", required=True)
    a = ap.parse_args(argv)
    print(f"승인본: {approve(a.dir)}")
    return 0


def _sandbox_requests_command(argv):
    ap = argparse.ArgumentParser(description="승인본으로 샌드박스 적재 요청 파일과 조회 요청 파일을 쓴다")
    ap.add_argument("--dir", required=True, help="review/approved")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    names = sandbox_requests(a.dir, json.loads(Path(a.plan).read_text(encoding="utf-8-sig")), a.out)
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(names))
    return 0


def _check_sandbox_command(argv):
    ap = argparse.ArgumentParser(description="샌드박스에서 다시 읽은 값으로 검토 엑셀을 다시 써서 승인본과 비교한다")
    ap.add_argument("--selected", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--calc", required=True)
    ap.add_argument("--base-date", required=True)
    ap.add_argument("--dir", required=True, help="review")
    a = ap.parse_args(argv)
    diffs = check_sandbox(a.selected, json.loads(Path(a.plan).read_text(encoding="utf-8-sig")), initial_load.load_calc(a.calc), a.base_date, a.dir)
    sys.stdout.reconfigure(encoding="utf-8")
    print("승인본과 같습니다" if not diffs else "\n".join(["승인본과 다른 곳:"] + diffs))
    return 1 if diffs else 0


COMMANDS = {"run": _run_command, "approve": _approve_command, "sandbox-requests": _sandbox_requests_command, "check-sandbox": _check_sandbox_command}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        sys.exit(f"명령: {' | '.join(COMMANDS)}")
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main())
