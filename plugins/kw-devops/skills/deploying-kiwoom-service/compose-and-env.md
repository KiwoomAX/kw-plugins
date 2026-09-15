# 3단계 — compose 파일과 환경변수

SKILL.md 의 3단계에서 연다. `Jenkinsfile` 틀은 SKILL.md 에 있다.

아래 틀을 그대로 두고 이름·포트·경로만 바꾼다. 안 쓰는 줄은 지운다 — 주석까지 그대로 옮겨
붙이지 않는다.

**compose 파일이 이미 있으면 새로 만들지 않고 그 파일을 고친다.** 서비스 정의가 두 곳에 생기면
어느 쪽이 도는지 알 수 없다. 틀에서는 빠진 것(`name:`·`container_name`·`healthcheck`)만 가져온다.

**`docker-compose.yml`**

```yaml
name: <저장소 이름을 소문자로>              # compose 프로젝트 이름. 아래 「프로젝트 이름」을 본다
services:
  backend:
    container_name: kiwoom-<이름>          # 파이프라인이 이 이름으로 컨테이너를 찾는다
    platform: linux/amd64
    build:
      context: .
      dockerfile: Dockerfile
      # 사설 저장소(Kiwoom-Manager 같은 것)를 설치하는 이미지만 필요하다. 아니면 args·secrets 째로 지운다.
      args:
        GITHUB_APP_ID: ${GITHUB_APP_ID:-2826312}
        GITHUB_INSTALLATION_ID: ${GITHUB_INSTALLATION_ID:-108948292}
      secrets:                              # 빌드 때만 보인다. 컨테이너에는 들어가지 않는다
        - ghpem
    ports:
      - "<배정한 호스트 포트>:<컨테이너 포트>"
    env_file:
      - .env                                # 파이프라인이 자격증명에서 복원한다
    environment:
      - SERVICE_NAME=kiwoom-<이름>
    restart: unless-stopped
    healthcheck:                            # 없으면 배포가 100초 뒤 오탐 실패한다
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:<컨테이너 포트>/')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

secrets:
  ghpem:
    file: ./certs/kiwoom.pem
```

프론트엔드(nginx)면 `build.args` 로 `VITE_*` 를 넘기고 `ports` 를 `"<호스트>:80"` 으로 두며
`healthcheck` 는 `["CMD", "wget", "-qO-", "http://127.0.0.1/"]` 로 바꾼다. `localhost` 로 적으면 컨테이너
안에서 `::1` 로 먼저 풀려, IPv4 에만 붙은 nginx 가 거부하고 늘 unhealthy 가 된다.

**환경변수가 어디서 오는지 먼저 정한다.** `.env` 없이는 서비스가 안 도는데, 그 파일은 repo 에
없다 — 파이프라인이 Jenkins 자격증명에서 빌드마다 복원한다.

| 무엇 | 어디에 두나 |
|---|---|
| 비밀이 아닌 것 — 다른 서비스 주소·포트·워커 수 | compose 의 `environment:` 에 `${VAR:-기본값}`. 파일이 없어도 돈다 |
| 비밀 — 키·토큰·비밀번호 | Jenkins 자격증명 **`env-<서비스>`**. 키 이름은 코드가 읽는 그대로 두고 SKILL.md 의 「AX 팀에 등록 요청 보내기」로 AX 팀에 넣어 달라고 한다 |
| 파일 키 — 서비스 계정 JSON 같은 것 | base64 한 줄로 바꿔 `.env` 에 `<이름>_B64` 로 넣는다. 아래 「비밀을 넘기는 통로」 |
| 여러 자격증명을 합쳐 쓰려면 | SKILL.md 파라미터 표의 `envCredIds` 행을 따른다 |

**복원된 `.env` 에는 `global-env`(전사 공통)·`env-<조직>`(조직 공통)·`env-<서비스>` 의 키가 차례로 들어 있다.**
앞의 둘은 여러 잡이 함께 쓴다. `env_file: .env` 는 그 파일 전체를 컨테이너에 넣으므로 내 컨테이너가 공용 키까지
갖는다. 비밀이 아닌 값을 굳이 거기 넣지 않는다.

**필요한 키는 compose 에 적어 없으면 멈추게 한다.** 파이프라인은 `test -s .env` 로 **비어
있지 않은지만** 본다 — 내 키가 들었는지는 안 본다. 그냥 두면 키가 빠져도 Build 가 초록불로
지나가고 Health check 에서야 죽는데, 그 로그에는 원인이 안 보인다.

