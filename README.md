# kw-plugins

키움 AX 팀이 사내 PC에 제공하는 클로드 코드 플러그인의 마켓플레이스다. 여기서 배포하는
것은 **컨트롤 타워**와 **문서 형식 스킬**과 **배포 스킬**과 **대시보드 스킬** 4개이고, 외부 코드 저장소에 있는 플러그인은 컨트롤
타워가 목록에 따라 설치한다.

**이름이 2개라서 헷갈리기 쉽다.** 코드 저장소 이름과 클로드 코드에 등록되는 마켓플레이스 이름이 다르다.
가리키는 것이 다르기 때문이다. 앞의 것은 어디서 내려받는지를, 뒤의 것은 어느 마켓플레이스의 플러그인인지를 나타낸다.
플러그인 ID가 `kw-devops@kiwoom-ax` 처럼 뒤의 이름을 쓰므로, 그것을 바꾸면 사내 모든
PC가 다시 설치해야 한다. 그래서 이름을 바꾸지 않는다.

| 쓰는 곳 | 이름 |
|---|---|
| GitHub 코드 저장소 | `KiwoomAX/kw-plugins` |
| 클로드 코드에 등록되는 마켓플레이스 이름 | `kiwoom-ax` |
| 플러그인 ID | `<플러그인이름>@kiwoom-ax` |

## 왜 이렇게 만들었나

전에는 "이 PC에 무엇을 설치할지"가 설치기(`kw_install`) 코드 안에 적혀 있었다. 그래서 플러그인을
하나 추가할 때마다 설치기를 고치고 **전 직원이 설치기를 다시 실행해야** 했다.

목록을 설치기 밖으로 꺼내 이 코드 저장소에 두었다. 이제 플러그인을 추가하는 일은 `manifest.json`에 한 줄을
추가하고 체크포인트로 저장해 GitHub에 업로드하는 것이고, 각 PC는 다음 세션에서 그 변경을 반영한다.

## 새 사내 플러그인을 추가하려면

**이 코드 저장소 안에 둔다.** `plugins/이름/` 아래에 플러그인을 놓고 2곳에 한 줄씩 추가한다.

```jsonc
// .claude-plugin/marketplace.json (무엇을 제공하는가)
{ "name": "kw-infra", "source": "./plugins/kw-infra" }

// plugins/kw-control-tower/manifest.json (각 PC가 그것을 갖춰야 하는가)
"required": [ "kw-infra@kiwoom-ax" ]
```

마켓플레이스는 이미 등록되어 있으므로 `marketplaces`는 수정하지 않는다. 출처가 이 코드 저장소 안의 경로라
마켓플레이스를 내려받을 때 파일이 함께 오고, 설치할 때 네트워크를 쓰지 않는다.

**출처를 `{ "source": "github", "repo": "소유자/저장소" }` 로 적지 마라.** 5가지 출처
형식 가운데 이것만 `https://` 같은 주소 앞부분 없이 적는 형식이라 클로드 코드가 주소를 직접 만든다.
그런데 플러그인을 설치하는 쪽은 SSH 주소를 만들기 때문에, SSH 키가 없는 사내 PC에서는
`Host key verification failed` 오류를 내고 설치가 실패한다. 코드 저장소가 공개인지는 관계없다.
그 오류는 접근 권한을 확인하기 전 단계인 호스트 키 검증에서 발생한다. 2026-09-06에 다시 확인했다.

외부 코드 저장소를 꼭 가리켜야 한다면 `{ "source": "url", "url": "https://…git" }` 처럼
**`https://`로 시작하는 완전한 주소**를 적는다. 공식 마켓플레이스가 외부 코드 저장소 238곳을 그 형식으로
가리키고 있고, 그 가운데 `superpowers`가 사내 PC에서도 매번 정상적으로 설치된다.

## 컨트롤 타워가 하는 일

2가지이고, 앞의 것이 뒤의 것을 호출한다.

