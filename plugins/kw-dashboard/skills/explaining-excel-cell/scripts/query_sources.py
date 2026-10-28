"""엑셀 안 데이터가 어디서 들어오는지 읽는다. 쿼리 · 매크로 연결과, 수식이 참조하는 외부 파일이다.

연결은 같은 플러그인의 쿼리 분리 스킬(extracting-excel-queries)이 찾는다. 그 스킬이 계정 · 비밀번호를 가리고
출처(WINUS · WFS 등)를 분류한 연결 목록을, 여기서 결과를 쓰는 시트 범위로 바꾼다.
파일 경로는 PC 의 사용자 이름을 포함할 수 있어 파일 이름만 돌려준다.
"""
import posixpath
import re
import sys
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import trace_cells

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
EXTRACTOR = Path(__file__).resolve().parents[2] / "extracting-excel-queries/scripts"
if str(EXTRACTOR) not in sys.path:
    sys.path.insert(0, str(EXTRACTOR))
from _model import DB_KINDS, READ_FAILURE_KINDS  # noqa: E402  연결 종류는 쿼리 분리 스킬 한 곳에서 정한다
FROM_NAME = re.compile(r"(?i)\b(?:from|join)\s+([\w$#가-힣]+(?:\.[\w$#가-힣]+)?(?:@[\w.]+)?)")
CELL = re.compile(r"^([A-Z]{1,3})(\d+)(?::([A-Z]{1,3})(\d+))?$")
COLUMNS = re.compile(r"^열 ([\d·~]+)$")


def file_name(target):
    """경로나 file:/// 주소에서 마지막 파일 이름만 남긴다. 경로가 아니면 그대로 돌려준다."""
    return re.split(r"[\\/]", urllib.parse.unquote(target).rstrip("\\/"))[-1]


def _scan_file(path):
    """(쿼리 분리 스킬이 찾은 연결 목록, 출처 대응표 상태). 대응표는 공용 폴더에서 한 번만 읽어 분류와 상태에 함께 쓴다."""
    from extract_queries import scan_file
    from source_rules import load_rules
    rules, state = load_rules()
    return scan_file(Path(path), rules), state


def source_name(kind, origin):
    """쿼리 분리 스킬의 분류 값을 화면의 출처 종류로 바꾼다."""
    if origin in ("WINUS", "WFS"):
        return origin
    if origin == "외부":
        return "외부 파일" if kind == "외부 통합문서 링크" else "외부 연결"
    return "DB 쿼리 연결" if kind in DB_KINDS else "외부 연결"


def _col(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n


def _columns(spec):
    """「3·6」 · 「3~5」 를 열 번호 목록으로."""
    out = []
    for part in spec.split("·"):
        lo, _, hi = part.partition("~")
        out += range(int(lo), int(hi or lo) + 1)
    return out


def _areas(rest, values):
    """「A1:B3」 · 「F2」 · 「열 3·6」 을 (r1, c1, r2, c2) 목록으로. 셀 하나와 열은 값이 이어진 데이터까지 넓힌다."""
    m = CELL.match(rest)
    if m and m.group(3):
        return [(int(m.group(2)), _col(m.group(1)), int(m.group(4)), _col(m.group(3)))]
    if m:
        r, c = int(m.group(2)), _col(m.group(1))
        r2, c2 = r, c
        while (r2 + 1, c) in values:
            r2 += 1
        while (r, c2 + 1) in values:
            c2 += 1
        return [(r, c, r2, c2)]
    m = COLUMNS.match(rest)
    if m:
        out = []
        for c in _columns(m.group(1)):
            rows = [r for (r, cc) in values if cc == c]
            if rows:
                out.append((min(rows), c, max(rows), c))
        return out
    return []


def load_connections(path, sheet_values):
    """(결과 범위 목록, 시트를 정할 수 없는 연결 목록, 출처 대응표 상태).

    결과 범위는 {sheet, area, source, kind, name, tables} 이다. VBA 연결의 시트 자리에는 VBA 객체 식이 들어가므로,
    그 글자가 시트 이름과 같을 때만 그 시트로 본다.
    """
    conns, state = _scan_file(path)
    loaded, unplaced = [], []
    for c in conns:
        if c.kind in READ_FAILURE_KINDS:  # 엑셀이나 VBA 프로젝트를 읽지 못했다는 행. 출처 판정이 틀릴 수 있음을 알린다
            unplaced.append({"kind": c.kind, "location": c.location, "why": "처리 오류"})
            continue
        if not c.output_range:
            if c.kind in DB_KINDS:
                unplaced.append({"kind": c.kind, "location": c.location, "why": "범위 모름"})
            continue
        if " 열 " in c.output_range:  # 「시트 열 3·6」. 시트 이름에 공백이 있어도 「 열 」 앞이 시트다
            obj, rest = c.output_range.split(" 열 ", 1)
            rest = f"열 {rest}"
        else:  # 「시트 A1:B3」 · 「시트 F2」. 마지막 공백 뒤가 범위다
            obj, _, rest = c.output_range.rpartition(" ")
        if obj not in sheet_values:
            unplaced.append({"kind": c.kind, "location": c.location, "why": "시트 모름"})
            continue
        tables = sorted({m.upper() for m in FROM_NAME.findall(c.sql or "")})
        for area in _areas(rest, sheet_values[obj]):
            loaded.append({"sheet": obj, "area": area, "source": source_name(c.kind, c.origin), "kind": c.kind,
                           "name": c.location.removeprefix("연결 "), "tables": tables})
    unplaced = [dict(t) for t in dict.fromkeys(tuple(u.items()) for u in unplaced)]  # 한 매크로가 여러 번 쓰는 연결은 1번만
    return loaded, unplaced, state


def query_tables(tables, loaded):
    """쿼리 표 이름 → {name, source, tables}. 같은 시트 · 같은 범위의 결과 범위에서 가져온다."""
    out = {}
    for name, t in tables.items():
        if not getattr(t, "query", False):
            continue
        lr = next((x for x in loaded if x["sheet"] == t.sheet and x["area"] == tuple(t.area)), None)
        if lr:
            out[name] = {"name": lr["name"], "source": lr["source"], "tables": lr["tables"]}
    return out


def load_external_files(path):
    """수식 속 외부 참조 번호(`[1]` 의 1)마다 외부 파일 이름을 돌려준다.

    번호는 xl/workbook.xml 의 externalReference 순서이고, 각 외부 링크의 관계 파일이 대상 경로를 갖는다.
    """
    with zipfile.ZipFile(path) as z:
        parts = set(z.namelist())
        refs = ET.fromstring(z.read("xl/workbook.xml")).find("m:externalReferences", NS)
        if refs is None:
            return {}
        rels = trace_cells._rels(z, "xl/workbook.xml")
        out = {}
        for i, ref in enumerate(refs, 1):
            part = rels.get(ref.get(f"{{{R}}}id"), (None, None))[1]
            if part is None:
                continue
            rel_path = posixpath.join(posixpath.dirname(part), "_rels", posixpath.basename(part) + ".rels")
            if rel_path not in parts:
                continue
            targets = [r.get("Target") for r in ET.fromstring(z.read(rel_path))]
            if targets:
                out[str(i)] = file_name(targets[0])
    return out