compose 의 `${VAR:?메시지}` 가 이것을 막는다. 없으면 **Build 첫 명령에서 변수 이름과 함께
멈춘다**.

```yaml
    environment:
      # 이 서비스가 반드시 필요로 하는 키. 없으면 여기서 멈춘다.
      - PARTNER_API_KEY=${PARTNER_API_KEY:?이 값이 서버에 등록돼 있지 않습니다. AX 팀에 "PARTNER_API_KEY 등록 요청" 이라고 전달해 주세요}
      # 없어도 되는 것은 기본값을 준다.
      - UVICORN_WORKERS=${UVICORN_WORKERS:-2}
```

```
error while interpolating services.backend.environment.[]:
  required variable PARTNER_API_KEY is missing a value:
  이 값이 서버에 등록돼 있지 않습니다. AX 팀에 "PARTNER_API_KEY 등록 요청" 이라고 전달해 주세요
```

**메시지는 담당자가 읽는다.** 그 사람은 개발자가 아니고 `global-env` 가 무엇인지 모른다. 그래서
저장소나 자격증명 이름을 쓰지 않고, **화면만 보고 바로 할 수 있는 행동 하나**를 적는다. 전달할
문장까지 따옴표 안에 담아 그대로 복사할 수 있게 한다.

| 이렇게 쓰지 않는다 | 이렇게 쓴다 |
|---|---|
| `global-env 에 없다` | `이 값이 서버에 등록돼 있지 않습니다` |
| `자격증명에 등록 필요` | `AX 팀에 "<키 이름> 등록 요청" 이라고 전달해 주세요` |
| `credential missing` | 한국어 존댓말로 쓴다 — 이 줄은 사람에게 하는 말이다 |

**코드에서 읽는 환경변수를 먼저 살펴 목록을 만든다**(`os.getenv`·`settings`·`env`). Jenkins 가
띄우는 서비스의 코드를 본다. 스케줄에만 쓰는 키는 SKILL.md 의 6단계가 따로 요청한다. 그 목록을 사용자에게 보여 어느 것이
비밀이고 어느 것이 기본값으로 충분한지 확인받은 뒤 compose 를 쓴다.

**비밀을 넘기는 통로** — 비밀은 이미지에 넣지 않고 Jenkins 자격증명에서 꺼내 필요한 순간에만 쓴다. 같은
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
값을 만들어 환경변수 등록 요청에 싣는 법은 SKILL.md 의 「AX 팀에 등록 요청 보내기」에 있다.

```python
creds = Credentials.from_service_account_info(
    json.loads(base64.b64decode(os.environ["GSHEET_CREDS_B64"])), scopes=SCOPES)
```

**빌드 산출물이 저장소에 없으면 멀티스테이지로 바꾼다.**

1단계에서 「`COPY` 하는 경로가 `.gitignore` 에 있다」가 나왔으면 그 산출물은 **누군가 자기 PC 에서
만들어 두는 것을 전제한 구조**다. 담당자는 개발자가 아니라 그 전제가 성립하지 않는다. 파이프라인이
직접 만들게 바꾼다.

**사내망이 HTTPS 를 가로채 컨테이너 안에서 `npm ci`·`pip install` 이 인증서 오류로 죽는데,
파이프라인이 그 해결책을 이미 워크스페이스에 놓아 준다** — Prepare secrets 가 복원하는
`certs/ePrism.crt` 가 사내 CA 다.

**CA 를 넣는 방법은 이미지마다 다르다.** node 는 시스템 인증서 저장소를 보지 않고
`NODE_EXTRA_CA_CERTS` 변수 하나만 본다. 게다가 `node:22-alpine` 에는 `update-ca-certificates` 가
없다. 파이썬 이미지는 위 「비밀을 넘기는 통로」의 Dockerfile 처럼 `update-ca-certificates` 로 시스템 저장소에
등록하고 `REQUESTS_CA_BUNDLE`·`SSL_CERT_FILE`·`CURL_CA_BUNDLE` 로 그 번들을 가리킨다.

저장소에 같은 CA 가 이미 커밋돼 있으면(예: `docker/certs/ePrism.crt`) 그것을 `COPY` 해도 된다.
파이프라인 복원에 기대지 않으므로 이 PC 에서도 빌드된다.

```dockerfile
FROM node:22-alpine AS build
COPY certs/ePrism.crt /usr/local/share/ca-certificates/eprism.crt
ENV NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/eprism.crt
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM nginx:1.29-alpine
COPY --from=build /web/dist /usr/share/nginx/html
```

