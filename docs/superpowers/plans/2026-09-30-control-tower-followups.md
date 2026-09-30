# kw-control-tower 후속 수정 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 세션 시작 맞춤이 불일치한 단계만, 시간 상한 안에서, 한 번에 하나씩 실행되고, 같은 원인의 실패를 되풀이하지 않게 한다.

**Architecture:** 감지(`hooks/session-check.ps1`)가 불일치마다 단계 번호를 붙여 맞춤(`scripts/sync.ps1`)에 `-Steps` 와 `-BudgetSeconds` 로 넘긴다. 맞춤은 `Want` 로 단계마다 실행 여부를 정한다. 실패하거나 상한에 끊긴 단계에는 지문을 적는다. 지문은 목록 파일 둘(`manifest.json`·`requirements.txt`)의 내용과 날짜와 단계 번호로 만든 MD5 이며, 감지는 다음 세션에 지문이 같으면 그 단계를 넘기고 알리기만 한다. python3 판정은 맞춤에서 가드로 옮긴다.

**Tech Stack:** PowerShell 7 (pwsh), 검사는 `tests/test_control_tower.ps1` 의 `Check` 함수.

**Spec:** `docs/superpowers/specs/2026-09-30-review-followups-design.md`

## Global Constraints

- 모든 스크립트는 PowerShell 7 을 전제한다. 5.1 호환 문법을 새로 넣지 않는다. 계획의 한 줄 명령도 PowerShell 7 에서 실행한다.
- PowerShell 파일에 BOM 을 붙이지 않는다(README 113행). 줄바꿈은 `.gitattributes` 가 정한다.
- **Task 1 을 마치기 전에는 `tests/test_control_tower.ps1` 전체를 실행하지 않는다.** 지금 파일은 실제 맞춤을 호출해 이 PC 의 파이썬·레지스트리를 바꿀 수 있다. Task 1 의 확인은 파일 전체가 아니라 적힌 한 줄 명령으로 한다.
- 행 번호는 모두 origin/main `c75a44f` 기준이다. 앞 Task 가 같은 파일을 바꾼 뒤에는 번호가 밀리므로, 함께 적은 코드 문자열과 검사 이름으로 위치를 찾는다.
- 감지가 호출하는 외부 프로그램은 `curl.exe` 하나뿐이다(2026-09-25 승인). 새로 늘리지 않는다.
- 공개 저장소의 AX 팀 메일과 `/home/chshin84/opt` 경로는 건드리지 않는다.
- 맞춤 단계 번호는 Task 3 이후 1–7 이다. 단계 6 은 `CLAUDE.md`, 단계 7 은 옛 스킬·훅이다.
- Task 마다 실패 확인은 `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1` 로 하고, 커밋 전 통과 확인은 README 「손으로 고칠 때 지킬 것」대로 검사 넷(`test_control_tower.ps1`·`test_doc_formats.ps1`·`test_devops.ps1`·`test_dashboard.ps1`)을 모두 실행한다. 기대는 `실패 없음` 또는 `FAIL=0` 이다. `ASK` 줄은 실패가 아니다.

## Review Focus

- `ranOnce` 만 있고 `suggestedDone` 이 없는 옛 PC 의 상태 파일 — 사용자가 지운 옛 권장 플러그인은 다시 깔지 않고, 이행 뒤 권장에 새로 올린 플러그인은 한 번 깔아야 한다. Task 10 의 이행 검사 두 개가 확인한다.
- 실제 `claude.exe` 호출이 시간 상한에 닿아 끊긴 실행 — 맞춤 잠금이 남지 않고, 끊긴 단계는 그날 다시 호출되지 않아야 한다. Task 9 와 Task 11 의 끊김 검사가 확인한다.
- Claude Code 창 둘을 거의 동시에 연 PC — 둘째 맞춤은 넘기고 첫째가 끝나면 잠금이 사라져야 한다. Task 11 의 검사가 확인한다.
- 감지가 찾은 불일치가 모두 같은 원인으로 이미 실패한 세션 — 맞춤을 호출하지 않고 알리기만 해야 한다. Task 9 의 검사가 확인한다.
- 옛 버전이 적은 `python3=redirector` 줄이 남은 상태 파일 — 가드는 그 줄을 보지 않고, 맞춤은 그 줄을 지워야 한다. Task 3 의 검사 두 개가 확인한다.

---

### Task 1: 검사가 실제 맞춤을 호출하지 않게 한다

지금 「알림 훅의 동작」 절의 검사 셋과 몇 검사는 `& '$plugin\hooks\session-check.ps1'` 로 진짜 플러그인 폴더의 훅을 실행한다. 훅은 자기 폴더 옆 `scripts\sync.ps1` 을 찾으므로 가짜 홈에서도 진짜 맞춤이 실행되어 pip 과 레지스트리와 `claude` 를 건드린다.

**Files:**
- Modify: `tests/test_control_tower.ps1` (298–357행 절, 313–322행, 423–441행, 525–533행, 1166–1174행 절)

**Interfaces:**
- Produces: 테스트 안의 `$quietRoot` — 맞춤을 뺀 플러그인 사본 폴더. 훅을 직접 실행하는 검사는 모두 이 경로의 훅을 쓴다.

- [ ] **Step 1: 차단 검사를 추가한다**

1166행 `# --- 검사가 이 PC 를 안 바꾼다` 절의 `Check '훅을 호출하는 검사가 진짜 홈을 안 넘긴다'` 바로 아래에 넣는다.

```powershell
# 진짜 플러그인 폴더의 훅을 실행하면 훅이 옆의 진짜 맞춤을 찾아 호출한다. 가짜 홈에는 필수
# 플러그인이 없어 불일치가 늘 생기므로 맞춤이 실행되고, 이 PC 의 파이썬과 레지스트리가 바뀐다.
Check '훅을 호출하는 검사가 진짜 플러그인 폴더의 훅을 안 돌린다' {
    $self = Get-Content $PSCommandPath -Raw -Encoding UTF8
    $self -notmatch '''\$plugin\\hooks\\session-check\.ps1'''
}
```

- [ ] **Step 2: 지금은 검출되는지 한 줄로 확인한다**

파일 전체를 실행하지 않는다. PowerShell 7 에서 실행한다.

Run: `pwsh -NoProfile -Command "(Get-Content tests\test_control_tower.ps1 -Raw) -match '''\`$plugin\\hooks\\session-check\.ps1'''"`
Expected: `True`

- [ ] **Step 3: 맞춤을 뺀 사본을 만든다**

302행(`New-Item ... $fake '.claude\plugins'`) 바로 아래에 넣는다.

```powershell
# 맞춤을 뺀 사본으로 훅을 실행한다. 훅은 자기 폴더 옆의 scripts\sync.ps1 을 호출하므로,
# 진짜 폴더의 훅을 실행하면 가짜 홈에서도 진짜 맞춤이 실행된다.
$quietRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-q-" + [guid]::NewGuid().ToString('n').Substring(0,8))
Copy-Item -LiteralPath $plugin -Destination $quietRoot -Recurse
Remove-Item -LiteralPath (Join-Path $quietRoot 'scripts\sync.ps1')
```

- [ ] **Step 4: 훅을 직접 실행하는 곳을 모두 사본으로 바꾼다**

아래 여섯 곳에서 `'$plugin\hooks\session-check.ps1'` 을 `'$quietRoot\hooks\session-check.ps1'` 로, 같은 명령 안의 `CLAUDE_PLUGIN_ROOT='$plugin'` 을 `CLAUDE_PLUGIN_ROOT='$quietRoot'` 로 바꾼다.

| 행 | 검사 |
|---|---|
| 306–307 | 설정 파일이 하나도 없으면 조용히 물러난다 |
| 318 | 목록 파일이 없으면 아무 말도 안 한다 (ROOT 는 `$empty` 그대로, 훅 경로만 바꾼다) |
| 328–329 | 할 말이 있으면 훅 JSON 으로 사용자와 Claude 에게 함께 낸다 |
| 345–346 | 몸통이 200밀리초 안에 끝난다 |
| 432 | 칸이 빠진 목록으로는 알림이 아무 말도 안 한다 (ROOT 는 `$badManifest` 그대로, 훅 경로만 바꾼다) |
| 529 | 망가진 설정에서 알림은 조용하고 자국을 남긴다 |

357행 `Remove-Item -LiteralPath $fake ...` 는 그대로 두고, 533행 `Remove-Item -LiteralPath $brokenHome ...` 바로 아래에 넣는다.

```powershell
Remove-Item -LiteralPath $quietRoot -Recurse -Force -ErrorAction SilentlyContinue
```

- [ ] **Step 5: 한 줄 확인이 뒤집혔는지 본다**

Run: Step 2 의 명령
Expected: `False`

- [ ] **Step 6: 검사를 실행한다**

Run: 검사 넷(Global Constraints)
Expected: 모두 실패 없음. 실패가 있으면 되돌려 대조하지 말고, 실패한 검사 이름과 출력을 사용자에게 알린다. 되돌린 옛 파일은 실제 맞춤을 호출한다.

- [ ] **Step 7: 커밋한다**

```bash
git add tests/test_control_tower.ps1
git commit -m "test: 훅 검사가 진짜 맞춤을 호출하지 않게 맞춤을 뺀 사본으로 실행한다"
```

---

### Task 2: 세션 시작 훅을 켤 때만 실행하고 도커 안내의 인코딩을 맞춘다

**Files:**
- Modify: `plugins/kw-control-tower/hooks/hooks.json:5`
- Modify: `plugins/kw-control-tower/hooks/docker-cert-reminder.ps1:8`
- Test: `tests/test_control_tower.ps1` (「맞춤이 끝까지 간다」 절, 「도커 인증서 안내」 절)

**Interfaces:**
- 없음. 다른 Task 가 기대는 이름을 만들지 않는다.

- [ ] **Step 1: 실패하는 검사 두 개를 넣는다**

「맞춤이 끝까지 간다」 절의 `Check '세션 시작 훅의 예산이 맞춤을 끝낼 만큼이다'` 아래에 넣는다.

```powershell
# 설치와 갱신은 클로드 코드를 다시 켜야 적용되므로 /clear 나 resume 에서 다시 맞춰도 이 세션에는
# 안 실린다. 켤 때만 실행한다.
Check '세션 시작 훅은 클로드 코드를 켤 때만 돈다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    (@($j.hooks.SessionStart).Count -eq 1) -and ($j.hooks.SessionStart[0].matcher -eq 'startup')
}
```

「도커 인증서 안내」 절의 `Check '번들 위치를 환경변수에서 읽는다'` 아래에 넣는다.

```powershell
# 콘솔 코드페이지가 949 면 한국어 안내가 cp949 로 나가 Claude 가 UTF-8 로 읽을 때 깨진다.
# 같은 플러그인의 다른 훅 둘은 이미 맞춘다.
Check '도커 안내 훅이 나가는 인코딩을 UTF-8 로 맞춘다' {
    $dockerSrc.Contains('[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)')
}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: `세션 시작 훅은 클로드 코드를 켤 때만 돈다` 와 `도커 안내 훅이 나가는 인코딩을 UTF-8 로 맞춘다` 가 `FAIL`

- [ ] **Step 3: 구현한다**

`hooks.json` 5행:

```json
        "matcher": "startup",
```

`docker-cert-reminder.ps1` 8행 `$ErrorActionPreference = 'Stop'` 바로 아래:

```powershell

# 나가는 인코딩을 맞춘다. 콘솔 코드페이지가 949 면 한국어 안내가 cp949 로 나가 깨진다.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }
```

- [ ] **Step 4: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-control-tower/hooks/hooks.json plugins/kw-control-tower/hooks/docker-cert-reminder.ps1 tests/test_control_tower.ps1
git commit -m "fix: 세션 시작 훅을 켤 때만 실행하고 도커 안내의 출력 인코딩을 맞춘다"
```

---

### Task 3: python3 가드가 호출할 때 직접 판정한다

