# 컨트롤 타워의 계약을 검사한다. 이 PC 를 안 바꾼다.
#
#   pwsh -File tests\test_control_tower.ps1
#
# 알림 훅은 격리된 가짜 홈에서 돌려 실제 설정을 안 건드린다.

Set-StrictMode -Off
$ErrorActionPreference = 'Continue'

$repo   = Split-Path -Parent $PSScriptRoot
$plugin = Join-Path $repo 'plugins\kw-control-tower'
$ps51   = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

$script:Pass = 0
$script:FailList = New-Object System.Collections.ArrayList

function Check {
    param([string]$Name, [scriptblock]$Body)
    try {
        $r = & $Body
        if ($r) { $script:Pass++; Write-Host "  ok   $Name" -ForegroundColor Green }
        else { [void]$script:FailList.Add($Name); Write-Host "  FAIL $Name" -ForegroundColor Red }
    } catch {
        [void]$script:FailList.Add("$Name ($($_.Exception.Message))")
        Write-Host "  FAIL $Name : $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ''
Write-Host '컨트롤 타워 계약 검사' -ForegroundColor Cyan
Write-Host ''

# --- 있어야 할 파일 --------------------------------------------------------
Write-Host '있어야 할 파일'
Check '있다: .claude-plugin\marketplace.json (레포 뿌리)' { Test-Path -LiteralPath (Join-Path $repo '.claude-plugin\marketplace.json') }
foreach ($rel in @(
    '.claude-plugin\plugin.json',
    'manifest.json',
    'hooks\hooks.json',
    'hooks\session-check.ps1',
    'scripts\sync.ps1',
    'commands\kw-sync.md',
    'requirements.txt'
)) {
    Check "있다: $rel" { Test-Path -LiteralPath (Join-Path $plugin $rel) }
}

# --- 형식 -----------------------------------------------------------------
Write-Host ''
Write-Host '형식'
Check 'marketplace.json 이 JSON 이다' { $null -ne (Get-Content (Join-Path $repo '.claude-plugin\marketplace.json') -Raw | ConvertFrom-Json) }
Check 'plugin.json 이 JSON 이다'      { $null -ne (Get-Content (Join-Path $plugin '.claude-plugin\plugin.json') -Raw | ConvertFrom-Json) }
Check 'manifest.json 이 JSON 이다'    { $null -ne (Get-Content (Join-Path $plugin 'manifest.json') -Raw | ConvertFrom-Json) }
Check 'hooks.json 이 JSON 이다'       { $null -ne (Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json) }

# 판본을 감지에 안 쓰기로 했으므로 plugin.json 에 version 을 안 적는다.
Check 'plugin.json 에 version 이 없다' {
    $j = Get-Content (Join-Path $plugin '.claude-plugin\plugin.json') -Raw | ConvertFrom-Json
    $null -eq $j.PSObject.Properties['version']
}

# --- 훅의 예산 -------------------------------------------------------------
Write-Host ''
Write-Host '훅의 예산'
$hookSrc = Get-Content (Join-Path $plugin 'hooks\session-check.ps1') -Raw

# 주석을 걷어낸 코드만 검사한다. 주석에 적힌 낱말을 코드로 세면 자기 설명이 자기
# 검사를 떨어뜨린다. 실제로 한 번 그렇게 됐다.
function Get-CodeOnly {
    param([string]$Text)
    ($Text -split "`n" | Where-Object { $_ -notmatch '^\s*#' }) -join "`n"
}
$hookCode = Get-CodeOnly $hookSrc

Check '세션 시작 훅이 하나뿐이다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    @($j.hooks.SessionStart).Count -eq 1 -and @($j.hooks.SessionStart[0].hooks).Count -eq 1
}
Check '훅을 powershell.exe 로 건다 (pwsh 7 이 없어도 돈다)' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $j.hooks.SessionStart[0].hooks[0].command -eq 'powershell.exe'
}
# 한 문자열로 적으면 셸이 그것을 다시 가르고, 사용자 이름에 공백이 든 PC 에서
# 플러그인 경로가 거기서 깨진다. 나눠 적으면 셸을 안 거친다.
Check '명령과 인자를 나눠 적는다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $all = @($j.hooks.SessionStart[0].hooks) + @($j.hooks.PreToolUse | ForEach-Object { $_.hooks })
    @($all | Where-Object { $_.command -ne 'powershell.exe' -or @($_.args).Count -lt 6 }).Count -eq 0
}
# matcher 는 도구 이름만 거른다. 명령 내용을 거르는 것은 if 이고, 이것이 없으면
# 도커도 python3 도 아닌 명령마다 프로세스가 뜬다.
Check '도구 훅마다 if 규칙이 걸려 있다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $tool = @($j.hooks.PreToolUse | ForEach-Object { $_.hooks })
    (@($tool).Count -eq 4) -and (@($tool | Where-Object { -not $_.'if' }).Count -eq 0)
}
Check 'if 규칙이 그 훅의 도구와 짝이 맞는다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $bad = 0
    foreach ($g in @($j.hooks.PreToolUse)) {
        foreach ($h in @($g.hooks)) { if (-not $h.'if'.StartsWith($g.matcher + '(')) { $bad++ } }
    }
    $bad -eq 0
}
Check '훅이 외부 프로그램을 안 부른다' {
    ($hookCode -notmatch '(?m)^\s*&\s') -and
    ($hookCode -notmatch 'Start-Process') -and
    ($hookCode -notmatch 'claude\s+plugin') -and
    ($hookCode -notmatch 'Get-FileHash')
}
Check '훅이 네트워크에 안 나간다' {
    $hookCode -notmatch 'Invoke-WebRequest|Invoke-RestMethod|System\.Net\.'
}
Check '훅이 아무 파일도 안 고친다 (자국 파일 둘은 뺀다)' {
    # 쓰기는 느림 자국과 오류 자국 둘뿐이고 나머지 쓰기 명령은 없어야 한다.
    ($hookCode -notmatch 'Set-Content|Remove-Item|New-Item|Move-Item|Copy-Item')
}
# 자국 파일이 영원히 자라면 그것도 이 PC 를 더럽히는 것이다.
Check '느림 자국은 덧붙이지 않고 덮어쓴다' { $hookCode -match 'WriteAllText\(\$over' }
Check '오류 자국은 스무 줄까지만 남긴다'   { $hookCode -match '\$keep\.Count -gt 20' }
# 감지 표가 적은 물음을 훅이 다 재야 한다. CLAUDE.md 문안 검사가 표에는 있고
# 훅에는 없어서, 사내 문안을 손으로 고쳐도 아무도 모르는 상태였다.
Check '훅이 감지 표의 물음을 다 잰다' {
    $spec2 = Get-Content (Join-Path $repo 'docs\superpowers\specs\2026-09-06-control-tower-design.md') -Raw
    # 표 머리에 바로 붙여 잡는다. 절 머리부터 잡으면 표 앞 문단에서 끊긴다.
    $tbl = [regex]::Match($spec2, "(?s)\| 물음 \| 어디서 재나 \|.*?(?=\r?\n\r?\n)").Value
    $rows = @([regex]::Matches($tbl, "(?m)^\|(?!-)")).Count - 1   # 머리 줄을 뺀다
    $asked = @([regex]::Matches($hookSrc, "(?m)^\s*# --- 물음 ")).Count
    # 한 주석이 물음 둘을 덮는 자리가 있어 주석 수가 아니라 번호의 최댓값을 센다
    # 한 주석이 물음 둘을 덮을 때 앞말에 따라 '과' 도 되고 '와' 도 된다.
    $nums = @([regex]::Matches($hookSrc, '# --- 물음 (\d+)(?:[과와] (\d+))?')) |
            ForEach-Object { [int]$_.Groups[1].Value; if ($_.Groups[2].Success) { [int]$_.Groups[2].Value } }
    ($asked -gt 0) -and (($nums | Measure-Object -Maximum).Maximum -eq $rows)
}
Check '훅이 CLAUDE.md 문안을 견준다' {
    ($hookCode -match 'personal-memory-ko\.md') -and ($hookCode -match 'BEGIN AX')
}
Check '훅이 5.1 전용 문법만 쓴다' {
    ($hookCode -notmatch '-AsHashtable') -and
    ($hookCode -notmatch '\?\?') -and
    ($hookCode -notmatch '\?\.')
}

