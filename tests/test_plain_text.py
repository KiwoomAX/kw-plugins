# plain_text 시험. 수식을 역할과 쉬운 문장으로 푸는 규칙을 본다.
#   uv run --no-project --with olefile --with openpyxl --with pytest pytest tests/test_plain_text.py
from conftest import THREE_SHEETS, all_tables, make_book

import plain_text
import tables

RANKED = {"A2": "순위", "B2": "펀드명", "C2": "1W", "A3": 1,
          "N2": "순위", "O2": "순위정리", "P2": "펀드명", "Q2": "1W", "N3": 1, "O3": 1, "P3": "가", "Q3": 0.1}


def sentence_of(tmp_path, cells, sheet, cell, names=None):
    book = make_book(tmp_path, cells)
    found = all_tables(book)
    return plain_text.sentence(book, sheet, cell, found, names or {}, tables.group_tables(found))


def test_vlookup_same_sheet_names_table_and_columns(tmp_path):
    text, _ = sentence_of(tmp_path, {"S": {**RANKED, "B3": "=VLOOKUP($A3,$O$3:$Q$3,2,FALSE)"}}, "S", "B3",
                          {"g2": "계산용 순위표"})
    assert text == ("「펀드명」 셀은 이 행의 「순위」 값을 「S」 시트의 계산용 순위표(N2:Q3)에서 찾습니다. "
                    "찾는 열은 「순위정리」 열입니다. 찾은 행의 「펀드명」 값을 가져옵니다.")


def test_vlookup_other_sheet_uses_default_table_name(tmp_path):
    cells = {**THREE_SHEETS, "U": {"A1": "코드", "B1": "이름", "C1": "비고", "A2": "k2", "B2": "=VLOOKUP(A2,T!$A$1:$C$4,2,FALSE)"}}
    text, _ = sentence_of(tmp_path, cells, "U", "B2")
    assert text.startswith("「이름」 셀은 이 행의 「코드」 값을 「T」 시트의 표(A1:C4)에서 찾습니다.")


def test_vlookup_across_many_tables_names_the_range(tmp_path):
    cells = {"W": {"A1": "코드", "B1": "이름", "C1": "값", "A2": "k", "B2": "가", "C2": 1.0,
                   "A4": "코드", "B4": "이름", "C4": "값", "A5": "m", "B5": "나", "C5": 2.0},
             "X": {"A1": "코드", "B1": "값", "C1": "비고", "A2": "k", "B2": "=VLOOKUP(A2,W!$A$1:$C$5,3,FALSE)"}}
    text, _ = sentence_of(tmp_path, cells, "X", "B2", {"g1": "주간 성과 표"})
    assert "「W」 시트의 A1:C5 범위에서 찾습니다. 이 범위는 주간 성과 표 2개를 이어 붙인 범위입니다." in text


def test_if_vlookup_zero_becomes_blank(tmp_path):
    f = '=IF(VLOOKUP($A3,$O$3:$Q$3,3,FALSE)<>0,VLOOKUP($A3,$O$3:$Q$3,3,FALSE),"")'
    text, _ = sentence_of(tmp_path, {"S": {**RANKED, "C3": f}}, "S", "C3")
    assert text.endswith("찾은 행의 「1W」 값을 가져옵니다. 가져온 값이 0이면 빈 셀로 둡니다.")


def test_other_formulas_use_fallback(tmp_path):
    for f in ['=IF(A3="","",VLOOKUP(A3,$N$3:$Q$3,2,FALSE))', "=VLOOKUP(A3,$N$3:$Q$3,2,TRUE)",
              "=INDEX(Q3:Q9,MATCH(A3,N3:N9,0))", "=SUMIF(N3:N9,A3,Q3:Q9)", '=TEXT(A3,"0")']:
        text, _ = sentence_of(tmp_path, {"S": {**RANKED, "D3": f}}, "S", "D3")
        assert text == "「D열」 셀은 수식으로 계산됩니다.", f


