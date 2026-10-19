"""DBGateway 에서 쿼리 목차나 고른 쿼리의 상세를 받아 표준 출력에 낸다.

인자 없이 돌리면 쿼리 단위 목차(id·이름·설명·사용 테이블)를 내고, --query 뒤에 쿼리 id 를 주면 그
쿼리들의 이름·설명·사용 테이블·인자·등록된 SQL 을 낸다. 목차에는 SQL 이 없고, SQL 은 고른 id 만
DBGateway 에 묻는다. 쓰지 않을 쿼리의 SQL 까지 사용자 PC 에 받지 않으려고 나눴다.

목차는 ~/.claude/cache/searching-winus/manifest_index.json 에 남긴다. 한 시간이 지나지 않은 사본이 있으면
DBGateway 를 부르지 않고 그것을 쓴다. 목차를 못 받았는데 사본이 낡았으면 낡은 것을 쓰되 첫 줄에 그렇게
적는다. 사본이 아예 없으면 멈춘다. SQL 은 남기지 않는다.

표준 라이브러리만 쓴다. 사내 SDK 는 비공개 저장소에 있어 사용자 PC 에서 설치하지 못한다.

사용: python scripts/fetch_manifest.py [--query id ...]
"""
import argparse
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

TTL_SECONDS = 3600
GATEWAY = os.environ.get("QUERY_GATEWAY_URL", "http://192.7.9.45:9101")
CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
CACHE = CONFIG_DIR / "cache" / "searching-winus" / "manifest_index.json"
# 옛 버전이 MongoDB 에서 받아 남긴 사본이다. 쿼리 전체의 SQL 이 들어 있어 보이는 대로 지운다.
OLD_CACHE = CACHE.with_name("query_index.json")


