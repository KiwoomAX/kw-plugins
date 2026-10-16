# 코드 동작 흐름 안내 화면 스킬 설계 리뷰 (2026-10-14)

대상은 `docs/superpowers/specs/2026-10-14-code-flow-guide-design.md` 이고, 렌즈 원본은 같은 이름의 폴더에 있다.

## 실행 조건

- 실행한 렌즈: `lens-grounding`, `lens-consistency`, `lens-adversarial`, `lens-fit`
- 렌즈를 한 번씩만 실행했다.
- 선행연구 렌즈: 제안하지 않았다. 손으로 두 번 만든 시제품의 절차를 스킬로 옮기는 spec 이어서, 되는지 자체가 미지수인 일이 아니다. 대상은 `docs/superpowers/specs` 아래에 있어 spec 으로 구분했다.

## 합친 지적

| 지적 | 잡은 렌즈 | 합치기 판정 |
|---|---|---|
| 캡처 중 버튼 클릭을 허용하는지가 없다. 클릭하면 운영 Redis 쓰기, Claude 과금, 메일 발송으로 이어진다 | adversarial | 근거 확인. `app/api/automation/send/route.ts` 가 POST 로 발송 스크립트를 실행한다 |
| 5xx 를 「데이터 없음」으로 묶어 로컬 전용 가드의 503 을 잘못 판정한다 | adversarial | 근거 확인. `lib/localOnly.ts` 가 503 을 돌려준다 |
| 페이지 문서 요청 자체의 401(Basic 인증)이나 로그인 리다이렉트를 판정표가 다루지 않는다 | adversarial | 근거 확인. `middleware.ts` |
| 판정 대상 API 를 고르는 규칙과 빈 목록의 모양이 없고, 200 샘플 응답이 정상으로 통과한다 | adversarial, grounding | 근거 확인. 두 렌즈가 함께 잡았다 |
| 서버 종료와 포트 충돌 처리가 없다 | adversarial | 근거 있음 |
| 토큰이 세션 기록 · 잠금 파일 · `~/.gitconfig` 에 남는 경로를 막는 수단이 없다 | adversarial, grounding | 근거 확인. ESG Dockerfile 이 `git config --global insteadOf` 를 쓴다 |
| 실데이터를 이유로 git 에서 빼면서 공유하라고만 안내한다 | adversarial | 근거 있음 |
| 루프백 연결을 특정 레포에만 적용해 판정 기준이 없다 | adversarial, grounding | 근거 확인. 시제품 실행은 실제로 `next dev -H 0.0.0.0 -p 3110` 이었다 |
| 헤드리스 Chrome 구동 수단과 응답 기록 수단이 정해지지 않았다 | adversarial, grounding, consistency | 근거 확인. 세 렌즈가 함께 잡았다 |
| `DOCK_BY_ID` 를 지우며 쓰인 적 없는 `dock` 입력을 남긴다 | adversarial | 근거 확인. 두 시제품 JSON 에 `dock` 이 없다 |
| 포트 3110 이 레포 설정에 없다 | grounding | 근거 확인. `-p 3110` 을 직접 줬다 |
| Kiwoom-ESG 는 화면이 Kiwoom-RAG 에 있어 「화면은 같은 레포」 가정과 부딪힌다 | grounding | 근거 확인. 사용자 가정의 예외 레포로 다룬다 |
| 헤드리스 가상 시간 주장에 출처가 없다 | grounding | 시제품 작업 중 관찰이 출처다. 문서에 관찰임을 적는다 |
| `generate_github_token.py` 는 Kiwoom-Parsing 에만 있고 ESG 는 bash 와 Dockerfile 인라인을 쓴다 | grounding | 근거 확인 |
| 토큰 스크립트의 App ID · 설치 ID 입력과 PyJWT 설치 위치가 없다 | grounding | 근거 확인 |
| ESG 사설 패키지는 `requirements.txt` 가 아니라 Dockerfile 에서 설치한다 | grounding | 근거 확인 |
| `--native-tls` 근거가 없고 `ePrism.crt` 를 쓰는 단계가 없다 | grounding | 근거 확인 |
| PowerShell 에서 성립한다는 근거가 없다 | grounding | 근거 있음 |
| `uv` 의 `.venv/.gitignore` 주장에 출처가 없다 | grounding, consistency | 주장은 맞다. 출처만 적는다 |
| 「레포를 고치지 않는다」와 uv 가상환경 · `npm install` 의 잠금 파일 변경이 모순된다 | consistency | 근거 확인. 시제품에서 `package-lock.json` 이 바뀌어 되돌렸다 |
| Node 의존성 설치 단계와 프론트 · 백엔드 실행 순서가 없다 | consistency | 근거 있음 |
| 토큰 발급 · 사설 패키지 설치 · 브라우저 의존성을 맡을 파일이 없다 | consistency | 근거 있음 |
| 표를 지운 뒤 템플릿 대체 경로와 필수 필드 누락 시 동작이 없다 | consistency | 근거 확인. `movie_template.html` 164 · 167 · 231행 |
| 좌표계(높이 520 기준, 0.86 배)가 없다 | consistency | 근거 확인 |
| `setupShot` 이 `screenImg` 가 없으면 칸을 숨겨 `screen.unavailable` 문구가 나오지 않는다 | consistency | 근거 확인. 293행 |
| JSON 필드 목록이 정의되지 않았다 | consistency | 근거 확인. `nodeOverride` · `startImg` · `endImg` 는 wholesale 에서 쓰이고 `zoneNames` · `dock` 은 쓰이지 않는다 |
| 분석 결과와 캡처 결과를 합치는 단계와 주체가 없다 | consistency | 근거 있음 |
| 캡처 해상도(1440×1000)가 없다 | consistency | 근거 확인. 290행 |
| 결과물 폴더 안의 파일 이름과 재실행 시 처리가 없다 | consistency | 근거 있음 |
| 플러그인 description 이 `plugin.json` 과 `marketplace.json` 두 곳에 있다 | consistency | 근거 확인 |
| 명칭표 「화면 표기」 열이 KIND 라벨과 노드 이름을 섞는다 | consistency | 근거 확인 |
| winus 구역 표시 이름이 없고 템플릿 주석은 「영역」이라 부른다 | consistency | 근거 확인 |
| 렌더 확인 「재생된다」와 「애니메이션은 헤드리스로 검증하지 않는다」가 부딪힌다 | consistency | 근거 있음 |
| 문장 규칙의 적용 대상에서 `tips-prompt.md` 가 빠졌다 | consistency | 근거 있음 |
| 레포 찾기 규칙(검색 위치, 후보 여럿 · 없음)이 없다 | consistency | 근거 있음 |
| 절 첫 문장이 결론이 아닌 절(목적 · 위치 · 템플릿에서 지울 값 · 하지 않는 것) | fit | 근거 확인 |
| 표 열의 말끝 불일치, 표 머리 「스킬에서」 | fit | 근거 확인 |
| 결정에 쓰이지 않는 개수, 개수 예고 | fit | 근거 확인 |
| 다섯 문장 단락, 두 문장 불릿 | fit | 근거 확인 |
| 주체 생략, 「장면」을 주체로 씀, 문장 중간 관형절 | fit | 근거 확인 |
| 서브에이전트 · 에이전트 · 분석 에이전트 혼용, 「줌 상자」 미설명 | fit | 근거 확인 |

## 커버리지 공백

렌즈 네 개가 모두 spec 전체를 읽었다. `generate_github_token.py` 가 사용자 PC 에서 실제로 토큰을 받는지, 사용자 PC 의 Chrome 설치 여부는 어느 렌즈도 측정하지 않았다.
