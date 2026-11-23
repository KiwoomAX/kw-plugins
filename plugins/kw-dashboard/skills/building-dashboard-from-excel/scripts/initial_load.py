"""개발 때 표를 처음 채울 적재 파일을 만든다. 적재는 개발자가 터미널에서 실행한다.
원천 · 수기 입력 · 고정값 표는 엑셀 저장값으로, 결과표는 그 표들로 계산 코드(calc.py)를 실행한 결과로 채운다.

실행: python initial_load.py <엑셀> --plan table_plan.json --results explain_results.json --calc calc.py --base-date YYYY-MM-DD --out load
스키마는 table_plan.json 의 schema 를 쓴다.
"""
import argparse
import datetime as dt
import importlib.util
import json
import re
import sys
import uuid
import zipfile
from pathlib import Path

from openpyxl.utils import column_index_from_string

import table_plan
import verify_calc

SHEET_DATE = re.compile(r"(20\d\d)\D?(\d{1,2})\D?(\d{1,2})")


def saved_time(path):
    """엑셀 파일이 저장된 시각. 수기 입력을 처음 채울 때 입력 시각으로 쓴다."""
    with zipfile.ZipFile(path) as z:
        core = z.read("docProps/core.xml").decode("utf-8")
    m = re.search(r"<dcterms:modified[^>]*>([^<]+)<", core)
    return m[1] if m else dt.datetime.fromtimestamp(Path(path).stat().st_mtime, dt.timezone.utc).isoformat()


def _date_text(value):
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()[:10]
    digits = re.sub(r"\D", "", str(value))
    return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}" if len(digits) >= 8 else None


def _fixed(plan, definitions):
    """표 밖 셀을 개발 고정값 표의 행으로 모은다. 버린 셀과 매개변수로 정한 셀은 넣지 않는다."""
    excel, out = plan["excel"], {t["name"]: [] for t in plan["tables"] if t["stage"] == "fixed"}
    for d in definitions:
        for item in d["outside"]["items"]:
            name = {"개발 고정값 표에 저장": f"{excel}__fixed__worker_cells", "별도 표로 저장": f"{excel}__fixed__{item.get('target')}"}.get(item["action"])
            if name:  # 쓰인 표가 없는 시트의 칸은 항목에 시트 이름이 붙어 온다
                out[name].append({"sheet": item.get("sheet", d["sheet"]), "cell": item["where"], "value": item["value"], "formula": item["formula"]})
    return out


def _dates_row(book, d):
    vals = book.sheet_values(d["sheet"])
    r = d["header_rows"][1]
    return {f"t_plus_{x['rel']}": _date_text(vals.get((r, column_index_from_string(x["col"])))) for x in d["date_columns"]}


def rows(book, plan, definitions, base_date):
    """{표 이름: 행 목록}. 제목 · 소계 행은 넣지 않고, 병합된 행 머리는 행마다 채운다."""
    by_id, saved, out = {d["id"]: d for d in definitions}, saved_time(book.path), _fixed(plan, definitions)
    stamp = {"base_date": base_date, "base_time": saved, "loaded_at": saved}
    for t in plan["tables"]:
        d = by_id.get(t.get("definition_id"))
        if d is None:
            continue
        if t["name"].endswith("_dates"):
            out[t["name"]] = [{**stamp, **_dates_row(book, d)}]
            continue
        extra = {"calc": "row_seq", "raw_manual": "row_id", "raw_external": "row_id"}.get(t["stage"])
        table = verify_calc.read_table(book, d)
        out[t["name"]] = [{**stamp, **({extra: i} if extra else {}), **r} for i, r in enumerate(table, 1)]
    return out


def _same_shape(book, d, sheet):
    """날짜 시트의 머리글이 기준 시트와 같은지 본다."""
    a, b = book.sheet_values(d["sheet"]), book.sheet_values(sheet)
    return all(a.get((r, c)) == b.get((r, c)) for r in range(d["header_rows"][0], d["header_rows"][1] + 1) for c in range(d["area"][1], d["area"][3] + 1))


def date_sheets(book, plan, definitions, group):
    """구조가 같은 지난 날짜 시트를 그 시트의 날짜를 기준일로 삼아 읽는다. 구조가 다르거나 날짜를 읽을 수 없는 시트는 different 로 알린다.
    기준 시트의 표는 그 날짜 시트에서 읽고, 다른 시트의 표는 기준 시트와 같은 값을 그 날짜로 넣는다."""
    mine = [d for d in definitions if d["sheet"] == group["base"]]
    loaded, different = {}, []
    for sheet in group["sheets"]:
        if sheet == group["base"]:
            continue
        m = SHEET_DATE.search(sheet)
        if not m or not all(_same_shape(book, d, sheet) for d in mine):
            different.append(sheet)
            continue
        moved = [{**d, "sheet": sheet} if d["sheet"] == group["base"] else d for d in definitions]
        day = f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
        loaded[day] = rows(book, plan, moved, day)
    return {"loaded": loaded, "different": different}


