# 코드 흐름 안내 화면 설계 리뷰 (2026-10-19)

대상은 `docs/superpowers/specs/2026-10-14-code-flow-guide-design.md` 의 2026-10-19 변경분이다. 변경분은 「동작마다 화면」 절, JSON 형식 표의 `screen.frames` · `step` 줄, 「화면과 문장 규칙」의 끝 대상 줄, 절차 표의 「장면 · 화면 대조」 줄이다. 렌즈 원본은 같은 이름의 폴더에 있다.

렌즈를 한 번씩만 실행했다.

선행연구 에이전트는 제안하지 않았다. 이번 변경은 이미 하는 캡처를 동작 단위로 나누는 일이고, 되는지 자체가 미지수인 일이 아니다. 대상은 `docs/superpowers/specs` 아래 파일이므로 spec 으로 판정했다.

## 지적 목록

| 지적 | 잡은 렌즈 |
|---|---|
| `frames` 는 준비 동작과 기다리기를 빼고 세는데 `step` 은 준비 동작만 빼고 센다. 「마지막 동작」이 기다리기일 수 있다 | grounding · consistency · adversarial · fit(범위 밖 확인 요청) |
| 고르기 이름의 「고른 항목 글자」는 계획에 없고(value 만 있음), 선택자 대상 누르기와 나머지 동작 종류의 이름 규칙이 없다. `name` 자동 생성은 요구되지 않았고 흐름 동작 `text` 와 중복된다 | grounding · consistency · adversarial |
| 「화면 칸 이름」이 기존 「화면 칸」(오른쪽 캡처 영역) · 「화면 표기」와 뜻이 다르다 | consistency |
| 입력 연출(`typed`)과 `frames` 가 같은 입력 동작을 가리킬 때 순서가 정해지지 않았다 | consistency |
| 끝 대상 규칙이 `analysis-prompt.md` 99행의 「결과 제목」 · 「그 단추 · 칸」 문장을 바꾸라고 적지 않았고, 범위 전체는 선택자로만 가리킬 수 있는데 적는 방법이 없다. 여럿 맞거나 못 찾으면 조용히 넘어간다 | consistency · adversarial |
| `render.py` 의 `frames` · `step` 검사, SKILL.md 합치기 표의 `frames` 줄, `frames` 의 `rect` 기준이 spec 에서 도출되지 않는다 | consistency · adversarial |
| 중간 동작에서 캡처가 멈출 때 이미 찍은 `frames` 의 처리가 없다 | consistency |
| 대조 단계에서 동작을 고치면 `step` 을 누가 다시 세는지 없다 | consistency · adversarial |
| 누르기가 창을 열면 동작 뒤 사진에서 가려진 단추 위치로 확대된다. `rect` 측정 시점이 없다 | adversarial |
| 대조 단계에 판정 기준이 없고, 주 세션은 사각형이 그려지지 않은 사진을 보며, 사진 약 81장을 맥락에 싣는다 | adversarial |
| 다시 캡처의 반복 상한 · 멈춤 조건이 없고, `capture.py` 에 장면을 고르는 입력이 없다 | adversarial |
| RM 장면 수는 31이 아니라 30이고, 12장면의 세는 기준이 없다 | grounding |
| `screens/` 는 약 4MB 가 아니라 약 5.0MB 다 | grounding |
| 용어: 「확대 사각형」 ↔ 「화면 사각형」, 「사진」 ↔ 「캡처 이미지」 | fit |
| 주체 누락: 「캡처」 · 「두 페이지」 · `flow.json` 이 주어, 템플릿 행의 주어 없음, `frames` 를 만드는 주체 없음, 계산 주체 · 날짜 · 커밋 없음 | fit |
| 「장면 · 화면 대조」 행에 쉼표 두 번, 사건 서술이 하는 일 칸에 있음, `step` 정의의 수식어 겹침, 「」 겹침 표기 | fit |

## 커버리지 공백

- 토스트 장면 넷(comment-1 · result-2 · result-3 · result-4)의 끝 사각형이 없는 원인(1.5초 뒤 사라짐인지 문구 불일치인지)은 어느 렌즈도 확인하지 않았다.
- RM 창에 `role="dialog"` 같은 고정 선택자가 있어 끝 대상 규칙을 지킬 수 있는지는 어느 렌즈도 확인하지 않았다.
- `manual_template.html` 의 전체 재생 흐름은 일부 줄만 읽혔다.
