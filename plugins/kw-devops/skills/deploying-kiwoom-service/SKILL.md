---
name: deploying-kiwoom-service
description: Use when a Kiwoom repo has to deploy through the shared Jenkins CI/CD pipeline on server 192.7.9.45 but has no docker-compose.yml and no Jenkinsfile yet. Picks a host port that will not collide by reading the kw_deploy.port registry through the rdb-handler and probing the server's live listeners, writes docker-compose.yml, the docker-compose.jenkins.yml DooD override, and a Jenkinsfile that only calls kiwoomDeploy, then registers the port. Reads the registry over HTTP, so it needs no repo access beyond the user's own. Needs no ssh account and no Docker on the user's PC. Triggers on 배포 붙여줘·CI/CD 태워줘·젠킨스 붙이기·파이프라인 연결·Jenkinsfile 만들어줘·docker compose 만들어줘·포트 뭐 쓰지·새 서비스 배포.
---

# deploying-kiwoom-service

repo 하나를 공용 Jenkins 파이프라인에 태운다. **만드는 것은 세 파일뿐이고, 파이프라인 로직은
한 줄도 만들지 않는다** — 그것은 `jenkins-shared-lib` 의 `kiwoomDeploy` 가 이미 갖고 있다.

| 만든다 | 무엇 |
|---|---|
| `docker-compose.yml` | 서비스 정의. 호스트 포트를 여기서 배정한다 |
| `docker-compose.jenkins.yml` | Jenkins(DooD) 전용 override. 바인드 마운트가 없으면 안 만든다 |
| `Jenkinsfile` | `kiwoomDeploy(...)` 호출 대여섯 줄 |

로직 정본은 `~/Kiwoom/jenkins-shared-lib/vars/kiwoomDeploy.groovy` 이고, 파라미터 목록은 같은
repo 의 `README.md` 다. **AX 팀이 고칠 때 보는 곳이다.** 담당자는 그 저장소를 열 수 없으므로, 이
스킬을 쓰는 데 필요한 동작은 이 문서에 옮겨 적었다.

## 서버 실측 (2026-09-08, `ssh -p 2222 chshin84@192.7.9.45`)

아래는 문서가 아니라 서버에서 직접 확인한 값이다. **README 와 어긋나는 것이 있으므로 문서만
읽고 판단하지 않는다.**

| 무엇 | 실측값 |
|---|---|
| Jenkins | 컨테이너 `jenkins`, 호스트 `9090`→내부 8080. 서버는 WSL2 + Docker Desktop |
| 조직 폴더 | `Kiwoom-AX`(repoOwner `KiwoomAX`)가 있고 스캔이 돌고 있다 |
| 스캔 주기 | `H/15 * * * *` — 15분마다. AX 스캔은 실제로 돌고 있다(2026-09-08 07:24 KST, 12초, repo 7개) |
| 발견 브랜치 | `RegexSCMHeadFilterTrait regex=main` — **`main` 만 발견한다.** 다른 브랜치는 잡조차 안 생긴다 |
| AX repo 현황 | `kw_install`·`Executive_dashboard`·`email_db`·`KW-doc-formats`·`DIMA`·`kw-plugins`·`wholesale-dashboard` 일곱 개가 모두 `Jenkinsfile` 없음으로 제외됐다 |
| 공용 라이브러리 | `jenkins-shared-lib`, defaultVersion `main`, `implicit=false`. Jenkins 전역 등록이다 |
| 자격증명 | 루트에 `global-env` 등이 있고 모든 잡이 받는다. `Kiwoom-AX` 폴더 전용 자격증명은 아직 없다 |
| 로그인 | GitHub 계정(2026-09-10 실측). `KiwoomAX` 조직원이면 잡을 읽고 빌드할 수 있다 |

### 무엇이 빌드를 일으키는가 — push 가 아니다

조직 폴더의 **빌드 268개를 전수로 세었다.** cron 263 · 수동 5 · 브랜치 인덱싱 0 · 웹훅 0.

`NoTriggerOrganizationFolderProperty` 가 `branches=.*` `strategy=INDEXING` 으로 걸려 인덱싱이
일으키는 빌드를 막고, `github-plugin-configuration.xml` 은 비어 있어 웹훅도 없다. 남은 트리거는
`kiwoomDeploy` 의 `cron(TZ=Asia/Seoul H 0 * * *)` 하나다.

