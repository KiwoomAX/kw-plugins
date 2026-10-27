"""「확인 필요한 사항」 화면의 목록을 만든다. 계산 묶음에서 벗어나는 행, 수식 없이 값이 같은 열, 분석이 모호했던 상황이다.

목록마다 상한이 있고 넘는 수는 more 에 둔다. 상한과 60% · 3개 · 5개 · 80% 기준은 목업에서 쓴 값이며 근거는 없다.
"""
from collections import Counter

from openpyxl.formula import Tokenizer

from explain_cell import a1, col_name, show
from plain_text import label, line_roles
from tables import is_constant_formula

ODD_MAX, SAME_MAX, AMBIGUOUS_MAX = 20, 15, 20
UNPLACED = {"시트 모름": ("매크로 시트", "매크로가 어느 시트에 값을 넣는지 알려 주세요."),
            "범위 모름": ("연결 범위", "이 연결이 값을 넣는 시트와 범위를 찾지 못했습니다. 어느 표에 값을 넣는지 알려 주세요."),
            "처리 오류": ("연결 읽기", "엑셀의 데이터 연결을 읽지 못했습니다. 원천 데이터 출처 판정이 틀릴 수 있습니다.")}
ODD_MIN, ODD_SHARE = 3, 0.6
SAME_MIN, SAME_SHARE = 5, 0.8
REF_TEXT = {"broken": "참조가 깨져 있어 어느 셀을 읽는지 알 수 없습니다.",
            "dynamic": "INDIRECT · OFFSET 으로 읽는 셀은 실행할 때 정해지므로 분석기가 따라가지 못했습니다.",
            "past_sheet": "분석하지 않는 과거 날짜 시트를 읽습니다. 이 연결은 흐름에 넣지 않았습니다."}


def _capped(items, limit):
    return {"items": items[:limit], "more": max(0, len(items) - limit)}


def _formula(book, sheet, pos):
    """상수만 적힌 수식은 값으로 보므로 None."""
    f = book.formula(sheet, pos)
    return f if f and not is_constant_formula(f) else None


def _role(formula):
    """RANK(..)+MAX(..) 도 순위다. 역할이 없는 수식(글자 잇기 등)은 「수식」."""
    return " → ".join(line_roles(formula)) or "수식"


def _column(t, c):
    return (t["header"][c - t["area"][1]] if t["header"] else None) or f"{col_name(c)}열"


def _rows(t):
    r1, _, r2, _ = t["area"]
    return range((t["header_row"] or r1 - 1) + 1, r2 + 1)


def odd_rows(book, tables):
    """열 셀의 60% 이상이 같은 역할이면, 역할이 다른 셀과 값 셀을 모은다. 머리글 글자와 같은 값은 뺀다."""
    heads = {}
    for t in tables:
        heads.setdefault(t["sheet"], set()).update(h for h in t["header"] or () if h)
    items = []
    for t in tables:
        sheet, cells, vals = t["sheet"], book.cells.get(t["sheet"], {}), book.sheet_values(t["sheet"])
        for c in range(t["area"][1], t["area"][3] + 1):
            got = []  # (위치, 역할 또는 None, 수식)
            for r in _rows(t):
                if (r, c) not in cells or (sheet, (r, c)) in book.pivot_at:
                    continue
                f = _formula(book, sheet, (r, c))
                if f or (r, c) in vals:
                    got.append(((r, c), _role(f) if f else None, f))
            if len(got) < ODD_MIN:
                continue
            role, n = Counter(x[1] for x in got).most_common(1)[0]
            if role is None or n / len(got) < ODD_SHARE:
                continue
            usual = next(f for _, x, f in got if x == role)
            for pos, x, f in got:
                if x == role:
                    continue
                v = vals.get(pos)
                if f is None and str(v).strip() in heads.get(sheet, ()):
                    continue
                items.append({"sheet": sheet, "cell": a1(*pos), "column": _column(t, c), "usual": usual,
                              "got": f if f else f"값 「{show(v)}」"})
    return _capped(items, ODD_MAX)


