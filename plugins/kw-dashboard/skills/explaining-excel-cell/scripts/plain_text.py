"""수식을 역할과 쉬운 문장으로 푼다. 엑셀을 처음 보는 사람이 읽는 문장이다.

문장은 시트 이름, 표 이름, 위치, 찾는 열과 가져오는 열을 모두 적는다. 수식에 없는 동작은 지어내지 않는다.
풀 수 있는 형식(VLOOKUP 정확히 찾기, 0이면 빈 셀로 두는 IF, RANK)이 아니면 FALLBACK 문장을 쓴다.
"""
import re

from openpyxl.formula import Tokenizer
from openpyxl.formula.translate import Translator

from explain_cell import a1, col_name, show

FALLBACK = "「{col}」 셀은 수식으로 계산됩니다."
ROLE_OF = {**dict.fromkeys(("VLOOKUP", "HLOOKUP", "INDEX", "MATCH", "XLOOKUP"), "찾아 채우기"),
           **dict.fromkeys(("IF", "IFS"), "기준 비교"),
           **dict.fromkeys(("RANK", "RANK.EQ", "LARGE", "SMALL"), "순위"),
           **dict.fromkeys(("SUM", "SUMIF", "SUMIFS", "AVERAGE", "STDEV", "STDEV.S", "STDEV.P"), "계산")}
REF = r"\$?[A-Z]{1,3}\$?\d+"
VL = (rf"VLOOKUP\((?P<key>{REF}),(?P<sheet>'[^']+'!|[^,'!()]+!)?(?P<area>\$?[A-Z]{{1,3}}\$?\d*:\$?[A-Z]{{1,3}}\$?\d*),"
      rf"(?P<idx>\d+|{REF}),(?:FALSE|0)\)")
RANK = re.compile(rf"^=(?P<ie>IFERROR\()?RANK\((?P<x>{REF}),(?P<rng>[^,()]+)(?:,(?P<ord>[01]))?\)"
                  r"(?P<max>\+MAX\([^()]+\))?(?(ie),\"\"\))$")


def roles(formula):
    """함수와 연산자 단위로 판정한 역할 목록. 안쪽 함수가 먼저다. 셀 하나만 읽으면 「옮기기」."""
    try:
        tokens = [t for t in Tokenizer(formula).items if t.type != "WHITE-SPACE"]
    except Exception:
        return []
    if len(tokens) == 1 and tokens[0].type == "OPERAND" and tokens[0].subtype == "RANGE":
        return ["옮기기"]
    out, stack = [], []
    for t in tokens:
        if t.type == "FUNC" and t.subtype == "OPEN":
            stack.append(t.value[:-1].upper())
        elif t.type == "FUNC" and t.subtype == "CLOSE" and stack:
            role = ROLE_OF.get(stack.pop())
            if role and role not in out:
                out.append(role)
        elif t.type == "OPERATOR-INFIX" and t.value in "+-*/" and "계산" not in out:
            out.append("계산")
    return out


def line_roles(formula):
    """화면에 보이는 역할 목록. RANK(..)+MAX(..) 는 이어 매기는 순위이므로 「순위」 하나다."""
    if RANK.match(re.sub(r"\s+", "", formula)):
        return ["순위"]
    return roles(formula)


def shape(formula, origin):
    """수식 형태: 상대 위치로 맞춘 뒤 셀 주소를 뺀 모양. 같은 일을 하는 수식을 세는 데 쓴다."""
    try:
        moved = Translator(formula, origin=origin).translate_formula("ZZ100000")
    except Exception:
        moved = formula
    return re.sub(REF, "<셀>", moved)


