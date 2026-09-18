# /// script
# requires-python = ">=3.10"
# dependencies = [
#   # 커밋을 고정한다. 고정하지 않으면 uv 가 돌 때마다 GitHub 에 HEAD 를 물으러 가고, 사내망만
#   # 열려 있고 인터넷이 막힌 PC 에서는 스크립트가 시작조차 못 해 아래 사본 대비책이 무의미해진다.
#   # SDK 를 올릴 때 이 커밋을 손으로 바꾼다.
#   "kiwoom-mdb-manager @ git+https://github.com/KiwoomAM/Kiwoom-Manager.git@807890e686106719a0aa2f0aa054d6573dc16d65#subdirectory=mdb-manager",
# ]
# ///
"""매니페스트를 MongoDB 에서 읽어 표준 출력에 낸다.

받은 것은 ~/.claude/cache/searching-winus/manifest.md 에 남긴다. 한 시간이 지나지 않은 사본이
있으면 MongoDB 를 부르지 않고 그것을 낸다. MongoDB 를 못 읽었는데 사본이 낡았으면 낡은 것을
내되 첫 줄에 그렇게 적는다. 사본이 아예 없으면 멈춘다.

사용: uv run scripts/fetch_manifest.py
"""
import os
import sys
import time
from pathlib import Path

TTL_SECONDS = 3600
CONFIG_DIR = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
CACHE = CONFIG_DIR / "cache" / "searching-winus" / "manifest.md"

DB, COLLECTION, DOC_ID = "kw_ai", "winus_query_manifest", "manifest"


def cache_age() -> float | None:
    """사본을 받은 지 몇 초 지났는가. 사본이 없으면 None."""
    try:
        return time.time() - CACHE.stat().st_mtime
    except FileNotFoundError:
        return None


def fetch() -> str:
    from mdb_manager import MongoDBManager

    doc = MongoDBManager(database=DB, collection=COLLECTION).find_one({"doc_id": DOC_ID})
    if not doc or not doc.get("markdown"):
        raise LookupError(f"{DB}.{COLLECTION} 에 {DOC_ID} 문서가 없다 — 매니페스트가 아직 올라오지 않았다")
    return doc["markdown"]


def manifest(fetch_doc=fetch) -> tuple[str, str | None]:
    """(본문, 경고). 경고가 있으면 낡은 사본을 낸 것이다."""
    age = cache_age()
    if age is not None and age < TTL_SECONDS:
        return CACHE.read_text(encoding="utf-8"), None
    try:
        text = fetch_doc()
    except ImportError as e:
        # SDK 가 안 깔린 것이라 사본으로 넘기면 원인이 가려진다. 이것만 따로 세운다.
        raise SystemExit(f"kiwoom-mdb-manager 를 불러오지 못했다 — uv run 으로 돌리는지 확인한다. {e}")
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        if age is None:
            raise SystemExit(f"매니페스트를 읽지 못했고 사본도 없다 — 사내망인지 확인한다. {detail}")
        return CACHE.read_text(encoding="utf-8"), f"MongoDB 를 읽지 못해 {age / 3600:.1f}시간 지난 사본을 쓴다 — {detail}"
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(text, encoding="utf-8")
    return text, None


def _selfcheck() -> None:
    global CACHE
    saved, CACHE = CACHE, Path(os.environ.get("TMPDIR", "/tmp")) / f"sw_selfcheck_{os.getpid()}.md"
    boom = lambda: (_ for _ in ()).throw(RuntimeError("끊김"))
    try:
        CACHE.unlink(missing_ok=True)
        assert manifest(lambda: "새것") == ("새것", None), "사본이 없으면 받아서 낸다"
        assert manifest(lambda: "딴것") == ("새것", None), "사본이 싱싱하면 받지 않는다"
        os.utime(CACHE, (0, 0))
        assert manifest(lambda: "딴것") == ("딴것", None), "사본이 낡으면 다시 받는다"
        os.utime(CACHE, (0, 0))
        text, warning = manifest(boom)
        assert (text, bool(warning)) == ("딴것", True), "못 받으면 낡은 사본을 내고 알린다"
        CACHE.unlink()
        try:
            manifest(boom)
        except SystemExit:
            pass
        else:
            raise AssertionError("사본이 없는데 못 받으면 멈춘다")
    finally:
        CACHE.unlink(missing_ok=True)
        CACHE = saved


def main() -> None:
    if "--selfcheck" in sys.argv:
        _selfcheck()
        print("selfcheck ok")
        return
    text, warning = manifest()
    if warning:
        print(f"경고: {warning}", file=sys.stderr)
        print(f"> **경고 — {warning}**\n")
    print(text)


if __name__ == "__main__":
    main()
