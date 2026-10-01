# Jenkins 로그와 함정

SKILL.md 의 4단계에서 빌드가 `Finished: SUCCESS` 로 끝나지 않았을 때, 그리고 배포 뒤 사용자가
증상을 말할 때 연다.

## 콘솔 로그에 나오는 줄

**아래 문자열은 파이프라인(`kiwoomDeploy`)이 실제로 찍는 줄이다.** 단계 순서는 Gate → Prepare secrets →
Build → Record → Deploy → Health check → Rollback(실패했을 때만) → Retention(성공했을 때만)이다.

| 로그에 나오는 줄 | 뜻 | 어떻게 한다 |
|---|---|---|
| `Gate: main 외 브랜치(…) → 빌드/배포 안 함` | 브랜치를 잘못 올렸다 | `main` 에 올린다 |
| `Gate: 스케줄 + 직전 성공 빌드 이후 커밋 없음 → 건너뜀` | 자정 cron 인데 마지막 성공 배포 뒤 새 커밋이 없다 | 정상이다. 지금 배포하려면 수동 빌드 |
| `Gate: 실행 조건 불충족 → 이후 stage 건너뜀` · `Finished: NOT_BUILT` | 위 두 조건 중 하나로 실행하지 않았다 | 위 두 줄을 먼저 본다 |
| `kiwoomDeploy: healthContainer 파라미터는 필수입니다` | Jenkinsfile 에 그 값을 안 넣었다 | jenkinsfile.md 의 틀을 다시 본다 |
| `Build: <서비스> → localhost:5000/<저장소>/<서비스>:${IMAGE_TAG:-latest}` | 빌드하는 서비스에 레지스트리 이름을 붙였다 | 정상이다 |
| `Build: 배포 방식 = registry (태그 <커밋>)` · `push 완료: …` | 커밋 태그로 빌드해 서버 레지스트리에 올렸다 | 정상이다 |
| `Build: 서비스 구성을 읽지 못했다(compose config --format json 실패)` | compose 파일을 해석하지 못했다. 바로 위 줄에 compose 가 찍은 원인이 있다 | `${VAR:?…}` 로 적은 키가 자격증명에 없으면 그 변수 이름이 위 줄에 나온다. 문법 오류면 그 줄을 고친다 |
| `Build: git 원격 주소에서 저장소 이름을 읽지 못했다` | 잡의 git 원격이 비어 있다 | 담당자가 고칠 수 없다. 관리자에게 알린다 |
| `Build: 덮어쓴 이미지 이름을 읽지 못했다` · `Build: 이미지 이름이 섞여 있다` | 파이프라인이 붙인 이름을 compose 가 받아들이지 못했다 | 담당자가 고칠 수 없다. 로그를 붙여 관리자에게 알린다 |
| `Record: 되돌릴 태그 = <서비스>=<커밋>` | 실패하면 돌아갈 직전 버전을 적어 두었다 | 정상이다 |
| `Record: 되돌릴 곳이 하나도 없다` · `Record: <서비스> 는 되돌릴 곳 없음` | 이 서비스의 첫 배포이거나 같은 커밋을 다시 배포했다 | 이번 배포가 실패하면 되돌리지 못하고 실패한 새 버전이 그대로 남는다. 실패하면 서비스가 정상이 아니라고 알린다 |
| `Waiting for … (status: not_found)` 가 열 번 | 헬스를 보는 도중 컨테이너가 사라졌다. 재시작을 반복하는 상황이 많다 | 아래 컨테이너 로그 30줄이 이유를 말한다 |
| `Waiting for … (status: unhealthy)` 가 열 번 | 컨테이너는 떴는데 healthcheck 명령이 실패한다 | 아래 컨테이너 로그 30줄이 이유를 말한다. 포트·경로를 먼저 본다 |
| `Waiting for … (status: starting)` 가 열 번 | 100초 안에 앱이 못 떴다 | `start_period` 를 늘리거나 앱 기동을 본다 |
| `FAILED: <서비스> 의 컨테이너가 실행 중이 아니다` | 컨테이너가 뜨자마자 종료됐거나 서비스 이름이 compose 와 다르다 | 아래 로그를 보고, `services` 값과 compose 의 키를 맞춘다 |
| `FAILED: healthcheck 가 정의된 서비스가 없어 배포 상태를 검증하지 못했다` | 빌드하는 서비스 어디에도 healthcheck 가 없다 | compose 나 Dockerfile 에 healthcheck 를 넣는다 |
| `OK: <서비스> 는 healthcheck 미정의 → 헬스 검증 생략` | 통과했지만 **검증을 생략했다** | healthcheck 를 넣는다. 안 넣으면 고장을 못 잡고 되돌리지도 못한다 |
| `OK: … is healthy` · `Finished: SUCCESS` | 떴다 | 5단계로 간다 |
| `=== 실패 로그: <서비스> ===` · `Rollback: <서비스> 를 <커밋> 로 되돌린다` | 헬스가 실패해 직전 버전으로 되돌리는 중이다. 위 로그가 새 버전이 실패한 이유다 | 되돌린 결과 줄을 이어서 본다 |
| `Rollback: 되돌린 뒤 상태 정상` | **서비스는 직전 버전으로 돌고 있다.** 빌드는 `FAILURE` 로 끝나고 빌드 설명에 `<새 커밋> 실패 → … 로 되돌림` 이 남는다 | 서비스가 멈췄다고 알리지 않는다. 실패 로그로 원인을 고쳐 다시 push 한다 |
| `Rollback: 되돌린 뒤에도 상태가 정상이 아니다` · `Rollback: <서비스> 되돌리기 실패` | 새 버전도 직전 버전도 뜨지 않았다. 서비스가 멈춰 있을 수 있다 | 바로 관리자에게 알린다 |
| `Retention: … 지울 태그 없음` · `Retention: … 삭제` | 레지스트리의 오래된 태그를 정리했다 | 정상이다 |
| `Retention: … 삭제 실패` · `Retention: … 태그 목록을 읽지 못했다` | 정리만 실패했다. 배포는 끝났고 빌드는 `SUCCESS` 다 | 조치하지 않는다. 다음 배포 때 다시 정리한다 |