**클로드 코드를 시작할 때 점검한다.** 이 PC가 목록과 다른 곳이 있는지 14가지를 확인한다. 파일을
읽고, GitHub 의 최신 버전 번호 하나만 `curl.exe`로 읽는다. 다른 곳이 하나도 없으면 아무것도 알리지 않고 종료한다.

**다른 곳이 있으면 즉시 동기화한다.** 단계는 8개이고 저마다 독립이라 하나가 실패해도 나머지는
실행된다. 마켓플레이스 등록과 업데이트, 필수 플러그인 설치와 다시 활성화와 업데이트,
더 이상 쓰지 않는 것 정리, 파이썬 라이브러리, `PYTHONUTF8`, `CLAUDE.md`의 사내 지침, 이전에
복사해 둔 스킬과 훅 연결 정리, 전역 설정의 출력 스타일(`outputStyle` 항목이 없을 때만 `"Concise"`)이다. 점검에서 다른 곳이 나온 단계만 실행하고, 제한 시간 60초에 이르면 남은 단계를 다음 세션으로 미룬다. 같은 원인으로 실패한 단계는 그날 다시 호출하지 않는다.

**동기화를 호출하는 명령을 따로 두지 않는다.** 예전에는 세션이 시작할 때 `/kw-sync` 를 입력하라는 안내만 표시했는데,
안내를 읽고 명령을 입력하는 사람이 없으면 점검이 정확해도 아무것도 바뀌지 않았다. 목록에
새 플러그인이 추가되었는데도 몇 주씩 설치되지 않은 PC가 남았다.

무엇을 바꿨는지 마지막에 요약하고, **사용자가 비활성화한 필수 플러그인을 다시 활성화했으면 그것을 따로
적는다.** 회사가 정한 것이라 다시 활성화하지만, 사용자의 결정을 뒤집은 것이므로 조용히 지나가지 않는다.

## 세션 시작이 느려지지 않게 한 것

이것이 이 플러그인에서 가장 우선하는 제약이다. 세션 시작이 느려지면 점검이 아무리 유용해도 사용자가 이 플러그인을
비활성화하게 된다. 지킬 조건은 5가지다.

| 무엇 | 값 |
|---|---|
| 세션이 시작할 때 실행되는 훅 | 세션 점검 훅 1개뿐이고, 클로드 코드를 시작할 때만 실행된다 |
| 외부 프로그램 | `curl.exe` 1개. 최신 버전 확인에 쓴다(2026-09-25 승인). `claude`도 `git`도 `python`도 호출하지 않는다 |
| 네트워크 | 제한 시간 2초인 `curl.exe` 요청 1개. 훅 자체의 실행 시간에서 뺀다 |
| 읽는 것 | 설정 파일과 상태 파일과 사내 지침 복사본, 레지스트리 값 1개 |
| 훅 자체의 실행 시간 | 200밀리초를 넘으면 그 값을 기록한다. 검사는 이것을 실패가 아니라 사용자에게 확인할 것으로 보고한다 |

이 PC에서 여러 차례 측정하니 프로그램을 띄우는 시간까지 합쳐 0.55초 안팎이었고, 훅 자체의 실행 시간은 모두 200밀리초 안이었다.
세션이 처음 열릴 때 한 번은 200밀리초를 넘을 수 있는데, 그때는 화면 안내에 넣지 않고 기록만 남긴다.

훅은 `pwsh`로 등록한다. 5.1이 204밀리초 빠르지만(357 대 561) 7을 선택했다. 설치기는 pwsh 7을
설치하지 못하면 아무것도 설치하지 않고 종료하므로 7이 없는 PC에는 이 훅도 없다. 그리고 5.1 때문에 만든 우회 코드가
11곳이었다. 그중 하나는 문서와 코드를 대조하는 검사 4개를 한 번도 통과하지 못하게
하고 있었다.

## 이 코드 저장소에 있는 것