def rank_text(tmp_path, f):
    cells = {"S": {"A1": "1년", "B1": "3년", "C1": "순위", **{f"A{r}": r * 0.1 for r in range(2, 7)},
                   **{f"B{r}": r * 0.2 for r in range(2, 7)}, "C2": f}}
    return sentence_of(tmp_path, cells, "S", "C2")[0]


def test_rank_variants(tmp_path):
    assert rank_text(tmp_path, "=RANK(A2,$A$2:$A$6,1)") == "「순위」 셀은 같은 표 안에서 「1년」 값이 작은 것부터 1위로 순위를 매깁니다."
    assert rank_text(tmp_path, "=RANK(B2,$B$2:$B$6)").startswith("「순위」 셀은 같은 표 안에서 「3년」 값이 큰 것부터")
    assert rank_text(tmp_path, '=IFERROR(RANK(A2,$A$2:$A$6,0),"")').endswith("순위를 매길 수 없으면 빈 셀로 둡니다.")
    assert rank_text(tmp_path, "=RANK(A2,$A$2:$A$3)+MAX($C$4:$C$6)").endswith(
        "아래 묶음의 가장 큰 순위 다음 번호부터 이어서 매깁니다.")


def test_minus_in_sheet_name_is_not_calculation():
    assert plain_text.roles("='A-B'!C1") == ["옮기기"]


def test_roles_inner_first():
    assert plain_text.roles('=IF(VLOOKUP(A1,B:C,2,FALSE)<>0,VLOOKUP(A1,B:C,2,FALSE),"")') == ["찾아 채우기", "기준 비교"]
    assert plain_text.roles("=SUM(A1:A3)*2") == ["계산"] and plain_text.roles("=A1&B1") == []


def test_shape_ignores_cell_addresses():
    assert plain_text.shape("=VLOOKUP($A3,$O$3:$Z$3,2,FALSE)", "B3") == plain_text.shape("=VLOOKUP($A9,$O$9:$Z$9,2,FALSE)", "B9")


def test_flow_summary():
    assert plain_text.flow_summary([], [], "U") == ["「U」 시트는 다른 시트를 읽지 않습니다."]
    assert plain_text.flow_summary(["S", "R"], ["T"], "U") == [
        "「S」, 「R」 시트의 값이 원천 데이터입니다.", "「T」 시트가 원천 데이터로 계산합니다.", "「U」 시트가 결과표입니다."]


def test_card_text_counts_tables():
    many = {"sheet": "W", "tables": [{"area": (1, 1, 2, 3)}, {"area": (4, 1, 5, 3)}]}
    one = {"sheet": "W", "tables": [{"area": (1, 1, 2, 3)}]}
    assert plain_text.card_text(many) == "「W」 시트에 같은 모양의 표 2개가 있습니다."
    assert plain_text.card_text(one) == "「W」 시트의 표(A1:C2)입니다."


def test_quoted_sheet_name_with_space_and_whole_columns(tmp_path):
    cells = {"원천 표": {"A1": "펀드명", "B1": "분류", "C1": "비고", "A2": "가", "B2": "액티브"},
             "S": {"A1": "펀드명", "B1": "분류", "C1": "비고", "A2": "가", "B2": "=VLOOKUP($A2, '원천 표'!$A:$B, 2, FALSE)"}}
    text, _ = sentence_of(tmp_path, cells, "S", "B2")
    assert text == ("「분류」 셀은 이 행의 「펀드명」 값을 「원천 표」 시트의 표(A1:C2)에서 찾습니다. "
                    "찾는 열은 「펀드명」 열입니다. 찾은 행의 「분류」 값을 가져옵니다.")


def test_flow_summary_without_source_says_only_calculation():
    assert plain_text.flow_summary([], ["T"], "U") == ["「T」 시트가 계산합니다.", "「U」 시트가 결과표입니다."]