맞춤 단계 8 이 적어 둔 값을 읽던 것을, 가드가 호출 순간에 판정하게 바꾼다. 가드는 `hooks.json` 의 `if` 로 `python3` 으로 시작하는 명령에서만 실행되므로 fsutil 값(이 PC 48밀리초)은 그 명령에만 든다. 단계 8 을 없애 맞춤은 일곱 단계가 된다.

**Files:**
- Modify: `plugins/kw-control-tower/hooks/python3-guard.ps1` (1–33행)
- Modify: `plugins/kw-control-tower/scripts/sync.ps1` (226행 뒤, 786–829행 단계 8 삭제)
- Modify: `docs/superpowers/specs/2026-09-06-control-tower-design.md` (301·325·334행)
- Modify: `README.md` (59–62행)
- Test: `tests/test_control_tower.ps1` (476–508행 절, 「맞춤의 갱신 기록」 절)

**Interfaces:**
- Produces: 가드의 판정 주입 환경 변수 `KWCT_PYTHON3_PROBE` — 값은 `redirector` · `real` · `absent`. 검사만 쓴다.

- [ ] **Step 1: 검사를 주입 방식으로 바꾸고 새 검사를 넣는다**

483–493행 `Invoke-Guard` 를 통째로 바꾼다.

```powershell
function Invoke-Guard {
    # 판정은 가드가 호출할 때 한다. 검사는 KWCT_PYTHON3_PROBE 로 판정을 주입해 이 PC 의 python3 에
    # 기대지 않는다. 빈 값을 주면 주입하지 않고 실제 판정 경로를 실행한다.
    param([string]$Command, [string]$Verdict = 'redirector')
    $payload = @{ tool_name = 'Bash'; tool_input = @{ command = $Command } } | ConvertTo-Json -Compress
    $probe = if ($Verdict) { "`$env:KWCT_PYTHON3_PROBE='$Verdict'; " } else { '' }
    return ($payload | & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$fake2'; $probe& '$guard'" 2>&1 | Out-String)
}
```

497행을 바꾼다.

```powershell
Check 'python3 이 없으면 안 막는다'             { -not ((Invoke-Guard 'python3 -c "print(1)"' 'absent') -match 'deny') }
```

506행(`Check '앞에 VAR=값 이 붙어도 막는다'`) 아래에 넣는다.

```powershell
# 옛 버전이 상태 파일에 적은 판정이 남아 있어도 가드는 그것을 안 본다.
Check '가드가 상태 파일을 안 읽는다' { (Get-Content $guard -Raw) -notmatch 'kw-control-tower\.state' }
Check '옛 판정 줄이 남아 있어도 주입한 판정을 따른다' {
    'python3=redirector' | Set-Content -LiteralPath (Join-Path $fake2 '.claude\kw-control-tower.state')
    -not ((Invoke-Guard 'python3 -V' 'real') -match 'deny')
}
# 주입 없이 실제 경로를 실행해도 가드가 스스로 실패하지 않는다. 실패하면 자국을 남긴다.
Check '실제 판정 경로가 오류 없이 끝난다' {
    Remove-Item -LiteralPath (Join-Path $fake2 '.claude\kw-control-tower.error') -ErrorAction SilentlyContinue
    $null = Invoke-Guard 'python3 -V' ''
    -not (Test-Path -LiteralPath (Join-Path $fake2 '.claude\kw-control-tower.error'))
}
Check '맞춤이 python3 을 판정하지 않는다' { $syncSrc -notmatch 'fsutil' }
```

「맞춤의 갱신 기록」 절의 `$r = Invoke-SyncScenario -Brief -Up 'fail'` 검사 블록 아래에 넣는다.

```powershell
# 옛 단계 8 이 적은 줄을 맞춤이 지운다. 남기면 읽는 곳이 없는 줄이 상태 파일에 영영 남는다.
$r = Invoke-SyncScenario -State "python3=redirector`npython3Target=C:\x\python3.exe"
Check '맞춤이 옛 python3 판정 줄을 지운다' { $r.State -notmatch '(?m)^python3' }
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: 아래 일곱 검사가 `FAIL` — `맨 앞의 python3 을 막는다`, `파이프 뒤의 python3 은 막는다`, `앞에 VAR=값 이 붙어도 막는다`, `가드가 상태 파일을 안 읽는다`, `옛 판정 줄이 남아 있어도 주입한 판정을 따른다`, `맞춤이 python3 을 판정하지 않는다`, `맞춤이 옛 python3 판정 줄을 지운다`

- [ ] **Step 3: 가드를 바꾼다**

`python3-guard.ps1` 8–10행 주석을 아래로 바꾼다.

```powershell
# 판정은 호출할 때 한다. hooks.json 의 if 가 python3 으로 시작하는 명령에서만 이 훅을 실행하므로
# fsutil 값(이 PC 에서 48밀리초)은 그 명령에만 든다. 맞춤이 적어 둔 값을 읽으면, 맞춤이 불일치한
# 단계만 실행하게 된 뒤로 판정을 적던 단계가 거의 실행되지 않아 판정이 굳는다.
```

18행(`try { [Console]::OutputEncoding ...`) 아래에 함수를 넣는다. 파싱은 옛 맞춤 단계 8 과 같다.

```powershell

function Get-Python3Verdict {
    # 검사가 판정을 주입한다. 실제 PC 의 python3 에 기대면 PC 마다 결과가 달라진다.
    if ($env:KWCT_PYTHON3_PROBE) {
        return @{ Kind = $env:KWCT_PYTHON3_PROBE; Target = 'C:\stub\AppInstallerPythonRedirector.exe' }
    }
    $c = Get-Command python3 -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $c) { return @{ Kind = 'absent'; Target = '' } }
    $src = $c.Source
    $item = Get-Item -LiteralPath $src -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -eq 0) { return @{ Kind = 'real'; Target = $src } }
    # 재지정 버퍼 안에 링크가 가리키는 실물의 경로가 UTF-16 으로 들어 있다.
    $dump = (& fsutil.exe reparsepoint query $src 2>&1 | Out-String)
    $bytes = New-Object System.Collections.Generic.List[byte]
    foreach ($line in ($dump -split "`n")) {
        if ($line -notmatch '^\s*[0-9a-fA-F]{4}:\s') { continue }
        $body = ($line -replace '^\s*[0-9a-fA-F]{4}:\s+', '')
        $hexPart = $body.Substring(0, [Math]::Min(48, $body.Length))
        foreach ($m in [regex]::Matches($hexPart, '\b[0-9a-fA-F]{2}\b')) { $bytes.Add([Convert]::ToByte($m.Value, 16)) }
    }
    $text = [System.Text.Encoding]::Unicode.GetString($bytes.ToArray())
    $exe = ($text -split "`0" | Where-Object { $_ -match '\.exe$' } | Select-Object -Last 1)
    $target = if ($exe) { $exe.Trim() } else { '' }
    # 경로에 WindowsApps 가 들었는지로 가르지 않는다. 스토어로 깐 진짜 파이썬도 거기 놓인다.
    $kind = if ($text -match 'AppInstallerPythonRedirector') { 'redirector' } else { 'real' }
    return @{ Kind = $kind; Target = $target }
}
```

24–33행(상태 파일을 읽는 줄부터 `if ($verdict -ne 'redirector') { exit 0 }` 까지)을 바꾼다.

```powershell
    $verdict = Get-Python3Verdict
    if ($verdict.Kind -ne 'redirector') { exit 0 }   # 파이썬으로 풀리거나 없다
    $target = $verdict.Target
```

- [ ] **Step 4: 맞춤에서 단계 8 을 없앤다**

`sync.ps1` 786–829행(`# ---...--- 단계 8` 부터 그 단계의 `Save-State` 까지)을 지운다. 226행 `$firstRun = ...` 아래에 넣는다.

```powershell
# 옛 버전의 단계 8 이 적던 python3 판정이다. 가드가 호출할 때 직접 판정하므로 남은 줄을 지운다.
$state.Remove('python3'); $state.Remove('python3Target')
```

- [ ] **Step 5: 설계 문서와 README 의 단계 수를 맞춘다**

`docs/superpowers/specs/2026-09-06-control-tower-design.md`:
- 325행 `단계 여덟이고` → `단계 일곱이고`
- 334행(`8. **\`python3\`이 무엇으로 풀리는지 재서 상태 파일에 적는다.**…`)을 지운다.
- 301행 문단을 아래로 바꾼다.

```markdown
**가드가 호출할 때 판정한다(2026-09-30 변경).** `python3`이 무엇으로 풀리는지 알려면 링크가 가리키는 실물을 읽어야 하고 그것이 이 PC에서 48밀리초다. `if` 규칙이 `python3`으로 시작하는 호출에서만 가드를 실행하므로 그 값은 그 호출에만 든다. 처음에는 맞춤의 단계 8이 한 번 측정해 상태 파일에 적고 가드가 그 한 줄을 읽었다. 맞춤이 불일치한 단계만 실행하게 되면 단계 8이 거의 실행되지 않아 판정이 굳으므로 옮겼다.
```

`README.md` 59–62행을 바꾼다.

```markdown
**불일치가 있으면 즉시 맞춘다.** 단계가 일곱이고 저마다 독립이라 하나가 실패해도 나머지는
실행된다. 배포처 등록과 사본 받아오기, 필수 플러그인 설치와 되켜기와 뒤처진 설치본 옮기기,
더 안 쓰는 것 정리, 파이썬 라이브러리, `PYTHONUTF8`, `CLAUDE.md`의 사내 문안, 옛 스킬
사본과 훅 연결 정리다.
```

- [ ] **Step 6: 통과를 확인한다**

Run: 검사 넷
Expected: 모두 실패 없음. `맞춤의 단계 번호가 1부터 빠짐없이 이어진다`·`설계 문서가 코드와 같은 수로 센다`·`README 가 코드와 같은 수로 센다` 가 7 로 통과한다.

- [ ] **Step 7: 커밋한다**

```bash
git add plugins/kw-control-tower/hooks/python3-guard.ps1 plugins/kw-control-tower/scripts/sync.ps1 docs/superpowers/specs/2026-09-06-control-tower-design.md README.md tests/test_control_tower.ps1
git commit -m "fix: python3 가드가 호출할 때 판정하고 맞춤의 단계 8 을 없앤다"
```

---

### Task 4: PYTHONUTF8 이 비어 있으면 1 을 넣는다

**Files:**
- Modify: `plugins/kw-control-tower/scripts/sync.ps1` (단계 5, 헬퍼 함수 구역)
- Modify: `docs/superpowers/specs/2026-09-06-control-tower-design.md:331`
- Test: `tests/test_control_tower.ps1` (「맞춤의 미리보기」 절)

**Interfaces:**
- Produces: `Resolve-Utf8Action([string]$Current) -> 'set' | 'keep' | 'fail'`

- [ ] **Step 1: 실패하는 검사를 넣는다**

「맞춤의 미리보기」 절 끝(`삭제 판정이 세 조건을 함께 본다` 아래)에 넣는다.

