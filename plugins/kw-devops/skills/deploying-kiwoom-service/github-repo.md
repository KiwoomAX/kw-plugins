# 1단계 — remote 가 없을 때 저장소 정하기

SKILL.md 의 1단계에서 `git remote get-url origin` 이 주소를 내지 않을 때 연다. zip 으로 받은 폴더처럼 `.git` 이
없는 복사본이 대부분이다.

**같은 코드의 저장소가 조직에 이미 있으면 새로 만들지 않고 그 저장소에 붙인다.** 저장소가 둘이 되면 조직 폴더가
같은 `Jenkinsfile` 로 잡을 둘 만들고, 두 잡의 Deploy 가 같은 `container_name` 의 컨테이너를 서로 지운다.

## 이름 후보 모으기

| 어디서 | 후보 |
|---|---|
| 폴더 이름 | 끝의 `-main`·`-master`·` (1)` 을 뗀 값. zip 과 브라우저가 붙이는 접미사다 |
| compose | `name:` 과 `container_name` |
| 패키지 파일 | `package.json`·`pyproject.toml` 의 `name` |

```powershell
(Split-Path -Leaf (Get-Location)) -replace ' \(\d+\)$', '' -replace '-(main|master)$', ''
```

## 두 곳에서 찾기

- **포트 등록부** — SKILL.md 1단계의 `--find` 줄에 후보를 모두 넘긴다. 나온 줄의 `repo` 칸이 저장소 이름이다.
  배포까지 마친 서비스는 GitHub 권한 없이 여기서 찾힌다.
- **GitHub 조직** — 두 조직의 저장소 이름 목록을 받아 후보와 비교한다. 대소문자와 `-`·`_` 차이는 무시한다
  (`Executive_dashboard` 와 `executive-dashboard` 는 같은 후보다). 이름만 보고 저장소 내용은 열지 않는다.

```powershell
gh repo list KiwoomAX --limit 1000 --json name,url,pushedAt
gh repo list KiwoomAM --limit 1000 --json name,url,pushedAt
```

`gh` 가 로그인 오류를 내면 멈추고, 담당자에게 `gh auth login` 을 직접 실행하라고 알린다. 목록을 보지 못한 채로
새 저장소를 만들지 않는다.

**목록에 보이지 않는 저장소는 없는 것으로 본다.** 담당자가 볼 권한이 없는 비공개 저장소는 담당자의 저장소가
아니므로 새로 만드는 쪽이 맞다.

## 담당자에게 확인받기

찾은 저장소가 있으면 주소와 마지막 push 시각(`pushedAt`)을 보여 주고 「이 코드의 저장소가 맞습니까」라고 묻는다.
없으면 「GitHub 에 이 코드를 올린 적이 없습니까, 올린다면 KiwoomAX 와 KiwoomAM 중 어느 조직입니까」라고 묻는다.

| 답 | 어떻게 한다 |
|---|---|
| 찾은 저장소가 맞다 | 「기존 저장소에 붙이기」 |
| 올린 적이 없다, 또는 찾은 저장소가 다른 코드다 | 「새 저장소 만들기」 |
| 모른다 | 새 저장소를 만들지 않고 멈춘다. 코드를 받은 사람(전임자·요청자)에게 저장소 주소를 물어보라고 알린다 |

## 기존 저장소에 붙이기

```powershell
if (-not (Test-Path .git)) { git init -b main }
git remote add origin <찾은 주소>
git fetch origin
git reset origin/main        # 작업 폴더 파일은 그대로 두고 기준만 원격 main 으로 맞춘다
git branch -u origin/main
git status --short
```

`git log -1` 이 원격 main 의 마지막 커밋을 가리키면 연결이 끝났다.

**이 시점에는 스킬이 아직 아무 파일도 쓰지 않았으므로, `git status` 의 차이는 모두 복사본과 원격의 차이다.** 차이가
있으면 목록을 보여 주고 파일마다 담당자가 고친 파일인지 묻는다. 담당자가 고치지 않은 파일은 복사본이 원격보다
오래돼 생긴 차이다. 그대로 커밋하면 남이 올린 변경을 되돌리므로 `git restore <파일>` 로 원격 것을 받는다. `??` 로
나오는 `.env`·`certs/` 는 커밋하지 않는다 — 3단계가 `.gitignore` 에 넣는다.

push 는 4단계에서 한다.

## 새 저장소 만들기

```powershell
if (-not (Test-Path .git)) { git init -b main }
gh repo create <조직>/<이름> --private --source . --remote origin
```

조직은 담당자가 답한 KiwoomAX 나 KiwoomAM 이다. 개인 계정 아래에 만들면 조직 폴더가 발견하지 못한다. 이름은 후보
중 담당자와 정한 이름을 쓴다. push 는 4단계에서 한다.
