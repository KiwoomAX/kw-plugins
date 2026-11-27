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


def _login_token(request):
    """화면 앞의 Kiwoom-Gateway 가 넘겨 준 로그인 토큰. 비어 있으면 샌드박스를 호출하지 않고 끝낸다.
    화면을 쓰는 사람이 고칠 수 없는 설정 문제라 503 으로 알린다."""
    from fastapi import HTTPException
    token = request.headers.get("X-Auth-Access-Token", "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="로그인 토큰을 받지 못했습니다. 이 화면의 /api/ 에 토큰을 넘기는 Kiwoom-Gateway 설정을 AX팀에 요청해 주세요")
    return token


def create_router(user_of=None, client=None):
    """기능의 API. 스키마는 table_plan.json 의 schema 를 쓴다.
    user_of(request) 는 로그인한 사람의 이름을 돌려주고, 업로드 이력에만 남는다.
    client 를 주지 않으면 요청마다 그 사람의 로그인 토큰으로 샌드박스를 호출한다. 권한은 샌드박스가 그 사람 기준으로 판정한다."""
    import api
    import store
    import winus
    plan = json.loads((HERE / "table_plan.json").read_text(encoding="utf-8"))
    if client is not None:
        def store_for(request):
            return store.Store(client, plan["schema"], plan)
    else:
        def store_for(request):
            return store.Store(store.SandboxClient(_login_token(request)), plan["schema"], plan)
    return api.make_router(plan, store_for, winus, _calculate(), user_of or (lambda request: ""))
