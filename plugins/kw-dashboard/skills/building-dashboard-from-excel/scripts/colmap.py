"""엑셀 원천 표와 쿼리 응답을 개발자가 정한 열 대응대로 대조한다. 키 열로 행을 짝지은 뒤 열마다 같은 행 수를 센다.

어느 응답 열이 어느 표 열인지는 찾지 않는다. 엑셀 모양은 끝이 없어 규칙으로 찾을 수 없으므로 Claude 가 제안하고 개발자가 정한다.
"""
import datetime as dt
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "templates/backend"))
import transform  # noqa: E402  운영 서버와 같은 변환 계산을 쓴다


def round_half_up(value, digits):
    """화면처럼 사사오입한다. 파이썬 round 는 0.005 경계에서 다르게 반올림한다."""
    return Decimal(repr(value) if isinstance(value, float) else str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def _key(v):
    """키 비교용 글자. 앞의 0 은 떼되, 0 으로만 된 값은 "0" 으로 남긴다. 빈 값은 키가 없는 행이다."""
    s = str(v).strip() if v is not None else ""
    return s.lstrip("0") or ("0" if s else "")


def _number(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _norm(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y%m%d")
    if isinstance(v, str):
        s = v.strip()
        return s.replace("-", "").replace(".", "") if len(s) in (8, 10) and s[:2] in ("19", "20") else s
    return v


def _tolerance(x):
    """엑셀 값의 소수 자릿수 반 단위(1.23 은 0.005, 0.0123 은 0.00005). 화면에서 반올림해 붙여 넣은 값을 맞추되 0.006 을 넘지 않는다."""
    exponent = Decimal(repr(x) if isinstance(x, float) else str(x)).as_tuple().exponent
    return min(0.006, 0.5 * 10 ** exponent) if isinstance(exponent, int) and exponent < 0 else 0.006


def _equal(a, b):
    a, b = 0 if a in (None, "") else a, 0 if b in (None, "") else b
    x, y = _number(a), _number(b)
    if x is not None and y is not None:
        return abs(x - y) <= max(_tolerance(x), abs(y) * 1e-6)
    return str(_norm(a)).strip() == str(_norm(b)).strip()


def _keyed(row, columns):
    return tuple(_key(row.get(c)) for c in columns)


def pair_rows(excel_rows, response_rows, keys):
    """(짝 [(엑셀 행, 응답 행)], 응답 키별 행 수). keys 는 [(엑셀 열, 응답 열)] 이다. 키가 비었거나 응답에 없는 엑셀 행은 짝이 없다."""
    excel_keys, response_keys = [e for e, _ in keys], [r for _, r in keys]
    count = {}
    for r in response_rows:
        count[_keyed(r, response_keys)] = count.get(_keyed(r, response_keys), 0) + 1
    by_key = {_keyed(r, response_keys): r for r in response_rows}
    return [(e, by_key[_keyed(e, excel_keys)]) for e in excel_rows if all(_keyed(e, excel_keys)) and _keyed(e, excel_keys) in by_key], count


def compare(excel_rows, response_rows, keys, mapping, limit=3):
    """{"checked": {표 열: {column, transform, same, rows, diff}}, "unmatched_rows": 개수, "repeated_keys": 개수}.
    keys 는 [(엑셀 열, 응답 열)], mapping 은 {표 열: (응답 열, 변환)}. diff 는 값이 다른 행을 limit 개까지 보인다.
    unmatched_rows 는 키가 응답에 없는 엑셀 행 수, repeated_keys 는 키가 겹쳐 짝을 정할 수 없는 응답 행 수다."""
    excel_keys = [e for e, _ in keys]
    pairs, count = pair_rows(excel_rows, response_rows, keys)
    checked = {}
    for col, (column, name) in mapping.items():
        same, diff = 0, []
        for e, q in pairs:
            y = q.get(column)
            if name != "same" and y not in (None, ""):
                y = float(transform.apply(name, y))
            if _equal(e.get(col), y):
                same += 1
            elif len(diff) < limit:
                diff.append({"key": [e.get(k) for k in excel_keys], "excel": e.get(col), "response": q.get(column)})
        checked[col] = {"column": column, "transform": name, "same": same, "rows": len(pairs), "diff": diff}
    return {"checked": checked, "unmatched_rows": len(excel_rows) - len(pairs), "repeated_keys": sum(n for n in count.values() if n > 1)}
