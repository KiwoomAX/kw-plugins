"""내 표 기록. 이 PC 의 사용자가 클로드 코드로 만든 샌드박스 테이블을 적어 둔다.

DBGateway 는 누가 테이블을 만들었는지 모른다. 그래서 "내가 만든 표인지"와 자세한 용도는 여기에만 있는 원본이다.
다시 받을 수 있는 복사본이 아니므로 cache 밖에 두고, 읽지 못하는 파일은 덮어쓰지 않는다.
컬럼은 적지 않는다. DBGateway 의 describe 로 언제나 최신을 받는다.

표준 라이브러리만 쓴다.
"""
import datetime
import json
import os
import tempfile
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
RECORD = CONFIG_DIR / "managing-sandbox" / "tables.json"


def entries() -> list[dict]:
    """기록의 표 목록. 파일이 없으면 빈 목록이고, 읽지 못하면 덮어쓰지 않도록 멈춘다."""
    try:
        saved = json.loads(RECORD.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except ValueError:
        saved = None
    if not isinstance(saved, dict) or not isinstance(saved.get("tables"), list):
        raise SystemExit(f"내 표 기록을 읽지 못함: {RECORD}. 파일을 덮어쓰지 않음"
                         "\n- 조치: 파일을 열어 고치거나 다른 이름으로 옮긴 뒤 다시 실행")
    return saved["tables"]


def _write(tables: list[dict]) -> None:
    # 반쪽 파일이 남지 않게 임시 파일에 쓴 뒤 바꿔 끼운다. 교체가 거부되면(Windows 에서 다른 창이 열고 있을 때)
    # 원본이라 조용히 건너뛰지 않고 OSError 를 올려, 호출한 쪽이 이미 반영된 변경과 함께 알린다.
    # shortcut: 두 창의 동시 갱신은 나중 쓰기가 이김, 실제로 겪으면 잠금 파일 추가
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    tmp = RECORD.with_name(f"{RECORD.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"tables": tables}, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.replace(tmp, RECORD)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def _same(t: dict, schema: str, table: str) -> bool:
    return t.get("schema") == schema and t.get("table") == table


def has(schema: str, table: str) -> bool:
    return any(_same(t, schema, table) for t in entries())


def add(schema: str, table: str, purpose: str) -> None:
    """표를 기록한다. 이미 있으면 용도만 바꾼다."""
    tables = entries()
    for t in tables:
        if _same(t, schema, table):
            t["purpose"] = purpose
            break
    else:
        tables.append({"schema": schema, "table": table, "purpose": purpose,
                       "created": datetime.date.today().isoformat()})
    _write(tables)


def remove(schema: str, table: str) -> bool:
    tables = entries()
    kept = [t for t in tables if not _same(t, schema, table)]
    if len(kept) == len(tables):
        return False
    _write(kept)
    return True


def rename(schema: str, old: str, new: str) -> bool:
    tables = entries()
    for t in tables:
        if _same(t, schema, old):
            t["table"] = new
            _write(tables)
            return True
    return False


def _selfcheck() -> None:
    import shutil
    global RECORD
    saved = RECORD
    root = Path(tempfile.mkdtemp())
    RECORD = root / "없는폴더" / "tables.json"
    try:
        assert entries() == [], "파일이 없으면 빈 기록"
        add("BS", "투자후보", "리테일 대시보드 월별 집계")
        assert has("BS", "투자후보") and entries()[0]["purpose"] == "리테일 대시보드 월별 집계"
        assert set(entries()[0]) == {"schema", "table", "purpose", "created"}, "항목은 넷뿐"
        add("BS", "투자후보", "용도 변경")
        assert len(entries()) == 1 and entries()[0]["purpose"] == "용도 변경", "같은 표는 한 줄"
        assert rename("BS", "투자후보", "후보") and has("BS", "후보") and not has("BS", "투자후보")
        assert remove("BS", "후보") and entries() == []
        assert not remove("BS", "없는표")
        assert not list(RECORD.parent.glob("*.tmp")), "임시 파일을 남기지 않는다"
        RECORD.write_text("{깨짐", encoding="utf-8")
        try:
            add("BS", "새표", "x")
        except SystemExit as e:
            assert "덮어쓰지 않음" in str(e)
        else:
            raise AssertionError("깨진 기록은 덮어쓰지 않고 멈춘다")
        assert RECORD.read_text(encoding="utf-8") == "{깨짐", "깨진 파일은 그대로 남는다"
    finally:
        shutil.rmtree(root, ignore_errors=True)
        RECORD = saved