def _keep(v):
    """소수만 비교한다. 정수 · 0(순위, 개수)과 글자(구분 이름)는 어느 표에서나 겹치므로 뺀다."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or float(v).is_integer():
        return None
    return round(float(v), 10)


def same_value_columns(book, tables_by_sheet, date_groups):
    """수식이 없는 두 열이 같은 소수를 5개 이상, 작은 열 값의 80% 이상 보유하면 묻는다. 날짜 시트는 기준과 바로 이전 시트만 본다."""
    dated = {s for g in date_groups for s in g["sheets"]}
    keep_dated = {s for g in date_groups for s in (g["base"], g["previous"])}
    columns = []  # (표, 열 번호, 값 집합)
    for sheet, found in tables_by_sheet.items():
        if sheet in dated and sheet not in keep_dated:
            continue
        vals = book.sheet_values(sheet)
        for t in found:
            for c in range(t["area"][1], t["area"][3] + 1):
                if any(_formula(book, sheet, (r, c)) for r in _rows(t)):
                    continue
                got = {k for r in _rows(t) if (k := _keep(vals.get((r, c)))) is not None}
                if len(got) >= SAME_MIN:
                    columns.append((t, c, got))
    owners = {}  # 값 → 그 값을 보유한 열 번호 목록
    for i, (_, _, got) in enumerate(columns):
        for v in got:
            owners.setdefault(v, []).append(i)
    shared = Counter()
    for idx in owners.values():
        for x in range(len(idx)):
            for y in range(x + 1, len(idx)):
                shared[(idx[x], idx[y])] += 1
    items = []
    for (i, j), n in sorted(shared.items()):
        (ta, ca, va), (tb, cb, vb) = columns[i], columns[j]
        if n < SAME_MIN or n < SAME_SHARE * min(len(va), len(vb)):
            continue
        text = (f"「{ta['sheet']}」 시트 {label(ta, {}, [])}의 「{_column(ta, ca)}」 값 {n}개가 "
                f"「{tb['sheet']}」 시트 {label(tb, {}, [])}의 「{_column(tb, cb)}」 값과 같습니다. "
                "두 열 사이에 수식 연결은 없습니다. 같은 값을 옮겨 붙이는 연결이 맞습니까?")
        items.append({"text": text, "a": f"{ta['sheet']}!{col_name(ca)}열", "b": f"{tb['sheet']}!{col_name(cb)}열", "count": n})
    return _capped(items, SAME_MAX)


def _tokens(formula):
    try:
        return [t for t in Tokenizer(formula).items if t.type != "WHITE-SPACE"]
    except Exception:
        return None


def _only_numbers_differ(f1, f2):
    t1, t2 = _tokens(f1), _tokens(f2)
    if not t1 or not t2 or len(t1) != len(t2):
        return False
    diff = False
    for a, b in zip(t1, t2):
        if (a.type, a.subtype) != (b.type, b.subtype):
            return False
        if a.value != b.value:
            if a.subtype != "NUMBER":
                return False
            diff = True
    return diff


def ambiguous(book, odd_refs, nameless, date_groups):
    """분석기가 판단하지 못한 상황. 참조, 과거 시트, 이름 없는 범위, 기준값, 매크로 시트 순이다."""
    items = [{"kind": "과거 시트" if o["why"] == "past_sheet" else "참조", "where": f"{o['sheet']}!{o['cell']}",
              "text": REF_TEXT[o["why"]]} for o in odd_refs]
    items += [{"kind": "이름 없는 범위", "where": n, "text": "결과표가 머리글 행이 없는 범위를 읽습니다."} for n in nameless]
    for g in date_groups:
        base, prev = book.cells.get(g["base"], {}), g["previous"]
        for pos in sorted(base):
            f1, f2 = book.formula(prev, pos) if pos in book.cells.get(prev, {}) else None, book.formula(g["base"], pos)
            if f1 and f2 and _only_numbers_differ(f1, f2):
                items.append({"kind": "기준값", "where": f"{g['base']}!{a1(*pos)}",
                              "text": "매주 바뀌는 기준값입니까? 정해진 규칙이 있습니까?"})
    items += [{"kind": UNPLACED[u.get("why", "시트 모름")][0], "where": u["location"],
               "text": UNPLACED[u.get("why", "시트 모름")][1]} for u in book.unplaced]
    return _capped(items, AMBIGUOUS_MAX)
