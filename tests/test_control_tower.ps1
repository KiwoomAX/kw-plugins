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
    'skills\kw-sync\SKILL.md',
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
    $j.hooks.SessionStart[0].hooks[0].command -match 'powershell\.exe'
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
    # Out-File 은 느림 자국과 오류 자국 둘뿐이고 나머지 쓰기 명령은 없어야 한다.
    $writes = [regex]::Matches($hookCode, 'Out-File')
    ($writes.Count -eq 2) -and ($hookCode -notmatch 'Set-Content|Remove-Item|New-Item|Move-Item|Copy-Item')
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
Check '되켠 것을 따로 적는다'              { $syncSrc -match '되켠 것' }
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

# --- 결과 -----------------------------------------------------------------
Write-Host ''
if ($script:FailList.Count -eq 0) {
    Write-Host "통과 $($script:Pass) 건, 실패 없음" -ForegroundColor Green
    exit 0
}
Write-Host "통과 $($script:Pass) 건, 실패 $($script:FailList.Count) 건" -ForegroundColor Red
foreach ($f in $script:FailList) { Write-Host "  - $f" }
exit 1