**그래서 배포는 push 한 순간이 아니라 그날 자정에 일어난다.** Gate 가 최근 24시간 커밋을 확인해
있으면 배포하고 없으면 `NOT_BUILT` 로 끝낸다. 실제 로그가 그렇다.

```
Started by timer
Gate: 스케줄 + 최근 24h 커밋 있음 → 진행
OK: kiwoom-chatbot-stream-backend is healthy
Finished: SUCCESS
```

**즉시 배포하려면 Jenkins 화면에서 수동 빌드를 누른다.** 사용자에게 이 사실을 반드시 알린다 —
모르면 push 해 놓고 오지 않을 배포를 기다린다.

이 실측은 `changedOnly` 파라미터에도 걸린다. 선별 빌드는 push·인덱싱 트리거에서만 켜지는데 그
트리거가 0이므로 **켜 두어도 항상 전량 빌드가 돈다.** `Kiwoom-Handler` 가 `changedOnly: true` 로
켜 두었지만 실제로 선별로 돈 빌드는 없다. 새 repo 에 이 값을 넣을 이유가 지금은 없다.

### 이미 되어 있는 것 — 셋업부터 하자고 접근하지 않는다

공용 라이브러리 등록·자격증명·조직 폴더 잡이 모두 구축돼 있다. **KiwoomAX 스캔도 켜져 있으므로
AX repo 의 `main` 에 `Jenkinsfile` 을 올리면 15분 안에 잡이 저절로 생긴다** — 잡을 손으로 만들지
않는다. 공용 라이브러리는 Jenkins 전역 등록이라 그대로 닿는다.

## 절대 규칙

- **환경을 대신 확인해 주지 않는다.** 이 스킬은 담당자 PC 에서 돌고, 그 PC 의 사정은 거기서만
  알 수 있다. 0단계를 건너뛰고 "아마 될 것" 으로 넘어가지 않는다.
- **도커가 없는 것을 기본으로 놓고 쓴다.** 대시보드 담당자 PC 에 도커는 없고, 도커가 무엇인지도
  모른다. **검증은 Jenkins 가 하는 것이 정상 경로다.** 이 PC 에 도커가 있으면 더 빨리 확인할 수
  있을 뿐이고, 없다고 설치를 요구하거나 검증을 건너뛰지 않는다. 「도커가 있을 것」을 전제로 한
  문장을 스킬 어디에도 두지 않는다.
- **포트는 `pick_port.py` 로 정하고, 정했으면 `--register` 로 넣는다.** 등록부와 실측을 함께 봐야
  한다. 마크다운 표를 쓰던 때 표는 `kw-dashboard-web` 을 `9001` 로 적고 「`8080` 이 다시 비었다」고
  했는데 서버의 그 컨테이너는 `8080` 에서 돌고 있었다 — 그 표를 믿고 8080 을 가져갔으면 대시보드가
  죽는다.
- **값을 SQL 에 박지 않는다.** 등록은 `%(name)s` 바인드로만 넘긴다. `kiwoom-rdb-manager` SDK 를
  쓰지 않는 것은 그 패키지가 사는 저장소가 private 이라 AX 전용 개발자가 설치할 수 없어서이고,
  계약(바인드·자격증명 없음·엔드포인트 고정)은 그대로 지킨다.
- **`healthContainer` 로 지정한 컨테이너는 healthcheck 를 가져야 한다.** compose 의 `healthcheck:`
  이든 Dockerfile 의 `HEALTHCHECK` 이든 하나는 있어야 한다. 없으면 `docker inspect` 의
  `.State.Health` 가 비어 영영 `healthy` 가 못 되고, 파이프라인이 100초를 기다린 뒤 멀쩡한 배포를
  실패로 떨어뜨린다.
- **`container_name` 을 반드시 적는다.** 파이프라인이 컨테이너를 이름으로 찾는다.
- **`main` 에 올린다.** 조직 폴더가 `main` 만 발견하고 Gate 가 다른 브랜치를 한 번 더 막는다.
- **파이프라인 로직을 Jenkinsfile 에 복제하지 않는다.** stage 를 직접 쓰고 싶어지면 그것은
  shared-lib 에 넣을 변경이다.
- **`.env` 와 `certs/` 를 커밋하지 않는다.** 파이프라인이 자격증명에서 빌드마다 복원한다.
  `.gitignore` 에 둘을 넣는 것까지가 이 스킬의 몫이다.