def upload_row(excel, base_date, saved_at):
    """초기 적재를 업로드 이력의 완료 행으로 남긴다. 이 행이 있어야 화면과 업로드가 그 기준일을 완료로 본다."""
    return {"upload_id": uuid.uuid4().hex, "excel": excel, "base_date": base_date, "base_time": saved_at, "status": "완료", "kind": "초기 적재",
            "uploaded_by": "", "started_at": saved_at, "finished_at": saved_at}


def _write(path, body):
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")


def calculated(plan, calculate, wired, base_date, stamp):
    """결과표 행. 엑셀 저장값 대신 원천 · 수기 입력 · 고정값 표로 계산 코드를 실행한다. 같은 기준일을 나중에 올려도 값이 같게 하기 위해서다."""
    by_name = {t["name"]: t for t in plan["tables"]}
    got = calculate({n: r for n, r in wired.items() if by_name[n]["stage"] != "calc"}, base_date)
    out = {}
    for t in plan["tables"]:
        if t["stage"] != "calc" or t["name"].endswith("_dates"):
            continue
        target = t["name"].split("__", 2)[2]
        if not got.get(target):
            sys.exit(f"계산 결과가 비어 있습니다: {target}. 적재 파일을 쓰지 않았습니다")
        out[t["name"]] = verify_calc.wire_values([{**stamp, **r} for r in got[target]], t["columns"])
    return out


def write_requests(book, plan, results, base_date, out, calculate):
    """적재 요청 파일을 쓴다. 파일 이름의 번호가 실행 순서이고, 번호 뒤의 글자(overwrite · upsert · insert)가 실행할 명령이다.
    날짜 시트 군이 있으면 구조가 같은 지난 날짜 시트도 그 날짜로 넣는다. 모든 기준일을 계산한 뒤에 파일을 쓰므로, 계산이 하나라도 실패하면 아무 파일도 쓰지 않는다.
    완료 이력(3번)은 마지막에 넣는다. 앞 파일이 하나라도 실패하면 3번을 넣지 않는다."""
    schema, by_name, saved = plan["schema"], {t["name"]: t for t in plan["tables"]}, saved_time(book.path)
    days, different = {base_date: rows(book, plan, results["definitions"], base_date)}, []
    for group in results.get("date_groups", []):
        got = date_sheets(book, plan, results["definitions"], group)
        days.update({day: r for day, r in got["loaded"].items() if day != base_date})
        different += got["different"]
    wired_days = {}
    for day, day_rows in days.items():
        wired = {name: verify_calc.wire_values(r, by_name[name]["columns"]) for name, r in day_rows.items()}
        wired.update(calculated(plan, calculate, wired, day, {"base_date": day, "base_time": saved, "loaded_at": saved}))
        wired_days[day] = wired
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for day, wired in wired_days.items():
        for name, table_rows in wired.items():
            if table_rows and by_name[name]["stage"] != "fixed":  # 처음에 비어 있는 표는 보낼 행이 없다
                _write(out / f"1_overwrite_{name}_{day}.json", {"schema": schema, "table": name, "where": {"base_date": day}, "rows": table_rows})
    for name, table_rows in wired_days[base_date].items():
        if table_rows and by_name[name]["stage"] == "fixed":  # 다시 적재해도 같은 칸은 고쳐 쓰고 중복으로 거절되지 않는다
            _write(out / f"2_upsert_{name}.json", {"schema": schema, "table": name, "mode": "upsert", "rows": table_rows})
    _write(out / "2_upsert_excel_registry.json", {"schema": schema, "table": "excel_registry", "mode": "upsert", "rows": table_plan.registry_rows(plan, results, schema)})
    _write(out / "3_insert_excel_upload.json", {"schema": schema, "table": "excel_upload", "mode": "append", "rows": [upload_row(plan["excel"], day, saved) for day in sorted(days)]})
    return {"dates": sorted(days), "different": different}


def load_calc(path):
    """7단계에서 엑셀 대조에 합격한 calc.py 의 calculate."""
    spec = importlib.util.spec_from_file_location("feature_calc", path)
    calc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calc)
    return calc.calculate


def open_book(path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "explaining-excel-cell/scripts"))
    import explain_cell
    return explain_cell.Book(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="엑셀 저장값과 계산 결과로 첫 적재 파일을 만든다")
    ap.add_argument("excel")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--calc", required=True, help="7단계에서 엑셀 대조에 합격한 calc.py")
    ap.add_argument("--base-date", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8-sig"))
    results = json.loads(Path(a.results).read_text(encoding="utf-8-sig"))
    got = write_requests(open_book(a.excel), plan, results, a.base_date, a.out, load_calc(a.calc))
    print(f"적재 파일: {a.out} (기준일 {', '.join(got['dates'])})")
    if got["different"]:
        print(f"구조가 달라 넣지 않은 날짜 시트: {', '.join(got['different'])}. 이 시트를 어떻게 할지 개발자에게 묻는다")


if __name__ == "__main__":
    main()
