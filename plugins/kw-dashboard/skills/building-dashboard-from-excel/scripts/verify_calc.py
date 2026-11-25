"""Python 으로 옮긴 계산 결과를 엑셀에 저장된 값과 셀 단위로 대조한다. 엑셀의 저장값이 정답이다.

대조는 표 정의 범위의 셀을 기준으로 한다. 그래서 계산 코드가 빠뜨린 행 · 열도 찾는다.

실행: python verify_calc.py <엑셀> --plan table_plan.json --results explain_results.json --calc calc.py --base-date YYYY-MM-DD --out verify_report.json [--inputs inputs.json]
--inputs 는 엑셀 저장값 대신 쓸 표 {표 이름: 행 목록} 이다. 9단계에서 실제 응답으로 다시 대조할 때 쓴다.
"""
import argparse
import datetime as dt
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

import openpyxl
from openpyxl.utils import column_index_from_string

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "templates/backend"))
import table_plan  # noqa: E402
from colmap import round_half_up  # noqa: E402

NEAR = Decimal("0.000000001")


def read_table(book, definition):
    """엑셀 저장값을 표 정의 범위로 읽는다. 여러 행에 병합된 행 머리는 행마다 채운다."""
    vals, tops = book.sheet_values(definition["sheet"]), book.merge_top.get(definition["sheet"], {})
    out = []
    for r in table_plan.data_rows(book, definition):
        row = {}
        for c in definition["columns"]:
            pos = (r, column_index_from_string(c["col"]))
            row[c["db"]] = vals.get(tops.get(pos, pos))
        out.append(row)
    return out


NUMBER = {"number", "numeric"}
SERIAL_ZERO = dt.datetime(1899, 12, 30)


def _serial(value):
    """날짜 · 시각 표시 형식 때문에 날짜로 읽힌 숫자 칸을 엑셀 일련값으로 되돌린다."""
    if isinstance(value, dt.time):
        return (value.hour * 3600 + value.minute * 60 + value.second + value.microsecond / 1e6) / 86400
    days = (value - SERIAL_ZERO).total_seconds() / 86400
    return round(days - 1 if 1 < days < 61 else days, 10)  # openpyxl 은 60 이하 일련값에 하루를 더해 읽는다(1900년 윤년 오류 보정)


