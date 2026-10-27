# query_sources 시험. 쿼리 분리 스킬의 연결 목록을 설명기 형식으로 바꾸는 일과 외부 파일 이름 읽기를 본다.
#   uv run --no-project --with olefile --with openpyxl --with pytest pytest tests/test_query_sources.py
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "plugins/kw-dashboard/skills"
sys.path.insert(0, str(ROOT / "explaining-excel-cell/scripts"))
sys.path.insert(0, str(ROOT / "extracting-excel-queries/scripts"))
import query_sources  # noqa: E402
from _model import Connection  # noqa: E402

M = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
R = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'
VALUES = {"S": {(1, 1): "코드", (1, 2): "값", (2, 1): "k", (2, 2): 1.5, (2, 4): 2.0, (5, 4): 3.0,
                (2, 6): 1.0, (2, 7): 2.0, (3, 6): 3.0, (3, 7): 4.0}}


@pytest.fixture
def fake_scan(monkeypatch):
    def use(conns, state="읽음"):
        monkeypatch.setattr(query_sources, "_scan_file", lambda path: (conns, state))
    return use


def test_query_table_becomes_loaded_range_with_table_names(fake_scan):
    fake_scan([Connection(kind="ODBC 쿼리 테이블", location="연결 q", output_range="S A1:B3", origin="미판별",
                          sql="select a from SCHEMA_A.T1 x join SCHEMA_A.T2 y on x.k = y.k")])
    loaded, unplaced, state = query_sources.load_connections("x.xlsx", VALUES)
    assert loaded == [{"sheet": "S", "area": (1, 1, 3, 2), "source": "DB 쿼리 연결", "kind": "ODBC 쿼리 테이블",
                       "name": "q", "tables": ["SCHEMA_A.T1", "SCHEMA_A.T2"]}]
    assert unplaced == [] and state == "읽음"


def test_column_and_cell_forms_cover_their_data(fake_scan):
    fake_scan([Connection(kind="VBA ADODB SQL", location="VBA M.Q", sql="select 2 from t", output_range="S 열 4", origin="WFS"),
               Connection(kind="VBA 쿼리 테이블 생성", location="VBA M.R", sql="select 3 from u", output_range="S F2", origin="WINUS")])
    loaded, _, _ = query_sources.load_connections("x.xlsm", VALUES)
    assert [(l["area"], l["source"]) for l in loaded] == [((2, 4, 5, 4), "WFS"), ((2, 6, 3, 7), "WINUS")]


def test_unknown_sheet_object_and_read_error_are_unplaced(fake_scan):
    fake_scan([Connection(kind="VBA ADODB SQL", location="VBA M.P", sql="select 1", output_range="ActiveSheet 열 3·6", origin="WINUS"),
               Connection(kind="외부 통합문서 링크", location="externalLink1.xml", origin="외부"),
               Connection(kind="처리 오류", location="", origin="")])
    loaded, unplaced, _ = query_sources.load_connections("x.xlsm", VALUES)
    assert loaded == [] and unplaced == [{"kind": "VBA ADODB SQL", "location": "VBA M.P", "why": "시트 모름"},
                                         {"kind": "처리 오류", "location": "", "why": "처리 오류"}]


def test_source_names_follow_kind_and_class():
    s = query_sources.source_name
    assert [s("ODBC 쿼리 테이블", "WINUS"), s("Power Query", "WFS"), s("VBA ADODB SQL", "미판별"),
            s("VBA 파일 읽기", "미판별"), s("외부 통합문서 링크", "외부"), s("DDE 링크", "외부")] == [
        "WINUS", "WFS", "DB 쿼리 연결", "외부 연결", "외부 파일", "외부 연결"]


def test_query_tables_take_connection_of_same_area():
    loaded = [{"sheet": "S", "area": (1, 1, 3, 2), "source": "WINUS", "kind": "ODBC 쿼리 테이블", "name": "q", "tables": ["SCHEMA_A.T1"]}]
    tables = {"표_Q": type("T", (), {"sheet": "S", "area": (1, 1, 3, 2), "query": True})(),
              "표_X": type("T", (), {"sheet": "S", "area": (9, 9, 9, 9), "query": True})()}
    assert query_sources.query_tables(tables, loaded) == {"표_Q": {"name": "q", "source": "WINUS", "tables": ["SCHEMA_A.T1"]}}


def test_external_files_map_bracket_number_to_file_name(tmp_path):
    from query_sources import load_external_files
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    path = tmp_path / "x.xlsx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {M} xmlns:r="{rel}"><externalReferences>'
                   '<externalReference r:id="rId5"/><externalReference r:id="rId6"/></externalReferences></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", f'<Relationships {R}>'
                   f'<Relationship Id="rId5" Type="{rel}/externalLink" Target="externalLinks/externalLink2.xml"/>'
                   f'<Relationship Id="rId6" Type="{rel}/externalLink" Target="externalLinks/externalLink1.xml"/></Relationships>')
        z.writestr("xl/externalLinks/_rels/externalLink2.xml.rels", f'<Relationships {R}><Relationship Id="rId1" '
                   f'Type="{rel}/externalLinkPath" Target="file:///C:\\data\\손익기초.XLS" TargetMode="External"/></Relationships>')
        z.writestr("xl/externalLinks/_rels/externalLink1.xml.rels", f'<Relationships {R}><Relationship Id="rId1" '
                   f'Type="{rel}/externalLinkPath" Target="Liquidity%20Report.xlsx" TargetMode="External"/></Relationships>')
    assert load_external_files(path) == {"1": "손익기초.XLS", "2": "Liquidity Report.xlsx"}


def test_db_connection_without_output_range_is_unplaced(fake_scan):
    fake_scan([Connection(kind="VBA ADODB SQL", location="VBA M.P", sql="select 1 from t", output_range="", origin="WINUS"),
               Connection(kind="처리 오류", location="", notes=["비밀번호 누출 검사 실패"]),
               Connection(kind="외부 통합문서 링크", location="링크 1", output_range="", origin="외부")])
    loaded, unplaced, _ = query_sources.load_connections("x.xlsm", VALUES)
    assert loaded == [] and unplaced == [{"kind": "VBA ADODB SQL", "location": "VBA M.P", "why": "범위 모름"},
                                         {"kind": "처리 오류", "location": "", "why": "처리 오류"}]


def test_same_unplaced_connection_is_listed_once(fake_scan):
    fake_scan([Connection(kind="VBA 쿼리 테이블 생성", location="VBA M.Q", sql="select 1", output_range=f"ActiveSheet ${c}$1", origin="미판별")
               for c in "AIR"])
    _, unplaced, _ = query_sources.load_connections("x.xlsm", VALUES)
    assert unplaced == [{"kind": "VBA 쿼리 테이블 생성", "location": "VBA M.Q", "why": "시트 모름"}]
