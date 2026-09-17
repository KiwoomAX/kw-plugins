# 3단계 — 비밀을 넘기는 통로

SKILL.md 의 3단계에서 연다. compose 파일과 Dockerfile 을 쓰거나 고칠 때 키 종류마다 이 통로를 따른다.

비밀은 이미지에 넣지 않고 Jenkins 자격증명에서 꺼내 필요한 순간에만 쓴다. 같은
종류의 키는 어느 저장소든 같은 통로를 쓴다. 기존 Dockerfile 이 이와 다르면 이 표대로 고친다.

| 키 종류 | 쓰는 때 | 통로 |
|---|---|---|
| GitHub App 개인키 `certs/kiwoom.pem` | 빌드 때 사설 저장소를 설치할 토큰을 받을 때 | compose `build.secrets` 의 `ghpem` 을 `RUN --mount=type=secret,id=ghpem,required=true` 로 그 명령 동안만 본다 |
| `.env` 값 — API 키·DB 접속 정보 | 컨테이너 실행 때 | `envCredIds` 자격증명을 이어 붙인 `.env` 를 compose `env_file` 이 환경변수로 넣는다 |
| 파일 키 — Google 서비스 계정 JSON 같은 것 | 컨테이너 실행 때 | JSON 을 base64 한 줄로 바꿔 `.env` 에 `<이름>_B64` 로 넣고 코드가 디코드해 읽는다 |
| 사내 CA `certs/ePrism.crt` | 빌드·실행 때 TLS 검증 | 비밀이 아닌 공개 인증서라 이미지에 넣는다. 파이프라인이 빌드마다 복원하고 지우지 않는다 |

**개인키는 `COPY` 하지 않는다.** `COPY` 한 뒤 `rm` 해도 레이어에 남아 `docker save` 로 꺼낼 수 있다. secret
마운트는 그 `RUN` 동안만 파일을 보여 주고 레이어에 남기지 않는다. `required=true` 가 있어 키가 없으면 빌드가
조용히 넘어가지 않고 바로 실패한다. 토큰은 설치 URL 에 박지 않고 `insteadOf` 로 넣었다가 설치 뒤 지운다.
TLS 검증은 끄지 않는다(`http.sslVerify false`·검증을 끈 연결을 쓰지 않는다) — 사내 CA 를 먼저 등록하면 된다.

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 사내 CA 를 시스템에 등록한다 — 아래 토큰 발급과 git clone 이 TLS 검증을 켠 채 돈다
COPY certs/ePrism.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# 개인키는 secret 으로만 받는다. App ID·Installation ID 는 compose build args 로 받는다.
ARG GITHUB_APP_ID=""
ARG GITHUB_INSTALLATION_ID=""
RUN --mount=type=secret,id=ghpem,required=true \
    uv pip install --system --no-cache PyJWT cryptography && \
    GITHUB_TOKEN=$(python -c "\
import jwt, time, json; \
from urllib.request import Request, urlopen; \
key = open('/run/secrets/ghpem').read(); \
now = int(time.time()); \
tok = jwt.encode({'iat': now-60, 'exp': now+600, 'iss': '${GITHUB_APP_ID}'}, key, algorithm='RS256'); \
req = Request('https://api.github.com/app/installations/${GITHUB_INSTALLATION_ID}/access_tokens', method='POST', headers={'Authorization': f'Bearer {tok}', 'Accept': 'application/vnd.github+json'}); \
print(json.loads(urlopen(req).read())['token'])") && \
    git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/" && \
    uv pip install --system --no-cache "git+https://github.com/KiwoomAM/Kiwoom-Manager.git@main#subdirectory=<패키지>" && \
    git config --global --unset-all url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf && \
    uv pip uninstall --system PyJWT cryptography
```

**파일 키는 경로 대신 환경변수를 받게 코드를 고친다.** 이미지에 JSON 을 복사하고 경로로 읽던 코드라면 이렇게 바꾼다.
값을 만들어 환경변수 등록 요청에 싣는 법은 ax-requests.md 의 「보내는 법」에 있다.

```python
creds = Credentials.from_service_account_info(
    json.loads(base64.b64decode(os.environ["GSHEET_CREDS_B64"])), scopes=SCOPES)
```
