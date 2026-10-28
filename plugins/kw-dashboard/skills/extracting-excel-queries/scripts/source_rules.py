"""출처 분류에 쓰는 대응표(이름 → WINUS · WFS)를 읽는다.

kw-plugins 는 공개 저장소라 사내 서버 · 스키마 · DB 링크 이름을 코드에 두지 않는다.
대응표는 사내 공용 폴더의 JSON 파일에 두고, 사내망에서 실행할 때만 읽힌다.
"""
import json
import pathlib

RULES_PATH = r"\\cifs\ai\projects\excel-analysis\source_rules.json"
KEYS = ("servers", "schemas", "links", "paths")


def load_rules(path=RULES_PATH) -> tuple[dict, str]:
    """(대응표, 상태). 읽으면 「읽음」, 파일이 없거나 형식이 틀리면 빈 대응표와 「읽기 실패」."""
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8-sig"))
        return {k: {str(n).upper(): str(v).upper() for n, v in data.get(k, {}).items()} for k in KEYS}, "읽음"
    except (OSError, ValueError, AttributeError):
        return {k: {} for k in KEYS}, "읽기 실패"
