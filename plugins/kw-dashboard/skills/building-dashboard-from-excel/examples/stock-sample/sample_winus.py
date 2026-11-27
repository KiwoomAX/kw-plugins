"""예시 화면의 등록 쿼리 대신. 템플릿 winus.fetch 와 같은 모양이지만 등록 쿼리 서버를 호출하지 않고 예시 저장소의 그 기준일 주가 행을 돌려준다.

예시 화면이 개발자 접근 키로 실제 등록 쿼리를 호출하지 않게 하기 위해서다. FOLDER 는 router.py 가 정한다.
"""
import json
from pathlib import Path

from winus import WinusRefused, WinusStopped  # noqa: F401  업로드가 이 모듈의 오류 이름을 쓴다

FOLDER = Path(__file__).resolve().parent / "store"
PRICE = "stock_sample__raw_winus__price"
HIDDEN = ("base_date", "base_time", "loaded_at")


def fetch(query_id, args, *, timeout=None):
    path = Path(FOLDER) / f"{PRICE}.json"
    rows = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return [{k: v for k, v in r.items() if k not in HIDDEN} for r in rows if r["base_date"] == args.get("base_date")]
