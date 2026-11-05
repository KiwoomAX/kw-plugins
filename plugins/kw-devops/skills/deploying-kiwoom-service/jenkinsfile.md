# 3단계 — 배포 설정 파일

SKILL.md 의 3단계에서 연다. 소속 조직에 따라 쓰는 파일이 다르다.

| 조직 | 쓰는 파일 | 잡을 만드는 조건 |
|---|---|---|
| KiwoomAX | `kiwoom-deploy.yml` (값만 적는다) | `main` 에 `kiwoom-deploy.yml` 이 있다 |
| KiwoomAM | `Jenkinsfile` (`kiwoomDeploy(...)` 호출) | `main` 에 `Jenkinsfile` 이 있다 |

## KiwoomAX — `kiwoom-deploy.yml`

KiwoomAX 저장소의 `Jenkinsfile` 은 실행되지 않는다. Jenkins 의 Kiwoom-AX 조직 폴더가 공통 파이프라인을 직접
실행하고, 저장소에서는 저장소 최상위의 `kiwoom-deploy.yml` 값만 읽는다. **`Jenkinsfile` 을 만들지 않는다.**

```yaml
# 배포 설정 — Jenkins 가 이 값으로 공통 파이프라인(jenkins-shared-lib kiwoomDeployFromConfig)을 실행한다.
# 받는 키: healthContainer(필수) · services · composeFiles · envCredIds · gatewayServices
healthContainer: kiwoom-<이름>
services: [backend, frontend]
composeFiles: [docker-compose.yml, docker-compose.jenkins.yml]
envCredIds: [env-<서비스>]
```

| 키 | 언제 적나 |
|---|---|
| `healthContainer` | **필수.** 대표 컨테이너 이름 하나 |
| `services` | 배포할 compose 서비스 목록. 적지 않으면 `[backend]` 다. 서비스 키가 `backend` 하나가 아니면 반드시 적는다. cron 이 실행하는 수집기처럼 상시 뜨지 않는 서비스는 넣지 않는다 |
| `composeFiles` | 적지 않으면 `[docker-compose.yml, docker-compose.jenkins.yml]` 이다. 덮어쓰기 파일이 없으면 `[docker-compose.yml]` 로 적는다. **저장소 최상위의 파일 이름만** 받는다 — `docker/compose.yml` 처럼 폴더 안 파일은 실패한다 |
| `envCredIds` | 서비스 전용 비밀이 있을 때 `[env-<서비스>]`. `env-ax` 는 파이프라인이 붙이므로 적지 않는다. `global-env` 는 받지 않는다 — 코드가 공통 키(Gemini 키 같은 것)를 쓰면 그 키를 `env-<서비스>` 에 넣어 달라고 AX 팀에 요청한다 |
| `gatewayServices` | 게이트웨이(로그인) 뒤로 옮길 서비스. 그 서비스의 호스트 포트는 열리지 않는다 |

**표에 없는 키는 빌드를 실패시킨다.** `service`·`conflictContainers`·`cronSchedule` 같은 `kiwoomDeploy` 파라미터도
받지 않는다. 서비스가 하나여도 `services: [web]` 처럼 목록으로 적는다.

### 파이프라인이 실패시키는 compose 구성

KiwoomAX 배포는 이미지를 빌드하기 전에 compose 구성을 검사하고, 아래 구성이 있으면 이유를 적고 멈춘다. 3단계에서
compose 를 쓸 때 처음부터 피한다.

- `privileged`·`cap_add`·`devices`·`network_mode: host`·`pid`·`ipc`·`logging` 같은 설정. 받는 설정은 이미지·빌드·포트·
  볼륨·네트워크·헬스·재시작 같은 보통 설정뿐이다
- 호스트 폴더 바인드 마운트. 받는 경로는 AX 팀이 저장소마다 등록한 경로뿐이다. 자료를 남겨야 하면 **named volume**
  (`volumes: { data: {} }` 로 선언하고 `data:/app/data` 로 붙이는 볼륨)을 쓴다. 호스트 폴더가 꼭 필요하면 AX 팀에
  경로 등록을 요청한다
