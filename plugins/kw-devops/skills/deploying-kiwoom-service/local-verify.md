# 4단계 빠른 길 — 이 PC 에서 먼저 빌드해 보기

SKILL.md 의 4단계에서 연다. 0단계에서 도커와 사내 인증서 번들이 둘 다 있다고 정했을 때만 쓴다. 이 길은 Jenkins
검증을 대신하지 않고 push 전에 한 번 걸러 볼 뿐이다.

**쓰지 않는 조건이 둘 있다.**

- `build.secrets` 로 `certs/kiwoom.pem`(`ghpem`)을 쓰는 이미지 — 개인키는 이 PC 에 없다.
- 이 PC 에 같은 이름의 컨테이너가 이미 있을 때(`docker ps -a --filter name=<container_name>`) — `build`·`up`·`down` 이
  그 컨테이너와 이미지를 덮어쓰거나 내린다. `config` 는 아무것도 만들지 않으므로 그래도 돌린다.

**저장소를 `$env:TEMP` 아래로 복사해 거기서 돌린다.** `.env` 와 `certs/` 는 Jenkins 가 빌드마다 복원하는 것이라
저장소에 없고, 저장소 안에서 `.env` 를 만들면 담당자의 진짜 값 파일을 덮을 수 있다.

1. 저장소를 `$env:TEMP\kwdevops-verify-<저장소 이름>` 으로 복사한다. `.git`·`.env*`·`node_modules` 는 뺀다.
2. 0단계의 번들을 복사본의 `certs/ePrism.crt` 로 복사한다. Jenkins 가 자격증명 `eprism-crt` 에서 복원하는 파일과
   같은 이름이다.
3. 복사본에 `.env` 를 새로 만들고 compose 가 `${VAR:?}` 로 요구하는 키만 가짜 값으로 채운다. 진짜 값은 쓰지 않는다.
4. 복사본에서 돌린다. 빌드는 끝날 때까지 기다린다.

   ```powershell
   docker compose -f docker-compose.yml -f docker-compose.jenkins.yml config | Out-Null   # 문법·병합
   docker compose up -d --build <서비스>
   docker inspect --format='{{.State.Health.Status}}' kiwoom-<이름>                        # healthy 여야 한다
   ```

5. 확인이 끝나면 `docker compose down` 으로 내리고 복사본 폴더를 지운다.

`healthy` 가 안 나오면 파이프라인에서도 안 나온다. 값이 가짜라서 외부 API 나 데이터베이스가 붙는지는 여기서 알 수
없다 — 그것은 Jenkins 에서 본다.
