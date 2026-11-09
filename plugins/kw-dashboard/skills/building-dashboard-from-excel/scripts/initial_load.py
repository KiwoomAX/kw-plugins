"""개발 때 엑셀 저장값으로 표를 처음 채울 적재 파일을 만든다. 적재는 개발자가 터미널에서 실행한다.

실행: python initial_load.py <엑셀> --plan table_plan.json --results explain_results.json --base-date YYYY-MM-DD --schema <스키마> --out load
"""
import argparse
import datetime as dt
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
            if name:
                out[name].append({"sheet": d["sheet"], "cell": item["where"], "value": item["value"], "formula": item["formula"]})
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
    """구조가 같은 지난 날짜 시트를 그 시트의 날짜를 기준일로 삼아 읽는다. 구조가 다르거나 날짜를 읽을 수 없는 시트는 different 로 알린다."""
    mine = [d for d in definitions if d["sheet"] == group["base"]]
    loaded, different = {}, []
    for sheet in group["sheets"]:
        if sheet == group["base"]:
            continue
        m = SHEET_DATE.search(sheet)
        if not m or not all(_same_shape(book, d, sheet) for d in mine):
            different.append(sheet)
            continue
        moved = [{**d, "sheet": sheet} for d in mine]
        ids = {d["id"] for d in mine}
        part = {**plan, "tables": [t for t in plan["tables"] if t.get("definition_id") in ids]}
        day = f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
        loaded[day] = rows(book, part, moved, day)
    return {"loaded": loaded, "different": different}


def upload_row(excel, base_date, saved_at):
    """초기 적재를 업로드 이력의 완료 행으로 남긴다. 이 행이 있어야 화면과 업로드가 그 기준일을 완료로 본다."""
    return {"upload_id": uuid.uuid4().hex, "excel": excel, "base_date": base_date, "base_time": saved_at, "status": "완료", "kind": "초기 적재",
            "uploaded_by": "", "started_at": saved_at, "finished_at": saved_at}


def _write(path, body):
    path.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")


def write_requests(book, plan, results, base_date, schema, out):
    """표마다 적재 요청 파일을 쓴다. 파일 이름의 앞 글자(overwrite · insert)가 실행할 명령이다."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    by_name = {t["name"]: t for t in plan["tables"]}
    for name, table_rows in rows(book, plan, results["definitions"], base_date).items():
        if not table_rows:  # 처음에 비어 있는 표(override 등)는 보낼 행이 없다
            continue
        wired = verify_calc.wire_values(table_rows, by_name[name]["columns"])
        if by_name[name]["stage"] == "fixed":
            _write(out / f"insert_{name}.json", {"schema": schema, "table": name, "mode": "append", "rows": wired})
        else:
            _write(out / f"overwrite_{name}.json", {"schema": schema, "table": name, "where": {"base_date": base_date}, "rows": wired})
    _write(out / "insert_excel_upload.json", {"schema": schema, "table": "excel_upload", "mode": "append", "rows": [upload_row(plan["excel"], base_date, saved_time(book.path))]})
    _write(out / "insert_excel_registry.json", {"schema": schema, "table": "excel_registry", "mode": "append", "rows": table_plan.registry_rows(plan, results, schema)})


def main(argv=None):
    ap = argparse.ArgumentParser(description="엑셀 저장값으로 첫 적재 파일을 만든다")
    ap.add_argument("excel")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--base-date", required=True)
    ap.add_argument("--schema", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "explaining-excel-cell/scripts"))
    import explain_cell
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8-sig"))
    results = json.loads(Path(a.results).read_text(encoding="utf-8-sig"))
    write_requests(explain_cell.Book(a.excel), plan, results, a.base_date, a.schema, a.out)
    print(f"적재 파일: {a.out}")


if __name__ == "__main__":
    main()
