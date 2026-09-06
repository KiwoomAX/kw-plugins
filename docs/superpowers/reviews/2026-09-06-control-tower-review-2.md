# spec 검진 기록 둘째 회차 — 컨트롤 타워 (2026-09-06)

검토 대상은 `docs/superpowers/specs/2026-09-06-control-tower-design.md`의 둘째 판이다. 렌즈를 한 번씩만 돌렸다. 한 서브에이전트가 grounding과 consistency를 차례로 적용했고 adversarial은 따로 띄웠다. 렌즈 원본은 이 파일과 같은 이름의 폴더에 있다. 선행연구 렌즈는 첫 회차에서 제안했고 사용자가 돌리지 않기로 정했으므로 이번에도 안 돌렸다.

이번 회차는 첫 회차 발견이 실제로 고쳐졌는지도 함께 보게 했다.

## 첫 회차의 처분

첫 회차가 올린 서른다섯 가운데 **열여덟이 고쳐졌고 아홉이 부분이며 넷이 새 문제를 낳았다.** 나머지는 두 렌즈의 판정이 겹친 것이다.

새 문제를 낳은 넷이 이번 회차의 중심이다.

| 첫 회차 발견 | 이번 판이 한 것 | 새로 생긴 것 |
|---|---|---|
| 해시가 라이브러리·문안 변경을 못 잡는다 | 해시를 버리고 플러그인 판본을 잰다 | 판본은 `plugin.json`의 선언을 따르고, 없으면 마켓플레이스 커밋이 되어 한 레포의 플러그인이 값을 함께 쓴다. 좁던 신호가 이제 넘치거나 다시 침묵한다 |
| 부분 실패에도 상태를 적는다 | 걸음이 다 성공했을 때만 적는다 | 영구히 실패하는 PC에서 같은 알림이 끝없이 뜨고 문구가 원인을 틀리게 말한다 |
| `_ensure_autoupdate.sh`가 우산 자리에서 못 돈다 | 사본에서 뺐다 | 함께 뗀 `_resolve_home.sh`가 우산에도 필요하다. 도메인 PC의 홈 리다이렉트를 다루는 것이 그 파일이다 |
| `register-corp-certs`가 두 벌이 된다 | 은퇴 목록에 넣었다 | 함께 들고 온 삭제 가드의 「설치기가 쓴 것 말고 없을 때만」이 설치기가 물러난 뒤 주인을 잃는다 |

## 이번 회차의 뿌리

**재는 자리와 고치는 자리가 어긋난다.** 두 렌즈가 서로 다른 각도에서 같은 문장에 닿았다.

첫 판은 해시 하나로 재고 고쳤다. 둘째 판은 `installed_plugins.json`으로 재고 `settings.json`의 `enabledPlugins`로 고친다. 그래서 재는 쪽에만 있는 사실과 고치는 쪽에만 있는 사실이 각각 **영원한 알림**과 **영원한 침묵**을 만든다.

- 은퇴한 플러그인은 `enabledPlugins`에서 걷히지만 `installed_plugins.json`에는 남는다. 맞춤이 성공해도 훅이 계속 알린다. **이 PC가 지금 그 상태다.**
- 사용자가 `/plugin` 화면에서 끈 것은 `enabledPlugins`에 `false`로 남고 `installed_plugins.json`에는 정상 항목으로 있다. 훅이 못 본다. 가장 흔한 끄는 방법 앞에서 「조용히 못 끄게」가 조용하다.
- 자동 갱신 경보는 남의 마켓플레이스까지 울리는데 맞춤은 남의 것을 못 고친다. 끌 수 없는 소음이 된다.

## 합친 목록

adversarial이 열다섯, grounding·consistency가 열여덟을 올렸다. 겹친 것을 합쳐 스물여덟이다.

