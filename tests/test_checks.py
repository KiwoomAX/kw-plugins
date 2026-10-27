# checks 시험. 벗어나는 행, 수식 없이 값이 같은 열, 분석이 모호했던 상황을 본다.
#   uv run --no-project --with olefile --with openpyxl --with pytest pytest tests/test_checks.py
from conftest import make_book

import checks
import tables

HEAD = {"A1": "가", "B1": "나", "C1": "다"}


def odd_of(tmp_path, cells):
    book = make_book(tmp_path, {"S": {**HEAD, **cells}})
    return checks.odd_rows(book, tables.find_tables(book, "S"))


def test_value_in_formula_column_is_odd(tmp_path):
    out = odd_of(tmp_path, {**{f"B{r}": r * 1.5 for r in range(2, 7)},
                            **{f"A{r}": f"=B{r}*2" for r in (2, 3, 5, 6)}, "A4": 9.5})
    assert [(i["cell"], i["column"], i["usual"], i["got"]) for i in out["items"]] == [("A4", "가", "=B2*2", "값 「9.5」")]
    assert out["more"] == 0


def test_rank_plus_max_is_not_odd(tmp_path):
    out = odd_of(tmp_path, {**{f"B{r}": r * 1.5 for r in range(2, 6)},
                            **{f"A{r}": f"=RANK(B{r},$B$2:$B$3)" for r in (2, 3)},
                            **{f"A{r}": f"=RANK(B{r},$B$4:$B$5)+MAX($A$2:$A$3)" for r in (4, 5)}})
    assert out["items"] == []


def test_role_change_is_odd(tmp_path):
    out = odd_of(tmp_path, {**{f"B{r}": f"k{r}" for r in range(2, 7)},
                            **{f"A{r}": f"=VLOOKUP(B{r},$B$2:$C$6,2,FALSE)" for r in (2, 3, 4, 6)}, "A5": "=SUM(C2:C4)"})
    assert [(i["cell"], i["got"]) for i in out["items"]] == [("A5", "=SUM(C2:C4)")]


def test_header_text_of_next_table_is_skipped(tmp_path):
    out = odd_of(tmp_path, {**{f"B{r}": r * 1.5 for r in range(2, 7)},
                            **{f"A{r}": f"=B{r}*2" for r in (2, 3, 5, 6)}, "A4": "가"})
    assert out["items"] == []


def test_same_decimal_columns_match_but_integers_do_not(tmp_path):
    def sheet(tag):
        return {**HEAD, **{f"A{r}": r for r in range(2, 8)}, **{f"B{r}": f"{tag}{r}" for r in range(2, 8)},
                **{f"C{r}": r * 0.37 for r in range(2, 8)}}
    book = make_book(tmp_path, {"S": sheet("s"), "T": sheet("t")})
    out = checks.same_value_columns(book, {s: tables.find_tables(book, s) for s in book.order}, [])
    assert len(out["items"]) == 1 and out["items"][0]["count"] == 6
    assert out["items"][0]["text"] == ("「S」 시트 표(A1:C7)의 「다」 값 6개가 「T」 시트 표(A1:C7)의 「다」 값과 같습니다. "
                                       "두 열 사이에 수식 연결은 없습니다. 같은 값을 옮겨 붙이는 연결이 맞습니까?")


def test_threshold_change_between_base_and_previous(tmp_path):
    book = make_book(tmp_path, {"2026년 1월1주": {"A1": 0.1, "B1": "=A1>0.03"},
                                "2026년 1월2주": {"A1": 0.2, "B1": "=A1>0.05"}})
    out = checks.ambiguous(book, [], [], tables.date_groups(book.order))
    assert [(i["kind"], i["where"]) for i in out["items"]] == [("기준값", "2026년 1월2주!B1")]
    assert out["items"][0]["text"] == "매주 바뀌는 기준값입니까? 정해진 규칙이 있습니까?"


def test_past_sheet_and_nameless_are_listed(tmp_path):
    book = make_book(tmp_path, {"S": {"A1": 1.5}})
    out = checks.ambiguous(book, [{"sheet": "S", "cell": "A1", "why": "past_sheet"}], ["V!A1:A3"], [])
    assert [i["kind"] for i in out["items"]] == ["과거 시트", "이름 없는 범위"]
    book.unplaced = [{"kind": "VBA ADODB SQL", "location": "Module1"}]
    out = checks.ambiguous(book, [], [], [])
    assert out["items"] == [{"kind": "매크로 시트", "where": "Module1", "text": "매크로가 어느 시트에 값을 넣는지 알려 주세요."}]


def test_text_columns_are_not_compared(tmp_path):
    def sheet():
        return {**HEAD, **{f"A{r}": f"운용사{r}" for r in range(2, 8)}, **{f"B{r}": r * 0.37 for r in range(2, 8)}}
    book = make_book(tmp_path, {"S": sheet(), "T": sheet()})
    out = checks.same_value_columns(book, {s: tables.find_tables(book, s) for s in book.order}, [])
    assert [i["count"] for i in out["items"]] == [6] and "「나」" in out["items"][0]["text"]


def test_unplaced_reasons_have_their_own_text(tmp_path):
    book = make_book(tmp_path, {"S": {"A1": 1.5}})
    book.unplaced = [{"kind": "VBA ADODB SQL", "location": "VBA M.P", "why": "범위 모름"},
                     {"kind": "처리 오류", "location": "", "why": "처리 오류"}]
    texts = [i["text"] for i in checks.ambiguous(book, [], [], [])["items"]]
    assert texts == ["이 연결이 값을 넣는 시트와 범위를 찾지 못했습니다. 어느 표에 값을 넣는지 알려 주세요.",
                     "엑셀의 데이터 연결을 읽지 못했습니다. 원천 데이터 출처 판정이 틀릴 수 있습니다."]