def _wire(value, kind):
    if value is None or kind == "integer":
        return value
    if value == "" and kind in NUMBER | {"date", "timestamptz"}:  # DB 가 숫자 · 날짜 열의 빈 글자를 거절한다
        return None
    if kind in NUMBER and isinstance(value, (dt.datetime, dt.time)):
        value = _serial(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()[:10]
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip() if kind in ("text", "code", "varchar") else str(value)


def wire_values(rows, columns):
    """샌드박스가 돌려주는 모양으로 바꾼다(소수 · 날짜는 글자). 계산 코드가 운영과 같은 입력을 받게 한다."""
    kinds = {c.get("db") or c["name"]: c["type"] for c in columns}
    return [{k: _wire(v, kinds.get(k, "text")) for k, v in row.items()} for row in rows]


def _decimal(v):
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        return Decimal(str(v))
    except InvalidOperation:
        return None


def _same(cached, computed, digits):
    if cached in (None, "") or computed in (None, ""):  # 빈 값과 0 은 같게 본다
        other = computed if cached in (None, "") else cached
        return other in (None, "") or _decimal(other) == 0
    a, b = _decimal(cached), _decimal(computed)
    if a is not None and b is not None:
        if digits is not None:
            return round_half_up(a, digits) == round_half_up(b, digits)
        return abs(a - b) <= NEAR
    if isinstance(cached, (dt.datetime, dt.date)):
        cached = cached.isoformat()[:10]
    return str(cached).strip() == str(computed).strip()


def _date_digits(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y%m%d")
    return "".join(ch for ch in str(v) if ch.isdigit())


def _group_heads(d, vals, row_map, stops):
    """{(행, 열): 위 행 값}. 소계 묶음 열의 빈칸은 엑셀에서 「위와 같음」이므로 위 데이터 행의 값으로 읽는다. 소계 행(stops)을 넘어서는 채우지 않는다."""
    cols = {column_index_from_string(c["col"]) for c in d["columns"] if c["db"] in {s["group_by"] for s in d["summaries"] if s["group_by"]}}
    out = {}
    for col in cols:
        last, last_row = None, None
        for r in sorted(row_map.values()):
            if last_row is not None and any(last_row < s < r for s in stops):
                last = None
            value = vals.get((r, col))
            if value in (None, "") and last is not None:
                out[(r, col)] = last
            else:
                last = value
            last_row = r
    return out


def _compare_cells(d, vals, rows, row_map, heads, digits, report):
    name, by_seq = d["sheet"], {r["row_seq"]: r for r in rows}
    report["extra"] += [{"table": d["target"], "row_seq": s} for s in by_seq if s not in row_map]
    for seq, r in row_map.items():
        row = by_seq.get(seq)
        for c in d["columns"]:
            col, cell = column_index_from_string(c["col"]), f"{name}!{c['col']}{r}"
            cached = heads.get((r, col), vals.get((r, col)))
            if isinstance(cached, str) and cached.startswith("#REF"):
                report["ref_error"].append(cell)
            elif row is None or c["db"] not in row:
                report["missing"].append({"cell": cell, "excel": cached})
            elif _same(cached, row[c["db"]], digits.get((r, col))):
                report["same"] += 1
            else:
                report["diff"].append({"cell": cell, "excel": cached, "computed": row[c["db"]]})


def _compare_summaries(d, lines, vals, results, row_map, heads, digits, report):
    """소계 · 합계 행마다 calc.py 의 통계 표 행과 엑셀 셀을 비교한다. 이름 글자가 같은 소계 항목 하나로 짝짓는다.
    묶는 열이 있으면 그 행 바로 위 데이터 행의 묶는 열 값으로 통계 표 행을 찾는다."""
    letters = {c["db"]: c["col"] for c in d["columns"]}
    data = sorted(row_map.values())
    for line in lines:
        item = next(s for s in d["summaries"] if s["label"] == line["label"])
        group = None
        if item["group_by"]:
            above = [r for r in data if r < line["row"]]
            pos = (above[-1], column_index_from_string(letters[item["group_by"]])) if above else None
            group = heads.get(pos, vals.get(pos)) if pos else None
        found = next((x for x in results.get(item["target"], [])
                      if (item["label_col"] is None or _same(line["label"], x.get(item["label_col"]), None))
                      and (not item["group_by"] or _same(group, x.get(item["group_by"]), None))), None)
        for db in item["values"]:
            col = column_index_from_string(letters[db])
            cached, cell = vals.get((line["row"], col)), f"{d['sheet']}!{letters[db]}{line['row']}"
            if found is None:
                report["summary_missing"].append({"cell": cell, "excel": cached})
            elif not _same(cached, found.get(db), digits.get((line["row"], col))):
                report["summary_diff"].append({"cell": cell, "excel": cached, "computed": found.get(db)})


def _compare_dates(d, vals, results, report):
    if not d["date_columns"]:
        return
    rows = results.get(f"{d['target']}_dates") or [{}]
    r = d["header_rows"][1]
    for x in d["date_columns"]:
        cached = vals.get((r, column_index_from_string(x["col"])))
        computed = rows[0].get(f"t_plus_{x['rel']}")
        if computed is None or _date_digits(cached) != _date_digits(computed):
            report["dates_diff"].append({"cell": f"{d['sheet']}!{x['col']}{r}", "excel": cached, "computed": computed})


def display_digits(path, sheets):
    """셀의 표시 형식에 나오는 소수 자릿수 {시트: {(행, 열): 자릿수}}. 일반 형식 셀은 넣지 않는다. %는 값이 비율이라 두 자리를 더한다."""
    wb = openpyxl.load_workbook(path)
    out = {}
    for sheet in sheets:
        found = {}
        for row in wb[sheet].iter_rows():
            for c in row:
                fmt = c.number_format.split(";")[0]
                if c.value is None or fmt == "General" or not re.search(r"[0#]", fmt) or re.search(r"[ymd]", fmt, re.I):
                    continue
                m = re.search(r"\.([0#]+)", fmt)
                found[(c.row, c.column)] = (len(m[1]) if m else 0) + (2 if "%" in fmt else 0)
        out[sheet] = found
    wb.close()
    return out


def compare(book, definitions, results, row_map, digits=None):
    """결과표마다 대조한다. results 는 calc.py 반환값 {대상: 행 목록}(결과표 대상과 통계 표 대상), row_map 은 {대상: {row_seq: 엑셀 행}},
    digits 는 {시트: {(행, 열): 표시 자릿수}} 다."""
    report = {"same": 0, "diff": [], "missing": [], "extra": [], "ref_error": [], "summary_diff": [], "summary_missing": [], "dates_diff": []}
    for d in definitions:
        if d["role"] != "결과":
            continue
        vals, rows, seqs = book.sheet_values(d["sheet"]), results.get(d["target"], []), {int(k): v for k, v in row_map[d["target"]].items()}
        cell_digits = (digits or {}).get(d["sheet"], {})
        lines = table_plan.summary_lines(book, d)
        heads = _group_heads(d, vals, seqs, {x["row"] for x in lines})
        _compare_cells(d, vals, rows, seqs, heads, cell_digits, report)
        _compare_summaries(d, lines, vals, results, seqs, heads, cell_digits, report)
        _compare_dates(d, vals, results, report)
    return report


def passed(report):
    """다른 셀, 빠진 셀, 남는 행, 다른 소계 칸, 빠진 소계 행이 하나도 없어야 합격이다. #REF! 셀은 합격 판정에서 뺀다."""
    return not any(report[k] for k in ("diff", "missing", "extra", "summary_diff", "summary_missing", "dates_diff"))


def main(argv=None):
    """합격이면 0, 아니면 1 을 돌려준다."""
    ap = argparse.ArgumentParser(description="calc.py 결과를 엑셀 저장값과 셀 단위로 대조한다")
    ap.add_argument("excel")
    ap.add_argument("--plan", required=True)
    ap.add_argument("--results", required=True)
    ap.add_argument("--calc", required=True)
    ap.add_argument("--base-date", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--inputs", help="엑셀 저장값 대신 쓸 표 {표 이름: 행 목록}")
    a = ap.parse_args(argv)
    import initial_load
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8-sig"))
    results = json.loads(Path(a.results).read_text(encoding="utf-8-sig"))
    defs = [d for d in results["definitions"] if not d.get("orphan")]  # 분석기가 찾지 못한 표는 table_plan.build 처럼 뺀다
    book, by_name = initial_load.open_book(a.excel), {t["name"]: t for t in plan["tables"]}
    tables = {n: wire_values(r, by_name[n]["columns"]) for n, r in initial_load.rows(book, plan, defs, a.base_date).items() if by_name[n]["stage"] != "calc"}
    tables.update(json.loads(Path(a.inputs).read_text(encoding="utf-8-sig")) if a.inputs else {})
    computed = initial_load.load_calc(a.calc)(tables, dt.date.fromisoformat(a.base_date))
    row_map = {d["target"]: {i: r for i, r in enumerate(table_plan.data_rows(book, d), 1)} for d in defs if d["role"] == "결과"}
    report = compare(book, defs, computed, row_map, display_digits(a.excel, sorted({d["sheet"] for d in defs if d["role"] == "결과"})))
    Path(a.out).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    ok = passed(report)
    print(f"{'합격' if ok else '불합격'}: 같은 셀 {report['same']}, 다른 셀 {len(report['diff'])}, 빠진 셀 {len(report['missing'])}, 남는 행 {len(report['extra'])}, "
          f"다른 소계 칸 {len(report['summary_diff'])}, 빠진 소계 행 {len(report['summary_missing'])}. 자세한 내용: {a.out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
