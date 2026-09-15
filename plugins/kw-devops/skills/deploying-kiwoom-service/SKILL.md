---
name: deploying-kiwoom-service
description: Use when a KiwoomAX or KiwoomAM repo has to be deployed through the shared Jenkins CI/CD pipeline on server 192.7.9.45 and lacks a Dockerfile, docker-compose.yml or Jenkinsfile, when a new service needs a host port that will not collide, or when a deployed service's secrets or scheduled jobs must be registered with the AX team. Triggers on 배포 붙여줘·CI/CD 태워줘·젠킨스 붙이기·파이프라인 연결·Jenkinsfile 만들어줘·docker compose 만들어줘·포트 뭐 쓰지·새 서비스 배포.
---

# deploying-kiwoom-service

repo 하나를 공용 Jenkins 파이프라인에 태운다. **파이프라인 로직은 한 줄도 만들지 않는다** — `jenkins-shared-lib` 의
`kiwoomDeploy` 가 이미 갖고 있고, 공용 라이브러리 등록·자격증명·조직 폴더 잡도 서버에 구축돼 있다. `main` 에
`Jenkinsfile` 을 올리면 15분 안에 잡이 저절로 생긴다.

| 만든다 | 무엇 |
|---|---|
| `Dockerfile` | 저장소에 없을 때만 만든다 |
| `docker-compose.yml` | 서비스 정의. 호스트 포트를 여기서 배정한다 |
| `docker-compose.jenkins.yml` | Jenkins(DooD) 전용 덮어쓰기. 바인드 마운트가 없으면 안 만든다 |
| `Jenkinsfile` | `kiwoomDeploy(...)` 호출 몇 줄 |

## 절대 규칙

- **환경을 대신 확인해 주지 않는다.** 이 스킬은 담당자 PC 에서 돈다. 0단계를 건너뛰고 "아마 될 것" 으로 넘어가지 않는다.
- **남의 저장소를 읽지 않는다.** 담당자는 자기 저장소 권한만 갖는다. 사내 인증서도 다른 저장소에서 가져오지 않고
  0단계의 번들을 쓴다.
- **도커가 없는 것을 기본으로 둔다.** 검증은 Jenkins 가 하는 것이 정상 경로다. 도커 설치를 요구하지 않는다.
- **포트는 `pick_port.py` 로 정하고 같은 작업 안에서 `--register` 로 넣는다.** 미루면 다음 사람이 같은 포트를
  골라 나중에 뜨는 쪽이 조용히 죽는다.
- **`container_name` 을 적고 `healthContainer` 컨테이너에는 healthcheck 를 둔다.** 파이프라인이 이름으로 찾고,
  healthcheck 가 없으면 100초를 기다린 뒤 멀쩡한 배포를 실패로 떨어뜨린다.
- **`main` 에 올린다.** 조직 폴더가 `main` 만 발견한다.
- **파이프라인 로직을 Jenkinsfile 에 복제하지 않는다.** stage 가 필요하면 그것은 shared-lib 에 넣을 변경이다.
- **`.env` 와 `certs/` 를 커밋하지 않는다.** 파이프라인이 자격증명에서 빌드마다 복원한다.
- **비밀을 이미지에 넣지 않는다.** `.env`·`kiwoom.pem`·서비스 계정 JSON 을 `COPY` 하지 않는다. 키 종류별 통로는
  [secrets.md](secrets.md) 에 있다.
- **값이 든 파일(`.env`·`.env.local` 같은 것)을 열지 않는다.** 열면 비밀 값이 대화 기록에 남는다.
- **담당자의 답을 기다리는 곳은 셋뿐이다.** 1단계에서 같은 서비스가 여러 줄 나올 때, 3단계에서 compose 를 쓰기
  전, 6단계에서 스케줄을 찾았을 때다. 포트와 Dockerfile 은 묻지 않고 정한 뒤 알린다.

## 절차

### 0. 사전 점검

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/pick_port.py" --doctor
```

파이썬 버전·포트 등록부 도달·도커 유무를 찍는다. **막는 것이 있으면 거기서 멈추고 그 줄을 그대로 보여 준다.**
도커가 없는 것은 막는 것이 아니다.

**4단계의 빠른 길을 쓸 수 있는지도 여기서 정해 알린다.** 도커가 있고, `kw_install` 설치기가 사용자 환경변수
`SSL_CERT_FILE` 에 경로를 적어 둔 사내 인증서 번들이 있을 때만이다. 둘 중 하나라도 없으면 검증은 Jenkins 하나뿐이라고
알리고 뒤에서 말을 바꾸지 않는다.

```powershell
$bundle = [Environment]::GetEnvironmentVariable('SSL_CERT_FILE', 'User'); $bundle; if ($bundle) { Test-Path $bundle }
```

### 1. 조사

**포트를 고르기 전에 이 서비스가 등록부에 있는지 먼저 찾는다.** 등록부의 옛 줄은 `repo` 칸이 비어 있어 저장소
이름으로는 못 찾으므로, 저장소 이름과 compose 에 적힌 `container_name` 을 **모두** 넘긴다.

```powershell
Get-ChildItem -Recurse -File -Filter '*compose*.y*ml' | Where-Object FullName -notmatch '[\\/]node_modules[\\/]' |
    Select-String '^\s*container_name:\s*(\S+)' | ForEach-Object { $_.Matches[0].Groups[1].Value }
