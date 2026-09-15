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

## 서버에서 이미 되어 있는 것

**공용 라이브러리 등록·자격증명·조직 폴더 잡이 모두 구축돼 있다. 셋업부터 하자고 접근하지 않는다.**
`main` 에 `Jenkinsfile` 을 올리면 15분 안에 잡이 저절로 생긴다.

## 절대 규칙

- **환경을 대신 확인해 주지 않는다.** 이 스킬은 담당자 PC 에서 돌고, 그 PC 의 사정은 거기서만
  알 수 있다. 0단계를 건너뛰고 "아마 될 것" 으로 넘어가지 않는다.
- **도커가 없는 것을 기본으로 놓고 쓴다.** 대시보드 담당자 PC 에 도커는 없고, 도커가 무엇인지도
  모른다. **검증은 Jenkins 가 하는 것이 정상 경로다.** 이 PC 에 도커가 있으면 더 빨리 확인할 수
  있을 뿐이고, 없다고 설치를 요구하거나 검증을 건너뛰지 않는다. 「도커가 있을 것」을 전제로 한
  문장을 스킬 어디에도 두지 않는다.
- **포트는 `pick_port.py` 로 정하고, 정했으면 `--register` 로 넣는다.** 등록부와 실측을 함께 봐야
  한다.
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
- **비밀을 이미지에 넣지 않는다.** `.env`·`kiwoom.pem`·서비스 계정 JSON 을 `COPY` 하지 않는다. 개인키는
  빌드 때 BuildKit secret `ghpem` 으로만 보이고, `.env` 값은 실행 때 `env_file` 로 들어간다. 파이프라인은
  실행이 끝나면 워크스페이스의 `.env` 와 `certs/kiwoom.pem` 을 지운다. 키 종류별 통로는
  [compose-and-env.md](compose-and-env.md) 의 「비밀을 넘기는 통로」에 있다.
- **포트를 정했으면 같은 작업 안에서 등록부에 넣는다.** 미루면 다음 사람이 같은 포트를 고르고,
  나중에 뜨는 쪽이 조용히 죽는다.

## 절차

### 0. 사전 점검 — 이 PC 가 돌릴 수 있는지부터 본다

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/pick_port.py" --doctor
```

**환경은 사람마다 다르고, 남이 대신 확인해 줄 수 없다.** 담당자 PC 에 사내망이 닿는지, 도커가
있는지는 그 PC 에서만 알 수 있다. 다른 PC 에서 재 본 값을 가져다 쓰지 않는다.

셋을 찍는다 — 파이썬 버전, 포트 등록부 도달, 도커 유무. 막는 것이 있으면 무엇을 해야 하는지
화살표로 함께 적고 종료 코드 1 로 끝난다. **막는 것이 있으면 거기서 멈추고 사용자에게 그 줄을
그대로 보여 준다.** 도커가 없는 것은 막는 것이 아니다 — 검증은 원래 Jenkins 가 한다.

**4단계의 빠른 길을 쓸 수 있는지도 여기서 정해 알린다.** 도커가 있고 사내 인증서 번들이 있을 때만
쓸 수 있다. 번들은 `kw_install` 설치기가 만들어 사용자 환경변수 `SSL_CERT_FILE` 에 경로를 적어 둔 파일이다.

```powershell
$bundle = [Environment]::GetEnvironmentVariable('SSL_CERT_FILE', 'User'); $bundle; if ($bundle) { Test-Path $bundle }
```

둘 중 하나라도 없으면 검증은 Jenkins 에서 하는 기본 길 하나뿐이라고 알리고, 뒤에서 말을 바꾸지 않는다.

**남의 저장소를 읽지 않는다.** 담당자는 자기 레포 권한만 갖는다. **ssh 계정도 필요 없다.**
등록부는 `kw_deploy.port` 테이블이고 `kiwoom-rdb-handler`(8700)를
거쳐 읽으므로 사내망에 닿기만 하면 된다.

### 1. 조사 — 이미 등록된 서비스인지부터 찾는다

**포트를 새로 고르기 전에 이 서비스가 등록부에 있는지 먼저 본다.** 저장소 이름과, compose 파일이
이미 있으면 거기 적힌 `container_name` 을 **모두** 넘긴다.

```powershell
Get-ChildItem -Recurse -File -Filter '*compose*.y*ml' | Where-Object FullName -notmatch '[\\/]node_modules[\\/]' |
    Select-String '^\s*container_name:\s*(\S+)' | ForEach-Object { $_.Matches[0].Groups[1].Value }
