# tables 시험. 표, 머리글 행, 표 묶음, 날짜 시트 군과 표 사이 읽기 관계를 본다.
#   uv run --no-project --with olefile --with openpyxl --with pytest pytest tests/test_tables.py
from conftest import make_book

import tables


def test_header_row_needs_three_text_cells_and_60_percent(tmp_path):
    book = make_book(tmp_path, {"S": {"A1": "순위", "B1": "펀드명", "C1": "1W", "A2": 1, "B2": "가", "C2": 0.1}})
    assert tables.header_row(book, "S", (1, 1, 2, 3)) == 1
    book2 = make_book(tmp_path, {"S": {"A1": "순위", "B1": "펀드명", "C1": 3, "D1": 4, "A2": 1, "B2": "가"}})
    assert tables.header_row(book2, "S", (1, 1, 2, 4)) is None


def test_two_column_table_needs_both_header_cells(tmp_path):
    # 코드 → 이름 대응표처럼 열이 2개인 표는 글자 셀 2개면 머리글 행이다. 열 1개는 머리글 행을 찾지 않는다
    book = make_book(tmp_path, {"S": {"A1": "펀드명", "B1": "분류", "A2": "가", "B2": 1.5, "D1": "목록", "D2": "가"}})
    assert tables.header_row(book, "S", (1, 1, 2, 2)) == 1 and tables.header_row(book, "S", (1, 4, 2, 4)) is None


def test_group_ignores_spaces_and_units_in_header():
    found = [{"id": "S!A1:C3", "sheet": "S", "header": ("순위", "설정액 (단위:억원)", "표준편차 (1Y)")},
             {"id": "S!A5:C7", "sheet": "S", "header": ("순위", "설정액 (단위 : 억 원)", "표준편차")},
             {"id": "S!A9:C9", "sheet": "S", "header": ("순위(준)", "순위", "펀드명")}]
    assert [len(g["tables"]) for g in tables.group_tables(found)] == [2, 1]


def test_find_tables_splits_by_blank_rows_and_reads_title(tmp_path):
    cells = {"S": {"A1": "※ 성과 현황", "A2": "순위", "B2": "펀드명", "C2": "1W", "A3": 1, "B3": "가", "C3": 0.1,
                   "A6": "순위", "B6": "펀드명", "C6": "1W", "A7": 1, "B7": "나", "C7": 0.2}}
    found = tables.find_tables(make_book(tmp_path, cells), "S")
    assert [t["area"] for t in found] == [(1, 1, 3, 3), (6, 1, 7, 3)]
    assert found[0]["title"] == "※ 성과 현황" and found[0]["header"] == ("순위", "펀드명", "1W")
    assert found[0]["header_row"] == 2 and found[0]["has_formula"] is False
    assert found[0]["id"] == "S!A1:C3"


def test_excel_table_wins_and_outside_cells_become_nameless_range(tmp_path):
    cells = {"S": {**{f"{c}1": h for c, h in zip("ABC", ["순위", "펀드명", "1W"])},
                   **{f"{c}{r}": r for c in "ABC" for r in (2, 3, 4)}, **{f"D{r}": f"=C{r}*2" for r in (2, 3, 4)}}}
    found = tables.find_tables(make_book(tmp_path, cells, {"S": [("T1", "A1:C4")]}), "S")
    assert [(t["area"], t["excel_table"]) for t in found] == [((1, 1, 4, 3), "T1"), ((2, 4, 4, 4), None)]
    assert found[1]["header"] is None and found[1]["has_formula"] is True


def test_group_tables_by_same_header_in_same_sheet(tmp_path):
    head = {"A{r}": "순위", "B{r}": "펀드명", "C{r}": "1W"}
    cells = {}
    for top in (1, 5, 9):
        cells.update({k.format(r=top): v for k, v in head.items()})
        cells.update({f"A{top + 1}": 1, f"B{top + 1}": "가", f"C{top + 1}": 0.1})
    cells.update({"F1": 1.0, "F2": 2.0})
    found = tables.find_tables(make_book(tmp_path, {"S": cells}), "S")
    groups = tables.group_tables(found)
    assert [len(g["tables"]) for g in groups] == [3, 1] and groups[0]["id"] == "g1"


