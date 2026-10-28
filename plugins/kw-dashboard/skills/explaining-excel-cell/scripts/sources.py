"""원천 표 묶음의 열마다 데이터가 어디서 오는지 정하고, 판정 근거 문장을 만든다.

쿼리 · 매크로가 결과를 쓰는 범위(book.loaded_ranges) 안의 값 셀은 그 범위의 출처다.
다른 엑셀 파일을 읽는 수식 셀은 「외부 파일」, 그 밖의 값 셀은 「수기 입력」이다. 그 밖의 수식 셀은 세지 않는다.
"""
from collections import Counter

from capture_views import SOURCE_KINDS
from explain_cell import col_name
from tables import is_constant_formula

ONLY_MANUAL = "WINUS · WFS 쿼리 연결이 이 표에 없고, 값이 직접 입력되어 있습니다."
LABEL = dict(SOURCE_KINDS)


def _cell_kind(book, sheet, pos):
    formula = book.formula(sheet, pos)
    if formula and not is_constant_formula(formula):
        return "외부 파일" if book.external_file(formula, sheet, pos) else None
    if pos not in book.sheet_values(sheet) and not formula:
        return None
    return book.loaded_source(sheet, pos) or "수기 입력"


def source_of(book, tables):
    """tables 는 한 묶음의 표 목록. {"kinds": {종류: [열 이름]}, "reason": 문장}."""
    counts = {}  # 열 이름 → 종류별 셀 수. 열 이름은 첫 표의 머리글 글자이고, 처음 만난 순서를 지킨다
    first = tables[0]
    for t in tables:
        r1, c1, r2, c2 = t["area"]
        top = (t["header_row"] or r1 - 1) + 1
        for c in range(c1, c2 + 1):
            i, fc = c - c1, first["area"][1] + c - c1
            name = (first["header"][i] if first["header"] and i < len(first["header"]) else None) or f"{col_name(fc)}열"
            for r in range(top, r2 + 1):
                kind = _cell_kind(book, t["sheet"], (r, c))
                if kind:
                    counts.setdefault(name, Counter())[kind] += 1
    kinds = {}
    for key, _ in SOURCE_KINDS:
        cols = [name for name, n in counts.items() if n.most_common(1)[0][0] == key]
        if cols:
            kinds[key] = cols
    if list(kinds) == ["수기 입력"]:
        if book.unplaced:  # 결과 범위를 모르는 연결이 있으면 「연결이 없다」고 단정하지 않는다
            return {"kinds": kinds, "reason": "이 표에서 쿼리 연결의 결과 범위를 찾지 못했고, 값이 직접 입력되어 있습니다. "
                                              f"결과 범위를 알 수 없는 연결이 {len(book.unplaced)}개 있어 이 판정은 틀릴 수 있습니다"
                                              "(「확인 필요한 사항」 참고)."}
        return {"kinds": kinds, "reason": ONLY_MANUAL}
    lines = []
    for key, cols in kinds.items():
        names = ", ".join(f"「{c}」" for c in cols)
        lines.append(f"{names} 열은 직접 입력되어 있습니다." if key == "수기 입력"
                     else f"{names} 열은 {LABEL[key]}에서 가져온 값입니다.")
    return {"kinds": kinds, "reason": " ".join(lines)}