# --- 한글이 5.1 에서 안 깨진다 ---------------------------------------------
Write-Host ''
Write-Host '한글'
foreach ($f in @((Join-Path $plugin 'hooks\session-check.ps1'), (Join-Path $plugin 'scripts\sync.ps1'))) {
    Check "UTF-8 BOM 이 있다: $(Split-Path $f -Leaf)" {
        $b = [System.IO.File]::ReadAllBytes($f)
        $b.Length -ge 3 -and $b[0] -eq 239 -and $b[1] -eq 187 -and $b[2] -eq 191
    }
}

# --- 두 스크립트가 같은 해시를 낸다 ----------------------------------------
Write-Host ''
Write-Host '해시가 두 곳에서 같다'
Check '알림 훅과 맞춤이 같은 해시 함수를 갖는다' {
    $a = ([regex]::Match($hookSrc, '(?s)function Get-CheapHash \{.*?\n\}')).Value
    $s = Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw
    $b = ([regex]::Match($s, '(?s)function Get-CheapHash \{.*?\n\}')).Value
    # 주석은 다를 수 있으므로 계산하는 줄만 견준다
    $strip = { param($t) ($t -split "`n" | Where-Object { $_ -notmatch '^\s*#' }) -join "`n" }
    (& $strip $a).Trim() -eq (& $strip $b).Trim()
}