- **포트를 정했으면 같은 작업 안에서 등록부에 넣는다.** 미루면 다음 사람이 같은 포트를 고르고,
  나중에 뜨는 쪽이 조용히 죽는다.

## 절차

### 0. 사전 점검 — 이 PC 가 돌릴 수 있는지부터 본다

```powershell
python "${CLAUDE_SKILL_DIR}/pick_port.py" --doctor
```

**환경은 사람마다 다르고, 남이 대신 확인해 줄 수 없다.** 담당자 PC 에 사내망이 닿는지, 도커가
있는지는 그 PC 에서만 알 수 있다. 다른 PC 에서 재 본 값을 가져다 쓰지 않는다.

셋을 찍는다 — 파이썬 버전, 포트 등록부 도달, 도커 유무. 막는 것이 있으면 무엇을 해야 하는지
화살표로 함께 적고 종료 코드 1 로 끝난다. **막는 것이 있으면 거기서 멈추고 사용자에게 그 줄을
그대로 보여 준다.** 도커가 없는 것은 막는 것이 아니다 — 검증은 원래 Jenkins 가 한다.

**남의 저장소를 읽지 않는다.** 담당자는 자기 레포 권한만 갖는다. **ssh 계정도 필요 없다.**
등록부는 `kw_deploy.port` 테이블이고 `kiwoom-rdb-handler`(8700)를
거쳐 읽으므로 사내망에 닿기만 하면 된다.

### 1. 조사 — 이미 등록된 서비스인지부터 찾는다

**포트를 새로 고르기 전에 이 서비스가 등록부에 있는지 먼저 본다.** 저장소 이름과, compose 파일이
이미 있으면 거기 적힌 `container_name` 을 **모두** 넘긴다.

```powershell
Get-ChildItem -Recurse -File -Filter '*compose*.y*ml' | Where-Object FullName -notmatch '[\\/]node_modules[\\/]' |
    Select-String '^\s*container_name:\s*(\S+)' | ForEach-Object { $_.Matches[0].Groups[1].Value }
python "${CLAUDE_SKILL_DIR}/pick_port.py" --find <저장소 이름> [<container_name> …]
```

**저장소 이름 하나로는 못 찾는 서비스가 있다.** 등록부의 옛 줄은 `repo` 칸이 비어 있다 — 임원실
대시보드의 `kw-dashboard-web` 두 줄이 그렇고, `--find Executive_dashboard` 는 「등록부에 없다」고
답한다(2026-09-10 실측). 그 답을 믿으면 이미 도는 서비스에 새 포트를 쥐여 준다.

찾은 줄마다 서버에서 **지금 뜨는지**도 함께 찍는다. 뜨는 줄이 있으면 이 서비스는 이미 서버에서
돌고 있으므로 3단계의 「이미 도는 서비스를 넘겨받을 때」를 따른다.

| 결과 | 어떻게 한다 |
|---|---|
| 없다 | 처음 올리는 서비스다. 조사를 마치고 **2단계로 간다** |
| 한 줄 있다 | 그 포트를 그대로 쓴다. **2단계를 건너뛰고 3단계로 간다** |
| 여러 줄 있다 | 어느 것을 쓸지 사용자에게 묻는다. `kw-dashboard-web` 이 `8080`·`9001` 둘을 갖고 있는 것이 그런 상태다 |

찾은 포트가 저장소 compose 의 `ports` 왼쪽 값과 다르면 3단계에서 찾은 포트로 고친다.

**이것을 빠뜨리면 이미 포트를 가진 서비스에 새 포트를 쥐여 준다.** 서비스가 조용히 다른 포트로
옮겨 가고 옛 줄은 등록부에 남아 썩는다. `container` 에 유일 제약이 없어(한 컨테이너가 포트 여럿을
갖는 것이 실제로 있다) 데이터베이스가 막아 주지 않는다.

그다음 repo 에서 여섯을 확인하고, 확인한 값을 사용자에게 보여 준 뒤 다음으로 간다.

