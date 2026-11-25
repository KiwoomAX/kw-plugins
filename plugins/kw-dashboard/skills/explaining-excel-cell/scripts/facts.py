"""결과표에서 수식 참조를 거슬러 올라가 결과에 쓰이는 셀을 모은다.

전체 모드 2번째 실행의 사실 자료(--facts)가 쓴다. 따라가지 못한 참조(INDIRECT · OFFSET, 깨진 참조, 분석하지 않는 날짜 시트)는
조용히 빼지 않고 따로 돌려준다. 외부 파일 참조는 지금 표 사이 읽기 관계(tables.read_map)와 같이 따라가지도 적지도 않는다.
"""
from types import SimpleNamespace

import trace_cells
from tables import _overlap


def _cell_name(r, c):
    from explain_cell import a1
    return a1(r, c)


def _refs(book, sheet, pos):
    """(참조 글자 목록, 동적 참조가 있는지, 깨진 참조가 있는지). 피벗 칸은 피벗 원본을 참조로 본다."""
    pivot = book.pivot_at.get((sheet, pos))
    if pivot is not None:
        return [pivot.source], False, False
    formula = book.formula(sheet, pos)
    if not formula:
        return [], False, False
    probe = SimpleNamespace(broken_refs=set(), dynamic_refs=set())
    refs = trace_cells._references(formula, probe, (sheet, *pos))
    return [r[0] if isinstance(r, tuple) else r for r in refs], bool(probe.dynamic_refs), bool(probe.broken_refs)


def _cells_in(book, sheet, area):
    """범위 안의 값 · 수식 셀. 열 전체 참조도 값이 있는 셀만 센다."""
    known = set(book.cells.get(sheet, {})) | set(book.sheet_values(sheet))
    return {(sheet, p) for p in known if _overlap((*p, *p), area)}


def used_cells(book, starts, stop_sheets=frozenset()):
    """(결과에 쓰이는 셀 집합 {(시트, (행, 열))}, 따라가지 못한 참조 [{sheet, cell, why}]).

    why 는 dynamic(INDIRECT · OFFSET) · broken(깨진 참조) · past_sheet(stop_sheets 시트를 가리킴) 이다.
    stop_sheets 의 셀은 결과에 넣지 않는다."""
    seen, queue, unfollowed, noted = set(starts), list(starts), [], set()

    def note(sheet, pos, why):
        if (sheet, pos, why) not in noted:
            noted.add((sheet, pos, why))
            unfollowed.append({"sheet": sheet, "cell": _cell_name(*pos), "why": why})

    while queue:
        sheet, pos = queue.pop()
        refs, dynamic, broken = _refs(book, sheet, pos)
        if dynamic:
            note(sheet, pos, "dynamic")
        if broken:
            note(sheet, pos, "broken")
        for ref in refs:
            got = book.resolve(ref, sheet, pos)
            if got == "external":
                continue
            if isinstance(got, str):
                note(sheet, pos, "broken")
                continue
            for other, area in got:
                if other in stop_sheets:
                    note(sheet, pos, "past_sheet")
                    continue
                for cell in _cells_in(book, other, area) - seen:
                    seen.add(cell)
                    queue.append(cell)
    return seen, unfollowed


def ranges_text(cells):
    """{시트: ["B5:B7", "C2"]}. 열마다 이어진 행을 범위 글자 하나로 묶는다. 열 순서, 행 순서로 늘어놓는다."""
    out = {}
    for sheet in sorted({s for s, _ in cells}):
        by_col = {}
        for s, (r, c) in cells:
            if s == sheet:
                by_col.setdefault(c, []).append(r)
        texts = []
        for c in sorted(by_col):
            rows = sorted(by_col[c])
            start = prev = rows[0]
            for r in rows[1:] + [None]:
                if r is not None and r == prev + 1:
                    prev = r
                    continue
                texts.append(_cell_name(start, c) if start == prev else f"{_cell_name(start, c)}:{_cell_name(prev, c)}")
                if r is not None:
                    start = prev = r
        out[sheet] = texts
    return out