# --- 알림 훅이 가짜 홈에서 아무 말도 안 한다 -------------------------------
Write-Host ''
Write-Host '알림 훅의 동작'
$fake = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path (Join-Path $fake '.claude\plugins') | Out-Null

Check '설정 파일이 하나도 없으면 조용히 물러난다' {
    $out = & $ps51 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command @"
`$env:USERPROFILE='$fake'; `$env:CLAUDE_PLUGIN_ROOT='$plugin'
& '$plugin\hooks\session-check.ps1'
"@ 2>&1
    # 목록은 읽히지만 필수 플러그인이 없으므로 말은 한다. 다만 죽지 않아야 한다.
    $LASTEXITCODE -eq 0
}

Check '목록 파일이 없으면 아무 말도 안 한다' {
    $empty = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-empty-" + [guid]::NewGuid().ToString('n').Substring(0,8))
    New-Item -ItemType Directory -Force -Path $empty | Out-Null
    $out = & $ps51 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command @"
`$env:USERPROFILE='$fake'; `$env:CLAUDE_PLUGIN_ROOT='$empty'
& '$plugin\hooks\session-check.ps1'
"@ 2>&1
    Remove-Item -LiteralPath $empty -Recurse -Force -ErrorAction SilentlyContinue
    [string]::IsNullOrWhiteSpace(($out | Out-String).Trim())
}

Check '몸통이 200밀리초 안에 끝난다' {
    $slow = Join-Path $fake '.claude\kw-control-tower.slow'
    Remove-Item -LiteralPath $slow -ErrorAction SilentlyContinue
    & $ps51 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command @"
`$env:USERPROFILE='$fake'; `$env:CLAUDE_PLUGIN_ROOT='$plugin'
& '$plugin\hooks\session-check.ps1'
"@ 2>&1 | Out-Null
    -not (Test-Path -LiteralPath $slow)
}