python "${CLAUDE_SKILL_DIR}/scripts/pick_port.py" --find <저장소 이름> [<container_name> …]
```

**저장소 이름 하나로는 못 찾는 서비스가 있다.** 등록부의 옛 줄은 `repo` 칸이 비어 있어 저장소 이름으로
찾으면 「등록부에 없다」고 답한다. 그 답을 믿으면 이미 도는 서비스에 새 포트를 쥐여 준다.

찾은 줄마다 서버에서 **지금 뜨는지**도 함께 찍는다. 뜨는 줄이 있으면 이 서비스는 이미 서버에서
돌고 있으므로 3단계의 「이미 도는 서비스를 넘겨받을 때」를 따른다.

| 결과 | 어떻게 한다 |
|---|---|
| 없다 | 처음 올리는 서비스다. 조사를 마치고 **2단계로 간다** |
| 한 줄 있다 | 그 포트를 그대로 쓴다. **2단계를 건너뛰고 3단계로 간다** |
| 여러 줄 있다 | 어느 것을 쓸지 사용자에게 묻는다 |

찾은 포트가 저장소 compose 의 `ports` 왼쪽 값과 다르면 3단계에서 찾은 포트로 고친다.

**이것을 빠뜨리면 이미 포트를 가진 서비스에 새 포트를 쥐여 준다.** 서비스가 조용히 다른 포트로
옮겨 가고 옛 줄은 등록부에 남아 썩는다. `container` 에 유일 제약이 없어(한 컨테이너가 포트 여럿을
갖는 것이 실제로 있다) 데이터베이스가 막아 주지 않는다.

그다음 repo 에서 일곱을 확인하고, 확인한 값을 사용자에게 보여 준 뒤 다음으로 간다.

| 확인할 것 | 어디서 | 왜 필요한가 |
|---|---|---|
| Dockerfile 위치와 컨테이너 내부 포트 | `Dockerfile` 의 `EXPOSE`·`CMD` | compose 의 `ports` 오른쪽 값 |
| 헬스 엔드포인트 | 앱 라우터(`/` 나 `/health`) | `healthcheck.test` |
| 소속 조직 | GitHub remote 의 조직 이름 | 등록부의 `org` 칸에 적는다 |
| 런타임에 읽는 호스트 파일 | 코드가 여는 절대경로 | Jenkins 덮어쓰기를 어떻게 쓸지 |
| **Dockerfile 이 `COPY` 하는 경로가 `.gitignore` 에 있는가** | `.gitignore` 와 `COPY` 줄을 대조 | 있으면 그 산출물이 저장소에 없다는 뜻이다. **Jenkins 는 clone 만 하므로 Build 가 거기서 죽는다** — 3단계에서 멀티스테이지로 바꾼다 |
| **compose 의 바인드 마운트가 각각 무엇인가** | `volumes:` 를 한 줄씩 | 설정·코드·자료 셋으로 갈리고 처리가 다르다(3단계) |
| **Dockerfile 이 비밀을 이미지에 넣거나 TLS 검증을 끄는가** | `COPY` 줄의 `.env`·`*.pem`·키 JSON, `sslVerify false`·검증을 끈 연결·URL 에 박힌 토큰 | 있으면 3단계에서 「비밀을 넘기는 통로」대로 고친다 |

**Dockerfile 이 없으면 스택을 알아볼 수 있는지 본다.** 담당자는 개발자가 아니라서 「Dockerfile 을
만들어 오세요」로 끝내면 갈 곳이 없다. 그리고 **이미지를 빌드하는 것은 어차피 Jenkins 다** — 여기서
쓴 Dockerfile 은 4단계에서 실제로 빌드되고 헬스 검사까지 받으므로 짐작이 조용히 통과하지 못한다.

| 상태 | 어떻게 한다 |
|---|---|
| `Dockerfile` 이 있다 | 그대로 쓴다. 고치는 것은 3단계의 멀티스테이지 조건에 걸릴 때뿐이다 |
| 없지만 스택을 알아볼 수 있다 | `package.json`·`pyproject.toml`·`requirements.txt`·`go.mod` 를 보고 **묻지 않고 만든다.** 만들었다고 알리기만 한다 |
| 없고 스택도 모르겠다 | 거기서 멈추고 사용자에게 알린다 |

만들 때는 `EXPOSE` 와 `CMD` 를 반드시 적는다. 4단계가 그 포트로 헬스를 본다.

### 2. 포트 확정 — 처음 올리는 서비스일 때만

**1단계의 `--find` 가 이미 있다고 답했으면 이 단계를 건너뛴다.** 있는 포트를 그대로 쓴다.

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/pick_port.py"
```