```powershell
# 파이썬의 기본 인코딩으로 정하던 때에는 판정식 sys.getdefaultencoding() 이 파이썬 3 에서
# 언제나 utf-8 이라 한 번도 넣지 못했다. 감지와 같은 규칙으로 비어 있으면 넣는다.
Check 'PYTHONUTF8 이 비어 있으면 넣고 0 과 1 은 그대로 둔다' {
    $ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $plugin 'scripts\sync.ps1'), [ref]$null, [ref]$null)
    $fn  = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Resolve-Utf8Action' }, $true)
    if ($null -eq $fn) { return $false }
    . ([scriptblock]::Create($fn.Extent.Text))
    ((Resolve-Utf8Action $null) -eq 'set') -and ((Resolve-Utf8Action '') -eq 'set') -and
    ((Resolve-Utf8Action '1') -eq 'keep') -and ((Resolve-Utf8Action '0') -eq 'keep') -and
    ((Resolve-Utf8Action 'x') -eq 'fail')
}
Check '맞춤이 파이썬 기본 인코딩으로 판정하지 않는다' { $syncSrc -notmatch 'getdefaultencoding' }
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: `PYTHONUTF8 이 비어 있으면 넣고 0 과 1 은 그대로 둔다` 와 `맞춤이 파이썬 기본 인코딩으로 판정하지 않는다` 가 `FAIL`

- [ ] **Step 3: 구현한다**

`sync.ps1` 의 `function Invoke-Claude` 정의 바로 위에 넣는다.

```powershell
function Resolve-Utf8Action([string]$Current) {
    # 비어 있으면 넣는다. 1 이면 할 일이 없고, 0 은 사용자가 끈 것이라 그대로 둔다.
    if ([string]::IsNullOrEmpty($Current)) { return 'set' }
    if ($Current -eq '1' -or $Current -eq '0') { return 'keep' }
    return 'fail'
}
```

단계 5 의 `try { ... } catch { Fail '5' ... }` 전체를 바꾼다(`Show '5. ...'` 줄과 끝의 `Save-State` 는 그대로).

```powershell
try {
    # 감지가 "비어 있다" 로 불일치를 내므로 같은 규칙이어야 알림이 멈춘다.
    $now = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'User')
    switch (Resolve-Utf8Action $now) {
        'set'  {
            if (-not $WhatIfOnly) { [Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'User') }
            Note 'PYTHONUTF8 을 1 로 설정했습니다.'
        }
        'keep' { Say "이미 $now 입니다. 그대로 둡니다." }
        'fail' { Fail '5' "값이 '$now' 입니다. 손으로 1 이나 0 으로 고쳐 주십시오." }
    }
} catch { Fail '5' $_.Exception.Message }
```

설계 문서 331행을 바꾼다.

```markdown
5. **`PYTHONUTF8`이 비어 있으면 1을 넣는다.** 0은 사용자가 끈 것이라 그대로 둔다. 파이썬의 기본 인코딩을 측정해 정하던 때에는 판정식이 늘 utf-8을 돌려줘 한 번도 넣지 못했다(2026-09-30).
```

- [ ] **Step 4: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-control-tower/scripts/sync.ps1 docs/superpowers/specs/2026-09-06-control-tower-design.md tests/test_control_tower.ps1
git commit -m "fix: 맞춤이 PYTHONUTF8 이 비어 있으면 1 을 넣는다"
```

---

### Task 5: 감지가 불일치한 단계만 맞춤에 넘긴다

**Files:**
- Modify: `plugins/kw-control-tower/hooks/session-check.ps1` (불일치를 적는 곳 전부, 상태 파일 읽는 곳 셋, 맞춤 호출 575행)
- Modify: `plugins/kw-control-tower/scripts/sync.ps1` (param, 단계 1–7 머리)
- Modify: `docs/superpowers/specs/2026-09-06-control-tower-design.md:325`
- Test: `tests/test_control_tower.ps1`

**Interfaces:**
- Produces (감지): `Add-Note([int[]]$Step, [string]$Text)` — `$notes`(문자열)와 `$noteSteps`(int 배열의 목록)에 같은 순서로 넣는다. `Read-KwState([string]$Path) -> hashtable` — 상태 파일을 한 번 읽는다. 감지 전역 `$kwState`.
- Produces (맞춤): 매개변수 `-Steps "1,2,6"`. 넘겼는데 비어 있으면 아무 단계도 실행하지 않고, 넘기지 않으면(설치기) 모두 실행한다. `Want([int]$n) -> bool`. 전역 `$script:Ran`(실행한 단계 번호 목록), `$script:Current`(지금 단계 번호).

단계 번호 대응은 아래와 같다.

| 감지의 불일치 | 단계 |
|---|---|
| 필수 플러그인 미설치·꺼짐 | 2 |
| 더 안 쓰는 플러그인·배포처 | 3 |
| 자동 갱신 꺼짐·배포처 등록 없음 | 1 |
| 파이썬 라이브러리 목록 | 4 |
| PYTHONUTF8 | 5 |
| 사내 문안 사본·블록 | 6 |
| 더 안 쓰는 스킬·훅 | 7 |
| 설치본 뒤처짐 | 1, 2 |
| 배포처 사본 오래됨 | 1 |

- [ ] **Step 1: 실패하는 검사를 넣는다**

984–990행 `$syncStub` 의 첫 줄 `param(...)` 을 바꾼다. 훅이 넘기는 인자를 스텁이 이름으로 받게 한다. 받지 않으면 값이 `$args` 로 흘러 스텁이 인자를 쓸 수 없다.

```powershell
param([switch]$Brief, [switch]$WhatIfOnly, [string]$Steps, [int]$BudgetSeconds)
```

1010행(`맞춤을 부르면 짧은 결과만 ...` 검사) 아래에 넣는다.

```powershell
# 감지는 무엇이 다른지 안다. 그것을 넘기지 않으면 불일치 하나에 모든 단계가 실행된다.
$stepsStub = @'
param([switch]$Brief, [switch]$WhatIfOnly, [string]$Steps, [int]$BudgetSeconds)
Write-Host 'kw-control-tower: 사내 설정을 맞췄습니다.'
Write-Host "  - steps=$Steps budget=$BudgetSeconds"
'@
Check '감지가 불일치한 단계만 맞춤에 넘긴다' {
    $o = Invoke-Scenario -Installed $shaOld -Remote $shaNew -Sync $stepsStub -Leaf 'a1a1a1a1a1a1'
    $m = [regex]::Match($o, 'steps=([\d,]+)')
    $got = if ($m.Success) { @($m.Groups[1].Value.Split(',') | ForEach-Object { [int]$_ }) } else { @() }
    # 가짜 홈은 뒤처짐(1,2)과 필수 미설치(2)와 kw-ax 사본 없음(6)을 늘 갖고, 옛 스킬·훅(7)은 없다.
    ($got -contains 1) -and ($got -contains 2) -and ($got -contains 6) -and ($got -notcontains 7)
}
# 불일치를 적는 곳이 하나라도 Add-Note 를 거치지 않으면 단계 번호가 빠져 그 불일치를 맞추지 못한다.
Check '감지의 불일치는 모두 단계 번호와 함께 적힌다' { @([regex]::Matches($hookCode, '\$notes\.Add\(')).Count -eq 1 }
```

「맞춤의 갱신 기록」 절의 claude 스텁(1025–1042행) 맨 앞에 호출 기록을 넣는다.

```powershell
if ($env:STUB_LOG) { Add-Content -LiteralPath $env:STUB_LOG -Value ($args -join ' ') }
```

`Invoke-SyncScenario`(1050행)의 `param` 에 `[string]$Steps = ''` 를 추가하고, 1071행 환경 변수 줄 끝에 `$env:STUB_LOG = Join-Path $h 'calls.log'` 를 추가한다. 1072행 명령 끝의 `$(if ($Brief) { '-Brief' })` 를 아래로 바꾼다.

```powershell
$(if ($Brief) { '-Brief' }) $(if ($Steps) { "-Steps '$Steps'" })
```

1074행 정리 목록에 `'STUB_LOG'` 를 추가하고, 돌려주는 해시에 한 줄을 추가한다.

```powershell
        Calls = $(if (Test-Path -LiteralPath (Join-Path $h 'calls.log')) { Get-Content -LiteralPath (Join-Path $h 'calls.log') -Raw } else { '' })
```

1123행 아래에 넣는다. 부정 검사는 맞춤이 실제로 실행되었는지까지 본다. 맞춤이 인자 오류로 아예 실행되지 않아도 설치본은 그대로이기 때문이다.

```powershell
$r = Invoke-SyncScenario -Steps '6'
Check '넘겨받은 단계가 아니면 돌지 않는다' {
    ($r.Sha -eq $shaOld) -and [string]::IsNullOrWhiteSpace($r.Calls) -and ($r.Out -match '넘겨받은 불일치가 없어 넘어갑니다')
}
$r = Invoke-SyncScenario -Steps '1,2'
Check '넘겨받은 단계는 돈다' { $r.Sha -eq $shaNew }
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: 아래 네 검사가 `FAIL` — `감지가 불일치한 단계만 맞춤에 넘긴다`, `감지의 불일치는 모두 단계 번호와 함께 적힌다`, `넘겨받은 단계가 아니면 돌지 않는다`, `넘겨받은 단계는 돈다`. 지금 `sync.ps1` 은 `[CmdletBinding()]` 이라 모르는 `-Steps` 를 받으면 본문을 실행하지 않는다.

- [ ] **Step 3: 맞춤에 단계 선택을 넣는다**

`sync.ps1` param 블록 끝에 한 줄을 추가한다.

```powershell
    [switch]$Brief,
    # 세션 시작 훅이 불일치한 단계 번호를 쉼표로 넘긴다. 넘기지 않으면(설치기) 모두 실행한다.
    [string]$Steps = ''
```

`$script:Covered` 선언(34행) 아래에 넣는다.

```powershell
# 넘겼는데 비어 있으면 실행할 단계가 없다. 넘기지 않은 것과 구분해, 감지가 번호를 빠뜨린 불일치 하나가
# 모든 단계를 실행하게 만들지 않는다.
$script:StepsGiven = $PSBoundParameters.ContainsKey('Steps')
$script:Want = @($Steps.Split(',') | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ })
$script:Ran = New-Object System.Collections.ArrayList   # 이번 실행에서 실행한 단계
$script:Current = 0                                      # 지금 실행 중인 단계
```

`function Resolve-Utf8Action` 위에 넣는다.

```powershell
function Want([int]$n) {
    # 넘겨받은 단계만 실행한다. 넘겨받지 않았으면 모두 실행한다.
    if ($script:StepsGiven -and $script:Want -notcontains $n) { return $false }
    [void]$script:Ran.Add($n)
    $script:Current = $n
    return $true
}
```

단계 1–7 마다 `Show 'N. …'` 줄 바로 아래에 `if (Want N) {` 를 넣고, 그 단계의 마지막 `Save-State` 바로 위에 아래 줄을 넣는다. 안쪽 줄의 들여쓰기는 바꾸지 않는다. 검사가 `^Show` 와 `^Save-State` 를 줄 머리에서 찾기 때문이다.

```powershell
} else { Say '넘겨받은 불일치가 없어 넘어갑니다.' }
```

단계 1 은 `if ($script:Refreshed) { $state['refreshed'] = ... }` 줄까지 `if` 안에 든다.

- [ ] **Step 4: 감지가 단계를 붙여 넘긴다**

`session-check.ps1` 의 `function Get-MarketplaceHead` 위에 넣는다.

```powershell
function Read-KwState([string]$Path) {
    # 상태 파일을 한 번만 읽는다. 질문마다 따로 열던 때에는 같은 파일을 세 번 열었다.
    $s = @{}
    $script:Budget.Files++
    if (Test-Path -LiteralPath $Path) {
        foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
            $i = $line.IndexOf('=')
            if ($i -gt 0) { $s[$line.Substring(0, $i)] = $line.Substring($i + 1) }
        }
    }
    return $s
}
```

158행 `$notes = ...` 아래에 넣는다.

```powershell
$noteSteps = New-Object System.Collections.ArrayList   # $notes 와 같은 순서로 맞춤 단계 번호
function Add-Note([int[]]$Step, [string]$Text) {
    [void]$notes.Add($Text)
    [void]$noteSteps.Add($Step)
}
```

186행 `$known = Read-Json ...` 아래에 넣는다.

```powershell
    $kwState = Read-KwState (Join-Path $cfg 'kw-control-tower.state')
