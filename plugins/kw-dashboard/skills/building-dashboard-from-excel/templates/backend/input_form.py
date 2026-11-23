"""입력 양식을 만들고, 올린 양식을 검사한다. 검사는 어떤 저장보다 먼저 실행한다.

양식의 시트는 수기 입력 표 · 외부 데이터 표마다 하나이고 마지막에 「매개변수」 시트가 있다.
각 표의 첫 값은 A1 에 놓이고, 행은 엑셀 주소 없이 행 ID 로 구분한다.
"""
import datetime as dt
import io
import zipfile

import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

SKIP = {"base_date", "base_time", "loaded_at", "row_id"}
ROW_ID = "행 ID"
PARAMETERS = "매개변수"


def _editable(plan):
    return [t for t in plan["tables"] if t.get("editable")]


def _sheet_name(table):
    return table["name"].rsplit("__", 1)[-1][:31]


def _columns(table):
    return [c for c in table["columns"] if c["name"] not in SKIP]


def _cell(value, column):
    """양식에 쓸 값. 샌드박스의 소수는 글자로 오므로 숫자로 바꾼다."""
    if value is None:
        return None
    return float(value) if column["type"] == "numeric" else value


def make(plan, values, parameters):
    """양식 엑셀 파일 내용(bytes). values 는 {표 이름: 행 목록}, parameters 는 {이름: 값} 이다."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for t in _editable(plan):
        ws = wb.create_sheet(_sheet_name(t))
        columns = _columns(t)
        ws.append([ROW_ID] + [c["name"] for c in columns])
        for row in values.get(t["name"], []):
            ws.append([row["row_id"]] + [_cell(row.get(c["name"]), c) for c in columns])
    ws = wb.create_sheet(PARAMETERS)
    ws.append(["이름", "값"])
    for name, value in parameters.items():
        ws.append([name, value])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _date_text(v):
    """날짜 값을 YYYY-MM-DD 글자로 바꾼다. 날짜가 아니면 None."""
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()[:10]
    try:
        return dt.date.fromisoformat(str(v).strip()).isoformat()
    except ValueError:
        return None


def _converted(value, column):
    """(저장할 값, 오류 문구). 빈 칸은 그대로 비워 둔다."""
    if value is None or value == "":
        return None, None
    if column["type"] == "numeric":
        return (value, None) if _number(value) else (None, "숫자가 아닙니다")
    if column["type"] == "date":
        text = _date_text(value)
        return (text, None) if text else (None, "날짜 형식이 아닙니다")
    return str(value).strip(), None


def _check_sheet(table, ws, previous, errors):
    """표 하나를 검사한다. 저장할 행 목록을 돌려준다."""
    name, columns = ws.title, _columns(table)
    errors += [{"sheet": name, "cell": str(m), "reason": "병합된 셀이 있습니다"} for m in ws.merged_cells.ranges]
    for i, want in enumerate([ROW_ID] + [c["name"] for c in columns], 1):
        if ws.cell(1, i).value != want:
            errors.append({"sheet": name, "cell": f"{get_column_letter(i)}1", "reason": f"열이 바뀌었습니다({want})"})
    rows, seen, next_id = [], set(), max(previous, default=0) + 1
    for r in range(2, ws.max_row + 1):
        cells = [ws.cell(r, i + 2).value for i in range(len(columns))]
        row_id = ws.cell(r, 1).value
        if row_id is None and all(v is None for v in cells):
            continue
        if row_id is None or row_id not in previous:
            if not table.get("row_config"):
                errors.append({"sheet": name, "cell": f"A{r}", "reason": "행을 추가할 수 없는 시트입니다"})
                continue
            row_id, next_id = next_id, next_id + 1
        elif row_id in seen:  # 행을 복사해 붙이면 행 ID 도 함께 복사된다
            if not table.get("row_config"):
                errors.append({"sheet": name, "cell": f"A{r}", "reason": f"같은 행 ID 가 두 번 있습니다({row_id})"})
                continue
            row_id, next_id = next_id, next_id + 1
        seen.add(row_id)
        row = {"row_id": row_id}
        for i, column in enumerate(columns):
            row[column["name"]], reason = _converted(cells[i], column)
            if reason:
                errors.append({"sheet": name, "cell": f"{get_column_letter(i + 2)}{r}", "reason": reason})
        rows.append(row)
    if not table.get("row_config"):  # 행을 추가하는 시트는 행을 지워도 된다. 지운 행은 이 기준일에서 빠지고 지난 기준일 값은 남는다
        errors += [{"sheet": name, "cell": f"행 ID {x}", "reason": "지워진 행이 있습니다"} for x in previous if x not in seen]
    return rows


def check(plan, data, previous_row_ids):
    """{"errors": [{sheet, cell, reason}], "tables": {표 이름: 행}, "parameters": {...}}. errors 가 있으면 아무것도 저장하지 않는다.
    previous_row_ids 는 {표 이름: 양식을 채운 기준일의 행 ID 목록} 이다. 새 기준일은 직전 기준일 값을 넘긴다."""
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError):
        return {"errors": [{"sheet": "", "cell": "", "reason": "엑셀 파일이 아닙니다"}], "tables": {}, "parameters": {}}
    errors, tables = [], {}
    for t in _editable(plan):
        name = _sheet_name(t)
        if name not in wb.sheetnames:
            errors.append({"sheet": name, "cell": "", "reason": "시트가 없습니다"})
            continue
        tables[t["name"]] = _check_sheet(t, wb[name], previous_row_ids.get(t["name"], []), errors)
    parameters = {}
    if PARAMETERS in wb.sheetnames:
        parameters = {r[0]: r[1] for r in wb[PARAMETERS].iter_rows(min_row=2, values_only=True) if r[0] is not None}
    else:
        errors.append({"sheet": PARAMETERS, "cell": "", "reason": "시트가 없습니다"})
    return {"errors": errors, "tables": tables, "parameters": parameters}
