# 결과표 조회 화면 템플릿

`dashboard-template` 으로 만든 대시보드 저장소에 결과표 조회 기능을 넣는 절차다. 엑셀마다 달라지는 값은 `table_plan.json` 과 `calc.py` 이다. 복사할지와 어떻게 고칠지는 개발자가 정한다.

## 복사 절차

`<기능>` 은 영문 소문자 이름이다.

대시보드 템플릿은 기능 폴더를 저절로 붙인다. 그래서 `main.py` 와 `routes.tsx` 는 고치지 않는다.

1. `backend` 폴더를 `src/backend/features/<기능>/` 으로 복사한다. 그 폴더의 `router.py` 가 API 를 `/api/<기능>` 아래에 붙인다.
2. 같은 폴더에 `table_plan.json` 과 `calc.py` 를 둔다. `table_plan.json` 의 `schema` 가 API 가 여는 스키마다.
3. `pyproject.toml` 의 `dependencies` 에 `httpx`, `openpyxl`, `python-multipart` 를 추가한다.
4. `frontend` 의 파일을 `src/frontend/src/features/<기능>/` 으로 복사한다.
5. 그 폴더의 `menu.ts` 에서 `<화면 이름>` 과 `<기능>` 을 바꾼다. 사이드바 메뉴에 그 이름으로 한 줄이 생긴다.
6. 서버 환경 변수에 `QUERY_GATEWAY_URL` 과 WINUS 조회용 `KIWOOM_ACCESS_KEY` 를 넣는다. 샌드박스는 화면을 쓰는 사람의 로그인 토큰으로 호출하므로 키가 필요 없다.
7. 그 화면의 `/api/` 요청에 로그인 토큰(`X-Auth-Access-Token` 헤더)을 넘기는 Kiwoom-Gateway 설정을 AX팀에 요청한다. 설정 전에는 화면이 「로그인 토큰을 받지 못했습니다」를 보인다.

## 지킬 규칙

- 업로드와 다시 받기도 그 사람의 로그인 토큰으로 저장하므로, 쓸 수 있는지는 샌드박스가 그 사람의 본부로 판정한다.
- 업로드 이력의 올린 사람 열은 `router.py` 의 `create_router(user_of=...)` 로 이름을 넘길 때만 채워진다. 넘기지 않으면 비어 있고, 누가 올렸는지는 샌드박스 작업 기록에 남는다.
- 동시 업로드는 프로세스 안의 잠금으로 거절한다. 백엔드를 `uvicorn` 단일 프로세스로 실행한다는 전제이고, 프로세스를 늘리면 잠금을 다시 설계한다.
- 저장 경로를 바꾸거나 올린 사람 이름을 넘길 때는 `router.py` 의 `create_router()` 한 줄만 고친다. 저장 경로는 `SandboxClient` 와 같은 `post(경로, 요청)` 을 가진 클라이언트를 `client=...` 로, 이름은 요청을 받아 이름을 돌려주는 함수를 `user_of=...` 로 넘긴다. `client` 를 넘기면 로그인 토큰을 쓰지 않으므로 그 클라이언트가 권한을 맡는다. 그 클라이언트도 소수와 날짜를 글자로 돌려주고 기준일 범위를 통째로 교체해야 한다.
- 한 대시보드에 기능을 여러 개 넣어도 복사한 코드는 같은 버전이어야 한다. 모듈 이름이 같아서 먼저 읽은 코드가 쓰이기 때문이다. 서버 코드를 고치면 같은 대시보드의 다른 기능 코드도 같게 고친다.
- `backend/file_client.py` 는 검토용 임시 저장소다. 스킬의 새 구조 임시 실행(`review_run.py`)과 예시 화면(`examples/stock-sample/`)에서만 쓰고, 운영 화면에서는 쓰지 않는다.
