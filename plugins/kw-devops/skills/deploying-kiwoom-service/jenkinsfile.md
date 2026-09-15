# 3단계 — Jenkinsfile

SKILL.md 의 3단계에서 연다. 틀을 그대로 두고 이름·compose 파일·자격증명만 바꾼다.

```groovy
// <프로젝트> CI/CD — 공통 Shared Library(jenkins-shared-lib) 호출.
// 파이프라인 로직의 SSOT 는 공용 라이브러리의 vars/kiwoomDeploy.groovy 다.
// 이 파일은 프로젝트별 값(컨테이너 이름·compose 파일)만 주입한다.

@Library('jenkins-shared-lib') _

kiwoomDeploy(
    healthContainer: 'kiwoom-<이름>',
    composeFiles:    ['docker-compose.yml', 'docker-compose.jenkins.yml'],   // 덮어쓰기 파일이 없으면 첫 파일만
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
| `extraCredentials` | 비밀 파일에는 쓰지 않는다. 서비스 계정 JSON 같은 파일 키는 base64 한 줄로 `.env` 에 넣는다(secrets.md) |
| `envCredIds` | 늘 넘긴다. `['global-env', 'env-<조직>', 'env-<서비스>']` 이고 조직은 KiwoomAX 면 `env-ax`, KiwoomAM 이면 `env-am` 이다. 앞에서 뒤 순서로 이어 붙고 같은 키는 뒤가 이긴다. `env-<서비스>` 는 환경변수 등록 요청을 받은 AX 팀이 만들고, 서비스 이름은 3단계에서 담당자와 정한 짧은 이름이다 |

`changedOnly` 는 넣지 않는다 — 선별 빌드는 push 트리거에서만 켜지는데 이 Jenkins 에는 그 트리거가 없다.

**전체 목록은 `jenkins-shared-lib` README 에 있지만 그 저장소는 담당자가 못 연다.** 위 여섯으로 안 되는 것을
만나면 뒤지지 말고 관리자에게 묻는다.
