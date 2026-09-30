# 적대적 리뷰 후속 설계·계획 리뷰 기록

대상 문서는 셋이다. spec `docs/superpowers/specs/2026-09-30-review-followups-design.md`, 계획 A `docs/superpowers/plans/2026-09-30-control-tower-followups.md`, 계획 B `docs/superpowers/plans/2026-09-30-plugin-fixes.md`. 렌즈 원본은 같은 이름의 폴더에 있다.

## 실행한 렌즈

렌즈를 한 번씩만 실행했다. 한 단계의 상한이 열 개라 계획 A·B 에는 넷(grounding·consistency·adversarial·fit)을, spec 에는 둘(grounding·consistency)을 실행했다. spec 의 lens-adversarial 과 lens-fit 은 잘랐다. spec 은 사용자가 대화에서 확정한 결정을 옮긴 기록이라 결정 자체를 공격할 대상이 아니고, 결정의 구현 방식은 두 계획의 adversarial 이 봤다.

선행연구 렌즈는 제안하지 않았다. spec 은 `docs/superpowers/specs` 아래라 spec 으로 판정했고, 이미 돌고 있는 맞춤과 스킬의 결함을 고치는 일이라 발동 기준(해본 적 없는 것을 해내려 함)에 들지 않는다.

## 합친 지적

「렌즈」 칸은 같은 지적을 잡은 렌즈다. 둘 이상이면 함께 잡은 것이다.

### spec

| 지적 | 렌즈 |
|---|---|
| 현행 유지 근거로 든 control-tower-design 313행은 커밋 버전을 받아들인 결정이 아니다. 받아들인 곳은 108·162·250–268행이다 | grounding |
| 2026-09-30 맞춤이 fsutil 을 돌렸다는 사례가 틀렸다. 이 PC 의 python3 은 링크가 아니라 fsutil 분기에 닿지 않는다 | grounding |
| 90초를 넘기면 알림이 사라진다는 동작이 가정 표시 없이 사실로 적혔다 | grounding |
| ranOnce 이행 기준이 spec 은 「그때의 목록」, 계획은 「지금 목록」이다 | spec-consistency, A-consistency, A-adversarial |
| 포트 등록 시점이 spec 은 「고른 직후」, 계획 B 는 「3단계 이름 확정 직후」다 | spec-consistency, B-consistency, B-grounding |
| 명백한 결함 18건의 결정이 spec 에 없다. 계획 B Task 7 은 spec 의 현행 유지 항목과 같은 워크플로를 고친다 | spec-consistency, A-consistency, B-consistency |
| 사본 이름 `.kw.bak` 이 적용되는 파일 범위가 계획과 다르다(계획은 settings.json 류만) | A-grounding |

### 계획 A

| 지적 | 렌즈 |
|---|---|
| 기존 설계 문서(2026-09-06)의 321·349·274·78·189–192·393·455–459·522·537·540행이 새 결정과 상충한 채 남는다. 동시에, 배포된 설계 문서를 덮어쓰는 것 자체가 설계 문서 수명 규칙과 부딪힌다 | spec-consistency, A-consistency, A-grounding, A-fit |
| 상한에 닿은 실행은 stuck 을 전혀 적지 않아 매번 상한을 넘기는 단계가 켤 때마다 되풀이되고, TimedOut 이 실행 전체 깃발이라 다른 단계의 기록까지 멈춘다 | A-adversarial |
| 상한에 끊긴 plugin update 가 기존 코드의 stuck-<배포처> 를 남겨 새 원격 커밋 전까지 재시도하지 않는다 | A-grounding |
| 상한은 claude 호출과 단계 시작에만 적용되어 pip·CLAUDE.md 잠금 대기가 90초를 넘길 수 있다 | A-adversarial, spec-consistency(notes) |
| claude.exe 의 표준입력을 열어 두고 닫지 않는다. 검사가 그 동작을 계약으로 고정한다 | A-adversarial, A-grounding(notes) |
| 잠금 해제가 exit 세 곳에만 붙어 예외 종료에서 잠금이 남는다 | A-adversarial |
| 잠금을 상태 파일 읽기 뒤에 잡아, 직전 맞춤이 적은 상태를 덮을 수 있다 | A-adversarial |
| Task 9 의 삽입 위치 「Fail 함수의 첫 줄 뒤」는 param 앞이다 | A-consistency, A-adversarial, A-grounding |
| ranOnce fallback 이 현재 목록을 돌려줘, 옛 PC 는 앞으로 추가하는 권장을 영영 깔지 않는다 | A-adversarial, A-consistency |
| 권장 설치 실패가 stuck-step2 로 기록되어 같은 날 필수 플러그인 교정까지 보류된다 | spec-consistency, A-adversarial |
| `-Steps` 빈 값이 「모든 단계」로 풀려 Add-Note 누락 하나가 전체 실행으로 이어진다 | A-adversarial |
| sync.ps1 이 `[CmdletBinding()]` 이라 구현 전 `-Steps` 는 바인딩 오류다. 부정 검사가 맞춤이 안 돌아도 통과한다 | A-grounding |
| Task 1 Step 6 의 stash 대조 지시가 옛 검사 파일 전체 실행을 허용한다 | A-adversarial, A-grounding |
| Task 3·8 의 기대 FAIL 목록이 실제와 다르다 | A-consistency, A-grounding, spec-consistency |
| Review Focus 의 두 줄(끊긴 뒤 잠금, 맞춤의 python3 줄 삭제)에 대응하는 검사가 없다 | A-fit, A-consistency, A-grounding |
| 뒤 작업이 앞 작업이 바꾼 뒤에도 origin/main 행 번호를 쓴다 | A-consistency, A-grounding |
| Task 5 Step 4 가 바꿀 곳 전부의 코드를 보이지 않는다 | A-fit |
| 검사를 test_control_tower 하나로만 돌리게 해 README 의 「넷 다」와 상충한다 | A-fit |
| $syncStub 변경 근거와 단계 6 검사 주석의 원인 설명이 코드와 다르다 | A-grounding |
| 가드 주석이 관측하지 않은 사건을 사실로 적는다 | A-grounding |
| Task 12 의 새 검사가 폴더 수만 세고 목록 포함 여부를 안 본다 | A-grounding |
| 문지기 판정에 CreationTime 을 쓰면 NTFS 터널링으로 오판할 수 있다(확인 못 함) | A-adversarial(notes) |
| 「작업 N」과 「Task N」 혼용, 「지문」 미설명, 금지 표현(막는·걸리는지·부르·더하·자리·돌고·돌리) | A-fit |