**두 곳을 보고 합친다.** 등록부(`kw_deploy.port`)는 「잡아 둔 것」이고 TCP 프로브는 「실제로 듣고
있는 것」이다. 어느 하나만 보면 구멍이 난다 — 등록만 되고 아직 안 뜬 포트를 프로브는 빈 포트로
보고, 뜨는데 등록 안 된 포트를 등록부는 모른다. 그래서 **차이를 먼저 찍는다.**

```
[차이] 등록됐지만 안 뜬다: 9001 kiwoom-<이름>
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

**고른 포트는 묻지 않고 쓴다.** 어느 포트를 썼는지 알리기만 하고 다음으로 간다. 사용자에게 묻는 것은
1단계에서 같은 서비스가 여러 줄 나왔을 때뿐이다.

### 3. 세 파일 작성

**compose 를 쓰기 전에 한 번 멈춘다.** 코드가 읽는 키 목록과 값이 든 파일을 담당자에게 보여 확인받고, 답을
받은 뒤에 compose 를 쓰고 4·5단계로 간다. 서비스 자격증명 `env-<서비스>` 에 쓸 짧은 서비스 이름도 제안해
함께 확인받는다. 1~5단계에서 담당자의 답을 기다리는 곳은 여기와 1단계의
「여러 줄 있다」뿐이다.

**`docker-compose.yml` 과 Dockerfile 을 쓰기 전에 [compose-and-env.md](compose-and-env.md) 를 끝까지 읽는다.**
틀과 규칙이 모두 그 파일에 있다. 다른 단계가 「3단계의 …」로 부르는 절도 거기 있다. 담긴 절은 이렇다.

| 절 | 무엇을 정하나 |
|---|---|
| `docker-compose.yml` | 서비스 정의 틀과 프론트엔드(nginx)일 때 바꿀 것 |
| 환경변수가 어디서 오는지 먼저 정한다 | 비밀과 기본값을 둘 곳, 키가 없으면 `${VAR:?}` 로 멈추게 하는 법 |
| 비밀을 넘기는 통로 | 개인키·`.env` 값·파일 키·사내 CA 를 빌드와 실행에 넘기는 법, `.dockerignore` 의 마지막 방어선 |
| 빌드 산출물이 저장소에 없으면 멀티스테이지로 바꾼다 | 사내 CA 를 이미지에 넣는 법과 `.dockerignore` |
| `docker-compose.jenkins.yml` | 바인드 마운트를 한 줄씩 처리하는 법과 런타임 자료 경로 |
| 이미 도는 서비스를 넘겨받을 때 | 지금 쓰는 마운트 경로를 받는 법과 첫 배포가 컨테이너를 내린다는 안내 |
| compose 가 저장소 루트에 없어도 된다 · 프로젝트 이름은 `name:` 으로 박아 둔다 | compose 파일 위치와 프로젝트 이름 |

**비밀 키 목록을 담당자에게 확인받으면 「AX 팀에 등록 요청 보내기」를 따른다.** 그때 값이 든 파일이
무엇인지(`.env`·`.env.local` 같은 것)도 함께 확인받는다. 파일 이름만 보고 열지 않는다. 이 서비스만 쓰는
비밀 키가 없으면 아래 Jenkinsfile 틀의 `envCredIds` 에서 `env-<서비스>` 를 뺀다.

**`Jenkinsfile`**

```groovy
// <프로젝트> CI/CD — 공통 Shared Library(jenkins-shared-lib) 호출.
// 파이프라인 로직의 SSOT 는 공용 라이브러리의 vars/kiwoomDeploy.groovy 다.
// 이 파일은 프로젝트별 값(컨테이너 이름·compose 파일)만 주입한다.

@Library('jenkins-shared-lib') _

