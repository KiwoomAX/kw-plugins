# spec 검진 기록 — 컨트롤 타워 (2026-09-06)

검토 대상은 `docs/superpowers/specs/2026-09-06-control-tower-design.md`다. 렌즈를 한 번씩만 돌렸다. 한 서브에이전트가 grounding과 consistency를 차례로 적용했고 adversarial은 자세가 반대라 따로 띄웠다. 렌즈 원본은 이 파일과 같은 이름의 폴더에 있다.

선행연구 렌즈는 제안했고 사용자가 돌리지 않기로 정했다. spec과 plan은 경로로 갈랐다(`specs/` 아래이므로 spec이다). 제안한 이유는 이 설계의 대부분이 이미 하던 일을 옮기는 것이라 발동 기준에 안 걸리지만, 관리 설정 없이 플러그인만으로 사내 표준을 강제하는 부분은 되는지가 미지수여서 판단이 갈렸기 때문이다. 판단이 갈리면 제안하는 것이 규칙이다.

## 두 렌즈가 함께 잡은 것

같은 자리를 둘이 짚은 것이 셋이다.

`_ensure_autoupdate.sh`를 그대로 쓸 수 없다는 것을 둘 다 잡았다. adversarial은 우산의 자리에 `marketplace.json`이 없어 아무것도 안 하고 0으로 끝난다는 실패 이야기로, grounding은 공개 함수가 늘 0을 돌려주고 종료 코드 10이 "항목이 아예 없다"까지 덮는다는 계약 오독으로 왔다. 사본의 계약을 함수 이름만 보고 적고 실제 호출 경계를 안 열어 본 것이 한 뿌리다.

이행 첫째 걸음에서 설치기와 우산이 `CLAUDE.md`를 함께 쓴다는 것도 둘 다 잡았다. 매칭 규칙이 다르고 직렬화 수단도 다르다.

사본 넷 가운데 실제로 값을 내는 것이 하나뿐이라는 것은 adversarial이 과설계로, grounding이 계약 오류 셋으로 각각 왔다.

## 가장 무거운 뿌리

**감지의 범위가 옮기려는 것의 범위보다 좁다.** 옮기는 것은 목록 셋(플러그인·라이브러리·문안)인데 훅이 재는 것은 선언 파일 하나의 해시다. 선언은 라이브러리와 문안을 가리키기만 하므로 그것들이 바뀌어도 해시가 안 바뀐다. 이 설계가 풀려던 바로 그 상황이 조용히 지나간다.

여기에 둘째가 겹친다. `/kw-sync`의 걸음 하나가 실패해도 마지막 걸음이 해시를 적어, 부분 성공이 완전 성공과 같은 흔적을 남긴다. 그 뒤로 훅은 영원히 조용하다.

## 합친 목록

adversarial이 열다섯, grounding·consistency가 스물하나를 올렸다. 근거를 열어 확인한 뒤 하나를 걸렀다.