| 확인할 것 | 어디서 | 왜 필요한가 |
|---|---|---|
| Dockerfile 위치와 컨테이너 내부 포트 | `Dockerfile` 의 `EXPOSE`·`CMD` | compose 의 `ports` 오른쪽 값 |
| 헬스 엔드포인트 | 앱 라우터(`/` 나 `/health`) | `healthcheck.test` |
| 소속 조직 | GitHub remote 의 조직 이름 | 등록부의 `org` 칸에 적는다 |
| 런타임에 읽는 호스트 파일 | 코드가 여는 절대경로 | Jenkins 덮어쓰기를 어떻게 쓸지 |
| **Dockerfile 이 `COPY` 하는 경로가 `.gitignore` 에 있는가** | `.gitignore` 와 `COPY` 줄을 대조 | 있으면 그 산출물이 저장소에 없다는 뜻이다. **Jenkins 는 clone 만 하므로 Build 가 거기서 죽는다** — 3단계에서 멀티스테이지로 바꾼다 |
| **compose 의 바인드 마운트가 각각 무엇인가** | `volumes:` 를 한 줄씩 | 설정·코드·자료 셋으로 갈리고 처리가 다르다(3단계) |

**Dockerfile 이 없으면 스택을 알아볼 수 있는지 본다.** 담당자는 개발자가 아니라서 「Dockerfile 을
만들어 오세요」로 끝내면 갈 곳이 없다. 그리고 **이미지를 빌드하는 것은 어차피 Jenkins 다** — 여기서
쓴 Dockerfile 은 4단계에서 실제로 빌드되고 헬스 검사까지 받으므로 짐작이 조용히 통과하지 못한다.

| 상태 | 어떻게 한다 |
|---|---|
| `Dockerfile` 이 있다 | 그대로 쓴다. 고치는 것은 3단계의 멀티스테이지 조건에 걸릴 때뿐이다 |
| 없지만 스택을 알아볼 수 있다 | `package.json`·`pyproject.toml`·`requirements.txt`·`go.mod` 를 보고 **만들어 주겠다고 제안한다.** 동의를 받고 쓴다 |
| 없고 스택도 모르겠다 | 거기서 멈추고 사용자에게 알린다 |

만들 때는 `EXPOSE` 와 `CMD` 를 반드시 적는다. 4단계가 그 포트로 헬스를 본다.

### 2. 포트 확정 — 처음 올리는 서비스일 때만

**1단계의 `--find` 가 이미 있다고 답했으면 이 단계를 건너뛴다.** 있는 포트를 그대로 쓴다.

```powershell
python "${CLAUDE_SKILL_DIR}/pick_port.py"
```

**두 곳을 보고 합친다.** 등록부(`kw_deploy.port`)는 「잡아 둔 것」이고 TCP 프로브는 「실제로 듣고
있는 것」이다. 어느 하나만 보면 구멍이 난다 — 등록만 되고 아직 안 뜬 포트를 프로브는 빈 포트로
보고, 뜨는데 등록 안 된 포트를 등록부는 모른다. 그래서 **차이를 먼저 찍는다.**

```
[차이] 등록됐지만 안 뜬다: 9001 kw-dashboard-web
위 차이를 사람에게 알린 뒤 포트를 고른다.
```

**차이가 나오면 포트를 고르기 전에 사용자에게 알린다.** 「뜨는데 등록이 없다」가 나오면 그 줄부터
등록부에 넣어야 다음 사람이 안 겹친다.

**망이 막히면 스크립트가 멈춘다.** 사내망 밖에서는 연결이 다 실패해 「전부 비었다」로 보이므로,
반드시 열려 있는 핸들러(`8700`)를 함께 물어보고 그것마저 닫혀 있으면 포트가 아니라 망을 의심하고
거기서 끝낸다. 다 비어 보이는 것을 빈 포트로 착각하면 안 된다.

**`9000`–`9199` 안에서 가장 작은 빈 포트를 고른다.** 이 대역이 이 스킬이 쓰는 전부다.
다른 대역은 다른 팀 것이라 건드리지 않고, 고르는 자리가 여기뿐이라 겹칠 일도 없다.
대역 규약은 `pick_port.py` 의 `대역` 상수가 정본이다.

고른 포트를 사용자에게 알리고 **동의를 받은 뒤** 다음으로 간다.

### 3. 세 파일 작성

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
      # Kiwoom-Manager 를 GitHub 에서 설치하는 이미지만 필요하다. 아니면 secrets 째로 지운다.
      secrets:
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
안에서 `::1` 로 먼저 풀려, IPv4 에만 붙은 nginx 가 거부하고 늘 unhealthy 가 된다(임원실 대시보드
compose 의 주석이 그 기록이다).

**환경변수가 어디서 오는지 먼저 정한다.** `.env` 없이는 서비스가 안 도는데, 그 파일은 repo 에
없다 — 파이프라인이 Jenkins 자격증명에서 빌드마다 복원한다.