```

불일치를 적는 곳을 아래 표대로 바꾼다. 왼쪽이 지금 코드, 오른쪽이 바꾼 코드다.

| 지금 코드(앞머리) | 바꾼 코드 |
|---|---|
| `[void]$notes.Add("필수 플러그인이 안 깔려 있습니다: …")` | `Add-Note 2 "필수 플러그인이 안 깔려 있습니다: $($missing -join ', ')"` |
| `[void]$notes.Add("필수 플러그인이 꺼져 있습니다: …")` | `Add-Note 2 "필수 플러그인이 꺼져 있습니다: $($disabled -join ', ')"` |
| `[void]$notes.Add("더 안 쓰는 플러그인이 남아 있습니다: …")` | `Add-Note 3 "더 안 쓰는 플러그인이 남아 있습니다: $($staleP -join ', ')"` |
| `[void]$notes.Add("더 안 쓰는 배포처가 남아 있습니다: …")` | `Add-Note 3 "더 안 쓰는 배포처가 남아 있습니다: $($staleM -join ', ')"` |
| `[void]$notes.Add("자동 갱신이 꺼져 있습니다: …")` | `Add-Note 1 "자동 갱신이 꺼져 있습니다: $($offAuto -join ', ')"` |
| `[void]$notes.Add('파이썬 라이브러리 목록이 …')` | `Add-Note 4 '파이썬 라이브러리 목록이 이 PC에 맞춰진 것과 다릅니다.'` |
| `[void]$notes.Add('PYTHONUTF8 이 설정되어 있지 않습니다. …')` | `Add-Note 5 'PYTHONUTF8 이 설정되어 있지 않습니다. 한글이 깨질 수 있습니다.'` |
| `[void]$notes.Add("CLAUDE.md 가 싣는 사내 문안 사본이 …")` | `Add-Note 6 "CLAUDE.md 가 싣는 사내 문안 사본이 없거나 배포된 것과 다릅니다: $($stale -join ', ')"` |
| `[void]$notes.Add('CLAUDE.md 에 사내 문안 블록이 없습니다.')` | `Add-Note 6 'CLAUDE.md 에 사내 문안 블록이 없습니다.'` |
| `[void]$notes.Add("CLAUDE.md 에 사내 문안 블록이 $howMany 개 있습니다.")` | `Add-Note 6 "CLAUDE.md 에 사내 문안 블록이 $howMany 개 있습니다."` |
| `[void]$notes.Add('CLAUDE.md 의 사내 문안 블록이 배포된 것과 다릅니다.')` | `Add-Note 6 'CLAUDE.md 의 사내 문안 블록이 배포된 것과 다릅니다.'` |
| `[void]$notes.Add("더 안 쓰는 스킬 사본이 남아 있습니다: …")` | `Add-Note 7 "더 안 쓰는 스킬 사본이 남아 있습니다: $($staleS -join ', ')"` |
| `[void]$notes.Add("더 안 쓰는 훅 연결이 남아 있습니다: …")` | `Add-Note 7 "더 안 쓰는 훅 연결이 남아 있습니다: $($staleH -join ', ')"` |
| `[void]$notes.Add("설치본이 원격보다 뒤처져 있습니다: …")` | `Add-Note @(1, 2) "설치본이 원격보다 뒤처져 있습니다: $(($behind \| Select-Object -Unique) -join ', ')"` |
| `[void]$notes.Add('배포처 사본을 열나흘 넘게 받아오지 않았습니다.')` | `Add-Note 1 '배포처 사본을 열나흘 넘게 받아오지 않았습니다.'` |

상태 파일을 여는 세 블록을 `$kwState` 조회로 바꾼다. 질문 6 의 `$was` 를 읽는 블록은 아래로 바꾼다.

```powershell
        $was = $kwState['requirements']
```

질문 11 의 `$stuckOf` 를 채우는 블록(`$stuckOf = @{}` 부터 그 `if` 블록 끝까지)을 지우고, `$stuckOf[$mkName]` 을 `$kwState["stuck-$mkName"]` 으로 바꾼다. 질문 12 의 `$refreshed` 를 읽는 블록은 아래로 바꾼다.

```powershell
    $refreshed = $kwState['refreshed']
```

세 블록 앞의 `$script:Budget.Files++` 도 지운다(`Read-KwState` 가 한 번 센다). `$stateFile` 변수는 쓰는 곳이 없어지면 지운다.

575행 맞춤 호출을 바꾼다.

```powershell
    $runSteps = @($noteSteps | ForEach-Object { $_ } | Sort-Object -Unique)
    $out = & pwsh -NoProfile -NonInteractive -File $sync -Brief -Steps ($runSteps -join ',') 2>&1
```

`「못 옮긴 원격 커밋을 맞춤이 적고 알림이 읽는다」` 검사(872–876행)의 `($hookCode -match "'\^stuck-")` 를 `($hookCode -match 'stuck-\$mkName')` 로 바꾼다. 조회 방식이 바뀌었기 때문이다.

설계 문서 325행 문장 뒤에 한 문장을 추가한다.

```markdown
세션 시작 훅은 불일치마다 단계 번호를 붙여 그 단계만 넘기고, 설치기는 인자 없이 호출해 모든 단계를 실행한다(2026-09-30).
```

- [ ] **Step 5: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 6: 커밋한다**

```bash
git add plugins/kw-control-tower/hooks/session-check.ps1 plugins/kw-control-tower/scripts/sync.ps1 docs/superpowers/specs/2026-09-06-control-tower-design.md tests/test_control_tower.ps1
git commit -m "feat: 감지가 불일치한 단계만 맞춤에 넘기고 상태 파일을 한 번만 읽는다"
```

---

### Task 6: 라이브러리 목록이 같으면 pip 을 호출하지 않는다

**Files:**
- Modify: `plugins/kw-control-tower/scripts/sync.ps1` (단계 4)
- Test: `tests/test_control_tower.ps1` (「맞춤의 미리보기」 절)

**Interfaces:**
- Consumes: Task 5 의 `if (Want 4) {` 머리.

- [ ] **Step 1: 실패하는 검사를 넣는다**

```powershell
# 감지는 목록 해시로 판정한다. 맞춤도 해시가 같으면 pip 을 호출하지 않는다. 설치기가 모든 단계를
# 실행할 때 사내 프록시를 거치는 pip 이 그때마다 실행되던 것을 없앤다.
Check '라이브러리 목록이 같으면 pip 을 안 부른다' {
    $b = [regex]::Match($syncSrc, "(?s)Show '4\..*?(?=Show '5\.)").Value
    $gate = $b.IndexOf("`$state['requirements'] -eq `$newHash")
    ($gate -ge 0) -and ($gate -lt $b.IndexOf('pip install'))
}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: `라이브러리 목록이 같으면 pip 을 안 부른다` 가 `FAIL`

- [ ] **Step 3: 구현한다**

단계 4 의 `if (Want 4) {` 안쪽 `try { ... } catch { Fail '4' ... }` 를 바꾼다.

```powershell
try {
    $req = Join-Path $root 'requirements.txt'
    if (-not (Test-Path -LiteralPath $req)) { throw "라이브러리 목록이 없습니다: $req" }
    $newHash = Get-CheapHash $req
    if ($state['requirements'] -eq $newHash) {
        # 지난번에 이 목록으로 깔았다. 감지도 같은 해시로 판정한다.
        Say '이미 목록과 같습니다.'
    } else {
        $py = (Get-Command python -ErrorAction SilentlyContinue)
        if ($null -eq $py) { throw '파이썬을 못 찾았습니다. python 이 PATH 에 있어야 합니다.' }
        if ($WhatIfOnly) {
            Say "[미리보기] $($py.Source) -m pip install -r $req"
        } else {
            # pip 은 이미 깔린 것마다 한 줄씩 출력해 요약을 파묻는다. 조용히 실행하고 실패했을 때만 보여 준다.
            $pipOut = & $py.Source -m pip install --quiet --disable-pip-version-check -r $req 2>&1
            if ($LASTEXITCODE -ne 0) {
                foreach ($l in $pipOut) { Say $l }
                throw "pip 이 코드 $LASTEXITCODE 로 끝났습니다."
            }
            Note '파이썬 라이브러리를 목록에 맞췄습니다.'
            $state['requirements'] = $newHash
        }
    }
} catch { Fail '4' $_.Exception.Message }
```

- [ ] **Step 4: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음. `단계마다 상태를 고친 뒤에 적는다` 도 통과해야 한다.

- [ ] **Step 5: 커밋한다**

```bash
git add plugins/kw-control-tower/scripts/sync.ps1 tests/test_control_tower.ps1
git commit -m "perf: 라이브러리 목록이 지난번과 같으면 pip 을 호출하지 않는다"
```

---

### Task 7: CLAUDE.md 가 싣는 사본만 복사하고 대조한다

**Files:**
- Modify: `plugins/kw-control-tower/hooks/session-check.ps1` (질문 8, 296–312행)
- Modify: `plugins/kw-control-tower/scripts/sync.ps1` (단계 6, 578–597행)
- Test: `tests/test_control_tower.ps1` (「문안 조립」 절)

**Interfaces:**
- Consumes: Task 5 의 `Add-Note`.
- Produces: 두 파일에 같은 `Get-AxCopies([string]$claudeMd) -> string[]` — `kw-ax` 로 복사하고 대조할 템플릿 파일 이름.

- [ ] **Step 1: 실패하는 검사를 넣는다**

「문안 조립」 절의 `foreach ($pair in ...)` 반복 안, `Check "$($pair.Name): @import 경로에 공백이 없다"` 아래에 넣는다.

```powershell
    $fc = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-AxCopies' }, $true)
    Check "$($pair.Name)에 Get-AxCopies 가 있다" { $null -ne $fc }
    if ($null -ne $fc) {
        . ([scriptblock]::Create($fc.Extent.Text))
        $cw = @(Get-AxCopies "앞`n# BEGIN disciplined-coder (managed — do not edit)`n@x`n# END disciplined-coder (managed — do not edit)`n")
        $co = @(Get-AxCopies "앞`n")
        $assembled["$($pair.Name)-copies"] = "$($cw -join ',')|$($co -join ',')"
        Check "$($pair.Name): disciplined-coder 가 있으면 사내 문안 사본 하나만 다룬다" { ($cw -join ',') -eq 'claude-md-ko.md' }
        Check "$($pair.Name): 블록이 싣는 파일이 모두 사본 목록에 있다" {
            $refs = @([regex]::Matches($without, '(?m)^@kw-ax/(\S+)$') | ForEach-Object { $_.Groups[1].Value })
            @($refs | Where-Object { $co -notcontains $_ }).Count -eq 0
        }
        Check "$($pair.Name): 원칙이 근거로 가리키는 사본도 다룬다" { $co -contains 'domain-korean_subset.md' }
    }
```

반복 뒤 `Check '맞춤과 훅이 같은 블록을 조립한다'` 아래에 넣는다.

```powershell
Check '맞춤과 훅이 같은 사본 목록을 쓴다' { $assembled['맞춤-copies'] -eq $assembled['훅-copies'] }
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: `맞춤에 Get-AxCopies 가 있다`, `훅에 Get-AxCopies 가 있다`, `맞춤과 훅이 같은 사본 목록을 쓴다` 가 `FAIL`

- [ ] **Step 3: 두 파일에 같은 함수를 넣는다**

`session-check.ps1` 과 `sync.ps1` 의 `function Get-AxBlock` 바로 아래에 똑같이 넣는다.

```powershell
# kw-ax 로 복사하고 대조할 템플릿이다. 블록이 싣는 파일과, 원칙이 근거로 가리키는 사본이다.
# 블록이 안 싣는 파일까지 대조하면 싣지도 않는 사본 하나 때문에 맞춤이 실행된다(2026-09-30 이 PC).
# 알림 훅에도 같은 함수가 있다. 둘이 다르면 맞춤이 복사한 것을 훅이 다르다고 알린다.
function Get-AxCopies([string]$claudeMd) {
    $files = @('claude-md-ko.md')
    if ($claudeMd -notmatch '(?m)^#\s*BEGIN disciplined-coder\b') {
        $files += @('claude-md-ko-principles.md', 'korean-banned-words.md', 'domain-korean_subset.md')
    }
    return $files
}
```

- [ ] **Step 4: 감지 질문 8 이 사본 목록만 대조한다**

`session-check.ps1` 의 질문 8 에서 `if (Test-Path -LiteralPath $tpl) { $stale = … }` 블록을 바꾼다(`$tpl`·`$mem`·`$u8` 선언은 그대로).

