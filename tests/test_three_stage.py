# 3단계 화면 시험. 결과표 하나의 페이지 자료(analyze → build_three_stage)와 화면 HTML 을 본다.
#   uv run --no-project --with olefile --with openpyxl --with pytest pytest tests/test_three_stage.py
from conftest import make_book, three_sheets

import explain_cell


def page_of(tmp_path, book, sheet="U", names=None, cache=None):
    analysis = explain_cell.analyze(book)
    return explain_cell.build_three_stage(book, analysis, {"sheet": sheet, "excel_table": None, "row_order": "순위 순"},
                                          names or {}, cache if cache is not None else {})


def test_three_stage_has_source_calc_result_cards(tmp_path):
    out = page_of(tmp_path, three_sheets(tmp_path))
    assert [len(out["screens"][k]) for k in ("source", "calc", "result")] == [1, 1, 1]
    assert out["screens"]["result"][0]["row_order"] == "순위 순"
    assert out["summary"] == ["「S」 시트의 값이 원천 데이터입니다.", "「T」 시트가 원천 데이터로 계산합니다.", "「U」 시트가 결과표입니다."]
    assert out["sources"][0]["kinds"] == {"수기 입력": ["코드", "이름", "값"]}


def test_card_shows_six_lines_and_more(tmp_path):
    cols = "ABCDEFGH"
    cells = {"U": {**{f"{c}1": f"열{c}" for c in cols}, **{f"{c}2": f"=S!C2*{i + 2}" for i, c in enumerate(cols)},
                   **{f"{c}3": f"=S!C3*{i + 2}" for i, c in enumerate(cols)}},
             "S": {"A1": "코드", "B1": "이름", "C1": "값", "C2": 1.5, "C3": 2.5}}
    card = page_of(tmp_path, make_book(tmp_path, cells))["screens"]["result"][0]
    assert len(card["lines"]) == 6 and card["more"] == 2


def test_line_where_lists_zone_and_columns(tmp_path):
    cells = {"U": {"A1": "Passive", "A2": "코드", "B2": "값", "C2": "두배", **{f"B{r}": r * 1.5 for r in (3, 4, 5)},
                   **{f"C{r}": f"=B{r}*2" for r in (3, 4, 5)}}}
    line = page_of(tmp_path, make_book(tmp_path, cells))["screens"]["result"][0]["lines"][0]
    assert line["where"] == "Passive (A~C열)"
    assert line["cell"] == "C3" and line["step"] == ("U", "C3") and line["roles"] == ["계산"] and line["formula"] == "=B3*2"


def test_preview_uses_tallest_table(tmp_path):
    cells = {}
    for top, last in ((2, 4), (6, 9)):
        cells.update({f"A{top}": "코드", f"B{top}": "값", f"C{top}": "두배"})
        cells.update({f"C{r}": f"=B{r}*2" for r in range(top + 1, last + 1)})
        cells.update({f"B{r}": r * 1.5 for r in range(top + 1, last + 1)})
    preview = page_of(tmp_path, make_book(tmp_path, {"U": cells}))["screens"]["result"][0]["preview"]
    assert preview["area"] == (6, 1, 9, 3)
    assert preview["note"] == "같은 모양 표 2개 중 이 표(A6:C9)를 예로 보여 드립니다. 이 표의 행이 가장 많습니다."
    assert preview["rows"][1][2] == {"v": "", "formula": True} and preview["rows"][1][1] == {"v": "10.5", "formula": False}


def test_unnamed_group_gets_default_name(tmp_path):
    card = page_of(tmp_path, three_sheets(tmp_path))["screens"]["source"][0]
    assert card["name"] == "「S」 표(A1:C4)" and card["guessed"] is False


def test_named_group_is_marked_guessed(tmp_path):
    card = page_of(tmp_path, three_sheets(tmp_path), names={"g1": "분류 대응표"})["screens"]["source"][0]
    assert card["name"] == "분류 대응표" and card["guessed"] is True