kiwoomDeploy(
    healthContainer: 'kiwoom-<이름>',
    composeFiles:    ['docker-compose.yml', 'docker-compose.jenkins.yml'],
    envCredIds:      ['global-env', 'env-ax', 'env-<서비스>'],   // KiwoomAM 이면 env-am. 서비스 전용 비밀 키가 없으면 마지막을 뺀다
)
```

넘길 일이 있는 파라미터는 이 여섯이 거의 전부다. 안 넘기면 기본값이 걸리므로 필요한 것만 적는다.

| 파라미터 | 언제 넘기나 |
|---|---|
| `healthContainer` | **필수.** 헬스를 볼 컨테이너 이름 하나 |
| `service` | compose 의 서비스 키가 `backend` 가 아니면 **반드시** 넘긴다. 기본값이 `backend` 라, 안 넘기면 Build 가 없는 서비스를 빌드하려다 멈춘다 |
| `services` | compose 에 배포할 서비스가 여럿일 때 그 목록. 적힌 것만 빌드하고 띄우므로, cron 이 부르는 수집기처럼 상시 뜨지 않는 서비스는 뺀다. 헬스는 여전히 `healthContainer` 한 곳만 본다 |
| `conflictContainers` | 안 넘기면 `healthContainer` 하나다. 서비스가 여럿일 때 나머지 `container_name` 까지 함께 넘긴다. 배포 직전 이 이름의 컨테이너를 어느 프로젝트 것이든 지운다 |
| `extraCredentials` | 비밀 파일에는 쓰지 않는다. 서비스 계정 JSON 같은 파일 키는 base64 한 줄로 `.env` 에 넣는다([compose-and-env.md](compose-and-env.md) 의 「비밀을 넘기는 통로」) |
| `envCredIds` | 늘 넘긴다. `['global-env', 'env-<조직>', 'env-<서비스>']` 이고 조직은 KiwoomAX 면 `env-ax`, KiwoomAM 이면 `env-am` 이다. 앞에서 뒤 순서로 이어 붙고 같은 키는 뒤가 이긴다. `env-<서비스>` 는 환경변수 등록 요청을 받은 AX 팀이 만들고, 서비스 이름은 3단계에서 담당자와 정한 짧은 이름이다 |

`changedOnly` 는 넣지 않는다 — 선별 빌드는 push 트리거에서만 켜지는데 이 Jenkins 에는 그 트리거가 없다.

**전체 목록은 `jenkins-shared-lib` README 에 있지만 그 저장소는 담당자가 못 연다.** KiwoomAX 전용
계정으로는 안 열리므로, 위 여섯으로 안 되는 것을 만나면 뒤지지 말고 관리자에게 묻는다.

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
4. **Console Output 을 끝까지 읽는다.** `Finished: SUCCESS` 가 아니면 [jenkins-logs.md](jenkins-logs.md) 의 로그 표에서 그 줄을 찾아 고친 뒤 다시 push 하고 2번부터
   되풀이한다.

**처음 올리는 서비스라면 첫 배포는 무너뜨릴 것이 없다.** Deploy 가 내리는 것은 그 compose 프로젝트와
`conflictContainers` 에 적힌 이름뿐인데 새 서비스에는 아직 아무것도 없다. 그러니 이 길에서 실패해도
남의 서비스는 멀쩡하다 — 겁내지 말고 눌러 본다. **이미 도는 서비스는 다르다** — 3단계의 「이미 도는
서비스를 넘겨받을 때」를 마친 뒤에 누른다.

**로그를 못 읽겠으면 Console Output 을 통째로 붙여 넣게 한다.** Claude 가 읽어 준다 — 이것이
자동화 대신 두는 길이고, 토큰도 권한도 필요 없다. 그 표는 자주 나오는 줄을 먼저 걸러 주는 것뿐이다.

#### 빠른 길 — 0단계에서 쓸 수 있다고 정했을 때만

**저장소를 `$env:TEMP` 아래로 복사해 거기서 돌린다.** `.env` 와 `certs/` 는 Jenkins 가 빌드마다 복원하는
것이라 저장소에 없고, 저장소 안에서 `.env` 를 만들면 담당자의 진짜 값 파일을 덮을 수 있다.

1. 저장소를 `$env:TEMP\kwdevops-verify-<저장소 이름>` 으로 복사한다. `.git`·`.env*`·`node_modules` 는 뺀다.
2. 0단계의 번들을 복사본의 `certs/ePrism.crt` 로 복사한다. Jenkins 가 자격증명 `eprism-crt` 에서 복원하는
   파일과 같은 이름이다.
3. 복사본에 `.env` 를 새로 만들고 compose 가 `${VAR:?}` 로 요구하는 키만 가짜 값으로 채운다. 진짜 값은 쓰지 않는다.
4. 복사본에서 돌린다.

   ```powershell
   docker compose -f docker-compose.yml -f docker-compose.jenkins.yml config | Out-Null   # 문법·병합
   docker compose up -d --build <서비스>
   docker inspect --format='{{.State.Health.Status}}' kiwoom-<이름>                        # healthy 여야 한다
   ```

5. 확인이 끝나면 `docker compose down` 으로 내리고 복사본 폴더를 지운다.

`healthy` 가 안 나오면 파이프라인에서도 안 나온다. 값이 가짜라서 외부 API 나 데이터베이스가 붙는지는
여기서 알 수 없다 — 그것은 기본 길에서 본다. `certs/kiwoom.pem`(`secrets`)을 쓰는 이미지는 그 파일이 이
PC 에 없으므로 이 길을 쓰지 않는다.

**이 PC 에 같은 이름의 컨테이너가 이미 있으면 `build`·`up`·`down` 은 돌리지 않는다**
(`docker ps -a --filter name=<container_name>`). 그 컨테이너와 이미지를 덮어쓰거나 내린다. `config` 는
아무것도 만들지 않으므로 그래도 돌린다.

### 5. 등록부에 넣고 push, 그리고 언제 뜨는지 알리기

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/pick_port.py" --register <포트> <컨테이너> <service_type> [org [repo]]
```