| 무엇 | 어디에 두나 |
|---|---|
| 비밀이 아닌 것 — 다른 서비스 주소·포트·워커 수 | compose 의 `environment:` 에 `${VAR:-기본값}`. 파일이 없어도 돈다 |
| 비밀 — 키·토큰·비밀번호 | Jenkins 자격증명 **`global-env`**. 관리자가 그 파일에 넣는다 |
| 이 repo 만 쓰는 파일 — JSON 키 같은 것 | `extraCredentials` 로 워크스페이스에 복원 |
| 이 repo 만의 `.env` 가 필요하면 | `envCredId` 로 새 자격증명을 가리킨다 |
| 여러 자격증명을 합쳐 쓰려면 | `envCredIds: ['global-env', '<다른 것>']` — 앞에서 뒤 순서로 이어 붙고 같은 키는 뒤가 이긴다 |

**`global-env` 는 모든 잡이 함께 쓰는 파일 하나다**(2026-09-10 실측). 그래서 둘을 지킨다.

- **이름에 서비스 접두를 붙인다.** `API_KEY` 로 넣으면 남의 것과 부딪힌다. `MYSVC_API_KEY` 로 둔다.
- **`env_file: .env` 는 그 파일 전체를 컨테이너에 넣는다.** 내 컨테이너가 남의 키까지 갖게 되므로,
  비밀이 아닌 값을 굳이 거기 넣지 않는다.

**필요한 키는 compose 에 적어 없으면 멈추게 한다.** 파이프라인은 `test -s .env` 로 **비어
있지 않은지만** 본다 — 내 키가 들었는지는 안 본다. 그냥 두면 키가 빠져도 Build 가 초록불로
지나가고 Health check 에서야 죽는데, 그 로그에는 원인이 안 보인다.

compose 의 `${VAR:?메시지}` 가 이것을 막는다. 없으면 **Build 첫 명령에서 변수 이름과 함께
멈춘다**(실측: `config`·`build`·`up` 모두 종료 1).

```yaml
    environment:
      # 이 서비스가 반드시 필요로 하는 키. 없으면 여기서 멈춘다.
      - MYSVC_API_KEY=${MYSVC_API_KEY:?이 값이 서버에 등록돼 있지 않습니다. AX 팀에 "MYSVC_API_KEY 등록 요청" 이라고 전달해 주세요}
      # 없어도 되는 것은 기본값을 준다.
      - UVICORN_WORKERS=${UVICORN_WORKERS:-2}
```

```
error while interpolating services.backend.environment.[]:
  required variable MYSVC_API_KEY is missing a value:
  이 값이 서버에 등록돼 있지 않습니다. AX 팀에 "MYSVC_API_KEY 등록 요청" 이라고 전달해 주세요
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
띄우는 서비스의 코드만 본다 — cron 이 따로 부르는 수집기 같은 것은 이 배포와 상관없다. 그 목록을
사용자에게 보여 어느 것이 비밀이고 어느 것이 기본값으로 충분한지 확인받은 뒤 compose 를 쓴다.

**빌드 산출물이 저장소에 없으면 멀티스테이지로 바꾼다.**

1단계에서 「`COPY` 하는 경로가 `.gitignore` 에 있다」가 나왔으면 그 산출물은 **누군가 자기 PC 에서
만들어 두는 것을 전제한 구조**다. 담당자는 개발자가 아니라 그 전제가 성립하지 않는다. 파이프라인이
직접 만들게 바꾼다.

**사내망이 HTTPS 를 가로채 컨테이너 안에서 `npm ci`·`pip install` 이 인증서 오류로 죽는데,
파이프라인이 그 해결책을 이미 워크스페이스에 놓아 준다** — Prepare secrets 가 복원하는
`certs/ePrism.crt` 가 사내 CA 다. 사내 저장소들이 이미 이 파일을 쓴다(`Kiwoom-STT`·`Kiwoom-pdfCollector`).

**CA 를 넣는 방법은 이미지마다 다르다.** node 는 시스템 인증서 저장소를 보지 않고
`NODE_EXTRA_CA_CERTS` 변수 하나만 본다. 게다가 `node:22-alpine` 에는 `update-ca-certificates` 가
없다(실측: 종료 127). 파이썬 이미지는 `Kiwoom-STT` 처럼 시스템 번들 뒤에 붙이고
`REQUESTS_CA_BUNDLE`·`SSL_CERT_FILE` 로 그 번들을 가리킨다.

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
`.env`·`data/` 까지 올라간다. 원래 하위 폴더에 있던 `.dockerignore`(예: `web/.dockerignore`)는 더는
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

**`Jenkinsfile`**

```groovy
// <프로젝트> CI/CD — 공통 Shared Library(jenkins-shared-lib) 호출.
// 파이프라인 로직의 SSOT 는 공용 라이브러리의 vars/kiwoomDeploy.groovy 다.
// 이 파일은 프로젝트별 값(컨테이너 이름·compose 파일)만 주입한다.

