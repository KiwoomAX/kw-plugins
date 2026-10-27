# formula_segments 의 수식 조각 시험. 값 읽기와 참조 해석은 dict 와 trace_cells.make_resolver 로 흉내 낸다.
#   uv run --no-project --with openpyxl --with pytest pytest tests/test_formula_segments.py
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "plugins/kw-dashboard/skills"
sys.path.insert(0, str(ROOT / "explaining-excel-cell/scripts"))
import trace_cells  # noqa: E402
from formula_segments import segments  # noqa: E402

VALUES = {"S": {(1, 1): 2.0, (1, 2): 3.0, (5, 1): "k", (5, 2): 10.0, (6, 1): "m", (6, 2): 4.0},
          "T": {(1, 1): 7.0}}
TABLE = trace_cells.Table("S", (5, 1, 7, 2), ["키", "값"], 1, 0)
RESOLVE = trace_cells.make_resolver({"S": {}, "T": {}}, {"T1": TABLE}, {"단가": "'S'!$A$1"})


def segs(formula, pos=(9, 9)):
    return segments(formula, "S", pos, lambda s: VALUES.get(s, {}), RESOLVE)["segments"]


def test_same_and_other_sheet_refs_get_values():
    out = segs("=A1+T!A1")
    assert out[0] == {"t": "="}
    assert out[1] == {"v": 2.0, "src": "A1", "ref": {"sheet": "S", "area": [1, 1, 1, 1]}}
    assert out[3] == {"v": 7.0, "src": "T!A1", "ref": {"sheet": "T", "area": [1, 1, 1, 1]}}


def test_vlookup_points_to_found_cell():
    out = segs('=VLOOKUP("k",A5:B7,2,FALSE)')
    assert out[1]["v"] == 10.0 and out[1]["ref"]["area"] == [5, 2, 5, 2]
    assert out[1]["src"] == 'VLOOKUP("k",A5:B7,2,FALSE)'


def test_defined_name_gets_value():
    out = segs("=단가*2")
    assert out[1] == {"v": 2.0, "src": "단가", "ref": {"sheet": "S", "area": [1, 1, 1, 1]}}


def test_vlookup_ignores_letter_case_like_excel():
    out = segs('=VLOOKUP("K",A5:B7,2,FALSE)')
    assert out[1]["v"] == 10.0 and out[1]["ref"]["area"] == [5, 2, 5, 2]


def test_vlookup_with_missing_key_stays_text():
    out = segs('=VLOOKUP("없음",A5:B7,2,FALSE)')
    assert out[1] == {"t": 'VLOOKUP("없음",A5:B7,2,FALSE)'}


def test_structured_this_row_ref_gets_value():
    out = segs("=T1[[#This Row],[값]]", pos=(6, 3))
    assert out[1]["v"] == 4.0 and out[1]["ref"]["area"] == [6, 2, 6, 2]


def test_range_and_external_refs_stay_text():
    out = segs("=SUM(A1:B1)+'[1]X'!A1")
    assert {"t": "A1:B1", "ref": {"sheet": "S", "area": [1, 1, 1, 2]}} in out
    assert {"t": "'[1]X'!A1", "ref": None} in out
    assert not any("v" in g for g in out)


def test_pivot_formula_shows_source():
    out = segs("피벗 원본: 'S'!A1:B5")
    assert out[0] == {"t": "피벗 합계 · 원본 "}
    assert out[1]["t"] == "'S'!A1:B5" and out[1]["ref"]["area"] == [1, 1, 5, 2]


def test_vlookup_column_number_from_a_cell_reference():
    VALUES["S"][(1, 5)] = 2.0  # E1 에 돌려줄 열 번호 2
    try:
        out = segs('=VLOOKUP("k",A5:B7,$E$1,FALSE)')
        assert out[1]["v"] == 10.0 and out[1]["ref"]["area"] == [5, 2, 5, 2]
    finally:
        del VALUES["S"][(1, 5)]


def test_whole_row_reference_is_not_a_single_cell():
    out = segs("=SUM(5:5)")
    assert not any("v" in g for g in out)
