# /// script
# requires-python = ">=3.10"
# dependencies = [
#   # 커밋을 고정한다. 고정하지 않으면 uv 가 돌 때마다 GitHub 에 HEAD 를 물으러 가고, 사내망만
#   # 열려 있고 인터넷이 막힌 PC 에서는 스크립트가 시작조차 못 해 아래 사본 대비책이 무의미해진다.
#   # SDK 를 올릴 때 이 커밋을 손으로 바꾼다.
#   "kiwoom-mdb-manager @ git+https://github.com/KiwoomAM/Kiwoom-Manager.git@807890e686106719a0aa2f0aa054d6573dc16d65#subdirectory=mdb-manager",
# ]
# ///
"""매니페스트를 MongoDB 에서 읽어 목차나 고른 화면의 상세를 표준 출력에 낸다.

인자 없이 돌리면 화면 단위 목차(화면 설명과 쿼리 요약)를 내고, --screen 뒤에 화면번호를 주면 그
화면들의 사용법(쿼리 설명·인자 표·결과 항목 표)을 낸다. 읽는 쪽이 필요한 화면만 읽게 하려고 나눴다.

받은 것은 ~/.claude/cache/searching-winus/manifest.json 에 남긴다. 한 시간이 지나지 않은 사본이
있으면 MongoDB 를 부르지 않고 그것을 쓴다. MongoDB 를 못 읽었는데 사본이 낡았으면 낡은 것을
쓰되 첫 줄에 그렇게 적는다. 사본이 아예 없으면 멈춘다.

사용: uv run scripts/fetch_manifest.py [--screen 화면번호 ...]
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

TTL_SECONDS = 3600
CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
CACHE = CONFIG_DIR / "cache" / "searching-winus" / "manifest.json"

DB, COLLECTION, DOC_ID = "kw_ai", "winus_query_manifest", "manifest"


def cache_age() -> float | None:
    """사본을 받은 지 몇 초 지났는가. 사본이 없으면 None."""
    try:
        return time.time() - CACHE.stat().st_mtime
    except FileNotFoundError:
        return None


def fetch() -> dict:
    from mdb_manager import MongoDBManager

    doc = MongoDBManager(database=DB, collection=COLLECTION).find_one({"doc_id": DOC_ID})
    if not doc:
        raise LookupError(f"{DB}.{COLLECTION} 에 {DOC_ID} 문서가 없다 — 매니페스트가 아직 올라오지 않았다")
    if not doc.get("index") or not doc.get("screens"):
        raise LookupError(f"{DB}.{COLLECTION}/{DOC_ID} 에 목차와 화면별 상세가 없다 — 예전 모양으로 발행돼 있다")
    return {"index": doc["index"], "screens": doc["screens"]}


def read_cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8"))


def manifest(fetch_doc=fetch) -> tuple[dict, str | None]:
    """({"index", "screens"}, 경고). 경고가 있으면 낡은 사본을 낸 것이다."""
    age = cache_age()
    if age is not None and age < TTL_SECONDS:
        return read_cache(), None
    try:
        doc = fetch_doc()
    except ImportError as e:
        # SDK 가 안 깔린 것이라 사본으로 넘기면 원인이 가려진다. 이것만 따로 세운다.
        raise SystemExit(f"kiwoom-mdb-manager 를 불러오지 못했다 — uv run 으로 돌리는지 확인한다. {e}")
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


def render(doc: dict, screens: list[str]) -> str:
    """화면번호가 없으면 목차, 있으면 그 화면들의 상세."""
    if not screens:
        return doc["index"]
    unknown = [no for no in screens if no not in doc["screens"]]
    if unknown:
        raise SystemExit(f"매니페스트에 없는 화면번호다: {', '.join(unknown)} — 있는 화면: {', '.join(doc['screens'])}")
    return "\n".join(doc["screens"][no] for no in screens)


def _selfcheck() -> None:
    global CACHE
    saved, CACHE = CACHE, Path(tempfile.gettempdir()) / f"sw_selfcheck_{os.getpid()}.json"
    boom = lambda: (_ for _ in ()).throw(RuntimeError("끊김"))
    new = {"index": "새것", "screens": {"1": "가"}}
    other = {"index": "딴것", "screens": {"1": "가", "2": "나"}}
    try:
        CACHE.unlink(missing_ok=True)
        assert manifest(lambda: new) == (new, None), "사본이 없으면 받아서 낸다"
        assert manifest(lambda: other) == (new, None), "사본이 싱싱하면 받지 않는다"
        os.utime(CACHE, (0, 0))
        assert manifest(lambda: other) == (other, None), "사본이 낡으면 다시 받는다"
        os.utime(CACHE, (0, 0))
        doc, warning = manifest(boom)
        assert (doc, bool(warning)) == (other, True), "못 받으면 낡은 사본을 내고 알린다"
        CACHE.unlink()
        try:
            manifest(boom)
        except SystemExit:
            pass
        else:
            raise AssertionError("사본이 없는데 못 받으면 멈춘다")
        assert render(other, []) == "딴것", "화면번호가 없으면 목차만 낸다"
        assert render(other, ["2", "1"]) == "나\n가", "고른 화면만 고른 순서로 낸다"
        try:
            render(other, ["3"])
        except SystemExit:
            pass
        else:
            raise AssertionError("없는 화면번호면 멈춘다")
    finally:
        CACHE.unlink(missing_ok=True)
        CACHE = saved


def main() -> None:
    # Windows 에서 출력이 파이프로 나가면 파이썬은 CP949 로 쓰고, 매니페스트의 '—'·'−' 에서 멈춘다.
    # --help 와 인자 오류도 이 설정을 거치도록 인자를 해석하기 전에 둔다.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="DBGateway 매니페스트의 목차나 화면별 상세를 낸다.")
    parser.add_argument("--screen", nargs="+", default=[], metavar="화면번호", help="이 화면들의 상세를 낸다")
    parser.add_argument("--selfcheck", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.selfcheck:
        _selfcheck()
        print("selfcheck ok")
        return
    doc, warning = manifest()
    text = render(doc, args.screen)
    if warning:
        print(f"경고: {warning}", file=sys.stderr)
        print(f"> **경고 — {warning}**\n")
    print(text)


if __name__ == "__main__":
    main()
