# 결과표 조회 화면 템플릿

`dashboard-template` 으로 만든 대시보드 저장소에 결과표 조회 기능을 넣는 절차다. 화면과 API 의 구조는 템플릿으로 같게 유지하고, 엑셀마다 달라지는 값은 `table_plan.json` 과 `calc.py` 뿐이다.

## 복사 절차

`<기능>` 은 영문 소문자 이름이다.

1. `backend` 폴더를 `src/backend/<기능>/` 으로 복사한다.
2. 같은 폴더에 `table_plan.json` 과 `calc.py` 를 둔다.
3. `src/backend/main.py` 에 API 를 연결한다.

   ```python
   from src.backend.<기능> import create_router

   app.include_router(create_router("<스키마>"), prefix="/api/<기능>")
   ```

4. `pyproject.toml` 의 `dependencies` 에 `httpx`, `openpyxl`, `python-multipart` 를 추가한다.
5. `frontend` 의 파일을 `src/frontend/src/pages/<기능>/` 으로 복사한다.
6. `src/frontend/src/routes.tsx` 의 메뉴 목록에 줄을 추가한다.

   ```tsx
   { name: '<화면 이름>', path: '/<기능>', page: () => <ExcelFeaturePage api="/api/<기능>" /> }
   ```

7. 서버 환경 변수에 `KIWOOM_ACCESS_KEY` 와 `QUERY_GATEWAY_URL` 을 넣는다.

## 지킬 규칙

- 복사한 코드를 고치지 않는다. 고칠 일이 생기면 스킬의 템플릿을 먼저 고치고 다시 복사한다.
- 화면 접근 제한이 없으면 업로드와 다시 받기를 열지 않는다. 그때는 `router.py` 의 `/upload` 와 `/refetch` 를 빼고, 화면의 두 단추도 뺀다.
- 동시 업로드는 프로세스 안의 잠금으로 거절한다. 백엔드를 `uvicorn` 단일 프로세스로 실행한다는 전제이고, 프로세스를 늘리면 잠금을 다시 설계한다.
- 저장 경로를 바꿀 때는 `store.py` 의 `SandboxClient` 만 바꾼다. 소수와 날짜를 글자로 돌려주고 기준일 범위를 통째로 교체하는 동작은 같아야 한다.
- 한 대시보드에 기능을 여러 개 넣어도 복사한 코드는 같은 버전이어야 한다. 모듈 이름이 같아서 먼저 읽은 코드가 쓰이기 때문이다.