def test_steps_made_once_per_representative_cell(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(explain_cell, "build", lambda b, s, c, *a, **k: calls.append((s, c)) or {"steps": [], "nodes": []})
    book, cache = three_sheets(tmp_path), {}
    page_of(tmp_path, book, cache=cache)
    page_of(tmp_path, book, cache=cache)
    assert calls and len(calls) == len(set(calls))


def test_result_sheet_reading_only_itself_still_builds(tmp_path):
    book = make_book(tmp_path, {"U": {"A1": "가", "B1": "나", "C1": "다", "A2": 1.5, "B2": "=A2*2", "C2": "=B2+1"}})
    out = page_of(tmp_path, book)
    assert out["screens"]["source"] == [] and out["summary"] == ["「U」 시트는 다른 시트를 읽지 않습니다."]


def test_date_note_names_base_sheet(tmp_path):
    result = {"A1": "가", "B1": "나", "C1": "다", "A2": 1.5, "B2": "=A2*2", "C2": "=B2+1"}
    out = page_of(tmp_path, make_book(tmp_path, {"2026년 1월1주": {"A1": 1}, "2026년 1월2주": result}), sheet="2026년 1월2주")
    assert out["date_note"] == "이 화면은 날짜가 붙은 시트 중 마지막 시트(2026년 1월2주)를 기준으로 작성했습니다"


def test_render_puts_command_when_no_step_file(tmp_path):
    out = page_of(tmp_path, three_sheets(tmp_path))
    html = explain_cell.render_three_stage(out, {step: None for step in out["steps"]})
    assert "explain_cell.py" in html and '\\"U\\" B2' in html and "__DATA__" not in html


def test_lines_with_same_sentence_are_merged(tmp_path):
    cells = {"U": {"A1": "순위", "B1": "값", "C1": "비고", **{f"B{r}": r * 1.5 for r in range(2, 6)},
                   "A2": "=RANK(B2,$B$2:$B$5)", "A3": "=RANK(B3,$B$2:$B$5)", "A4": "=RANK(B4,$B$2:$B$5,0)", "A5": "=RANK(B5,$B$2:$B$5,0)"}}
    card = page_of(tmp_path, make_book(tmp_path, cells))["screens"]["result"][0]
    assert len(card["lines"]) == 1 and card["more"] == 0


def test_table_read_inside_result_sheet_is_calc(tmp_path):
    # 결과표와 같은 시트의 계산 표(G~I열)는 결과표(A~C열)가 읽으므로 계산된 표다
    cells = {"S": {"A1": "코드", "B1": "이름", "C1": "값", **{f"A{r}": f"k{r}" for r in (2, 3)}, **{f"C{r}": r * 1.5 for r in (2, 3)}},
             "U": {"A1": "코드", "B1": "두배", "C1": "비고", "G1": "코드", "H1": "값", "I1": "메모",
                   **{f"A{r}": f"k{r}" for r in (2, 3)}, **{f"G{r}": f"k{r}" for r in (2, 3)},
                   **{f"H{r}": f"=VLOOKUP(G{r},S!$A$1:$C$3,3,FALSE)" for r in (2, 3)},
                   **{f"B{r}": f"=VLOOKUP(A{r},$G$1:$H$3,2,FALSE)*2" for r in (2, 3)}}}
    out = page_of(tmp_path, make_book(tmp_path, cells))
    assert [c["preview"]["area"] for c in out["screens"]["calc"]] == [(1, 7, 3, 9)]
    assert [c["preview"]["area"] for c in out["screens"]["result"]] == [(1, 1, 3, 3)]
    assert out["summary"][1] == "「U」 시트가 원천 데이터로 계산합니다."


def test_fallback_sentences_are_not_merged(tmp_path):
    # 같은 머리글 표 2개. 「1W」 열이 한쪽은 VLOOKUP(TRUE), 다른 쪽은 INDEX(MATCH) 다. 문장은 같지만 방식이 다르다
    cells = {"U": {"A1": "코드", "B1": "1W", "C1": "비고", "A2": "k", "B2": "=VLOOKUP(A2,$A$2:$C$2,3,TRUE)",
                   "E1": "코드", "F1": "1W", "G1": "비고", "E2": "k", "F2": "=INDEX(G2:G2,MATCH(E2,E2:E2,0))"}}
    card = page_of(tmp_path, make_book(tmp_path, cells))["screens"]["result"][0]
    assert len(card["lines"]) == 2


def test_rank_plus_max_line_has_rank_role_only(tmp_path):
    cells = {"U": {"A1": "순위", "B1": "값", "C1": "비고", **{f"B{r}": r * 1.5 for r in range(2, 5)},
                   "A2": "=RANK(B2,$B$2:$B$3)+MAX($A$4:$A$4)", "A3": "=RANK(B3,$B$2:$B$3)+MAX($A$4:$A$4)", "A4": "=RANK(B4,$B$4:$B$4)"}}
    lines = page_of(tmp_path, make_book(tmp_path, cells))["screens"]["result"][0]["lines"]
    assert all(line["roles"] == ["순위"] for line in lines)


def test_render_command_uses_full_excel_path(tmp_path):
    book = three_sheets(tmp_path)
    out = page_of(tmp_path, book)
    html = explain_cell.render_three_stage(out, {step: None for step in out["steps"]})
    assert str(book.path).replace("\\", "\\\\") in html