**넣지 못해 담당자에게 넘길 때는 스크립트의 전체 경로로 명령을 적는다.** `${CLAUDE_SKILL_DIR}` 를 푼
절대경로다. 담당자는 `pick_port.py` 가 어디 있는지 모른다.

**역할과 조직을 두 칸에 나눠 적는다.** AX 프론트엔드라면 `frontend` + `KiwoomAX` 다.

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
일어난다. 지금 띄우려면 Jenkins 화면에서 그 잡을 수동으로 빌드한다. 그다음 6단계로 간다.

### 6. 스케줄이 필요한지 본다 — 배포를 마친 뒤에

**1~5단계는 대시보드를 배포하는 것만 한다.** 스케줄은 배포가 끝난 뒤에 묻는다. 앞 단계에서 스케줄
흔적을 보았어도 5단계를 마칠 때까지 꺼내지 않고, 3단계 질문에 끼워 묻지도 않는다. 그 전에 스케줄 때문에
배포 방식을 바꾸자고 하지 않는다.

저장소에서 정해진 시각에 도는 것을 찾는다.

| 흔적 | 무엇이 도는가 | 요청 종류 |
|---|---|---|
| compose 에 Jenkinsfile 이 띄우지 않는 서비스 | 그 컨테이너를 한 번 돌리고 끝낸다 | 컨테이너 실행형 |
| `vercel.json` 의 `crons`, 스케줄러가 부르는 `/api/cron/…` 같은 라우트 | 스케줄러가 앱의 주소를 부르면 앱이 그 요청 안에서 일한다 | 주소 호출형 |

Jenkinsfile 이 띄우지 않는 서비스는 `services` 를 넘겼으면 거기 없는 서비스이고, 넘기지 않았으면
`service`(기본값 `backend`)가 아닌 서비스다.

**찾은 것이 없으면 「스케줄로 도는 것이 없다」고만 알리고 끝낸다.** 있으면 담당자에게 보여 주고 서버에서
돌릴지 묻는다. 지금 Vercel 같은 다른 곳에서 돌고 있으면 두 곳에서 같은 일이 돌지 않게 어느 쪽에 둘지도
함께 묻는다. 돌리겠다고 한 것마다 스케줄 등록 요청을 한 통씩 보낸다. 실행 주기와 예상 실행 시간은
코드로 알 수 없으므로 담당자에게 묻는다. `vercel.json` 의 `schedule` 은 UTC 이므로 한국 시간으로 옮겨 적는다.

**컨테이너 실행형이 자료를 쓰면 보내기 전에 덮어쓰기 파일부터 고친다.** [compose-and-env.md](compose-and-env.md) 의
`docker-compose.jenkins.yml` 절을 따라 자료 마운트를 적고 push 한다.

**스케줄에만 쓰는 비밀 키가 있으면 환경변수 등록 요청을 한 통 더 보낸다.** 3단계에서 보낸 키는 빼고 새 키만
담는다. 주소 호출형이 헤더에 싣는 `CRON_SECRET` 같은 키가 그렇다.

## AX 팀에 등록 요청 보내기