```powershell
    $memText = if (Test-Path -LiteralPath $mem) { [System.IO.File]::ReadAllText($mem, $u8) } else { '' }
    if (Test-Path -LiteralPath $tpl) {
        $stale = New-Object System.Collections.ArrayList
        $tplDir = Split-Path -Parent $tpl
        foreach ($name in @(Get-AxCopies $memText)) {
            $src  = Join-Path $tplDir $name
            $copy = Join-Path (Join-Path $cfg 'kw-ax') $name
            $script:Budget.Files += 2
            if (-not (Test-Path -LiteralPath $src)) { continue }
            if (-not (Test-Path -LiteralPath $copy) -or
                ([System.IO.File]::ReadAllText($copy, $u8) -ne [System.IO.File]::ReadAllText($src, $u8))) {
                [void]$stale.Add($name)
            }
        }
        if ($stale.Count -gt 0) {
            Add-Note 6 "CLAUDE.md 가 싣는 사내 문안 사본이 없거나 배포된 것과 다릅니다: $($stale -join ', ')"
        }
    }
```

바로 뒤 블록의 `$now = [System.IO.File]::ReadAllText($mem, $u8)` 는 `$now = $memText` 로 바꾼다.

- [ ] **Step 5: 맞춤 단계 6 이 사본 목록만 복사한다**

`sync.ps1` 단계 6 에서 `$target = Join-Path $userHome '.claude\CLAUDE.md'` 줄을 `$axDir = ...` 위로 옮기고, `foreach ($t in @(Get-ChildItem -LiteralPath $tplDir -Filter '*.md' -File))` 반복을 바꾼다. 반복 위의 주석(「템플릿은 모두 복사한다…」 세 줄)은 아래 첫 줄로 바꾼다.

```powershell
    # 블록이 싣는 파일과 원칙이 가리키는 근거 사본만 복사한다. 훅도 Get-AxCopies 로 같은 목록을 대조한다.
    $mdNow = if (Test-Path -LiteralPath $target) { [System.IO.File]::ReadAllText($target, $utf8) } else { '' }
    foreach ($name in @(Get-AxCopies $mdNow)) {
        $src  = Join-Path $tplDir $name
        if (-not (Test-Path -LiteralPath $src)) { continue }
        $copy = Join-Path $axDir $name
        $same = (Test-Path -LiteralPath $copy) -and
                ([System.IO.File]::ReadAllText($copy, $utf8) -eq [System.IO.File]::ReadAllText($src, $utf8))
        if ($same) { continue }
        if ($WhatIfOnly) { Say "[미리보기] $copy 를 템플릿으로 바꿉니다."; continue }
        Copy-Item -LiteralPath $src -Destination $copy -Force
        Note "$copy 를 템플릿으로 바꿨습니다."
    }
```

`$utf8` 선언(`$utf8 = New-Object System.Text.UTF8Encoding($false)`)이 이 반복보다 앞에 있는지 확인한다.

- [ ] **Step 6: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음. `맞춤이 블록을 쓰기 전에 템플릿을 kw-ax 로 복사한다` 와 `훅이 kw-ax 사본을 템플릿과 대조한다` 도 통과해야 한다.

- [ ] **Step 7: 커밋한다**

```bash
git add plugins/kw-control-tower/hooks/session-check.ps1 plugins/kw-control-tower/scripts/sync.ps1 tests/test_control_tower.ps1
git commit -m "fix: CLAUDE.md 가 싣는 사내 문안 사본만 복사하고 대조한다"
```

---

### Task 8: 맞춤에 시간 상한을 둔다

**Files:**
- Modify: `plugins/kw-control-tower/scripts/sync.ps1` (param, `Invoke-Claude`, `Want`, 마무리)
- Modify: `plugins/kw-control-tower/hooks/session-check.ps1` (맞춤 호출)
- Test: `tests/test_control_tower.ps1` (「맞춤의 갱신 기록」 절, `클로드를 이름이 아니라…` 검사 367–371행)

**Interfaces:**
- Consumes: Task 5 의 `Want`, `$script:Current`, `-Steps`.
- Produces: 매개변수 `-BudgetSeconds <int>`(0 이면 상한 없음). `Get-Remaining -> int`(남은 초). `$script:Margin`(단계를 새로 시작할 때 남아 있어야 하는 초). `$script:Deferred`(미룬 단계 목록), `$script:TimedOutSteps`(상한에 끊긴 호출이 있던 단계 목록). 테스트 전역 `$hang`(끝나지 않는 `claude.cmd` 폴더), `$hangRun`(끊김 시나리오 결과).

상한은 `claude` 호출과 단계 시작에서 확인한다. pip 과 `CLAUDE.md` 잠금 대기는 중간에 끊을 수 없으므로, 단계는 남은 시간이 `$script:Margin`(상한의 3분의 1, 최대 20초) 이상일 때만 새로 시작한다. 훅은 상한 60초를 넘기므로 그 단계들이 쓸 수 있는 여유가 20초 남는다.

- [ ] **Step 1: 실패하는 검사를 넣는다**

367–371행 검사를 바꾼다. 호출 방식이 `&` 에서 프로세스 시작으로 바뀌기 때문이다.

```powershell
Check '클로드를 이름이 아니라 찾아 둔 경로로 부른다' {
    ($syncSrc -match '\$script:ClaudeExe = \(Get-Command claude') -and
    ($syncSrc -match '\$file = \$script:ClaudeExe') -and
    ($syncSrc -notmatch '& claude @ClaudeArgs')
}
```

「맞춤의 갱신 기록」 절의 claude 스텁에서 `marketplace update` 분기 첫 줄에 넣는다.

```powershell
    if ($env:STUB_SLEEP) { Start-Sleep -Seconds ([int]$env:STUB_SLEEP) }
```

`Invoke-SyncScenario` 의 param 에 `[int]$Budget = 0, [int]$Sleep = 0, [string]$Bin = ''` 를 추가한다. 환경 변수 줄에 `$env:STUB_SLEEP = if ($Sleep) { "$Sleep" } else { '' }` 를 추가하고 정리 목록에 `'STUB_SLEEP'` 를 추가한다. 명령에서 PATH 의 첫 항목 `$sy\bin` 을 `$(if ($Bin) { $Bin } else { "$sy\bin" })` 로 바꾸고, 인자 끝에 `$(if ($Budget) { "-BudgetSeconds $Budget" })` 를 추가한다.

Task 5 에서 넣은 검사 아래에 넣는다.

```powershell
# 훅 제한은 90초다. 맞춤이 그것을 넘기면 알림이 사라진다고 보고, 맞춤 스스로 멈추고 남은 단계를 다음
# 세션으로 미룬다. .ps1 스텁은 이 프로세스 안에서 실행되어 한 호출 안에서는 끊지 못한다.
$r = Invoke-SyncScenario -Budget 3 -Sleep 4 -Brief
Check '시간 상한을 넘기면 남은 호출을 하지 않고 다음 세션으로 미룬다' {
    ($r.Sha -eq $shaOld) -and ($r.Out -match '다음 세션으로 미뤘습니다') -and ($r.Calls -notmatch 'plugin update')
}
# 진짜 claude.exe 는 한 호출이 상한을 넘기면 끊는다. 인자와 표준입력에 관계없이 30초를 기다리는
# claude.cmd 를 두고 확인한다. .cmd 는 CreateProcess 가 cmd.exe 로 실행한다.
$hang = Join-Path $sy 'hang'
New-Item -ItemType Directory -Force -Path $hang | Out-Null
'@ping -n 30 127.0.0.1 >nul' | Set-Content -LiteralPath (Join-Path $hang 'claude.cmd') -Encoding ascii
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$hangRun = Invoke-SyncScenario -Budget 3 -Bin $hang -Steps '1'
$sw.Stop()
Check '상한을 넘긴 claude 호출을 끊는다' {
    ($sw.Elapsed.TotalSeconds -lt 20) -and ($hangRun.Out -match '시간 상한에 닿아 멈췄습니다')
}
```

`세션 시작 훅의 예산이 맞춤을 끝낼 만큼이다` 검사 아래에 넣는다.

```powershell
Check '훅이 맞춤에 훅 제한보다 짧은 상한을 넘긴다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $m = [regex]::Match($hookCode, '-BudgetSeconds (\d+)')
    $m.Success -and ([int]$m.Groups[1].Value -lt $j.hooks.SessionStart[0].hooks[0].timeout)
}
# 끊긴 claude 가 표준입력을 기다리지 않게 바로 닫는다.
Check '맞춤이 claude 의 표준입력을 바로 닫는다' { $syncSrc -match '\$p\.StandardInput\.Close\(\)' }
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: 아래 다섯 검사가 `FAIL` — `클로드를 이름이 아니라 찾아 둔 경로로 부른다`, `시간 상한을 넘기면 남은 호출을 하지 않고 다음 세션으로 미룬다`, `상한을 넘긴 claude 호출을 끊는다`, `훅이 맞춤에 훅 제한보다 짧은 상한을 넘긴다`, `맞춤이 claude 의 표준입력을 바로 닫는다`

- [ ] **Step 3: 맞춤에 상한을 넣는다**

param 에 추가한다.

```powershell
    # 세션 시작 훅이 넘긴다. 0 이면 상한이 없다(설치기).
    [int]$BudgetSeconds = 0
