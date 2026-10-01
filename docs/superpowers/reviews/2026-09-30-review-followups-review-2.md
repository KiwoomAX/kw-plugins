# 적대적 리뷰 후속 계획 2차 리뷰 기록

대상은 계획 A `docs/superpowers/plans/2026-09-30-control-tower-followups.md` 와 계획 B `docs/superpowers/plans/2026-09-30-plugin-fixes.md` 다. 1차 리뷰(`2026-09-30-review-followups-review.md`)의 반영으로 동작이 바뀌어 사용자가 다시 리뷰를 정했다. 렌즈 원본은 같은 이름의 폴더에 있다.

## 실행한 렌즈

렌즈를 한 번씩만 실행했다. 사용자가 고른 범위대로 두 계획에 lens-adversarial 과 lens-consistency 만 실행했다(넷). lens-grounding·lens-fit 과 spec 은 이번 차수에 보지 않았다. 선행연구 렌즈는 계획이라 제안하지 않았다.

## 합친 지적

### 계획 A

| 지적 | 렌즈 |
|---|---|
| 권장 설치 호출이 상한에 끊기면 stuck-step2 가 적혀, 막으려던 필수 교정 보류가 끊김 경로로 생긴다 | adversarial |
| 남은 시간이 0 이라 시작하지 않은 호출도 「끊긴 단계」로 적힌다 | adversarial |
| 단계 1 이 끊긴 날 다음 세션에 단계 2 만 실행되면 stuck-<배포처> 가 적혀 새 커밋까지 재시도하지 않는다 | adversarial |
| 감지의 권장 대기 판정(Task 10 Step 5)은 spec 에 없고, 늘 실패하는 권장을 세션마다 반복시킨다. 설계 감지 표와 README 의 질문 수에도 없다 | adversarial, consistency |
| pip 실행 시간에 제한이 없어 여유 20초를 넘길 수 있다 | adversarial |
| 쓰기 도중 끊긴 claude 가 설정 파일을 절반만 쓸 수 있다(가정) | adversarial |
| 사본이 최신이어도 뒤처짐마다 단계 1 을 넘겨, 느리게 성공하는 단계 1 이 단계 2 를 영영 미룬다 | adversarial |
| 옛 설계 212행(필수·권장 구분)과 446행(dc 의 PYTHONUTF8 규칙), 389행(매처가 없다)이 남는다 | adversarial, consistency |
| sync.ps1 의 주석 두 곳(단계를 건너뛰지 않는다, 상태 파일은 두 가지)과 session-check 의 주석 한 곳(모두 대조한다)이 코드와 어긋난 채 남는다 | consistency |
| Task 7·10·11 의 기대 FAIL 목록이 실제와 다르다 | consistency |
| Task 4·10 의 설계 교체문이 「(2026-09-30 변경)」 표기를 쓰지 않는다 | consistency |
| 두 파일의 Get-SuggestedDone 동일성 검사가 없다 | consistency |

### 계획 B

| 지적 | 렌즈 |
|---|---|
| Task 6 의 포기 안내 검사 정규식이 문안의 줄바꿈을 넘지 못해 구현 뒤에도 실패한다 | adversarial, consistency |
| Task 6 Step 2 가 `--check` 실패로 함께 떨어지는 test_devops 두 검사를 빠뜨린다 | consistency |
| 금지어 워크플로의 비교가 CRLF 와 LF 차이로 늘 거짓이다 | adversarial |
| 같은 내용 검사가 열린 PR 확인보다 앞이라 PR 이 닫히고 브랜치만 남으면 PR 없이 끝난다 | adversarial, consistency |
| xlsx 예제의 `SaveAs` 가 조건 없이 실행되어 원본 덮어쓰기 검사가 없고, 주석(선택)과 코드(무조건)가 다르며, 형식 인자가 없다 | adversarial, consistency |
| `SpecialCells` 의 catch 가 모든 예외를 「오류 없음」으로 바꾼다(보호 시트, 가정) | adversarial |
| xlsx 새 문단의 「수식 파일마다 COM」이 앞 절의 「COM 은 마지막 수단」과 상충한다 | consistency |
| hwp 설명은 오피스 자동 변환을 약속하는데 본문은 수동 저장만 안내한다 | consistency |
| docx 문단이 「변경 추적」을 공식 방식과 워드 COM 두 곳에 지정한다 | consistency |

## 상충과 공백

렌즈끼리 상충한 판정은 없다. 이번 차수는 grounding·fit 과 spec 을 보지 않았다.