def get(path: str) -> dict:
    """DBGateway GET. 400 은 DBGateway 가 판정한 거절이라 낡은 사본으로 넘기지 않고 그 detail 로 멈춘다."""
    try:
        with urllib.request.urlopen(GATEWAY + path, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code != 400:
            raise
        body = e.read().decode("utf-8", "replace")
        try:
            body = json.loads(body).get("detail") or body
        except ValueError:
            pass
        raise SystemExit(f"DBGateway 가 거절했다: {body}")


def fetch_index() -> list[dict]:
    rows = get("/winus/manifest")["queries"]
    if not rows:
        raise ValueError("DBGateway 목차가 비어 있다")
    return rows


def cache_age() -> float | None:
    """사본을 받은 지 몇 초 지났는가. 사본이 없으면 None."""
    try:
        return time.time() - CACHE.stat().st_mtime
    except FileNotFoundError:
        return None


def read_cache() -> list[dict]:
    return json.loads(CACHE.read_text(encoding="utf-8"))


def manifest(fetch=fetch_index) -> tuple[list[dict], str | None]:
    """(목차 행, 경고). 경고가 있으면 낡은 사본을 낸 것이다."""
    OLD_CACHE.unlink(missing_ok=True)
    age = cache_age()
    if age is not None and age < TTL_SECONDS:
        return read_cache(), None
    try:
        rows = fetch()
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        if age is None:
            raise SystemExit(f"쿼리 목차를 받지 못했고 사본도 없다 — 사내망인지 확인한다. {detail}")
        return read_cache(), f"DBGateway 에서 목차를 받지 못해 {age / 3600:.1f}시간 지난 사본을 쓴다 — {detail}"
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    # 다른 세션이 반쯤 쓴 사본을 읽지 않도록 임시 파일에 쓴 뒤 바꿔 끼운다. Windows 에서는 그 순간
    # 다른 세션이 사본을 열고 있으면 교체가 거부되는데, 사본은 다음 실행에 다시 받으면 되므로 넘긴다.
    tmp = CACHE.with_name(f"{CACHE.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    try:
        os.replace(tmp, CACHE)
    except OSError:
        tmp.unlink(missing_ok=True)
    return rows, None


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_index(rows: list[dict]) -> str:
    lines = ["# DBGateway 쿼리 목차", "", "| id | 이름 | 설명 | 사용 테이블 |", "|---|---|---|---|"]
    lines += [f"| {q['query_id']} | {cell(q['query_name'])} | {cell(q['description'])} | {cell(', '.join(q['tables']))} |"
              for q in rows]
    return "\n".join(lines)


def render_detail(q: dict) -> str:
    args = ", ".join(f"`{a['name']}`({a['kind']}" + (f", 최대 {a['max_items']}개" if a.get("max_items") else "") + ")"
                     for a in q["arguments"]) or "없음"
    return "\n".join([f"## id {q['query_id']} · {q['query_name']}", "", f"- 설명: {q['description']}",
                      f"- 사용 테이블: {', '.join(q['tables'])}", f"- 인자: {args}", "- 등록된 SQL:", "",
                      "```sql", q["sql"], "```", ""])


def _selfcheck() -> None:
    import shutil
    global CACHE, OLD_CACHE
    # 사용자의 실제 사본과 섞이지 않게 빈 임시 폴더를 쓴다.
    saved = CACHE, OLD_CACHE
    CACHE = Path(tempfile.mkdtemp()) / "manifest_index.json"
    OLD_CACHE = CACHE.with_name("query_index.json")
    boom = lambda: (_ for _ in ()).throw(RuntimeError("끊김"))
    new = [{"query_id": 1, "query_name": "가", "description": "설명 | 하나", "tables": ["T_A", "T_B"]}]
    other = [{"query_id": 2, "query_name": "나", "description": "둘", "tables": ["T_C"]}]
    try:
        OLD_CACHE.write_text("{}", encoding="utf-8")
        assert manifest(lambda: new) == (new, None), "사본이 없으면 받아서 낸다"
        assert not OLD_CACHE.exists(), "옛 사본은 지운다"
        assert manifest(lambda: other) == (new, None), "사본이 싱싱하면 받지 않는다"
        os.utime(CACHE, (0, 0))
        assert manifest(lambda: other) == (other, None), "사본이 낡으면 다시 받는다"
        os.utime(CACHE, (0, 0))
        rows, warning = manifest(boom)
        assert (rows, bool(warning)) == (other, True), "못 받으면 낡은 사본을 내고 알린다"
        try:
            manifest(lambda: (_ for _ in ()).throw(SystemExit("DBGateway 가 거절했다: x")))
        except SystemExit as e:
            assert "거절" in str(e), e
        else:
            raise AssertionError("DBGateway 가 거절하면 낡은 사본으로 넘기지 않는다")
        CACHE.unlink()
        try:
            manifest(boom)
        except SystemExit:
            pass
        else:
            raise AssertionError("사본이 없는데 못 받으면 멈춘다")
        out = render_index(new)
        assert "| 1 | 가 | 설명 \\| 하나 | T_A, T_B |" in out, out
        d = render_detail({"query_id": 7, "query_name": "기준일", "description": "d", "tables": ["T"],
                           "sql": "SELECT 1 FROM T", "arguments": [{"name": "오늘", "kind": "스칼라"},
                                                                    {"name": "codes", "kind": "목록", "max_items": 100}]})
        assert "## id 7 · 기준일" in d and "- 인자: `오늘`(스칼라), `codes`(목록, 최대 100개)" in d, d
        assert "```sql\nSELECT 1 FROM T\n```" in d, d
        assert "- 인자: 없음" in render_detail({"query_id": 1, "query_name": "a", "description": "",
                                                 "tables": [], "sql": "", "arguments": []})
    finally:
        shutil.rmtree(CACHE.parent, ignore_errors=True)
        CACHE, OLD_CACHE = saved


def main() -> None:
    # Windows 에서 출력이 파이프로 나가면 파이썬은 CP949 로 쓰고, 목차의 '—'·'−' 에서 멈춘다.
    # --help 와 인자 오류도 이 설정을 거치도록 인자를 해석하기 전에 둔다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="DBGateway 의 쿼리 목차나 고른 쿼리의 상세를 낸다.")
    parser.add_argument("--query", nargs="+", type=int, default=[], metavar="id",
                        help="이 쿼리들의 이름·설명·사용 테이블·인자·등록된 SQL 을 낸다")
    parser.add_argument("--selfcheck", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.selfcheck:
        _selfcheck()
        print("selfcheck ok")
        return
    if args.query:
        print("\n".join(render_detail(get(f"/winus/manifest/{i}")) for i in args.query))
        return
    rows, warning = manifest()
    if warning:
        print(f"경고: {warning}", file=sys.stderr)
        print(f"> **경고 — {warning}**\n")
    print(render_index(rows))


if __name__ == "__main__":
    main()
