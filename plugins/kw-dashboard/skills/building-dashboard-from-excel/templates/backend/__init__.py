"""대시보드 저장소에 복사한 기능 하나. create_router 가 이 폴더의 table_plan.json 과 calc.py 로 API 를 만든다."""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _calculate():
    spec = importlib.util.spec_from_file_location(f"{HERE.name}_calc", HERE / "calc.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.calculate


def create_router(user_of=None, client=None):
    """기능의 API. 스키마는 table_plan.json 의 schema 를 쓴다.
    user_of(request) 는 로그인한 사람의 이름을 돌려주고, 업로드 이력에만 남는다. client 를 주지 않으면 샌드박스에 저장한다."""
    import api
    import store
    import winus
    plan = json.loads((HERE / "table_plan.json").read_text(encoding="utf-8"))
    return api.make_router(plan, store.Store(client or store.SandboxClient(), plan["schema"], plan), winus, _calculate(), user_of or (lambda request: ""))
