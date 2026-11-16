# PC 에서 띄워 확인하는 명령 예시

이 파일은 `feature_code_rules.md` 「PC에서 띄워 확인하기」의 명령 예시다. 지킬 조건은 그 절에 있다.

- 파이썬 환경은 기능 레포 안에 `python -m venv .venv` 로 만든다. 의존성은 `requirements.txt` 에 `==` 로 버전을 고정해 적고 `.venv\Scripts\pip install -r requirements.txt` 로 설치한다. 전역 파이썬에 패키지를 설치하지 않는다.
- 백엔드는 `.venv\Scripts\uvicorn <모듈>:app --host 127.0.0.1 --port 8000 --reload` 로 PC 안에만 띄운다. 라우터를 등록하는 작은 FastAPI 앱 파일을 기능 레포에 함께 둔다. 이 파일은 대시보드에 붙일 때 쓰지 않는다.
- 화면은 Vite 개발 서버를 `--host 0.0.0.0` 으로 띄워 다른 PC 에서도 IP 로 접속할 수 있게 한다. Vite 설정의 `server.proxy` 로 `/api` 요청을 `http://127.0.0.1:8000` 에 넘긴다. 포트가 이미 쓰이고 있으면 비어 있는 포트를 쓴다.
- 띄운 뒤 개발자에게 `http://<이 PC의 IP>:<Vite 포트>` 주소를 알린다. 처음 띄울 때 Windows 방화벽 허용 창이 나오면 허용하라고 안내한다. 회사 정책으로 막혀 있으면 PC 안에서만 확인하고 AX팀에 문의하라고 알린다.
- 띄운 화면은 사내망에 인증 없이 열린다. 확인이 끝나면 서버를 끄라고 알린다.
