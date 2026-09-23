# kw-plugins

키움 AX 팀이 사내 PC에 나눠 주는 클로드 코드 플러그인의 마켓플레이스다. 여기서 배포하는
것은 **컨트롤 타워**와 **문서 형식 스킬**과 **배포 스킬**과 **대시보드 스킬** 넷이고, 남의 저장소에 있는 플러그인은 컨트롤
타워가 목록을 들고 끌어온다.

**이름이 둘인 것이 헷갈리기 쉽다.** 저장소 이름과 클로드 코드에 등록되는 이름이 다르다.
가리키는 것이 달라서 그렇다. 앞의 것은 어디서 받아오는지이고, 뒤의 것은 누가 낸 것인지다.
플러그인 번호표가 `kw-devops@kiwoom-ax` 처럼 뒤의 이름을 쓰므로, 그것을 바꾸면 사내 모든
PC가 다시 깔아야 한다. 그래서 두 이름을 그대로 둔다.

| 쓰는 곳 | 이름 |
|---|---|
| GitHub 저장소 | `KiwoomAX/kw-plugins` |
| 클로드 코드의 배포처 등록 이름 | `kiwoom-ax` |
| 플러그인 번호표 | `<플러그인이름>@kiwoom-ax` |

## 왜 이렇게 만들었나

전에는 "이 PC에 무엇을 깔지"가 설치기(`kw_install`) 코드 안에 적혀 있었다. 그래서 플러그인을
하나 추가할 때마다 설치기를 고치고 **전 직원이 그것을 다시 돌려야** 했다.

목록을 설치기 밖으로 꺼내 여기 두었다. 이제 플러그인을 추가하는 일은 `manifest.json`에 한 줄
추가하고 커밋하는 것이고, 각 PC는 다음 세션에 그 변화를 듣는다.

## 새 사내 플러그인을 추가하려면

**이 저장소 안에 둔다.** `plugins/이름/` 아래에 플러그인을 놓고 두 곳에 한 줄씩 추가한다.

```jsonc
// .claude-plugin/marketplace.json — 무엇을 파는가
{ "name": "kw-infra", "source": "./plugins/kw-infra" }

// plugins/kw-control-tower/manifest.json — 각 PC가 그것을 갖춰야 하는가
"required": [ "kw-infra@kiwoom-ax" ]
```

배포처는 이미 등록돼 있으므로 `marketplaces`는 안 건드린다. 원본이 이 저장소 안의 경로라
마켓플레이스를 받을 때 파일이 함께 오고, 설치가 네트워크를 안 쓴다.

**원본을 `{ "source": "github", "repo": "소유자/저장소" }` 로 적지 마라.** 다섯 가지 원본
형식 가운데 이것만 프로토콜을 안 받아서 클로드 코드가 주소를 조립하는데, 플러그인 설치 쪽
조립기가 SSH를 골라 SSH 키가 없는 사내 PC에서 `Host key verification failed`로 끝난다.
저장소가 퍼블릭인지는 무관하다 — 그 오류는 인가 이전인 호스트 키 검증에서 난다.
2026-09-06에 재고 확인했다.

정말로 남의 저장소를 가리켜야 한다면 `{ "source": "url", "url": "https://…git" }` 처럼
**프로토콜이 든 완전한 주소**를 적는다. 공식 마켓플레이스가 외부 저장소 238곳을 그 형식으로
가리키고 있고, 그 가운데 `superpowers`가 사내 PC에서 매번 깔린다.

## 컨트롤 타워가 하는 일

두 가지이고, 앞의 것이 뒤의 것을 호출한다.

**세션이 시작할 때 감지한다.** 이 PC가 목록과 불일치하는 곳을 열두 가지로 확인한다. 파일만
읽고 네트워크에 안 나간다. 불일치가 하나도 없으면 아무 말도 하지 않고 끝난다. 이
PC에서 362밀리초다.

**불일치가 있으면 즉시 맞춘다.** 단계가 여덟이고 저마다 독립이라 하나가 실패해도 나머지는
돈다. 배포처 등록과 사본 받아오기, 필수 플러그인 설치와 되켜기와 뒤처진 설치본 옮기기,
더 안 쓰는 것 정리, 파이썬 라이브러리, `PYTHONUTF8`, `CLAUDE.md`의 사내 문안, 옛 스킬
사본과 훅 연결 정리, `python3` 판정이다.

**호출하는 명령을 따로 두지 않는다.** 예전에는 알림이 `/kw-sync` 를 치라고 말하고 끝났는데,
알림을 읽고 명령을 치는 사람이 없으면 감지가 정확해도 아무것도 안 바뀌었다. 사내 목록에
새 플러그인이 추가된 것을 알고도 몇 주씩 안 깔린 PC가 남았다.

