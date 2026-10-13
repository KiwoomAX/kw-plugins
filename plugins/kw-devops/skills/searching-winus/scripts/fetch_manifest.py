# /// script
# requires-python = ">=3.10"
# dependencies = [
#   # 커밋을 고정한다. 고정하지 않으면 uv 가 돌 때마다 GitHub 에 HEAD 를 물으러 가고, 사내망만
#   # 열려 있고 인터넷이 막힌 PC 에서는 스크립트가 시작조차 못 해 아래 사본 대비책이 무의미해진다.
#   # SDK 를 올릴 때 이 커밋을 손으로 바꾼다. SKILL.md 는 사내 PC 의 V3 가 uv 의 스크립트 환경
#   # 런처를 차단해 이 블록 대신 `uv run --with` 로 같은 SDK 를 주므로, 거기 적힌 커밋도 함께 바꾼다.
#   # 두 값이 같은지는 tests/test_devops.ps1 이 검사한다.
#   "kiwoom-mdb-manager @ git+https://github.com/KiwoomAM/Kiwoom-Manager.git@807890e686106719a0aa2f0aa054d6573dc16d65#subdirectory=mdb-manager",
# ]
# ///
"""매니페스트를 MongoDB 에서 읽어 쿼리 목차나 고른 쿼리의 상세를 표준 출력에 낸다.

인자 없이 돌리면 쿼리 단위 목차(id·이름·설명·사용 테이블)를 내고, --query 뒤에 쿼리 id 를 주면 그
쿼리들의 이름·설명·인자 키·등록된 SQL 을 낸다. 읽는 쪽이 필요한 쿼리의 SQL 만 읽게 하려고 나눴다.
인자 키는 DBGateway 와 같은 바인드 규칙으로 SQL 에서 뽑는다.

받은 것은 ~/.claude/cache/searching-winus/query_index.json 에 남긴다. 한 시간이 지나지 않은 사본이
있으면 MongoDB 를 부르지 않고 그것을 쓴다. MongoDB 를 못 읽었는데 사본이 낡았으면 낡은 것을
쓰되 첫 줄에 그렇게 적는다. 사본이 아예 없으면 멈춘다. MongoDB 를 읽었는데 query_index 문서가 없으면
사본으로 넘어가지 않고 멈춘다.

사용: uv run scripts/fetch_manifest.py [--query id ...]
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

TTL_SECONDS = 3600
CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
CACHE = CONFIG_DIR / "cache" / "searching-winus" / "query_index.json"

DB, COLLECTION, DOC_ID = "kw_ai", "winus_query_manifest", "query_index"
# DBGateway 와 같은 바인드 규칙이다. 문자열·주석 안의 콜론도 인자로 센다.
BIND = re.compile(r":([A-Za-z_가-힣][A-Za-z0-9_가-힣]*)")


class NotPublished(Exception):
    """MongoDB 는 읽었는데 query_index 문서가 없다. 낡은 사본으로 넘어가면 지난 목차를 최신처럼 보이게 된다."""


def cache_age() -> float | None:
    """사본을 받은 지 몇 초 지났는가. 사본이 없으면 None."""
    try:
        return time.time() - CACHE.stat().st_mtime
    except FileNotFoundError:
        return None


def from_doc(doc: dict | None) -> dict:
    """받은 문서에서 목차와 쿼리만 남긴다. 둘 중 하나라도 없으면 발행본이 아니다."""
    if not doc or not doc.get("index") or not doc.get("queries"):
        raise NotPublished(f"{DB}.{COLLECTION}/{DOC_ID} 가 없거나 목차·쿼리가 비어 있다 —"
                           " 매니페스트가 발행되지 않았다. 사용자는 AX팀에 발행을 요청해야 한다")
    return {"index": doc["index"], "queries": doc["queries"]}


def fetch() -> dict:
    from mdb_manager import MongoDBManager

    return from_doc(MongoDBManager(database=DB, collection=COLLECTION).find_one({"doc_id": DOC_ID}))


def read_cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8"))


def manifest(fetch_doc=fetch) -> tuple[dict, str | None]:
    """({"index", "queries"}, 경고). 경고가 있으면 낡은 사본을 낸 것이다."""
    age = cache_age()
    if age is not None and age < TTL_SECONDS:
        return read_cache(), None
    try:
        doc = fetch_doc()
    except ImportError as e:
        # SDK 가 안 깔린 것이라 사본으로 넘기면 원인이 가려진다. 이것만 따로 세운다.
        raise SystemExit(f"kiwoom-mdb-manager 를 불러오지 못했다 — SKILL.md 의 명령대로 uv run --with 로 SDK 를 함께 주는지 확인한다. {e}")
    except NotPublished as e:
        raise SystemExit(str(e))
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        if age is None:
            raise SystemExit(f"매니페스트를 읽지 못했고 사본도 없다 — 사내망인지 확인한다. {detail}")
        return read_cache(), f"MongoDB 를 읽지 못해 {age / 3600:.1f}시간 지난 사본을 쓴다 — {detail}"
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    # 다른 세션이 반쯤 쓴 사본을 읽지 않도록 임시 파일에 쓴 뒤 바꿔 끼운다. Windows 에서는 그 순간
    # 다른 세션이 사본을 열고 있으면 교체가 거부되는데, 사본은 다음 실행에 다시 받으면 되므로 넘긴다.
    tmp = CACHE.with_name(f"{CACHE.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    try:
        os.replace(tmp, CACHE)
    except OSError:
        tmp.unlink(missing_ok=True)
    return doc, None


def bind_keys(sql: str) -> list[str]:
    """DBGateway 가 요구하는 인자 키를 처음 나온 순서로 중복 없이 낸다."""
    return list(dict.fromkeys(BIND.findall(sql)))


def render(doc: dict, ids: list[str]) -> str:
    """id 가 없으면 목차, 있으면 그 쿼리들의 이름·설명·인자 키·등록된 SQL."""
    if not ids:
        return doc["index"]
    unknown = [i for i in ids if i not in doc["queries"]]
    if unknown:
        raise SystemExit(f"매니페스트에 없는 쿼리 id 다: {', '.join(unknown)} — 목차에는 활성 쿼리만 실린다")
    lines = []
    for i in ids:
        q = doc["queries"][i]
        keys = ", ".join(f"`{k}`" for k in bind_keys(q["sql"])) or "없음"
        lines += [f"## id {i} · {q['name']}", "", f"- 설명: {q['description']}", f"- 인자 키: {keys}",
                  "- 등록된 SQL:", "", "```sql", q["sql"], "```", ""]
    return "\n".join(lines)


def _selfcheck() -> None:
    import shutil
    global CACHE
    # 사용자의 실제 사본과 섞이지 않게 빈 임시 폴더를 쓴다.
    saved, CACHE = CACHE, Path(tempfile.mkdtemp()) / "query_index.json"
    boom = lambda: (_ for _ in ()).throw(RuntimeError("끊김"))
    sql = "SELECT a FROM T_X WHERE d = :d0 AND t = TO_CHAR(s, 'HH24:MI') /* :c */ AND k IN (:codes) AND e = :d0"
    new = {"index": "새것", "queries": {"1": {"name": "가", "description": "설명 :d0", "sql": sql}}}
    other = {"index": "딴것", "queries": {"1": {"name": "가", "description": "하나", "sql": "SELECT 1 FROM T_A"},
                                          "2": {"name": "나", "description": "둘", "sql": "SELECT 2 FROM T_B"}}}
    try:
        CACHE.unlink(missing_ok=True)
        assert manifest(lambda: new) == (new, None), "사본이 없으면 받아서 낸다"
        assert manifest(lambda: other) == (new, None), "사본이 싱싱하면 받지 않는다"
        os.utime(CACHE, (0, 0))
        assert manifest(lambda: other) == (other, None), "사본이 낡으면 다시 받는다"
        os.utime(CACHE, (0, 0))
        doc, warning = manifest(boom)
        assert (doc, bool(warning)) == (other, True), "못 받으면 낡은 사본을 내고 알린다"
        # query_index 문서가 없으면 낡은 사본이 있어도 넘어가지 않고 멈춘다
        try:
            manifest(lambda: from_doc({"doc_id": DOC_ID, "index": "목차뿐"}))
        except SystemExit as e:
            assert "매니페스트가 발행되지 않았다" in str(e), e
        else:
            raise AssertionError("발행본이 없으면 멈춘다")
        CACHE.unlink()
        try:
            manifest(boom)
        except SystemExit:
            pass
        else:
            raise AssertionError("사본이 없는데 못 받으면 멈춘다")
        for bad in (None, {}, {"index": "x"}, {"queries": {"1": {}}}, {"index": "x", "queries": {}}):
            try:
                from_doc(bad)
            except NotPublished:
                pass
            else:
                raise AssertionError(f"발행본이 아니면 거절한다: {bad}")
        assert from_doc({"doc_id": DOC_ID, "index": "i", "queries": {"1": {}}, "query_ids": [1]}) \
            == {"index": "i", "queries": {"1": {}}}, "목차와 쿼리만 남긴다"
        # DBGateway 처럼 문자열·주석 안의 콜론도 세고, 처음 나온 순서로 중복 없이 낸다
        assert bind_keys(sql) == ["d0", "MI", "c", "codes"], bind_keys(sql)
        assert bind_keys("SELECT 1 FROM T_A WHERE x = :오늘") == ["오늘"]
        assert render(other, []) == "딴것", "id 가 없으면 목차만 낸다"
        out = render(new, ["1"])
        assert "## id 1 · 가" in out and "- 설명: 설명 :d0" in out, out
        assert "- 인자 키: `d0`, `MI`, `c`, `codes`" in out, out
        assert "```sql\n" + sql + "\n```" in out, out
        two = render(other, ["2", "1"])
        assert two.index("## id 2 · 나") < two.index("## id 1 · 가"), "고른 쿼리만 고른 순서로 낸다"
        # 바인드가 없는 쿼리는 인자 키가 없음이다
        assert "- 인자 키: 없음" in render(other, ["1"])
        # 없는 id 는 그 id 와 활성 쿼리만 실린다는 말을 적고 멈춘다
        try:
            render(other, ["3", "1"])
        except SystemExit as e:
            assert "3" in str(e) and "활성 쿼리만" in str(e), e
        else:
            raise AssertionError("없는 id 면 멈춘다")
    finally:
        shutil.rmtree(CACHE.parent, ignore_errors=True)
        CACHE = saved


def main() -> None:
    # Windows 에서 출력이 파이프로 나가면 파이썬은 CP949 로 쓰고, 매니페스트의 '—'·'−' 에서 멈춘다.
    # --help 와 인자 오류도 이 설정을 거치도록 인자를 해석하기 전에 둔다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="DBGateway 매니페스트의 쿼리 목차나 고른 쿼리의 상세를 낸다.")
    parser.add_argument("--query", nargs="+", default=[], metavar="id", help="이 쿼리들의 이름·설명·인자 키·등록된 SQL 을 낸다")
    parser.add_argument("--selfcheck", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.selfcheck:
        _selfcheck()
        print("selfcheck ok")
        return
    doc, warning = manifest()
    text = render(doc, args.query)
    if warning:
        print(f"경고: {warning}", file=sys.stderr)
        print(f"> **경고 — {warning}**\n")
    print(text)


if __name__ == "__main__":
    main()
