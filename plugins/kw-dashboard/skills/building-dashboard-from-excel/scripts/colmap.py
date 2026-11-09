"""엑셀 원천 표의 열마다 같은 값을 가진 쿼리 응답 열과 변환을 찾는다. 키 열로 행을 맞춘 뒤 값 일치율을 본다."""
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

MATCH = 0.8  # 같은 열로 보는 값 일치율(근거 없는 시작 값)
TRANSFORMS = {"same": lambda x: x, "/1e8": lambda x: x / 1e8, "round(/1e8)": lambda x: round(x / 1e8), "*100": lambda x: x * 100, "/100": lambda x: x / 100}


def round_half_up(value, digits):
    """화면처럼 사사오입한다. 파이썬 round 는 0.005 경계에서 다르게 반올림한다."""
    return Decimal(repr(value) if isinstance(value, float) else str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


def _key(v):
    return str(v).strip().lstrip("0") if v is not None else ""


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


def _equal(a, b):
    a, b = 0 if a in (None, "") else a, 0 if b in (None, "") else b
    x, y = _number(a), _number(b)
    if x is not None and y is not None:
        return abs(x - y) <= max(0.006, abs(y) * 1e-6)
    return str(_norm(a)).strip() == str(_norm(b)).strip()


def _score(pairs, excel_col, query_col, name):
    ok = n = 0
    for e, q in pairs:
        x, y = e.get(excel_col), q.get(query_col)
        if name != "same":
            y = _number(y)
            y = TRANSFORMS[name](y) if y is not None else None
        n += 1
        ok += _equal(x, y)
    return ok / n if n else 0


def match(excel_rows, query_rows, key_columns):
    """{"mapped": {엑셀 열: {"column", "transform", "match"}}, "missing": [엑셀 열]}. 빈 값은 0 으로 보고, 둘 다 빈 열은 이름으로 맞춘다."""
    excel_key, query_key = key_columns
    by_key = {_key(r.get(query_key)): r for r in query_rows}
    pairs = [(r, by_key[_key(r.get(excel_key))]) for r in excel_rows if _key(r.get(excel_key)) in by_key]
    columns = [c for c in (query_rows[0] if query_rows else {}) if c != query_key]
    mapped, missing = {}, []
    for col in (c for c in (excel_rows[0] if excel_rows else {}) if c != excel_key):
        if all(e.get(col) in (None, "", 0) for e, _ in pairs):
            named = col if col in columns else next((c for c in columns if all(q.get(c) in (None, "", 0) for _, q in pairs)), None)
            if named:
                mapped[col] = {"column": named, "transform": "same", "match": 1.0}
            else:
                missing.append(col)
            continue
        best = max(((_score(pairs, col, c, t), c, t) for c in columns for t in TRANSFORMS), key=lambda x: x[0], default=(0, None, None))
        if best[0] >= MATCH:
            mapped[col] = {"column": best[1], "transform": best[2], "match": best[0]}
        else:
            missing.append(col)
    return {"mapped": mapped, "missing": missing}