def test_constant_formula_is_not_a_formula():
    assert tables.is_constant_formula("=10369.6+6.04") and not tables.is_constant_formula("=A1+1")
    assert not tables.is_constant_formula("=SUM(1,2)")


def test_date_groups_need_year_or_date_digits():
    assert tables.date_groups(["2026년 1월1주", "2026년 1월2주", "Sheet1", "Sheet2", "요약"]) == [
        {"pattern": "#년#월#주", "sheets": ["2026년 1월1주", "2026년 1월2주"], "base": "2026년 1월2주",
         "previous": "2026년 1월1주"}]


def test_date_group_base_follows_numbers_not_workbook_order():
    assert tables.date_groups(["2026년 1월2주", "2026년 1월1주"])[0]["base"] == "2026년 1월2주"


def test_date_group_base_is_by_name_even_if_empty(tmp_path):
    book = make_book(tmp_path, {"2026년 1월1주": {"A1": "=1+B1"}, "2026년 1월2주": {}})
    assert tables.analyzed_sheets(book)[0] == ["2026년 1월2주"]


def test_base_override_changes_analyzed_sheet(tmp_path):
    book = make_book(tmp_path, {"2026년 1월1주": {"A1": 1}, "2026년 1월2주": {"A1": 2}, "요약": {"A1": 3}})
    assert tables.analyzed_sheets(book, {"#년#월#주": "2026년 1월1주"})[0] == ["2026년 1월1주", "요약"]


from conftest import THREE_SHEETS, all_tables  # noqa: E402


def test_read_map_links_formula_to_the_table_it_reads(tmp_path):
    book = make_book(tmp_path, THREE_SHEETS)
    reads, odd = tables.read_map(book, all_tables(book), set())
    assert reads["U!A1:C4"] == {"T!A1:C4"} and reads["T!A1:C4"] == {"S!A1:C4"} and reads["S!A1:C4"] == set()
    assert odd == []


def test_dynamic_and_past_sheet_references_are_listed_not_linked(tmp_path):
    book = make_book(tmp_path, {"2026년 1월1주": {"A1": 1.5},
                                "2026년 1월2주": {"A1": "='2026년 1월1주'!A1", "A2": '=INDIRECT("B1")'}})
    found = tables.find_tables(book, "2026년 1월2주")
    reads, odd = tables.read_map(book, found, {"2026년 1월1주"})
    assert sorted(o["why"] for o in odd) == ["dynamic", "past_sheet"] and reads[found[0]["id"]] == set()


def test_candidates_are_sheets_with_unread_formula_tables(tmp_path):
    book = make_book(tmp_path, THREE_SHEETS)
    found = all_tables(book)
    reads, _ = tables.read_map(book, found, set())
    assert tables.candidates(found, reads) == [{"sheet": "U", "tables": ["U!A1:C4"], "reads": 2}]


def test_constant_formula_counts_as_value_column(tmp_path):
    book = make_book(tmp_path, {"S": {"A1": "가", "B1": "나", "C1": "다", "A2": "=1+2", "B2": 3, "C2": "=A2+B2"}})
    assert tables.column_kinds(book, tables.find_tables(book, "S")[0]) == (2, 1)


def test_classify_splits_source_calc_and_result(tmp_path):
    book = make_book(tmp_path, THREE_SHEETS)
    found = all_tables(book)
    reads, _ = tables.read_map(book, found, set())
    out = tables.classify(book, found, reads, {"U!A1:C4"})
    assert out["source"] == ["S!A1:C4"] and out["calc"] == ["T!A1:C4"] and out["result"] == ["U!A1:C4"]
    assert out["order"] == ["S!A1:C4", "T!A1:C4", "U!A1:C4"]


def test_value_table_with_total_row_is_source_and_vlookup_table_is_calc(tmp_path):
    cells = {"V": {"A1": "가", "B1": "나", "C1": "다", "D1": "라", **{f"{c}{r}": float(r) for c in "ABCD" for r in (2, 3)},
                   "A4": "=SUM(A2:A3)"},
             "W": {"A1": "키", "B1": "키2", "C1": "값", "D1": "값2", "A2": "a", "B2": "b",
                   "C2": "=VLOOKUP(A2,V!$A$1:$D$3,2,FALSE)", "D2": "=VLOOKUP(B2,V!$A$1:$D$3,3,FALSE)"},
             "X": {"A1": "=W!C2+W!D2"}}
    book = make_book(tmp_path, cells)
    found = all_tables(book)
    reads, _ = tables.read_map(book, found, set())
    out = tables.classify(book, found, reads, {"X!A1:A1"})
    assert out["source"] == ["V!A1:D4"] and out["calc"] == ["W!A1:D2"]