| 무엇 | 렌즈 | 함께 잡음 |
|---|---|---|
| 훅의 해시가 라이브러리·문안 변경을 못 잡는다 | adversarial | |
| 부분 실패에도 해시를 적는다 | adversarial | |
| `_ensure_autoupdate.sh`가 우산의 자리에서 아무것도 못 한다 | adversarial·grounding | ○ |
| 공개 함수가 늘 0을 돌려주어 판정 입력이 없다 | grounding | |
| 종료 코드 10이 "항목 없음"까지 덮는다 | grounding | |
| `known_marketplaces.json`과 `settings.json`에는 잠금이 없다 | adversarial | |
| 이행 첫째 걸음에서 두 기록자가 `CLAUDE.md`를 함께 쓴다 | adversarial·consistency | ○ |
| `register-corp-certs`가 개인 스킬 폴더에 남아 두 벌이 된다 | adversarial | |
| 걸음 5가 설치기의 삭제 가드 셋과 백업을 버렸다 | adversarial·consistency | ○ |
| 이행 둘째 걸음이 셋째보다 앞서 스킬이 사라질 수 있다 | adversarial | |
| 9단계가 어느 bash를 부를지 안 정했다 | adversarial | |
| `Merge-ClaudeSettings`의 청소가 `$script:Plugins`를 진실로 삼는다 | adversarial | |
| 잠금 규약이 갈리면 배제가 깨지는데 아무도 안 잰다 | adversarial | |
| 마켓플레이스 클론과 플러그인 캐시가 다른 시점에 갱신된다 | adversarial | |
| `schema`는 보호 대상이 그 코드를 안 가져 발동할 수 없다 | adversarial | |
| 되돌리기 절이 없다 | adversarial | |
| 사본 넷 가운데 하나만 값을 낸다 | adversarial·grounding | ○ |
| 라이브러리가 여덟이 아니라 일곱이다 | grounding | |
| `Set-MarketplaceAutoUpdate`가 레지스트리를 쓴다는 서술이 틀렸다 | grounding | |
| 사본 표가 이미 끝난 리팩터를 기다린다고 적었다 | grounding | |
| "고아 BEGIN을 중화한다"가 지금 동작이 아니다 | grounding | |
| 은퇴 목록에서 `frontend-design@claude-code-plugins`가 빠졌다 | grounding | |
| 감사의 "가장 무거운 뿌리"는 재지 않은 순위다 | grounding | |
| `sync.ps1`과 `sync.sh`가 네 자리에서 갈린다 | consistency | |
| 경계 표가 우산의 `settings.json` 소유를 좁게 적었다 | consistency | |
| 되켜기 근거가 인용한 앞선 결정과 반대다 | consistency | |
| 걸음 1에 되켜기 대상 한정이 없다 | consistency | |
| `python3` 가드가 세 절에서 빠졌다 | consistency | |
| `vendor.sh`의 자리가 어느 표에도 없다 | consistency | |
| 도커 훅의 옛 항목을 걷는 자리가 없다 | consistency | |
| `retiredPlugins`가 마켓플레이스 등록을 못 걷는다 | consistency | |
| 테스트가 정한 계약의 절반만 덮는다 | consistency | |
| 0단계가 새 번호에 없다 | consistency | |

## 거른 것

grounding이 「이행」의 "괄호 안 문구를 바꿔도 살아남게 하려던 것이라고 주석에 적혀 있다"를 근거 없는 인용이라고 올렸다. **틀린 지적이다.** `setup.ps1:1616-1618`에 `matching a prefix also survives somebody rewording the parenthetical`이 실제로 있다. 같은 렌즈가 그 정규식 자체는 맞다고 확인했으므로 주장의 나머지는 살아 있다.

## 상충

두 렌즈가 서로 반대되는 판정을 낸 자리는 없었다. 겹친 셋은 같은 방향에서 다른 각도로 왔다.

## 커버리지 공백

adversarial은 우산의 실물 스크립트가 아직 없어 걸음의 종료 코드 처리와 해시 계산 범위를 문서 서술로만 판정했다. grounding은 `HKLM` 정책 키와 조직 계정 서버 쪽을 확인하지 않아 "관리 설정이 없다"는 사용자 답변에 기댔다. 둘 다 `disciplined-coder`가 `_ensure_autoupdate.sh`를 실제로 어떤 인자로 부르는지는 안 열었다.

## 검토 중에 대상이 움직인 것

`_managed_block.sh`가 이 검진이 도는 동안 바뀌었다. 렌즈가 처음 읽었을 때는 이름표가 상수였고 다시 읽었을 때 `MANAGED_TAG`가 들어와 있었다. `disciplined-coder` 세션이 같은 시각에 그 리팩터를 커밋했다. 선행 결정으로 렌즈에게 넘긴 "아직 안 됐다"가 검토 시점에 이미 낡았다.

## 이 회차가 남기는 것

렌즈가 아니었으면 훅이 아무것도 감지하지 못하는 채로 구현에 들어갔을 것이다. 감지 장치를 설계하면서 무엇을 감지해야 하는지를 다시 세지 않았다.

발견을 사용자에게 올린 뒤 사용자가 구조를 바꾸기로 했다. 우산은 목록만 갖고 환경을 별도 플러그인으로 가른다. 그 판단의 근거가 이 회차의 첫째 발견이다.

<!-- spec-review: escalated -->
