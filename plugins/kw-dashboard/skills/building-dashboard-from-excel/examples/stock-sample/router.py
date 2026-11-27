"""예시 화면의 API. 템플릿 router.py 와 달리 create_router 를 쓰지 않는다.

create_router 는 저장 클라이언트만 바꿀 수 있고 등록 쿼리 모듈은 바꿀 수 없다. 예시 화면은 샌드박스와 등록 쿼리 서버를 호출하지 않아야 하므로
같은 폴더의 table_plan.json 과 calc.py, PC 파일 저장소(store/), 가짜 등록 쿼리(sample_winus.py)로 API 를 직접 만든다.
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1] / "templates/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import api  # noqa: E402
import store  # noqa: E402
from file_client import FileClient  # noqa: E402


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_router(folder=None):
    """folder 는 저장소 폴더다. 주지 않으면 이 폴더의 store/ 를 쓴다. 시험은 복사본 폴더를 넘겨 원본을 바꾸지 않는다."""
    folder = Path(folder) if folder else HERE / "store"
    plan = json.loads((HERE / "table_plan.json").read_text(encoding="utf-8"))
    sample_winus = _module("stock_sample_winus", HERE / "sample_winus.py")
    sample_winus.FOLDER = folder
    calculate = _module("stock_sample_calc", HERE / "calc.py").calculate
    return api.make_router(plan, lambda request: store.Store(FileClient(folder, plan), plan["schema"], plan), sample_winus, calculate, lambda request: "예시")


router = make_router()