@Library('jenkins-shared-lib') _

kiwoomDeploy(
    healthContainer: 'kiwoom-<이름>',
    composeFiles:    ['docker-compose.yml', 'docker-compose.jenkins.yml'],
)
```

넘길 일이 있는 파라미터는 이 다섯이 거의 전부다. 안 넘기면 기본값이 걸리므로 필요한 것만 적는다.

| 파라미터 | 언제 넘기나 |
|---|---|
| `healthContainer` | **필수.** 헬스를 볼 컨테이너 이름 하나 |
| `service` | compose 의 서비스 키가 `backend` 가 아니면 **반드시** 넘긴다. 기본값이 `backend` 라, 안 넘기면 Build 가 없는 서비스를 빌드하려다 멈춘다 |
| `services` | compose 에 배포할 서비스가 여럿일 때 그 목록. 적힌 것만 빌드하고 띄우므로, cron 이 부르는 수집기처럼 상시 뜨지 않는 서비스는 뺀다. 헬스는 여전히 `healthContainer` 한 곳만 본다 |
| `conflictContainers` | 안 넘기면 `healthContainer` 하나다. 서비스가 여럿일 때 나머지 `container_name` 까지 함께 넘긴다. 배포 직전 이 이름의 컨테이너를 어느 프로젝트 것이든 지운다 |
| `extraCredentials` | 공통 셋 말고 이 repo 만 쓰는 비밀 파일이 있을 때. `[[id: '<자격증명 ID>', file: '<경로>']]` |

`changedOnly` 는 넣지 않는다 — 선별 빌드는 push 트리거에서만 켜지는데 그 트리거가 없다(위 실측).

**전체 목록은 `jenkins-shared-lib` README 에 있지만 그 저장소는 담당자가 못 연다.** KiwoomAX 전용
계정으로는 안 열리므로, 위 넷으로 안 되는 것을 만나면 뒤지지 말고 관리자에게 묻는다.

`.gitignore` 에 `.env` 와 `/certs/` 를 넣는다. `certs/` 앞의 `/` 를 빼면 저장소 안 다른 폴더
(`docker/certs/` 같은 것)까지 가려진다.

### 4. 검증 — 돌려 보지 않고 됐다고 하지 않는다

**검증은 Jenkins 가 한다.** 담당자 PC 에 도커가 없는 것을 기본으로 놓는다 — 도커가 무엇인지도
모르는 사람이 대부분이다. Jenkins 가 곧 도커 환경이므로 거기서 빌드하고 띄워 보는 것이 정상
경로이고, 이 PC 에 도커가 있으면 그보다 먼저 한 번 걸러 볼 수 있을 뿐이다.

`docker compose version` 이 답하지 않아도 **그것은 막는 조건이 아니다.** 설치를 요구하지 않는다.

#### 기본 길 — Jenkins 에서

**Jenkins 가 곧 도커 환경이다.** 이 길에서는 push 가 검증보다 먼저 온다 — 5단계의 push 를 여기서
하고, 그 결과를 본다. 자정을 기다리지 않는다.

1. `main` 에 push 한다.
2. `http://192.7.9.45:9090` 에 **GitHub 계정으로 로그인**한 뒤, 조직 폴더 `Kiwoom-AX` 에서
   **Scan Organization Folder Now** 를 누른다. 15분 주기 스캔을
   기다리지 않고 잡이 바로 생긴다. `KiwoomAX` 조직원이면 이 버튼을 누를 수 있다.
3. 생긴 잡의 `main` 브랜치에서 **Build Now** 를 누른다. Gate·Build·Deploy·Health check 가 그대로 돈다.
4. **Console Output 을 끝까지 읽는다.** `Finished: SUCCESS` 가 아니면 고쳐서 다시 push 하고 2번부터
   되풀이한다.

