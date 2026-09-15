# Jenkins 로그와 함정

SKILL.md 의 4단계에서 빌드가 `Finished: SUCCESS` 로 끝나지 않았을 때, 그리고 배포 뒤 사용자가
증상을 말할 때 연다.

## 콘솔 로그에 나오는 줄

**아래 문자열은 파이프라인(`kiwoomDeploy`)이 실제로 찍는 줄이다.**

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
| 첫 빌드가 `Prepare secrets` 단계에서 자격증명 `env-<서비스>` 를 찾지 못하고 멈춘다 | AX 팀이 이 저장소의 자격증명을 아직 만들지 않았다 | AX 팀의 등록 회신을 받은 뒤 Build Now 를 다시 누른다. 요청을 안 보냈으면 SKILL.md 의 「AX 팀에 등록 요청 보내기」로 보낸다 |