python "${CLAUDE_SKILL_DIR}/scripts/pick_port.py" --find <저장소 이름> [<container_name> …]
```

| 결과 | 어떻게 한다 |
|---|---|
| 없다 | 처음 올리는 서비스다. 2단계로 간다 |
| 한 줄 있다 | 그 포트를 쓰고 2단계를 건너뛴다. compose 의 `ports` 왼쪽 값이 다르면 3단계에서 고친다 |
| 여러 줄 있다 | 어느 것을 쓸지 담당자에게 묻는다 |

찾은 줄이 서버에서 **지금 뜨면** 이미 도는 서비스다. 3단계에서 compose-and-env.md 의 「이미 도는 서비스를 넘겨받을 때」를 따른다.

그다음 저장소에서 일곱을 확인해 담당자에게 보여 준다.

| 확인할 것 | 어디서 | 쓰는 곳 |
|---|---|---|
| Dockerfile 과 컨테이너 내부 포트 | `EXPOSE`·`CMD` | compose `ports` 오른쪽 값 |
| 헬스 엔드포인트 | 앱 라우터(`/`·`/health`) | `healthcheck.test` |
| 소속 조직 | GitHub remote | 등록부 `org` 칸, `envCredIds` 의 `env-<조직>` |
| 런타임에 읽는 호스트 파일 | 코드가 여는 절대경로 | Jenkins 덮어쓰기 |
| `COPY` 하는 경로가 `.gitignore` 에 있는가 | `.gitignore` 와 `COPY` 대조 | 있으면 Jenkins 빌드가 거기서 죽는다. 3단계에서 멀티스테이지로 바꾼다 |
| 바인드 마운트가 각각 무엇인가 | `volumes:` 한 줄씩 | 설정·코드·자료마다 처리가 다르다 |
| Dockerfile 이 비밀을 넣거나 TLS 검증을 끄는가 | `COPY` 의 `.env`·`*.pem`·키 JSON, `sslVerify false`·URL 에 박힌 토큰 | 3단계에서 secrets.md 대로 고친다 |

**Dockerfile 이 없으면** `package.json`·`pyproject.toml`·`requirements.txt`·`go.mod` 로 스택을 보고 **묻지 않고
만든다.** `EXPOSE` 와 `CMD` 를 반드시 적는다. 스택을 알아볼 수 없으면 멈추고 알린다. 빌드는 어차피 Jenkins 가
하므로 틀린 짐작은 4단계에서 드러난다.

### 2. 포트 확정 — 처음 올리는 서비스일 때만

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/pick_port.py"
```

등록부(잡아 둔 포트)와 서버 TCP 프로브(실제로 듣는 포트)를 합쳐 **차이부터 찍는다.** 차이가 나오면 담당자에게
알린다. 「뜨는데 등록이 없다」 줄도 등록부에 넣어야 다음 사람이 안 겹친다. 핸들러(`8700`)마저 닫혀 있으면 포트가
아니라 망 문제이므로 다 비어 보여도 빈 포트로 믿지 않고 거기서 끝낸다.

**`9000`–`9199` 에서 가장 작은 빈 포트를 묻지 않고 쓰고, 어느 포트인지 알린다.** 대역 규약은 `pick_port.py` 의
`대역` 상수가 정본이다.

### 3. 파일 작성

**compose 를 쓰기 전에 한 번 멈추고 담당자에게 셋을 확인받는다.**

- 코드가 읽는 키 목록과 그중 어느 것이 비밀인지
- 값이 든 파일이 무엇인지 — 파일 이름만 보고 열지 않는다
- 서비스 자격증명 `env-<서비스>` 에 쓸 짧은 서비스 이름

답을 받으면 차례로 한다.

1. 비밀 키가 있으면 「AX 팀에 등록 요청 보내기」로 환경변수 등록 요청을 보낸다.
2. [compose-and-env.md](compose-and-env.md) 와 [secrets.md](secrets.md) 를 끝까지 읽고 `docker-compose.yml` 과,
   필요하면 덮어쓰기 파일과 Dockerfile 수정을 쓴다.
3. [jenkinsfile.md](jenkinsfile.md) 의 틀로 `Jenkinsfile` 을 쓴다.
4. `.gitignore` 에 `.env` 와 `/certs/` 를 넣는다. `/` 를 빼면 `docker/certs/` 같은 다른 폴더까지 가려진다.

### 4. 검증 — 돌려 보지 않고 됐다고 하지 않는다