**처음 올리는 서비스라면 첫 배포는 무너뜨릴 것이 없다.** Deploy 가 내리는 것은 그 compose 프로젝트와
`conflictContainers` 에 적힌 이름뿐인데 새 서비스에는 아직 아무것도 없다. 그러니 이 길에서 실패해도
남의 서비스는 멀쩡하다 — 겁내지 말고 눌러 본다. **이미 도는 서비스는 다르다** — 3단계의 「이미 도는
서비스를 넘겨받을 때」를 마친 뒤에 누른다.

**로그를 못 읽겠으면 Console Output 을 통째로 붙여 넣게 한다.** Claude 가 읽어 준다 — 이것이
자동화 대신 두는 길이고, 토큰도 권한도 필요 없다. 아래 표는 자주 나오는 줄을 먼저 걸러 주는 것뿐이다.

**아래 문자열은 `kiwoomDeploy.groovy` 에 그대로 있는 것이다.** 지어낸 것이 아니라 파이프라인이
실제로 찍는 줄이고, 운영 Jenkins 에 실패한 빌드가 아직 한 건도 없어 실물 로그로는 대조하지 못했다.

| 로그에 나오는 줄 | 뜻 | 어떻게 한다 |
|---|---|---|
| `Gate: main 외 브랜치(…) → 빌드/배포 안 함` | 브랜치를 잘못 올렸다 | `main` 에 올린다 |
| `Gate: 스케줄이지만 최근 24h 커밋 없음 → 건너뜀` | 자정 cron 인데 그날 커밋이 없다 | 정상이다. 지금 띄우려면 수동 빌드 |
| `Gate: 실행 조건 불충족 → 이후 stage 건너뜀` · `Finished: NOT_BUILT` | 위 둘 중 하나로 걸러졌다 | 위 두 줄을 먼저 본다 |
| `kiwoomDeploy: healthContainer 파라미터는 필수입니다` | Jenkinsfile 에 그 값을 안 넣었다 | 3단계의 틀을 다시 본다 |
| `Waiting for … (status: not_found)` 가 열 번 | **컨테이너 이름이 안 맞는다** | `healthContainer` 와 compose 의 `container_name` 을 같게 |
| `Waiting for … (status: unhealthy)` 가 열 번 | 컨테이너는 떴는데 healthcheck 명령이 실패한다 | 아래 컨테이너 로그 30줄이 이유를 말한다. 포트·경로를 먼저 본다 |
| `Waiting for … (status: starting)` 가 열 번 | 100초 안에 앱이 못 떴다 | `start_period` 를 늘리거나 앱 기동을 본다 |
| `FAILED: no container for <서비스>` | 서비스 이름이 compose 와 다르다 | `services` 값과 compose 의 키를 맞춘다 |
| `OK: <서비스> 는 healthcheck 미정의 → 헬스 검증 생략` | 초록불이지만 **검증을 안 한 것이다** | healthcheck 를 넣는다. 안 넣으면 고장을 못 잡는다 |
| `OK: … is healthy` · `Finished: SUCCESS` | 떴다 | 5단계로 간다 |

**Build 단계에서 멈추면 위 표에 없는 줄이 나온다.** 그것은 파이프라인이 아니라 docker 가 찍는
것이라(`port is already allocated`·`failed to solve`·`no such file or directory` 따위) 상황마다
다르다. 그때는 표를 뒤지지 말고 **그 줄을 붙여 넣게 한다.**

#### 빠른 길 — 이 PC 에 도커가 있을 때만

```powershell
docker compose -f docker-compose.yml -f docker-compose.jenkins.yml config | Out-Null   # 문법·병합
docker compose up -d --build backend
docker inspect --format='{{.State.Health.Status}}' kiwoom-<이름>                        # healthy 여야 한다
```

`healthy` 가 안 나오면 파이프라인에서도 안 나온다. 확인이 끝나면 `docker compose down` 으로 내린다.

**`.env` 와 `certs/` 는 Jenkins 가 빌드마다 복원하는 것이라 이 PC 에는 없다.** compose 나 Dockerfile 이
그중 하나라도 쓰면(`env_file`·`secrets`·`COPY certs/…`) 이 길을 쓰지 않는다. `.env` 가 없으면
`docker compose config` 부터 `env file not found` 로 멈추고, pem 이 없으면 build 에서 멈춘다(실측).
기본 길로 충분하다.