**빌드 컨텍스트를 저장소 루트로 둔다.** `certs/` 와 소스를 둘 다 봐야 하기 때문이다.
compose 의 `context` 가 하위 폴더를 가리키고 있으면 루트로 올린다.

**루트로 올리면 무엇이 데몬으로 올라가는지도 정한다.** 루트에 `.dockerignore` 가 이미 있고 그것이
다른 이미지용이면 고치지 않는다 — 그 이미지의 빌드가 깨진다. 대신 Dockerfile 옆에
`<Dockerfile 이름>.dockerignore`(예: `docker/Dockerfile.dockerignore`)를 새로 둔다. BuildKit 은 그
파일을 루트 것보다 먼저 본다. 어느 쪽이든 `*` 로 닫고 실제로 `COPY` 하는 것만 연다 — 안 닫으면
`.env`·`data/` 까지 올라간다. **파일 끝에는 `.env` 와 `**/*.pem` 을 다시 막는 두 줄을 둔다.** 실수로 연 경로나
`COPY . .` 가 있어도 비밀이 빌드 컨텍스트에 실리지 않게 하는 마지막 방어선이다. 원래 하위 폴더에 있던 `.dockerignore`(예: `web/.dockerignore`)는 더는
쓰이지 않으므로 지운다.

**`docker-compose.jenkins.yml`** — 바인드 마운트가 있을 때만 만든다.

Jenkins 는 컨테이너 안에서 돌지만 `docker` 명령은 호스트 데몬이 실행한다. 그래서 호스트가
Jenkins 워크스페이스 경로를 못 보고 **상대경로 마운트가 빈 디렉터리로 덮인다.** 통째로 비우면
살려야 할 것까지 사라지므로 **마운트를 한 줄씩 셋으로 나눠 처리한다.**

| 마운트가 가리키는 것 | 어떻게 아나 | 처리 |
|---|---|---|
| **코드** — `./src`·`./app` | 이미지에 이미 들어 있다 | 비운다. 이미지에 구운 것을 쓴다 |
| **설정 파일** — `./nginx.conf`·`./config.yml` | 저장소에 있고 잘 안 바뀐다 | **Dockerfile 에 `COPY` 로 굽고 마운트를 지운다** |
| **런타임 자료** — 수집기가 쓰는 폴더, 업로드 보관소 | 저장소에 없고 서버에서 계속 쌓인다 | **아래 규약 경로로 바꾼다.** 절대경로는 호스트가 정상으로 본다 |
| **서버에만 있는 설정** — 인증 파일(`./auth`) 같은 것 | 저장소에는 없거나 빈 폴더(`.gitkeep`)이고 서버에서 손으로 넣는다 | **지우지 않는다. 서버의 절대경로로 다시 적는다.** 지우면 켜져 있던 인증 같은 기능이 조용히 꺼진다 |

**런타임 자료는 한 곳에 모은다.**

```
/home/chshin84/opt/<저장소 이름>/data/
```

**저장소 이름으로 키를 잡는다.** 컨테이너가 둘 이상이어도 자료는 하나를 함께 쓰기 때문이다
(화면 컨테이너와 수집기 컨테이너가 한 폴더를 함께 쓰는 식이다). 자료는 서비스에
딸린 것이지 컨테이너에 딸린 것이 아니다.

**코드와 자료를 갈라 두려는 것이다.** 저장소 체크아웃 안에 자료가 있으면 누가 다시 clone 하거나
폴더를 정리할 때 함께 날아간다.

```yaml
services:
  web:
    volumes: !override
      # 자료만 남긴다. 설정은 이미지에 구웠고 코드는 이미지에 있다.
      - /home/chshin84/opt/<저장소 이름>/data:/srv/data:ro
```

스케줄 등록 요청을 보낼 서비스가 자료를 쓰면 **그 서비스의 자료 마운트도 이 파일에 같은 규약 경로로
적는다.** 서버 crontab 이 이 덮어쓰기 파일을 함께 넘겨 돌리므로 화면 컨테이너와 그 서비스가 한 폴더를
본다.

```yaml
services:
  collector:
    volumes: !override
      - /home/chshin84/opt/<저장소 이름>/data:/srv/data
```

**폴더를 먼저 만들라고 알린다.** 없으면 도커가 컨테이너를 띄우며 **root 소유로** 만들어 버리고,
그러면 자료를 쓰는 쪽(cron 이나 수집기)이 못 쓴다. 조용히 빈 화면이 되는 길이라 반드시 먼저 알린다.