def _col(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _pos(ref):
    m = re.match(r"\$?([A-Z]{1,3})\$?(\d+)", ref)
    return int(m.group(2)), _col(m.group(1))


def _table_at(found, sheet, pos):
    return next((t for t in found if t["sheet"] == sheet and t["area"][0] <= pos[0] <= t["area"][2]
                 and t["area"][1] <= pos[1] <= t["area"][3]), None)


def _header(found, sheet, pos):
    t = _table_at(found, sheet, pos)
    if t and t["header"]:
        h = t["header"][pos[1] - t["area"][1]]
        if h:
            return h
    return None


def _group_of(groups, t):
    return next((g for g in groups if any(x["id"] == t["id"] for x in g["tables"])), None)


def label(t, names, groups):
    """찾는 범위 문장에 쓰는 표 이름. 「계산용 순위표(N2:Q3)」, 이름이 없으면 「표(A1:C4)」 · 「이름 없는 범위(A1:A3)」."""
    g = _group_of(groups, t)
    name = names.get(g["id"]) if g else None
    r1, c1, r2, c2 = t["area"]
    return f"{name or ('표' if t['header'] else '이름 없는 범위')}({a1(r1, c1)}:{a1(r2, c2)})"


def _vlookup(book, sheet, pos, m, found, names, groups):
    own = _header(found, sheet, pos) or f"{col_name(pos[1])}열"
    key = _pos(m.group("key"))
    keyh = _header(found, sheet, key) or f"{col_name(key[1])}열"
    other = (m.group("sheet") or "").rstrip("!").strip("'") or sheet
    area = m.group("area").replace("$", "")
    a, b = area.split(":")
    ma, mb = re.match(r"([A-Z]+)(\d*)", a), re.match(r"([A-Z]+)(\d*)", b)
    rect = (int(ma.group(2)) if ma.group(2) else None, _col(ma.group(1)), int(mb.group(2)) if mb.group(2) else None, _col(mb.group(1)))
    idx = m.group("idx")
    n = int(idx) if idx.isdigit() else book.sheet_values(sheet).get(_pos(idx))
    if not isinstance(n, (int, float)):
        return None
    import tables as tb
    hits = [t for t in found if t["sheet"] == other and tb._overlap(t["area"], rect)]
    if not hits:
        return None
    first = hits[0]
    keycol = _header(found, other, (first["area"][0] + 1, rect[1])) if first["header"] else None
    target = _header(found, other, (first["area"][0] + 1, rect[1] + int(n) - 1)) if first["header"] else None
    if len(hits) == 1:
        text = f"「{own}」 셀은 이 행의 「{keyh}」 값을 「{other}」 시트의 {label(first, names, groups)}에서 찾습니다."
    else:
        g = _group_of(groups, first)
        text = (f"「{own}」 셀은 이 행의 「{keyh}」 값을 「{other}」 시트의 {area} 범위에서 찾습니다. "
                f"이 범위는 {(names.get(g['id']) if g else None) or '표'} {len(hits)}개를 이어 붙인 범위입니다.")
    if keycol:
        text += f" 찾는 열은 「{keycol}」 열입니다."
    text += f" 찾은 행의 「{target or str(int(n)) + '번째 열'}」 값을 가져옵니다."
    vals = book.sheet_values(sheet)
    return text, f"예: 「{show(vals.get(key, ''))}」 → 「{show(vals.get(pos, ''))}」"


def _rank_is_plain(m, pos):
    """_rank 문장이 수식과 맞는가. 순위 범위가 같은 시트이고, +MAX 가 있으면 그 범위가 이 셀보다 아래에서 시작해야 한다."""
    if "!" in m.group("rng"):
        return False
    if m.group("max"):
        rows = re.findall(r"\$?[A-Z]{1,3}\$?(\d+)", m.group("max"))
        return bool(rows) and int(rows[0]) > pos[0]
    return True


def _rank(book, sheet, pos, m, found):
    own = _header(found, sheet, pos) or f"{col_name(pos[1])}열"
    x = _pos(m.group("x"))
    ch = _header(found, sheet, x) or f"{col_name(x[1])}열"
    text = f"「{own}」 셀은 같은 표 안에서 「{ch}」 값이 {'작은' if m.group('ord') == '1' else '큰'} 것부터 1위로 순위를 매깁니다."
    if m.group("max"):
        text += " 아래 묶음의 가장 큰 순위 다음 번호부터 이어서 매깁니다."
    if m.group("ie"):
        text += " 순위를 매길 수 없으면 빈 셀로 둡니다."
    return text, f"예: {show(book.sheet_values(sheet).get(pos, ''))}위"


def sentence(book, sheet, cell, found, names, groups):
    """(쉬운 문장, 실제 값 예). found 는 표 목록, names 는 묶음 번호 → 이름, groups 는 표 묶음."""
    m = re.match(r"\$?([A-Z]{1,3})\$?(\d+)$", cell)
    pos = (int(m.group(2)), _col(m.group(1)))
    # 공백을 지우되 따옴표 안(시트 이름 '2026년 7월5주', 글자 " ")은 그대로 둔다
    formula = "".join(p if p[:1] in "'\"" else re.sub(r"\s+", "", p)
                      for p in re.split(r"('[^']*'|\"[^\"]*\")", book.formula(sheet, pos) or ""))
    vl = re.fullmatch(rf"={VL}", formula)
    iv = re.fullmatch(rf"=IF\({VL}<>0,(?P<again>VLOOKUP\([^()]*\)),\"\"\)", formula)
    if iv and iv.group("again") == iv.group(0)[4:].split("<>0,")[0]:
        got = _vlookup(book, sheet, pos, iv, found, names, groups)
        if got:
            return got[0] + " 가져온 값이 0이면 빈 셀로 둡니다.", got[1]
    if vl:
        got = _vlookup(book, sheet, pos, vl, found, names, groups)
        if got:
            return got
    rk = RANK.match(formula)
    if rk and _rank_is_plain(rk, pos):
        return _rank(book, sheet, pos, rk, found)
    own = _header(found, sheet, pos) or f"{col_name(pos[1])}열"
    return FALLBACK.format(col=own), f"예: {show(book.sheet_values(sheet).get(pos, ''))}"


def _names(sheets):
    return ", ".join(f"「{s}」" for s in sheets)


def flow_summary(source_sheets, calc_sheets, result_sheet):
    """원천 · 계산 · 결과를 한 문장씩. 원천과 계산 시트가 없으면 「다른 시트를 읽지 않습니다」 한 문장."""
    if not source_sheets and not calc_sheets:
        return [f"「{result_sheet}」 시트는 다른 시트를 읽지 않습니다."]
    out = []
    if source_sheets:
        out.append(f"{_names(source_sheets)} 시트의 값이 원천 데이터입니다.")
    if calc_sheets:
        out.append(f"{_names(calc_sheets)} 시트가 {'원천 데이터로 ' if source_sheets else ''}계산합니다.")
    out.append(f"「{result_sheet}」 시트가 결과표입니다.")
    return out


def card_text(group):
    """카드 제목 아래 한 문장."""
    ts = group["tables"]
    if len(ts) > 1:
        return f"「{group['sheet']}」 시트에 같은 모양의 표 {len(ts)}개가 있습니다."
    r1, c1, r2, c2 = ts[0]["area"]
    return f"「{group['sheet']}」 시트의 표({a1(r1, c1)}:{a1(r2, c2)})입니다."
