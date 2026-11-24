"""엑셀 원천 표의 열마다 같은 값을 가진 쿼리 응답 열과 변환을 찾는다. 키 열로 행을 맞춘 뒤 값 일치율을 본다."""
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

MATCH = 0.8  # 같은 열로 보는 값 일치율(근거 없는 시작 값)
def round_half_up(value, digits):
    """화면처럼 사사오입한다. 파이썬 round 는 0.005 경계에서 다르게 반올림한다."""
    return Decimal(repr(value) if isinstance(value, float) else str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)


TRANSFORMS = {"same": lambda x: x, "/1e8": lambda x: x / 1e8, "round(/1e8)": lambda x: int(round_half_up(x / 1e8, 0)), "*100": lambda x: x * 100, "/100": lambda x: x / 100}


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
    """{"mapped": {엑셀 열: {"column", "transform", "match"}}, "missing": [엑셀 열]}. 빈 값은 0 으로 보고, 엑셀 열이 비었으면 이름이 같은 응답 열에만 맞춘다.
    가장 잘 맞는 응답 열이 둘 이상이면 고르지 않고 missing 으로 둔다."""
    excel_key, query_key = key_columns
    by_key = {_key(r.get(query_key)): r for r in query_rows}
    pairs = [(r, by_key[_key(r.get(excel_key))]) for r in excel_rows if _key(r.get(excel_key)) in by_key]
    columns = [c for c in (query_rows[0] if query_rows else {}) if c != query_key]
    mapped, missing = {}, []
    for col in (c for c in (excel_rows[0] if excel_rows else {}) if c != excel_key):
        if all(e.get(col) in (None, "", 0) for e, _ in pairs):
            if col in columns:
                mapped[col] = {"column": col, "transform": "same", "match": 1.0}
            else:
                missing.append(col)
            continue
        scores = [(_score(pairs, col, c, t), c, t) for c in columns for t in TRANSFORMS]
        best = max(scores, key=lambda x: x[0], default=(0, None, None))
        tied = {c for score, c, _ in scores if score == best[0]}
        if best[0] >= MATCH and len(tied) == 1:
            mapped[col] = {"column": best[1], "transform": best[2], "match": best[0]}
        else:
            missing.append(col)
    return {"mapped": mapped, "missing": missing}