**Build 단계에서 위 `Build:` 줄이 아닌 곳에서 멈추면** 그 줄은 파이프라인이 아니라 docker 가 찍은 줄이라
(`port is already allocated`·`failed to solve`·`no such file or directory` 따위) 상황마다 다르다. 그때는 표를
뒤지지 말고 **그 줄을 붙여 넣게 한다.**

## 함정

| 증상 | 원인 | 어떻게 한다 |
|---|---|---|
| `docker: command not found` | 정상이다. 검증은 원래 Jenkins 가 한다 | 그대로 4단계 기본 길로 간다. 설치를 요구하지 않는다 |
| Build 는 통과했는데 Health check 에서 실패한다 | 그 서비스가 쓰는 키가 자격증명에 없다. 파이프라인은 파일이 비었는지만 본다 | 3단계로 돌아가 그 키를 `${VAR:?}` 로 적는다. 그러면 다음 빌드가 이름을 대며 멈춘다 |
| 빌드는 `FAILURE` 인데 서비스는 잘 돈다 | 새 버전이 헬스에 실패해 직전 버전으로 되돌아갔다 | 로그의 `Rollback:` 줄과 빌드 설명을 확인하고 `=== 실패 로그 ===` 로 원인을 고친다 |
| push 했는데 몇 시간째 배포가 안 된다 | 정상이다. 트리거는 자정 cron 하나뿐이다 | 기다리거나 수동 빌드를 누른다 |
| Scan 을 눌렀는데 잡이 안 생긴다 | `main` 에 `Jenkinsfile` 이 없다 | 파일 이름과 브랜치를 본다 |
| push 했는데 잡조차 안 보인다 | `main` 이 아니거나 `Jenkinsfile` 이 없다 | 조직 폴더는 `main` 의 `Jenkinsfile` 만 발견한다 |
| Health check 가 기다리지 않고 바로 실패한다 | 빌드하는 서비스 어디에도 healthcheck 가 없다 | compose 나 Dockerfile 에 넣는다 |
| 컨테이너는 뜨는데 앱이 import 에 실패한다 | DooD 에서 상대경로 마운트가 빈 디렉터리로 덮였다 | override 에 `volumes: !reset []` |
| 배포는 성공했는데 기능 하나가 조용히 빠졌다 | `!reset []` 이 살려야 할 절대경로 마운트까지 지웠다 | `!override` 로 그것만 다시 적는다 |
| 나중에 뜨는 컨테이너가 포트 충돌로 종료된다 | 앞사람이 등록부에 안 넣었다 | `pick_port.py` 로 다시 세고 「뜨는데 등록이 없다」 줄을 넣는다 |
| 첫 빌드가 `Prepare secrets` 단계에서 자격증명 `env-<서비스>` 를 찾지 못하고 멈춘다 | AX 팀이 이 저장소의 자격증명을 아직 만들지 않았다 | AX 팀의 등록 회신을 받은 뒤 Build Now 를 다시 누른다. 요청을 안 보냈으면 SKILL.md 의 「AX 팀에 등록 요청 보내기」로 보낸다 |