```bash
mkdir -p /home/chshin84/opt/<저장소 이름>/data
```

이 명령은 서버 계정이 있어야 돌므로 **담당자가 아니라 AX 팀이 한 번 돌린다.** 스킬은 그 줄을
그대로 내주고, 담당자에게는 「서버에 폴더 하나를 만들어 달라고 전달하세요」로만 말한다.

**이미 다른 곳에 쌓이고 있으면 그 경로를 그대로 쓴다.** 규약은 새로 붙이는 서비스에 건다.
도는 서비스의 자료를 옮기는 것은 그 자료를 쓰는 쪽(cron·수집기)까지 함께 고치는 일이라 배포와
관심사가 다르다. **이 스킬이 옮기자고 하지 않는다** — 지금 자료가 어디 있는지만 확인해(바로 아래)
절대경로로 적고, 옮기는 것은 따로 정할 일이라고 알린다.

**이미 도는 서비스를 넘겨받을 때** — 1단계의 `--find` 가 「뜬다」를 찍었으면 이 서비스는 Jenkins
밖에서 이미 돌고 있다. 두 가지가 달라진다.

**지금 쓰는 경로를 짐작하지 않는다.** 담당자는 서버를 볼 수 없고, README 나 폴더 구조로 추측한
경로가 틀리면 첫 배포가 자료 없는 화면을 띄운다. AX 팀에 「`<컨테이너>` 가 지금 쓰는 마운트 경로를
알려 주세요」라고 전달하게 하고, 받은 값을 절대경로로 적는다. **받기 전에는 push 하지 않는다.**
AX 팀은 이 명령 하나로 답한다.

```bash
docker inspect <컨테이너> --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'
```

마운트 중에 **설정 파일**(`nginx.conf` 같은 것)이 있으면 「서버의 그 파일이 저장소 `main` 의 것과
같은지도 봐 주세요」를 함께 전달한다. 3단계는 설정을 저장소 사본으로 이미지에 굽기 때문에, 서버
사본이 다르면 첫 배포가 화면 동작을 조용히 바꾼다. 다르다는 답이 오면 서버 사본을 받아 저장소에
넣은 뒤 굽는다.

**첫 배포가 지금 도는 컨테이너를 내린다.** Deploy 는 `conflictContainers`(기본값은 `healthContainer`)에
적힌 이름의 컨테이너를 어느 프로젝트 것이든 지우고 새로 띄운다. 새 컨테이너가 헬스 검사를 통과하면
그대로 넘겨받은 것이다. 사용자에게 「수동 빌드를 누르는 순간 지금 화면이 잠깐 내려갔다 다시 뜬다」고
미리 알린다.

새 대시보드는 대개 런타임 자료가 아예 없다 — 그때는 이 마운트를 만들지 않는다.

마운트가 아예 없으면 이 파일을 만들지 말고 Jenkinsfile 에서 `composeFiles: ['docker-compose.yml']`
하나만 넘긴다.

**compose 가 저장소 루트에 없어도 된다.** `docker compose -f docker/compose.yml` 은 그 파일이 있는
폴더를 기준으로 경로를 푼다. Jenkinsfile 에 그 경로를 적으면 그만이다. `docker-compose.jenkins.yml` 도
그 옆에 둔다(예: `docker/compose.jenkins.yml`). 여러 파일을 합칠 때 상대경로는 **첫 파일이 있는
폴더**를 기준으로 풀리므로, 덮어쓰기 안의 경로는 어디 두든 절대경로로 적는다. 다만 `.env` 는 워크스페이스
**루트**에 복원되므로, compose 가 `env_file` 을 쓰면 `../.env` 로 고친다.

**프로젝트 이름은 `name:` 으로 박아 둔다.** `kiwoomDeploy` 는 `-p` 를 넘기지 않으므로, 이름이 없으면
첫 compose 파일이 있는 폴더 이름이 프로젝트 이름이 된다. `docker/compose.yml` 이면 `docker` 다. 그러면
Deploy 의 `compose down --remove-orphans` 가 서버에서 같은 이름을 쓰는 남의 프로젝트까지 내린다.
저장소 이름을 소문자로 적는다(영문 소문자·숫자·`-`·`_` 만 된다). 그 compose 파일을 Jenkins 말고
다른 곳(서버 cron 의 `docker compose run` 같은 것)도 쓰면, 그쪽 프로젝트 이름도 함께 바뀐다고 알린다.