Check '훅이 스스로 오류를 남기지 않았다' {
    -not (Test-Path -LiteralPath (Join-Path $fake '.claude\kw-control-tower.error'))
}

Remove-Item -LiteralPath $fake -Recurse -Force -ErrorAction SilentlyContinue

# --- 맞춤이 미리보기에서 아무것도 안 바꾼다 --------------------------------
Write-Host ''
Write-Host '맞춤의 미리보기'
$syncSrc = Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw
Check '미리보기가 한 일처럼 적지 않는다' { $syncSrc -match '안 함 · 미리보기' }
Check '안 깔린 것에만 install 을 쓴다'    { $syncSrc -match "if \(-not \`$onDisk\)" -and $syncSrc -match "'plugin', 'enable'" }
# 파이썬을 다루는 걸음은 없을 때 알아듣게 말하는데 클로드를 다루는 걸음은 셸
# 오류를 그대로 뱉고 있었다. 같은 규율을 건다.
Check '클로드를 이름이 아니라 찾아 둔 경로로 부른다' {
    ($syncSrc -match '\$script:ClaudeExe = \(Get-Command claude') -and
    ($syncSrc -match '& \$script:ClaudeExe @ClaudeArgs') -and
    ($syncSrc -notmatch '& claude @ClaudeArgs')
}
Check '클로드가 없으면 무엇이 없는지 말한다' { $syncSrc -match '클로드 코드를 못 찾았습니다' }
Check '되켠 것을 따로 적는다'              { $syncSrc -match '되켠 것' }
# "한 번 돌았다" 표시는 권장 플러그인 갈래를 영영 닫는다. 첫 실행이 실패했는데도
# 적어 버리면 사용자가 영영 모른 채 그 플러그인 없이 지낸다.
Check '권장을 다 못 깔면 한 번 돌았다를 안 적는다' {
    ($syncSrc -match '\$script:SuggestedIncomplete = \$true') -and
    ($syncSrc -match 'if \(-not \$script:SuggestedIncomplete\) \{ \$state\[''ranOnce''\]')
}
Check '스킬 이름을 허용 목록으로 막는다'    { $syncSrc -match "\^\[A-Za-z0-9\._-\]\+\$" }
Check '지우기 전에 사본을 뜬다'            { $syncSrc -match 'Copy-Item' -and $syncSrc -match 'kw-control-tower-backups' }
Check '삭제 판정이 세 조건을 함께 본다'     { $syncSrc -match "\`$subdirs\.Count -eq 0\) -and \(\`$files\.Count -eq 1\) -and \(\`$files\[0\]\.Name -eq 'SKILL\.md'\)" }

# --- 목록 파일의 계약 -------------------------------------------------------
Write-Host ''
Write-Host '목록 파일'
$mf = Get-Content (Join-Path $plugin 'manifest.json') -Raw | ConvertFrom-Json
Check '필수 플러그인의 배포처가 목록에 등록되어 있다' {
    $mkNames = @($mf.marketplaces | ForEach-Object { $_.name })
    @($mf.required | Where-Object { $mkNames -notcontains ($_ -split '@')[1] }).Count -eq 0
}
Check '정리 항목마다 언제 넣었는지 적혀 있다' {
    $all = @($mf.retiredPlugins) + @($mf.retiredMarketplaces) + @($mf.retiredSkills) + @($mf.retiredHooks)
    @($all | Where-Object { -not $_.since }).Count -eq 0
}
Check '은퇴 훅은 이름과 경로를 함께 갖는다' {
    @($mf.retiredHooks | Where-Object { -not $_.file -or -not $_.pathContains }).Count -eq 0
}
# 읽히는 것과 형식이 맞는 것은 다르다. 키 이름을 하나 잘못 적으면 JSON 으로는
# 읽히고 그 목록만 조용히 비어, 아무것도 안 하고 성공으로 끝난다.
$manifestKeys = @('marketplaces','required','suggested','retiredPlugins','retiredMarketplaces','retiredSkills','retiredHooks')
Check '목록 파일에 있어야 할 칸이 다 있다' {
    @($manifestKeys | Where-Object { $null -eq $mf.PSObject.Properties[$_] }).Count -eq 0
}
Check '맞춤이 칸이 빠진 목록에서 멈춘다' {
    @($manifestKeys | Where-Object { $syncSrc -notmatch [regex]::Escape("'$_'") }).Count -eq 0 -and
    ($syncSrc -match '목록 파일에 칸이 빠졌습니다')
}
Check '알림도 칸이 빠진 목록에서 물러난다' { $hookCode -match "목록 파일에 '\`$k' 칸이 없습니다" }

