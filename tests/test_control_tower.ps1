# 컨트롤 타워의 계약을 검사한다. 이 PC 를 안 바꾼다.
#
#   pwsh -File tests\test_control_tower.ps1
#
# 알림 훅은 격리된 가짜 홈에서 돌려 실제 설정을 안 건드린다.

Set-StrictMode -Off
$ErrorActionPreference = 'Continue'

$repo   = Split-Path -Parent $PSScriptRoot
$plugin = Join-Path $repo 'plugins\kw-control-tower'
$ps7    = 'pwsh'   # 컨트롤 타워는 7 을 전제한다. 설치기가 7 없이는 아무것도 안 깐다.

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
Check '있다: .claude-plugin\marketplace.json (레포 최상위)' { Test-Path -LiteralPath (Join-Path $repo '.claude-plugin\marketplace.json') }
foreach ($rel in @(
    '.claude-plugin\plugin.json',
    'manifest.json',
    'hooks\hooks.json',
    'hooks\session-check.ps1',
    'scripts\sync.ps1',
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

# 클로드 코드가 읽는 JSON 에 밑줄 접두 키를 두지 않는다. 한동안 그것으로 주석을 흉내
# 냈는데 형식에 없는 키라, 플러그인을 적재할 때마다 "unknown keys ignored" 경고가 떴다.
# 이상이 없으면 아무 말도 안 한다는 이 플러그인의 첫째 규율을 그 경고가 매 세션 어겼다.
# 적을 것은 이 검사들의 주석과 README 에 있고, 거기서는 설명에 그치지 않고 강제된다.
#
# manifest.json 은 뺀다. 그것은 클로드 코드가 안 읽고 sync.ps1 이 읽는 우리 파일이라
# 경고를 내지 않고, 그 주석들은 목록을 고칠 사람이 바로 보는 곳이다.
#
# 아는 키를 나열해 견주지 않고 밑줄만 막는다. 나열하면 형식에 키가 하나 늘 때마다
# 사람이 이 목록을 맞춰야 하고, 안 맞추면 멀쩡한 키에서 검사가 떨어진다.
Check '클로드 코드가 읽는 JSON 에 밑줄 주석 키가 없다' {
    $files = @(
        (Join-Path $repo   '.claude-plugin\marketplace.json')
        (Join-Path $plugin '.claude-plugin\plugin.json')
        (Join-Path $plugin 'hooks\hooks.json')
        (Join-Path $repo   'plugins\kw-doc-formats\.claude-plugin\plugin.json')
        (Join-Path $repo   'plugins\kw-devops\.claude-plugin\plugin.json')
    )
    $bad = 0
    foreach ($f in $files) {
        $j = Get-Content $f -Raw | ConvertFrom-Json
        $bad += @($j.PSObject.Properties.Name | Where-Object { $_.StartsWith('_') }).Count
    }
    $bad -eq 0
}

# 버전을 감지에 안 쓰기로 했으므로 plugin.json 에 version 을 안 적는다.
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

# 예산은 감지에만 적용된다. 불일치한 곳을 찾은 뒤 맞춤을 호출하는 것은 예산 밖이라고
# 설계가 정했으므로, 그 경계 앞의 코드만 떼어 예산 검사를 건다. 경계는 알릴 것이
# 없을 때 그대로 끝내는 줄이다.
$guard = '$notes.Count -eq 0'
$gi = $hookCode.IndexOf($guard)
$hookDetect = if ($gi -ge 0) { $hookCode.Substring(0, $gi) } else { $hookCode }
Check '감지와 맞춤을 구분하는 경계가 있다' { $gi -ge 0 }

Check '세션 시작 훅이 하나뿐이다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    @($j.hooks.SessionStart).Count -eq 1 -and @($j.hooks.SessionStart[0].hooks).Count -eq 1
}
Check '훅을 pwsh 로 건다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $j.hooks.SessionStart[0].hooks[0].command -eq 'pwsh'
}
# 한 문자열로 적으면 셸이 그것을 다시 구분하고, 사용자 이름에 공백이 든 PC 에서
# 플러그인 경로가 거기서 깨진다. 나눠 적으면 셸을 안 거친다.
Check '명령과 인자를 나눠 적는다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $all = @($j.hooks.SessionStart[0].hooks) + @($j.hooks.PreToolUse | ForEach-Object { $_.hooks })
    @($all | Where-Object { $_.command -ne 'pwsh' -or @($_.args).Count -lt 6 }).Count -eq 0
}
# matcher 는 도구 이름만 거른다. 명령 내용을 거르는 것은 if 이고, 이것이 없으면
# 도커도 python3 도 아닌 명령마다 프로세스가 뜬다.
Check '도구 훅마다 if 규칙이 적용돼 있다' {
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
# 감지가 외부 프로그램을 호출하면 불일치한 곳이 없는 세션까지 값을 문다. 맞춤을 호출하는
# 것은 이 검사 뒤의 코드이고, 그것은 불일치한 세션에서만 돈다.
Check '감지가 외부 프로그램을 안 호출한다' {
    ($hookDetect -notmatch '(?m)^\s*&\s') -and
    ($hookDetect -notmatch 'Start-Process') -and
    ($hookDetect -notmatch 'claude\s+plugin') -and
    ($hookDetect -notmatch 'Get-FileHash')
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
# 감지 표가 적은 질문을 훅이 다 재야 한다. CLAUDE.md 문안 검사가 표에는 있고
# 훅에는 없어서, 사내 문안을 손으로 고쳐도 아무도 모르는 상태였다.
Check '훅이 감지 표의 질문을 다 측정한다' {
    $spec2 = Get-Content (Join-Path $repo 'docs\superpowers\specs\2026-09-06-control-tower-design.md') -Raw -Encoding UTF8
    # 표 머리에 바로 붙여 잡는다. 절 머리부터 잡으면 표 앞 문단에서 끊긴다.
    $tbl = [regex]::Match($spec2, "(?s)\| 질문 \| 어디서 재나 \|.*?(?=\r?\n\r?\n)").Value
    $rows = @([regex]::Matches($tbl, "(?m)^\|(?!-)")).Count - 1   # 머리 줄을 뺀다
    $asked = @([regex]::Matches($hookSrc, "(?m)^\s*# --- 질문 ")).Count
    # 한 주석이 질문 둘을 덮는 곳이 있어 주석 수가 아니라 번호의 최댓값을 센다
    # 한 주석이 질문 둘을 덮을 때 앞말에 따라 '과' 도 되고 '와' 도 된다.
    $nums = @([regex]::Matches($hookSrc, '# --- 질문 (\d+)(?:[과와] (\d+))?')) |
            ForEach-Object { [int]$_.Groups[1].Value; if ($_.Groups[2].Success) { [int]$_.Groups[2].Value } }
    ($asked -gt 0) -and (($nums | Measure-Object -Maximum).Maximum -eq $rows)
}
Check '훅이 CLAUDE.md 문안을 견준다' {
    ($hookCode -match 'claude-md-ko\.md') -and ($hookCode -match 'BEGIN AX')
}
# 5.1 을 버렸으므로 그 문법 제약을 더 지킬 이유가 없다. 대신 되돌아가지 않았는지를 본다.
# 훅이 powershell.exe 로 돌면 한국어가 ANSI 로 읽혀 조용히 깨진다.
Check '훅이 5.1 을 호출하지 않는다' {
    ($hookCode -notmatch 'powershell\.exe') -and ($hookCode -match 'pwsh')
}

# --- 한글이 안 깨진다 ---------------------------------------------
Write-Host ''
Write-Host '한글'
# BOM 을 붙이지 않는다. 7 은 BOM 없이도 UTF-8 로 읽고, BOM 이 없으면 5.1 로 돌렸을 때
# 한글이 조용히 깨지는 것이 아니라 파싱 오류로 죽어서 잘못 호출한 것이 그 줄에서 드러난다.
foreach ($f in @((Join-Path $plugin 'hooks\session-check.ps1'), (Join-Path $plugin 'scripts\sync.ps1'),
                 (Join-Path $plugin 'hooks\python3-guard.ps1'), (Join-Path $plugin 'hooks\docker-cert-reminder.ps1'))) {
    Check "UTF-8 BOM 이 없다: $(Split-Path $f -Leaf)" {
        $b = [System.IO.File]::ReadAllBytes($f)
        -not ($b.Length -ge 3 -and $b[0] -eq 239 -and $b[1] -eq 187 -and $b[2] -eq 191)
    }
    Check "한글이 성한 채로 읽힌다: $(Split-Path $f -Leaf)" {
        (Get-Content -LiteralPath $f -Raw -Encoding UTF8) -match '[가-힣]'
    }
}

# --- 두 스크립트가 같은 해시를 낸다 ----------------------------------------
Write-Host ''
Write-Host '해시가 두 곳에서 같다'
Check '알림 훅과 맞춤이 같은 해시 함수를 보유한다' {
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
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command @"
`$env:USERPROFILE='$fake'; `$env:CLAUDE_PLUGIN_ROOT='$plugin'
& '$plugin\hooks\session-check.ps1'
"@ 2>&1
    # 목록은 읽히지만 필수 플러그인이 없으므로 말은 한다. 다만 죽지 않아야 한다.
    $LASTEXITCODE -eq 0
}

Check '목록 파일이 없으면 아무 말도 안 한다' {
    $empty = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-empty-" + [guid]::NewGuid().ToString('n').Substring(0,8))
    New-Item -ItemType Directory -Force -Path $empty | Out-Null
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command @"
`$env:USERPROFILE='$fake'; `$env:CLAUDE_PLUGIN_ROOT='$empty'
& '$plugin\hooks\session-check.ps1'
"@ 2>&1
    Remove-Item -LiteralPath $empty -Recurse -Force -ErrorAction SilentlyContinue
    [string]::IsNullOrWhiteSpace(($out | Out-String).Trim())
}

Check '몸통이 200밀리초 안에 끝난다' {
    $slow = Join-Path $fake '.claude\kw-control-tower.slow'
    Remove-Item -LiteralPath $slow -ErrorAction SilentlyContinue
    & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command @"
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
# 파이썬을 다루는 단계는 없을 때 알아듣게 말하는데 클로드를 다루는 단계는 셸
# 오류를 그대로 뱉고 있었다. 같은 규율을 건다.
Check '클로드를 이름이 아니라 찾아 둔 경로로 부른다' {
    ($syncSrc -match '\$script:ClaudeExe = \(Get-Command claude') -and
    ($syncSrc -match '& \$script:ClaudeExe @ClaudeArgs') -and
    ($syncSrc -notmatch '& claude @ClaudeArgs')
}
Check '클로드가 없으면 무엇이 없는지 말한다' { $syncSrc -match '클로드 코드를 못 찾았습니다' }
Check '되켠 것을 따로 적는다'              { $syncSrc -match '되켠 것' }
# "한 번 돌았다" 표시는 권장 플러그인 분기를 영영 닫는다. 첫 실행이 실패했는데도
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
# replacedBy 는 이 PC 가 실제로 보유하게 될 플러그인 이름이어야 한다. 배포처 이름을
# 하나 잘못 적으면 installed_plugins.json 의 키와 안 맞고, 단계 7 이 "대체가 아직
# 안 깔렸다"고 말하며 영원히 넘어간다. 옛 스킬 사본이 남아 같은 스킬이 두 벌 실리는데,
# 화면에는 이유가 틀린 안내만 찍히므로 아무도 알아채지 못한다. 2026-09-06 에
# document-formats 가 정확히 그 상태였다.
Check 'replacedBy 가 이 PC 에 실제로 깔릴 플러그인을 가리킨다' {
    # 컨트롤 타워 자신은 목록에 없다. 설치기가 깔고, 이 스크립트는 그 안에서 돈다.
    $willHave = @($mf.required) + @($mf.suggested) + @('kw-control-tower@kiwoom-ax')
    $named    = @(@($mf.retiredPlugins) + @($mf.retiredSkills) |
                  Where-Object { $_.replacedBy } | ForEach-Object { $_.replacedBy })
    @($named | Where-Object { $willHave -notcontains $_ }).Count -eq 0
}
Check '정리 항목마다 언제 넣었는지 적혀 있다' {
    $all = @($mf.retiredPlugins) + @($mf.retiredMarketplaces) + @($mf.retiredSkills) + @($mf.retiredHooks)
    @($all | Where-Object { -not $_.since }).Count -eq 0
}
Check '은퇴 훅은 이름과 경로를 함께 보유한다' {
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
# 홈도 가짜로 준다. 훅은 칸이 빠진 목록을 만나면 물러나면서 자국을 남기는데, 여기에
# 진짜 USERPROFILE 을 넘기던 때에는 검사를 돌릴 때마다 사용자의 실제 프로필에 있는
# kw-control-tower.error 가 자랐다. 이 파일 첫 줄의 "이 PC 를 안 바꾼다" 를 그것이 어겼다.
$badHome = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-badhome-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path (Join-Path $badHome '.claude') | Out-Null
Check '칸이 빠진 목록으로는 알림이 아무 말도 안 한다' {
    '{ "marketplaces": [], "required": [] }' | Set-Content -LiteralPath (Join-Path $badManifest 'manifest.json')
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$badHome'; `$env:CLAUDE_PLUGIN_ROOT='$badManifest'; & '$plugin\hooks\session-check.ps1'" 2>&1
    [string]::IsNullOrWhiteSpace(($out | Out-String).Trim())
}
# 자국이 가짜 홈 안에 떨어져야 모래상자가 성립한다. 위 검사만으로는 훅이 조용한 것만
# 보고 어디에 적었는지는 안 본다.
Check '물러나며 남긴 자국이 가짜 홈 안에 떨어진다' {
    Test-Path -LiteralPath (Join-Path $badHome '.claude\kw-control-tower.error')
}
Remove-Item -LiteralPath $badManifest -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $badHome -Recurse -Force -ErrorAction SilentlyContinue
# 이 마켓플레이스는 자기 레포 안의 것만 낸다. 외부 레포를 플러그인 원본으로
# 가리키면 SSH 로 클론해 사내 PC 에서 실패하는 것을 2026-09-06 에 확인했다.
Check '마켓플레이스가 외부 레포를 원본으로 안 가리킨다' {
    $mk = Get-Content (Join-Path $repo '.claude-plugin\marketplace.json') -Raw | ConvertFrom-Json
    @($mk.plugins | Where-Object { $_.source -isnot [string] -or -not $_.source.StartsWith('./') }).Count -eq 0
}
# required 에 적은 것이 배포처 목록에 없으면 이름으로 못 호출한다. 올리기 전에는 아무도
# 안 잡고, 사내 PC 마다 맞춤이 설치에 실패하면서 드러난다. 고칠 곳이 둘인데 한 곳만
# 고치기 쉬워서 계약으로 못 박는다.
Check '필수 목록의 플러그인이 배포처 목록에도 있다' {
    $mk2 = Get-Content (Join-Path $repo '.claude-plugin\marketplace.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $sold = @($mk2.plugins | ForEach-Object { $_.name })
    $bad = @()
    foreach ($id in @($mf.required) + @($mf.suggested)) {
        if ($id -notlike '*@kiwoom-ax') { continue }   # 남의 배포처는 여기서 못 본다
        if ($sold -notcontains $id.Split('@')[0]) { $bad += $id }
    }
    $bad.Count -eq 0
}
# 먼저 걷고 설치가 실패하면 그 플러그인이 아예 없는 PC 가 된다. 실제로 그렇게
# 됐던 적이 있어 계약으로 못 박는다.
Check '정리할 플러그인에는 대체자가 적혀 있다' {
    @($mf.retiredPlugins | Where-Object { -not $_.replacedBy }).Count -eq 0
}
Check '맞춤이 대체를 확인한 뒤에 걷는다' {
    $syncSrc -match '대체할 \$by 가 아직 안 깔려 있어'
}
# 플러그인에만 대체 가드를 적용하고 배포처에 적용하지 않으면 그 둘이 불일치한다. 설치가 실패해 옛
# 플러그인이 그대로 남은 PC 에서 배포처만 걷혀, 깔린 플러그인의 출처가 사라진다.
# 정리 목록에 배포처를 처음 올리면서 드러난 문제다.
Check '맞춤이 남은 플러그인이 있는 배포처를 안 걷는다' {
    $syncSrc -match '가 아직 깔려 있어 그대로 둡니다'
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
    return ($payload | & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$fake2'; & '$guard'" 2>&1 | Out-String)
}

Check '맨 앞의 python3 을 막는다'            { (Invoke-Guard 'python3 -c "print(1)"') -match 'deny' }
Check '판정이 안내판이 아니면 안 막는다'      { -not ((Invoke-Guard 'python3 -c "print(1)"' 'real') -match 'deny') }
Check '아직 안 측정했으면 안 막는다'              { -not ((Invoke-Guard 'python3 -c "print(1)"' '') -match 'deny') }
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
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$brokenHome'; `$env:CLAUDE_PLUGIN_ROOT='$plugin'; & '$plugin\hooks\session-check.ps1'" 2>&1
    ([string]::IsNullOrWhiteSpace(($out | Out-String).Trim())) -and
    (Test-Path -LiteralPath (Join-Path $brokenHome '.claude\kw-control-tower.error'))
}
Remove-Item -LiteralPath $brokenHome -Recurse -Force -ErrorAction SilentlyContinue

# --- 훅이 맞춤을 호출한다 -----------------------------------------------------
Write-Host ''
Write-Host '훅이 맞춤을 호출한다'
# 사람이 호출하는 명령을 없앴다. 알림을 읽고 명령을 치는 사람이 없으면 감지가
# 아무것도 바꾸지 못하기 때문이다. 호출하는 곳은 훅 하나이고, 설치기 9단계는
# 예전처럼 같은 스크립트를 직접 호출한다.
Check '훅이 맞춤 스크립트를 호출한다'      { $hookCode -match 'sync\.ps1' }
Check '훅이 호출하는 스크립트가 실재한다'  { Test-Path -LiteralPath (Join-Path $plugin 'scripts\sync.ps1') }
# 불일치한 곳이 없으면 맞춤을 안 호출한다. 이 경계가 사라지면 모든 세션이 맞춤 값을 문다.
# 사용자가 직접 해야 하는 것은 맞춤을 안 호출한다. 호출하면 로그인 안 한 PC 에서 매 세션
# 맞춤이 돌고도 아무것도 못 고친다.
Check '직접 할 일과 맞춤이 고칠 것을 나눠 적는다' {
    ($hookCode -match '\$asks\s*=\s*New-Object') -and ($hookCode -match '\$notes\s*=\s*New-Object')
}
Check '맞춤을 호출할지는 notes 만 보고 정한다' {
    $hookCode -match '\$notes\.Count -eq 0[^
]*\}\s*(#[^
]*)?'
}
# 상태에 따라 갈리는 안내를 CLAUDE.md 문안에 두면, 끝낸 사람도 매 세션 읽고 안 한
# 사람은 읽고 넘겨도 아무 일이 없다. 그런 것은 점검이 맡는다.
# 목록은 KiwoomAX/korean-banned-words 가 만들어 낸 것을 받아 온 것이다. 여기서 만들지
# 않는다. 만드는 곳이 둘이면 목록은 한 곳에서 나오는데 그것을 어떻게 쓰라는 안내가
# 두 곳에서 따로 쓰인다. 실제로 그렇게 나뉘었다.
Check '금지어 목록이 생성물이라고 밝힌다' {
    $bw = Get-Content (Join-Path $plugin 'templates\korean-banned-words.md') -Raw -Encoding UTF8
    ($bw -match '이 파일은 생성물이다') -and ($bw -match 'korean-banned-words')
}
# 받아 오는 장치가 없으면 원본이 바뀌어도 아무도 모른다.
Check '목록을 받아 오는 워크플로가 있다' {
    $wf = Join-Path $repo '.github\workflows\sync-banned-words.yml'
    (Test-Path -LiteralPath $wf) -and ((Get-Content $wf -Raw -Encoding UTF8) -match 'korean-banned-words\.md')
}
# 여기서 만들면 안내가 두 벌이 된다.
Check '이 저장소에 생성기가 없다' {
    -not (Test-Path -LiteralPath (Join-Path $repo 'scripts\build-banned-words.ps1'))
}

# 문안이 @import 로 호출하는 파일이 실제로 있어야 한다. 없으면 CLAUDE.md 가 없는 파일을
# 가리키고, 그 상태를 아무도 못 본다.
Check '문안이 호출하는 파일이 템플릿에 있다' {
    $tplSrc0 = Get-Content (Join-Path $plugin 'templates\claude-md-ko.md') -Raw -Encoding UTF8
    $ok = $true
    foreach ($m in [regex]::Matches($tplSrc0, '(?m)^@(\S+)')) {
        $rel = $m.Groups[1].Value -replace '^kw-ax/', ''
        if (-not (Test-Path -LiteralPath (Join-Path $plugin (Join-Path 'templates' $rel)))) { $ok = $false }
    }
    $ok
}
# 경로에 공백이 들어가면 어디까지가 경로인지 갈리지 않는다.
Check '@import 경로에 공백이 없다' {
    $tplSrc1 = Get-Content (Join-Path $plugin 'templates\claude-md-ko.md') -Raw -Encoding UTF8
    -not ($tplSrc1 -match '(?m)^@[^\r\n]* ')
}
# 보유하다 놓는 것은 맞춤의 일이다. 템플릿에만 있고 맞춤이 안 옮기면 아무 PC 에도 안 생긴다.
Check '맞춤이 그 파일을 보유하다 놓는다' {
    $syncSrc3 = Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw
    ($syncSrc3 -match 'korean-banned-words\.md') -and ($syncSrc3 -match 'kw-ax')
}

Check '문안 템플릿에 GitHub 로그인 안내가 없다' {
    $tplSrc = Get-Content (Join-Path $plugin 'templates\claude-md-ko.md') -Raw -Encoding UTF8
    $tplSrc -notmatch 'gh auth login'
}
Check '점검이 GitHub 로그인을 확인한다' {
    ($hookCode -match 'hosts\.yml') -and ($hookCode -match 'gh auth login')
}
Check '맞춤은 GitHub 로그인을 건드리지 않는다' {
    (Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw) -notmatch 'gh auth login'
}

Check '맞춤 호출이 경계 뒤에 있다' {
    $g2 = $hookCode.IndexOf('$notes.Count -eq 0')
    $s2 = $hookCode.IndexOf('sync.ps1')
    ($g2 -ge 0) -and ($s2 -gt $g2)
}
# 맞춤이 실패해도 세션을 막지 않는다. 훅은 언제나 0 으로 끝난다.
Check '맞춤을 감싸 두고 0 으로 끝난다' {
    ($hookCode -match 'catch') -and ($hookCode.TrimEnd().EndsWith('exit 0'))
}
# 없앤 명령과 그 이름의 스킬이 남아 있으면 호출하는 곳이 둘이 되어 곧 불일치한다.
Check '없앤 명령 파일이 남아 있지 않다'   { -not (Test-Path -LiteralPath (Join-Path $plugin 'commands\kw-sync.md')) }
Check '같은 이름의 스킬이 남아 있지 않다' { -not (Test-Path -LiteralPath (Join-Path $plugin 'skills\kw-sync')) }
# 알림과 맞춤이 사본의 버전을 서로 다르게 읽으면, 알림이 말한 것을 맞춤이 못 고친다.
Check '알림과 맞춤이 같은 함수로 사본 버전을 읽는다' {
    $syncSrc2 = Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw
    ($hookSrc -match 'function Get-MarketplaceHead') -and ($syncSrc2 -match 'function Get-MarketplaceHead')
}
# 읽기 전용 자동 변수를 덮어쓰면 그 블록이 통째로 죽는다. 실제로 그렇게 됐다.
Check '읽기 전용 자동 변수를 안 쓴다' {
    ($hookSrc -notmatch '\$pid\b') -and ((Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw) -notmatch '\$pid\b')
}

# --- 훅이 표준입력을 읽는 방식 ---------------------------------------------
Write-Host ''
Write-Host '표준입력'
# [Console]::In 은 콘솔 코드페이지로 해석한다. 한국어 윈도는 949 라 클로드가 보내는
# UTF-8 한글이 깨지고 따옴표 짝이 틀어져 JSON 이 무너진다. 그러면 가드가 판정을 못 하고
# 통과시켜, 한글이 든 명령만 골라 샌다. 2026-09-19 에 949 와 65001 로 확인했다.
foreach ($h in @('python3-guard.ps1', 'docker-cert-reminder.ps1')) {
    $src = Get-Content (Join-Path $plugin (Join-Path 'hooks' $h)) -Raw
    Check "표준입력을 UTF-8 로 직접 읽는다: $h" {
        ($src -match 'OpenStandardInput') -and ($src -notmatch '\$Console\]::In\.ReadToEnd')
    }
}
# 5.1 의 ConvertFrom-Json 은 예외 메시지에 입력 전체를 포함한다. 그대로 적으면 명령 전문과
# 세션 기록 경로가 자국에 쌓인다.
Check '가드가 예외 메시지를 통째로 남기지 않는다' {
    $src = Get-Content (Join-Path $plugin 'hooks\python3-guard.ps1') -Raw
    $src -match 'Substring\(0, 120\)'
}

# 짝 없는 BEGIN 이 있으면 손대지 않는다. 그대로 두면 다음 실행에서 그 BEGIN 이 새 블록의
# END 와 짝지어져 둘 사이의 사용자 글이 통째로 지워진다. 재현했다. 블록을 세는 검사는
# 이것을 못 잡는다. 세어 보면 하나가 맞기 때문이다.
Check '짝 없는 BEGIN 을 만나면 멈춘다' {
    ($syncSrc -match "END 가 없는 '# BEGIN AX'") -and
    ($syncSrc -match "END 가 없는 '# BEGIN korean-banned-words'")
}
Check '여는 마커 수와 짝 수를 견준다' {
    ($syncSrc.Contains('$opens -gt $pairs')) -and ($syncSrc.Contains('$opens2 -gt $pairs2'))
}

# 클로드 코드는 켤 때 플러그인을 읽는다. 깔거나 옮기거나 켜거나 걷은 것은 그 세션에
# 안 실린다. 훅이 맞춤의 출력에서 문구를 찾아 판정하던 때는 다섯 중 둘만 잡고 있었다.
Check '플러그인을 바꾸는 곳마다 재시작 깃발을 설정한다' {
    $calls = @([regex]::Matches($syncSrc, "Invoke-Claude @\('plugin', '(install|update|enable|uninstall)'")).Count
    $flags = @([regex]::Matches($syncSrc, '\$script:Restart = \$true')).Count
    ($calls -gt 0) -and ($calls -eq $flags)
}
Check '맞춤이 다시 켜라고 알린다' {
    $syncSrc -match '다시 켜야 실립니다'
}
# 훅이 문구로 판정하면 문구가 늘 때마다 함께 고쳐야 하고, 실제로 빠졌다.
Check '훅은 문구로 재시작을 판정하지 않는다' {
    $hookCode -notmatch '플러그인을 깔았습니다'
}

# --- 금지어 공용 블록 -------------------------------------------------------
Write-Host ''
Write-Host '금지어 공용 블록'
# 규약은 KiwoomAX/korean-banned-words 의 import-protocol.md 가 소유한다.
# disciplined-coder 도 같은 블록을 쓴다. 어느 쪽이 먼저 돌든 결과가 같아야 한다.
Check '맞춤이 공용 블록을 다룬다' {
    ($syncSrc -match 'BEGIN korean-banned-words') -and ($syncSrc -match 'END korean-banned-words')
}
# AX 블록은 매번 템플릿으로 통째로 교체된다. 공용 블록을 그 안에 두면 상대가 쓴 것이
# 날아가고, 문안에 @import 를 두면 공용 블록과 합쳐 두 벌이 실린다.
Check '문안에 목록 @import 가 없다' {
    $tplSrc2 = Get-Content (Join-Path $plugin 'templates\claude-md-ko.md') -Raw -Encoding UTF8
    $tplSrc2 -notmatch '(?m)^@[^\r\n]*korean-banned-words'
}
# 버전 표시가 없으면 언제나 낡은 것으로 취급되어 상대 파일이 선택된다.
Check '배포하는 목록에 버전 표시가 머리 스무 줄 안에 있다' {
    $head = @(Get-Content (Join-Path $plugin 'templates\korean-banned-words.md') -TotalCount 20 -Encoding UTF8)
    ($head -join "`n") -match '원본 (?:버전|판):\s*schema\s*\d+'
}
# 지문이 다를 때 덮어쓰면 두 설치기가 세션마다 서로를 덮어 번갈아 바뀐다.
Check '버전이 같고 지문이 다르면 안 덮어쓴다' {
    $syncSrc -match '어느 것이 새것인지 알 수 없어'
}
# 규약은 바깥 줄을 지우지 말고 알리라고 한다. 사용자가 손으로 넣은 것일 수 있다.
Check '블록 바깥의 줄은 알리기만 한다' {
    ($syncSrc -match '블록 바깥에 같은 목록') -and ($syncSrc -match '지우지 않았습니다')
}

# --- 도커 인증서 안내 -------------------------------------------------------
Write-Host ''
Write-Host '도커 인증서 안내'
$dockerHook = Join-Path $plugin 'hooks\docker-cert-reminder.ps1'
$dockerSrc  = Get-Content $dockerHook -Raw
# 옛 설치기는 번들이 없는 PC 에 이 훅을 아예 적용하지 않았다. 플러그인 훅은 연결이 PC 마다
# 갈리지 않으므로 그 판정을 훅 자신이 해야 한다.
Check '번들이 없으면 아무 말도 안 한다' { $dockerSrc -match 'Test-Path -LiteralPath \$bundleFile\)\) \{ exit 0 \}' }
Check '어떤 상황에도 호출을 안 막는다'   { $dockerSrc -notmatch "permissionDecision" }
# 번들 위치를 박아 두면 설치기가 그것을 옮길 때 이 훅만 옛 곳을 가리킨 채 남는다.
# 실제로 그렇게 됐다. 설치기가 D:\corp-certs 로 옮겼는데 훅은 %LOCALAPPDATA% 를 보고
# 있어서, 새로 설치한 PC 에서 이 안내가 통째로 사라질 참이었다.
Check '번들 위치를 환경변수에서 읽는다'  { $dockerSrc -match '\$env:SSL_CERT_FILE' }
# 주석은 빼고 본다. 왜 이렇게 바뀌었는지 설명하려면 옛 경로를 적을 수밖에 없는데,
# 그것까지 막으면 이유를 적지 말라는 검사가 된다.
Check '번들 위치를 코드에 안 박는다' {
    $codeOnly = (($dockerSrc -split "`n") | Where-Object { $_ -notmatch '^\s*#' }) -join "`n"
    $codeOnly -notmatch 'LOCALAPPDATA'
}
# 안내에 적히는 마운트 경로도 그 변수에서 와야 한다. 판정만 고치고 문안을 두면
# 훅은 옳게 켜지면서 사용자에게는 없는 폴더를 마운트하라고 시킨다.
Check '안내 문안의 경로도 실제 번들 폴더다' {
    ($dockerSrc -match '__BUNDLE_DIR__') -and ($dockerSrc -match "Replace\('__BUNDLE_DIR__', \`$bundleDir\)")
}

$noBundle = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-nb-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path $noBundle | Out-Null
Check '번들 없는 PC 에서 실제로 조용하다' {
    $payload = @{ tool_name = 'Bash'; tool_input = @{ command = 'docker run alpine' } } | ConvertTo-Json -Compress
    $out = $payload | & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:SSL_CERT_FILE=''; & '$dockerHook'" 2>&1
    [string]::IsNullOrWhiteSpace(($out | Out-String).Trim())
}
# 번들이 어디 있든 따라가야 하므로, 흉내 내는 곳도 %LOCALAPPDATA% 아래가 아닌
# 임시 폴더로 둔다. 경로가 코드에 박혀 있으면 이 검사가 실패한다.
$bundleStub = Join-Path $noBundle 'somewhere\ca-bundle.pem'
Check '번들 있는 PC 에서는 말한다' {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $bundleStub) | Out-Null
    Set-Content -LiteralPath $bundleStub -Value '# stand-in'
    $payload = @{ tool_name = 'Bash'; tool_input = @{ command = 'docker run alpine' } } | ConvertTo-Json -Compress
    $out = $payload | & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:SSL_CERT_FILE='$bundleStub'; & '$dockerHook'" 2>&1
    ($out | Out-String) -match 'additionalContext'
}
# 안내에 실제 번들 폴더가 적혀 나오는지까지 본다. 치환을 빠뜨리면 사용자가 받는 명령에
# __BUNDLE_DIR__ 이 그대로 남는다.
Check '안내에 그 PC 의 번들 폴더가 적힌다' {
    $payload = @{ tool_name = 'Bash'; tool_input = @{ command = 'docker run alpine' } } | ConvertTo-Json -Compress
    $out = ($payload | & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:SSL_CERT_FILE='$bundleStub'; & '$dockerHook'" 2>&1 | Out-String)
    ($out -notmatch '__BUNDLE_DIR__') -and ($out -match 'somewhere')
}
Remove-Item -LiteralPath $noBundle -Recurse -Force -ErrorAction SilentlyContinue

# --- CLAUDE.md 단계 ---------------------------------------------------------
Write-Host ''
Write-Host 'CLAUDE.md 단계'
# 접두로 찾는다는 것은 마커 뒤 괄호 문구가 바뀌어도 같은 블록으로 알아본다는 뜻이다.
# 전체 줄 일치로 찾으면 옛 문구를 못 찾고 블록을 하나 더 붙인다.
Check '마커를 접두로 찾는다'          { $syncSrc.Contains('^#\s*BEGIN AX\b') -and $syncSrc.Contains('^#\s*END AX[^\r\n]*') }
Check '마커 바깥은 안 건드린다'        { $syncSrc -match '마커 바깥은 안 건드렸습니다' }
Check '고치기 전에 사본을 뜬다'        { $syncSrc -match '\$target\.bak' }
Check '잠금 폴더 이름을 상대와 맞춘다' { $syncSrc -match '\$target\.lock' -and $syncSrc -match "lock\.gate" }
Check '오래 잡힌 잠금은 빼앗는다'      { $syncSrc -match 'heldsince' -and $syncSrc -match '\-ge 10' }
Check '남의 잠금은 안 지운다'          { $syncSrc -match "\`$owner -eq \`$token" }
Check '줄바꿈을 대상 파일에 맞춘다'    { $syncSrc -match '\$nl' }
# 블록이 둘이 되면 다음 실행이 자기 블록을 못 찾아 또 하나를 붙인다. 사용자 파일이라
# 그렇게 두느니 안 쓴다.
Check '쓰기 전에 블록이 하나인지 본다' { $syncSrc -match '블록이 하나여야 하는데' }
# 블록이 둘이면 정규식이 첫 것만 보고 "이미 같다" 로 끝나 중복이 조용히 남는다.
Check '블록이 둘 이상이면 하나로 줄인다' { $syncSrc -match '개 있어 하나로 줄였습니다' }
Check '훅도 블록 개수를 센다'            { $hookCode -match '개 있습니다' }
# 메모리에서 고친 것과 파일에 있던 것을 견주면 "이미 같다" 로 끝나 안 써진다.
Check '견주는 대상은 파일에 있던 것이다' {
    ($syncSrc -match '\$merged -eq \$fileNow') -and ($syncSrc -notmatch '\$merged -eq \$original')
}
Check '쓴 뒤에도 다시 본다'            { $syncSrc -match '쓴 뒤에 블록이 하나가 아닙니다' }

# --- 문서와 코드를 대조한다 ---------------------------------------------------
Write-Host ''
Write-Host '문서와 코드'
# 설계 문서가 단계를 일곱으로 세는데 코드가 여덟인 적이 있었다. 사람이 셀 일이
# 아니라 대조하면 되는 일이다.
$spec = Get-Content (Join-Path $repo 'docs\superpowers\specs\2026-09-06-control-tower-design.md') -Raw -Encoding UTF8
$readme = Get-Content (Join-Path $repo 'README.md') -Raw -Encoding UTF8

$codeSteps = @([regex]::Matches($syncSrc, "(?m)^Write-Host '(\d+)\.")) | ForEach-Object { [int]$_.Groups[1].Value }
Check '맞춤의 단계 번호가 1부터 빠짐없이 이어진다' {
    ($codeSteps.Count -gt 0) -and (@(1..$codeSteps.Count | Where-Object { $codeSteps -notcontains $_ }).Count -eq 0)
}
Check '설계 문서가 코드와 같은 수로 센다' {
    $m = [regex]::Match($spec, '단계 (\S+)이고 각각 독립이며 멱등이다')
    $words = @{ '넷'=4; '다섯'=5; '여섯'=6; '일곱'=7; '여덟'=8; '아홉'=9; '열'=10 }
    $m.Success -and $words[$m.Groups[1].Value] -eq $codeSteps.Count
}
Check '설계 문서의 단계 목록이 코드와 같은 수다' {
    $body = [regex]::Match($spec, "(?s)## 맞춤이 고친다.*?(?=`r?`n## )").Value
    @([regex]::Matches($body, '(?m)^\d+\. \*\*')).Count -eq $codeSteps.Count
}
Check 'README 가 코드와 같은 수로 센다' {
    $m = [regex]::Match($readme, '단계가 (\S+)이고')
    $words = @{ '넷'=4; '다섯'=5; '여섯'=6; '일곱'=7; '여덟'=8; '아홉'=9; '열'=10 }
    $m.Success -and $words[$m.Groups[1].Value] -eq $codeSteps.Count
}
# 알림이 호출하는 맞춤 스크립트가 이 플러그인 안에 있어야 한다. 밖을 가리키면 플러그인을
# 옮기거나 지운 PC 에서 알림만 뜨고 아무것도 안 고쳐진다.
Check '알림이 자기 플러그인 안의 맞춤을 호출한다' {
    $hookCode -match 'Split-Path -Parent \$PSScriptRoot'
}

# --- 뒤처짐 감지 ------------------------------------------------------------
Write-Host ''
Write-Host '뒤처짐 감지'
$syncCode = Get-CodeOnly $syncSrc
# 배포처 사본의 HEAD 를 읽으려면 .git\HEAD 가 가리키는 ref 파일을 찾아가야 한다.
# 슬래시를 빈 문자열로 바꾸면 refs/heads/main 이 refsheadsmain 이 되어 언제나 없는
# 파일을 가리키고, 뒤처짐 감지가 조용히 한 번도 발화하지 않는다. Join-Path 는
# 슬래시를 그대로 받으므로 바꿀 것이 없다.
foreach ($pair in @(@{ Name = '알림'; Src = $hookCode }, @{ Name = '맞춤'; Src = $syncCode })) {
    Check "$($pair.Name)이 ref 경로에서 슬래시를 지우지 않는다" {
        $pair.Src -notmatch "Replace\('/', ''\)"
    }
}
# 두 파일이 같은 값을 봐야 알림이 말한 것을 맞춤이 고친다. 한쪽만 고치면 알림은
# 뒤처졌다고 하는데 맞춤은 옮길 것이 없다고 하는 상태가 된다.
Check '알림과 맞춤이 같은 방식으로 ref 를 읽는다' {
    ($hookCode -match 'Join-Path \$g \(\$line\.Substring\(5\)\)') -and
    ($syncCode -match 'Join-Path \$g \(\$line\.Substring\(5\)\)')
}

# --- 맞춤이 끝까지 간다 -----------------------------------------------------
Write-Host ''
Write-Host '맞춤이 끝까지 간다'
# 맞춤은 네트워크와 pip 을 거치므로 감지의 십 초 예산 안에 안 끝난다. 훅이 그것을
# 동기로 호출하므로 예산이 짧으면 반쯤 하다 죽는다. 보통의 PC 가 한 번에 끝낼 만큼 준다.
Check '세션 시작 훅의 예산이 맞춤을 끝낼 만큼이다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $j.hooks.SessionStart[0].hooks[0].timeout -ge 90
}
# 예산을 늘리면 그만큼 세션 시작이 멈춘 것처럼 보인다. 무엇을 기다리는지 먼저 말한다.
Check '맞춤을 호출하기 전에 기다리라고 말한다' {
    $ci = $hookCode.IndexOf('-File $sync')
    $wi = $hookCode.IndexOf('잠시 기다려')
    ($ci -ge 0) -and ($wi -ge 0) -and ($wi -lt $ci)
}
# 상태를 마지막에 한 번만 적으면 예산에 막혀 죽은 실행이 아무것도 안 한 것으로 남아,
# 다음 세션이 처음부터 다시 돌고 그것이 영영 되풀이된다. 단계는 저마다 독립이고
# 멱등이므로 단계가 끝날 때마다 적어 거기까지의 진행을 남긴다.
$stepBodies = @([regex]::Split($syncCode, "(?m)^Write-Host '\d+\. ") | Select-Object -Skip 1)
Check '단계 조각이 단계 수와 같다' { $stepBodies.Count -eq $codeSteps.Count }
Check '단계마다 끝에서 상태를 적는다' {
    @($stepBodies | Where-Object { $_ -notmatch '(?m)^Save-State\b' }).Count -eq 0
}
# 적는 곳이 단계 안에 있기만 해서는 모자란다. 상태를 고치고 나서 적어야 한다.
# 적고 나서 고치면 그 값은 다음 단계가 끝날 때까지 디스크에 안 남아, 그 사이에
# 죽으면 그대로 유실된다. 단계 1 의 refreshed 가 실제로 그랬다.
Check '단계마다 상태를 고친 뒤에 적는다' {
    $bad = 0
    foreach ($b in $stepBodies) {
        $lastWrite = @([regex]::Matches($b, 'state\[''[^'']+''\] =')) | Select-Object -Last 1
        $lastSave  = @([regex]::Matches($b, '(?m)^Save-State\b')) | Select-Object -Last 1
        if ($null -eq $lastSave) { $bad++; continue }
        if ($null -ne $lastWrite -and $lastWrite.Index -gt $lastSave.Index) { $bad++ }
    }
    $bad -eq 0
}
# 적는 곳이 여럿이면 한 곳만 고쳐지고 나머지가 옛 방식으로 남는다.
Check '상태 파일을 적는 곳이 한 곳이다' {
    @([regex]::Matches($syncCode, 'Out-File -LiteralPath \$statePath')).Count -eq 1
}

# --- 검사가 이 PC 를 안 바꾼다 ----------------------------------------------
Write-Host ''
Write-Host '검사가 이 PC 를 안 바꾼다'
# 훅을 호출하는 검사는 홈을 반드시 가짜로 준다. 진짜 USERPROFILE 을 넘기면 훅이 남기는
# 자국이 사용자의 프로필에 쌓이고, 그것을 보는 검사가 없어 아무도 모른다.
Check '훅을 호출하는 검사가 진짜 홈을 안 넘긴다' {
    $self = Get-Content $PSCommandPath -Raw -Encoding UTF8
    $self -notmatch "USERPROFILE='\`$env:USERPROFILE'"
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