- `external` 볼륨·네트워크, 볼륨 `driver_opts`, 네트워크 `ipam` 서브넷 지정
- `localhost:5000/` 으로 시작하는 `image:` (레지스트리 이름은 파이프라인이 `localhost:5000/ax/<저장소>/<서비스>` 로 붙인다)
- compose `name` 이 다른 저장소의 프로젝트 이름과 같은 구성, 이미 다른 컨테이너가 쓰는 `container_name`
- `.env`·`certs`·compose 파일을 심볼릭 링크로 커밋한 저장소, 원본 compose 의 `include`·`extends`

## KiwoomAM — `Jenkinsfile`

틀을 그대로 두고 이름·compose 파일·자격증명만 바꾼다.

```groovy
// <프로젝트> CI/CD — 공통 Shared Library(jenkins-shared-lib) 호출.
// 파이프라인 로직의 기준은 공용 라이브러리의 vars/kiwoomDeploy.groovy 다.
// 이 파일은 프로젝트별 값(컨테이너 이름·compose 파일)만 주입한다.

@Library('jenkins-shared-lib') _

kiwoomDeploy(
    healthContainer: 'kiwoom-<이름>',
    composeFiles:    ['docker-compose.yml', 'docker-compose.jenkins.yml'],   // 덮어쓰기 파일이 없으면 첫 파일만
    envCredIds:      ['global-env', 'env-am', 'env-<서비스>'],   // 서비스 전용 비밀 키가 없으면 마지막을 뺀다
)
```

넘길 일이 있는 파라미터는 아래 여섯이 거의 전부다. 넘기지 않은 파라미터는 기본값으로 실행되므로 필요한 것만 적는다.

| 파라미터 | 언제 넘기나 |
|---|---|
| `healthContainer` | **필수.** 대표 컨테이너 이름 하나. `conflictContainers` 의 기본값이 되고, healthcheck 가 하나도 없을 때 실패 메시지에 나온다 |
| `service` | compose 의 서비스 키가 `backend` 가 아니면 **반드시** 넘긴다. 기본값이 `backend` 라, 넘기지 않으면 Build 가 없는 서비스를 빌드하려다 멈춘다 |
| `services` | compose 에 배포할 서비스가 여럿일 때 그 목록. 적힌 것만 빌드하고 실행하므로, cron 이 실행하는 수집기처럼 상시 뜨지 않는 서비스는 뺀다. 헬스는 목록 중 healthcheck 가 있는 서비스를 모두 본다 |
| `conflictContainers` | 넘기지 않으면 `healthContainer` 하나다. 서비스가 여럿일 때 나머지 `container_name` 까지 함께 넘긴다. 배포 직전 이 이름의 컨테이너 중 이 compose 프로젝트 소유가 아닌 것만 지운다 |
| `extraCredentials` | 비밀 파일에는 쓰지 않는다. 서비스 계정 JSON 같은 파일 키는 base64 한 줄로 `.env` 에 넣는다(secrets.md) |
| `envCredIds` | 늘 넘긴다. `['global-env', 'env-am', 'env-<서비스>']` 이다. 앞에서 뒤 순서로 이어 붙고 같은 키는 뒤가 이긴다. `env-<서비스>` 는 환경변수 등록 요청을 받은 AX 팀이 만들고, 서비스 이름은 3단계에서 담당자와 정한 짧은 이름이다 |

`changedOnly` 는 넣지 않는다 — 선별 빌드는 push 트리거에서만 켜지는데 이 Jenkins 에는 그 트리거가 없다.

**전체 목록은 `jenkins-shared-lib` README 에 있지만 그 저장소는 담당자가 못 연다.** 위 여섯으로 안 되는 것을
만나면 뒤지지 말고 관리자에게 묻는다.