**0단계에서 빠른 길을 쓸 수 있다고 정했으면** 먼저 [local-verify.md](local-verify.md) 대로 이 PC 에서 빌드와 헬스
검사를 한다. 그다음 기본 길로 간다.

**기본 길은 Jenkins 다.** 이 길에서는 push 가 검증보다 먼저 온다.

1. `main` 에 push 한다.
2. `http://192.7.9.45:9090` 에 GitHub 계정으로 로그인해 조직 폴더(`Kiwoom-AX`, KiwoomAM 이면 `Kiwoom-AM`)에서
   **Scan Organization Folder Now** 를 누른다.
3. 생긴 잡의 `main` 브랜치에서 **Build Now** 를 누른다.
4. **Console Output 을 끝까지 읽는다.** `Finished: SUCCESS` 가 아니면 [jenkins-logs.md](jenkins-logs.md) 에서 그 줄을
   찾아 고치고 다시 push 한다. 담당자가 로그를 못 읽으면 통째로 붙여 넣게 한다.

처음 올리는 서비스는 실패해도 남의 서비스를 내리지 않는다. 이미 도는 서비스는 「이미 도는 서비스를 넘겨받을 때」를
마친 뒤에 누른다.

### 5. 등록부에 넣고 알리기

```powershell
python "${CLAUDE_SKILL_DIR}/scripts/pick_port.py" --register <포트> <컨테이너> <service_type> [org [repo]]
```

| 칸 | 값 |
|---|---|
| `service_type` | `infra`(여러 서비스가 함께 부르는 핸들러·데이터베이스) · `backend` · `frontend` · `dashboard` |
| `org` | `KiwoomAM` · `KiwoomAX`. 이미지를 그대로 띄운 인프라는 뺀다 |
| `repo` | 저장소 이름만 |

1단계에서 이미 찾은 서비스도 쓸 포트로 한 번 돌린다 — 비어 있는 `repo` 칸이 채워진다. 「남이 먼저 잡았다」고
하면 2단계로 돌아간다. **넣지 못해 담당자에게 넘길 때는 `${CLAUDE_SKILL_DIR}` 를 푼 전체 경로로 명령을 적는다.**

**잡이 생기는 것과 배포가 도는 것이 다르다고 알린다.** 잡은 15분 안에 생기지만 배포는 그날 KST 자정 cron 이나
수동 빌드 때 돈다.

### 6. 스케줄 — 배포를 마친 뒤에

**5단계를 마칠 때까지 스케줄을 꺼내지 않는다.** 앞에서 흔적을 보았어도 3단계 질문에 끼워 묻지 않는다.

| 흔적 | 요청 종류 |
|---|---|
| compose 에서 Jenkinsfile 이 띄우지 않는 서비스 — `services` 에 없거나 `service`(기본값 `backend`)가 아닌 것 | 컨테이너 실행형 |
| `vercel.json` 의 `crons`, 스케줄러가 부르는 `/api/cron/…` 같은 라우트 | 주소 호출형 |

**찾은 것이 없으면 「스케줄로 도는 것이 없다」고만 알리고 끝낸다.** 있으면 서버에서 돌릴지, 실행 주기와 예상
실행 시간을 담당자에게 묻는다. Vercel 같은 다른 곳에서도 돌고 있으면 어느 쪽에 둘지 함께 묻는다. 돌리겠다고 한
것마다 스케줄 등록 요청을 보낸다.

## AX 팀에 등록 요청 보내기

**담당자는 Jenkins 자격증명과 서버를 볼 수 없으므로 두 등록을 AX 팀에 메일로 요청한다.** 확인 없이 바로 보낸다.
**보내기 전에 [ax-requests.md](ax-requests.md) 를 읽는다** — 준비할 것, 제목과 본문, 종료 코드별 대응이 거기 있다.

| 요청 | 언제 보내나 |
|---|---|
| 환경변수 등록 요청 | 3단계 확인 직후. 비밀 키가 없으면 보내지 않는다. 6단계에서 스케줄에만 쓰는 키가 생기면 한 통 더 |
| 스케줄 등록 요청 | 6단계에서 돌리겠다고 한 스케줄마다 한 통 |

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_SKILL_DIR}/scripts/request-ax.ps1" -Subject "<제목>" -BodyPath "<본문.json>" -EnvSource "<값이 든 파일>" -EnvKeys "<키1>,<키2>"
```

키 이름만 넘기면 스크립트가 값이 든 파일에서 그 키만 뽑아 첨부하고 화면에는 키 이름만 찍는다. 스케줄 등록 요청은
`-EnvSource`·`-EnvKeys` 를 빼고 부른다. 메일이 실패해도 배포 절차는 멈추지 않는다.

## 증상으로 찾을 때

배포 뒤에 사용자가 증상을 말하면 [jenkins-logs.md](jenkins-logs.md) 의 「함정」 표에서 찾는다.