무엇을 바꿨는지 마지막에 요약하고, **사용자가 꺼 둔 필수 플러그인을 되켰으면 그것을 따로
적는다.** 회사가 정한 것이라 되켜지만 사용자 결정을 뒤집은 것이므로 조용히 지나가지 않는다.

## 세션 시작이 느려지지 않게 한 것

이것이 이 플러그인의 첫째 제약이다. 알림이 느려지면 감지의 값이 얼마든 사용자가 그것을
끄게 된다. 계약이 다섯이다.

| 무엇 | 값 |
|---|---|
| 세션 시작에 도는 훅 | 하나뿐이다 |
| 외부 프로그램 | 호출하지 않는다. `claude`도 `git`도 `python`도 |
| 네트워크 | 안 나간다. 디스크에 있는 것만 본다 |
| 읽는 것 | 파일 여덟과 레지스트리 값 하나. 이 PC에서 합쳐 25KB 미만 |
| 몸통 시간 | 200밀리초를 넘으면 그 값을 남기고 검사가 떨어진다 |

이 PC에서 여러 차례 재니 프로세스까지 합쳐 0.55초 안팎이고 몸통은 다 200밀리초 안이었다.
세션이 처음 열릴 때 한 번은 넘길 수 있는데, 그때는 알림에 안 섞고 자국만 남긴다.

훅을 `pwsh`로 건다. 5.1이 204밀리초 빠르지만(357 대 561) 7을 골랐다. 설치기가 pwsh 7을
못 깔면 아무것도 안 깔고 끝내므로 7이 없는 PC에는 이 훅도 없고, 5.1이 만든 우회가
열한 군데였다. 그중 하나는 문서와 코드를 대조하는 검사 넷을 한 번도 통과하지 못하게
하고 있었다.

## 이 저장소에 있는 것

| 경로 | 무엇 |
|---|---|
| `.claude-plugin/marketplace.json` | 마켓플레이스 `kiwoom-ax` 정의 |
| `plugins/kw-control-tower/manifest.json` | **목록의 원본.** 새 플러그인은 여기에 추가한다 |
| `plugins/kw-control-tower/hooks/` | 세션 시작 알림, 도커 인증서 안내, `python3` 가드 |
| `plugins/kw-control-tower/scripts/sync.ps1` | 이 PC를 목록에 맞게 고치는 본체. 알림 훅과 설치기 9단계가 호출한다 |
| `plugins/kw-control-tower/skills/` | 사내 인증서 스킬 |
| `plugins/kw-doc-formats/skills/` | 문서 형식 스킬 여섯. `common`·`hwp`·`pdf`·`pptx`·`xlsx`·`docx` |
| `plugins/kw-devops/skills/` | 배포 스킬 `deploying-kiwoom-service`와 그 스킬이 호출하는 `scripts/pick_port.py`·`scripts/request-ax.ps1`, Query Gateway 클라이언트 스킬 `searching-winus`와 그 스킬이 호출하는 `scripts/fetch_manifest.py` |
| `tests/test_control_tower.ps1` | 컨트롤 타워의 계약 검사 |
| `tests/test_doc_formats.ps1` | 문서 형식 스킬의 계약 검사 |
| `plugins/kw-dashboard/skills/` | 대시보드 스킬 `building-kiwoom-dashboard`와 그 스킬이 여는 `moving-existing-dashboard.md` |
| `tests/test_devops.ps1` | 배포 스킬과 Query Gateway 스킬의 계약 검사 |
| `tests/test_dashboard.ps1` | 대시보드 스킬의 계약 검사 |
| `docs/superpowers/specs/` | 설계 문서. 왜 그렇게 만들었는지가 여기 있다 |
| `docs/superpowers/reviews/` | 그 설계를 검토한 기록 |

## 손으로 고칠 때 지킬 것

**PowerShell 파일에 BOM을 붙이지 않는다.** 7은 BOM 없이도 UTF-8로 읽는다. 붙이지 않는
편이 낫기까지 한데, BOM이 없으면 5.1로 돌렸을 때 한국어가 조용히 깨지는 것이 아니라
파싱 오류로 죽어서 잘못 호출한 것이 그 줄에서 드러난다.

**마크다운을 읽는 코드에는 `-Encoding UTF8`을 적는다.** 마크다운에는 BOM이 없어서 이것을
빼면 한국어가 깨진 채로 비교된다. 검사 넷이 이것 때문에 한 번도 통과한 적이 없었고,
내용이 틀려서가 아니라 표를 아예 못 찾아서였다.

**`powershell.exe`를 호출하지 않는다.** 훅도 맞춤도 `pwsh`로만 돈다.

**고친 뒤에는 검사를 넷 다 돌린다.**

```
pwsh -NoProfile -File tests\test_control_tower.ps1
pwsh -NoProfile -File tests\test_doc_formats.ps1
pwsh -NoProfile -File tests\test_devops.ps1
pwsh -NoProfile -File tests\test_dashboard.ps1
```
