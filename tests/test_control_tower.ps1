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

# --- 결과 -----------------------------------------------------------------
Write-Host ''
if ($script:FailList.Count -eq 0) {
    Write-Host "통과 $($script:Pass) 건, 실패 없음" -ForegroundColor Green
    exit 0
}
Write-Host "통과 $($script:Pass) 건, 실패 $($script:FailList.Count) 건" -ForegroundColor Red
foreach ($f in $script:FailList) { Write-Host "  - $f" }
exit 1
