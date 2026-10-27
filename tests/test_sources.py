# sources 시험. 원천 표 묶음의 열마다 출처를 정하고 판정 근거 문장을 만든다.
#   uv run --no-project --with olefile --with openpyxl --with pytest pytest tests/test_sources.py
from conftest import make_book

import sources
import tables

CELLS = {"S": {"A1": "코드", "B1": "이름", "C1": "값", "A2": "k", "B2": "n", "C2": 1.5}}


def test_values_only_is_manual_input(tmp_path):
    book = make_book(tmp_path, CELLS)
    out = sources.source_of(book, tables.find_tables(book, "S"))
    assert out == {"kinds": {"수기 입력": ["코드", "이름", "값"]},
                   "reason": "WINUS · WFS 쿼리 연결이 이 표에 없고, 값이 직접 입력되어 있습니다."}


def test_loaded_range_columns_use_its_source(tmp_path):
    book = make_book(tmp_path, CELLS)
    book.loaded_ranges = [{"sheet": "S", "area": (1, 1, 2, 3), "source": "WINUS", "kind": "VBA ADODB SQL", "name": "VBA M.P", "tables": []}]
    out = sources.source_of(book, tables.find_tables(book, "S"))
    assert out == {"kinds": {"WINUS": ["코드", "이름", "값"]}, "reason": "「코드」, 「이름」, 「값」 열은 WINUS에서 가져온 값입니다."}


def test_external_file_column_and_mixed_kinds(tmp_path, monkeypatch):
    book = make_book(tmp_path, {"S": {**CELLS["S"], "C2": "=[1]Sheet1!A1"}})
    monkeypatch.setattr(book, "external_file", lambda formula, sheet, pos: "a.xlsx" if "[1]" in formula else None)
    out = sources.source_of(book, tables.find_tables(book, "S"))
    assert out["kinds"] == {"외부 파일": ["값"], "수기 입력": ["코드", "이름"]}
    assert out["reason"] == "「값」 열은 외부 파일에서 가져온 값입니다. 「코드」, 「이름」 열은 직접 입력되어 있습니다."


def test_group_tables_share_column_names(tmp_path):
    # 머리글 글자가 공백만 다른 같은 묶음의 표는 첫 표의 열 이름으로 센다
    cells = {"S": {"A1": "코드", "B1": "이름", "C1": "설정액 (억원)", "A2": "k", "B2": "n", "C2": 1.5,
                   "A4": "코드", "B4": "이름", "C4": "설정액 (억 원)", "A5": "m", "B5": "o", "C5": 2.5}}
    book = make_book(tmp_path, cells)
    out = sources.source_of(book, tables.find_tables(book, "S"))
    assert out["kinds"] == {"수기 입력": ["코드", "이름", "설정액 (억원)"]}


def test_unplaced_connection_keeps_reason_from_denying_connections(tmp_path):
    book = make_book(tmp_path, CELLS)
    book.unplaced = [{"kind": "VBA ADODB SQL", "location": "VBA M.P", "why": "범위 모름"}]
    out = sources.source_of(book, tables.find_tables(book, "S"))
    assert out["reason"] == ("이 표에서 쿼리 연결의 결과 범위를 찾지 못했고, 값이 직접 입력되어 있습니다. "
                             "결과 범위를 알 수 없는 연결이 1개 있어 이 판정은 틀릴 수 있습니다(「확인 필요한 사항」 참고).")