$badManifest = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-bad-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path $badManifest | Out-Null
Check '칸이 빠진 목록으로는 알림이 아무 말도 안 한다' {
    '{ "marketplaces": [], "required": [] }' | Set-Content -LiteralPath (Join-Path $badManifest 'manifest.json')
    $out = & $ps51 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$env:USERPROFILE'; `$env:CLAUDE_PLUGIN_ROOT='$badManifest'; & '$plugin\hooks\session-check.ps1'" 2>&1
    [string]::IsNullOrWhiteSpace(($out | Out-String).Trim())
}
Remove-Item -LiteralPath $badManifest -Recurse -Force -ErrorAction SilentlyContinue
# 이 마켓플레이스는 자기 레포 안의 것만 낸다. 외부 레포를 플러그인 원본으로
# 가리키면 SSH 로 클론해 사내 PC 에서 실패하는 것을 2026-09-06 에 확인했다.
Check '마켓플레이스가 외부 레포를 원본으로 안 가리킨다' {
    $mk = Get-Content (Join-Path $repo '.claude-plugin\marketplace.json') -Raw | ConvertFrom-Json
    @($mk.plugins | Where-Object { $_.source -isnot [string] -or -not $_.source.StartsWith('./') }).Count -eq 0
}
# 먼저 걷고 설치가 실패하면 그 플러그인이 아예 없는 PC 가 된다. 실제로 그렇게
# 됐던 자리라 계약으로 못 박는다.
Check '정리할 플러그인에는 대체자가 적혀 있다' {
    @($mf.retiredPlugins | Where-Object { -not $_.replacedBy }).Count -eq 0
}
Check '맞춤이 대체를 확인한 뒤에 걷는다' {
    $syncSrc -match '대체할 \$by 가 아직 안 깔려 있어'
}

# --- python3 가드 -----------------------------------------------------------
Write-Host ''
Write-Host 'python3 가드'
$guard = Join-Path $plugin 'hooks\python3-guard.ps1'
$fake2 = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-g-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path (Join-Path $fake2 '.claude') | Out-Null