### 계획 B

| 지적 | 렌즈 |
|---|---|
| 3단계 등록은 compose 를 읽기 전이라 기존 compose 의 container_name 과 등록 이름이 달라질 수 있고, `kiwoom-<짧은 서비스 이름>` 규칙은 근거가 없다 | B-adversarial, B-grounding |
| 등록을 앞당기면 배포를 포기할 때 등록이 남고 지우는 경로가 없다 | B-adversarial |
| 3단계 등록을 고정하는 검사가 없다 | B-consistency |
| 금지어 워크플로가 PR 이 열린 동안 매일 force push 해 검토한 head 를 바꾸고 사람의 커밋을 지운다 | B-adversarial |
| xlsx 오류 확인이 표시값(`####`)에 기대고 셀마다 COM 을 불러 느리다. recalc.py 가 하는 「계산 결과를 파일에 남기기」의 대체가 없다 | B-adversarial, B-grounding |
| pptx 경로 검사가 abspath 문자열 비교라 `Z:\` 와 `\\cifs\` 같은 다른 표기를 못 잡는다 | B-adversarial |
| fetch_manifest 의 cp949 실행 검사는 경고 경로에 닿지 않아 수정 전에도 통과한다 | B-adversarial, B-consistency, B-grounding |
| docx 예제의 결과 경로에 절대경로 표시가 없다 | B-adversarial |
| docx 본문 17행의 설치 주체가 새 설명과 상충한 채 남는다 | B-consistency, B-grounding |
| .doc·.ppt 변환을 COM 이라 하면서 수동 저장만 있는 hwp 절로 보낸다 | B-consistency |
| 엑셀·파워포인트 실행 중 확인이 검사로 고정되지 않는다 | B-consistency |
| compose-and-env.md 의 env-ax 수정을 검사가 확인하지 못한다 | B-consistency |
| Global Constraints 의 날짜·실측 금지가 kw-doc-formats 에는 적용되지 않는다 | B-grounding |
| Review Focus 의 hwp 암호·손상 동작은 확인할 수 없고 검사는 문자열만 본다 | B-grounding |
| Interfaces 블록 누락, Task 2 의 「같은 명령」, test_dashboard 실행 누락, 표 머리 「이 PC 에서」, 「작업 N」·「Task N」 혼용, 금지 표현(막는·판·자리·더한·부르·찍), 수사를 대명사처럼 씀 | B-fit |
| 행 번호가 앞 삽입으로 밀린다(찾을 문자열은 함께 있음) | B-consistency |

## 상충과 공백

렌즈끼리 판정이 상충한 곳은 없다. 기존 설계 문서 수정은 fit 이 「설계 문서를 덮어쓴다」로, consistency·grounding 이 「덜 고친다」로 올려 방향이 반대인데, 둘은 같은 사실(옛 문서가 코드 계약으로 묶여 살아 있다)에서 나온 것이라 처분에서 함께 다룬다. 커버리지 공백은 spec 의 adversarial·fit 이다. 위 「실행한 렌즈」에 이유를 적었다.