| 경로 | 무엇 |
|---|---|
| `.claude-plugin/marketplace.json` | 마켓플레이스 `kiwoom-ax` 정의 |
| `plugins/kw-control-tower/manifest.json` | **목록.** 새 플러그인은 여기에 추가한다 |
| `plugins/kw-control-tower/hooks/` | 세션 점검 훅, 도커 인증서 안내, 가짜 `python3` 호출 차단 |
| `plugins/kw-control-tower/scripts/sync.ps1` | PC를 목록에 맞게 고치는 동기화 스크립트. 세션 점검 훅과 설치기 9단계가 호출한다 |
| `plugins/kw-control-tower/scripts/git-identity.ps1` | git 명의를 GitHub 계정의 사내 메일로 제안하고, 사용자가 승인한 값을 저장한다. 세션 점검 훅의 안내를 받은 클로드가 실행한다 |
| `plugins/kw-control-tower/skills/` | 사내 인증서 스킬 |
| `plugins/kw-doc-formats/skills/` | 문서 형식 스킬 6개. `common`·`hwp`·`pdf`·`pptx`·`xlsx`·`docx` |
| `plugins/kw-devops/skills/` | 배포 스킬 `deploying-kiwoom-service`와 그 스킬이 호출하는 `scripts/pick_port.py`·`scripts/request-ax.ps1`, DBGateway 클라이언트 스킬 `searching-winus`와 그 스킬이 호출하는 `scripts/fetch_manifest.py`, fnguide 리포트 검색 스킬 `searching-document` |
| `tests/test_control_tower.ps1` | 컨트롤 타워가 지킬 조건을 확인하는 검사 |
| `tests/test_doc_formats.ps1` | 문서 형식 스킬이 지킬 조건을 확인하는 검사 |
| `plugins/kw-dashboard/skills/` | 대시보드 스킬 `building-kiwoom-dashboard`와 그 스킬이 여는 `migrating-existing-dashboard.md` |
| `tests/test_devops.ps1` | 배포 스킬과 DBGateway 스킬과 리포트 검색 스킬이 지킬 조건을 확인하는 검사 |
| `tests/test_dashboard.ps1` | 대시보드 스킬이 지킬 조건을 확인하는 검사 |
| `plugins/kw-design/skills/` | 사내 웹 화면의 기본 디자인 스킬 `designing-kiwoom-frontend`와 대시보드 목업 템플릿·토큰 복사본(`templates/`) |
| `tests/test_design.ps1` | 디자인 스킬이 지킬 조건을 확인하는 검사 |
| `docs/style-guide.md` | 문서, 주석, 화면 문구의 용어와 표현 기준 |
| `docs/superpowers/specs/` | 설계 문서. 왜 그렇게 만들었는지 |
| `docs/superpowers/reviews/` | 설계를 검토한 기록 |

## 손으로 고칠 때 지킬 것

**PowerShell 파일에 BOM을 붙이지 않는다.** 7은 BOM 없이도 UTF-8로 읽는다. 붙이지 않는
편이 오히려 낫다. BOM이 없으면 5.1로 실행했을 때 한국어가 조용히 깨지는 대신
문법 오류로 중단되어, 잘못 호출했다는 사실이 그 줄에서 드러난다.

**마크다운을 읽는 코드에는 `-Encoding UTF8`을 적는다.** 마크다운에는 BOM이 없어서 이것을
빼면 한국어가 깨진 채로 비교된다. 검사 4개가 이것 때문에 한 번도 통과한 적이 없었다.
내용이 틀려서가 아니라 표를 아예 찾지 못해서였다.

**`powershell.exe`를 호출하지 않는다.** 훅도 동기화도 `pwsh`로만 실행된다.

**고친 뒤에는 검사 5개를 모두 실행한다.**

```
pwsh -NoProfile -File tests\test_control_tower.ps1
pwsh -NoProfile -File tests\test_doc_formats.ps1
pwsh -NoProfile -File tests\test_devops.ps1
pwsh -NoProfile -File tests\test_dashboard.ps1
pwsh -NoProfile -File tests\test_design.ps1
```