| 무엇 | 렌즈 | 함께 잡음 |
|---|---|---|
| 훅이 재는 파일과 맞춤이 고치는 파일이 다르다 | adversarial·consistency | ○ |
| `enabledPlugins: false`를 훅이 못 본다 | adversarial | |
| 판본이 `plugin.json` 선언을 따라 갈린다 | adversarial·grounding | ○ |
| `gitCommitSha`가 없는 항목이 있다 | grounding | |
| 자동 갱신 경보가 고칠 수 없는 상태에 걸린다 | consistency | |
| 영구 실패 PC에서 알림이 끝없이 뜨고 문구가 원인을 틀리게 말한다 | adversarial | |
| 우산의 걸음에 환경을 부르는 걸음이 없다 | adversarial·consistency | ○ |
| `_resolve_home.sh`가 우산에도 필요하다 | adversarial | |
| bash 절대 경로 규율이 훅 다섯에 안 걸렸다 | adversarial·consistency | ○ |
| "설치기가 파이썬과 pwsh를 절대 경로로 찾는다"가 틀렸다 | grounding | |
| 훅 매처가 Bash와 PowerShell 둘인데 하나만 옮기면 실제 경로가 빠진다 | adversarial | |
| `python3` 가드가 도커와 WSL 안의 `python3`까지 막는다 | adversarial | |
| 걸음 2가 사용자가 지운 선택형 플러그인을 매번 되돌린다 | adversarial | |
| 삭제 가드의 "설치기가 쓴 것" 기준이 주인을 잃는다 | adversarial | |
| 가드에 걸려 안 지운 것이 성공인지 실패인지 안 정해졌다 | adversarial | |
| 정규화가 개발 PC 한 번인데 드리프트는 각 PC에 있다 | adversarial | |
| 첫째 걸음 창에서 옛 설치기가 우산 항목을 걷는다 | adversarial | |
| 되돌리기가 배포된 PC를 되돌리지 않는다 | adversarial | |
| `--plugin-dir` 시험이 훅 판정을 시험하지 못한다 | adversarial | |
| `CLAUDE.md` 걸음을 끄는 스위치가 무엇인지 없다 | adversarial | |
| 사본의 값이 조건부인데 장치는 무조건이다 | adversarial | |
| `_ensure_autoupdate.sh`를 안 받는 근거 둘째가 틀렸다 | grounding | |
| `disciplined-coder`가 `claude-plugins-official`을 만진다는 근거가 없다 | grounding | |
| 훅이 읽는 두 파일에 `settings.json`이 없어 스스로 잰 어긋남을 못 본다 | grounding | |
| 선언이 첫째 걸음에 이미 발행처 이전을 담아 같은 창이 다시 열린다 | grounding | |
| 「세 층」 블록이 0단계를 빼고 1~7단계를 통째로 설치기에 남긴다 | consistency | |
| 우산의 산출물 표가 없어 `sync.sh`와 `manifest.json`의 자리가 안 정해졌다 | consistency | |
| 환경의 은퇴 스킬 선언이 어느 파일에 사는지 안 정해졌다 | consistency | |
| 이행 넷째 걸음에 되돌리기가 없다 | consistency | |
| 설치기에 남는 키가 표에서 셋, 본문에서 넷이다 | consistency | |
| 이행 첫째 걸음의 "훅 셋"이 문서가 세운 넷과 안 맞는다 | consistency | |
| 테스트가 마커 정규화와 선언 못 읽음 갈래를 안 덮는다 | consistency | |
| `retiredMarketplaces`에 `superpowers-marketplace`가 빠졌다 | grounding | |

## 거른 것

없다. 근거를 열어 확인한 것은 전부 실물과 맞았다. 첫 회차에서 하나 걸렀던 자리(마커 접두 매칭의 이유가 주석에 있다)는 이번 회차가 "실제로 있다"고 확인해 주었다.

## 상충

두 렌즈가 반대 판정을 낸 자리는 없다. 겹친 넷은 같은 방향에서 다른 각도로 왔다.

## 커버리지 공백

`kw-plugins`에 실물 스크립트가 아직 없어 훅과 맞춤의 판정 순서와 종료 코드 처리를 문서 서술로만 봤다. 플러그인이 나르는 `.sh` 훅을 윈도의 클로드 코드가 어느 인터프리터로 부르는지 재지 못했다. `claude plugin install`이 `enabledPlugins`가 `false`인 것을 다시 켜는지도 못 쟀다. `HKLM` 정책 키는 첫 회차와 같이 안 열었다.

## 이 회차가 남기는 것

두 회차가 모두 **감지 장치**에서 무너졌다. 첫 판은 재는 범위가 좁았고 둘째 판은 재는 것과 고치는 것이 어긋났다. 같은 자리를 두 번 틀렸다면 다음 판은 감지를 먼저 설계하고 나머지를 거기 맞춰야 한다.

adversarial이 과설계로 올린 것도 같은 방향을 가리킨다. 사내 플러그인 둘에 층 셋과 훅 넷과 맞춤 명령 둘을 두었고, 사본 셋의 값은 다른 레포가 아직 받지 않은 제안에 걸려 있다.

<!-- spec-review: escalated -->