function Invoke-Guard {
    param([string]$Command, [string]$Verdict = 'redirector')
    if ($Verdict) {
        "python3=$Verdict`r`npython3Target=C:\stub\AppInstallerPythonRedirector.exe" |
            Set-Content -LiteralPath (Join-Path $fake2 '.claude\kw-control-tower.state')
    } else {
        Remove-Item -LiteralPath (Join-Path $fake2 '.claude\kw-control-tower.state') -ErrorAction SilentlyContinue
    }
    $payload = @{ tool_name = 'Bash'; tool_input = @{ command = $Command } } | ConvertTo-Json -Compress
    return ($payload | & $ps51 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$fake2'; & '$guard'" 2>&1 | Out-String)
}

Check '맨 앞의 python3 을 막는다'            { (Invoke-Guard 'python3 -c "print(1)"') -match 'deny' }
Check '판정이 안내판이 아니면 안 막는다'      { -not ((Invoke-Guard 'python3 -c "print(1)"' 'real') -match 'deny') }
Check '아직 안 쟀으면 안 막는다'              { -not ((Invoke-Guard 'python3 -c "print(1)"' '') -match 'deny') }
Check 'python 은 안 막는다'                   { -not ((Invoke-Guard 'python -c "print(1)"') -match 'deny') }
Check 'py -3 은 안 막는다'                    { -not ((Invoke-Guard 'py -3 -c "print(1)"') -match 'deny') }
Check 'python312 처럼 이름이 다르면 안 막는다' { -not ((Invoke-Guard 'python312 -V') -match 'deny') }
Check 'python3.12 도 안 막는다'                { -not ((Invoke-Guard 'python3.12 -V') -match 'deny') }
Check 'wsl 안의 python3 은 안 막는다'          { -not ((Invoke-Guard 'wsl python3 -c "print(1)"') -match 'deny') }
Check 'docker exec 안의 python3 도 안 막는다'  { -not ((Invoke-Guard 'docker exec c python3 -V') -match 'deny') }
Check '따옴표 안의 python3 은 안 막는다'       { -not ((Invoke-Guard 'echo "run python3 later"') -match 'deny') }
Check '파이프 뒤의 python3 은 막는다'          { (Invoke-Guard 'cat x | python3 -') -match 'deny' }
Check '앞에 VAR=값 이 붙어도 막는다'           { (Invoke-Guard 'FOO=1 python3 -V') -match 'deny' }

Remove-Item -LiteralPath $fake2 -Recurse -Force -ErrorAction SilentlyContinue

# --- 사용자 파일을 쓸 때 ----------------------------------------------------
Write-Host ''
Write-Host '사용자 파일 쓰기'
# settings.json 은 사용자 파일이다. 통째로 다시 쓰므로 셋을 지켜야 한다.
Check '고치기 전에 사본을 남긴다'        { $syncSrc.Contains('Copy-Item -LiteralPath $Path -Destination "$Path.bak"') }
Check '다시 안 읽힐 것은 안 쓴다'        { $syncSrc.Contains('$null = $json | ConvertFrom-Json') }
Check '5.1 이 만든 이스케이프를 되돌린다' { $syncSrc.Contains("[regex]::Replace(`$json, '\\u([0-9a-fA-F]{4})'") }
Check '임시 파일에 쓰고 옮긴다'          { $syncSrc -match '\$Path\.kwtmp' -and $syncSrc -match 'Move-Item' }
Check 'BOM 없이 쓴다'                    { $syncSrc -match 'UTF8Encoding\(\$false\)' }
# 없는 것과 못 읽는 것은 다르다. 삼키면 망가진 설정을 가진 PC 에서 맞춤이
# 아무것도 안 하고 "바꾼 것이 없습니다" 라고 말한다.
Check '못 읽는 JSON 은 삼키지 않고 던진다' {
    ($syncSrc -match 'catch \{ throw "JSON 으로 안 읽힙니다') -and
    ($hookCode -match 'catch \{ throw "JSON 으로 안 읽힙니다')
}

$brokenHome = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-brk-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path (Join-Path $brokenHome '.claude\plugins') | Out-Null
'{ not json' | Set-Content -LiteralPath (Join-Path $brokenHome '.claude\settings.json')
Check '망가진 설정에서 알림은 조용하고 자국을 남긴다' {
    $out = & $ps51 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$brokenHome'; `$env:CLAUDE_PLUGIN_ROOT='$plugin'; & '$plugin\hooks\session-check.ps1'" 2>&1
    ([string]::IsNullOrWhiteSpace(($out | Out-String).Trim())) -and
    (Test-Path -LiteralPath (Join-Path $brokenHome '.claude\kw-control-tower.error'))
}
Remove-Item -LiteralPath $brokenHome -Recurse -Force -ErrorAction SilentlyContinue

# --- /kw-sync 명령 ----------------------------------------------------------
Write-Host ''
Write-Host '/kw-sync 명령'
$cmdSrc = Get-Content (Join-Path $plugin 'commands\kw-sync.md') -Raw
Check '설명이 앞머리에 있다'            { $cmdSrc -match '(?s)^---\s*\r?\ndescription:' }
# 플러그인이 나르는 명령은 언제나 '플러그인이름:명령이름' 으로 불린다. 알림이 짧은
# 이름을 적으면 사용자가 없는 명령을 친다.
Check '알림이 온전한 명령 이름을 말한다' { $hookCode.Contains('/kw-control-tower:kw-sync') }
Check '알림이 짧은 이름을 안 쓴다'        { -not ($hookCode -match '(?<!tower:)(?<!-)/kw-sync') }
Check '맞춤 스크립트를 부른다'          { $cmdSrc -match 'scripts/sync\.ps1' }
Check '미리보기 방법을 적어 둔다'        { $cmdSrc -match '\-WhatIfOnly' }
Check '되켠 것을 말하라고 적혀 있다'      { $cmdSrc -match '되켠 것' }
# 명령과 스킬이 같은 말을 두 곳에서 하면 곧 어긋난다. 부르는 자리는 명령 하나다.
Check '같은 이름의 스킬이 남아 있지 않다' { -not (Test-Path -LiteralPath (Join-Path $plugin 'skills\kw-sync')) }

# --- 도커 인증서 안내 -------------------------------------------------------
Write-Host ''
Write-Host '도커 인증서 안내'
$dockerHook = Join-Path $plugin 'hooks\docker-cert-reminder.ps1'
$dockerSrc  = Get-Content $dockerHook -Raw
# 옛 설치기는 번들이 없는 PC 에 이 훅을 아예 안 걸었다. 플러그인 훅은 배선이 PC 마다
# 갈리지 않으므로 그 판정을 훅 자신이 해야 한다.
Check '번들이 없으면 아무 말도 안 한다' { $dockerSrc -match "ca-bundle\.pem'\)\)\) \{ exit 0 \}" }
Check '어떤 경우에도 호출을 안 막는다'   { $dockerSrc -notmatch "permissionDecision" }

$noBundle = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-nb-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path $noBundle | Out-Null
Check '번들 없는 PC 에서 실제로 조용하다' {
    $payload = @{ tool_name = 'Bash'; tool_input = @{ command = 'docker run alpine' } } | ConvertTo-Json -Compress
    $out = $payload | & $ps51 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:LOCALAPPDATA='$noBundle'; & '$dockerHook'" 2>&1
    [string]::IsNullOrWhiteSpace(($out | Out-String).Trim())
}
Check '번들 있는 PC 에서는 말한다' {
    New-Item -ItemType Directory -Force -Path (Join-Path $noBundle 'corp-certs') | Out-Null
    Set-Content -LiteralPath (Join-Path $noBundle 'corp-certs\ca-bundle.pem') -Value '# stand-in'
    $payload = @{ tool_name = 'Bash'; tool_input = @{ command = 'docker run alpine' } } | ConvertTo-Json -Compress
    $out = $payload | & $ps51 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:LOCALAPPDATA='$noBundle'; & '$dockerHook'" 2>&1
    ($out | Out-String) -match 'additionalContext'
}
Remove-Item -LiteralPath $noBundle -Recurse -Force -ErrorAction SilentlyContinue

# --- CLAUDE.md 걸음 ---------------------------------------------------------
Write-Host ''
Write-Host 'CLAUDE.md 걸음'
# 접두로 찾는다는 것은 마커 뒤 괄호 문구가 바뀌어도 같은 블록으로 알아본다는 뜻이다.
# 전체 줄 일치로 찾으면 옛 문구를 못 찾고 블록을 하나 더 붙인다.
Check '마커를 접두로 찾는다'          { $syncSrc.Contains('^#\s*BEGIN AX\b') -and $syncSrc.Contains('^#\s*END AX[^\r\n]*') }
Check '마커 바깥은 안 건드린다'        { $syncSrc -match '마커 바깥은 안 건드렸습니다' }
Check '고치기 전에 사본을 뜬다'        { $syncSrc -match '\$target\.bak' }
Check '잠금 폴더 이름을 상대와 맞춘다' { $syncSrc -match '\$target\.lock' -and $syncSrc -match "lock\.gate" }
Check '오래 잡힌 잠금은 빼앗는다'      { $syncSrc -match 'heldsince' -and $syncSrc -match '\-ge 10' }
Check '남의 잠금은 안 지운다'          { $syncSrc -match "\`$owner -eq \`$token" }
Check '줄바꿈을 대상 파일에 맞춘다'    { $syncSrc -match '\$nl' }

# --- 문서와 코드를 맞댄다 ---------------------------------------------------
Write-Host ''
Write-Host '문서와 코드'
# 설계 문서가 걸음을 일곱으로 세는데 코드가 여덟인 적이 있었다. 사람이 셀 일이
# 아니라 맞대면 되는 일이다.
$spec = Get-Content (Join-Path $repo 'docs\superpowers\specs\2026-09-06-control-tower-design.md') -Raw
$readme = Get-Content (Join-Path $repo 'README.md') -Raw

$codeSteps = @([regex]::Matches($syncSrc, "(?m)^Write-Host '(\d+)\.")) | ForEach-Object { [int]$_.Groups[1].Value }
Check '맞춤의 걸음 번호가 1부터 빠짐없이 이어진다' {
    ($codeSteps.Count -gt 0) -and (@(1..$codeSteps.Count | Where-Object { $codeSteps -notcontains $_ }).Count -eq 0)
}
Check '설계 문서가 코드와 같은 수로 센다' {
    $m = [regex]::Match($spec, '걸음 (\S+)이고 각각 독립이며 멱등이다')
    $words = @{ '넷'=4; '다섯'=5; '여섯'=6; '일곱'=7; '여덟'=8; '아홉'=9; '열'=10 }
    $m.Success -and $words[$m.Groups[1].Value] -eq $codeSteps.Count
}
Check '설계 문서의 걸음 목록이 코드와 같은 수다' {
    $body = [regex]::Match($spec, "(?s)## 맞춤이 고친다.*?(?=`r?`n## )").Value
    @([regex]::Matches($body, '(?m)^\d+\. \*\*')).Count -eq $codeSteps.Count
}
Check 'README 가 코드와 같은 수로 센다' {
    $m = [regex]::Match($readme, '걸음이 (\S+)이고')
    $words = @{ '넷'=4; '다섯'=5; '여섯'=6; '일곱'=7; '여덟'=8; '아홉'=9; '열'=10 }
    $m.Success -and $words[$m.Groups[1].Value] -eq $codeSteps.Count
}
# 알림이 부르라고 하는 명령이 실제로 있는 파일이어야 한다.
Check '알림이 가리키는 명령 파일이 실재한다' {
    $m = [regex]::Match($hookCode, '/([a-z0-9-]+):([a-z0-9-]+) 를 실행')
    $m.Success -and (Test-Path -LiteralPath (Join-Path $plugin ("commands\" + $m.Groups[2].Value + ".md")))
}
Check '알림이 가리키는 플러그인 이름이 자기 이름과 같다' {
    $m = [regex]::Match($hookCode, '/([a-z0-9-]+):([a-z0-9-]+) 를 실행')
    $pj = Get-Content (Join-Path $plugin '.claude-plugin\plugin.json') -Raw | ConvertFrom-Json
    $m.Success -and $m.Groups[1].Value -eq $pj.name
}

# --- 결과 -----------------------------------------------------------------
Write-Host ''
if ($script:FailList.Count -eq 0) {
    Write-Host "통과 $($script:Pass) 건, 실패 없음" -ForegroundColor Green
    exit 0
}
Write-Host "통과 $($script:Pass) 건, 실패 $($script:FailList.Count) 건" -ForegroundColor Red
foreach ($f in $script:FailList) { Write-Host "  - $f" }
exit 1