```

`$script:Current` 선언 아래에 넣는다.

```powershell
$script:Deadline = if ($BudgetSeconds -gt 0) { (Get-Date).AddSeconds($BudgetSeconds) } else { $null }
# 단계를 새로 시작하려면 남아 있어야 하는 초다. pip 과 CLAUDE.md 잠금 대기는 중간에 끊지 못한다.
$script:Margin = [Math]::Min(20, [int][Math]::Floor($BudgetSeconds / 3))
$script:Deferred = New-Object System.Collections.ArrayList        # 상한에 닿아 미룬 단계
$script:TimedOutSteps = New-Object System.Collections.ArrayList   # 상한에 끊긴 호출이 있던 단계
function Get-Remaining {
    if ($null -eq $script:Deadline) { return [int]::MaxValue }
    return [int][Math]::Floor(($script:Deadline - (Get-Date)).TotalSeconds)
}
```

`Want` 를 바꾼다.

```powershell
function Want([int]$n) {
    # 넘겨받은 단계만 실행한다. 넘겨받지 않았으면 모두 실행한다. 남은 시간이 여유보다 적으면
    # 다음 세션으로 미룬다.
    if ($script:StepsGiven -and $script:Want -notcontains $n) { return $false }
    if ((Get-Remaining) -lt [Math]::Max(1, $script:Margin)) { [void]$script:Deferred.Add($n); return $false }
    [void]$script:Ran.Add($n)
    $script:Current = $n
    return $true
}
```

`Invoke-Claude` 를 바꾼다.

```powershell
function Invoke-Claude {
    # 클로드를 이름으로 호출하지 않고 시작할 때 한 번 찾아 둔 절대 경로로 호출한다.
    # 남은 시간만큼만 기다리고 넘으면 프로세스 트리째 끊는다.
    param([string[]]$ClaudeArgs)
    if ($WhatIfOnly) { Say "[미리보기] claude $($ClaudeArgs -join ' ')"; return $true }
    if (-not $script:ClaudeExe) { throw '클로드 코드를 못 찾았습니다. claude 가 PATH 에 있어야 합니다.' }
    $left = Get-Remaining
    if ($left -le 0) {
        Say "시간 상한에 닿아 실행하지 않았습니다: claude $($ClaudeArgs -join ' ')"
        [void]$script:TimedOutSteps.Add($script:Current)
        return $false
    }
    $file = $script:ClaudeExe
    if ($file -like '*.ps1') {
        # 검사의 스텁이다. 이 프로세스 안에서 실행해 출력과 종료 코드를 그대로 받는다. 한 호출 안에서는 못 끊는다.
        & $file @ClaudeArgs 2>&1 | ForEach-Object { Say $_ }
        return ($LASTEXITCODE -eq 0)
    }
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $file
    foreach ($a in $ClaudeArgs) { $psi.ArgumentList.Add($a) }
    $psi.UseShellExecute = $false
    $psi.RedirectStandardInput  = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $psi.StandardErrorEncoding  = New-Object System.Text.UTF8Encoding($false)
    $p = [System.Diagnostics.Process]::Start($psi)
    $p.StandardInput.Close()   # 입력을 기다리는 명령이 있어도 곧바로 끝을 받게 한다
    $outTask = $p.StandardOutput.ReadToEndAsync()
    $errTask = $p.StandardError.ReadToEndAsync()
    $ms = if ($left -ge 2000000) { -1 } else { $left * 1000 }
    if (-not $p.WaitForExit($ms)) {
        try { $p.Kill($true) } catch { }
        Say "시간 상한에 닿아 멈췄습니다: claude $($ClaudeArgs -join ' ')"
        [void]$script:TimedOutSteps.Add($script:Current)
        return $false
    }
    foreach ($l in (($outTask.Result + "`n" + $errTask.Result) -split "`r?`n")) { if ($l) { Say $l } }
    return ($p.ExitCode -eq 0)
}
```

마무리의 `if ($script:UpdateFailed.Count -gt 0) {` 블록 바로 위에 넣는다.

```powershell
if ($script:Deferred.Count -gt 0) {
    Write-Host "kw-control-tower: 시간 상한에 닿아 단계 $(($script:Deferred | Sort-Object -Unique) -join ', ') 는 다음 세션으로 미뤘습니다." -ForegroundColor Yellow
}
```

- [ ] **Step 4: 훅이 상한을 넘긴다**

`session-check.ps1` 의 맞춤 호출 줄 끝에 `-BudgetSeconds 60` 을 추가한다.

```powershell
    $out = & pwsh -NoProfile -NonInteractive -File $sync -Brief -Steps ($runSteps -join ',') -BudgetSeconds 60 2>&1
```

- [ ] **Step 5: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 6: 커밋한다**

```bash
git add plugins/kw-control-tower/scripts/sync.ps1 plugins/kw-control-tower/hooks/session-check.ps1 tests/test_control_tower.ps1
git commit -m "feat: 맞춤이 시간 상한을 넘기면 claude 호출을 끊고 남은 단계를 미룬다"
```

---

### Task 9: 같은 원인으로 실패한 단계는 다시 호출하지 않는다

실패한 단계와 상한에 끊긴 단계에 지문을 적는다. 끊긴 단계도 적는 이유는, 매번 상한을 넘기는 단계를 적지 않으면 켤 때마다 약 60초가 되풀이되고 그 뒤 번호의 단계는 영영 미뤄지기 때문이다. 지문에 날짜가 들어 있어 다음 날에는 다시 시도한다.

**Files:**
- Modify: `plugins/kw-control-tower/scripts/sync.ps1` (`Fail`, 단계 2 의 `stuck-<배포처>` 기록, 마무리)
- Modify: `plugins/kw-control-tower/hooks/session-check.ps1` (맞춤 호출 앞)
- Test: `tests/test_control_tower.ps1`

**Interfaces:**
- Consumes: Task 5 의 `$noteSteps`·`$kwState`·`$script:Ran`, Task 8 의 `$script:TimedOutSteps`·`$hangRun`.
- Produces: 두 파일에 같은 `Get-StuckPrint([string]$Root, [int]$Step) -> string`. 상태 키 `stuck-step<N>`. `Fail` 의 새 스위치 `-NoStuck`.

- [ ] **Step 1: 실패하는 검사를 넣는다**

「맞춤의 갱신 기록」 절, Task 8 검사 아래에 넣는다.

```powershell
$r = Invoke-SyncScenario -Mk 'fail' -Steps '1'
Check '단계가 실패하면 그 단계의 지문을 적는다' { $r.State -match '(?m)^stuck-step1=[0-9A-F]{32}\s*$' }
$r = Invoke-SyncScenario -Steps '1' -State 'stuck-step1=00000000000000000000000000000000'
Check '단계가 성공하면 지문을 지운다' { $r.State -notmatch 'stuck-step1' }
# 매번 상한을 넘기는 단계를 켤 때마다 다시 실행하지 않게, 끊긴 단계도 그날은 다시 호출하지 않는다.
Check '상한에 끊긴 단계도 지문을 적는다' { $hangRun.State -match '(?m)^stuck-step1=' }
```

단계 2 의 `stuck-<배포처>` 조건(Step 4)은 이 하네스로 확인하지 못한다. 끊김 시나리오에서는 상한이 단계 1 에서 다 쓰여 단계 2 가 시작되지 않기 때문이다. 코드 검토로 확인한다.

「원격 확인의 조건들」 절, Task 5 검사 아래에 넣는다.

```powershell
# 같은 원인으로 이미 실패한 단계만 남았으면 맞춤을 호출하지 않고 알리기만 한다.
$fnPrint = [regex]::Match($hookSrc, '(?s)function Get-StuckPrint \{.*?\n\}').Value
Check '같은 원인으로 실패한 단계만 남으면 맞춤을 부르지 않는다' {
    . ([scriptblock]::Create($fnPrint))
    $all = (1..7 | ForEach-Object { "stuck-step$_=$(Get-StuckPrint $plugin $_)" }) -join "`n"
    $o = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Sync $stepsStub -Leaf 'b2b2b2b2b2b2' -State $all
    ($o -notmatch 'steps=') -and ($o -match '같은 원인으로 이미 실패해 다시 시도하지 않았습니다')
}
Check '맞춤과 훅이 같은 지문을 만든다' {
    $a = [regex]::Match($hookSrc, '(?s)function Get-StuckPrint \{.*?\n\}').Value
    $b = [regex]::Match((Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw), '(?s)function Get-StuckPrint \{.*?\n\}').Value
    $a -and ($a -eq $b)
}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: 아래 다섯 검사가 `FAIL` — `단계가 실패하면 그 단계의 지문을 적는다`, `단계가 성공하면 지문을 지운다`(지금 코드는 그 줄을 그대로 옮겨 적는다), `상한에 끊긴 단계도 지문을 적는다`, `같은 원인으로 실패한 단계만 남으면 맞춤을 부르지 않는다`, `맞춤과 훅이 같은 지문을 만든다`

- [ ] **Step 3: 두 파일에 같은 지문 함수를 넣는다**

`session-check.ps1` 과 `sync.ps1` 의 `function Get-CheapHash` 아래에 똑같이 넣는다. 함수 몸의 줄과 들여쓰기까지 같아야 검사가 통과한다.

```powershell
function Get-StuckPrint {
    # 실패한 원인이 같은지를 목록 파일 둘의 내용과 날짜와 단계 번호로 가른다. 목록이 바뀌거나
    # 날이 바뀌면 다시 시도한다. 알림 훅에도 같은 함수가 있다. 글자 그대로 같아야 한다.
    param([string]$Root, [int]$Step)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $bytes = New-Object System.Collections.Generic.List[byte]
        foreach ($f in @('manifest.json', 'requirements.txt')) {
            $p = Join-Path $Root $f
            if (Test-Path -LiteralPath $p) { $bytes.AddRange([System.IO.File]::ReadAllBytes($p)) }
        }
        $bytes.AddRange([System.Text.Encoding]::UTF8.GetBytes("step$Step " + (Get-Date -Format 'yyyy-MM-dd')))
        return [System.BitConverter]::ToString($md5.ComputeHash($bytes.ToArray())).Replace('-', '')
    } finally { $md5.Dispose() }
}
```

- [ ] **Step 4: 맞춤이 실패한 단계를 적는다**

`$script:Covered` 선언 아래에 `$script:FailedSteps = New-Object System.Collections.ArrayList` 를 넣는다. `Fail` 함수의 `param(...)` 줄을 아래로 바꾼다.

```powershell
    param([string]$step, [string]$m, [switch]$Covered, [switch]$NoStuck)
```

그 바로 아래 `[void]$script:Failed.Add("$step : $m")` 줄 다음에 넣는다. `param` 은 함수의 첫 문장이어야 하므로 그 앞에 코드를 두지 않는다.

```powershell
    # 다른 알림이 이미 다루는 실패(갱신 실패는 stuck-<배포처>)와 단계 전체를 막을 일이 아닌 실패
    # (권장 플러그인 하나의 설치 실패)는 단계 지문으로 적지 않는다.
    if (-not $Covered -and -not $NoStuck -and $step -match '^\d+$') { [void]$script:FailedSteps.Add([int]$step) }
```

단계 2 의 `if ($late) { $state["stuck-$mkName"] = $remoteOf[$mkName] } else { $state.Remove("stuck-$mkName") }` 를 바꾼다.

```powershell
            # 상한에 끊긴 갱신은 원격 커밋 탓이 아니다. 적으면 새 커밋이 생길 때까지 재시도하지 않는다.
            if ($late -and ($script:TimedOutSteps -notcontains 2)) { $state["stuck-$mkName"] = $remoteOf[$mkName] }
            elseif (-not $late) { $state.Remove("stuck-$mkName") }
```

마무리의 `Save-State`(로그 쓰기 앞) 바로 위에 넣는다.

```powershell
# 실행한 단계마다 실패했거나 상한에 끊겼으면 지문을 적고, 끝까지 성공했으면 지운다.
if (-not $WhatIfOnly) {
    foreach ($n in ($script:Ran | Sort-Object -Unique)) {
        if (($script:FailedSteps -contains $n) -or ($script:TimedOutSteps -contains $n)) { $state["stuck-step$n"] = Get-StuckPrint $root $n }
        else { $state.Remove("stuck-step$n") }
    }
}
```

- [ ] **Step 5: 감지가 같은 원인의 단계를 넘긴다**

`session-check.ps1` 에서 Task 5 의 `$runSteps = ...` 줄을 아래로 바꾼다. 이 블록은 맞춤을 호출하는 `try` 보다 앞, `$sync` 존재 확인보다도 앞에 두고, `$say` 선언 뒤에 둔다.

```powershell
    # 같은 원인으로 이미 실패한 단계는 다시 호출하지 않는다. 호출해도 같은 실패가 되풀이될 뿐이다.
    $runSteps = New-Object System.Collections.ArrayList
    $held     = New-Object System.Collections.ArrayList
    foreach ($n in @($noteSteps | ForEach-Object { $_ } | Sort-Object -Unique)) {
        if ($kwState["stuck-step$n"] -eq (Get-StuckPrint $root $n)) { [void]$held.Add($n) } else { [void]$runSteps.Add($n) }
    }
    if ($held.Count -gt 0) {
        [void]$say.Add("kw-control-tower: 맞춤이 단계 $($held -join ', ') 에서 같은 원인으로 이미 실패해 다시 시도하지 않았습니다. 기록: $(Join-Path $cfg 'kw-control-tower.sync.log')")
    }
    if ($runSteps.Count -eq 0) { Send-Hook; exit 0 }
```

- [ ] **Step 6: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 7: 커밋한다**

```bash
git add plugins/kw-control-tower/scripts/sync.ps1 plugins/kw-control-tower/hooks/session-check.ps1 tests/test_control_tower.ps1
git commit -m "feat: 같은 원인으로 실패하거나 상한에 끊긴 맞춤 단계는 그날 다시 호출하지 않는다"
```

---

### Task 10: 권장 플러그인을 하나씩 기록하고 등급을 옮긴다

**Files:**
- Modify: `plugins/kw-control-tower/scripts/sync.ps1` (단계 2 의 권장 분기 367–385행, 마무리 832–837행, `$firstRun`·`$script:SuggestedIncomplete`)
- Modify: `plugins/kw-control-tower/hooks/session-check.ps1` (질문 1·2 뒤)
- Modify: `plugins/kw-control-tower/manifest.json`
- Modify: `tests/test_dashboard.ps1:44`
- Modify: `docs/superpowers/specs/2026-09-06-control-tower-design.md:328`
- Test: `tests/test_control_tower.ps1`

**Interfaces:**
- Consumes: Task 5 의 `Add-Note`·`$kwState`, Task 9 의 `Fail -NoStuck`.
- Produces: 두 파일에 같은 `Get-SuggestedDone($State) -> string[]`. 상태 키 `suggestedDone`(세미콜론으로 이은 플러그인 id).

- [ ] **Step 1: 실패하는 검사를 넣는다**

claude 스텁에 `plugin install` 분기를 추가한다(`plugin update` 분기 앞).

```powershell
if ($a[0] -eq 'plugin' -and $a[1] -eq 'install') {
    if ($env:STUB_INSTALL_FAIL -and $a[2] -eq $env:STUB_INSTALL_FAIL) { exit 1 }
    $f = Join-Path $pd 'installed_plugins.json'
    $j = Get-Content -LiteralPath $f -Raw | ConvertFrom-Json
    $j.plugins | Add-Member -NotePropertyName $a[2] -NotePropertyValue @(@{ installPath = (Join-Path $pd 'cache\x'); gitCommitSha = $env:STUB_NEW }) -Force
    $j | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $f
    exit 0
}
```

`Invoke-SyncScenario` 를 고친다.
- param 에 `[switch]$NoRanOnce, [string]$InstallFail = '', [string[]]$Drop = @()` 를 추가한다.
- `$ids` 에 `'document-skills@anthropic-agent-skills'` 를 추가한다. 필수로 옮기므로 기본 설치본에 있어야 옛 검사가 설치 한 건으로 흔들리지 않는다.
- `$plug` 를 채운 뒤 `foreach ($d in $Drop) { $plug.Remove($d) }` 를 넣는다.
- 상태 줄을 `$(if ($NoRanOnce) { $State } else { "ranOnce=2026-01-01`n$State" }).Trim()` 로 바꾼다.
- 환경 변수에 `$env:STUB_INSTALL_FAIL = $InstallFail` 를 추가하고 정리 목록에도 추가한다.

Task 9 검사 아래에 넣는다.

```powershell
# 권장은 플러그인마다 한 번이다. 하나가 실패해도 성공한 것은 기록되고, 실패한 것만 다시 해 본다.
$r = Invoke-SyncScenario -NoRanOnce -Steps '2' -InstallFail 'playwright@claude-plugins-official'
Check '권장 설치에 성공한 것만 기록한다' {
    ($r.State -match '(?m)^suggestedDone=.*superpowers@claude-plugins-official') -and
    ($r.State -notmatch 'playwright@claude-plugins-official')
}
# 권장 하나의 실패는 단계 2 전체를 막지 않는다. 막으면 같은 날 필수 플러그인 교정까지 보류된다.
Check '권장 설치 실패는 단계 지문을 남기지 않는다' { $r.State -notmatch 'stuck-step2' }
# 기록된 것은 사용자가 지운 뒤에도 다시 깔지 않는다.
$r = Invoke-SyncScenario -NoRanOnce -Steps '2' -Drop 'kw-dashboard@kiwoom-ax' `
        -State 'suggestedDone=kw-devops@kiwoom-ax;kw-dashboard@kiwoom-ax;superpowers@claude-plugins-official;playwright@claude-plugins-official;frontend-design@claude-plugins-official'
Check '기록된 권장 플러그인은 지워도 다시 안 깐다' { $r.Calls -notmatch 'plugin install kw-dashboard' }
# ranOnce 만 있는 옛 PC 는 이행 때의 권장 목록을 처리한 것으로 본다. 그 목록의 것은 다시 깔지 않고,
# 이행 뒤 권장에 새로 올린 것은 한 번 깐다.
$r = Invoke-SyncScenario -Steps '2' -Drop 'superpowers@claude-plugins-official'
Check 'ranOnce 만 있는 PC 에서 옛 권장은 지웠으면 다시 안 깐다' { $r.Calls -notmatch 'plugin install superpowers' }
$r = Invoke-SyncScenario -Steps '2' -Drop 'kw-dashboard@kiwoom-ax'
Check 'ranOnce 만 있는 PC 에도 새 권장은 한 번 깐다' { $r.Calls -match 'plugin install kw-dashboard@kiwoom-ax' }
```

「목록 파일」 절에 넣는다.

```powershell
# kw-dashboard 는 배포를 권장인 kw-devops 에 넘기므로 같은 등급이다. kw-doc-formats 는 공식
# document-skills 위에 얹는 보정 스킬이라 기본 스킬이 늘 있어야 한다(2026-09-30 사용자 결정).
Check 'kw-dashboard 는 권장이고 document-skills 는 필수다' {
    (@($mf.suggested) -contains 'kw-dashboard@kiwoom-ax') -and (@($mf.required) -notcontains 'kw-dashboard@kiwoom-ax') -and
    (@($mf.required) -contains 'document-skills@anthropic-agent-skills') -and (@($mf.suggested) -notcontains 'document-skills@anthropic-agent-skills')
}
```

`Check '권장을 다 못 깔면 한 번 돌았다를 안 적는다'`(376–379행)를 지운다. 이 규칙을 위 기록 방식이 대신한다.

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: `권장 설치에 성공한 것만 기록한다`, `권장 설치 실패는 단계 지문을 남기지 않는다`, `ranOnce 만 있는 PC 에도 새 권장은 한 번 깐다`, `kw-dashboard 는 권장이고 document-skills 는 필수다` 가 `FAIL`

- [ ] **Step 3: 두 파일에 같은 함수를 넣는다**

`session-check.ps1` 과 `sync.ps1` 의 `function Get-Prop` 아래에 똑같이 넣는다.

```powershell
function Get-SuggestedDone {
    # 한 번 처리한 권장 플러그인이다. 옛 버전은 ranOnce 하나로 권장 분기를 통째로 닫았으므로, 그 표시만
    # 있는 PC 는 이행 때(2026-09-30)의 권장 목록을 처리한 것으로 본다. 그 PC 에서 사용자가 지운 것을
    # 되살리지 않고, 그 뒤에 권장에 올린 것은 한 번 깔기 위해서다. 알림 훅에도 같은 함수가 있다.
    param($State)
    if ($State.ContainsKey('suggestedDone')) { return @($State['suggestedDone'].Split(';') | Where-Object { $_ }) }
    if ($State.ContainsKey('ranOnce')) {
        return @('kw-devops@kiwoom-ax', 'superpowers@claude-plugins-official', 'document-skills@anthropic-agent-skills',
                 'playwright@claude-plugins-official', 'frontend-design@claude-plugins-official')
    }
    return @()
}
```

- [ ] **Step 4: 맞춤의 권장 분기를 바꾼다**

권장 분기(`# 권장 플러그인은 이 PC 에서 맞춤이 한 번도 …` 부터 `else { Say '권장 플러그인은 처음 한 번만 깝니다. 건너뜁니다.' }` 까지)를 바꾼다.

```powershell
    # 권장은 플러그인마다 한 번만 깐다. 깔았거나 이미 있던 것은 suggestedDone 에 적고, 사용자가
    # 나중에 지워도 다시 깔지 않는다. uninstall 은 흔적을 모두 지워 지운 것과 처음 보는 것이
    # 구별되지 않으므로 이 기록이 유일한 근거다. 설치에 실패한 것만 다음에 다시 해 본다.
    $done = @(Get-SuggestedDone $state)
    foreach ($id in @($manifest.suggested)) {
        if ($done -contains $id) { continue }
        if ($null -ne (Get-Prop $installedOf $id)) { $done += $id; continue }
        if (Invoke-Claude @('plugin', 'install', $id)) {
            Note "권장 플러그인을 깔았습니다: $id"
            $script:Restart = $true
            $done += $id
        }
        else { Fail '2' "권장 플러그인 설치에 실패했습니다: $id" -NoStuck }
    }
    if (-not $WhatIfOnly) { $state['suggestedDone'] = ($done -join ';') }
```

`$firstRun = -not $state.ContainsKey('ranOnce')` 줄과 `$script:SuggestedIncomplete = $false` 줄을 지운다. 마무리의 `if (-not $WhatIfOnly) { if (-not $script:SuggestedIncomplete) ... }` 블록을 지운다. `ranOnce` 는 이제 읽기만 한다.

- [ ] **Step 5: 감지가 아직 못 깐 권장을 단계 2 로 넘긴다**

`session-check.ps1` 질문 1·2 의 `if ($disabled.Count -gt 0) {…}` 블록 아래에 넣는다. `$kwState` 는 Task 5 에서 이 블록보다 앞에서 읽는다.

```powershell
    # 권장 가운데 아직 처리하지 않았고 깔리지도 않은 것이 있으면 단계 2 가 다시 해 본다.
    $doneS = @(Get-SuggestedDone $kwState)
    $pending = @(@($manifest.suggested) | Where-Object { ($doneS -notcontains $_) -and ($null -eq (Get-Prop $installedOf $_)) })
    if ($pending.Count -gt 0) {
        Add-Note 2 "권장 플러그인을 아직 못 깔았습니다: $($pending -join ', ')"
    }
```

- [ ] **Step 6: 등급을 옮긴다**

`manifest.json` 을 아래로 고친다.

```json
  "required": [
    "kw-doc-formats@kiwoom-ax",
    "document-skills@anthropic-agent-skills"
  ],

  "_suggested_comment": "kw-devops 는 사내 서버 192.7.9.45 에만 접속하므로 외부망 PC 에서는 쓸 수 없다. 필수에 두면 사용자가 꺼도 맞춤이 매 세션 다시 켠다. 권장으로 두어 한 번만 깔고, 끈 것은 그대로 둔다(2026-09-29 사용자 결정). kw-dashboard 는 배포를 kw-devops 에 넘기므로 같은 권장이다. document-skills 는 kw-doc-formats 가 얹히는 기본 스킬이라 필수로 옮겼다(2026-09-30 사용자 결정). 권장은 플러그인마다 한 번 깔고 상태 파일의 suggestedDone 에 적는다. 켜져 있든 꺼져 있든 깔려 있으면 뒤처진 설치본은 맞춤이 옮긴다.",

  "suggested": [
    "kw-devops@kiwoom-ax",
    "kw-dashboard@kiwoom-ax",
    "superpowers@claude-plugins-official",
    "playwright@claude-plugins-official",
    "frontend-design@claude-plugins-official"
  ],
```

`tests/test_dashboard.ps1` 44행을 바꾼다.

```powershell
Assert "the control tower suggests $PluginId" ($null -ne $manifest -and @($manifest.suggested) -contains $PluginId)
```

설계 문서 328행의 `**\`suggested\`는 이 PC에서 맞춤이 한 번도 안 돈 때에만 깐다.** 상태 파일에 그 표시가 있으면 두 번째부터는 아예 안 본다.` 를 아래로 바꾼다.

```markdown
**`suggested`는 플러그인마다 한 번만 깐다.** 깔았거나 이미 있던 것을 상태 파일의 `suggestedDone`에 적고, 사용자가 나중에 지워도 다시 깔지 않는다. 실패한 것만 다음에 다시 해 본다. 옛 `ranOnce`만 있는 PC는 이행 때의 권장 목록을 처리한 것으로 보고, 그 뒤에 권장에 올린 것은 한 번 깐다(2026-09-30).
```

- [ ] **Step 7: 통과를 확인한다**

Run: 검사 넷
Expected: 모두 실패 없음. `플러그인을 바꾸는 곳마다 재시작 깃발을 설정한다` 도 통과해야 한다.

- [ ] **Step 8: 커밋한다**

```bash
git add plugins/kw-control-tower/scripts/sync.ps1 plugins/kw-control-tower/hooks/session-check.ps1 plugins/kw-control-tower/manifest.json tests/test_control_tower.ps1 tests/test_dashboard.ps1 docs/superpowers/specs/2026-09-06-control-tower-design.md
git commit -m "feat: 권장 플러그인을 하나씩 기록하고 kw-dashboard 를 권장으로, document-skills 를 필수로 옮긴다"
```

---

### Task 11: 맞춤을 한 번에 하나만 실행한다

**Files:**
- Modify: `plugins/kw-control-tower/scripts/sync.ps1` (목록 파일 검사 뒤·상태 파일 읽기 앞, 파일 끝, `Save-Json`, 단계 6 잠금 반복)
- Test: `tests/test_control_tower.ps1`

**Interfaces:**
- Consumes: Task 8 의 `$hang`.
- Produces: 잠금 폴더 `~\.claude\kw-control-tower.sync.lock`. 맞춤 본문 전체를 감싸는 `try { … } finally { … }`.

- [ ] **Step 1: 실패하는 검사를 넣는다**

`Invoke-SyncScenario` param 에 `[string]$Lock = ''` 를 추가하고, 상태 파일을 쓴 줄 아래에 넣는다.

```powershell
    $lockDir = Join-Path $h '.claude\kw-control-tower.sync.lock'
    if ($Lock) {
        New-Item -ItemType Directory -Force -Path $lockDir | Out-Null
        if ($Lock -eq 'stale') { (Get-Item -LiteralPath $lockDir).CreationTime = (Get-Date).AddMinutes(-15) }
    }
```

돌려주는 해시에 `LockLeft = (Test-Path -LiteralPath $lockDir)` 를 추가한다.

Task 10 검사 아래에 넣는다.

```powershell
$r = Invoke-SyncScenario -Steps '1,2'
Check '맞춤이 끝나면 잠금을 치운다' { ($r.Sha -eq $shaNew) -and -not $r.LockLeft }
$r = Invoke-SyncScenario -Steps '1,2' -Lock 'fresh'
Check '다른 맞춤이 실행 중이면 넘긴다' { ($r.Sha -eq $shaOld) -and ($r.Out -match '이번에는 넘깁니다') }
$r = Invoke-SyncScenario -Steps '1,2' -Lock 'stale'
Check '10분 넘은 잠금은 치우고 실행한다' { ($r.Sha -eq $shaNew) -and -not $r.LockLeft }
# 상한에 끊긴 실행도 잠금을 남기지 않는다. Task 8 의 끊김 시나리오를 다시 실행한다.
$r = Invoke-SyncScenario -Budget 3 -Bin $hang -Steps '1'
Check '상한에 끊긴 실행도 잠금을 치운다' { -not $r.LockLeft }
```

「사용자 파일 쓰기」 절 514행을 바꾼다.

```powershell
# disciplined-coder 도 settings.json·known_marketplaces.json 에 <파일>.bak 을 남긴다. 이름을 구분해 서로의 사본을 덮지 않는다.
Check '고치기 전에 사본을 남긴다'        { $syncSrc.Contains('Copy-Item -LiteralPath $Path -Destination "$Path.kw.bak"') }
```

「CLAUDE.md 단계」 절에 넣는다.

```powershell
# 상대가 문지기를 만든 채 종료되면 문지기가 남아, 치우지 않으면 반복을 다 쓰고 단계 6 이 실패한다.
# 폴더 생성 시각은 파일 시스템이 옛 값을 다시 붙일 수 있어 쓰지 않고, 연속으로 못 만든 횟수로 판정한다.
Check '남은 문지기 폴더를 치운다' { $syncSrc -match '\$gateMiss -ge 200' }
# 잠금은 상태 파일을 읽기 전에 잡는다. 뒤에 잡으면 직전 맞춤이 적은 상태를 옛 값으로 덮는다.
Check '맞춤 잠금을 상태 파일 읽기 전에 잡는다' {
    $l = $syncSrc.IndexOf("'kw-control-tower.sync.lock'"); $s = $syncSrc.IndexOf('$state = @{}')
    ($l -ge 0) -and ($s -gt $l)
}
```

- [ ] **Step 2: 실패를 확인한다**

Run: `pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1`
Expected: `다른 맞춤이 실행 중이면 넘긴다`, `고치기 전에 사본을 남긴다`, `남은 문지기 폴더를 치운다`, `맞춤 잠금을 상태 파일 읽기 전에 잡는다` 가 `FAIL`. 잠금이 원래 없으므로 잠금을 치우는지 보는 검사 세 개는 통과할 수 있다.

- [ ] **Step 3: 잠금을 넣는다**

목록 파일 칸 검사(`목록 파일에 칸이 빠졌습니다` 의 `exit 1` 블록) 바로 아래, `$state = @{}` 보다 앞에 넣는다.

```powershell
# 맞춤은 한 번에 하나만 실행한다. 창을 둘 이상 동시에 열면 훅이 저마다 맞춤을 호출해 pip 과
# claude plugin 과 상태 파일 쓰기가 겹친다. 잠금 폴더를 먼저 만든 쪽만 실행하고 못 만든 쪽은
# 이번 세션을 넘긴다. 상태 파일을 읽기 전에 잡아야 직전 맞춤이 적은 값을 덮지 않는다.
# 훅이 제한에 걸려 끊기면 잠금이 남으므로 10분 넘은 것은 치운다.
$syncLock = Join-Path $cfg 'kw-control-tower.sync.lock'
if (-not $WhatIfOnly) {
    if (Test-Path -LiteralPath $syncLock) {
        $lockAge = (Get-Date) - (Get-Item -LiteralPath $syncLock).CreationTime
        if ($lockAge.TotalMinutes -ge 10) { Remove-Item -LiteralPath $syncLock -Recurse -Force -ErrorAction SilentlyContinue }
    }
    try { New-Item -ItemType Directory -Path $syncLock -ErrorAction Stop | Out-Null }
    catch { Write-Host 'kw-control-tower: 다른 창에서 맞춤이 실행 중이라 이번에는 넘깁니다.'; exit 0 }
}
# 여기서부터 끝까지를 감싼다. exit 와 예외와 중단 모두에서 finally 가 잠금을 치운다.
try {
```

파일 맨 끝(마지막 `exit 0` 뒤)에 넣는다.

```powershell
} finally {
    if (-not $WhatIfOnly) { Remove-Item -LiteralPath $syncLock -Recurse -Force -ErrorAction SilentlyContinue }
}
```

`try {` 와 `} finally {` 사이 줄의 들여쓰기는 바꾸지 않는다. 검사가 `^Show` 와 `^Save-State` 를 줄 머리에서 찾는다.

`Save-Json` 의 `Copy-Item -LiteralPath $Path -Destination "$Path.bak" -Force` 를 바꾼다.

```powershell
        Copy-Item -LiteralPath $Path -Destination "$Path.kw.bak" -Force
```

- [ ] **Step 4: 남은 문지기를 치운다**

단계 6 잠금 반복의 `for ($tick = 0; …)` 바로 위에 `$gateMiss = 0` 을 넣고, 문지기 생성에 실패한 `} catch { Start-Sleep -Milliseconds 50; continue }` 를 바꾼다.

```powershell
            } catch {
                # 상대가 문지기를 만든 채 종료되면 문지기가 남는다. 문지기는 잠금을 잡는 순간에만 쥐므로
                # 연속으로 200번(약 10초) 못 만들면 남은 것으로 보고 치운다.
                $gateMiss++
                if ($gateMiss -ge 200) { Remove-Item -LiteralPath $gate -Recurse -Force -ErrorAction SilentlyContinue; $gateMiss = 0 }
                Start-Sleep -Milliseconds 50; continue
            }
```

문지기를 만든 경로(`New-Item -ItemType Directory -Path $gate` 가 성공한 뒤)의 첫 줄에 `$gateMiss = 0` 을 넣는다.

- [ ] **Step 5: 통과를 확인한다**

Run: 검사 넷. Expected: 모두 실패 없음

- [ ] **Step 6: 커밋한다**

```bash
git add plugins/kw-control-tower/scripts/sync.ps1 tests/test_control_tower.ps1
git commit -m "feat: 맞춤을 한 번에 하나만 실행하고 남은 잠금과 문지기를 치운다"
```

---

### Task 12: 저장소 검사와 README 를 정리한다

**Files:**
- Modify: `tests/test_control_tower.ps1` (78–92행 밑줄 키 검사, 끝에 validate)
- Modify: `tests/test_doc_formats.ps1` (128–137행), `tests/test_devops.ps1` (347–353행), `tests/test_dashboard.ps1` (77–83행)
- Modify: `README.md` (55–57행, 59–62행 문단 끝, 76–82행)

**Interfaces:**
- Produces: 테스트 전역 `$claudeJsonFiles` — 클로드 코드가 읽는 JSON 파일 목록.

- [ ] **Step 1: 밑줄 키 검사가 모든 플러그인을 모은다**

78행 `Check '클로드 코드가 읽는 JSON 에 밑줄 주석 키가 없다'` 바로 위에 넣고, 검사 안의 `$files = @( … )` 를 `$files = $claudeJsonFiles` 로 바꾼다.

```powershell
# 플러그인을 추가할 때 이 목록을 손으로 고치지 않도록 plugins 아래를 모은다. kw-dashboard 가 빠져 있었다.
$claudeJsonFiles = @((Join-Path $repo '.claude-plugin\marketplace.json'), (Join-Path $plugin 'hooks\hooks.json')) +
    @(Get-ChildItem (Join-Path $repo 'plugins') -Directory | ForEach-Object { Join-Path $_.FullName '.claude-plugin\plugin.json' } | Where-Object { Test-Path -LiteralPath $_ })
```

그 검사 아래에 넣는다.

```powershell
Check '밑줄 키 검사가 모든 플러그인의 plugin.json 을 본다' {
    $want = @(Get-ChildItem (Join-Path $repo 'plugins') -Directory | ForEach-Object { Join-Path $_.FullName '.claude-plugin\plugin.json' } | Where-Object { Test-Path -LiteralPath $_ })
    ($want.Count -ge 4) -and (@($want | Where-Object { $claudeJsonFiles -notcontains $_ }).Count -eq 0)
}
```

- [ ] **Step 2: 마켓플레이스 검증을 한 곳으로 옮긴다**

`test_control_tower.ps1` 의 `# --- 결과` 절 바로 위에 넣는다.

```powershell
# --- 마켓플레이스 검증 ------------------------------------------------------
# 저장소 전체를 한 번 검증한다. 플러그인별 검사 셋이 각자 같은 검증을 실행하던 것을 여기로 모았다.
Write-Host ''
Write-Host '마켓플레이스 검증'
Push-Location $repo
try { $null = & claude plugin validate ./ 2>&1 | Out-String; $validateCode = $LASTEXITCODE } finally { Pop-Location }
Check 'claude plugin validate 가 0 으로 끝난다(경고는 허용)' { $validateCode -eq 0 }
```

`test_doc_formats.ps1` 128–137행, `test_devops.ps1` 347–353행, `test_dashboard.ps1` 77–83행의 `--- claude plugin validate ---` 절을 지우고 각 위치에 한 줄을 남긴다.

```powershell
# 마켓플레이스 전체 검증은 tests/test_control_tower.ps1 이 한 번 실행한다.
```

- [ ] **Step 3: README 의 세션 시작 계약을 코드와 맞춘다**

55–57행을 바꾼다.

```markdown
**클로드 코드를 켤 때 감지한다.** 이 PC가 목록과 불일치하는 곳을 열세 가지로 확인한다. 파일을
읽고, 원격 커밋 하나만 `curl.exe`로 읽는다. 불일치가 하나도 없으면 아무 말도 하지 않고 끝난다.
```

76–82행 표를 바꾼다.

```markdown
| 무엇 | 값 |
|---|---|
| 세션 시작에 실행되는 훅 | 하나뿐이고, 클로드 코드를 켤 때만 실행된다 |
| 외부 프로그램 | `curl.exe` 하나. 원격 커밋을 읽는다(2026-09-25 승인). `claude`도 `git`도 `python`도 호출하지 않는다 |
| 네트워크 | `curl.exe`의 2초 요청 하나. 몸통 시간에서 뺀다 |
| 읽는 것 | 설정 파일과 상태 파일과 사내 문안 사본, 레지스트리 값 하나 |
| 몸통 시간 | 200밀리초를 넘으면 그 값을 남기고 검사가 묻는다 |
```

59행 문단(Task 3 에서 고친 것) 끝에 두 문장을 추가한다.

```markdown
불일치한 단계만 실행하고, 60초 상한에 닿으면 남은 단계를 다음 세션으로 미룬다. 같은 원인으로
실패한 단계는 그날 다시 호출하지 않는다.
```

- [ ] **Step 4: 검사 넷을 모두 실행한다**

Run:
```
pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_control_tower.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_doc_formats.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_devops.ps1
pwsh -NoProfile -ExecutionPolicy Bypass -File tests\test_dashboard.ps1
```
Expected: 넷 다 실패 없음

- [ ] **Step 5: 커밋한다**

```bash
git add tests/ README.md
git commit -m "test: 마켓플레이스 검증을 한 곳으로 모으고 README 의 세션 시작 계약을 코드와 맞춘다"
```

<!-- spec-review: escalated -->