def test_result_table_is_never_source(tmp_path):
    book = make_book(tmp_path, {"S": {"A1": "가", "B1": "나", "C1": "다", "A2": 1.0, "B2": 2.0, "C2": "=A2+B2"}})
    found = all_tables(book)
    reads, _ = tables.read_map(book, found, set())
    out = tables.classify(book, found, reads, {"S!A1:C2"})
    assert out["source"] == [] and out["result"] == ["S!A1:C2"]


def test_nameless_range_read_by_result_is_reported(tmp_path):
    cells = {**THREE_SHEETS, "V": {"A1": "=1.5*2", "A2": "=A1*2", "A3": "=A2*2"}}
    cells["U"] = {**cells["U"], "D1": "보정", "D2": "=V!A3"}
    book = make_book(tmp_path, cells)
    found = all_tables(book)
    reads, _ = tables.read_map(book, found, set())
    assert tables.nameless_read(found, reads, {"U!A1:D4"}) == ["V!A1:A3"]


def test_row_order_rank_column(tmp_path):
    ranked = make_book(tmp_path, {"S": {"A1": "순위", "B1": "펀드명", "C1": "1W", "A2": 1, "A3": 2, "A4": 3}})
    assert tables.row_order(ranked, tables.find_tables(ranked, "S")[0]) == "순위 순"
    mixed = make_book(tmp_path, {"S": {"A1": "순위", "B1": "펀드명", "C1": "1W", "A2": 2, "A3": 1, "A4": 3}})
    assert tables.row_order(mixed, tables.find_tables(mixed, "S")[0]) == "판정할 수 없음"


def test_tables_reading_each_other_are_still_candidates():
    # 두 표가 서로를 읽고 밖에서는 아무도 읽지 않으면, 순환 안의 표도 결과표 후보다
    found = [{"id": "S!A1:B2", "sheet": "S", "has_formula": True}, {"id": "S!A4:B5", "sheet": "S", "has_formula": True},
             {"id": "S!D1:D2", "sheet": "S", "has_formula": False}]
    reads = {"S!A1:B2": {"S!A4:B5", "S!D1:D2"}, "S!A4:B5": {"S!A1:B2"}, "S!D1:D2": set()}
    assert tables.candidates(found, reads) == [{"sheet": "S", "tables": ["S!A1:B2", "S!A4:B5"], "reads": 1}]


def test_cells_around_excel_table_never_overlap_it(tmp_path):
    # 엑셀 표 A1:C4 오른쪽 수식 열과 아래 합계 행. 나머지 셀 범위는 엑셀 표와 겹치지 않아야 한다
    cells = {"S": {**{f"{c}1": h for c, h in zip("ABC", ["순위", "펀드명", "1W"])},
                   **{f"{c}{r}": r for c in "ABC" for r in (2, 3, 4)}, **{f"D{r}": f"=C{r}*2" for r in (1, 2, 3, 4)},
                   "A5": "합계", "C5": "=SUM(C2:C4)", "D5": "=SUM(D2:D4)"}}
    found = tables.find_tables(make_book(tmp_path, cells, {"S": [("T1", "A1:C4")]}), "S")
    excel = (1, 1, 4, 3)
    others = [t["area"] for t in found if not t["excel_table"]]
    assert others and not any(tables._overlap(excel, a) for a in others)
    covered = {(r, c) for a in others for r in range(a[0], a[2] + 1) for c in range(a[1], a[3] + 1)}
    assert {(5, 1), (5, 3), (5, 4), (1, 4), (4, 4)} <= covered


def test_released_date_group_analyzes_every_sheet(tmp_path):
    book = make_book(tmp_path, {"TDF2030": {"A1": 1}, "TDF2040": {"A1": 2}, "요약": {"A1": 3}})
    sheets, groups = tables.analyzed_sheets(book, {"TDF#": None})
    assert sheets == ["TDF2030", "TDF2040", "요약"] and groups == []