**이 PC 에 같은 이름의 컨테이너가 이미 있으면 `build`·`up`·`down` 은 돌리지 않는다**
(`docker ps -a --filter name=<container_name>`). 그 컨테이너와 이미지를 덮어쓰거나 내린다. `config` 는
아무것도 만들지 않으므로 그래도 돌린다.

### 5. 등록부에 넣고 push, 그리고 언제 뜨는지 알리기

```powershell
python "${CLAUDE_SKILL_DIR}/pick_port.py" --register <포트> <컨테이너> <service_type> [org [repo]]
```

**역할과 조직이 두 칸으로 갈려 있다.** 한 칸에 섞여 있던 때는 AX 프론트엔드가 어느 값인지
정할 수 없었는데, 이제 `frontend` + `KiwoomAX` 로 그냥 적는다.

| 칸 | 쓸 수 있는 값 |
|---|---|
| `service_type` | `infra` · `backend` · `frontend` · `dashboard` |
| `org` | `KiwoomAM` · `KiwoomAX`. 이미지를 그대로 띄운 인프라는 뺀다 |
| `repo` | 저장소 **이름만**. 조직은 `org` 칸에 있다 |

**`infra` 는 남이 부르는 공용 설비다.** 핸들러와 데이터베이스가 그렇다. 서비스 백엔드가 아니라
여러 서비스가 함께 부르는 것이면 `infra` 로 넣되, 소속과 저장소는 그대로 적는다.

**넣는 것을 미루지 않는다.** 안 넣으면 다음 사람이 같은 포트를 고르고, 나중에 뜨는 쪽이 조용히
죽는다.

**1단계의 `--find` 가 이미 찾았으면 새로 넣을 것은 없다.** 그래도 쓸 포트로 한 번 돌린다 — 그 줄의
`repo` 칸이 비어 있으면 저장소 이름을 채우고, 차 있으면 아무것도 안 한다. 채워 두어야 다음 사람이
저장소 이름만으로 찾는다. 「남이 먼저 잡았다」고 하면 그 포트는 다른 서비스 것이므로 2단계로 돌아가 다시 센다.

repo 쪽은 `main` 에 push 한다(4단계 기본 길로 갔다면 이미 했다). 그리고 **잡이 생기는 것과 배포가
도는 것이 다르다는 것을 알린다.** 잡은 15분 안에 생기지만, 배포는 그날 KST 자정 cron 이 돌 때
일어난다. 지금 띄우려면 Jenkins 화면에서 그 잡을 수동으로 빌드한다.

## 함정

| 증상 | 원인 | 어떻게 한다 |
|---|---|---|
| `docker: command not found` | 정상이다. 검증은 원래 Jenkins 가 한다 | 그대로 4단계 기본 길로 간다. 설치를 요구하지 않는다 |
| Build 는 초록불인데 Health check 에서 죽는다 | 그 서비스가 쓰는 키가 자격증명에 없다. 파이프라인은 파일이 비었는지만 본다 | 3단계로 돌아가 그 키를 `${VAR:?}` 로 적는다. 그러면 다음 빌드가 이름을 대며 멈춘다 |
| push 했는데 몇 시간째 배포가 안 된다 | 정상이다. 트리거는 자정 cron 하나뿐이다 | 기다리거나 수동 빌드를 누른다 |
| Scan 을 눌렀는데 잡이 안 생긴다 | `main` 에 `Jenkinsfile` 이 없다 | 파일 이름과 브랜치를 본다 |
| push 했는데 잡조차 안 보인다 | `main` 이 아니거나 `Jenkinsfile` 이 없다 | 조직 폴더는 `main` 의 `Jenkinsfile` 만 발견한다 |
| Health check 가 100초 뒤 실패하는데 컨테이너는 멀쩡하다 | healthcheck 미정의 | compose 나 Dockerfile 에 넣는다 |
| 컨테이너는 뜨는데 앱이 import 에 실패한다 | DooD 에서 상대경로 마운트가 빈 디렉터리로 덮였다 | override 에 `volumes: !reset []` |
| 배포는 초록불인데 기능 하나가 조용히 빠졌다 | `!reset []` 이 살려야 할 절대경로 마운트까지 지웠다 | `!override` 로 그것만 다시 적는다 |
| 나중에 뜨는 컨테이너가 포트 충돌로 죽는다 | 앞사람이 등록부에 안 넣었다 | `pick_port.py` 로 다시 세고 「뜨는데 등록이 없다」 줄을 넣는다 |
