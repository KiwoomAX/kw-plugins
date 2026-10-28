"""수식 하나를 조각으로 나눠, 셀 참조와 VLOOKUP · HLOOKUP 호출 자리에 실제 값을 넣는다.

값 조각에는 원본 셀 위치(ref)를 붙인다. 범위 참조는 글자로 두고 위치만 붙인다.
값을 어디서 읽고 참조를 어떻게 푸는지는 호출하는 쪽이 정한다. 설명기는 엑셀 파일에서,
대시보드 화면 백엔드는 snapshot 에서 읽는다.
"""
import datetime as dt
import math

from openpyxl.formula.tokenizer import Tokenizer

LOOKUPS = {"VLOOKUP(": "col", "HLOOKUP(": "row"}


def jsonable(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if hasattr(v, "item"):
        return v.item()
    return v


def segments(formula, sheet, pos, sheet_values, resolve):
    """sheet_values(시트) -> {(행, 열): 값}. resolve(참조 글자, 시트, (행, 열)) -> [(시트, 영역)] 이거나 그 밖(풀 수 없음)."""
    def where(text):
        found = resolve(text, sheet, pos)
        return found[0] if isinstance(found, list) and len(found) == 1 else None

    def value_at(s, r, c):
        return sheet_values(s).get((r, c))

    def single(area):
        """셀 하나를 가리키는가. 행 전체(5:5) · 열 전체(C:C)는 끝이 비어 있어 셀 하나가 아니다."""
        r1, c1, r2, c2 = area
        return None not in (r1, c1) and r1 == r2 and c1 == c2

    def number_of(tok):
        if tok.subtype == "NUMBER":
            return int(float(tok.value))
        if tok.subtype == "RANGE":
            loc = where(tok.value)
            if loc and single(loc[1]):
                v = value_at(loc[0], loc[1][0], loc[1][1])
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return int(v)
        return None

    def ref_json(s, area):
        return {"sheet": s, "area": list(area)}

    if formula.startswith("피벗 원본:"):
        src = formula.split(":", 1)[1].strip()
        loc = where(src)
        return {"formula": formula, "segments": [{"t": "피벗 합계 · 원본 "},
                                                 {"t": src, "ref": ref_json(*loc) if loc else None}]}
    try:
        tokens = Tokenizer(formula).items
    except Exception:
        return {"formula": formula, "segments": [{"t": formula}]}

    def lookup(args, axis):
        """VLOOKUP(키, 표, n[, FALSE]) 를 계산해 (값, 시트, 행, 열) 을 돌려준다. 못 풀면 None."""
        if len(args) < 3 or len(args[1]) != 1 or len(args[2]) != 1:
            return None
        n = number_of(args[2][0])  # 돌려줄 열(행) 번호. 숫자이거나 숫자가 든 셀 참조다
        if n is None:
            return None
        key_tok, table = args[0], where(args[1][0].value)
        if table is None or len(key_tok) != 1:
            return None
        if key_tok[0].subtype == "RANGE":
            loc = where(key_tok[0].value)
            if not loc:
                return None
            key = value_at(loc[0], loc[1][0], loc[1][1])
        else:
            key = key_tok[0].value.strip('"')
        t_sheet, (r1, c1, r2, c2) = table
        for (r, c), v in sorted(sheet_values(t_sheet).items()):
            first = c == c1 if axis == "col" else r == r1
            inside = (r1 is None or r1 <= r <= r2) and (c1 is None or c1 <= c <= c2)
            if first and inside and key is not None and str(v).upper() == str(key).upper():  # 엑셀처럼 대소문자를 가리지 않는다
                tr, tc = (r, c1 + n - 1) if axis == "col" else (r1 + n - 1, c)
                return value_at(t_sheet, tr, tc), t_sheet, tr, tc
        return None

    segs, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "FUNC" and tok.subtype == "OPEN" and tok.value.upper() in LOOKUPS:
            depth, j, args = 1, i + 1, [[]]
            while j < len(tokens) and depth:
                t = tokens[j]
                if t.type == "FUNC" and t.subtype == "OPEN":
                    depth += 1
                elif t.type == "FUNC" and t.subtype == "CLOSE":
                    depth -= 1
                if depth == 1 and t.type == "SEP" and t.subtype == "ARG":
                    args.append([])
                elif depth and t.type != "WHITE-SPACE":
                    args[-1].append(t)
                j += 1
            text = "".join(t.value for t in tokens[i:j])
            hit = lookup(args, LOOKUPS[tok.value.upper()])
            if hit:
                v, hs, hr, hc = hit
                segs.append({"v": jsonable(v), "src": text, "ref": ref_json(hs, (hr, hc, hr, hc))})
            else:
                segs.append({"t": text})
            i = j
            continue
        if tok.type == "OPERAND" and tok.subtype == "RANGE":
            loc = where(tok.value)
            if loc and single(loc[1]):
                segs.append({"v": jsonable(value_at(loc[0], loc[1][0], loc[1][1])), "src": tok.value,
                             "ref": ref_json(*loc)})
            else:
                segs.append({"t": tok.value, "ref": ref_json(*loc) if loc else None})
        else:
            segs.append({"t": tok.value})
        i += 1
    return {"formula": formula, "segments": [{"t": "="}] + segs}