**담당자는 Jenkins 자격증명과 서버를 볼 수 없으므로 두 등록은 AX 팀에 메일로 요청한다.** 스크립트가
확인 없이 바로 보낸다. 제목과 본문 블록과 고정 문장은 [ax-requests.md](ax-requests.md) 가 정한다.

| 요청 | 언제 보내나 |
|---|---|
| 환경변수 등록 요청 | 3단계에서 비밀 키 목록을 담당자에게 확인받은 직후에 보낸다. 비밀 키가 없으면 보내지 않는다 |
| 스케줄 등록 요청 | 6단계에서 담당자가 서버에서 돌리겠다고 한 스케줄마다 한 통씩 보낸다 |

**값이 든 파일을 열지 않는다.** 3단계에서 확인받은 파일(`.env`·`.env.local` 같은 것)이다. 열면 비밀 값이
대화 기록에 남는다. 키 이름만 넘기면 스크립트가 그 파일에서 그 키만 뽑아 첨부를 만들고, 화면에는 키
이름만 찍는다.

**파일 키는 보내기 전에 base64 한 줄로 바꿔 값이 든 파일에 붙인다.** 담당자에게 키 파일(서비스 계정 JSON
같은 것)의 경로만 받고 그 파일은 열지 않는다. 아래 명령은 값을 화면에 찍지 않는다. 붙인 `<이름>_B64` 를
`-EnvKeys` 에 함께 넘긴다.

```powershell
Add-Content -LiteralPath "<값이 든 파일>" -Value ("`n<이름>_B64=" + [Convert]::ToBase64String([IO.File]::ReadAllBytes("<키 파일>")))
```

본문 JSON 을 저장소 밖(`$env:TEMP` 가 가리키는 폴더의 절대경로 같은 곳)에 Write 로 만든 뒤 부른다. `-EnvKeys` 는 쉼표로 이은 문자열
하나로 넘긴다. 공백으로 나누면 둘째 키가 다른 인자로 샌다. 스케줄 등록 요청은 `-EnvSource` 와
`-EnvKeys` 를 빼고 부른다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_SKILL_DIR}/scripts/request-ax.ps1" -Subject "<제목>" -BodyPath "<본문.json>" -EnvSource "<값이 든 파일>" -EnvKeys "<키1>,<키2>"
```

종료 코드로 다음을 정한다.

| 종료 코드 | 어떻게 한다 |
|---|---|
| 0 | "SMTP 가 받아들였다"고만 알린다. `[첨부 제외]` 줄에 찍힌 키는 값이 가지 않았으니 담당자가 AX 팀에 직접 전달해야 한다고 알린다 |
| 8, 또는 2 이고 사유가 `-EnvSource 파일이 없다` | 값이 든 파일이 없거나 요청한 키가 하나도 없다. 본문의 `p` 블록을 「첨부 없음 문장」으로 바꾸고 `-EnvSource`·`-EnvKeys` 없이 다시 부른다 |
| 2 이고 사유가 `-Subject`·`-BodyPath`·`-EnvKeys`·`함께 줘야 한다` 이거나 본문 JSON 을 읽지 못한 것 | 부르는 쪽의 실수이고 메일은 나가지 않았다. 사유대로 인자나 본문 JSON 을 고쳐 한 번만 다시 부른다 |
| 4 이고 사유가 `렌더러가 종료 코드` | 본문 블록이 렌더러 형식과 다르고 메일은 나가지 않았다. [ax-requests.md](ax-requests.md) 의 블록 이름과 칸에 맞춰 고친 뒤 한 번만 다시 부른다 |
| 그 밖, 또는 다시 부른 뒤에도 실패 | 코드와 스크립트가 찍은 사유를 눈에 띄게 알린다. 만든 본문을 담당자에게 보여 직접 전달하게 하고, 비밀 값은 AX 팀과 전달 방법을 정하라고 알린다. 값이 든 파일을 대화에 붙여 넣으라고 하지 않는다. 배포 절차는 멈추지 않고 이어 간다 |

**환경변수 등록 요청이 첨부와 함께 0 으로 끝났는지 기억해 둔다.** 스케줄 등록 요청의 `note` 에서
그렇다면 「값은 첨부에 있음」을, 아니면 「값은 따로 전달」을 쓴다.

## 증상으로 찾을 때

배포 뒤에 사용자가 증상을 말하면 [jenkins-logs.md](jenkins-logs.md) 의 「함정」 표에서 찾는다.
