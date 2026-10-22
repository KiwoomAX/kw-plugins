# 컨트롤 타워가 지킬 조건을 검사한다. 이 PC 를 바꾸지 않는다.
#
#   pwsh -File tests\test_control_tower.ps1
#
# 세션 점검 훅은 격리된 가짜 홈에서 실행해 실제 설정을 수정하지 않는다.

Set-StrictMode -Off
$ErrorActionPreference = 'Continue'

$repo   = Split-Path -Parent $PSScriptRoot
$plugin = Join-Path $repo 'plugins\kw-control-tower'
$ps7    = 'pwsh'   # 컨트롤 타워는 7 을 전제한다. 설치기는 7 이 없으면 아무것도 설치하지 않는다.

# 훅·동기화·명의 스크립트는 UTF-8 로 출력하고, PowerShell 은 자식 프로그램의 출력을
# [Console]::OutputEncoding 으로 읽는다. 이 값은 PC 의 코드페이지를 따르므로(한국어 윈도우는 949)
# 맞추지 않으면 한글이 깨져 출력을 대조하는 검사가 모두 실패한다. 결과를 낸 뒤 원래 값으로 되돌린다.
$consoleEncoding = [Console]::OutputEncoding
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

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

# 실패로 판정하지 않고 사용자에게 물을 것으로 모은다. 훅의 제약 3가지(외부 프로그램, 네트워크,
# 훅 자체의 실행 시간 200밀리초)는 금지가 아니라 "개발할 때 먼저 묻는다" 이다(2026-09-25 사용자 결정).
# 이 검사에 걸리면 측정값이나 새 호출을 보이고 사용자 승인을 받은 뒤 승인 목록을 고친다.
$script:AskList = New-Object System.Collections.ArrayList
function Ask {
    param([string]$Name, [scriptblock]$Body)
    $r = $false
    try { $r = & $Body } catch { $r = $false }
    if ($r) { $script:Pass++; Write-Host "  ok   $Name" -ForegroundColor Green }
    else { [void]$script:AskList.Add($Name); Write-Host "  ASK  $Name" -ForegroundColor Yellow }
}

Write-Host ''
Write-Host '컨트롤 타워가 지킬 조건 검사' -ForegroundColor Cyan
Write-Host ''

# --- 있어야 할 파일 --------------------------------------------------------
Write-Host '있어야 할 파일'
Check '있다: .claude-plugin\marketplace.json (코드 저장소 최상위)' { Test-Path -LiteralPath (Join-Path $repo '.claude-plugin\marketplace.json') }
foreach ($rel in @(
    '.claude-plugin\plugin.json',
    'manifest.json',
    'hooks\hooks.json',
    'hooks\session-check.ps1',
    'scripts\sync.ps1',
    'scripts\git-identity.ps1',
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

# 클로드 코드가 읽는 JSON 에 밑줄 접두 항목을 두지 않는다. 형식에 없는 항목이라 플러그인을 불러올
# 때마다 "unknown keys ignored" 경고가 표시되어, 이상이 없으면 아무 말도 하지 않는다는 이
# 플러그인의 첫째 규율을 매 세션 어긴다. 설명은 이 검사들의 주석과 README 에 둔다.
#
# manifest.json 은 뺀다. 클로드 코드가 아니라 sync.ps1 이 읽는 파일이라 경고가 나지 않고,
# 그 주석은 목록을 고칠 사람이 바로 보는 곳이다.
#
# 아는 항목을 나열해 비교하지 않고 밑줄만 막는다. 나열하면 형식에 항목이 늘 때마다 이 목록을
# 직접 고쳐야 하고, 고치지 않으면 멀쩡한 항목에서 검사가 실패한다.
# 플러그인을 추가할 때 이 목록을 직접 고치지 않도록 plugins 아래를 모은다.
$claudeJsonFiles = @((Join-Path $repo '.claude-plugin\marketplace.json'), (Join-Path $plugin 'hooks\hooks.json')) +
    @(Get-ChildItem (Join-Path $repo 'plugins') -Directory | ForEach-Object { Join-Path $_.FullName '.claude-plugin\plugin.json' } | Where-Object { Test-Path -LiteralPath $_ })
Check '클로드 코드가 읽는 JSON 에 밑줄 주석 항목이 없다' {
    $files = $claudeJsonFiles
    $bad = 0
    foreach ($f in $files) {
        $j = Get-Content $f -Raw | ConvertFrom-Json
        $bad += @($j.PSObject.Properties.Name | Where-Object { $_.StartsWith('_') }).Count
    }
    $bad -eq 0
}
Check '밑줄 항목 검사가 모든 플러그인의 plugin.json 을 본다' {
    $want = @(Get-ChildItem (Join-Path $repo 'plugins') -Directory | ForEach-Object { Join-Path $_.FullName '.claude-plugin\plugin.json' } | Where-Object { Test-Path -LiteralPath $_ })
    ($want.Count -ge 4) -and (@($want | Where-Object { $claudeJsonFiles -notcontains $_ }).Count -eq 0)
}

# 버전을 점검에 쓰지 않기로 했으므로 plugin.json 에 version 을 적지 않는다.
Check 'plugin.json 에 version 이 없다' {
    $j = Get-Content (Join-Path $plugin '.claude-plugin\plugin.json') -Raw | ConvertFrom-Json
    $null -eq $j.PSObject.Properties['version']
}
# 따옴표 하나가 빠져도 스크립트 전체가 실행되지 않고, 동기화는 모든 PC 에서 한꺼번에 멈춘다.
# 리뷰 화면에서 제안을 반영하면 이 검사를 거치지 않고 병합될 수 있으므로 문법부터 따로 본다.
# 스크립트가 늘어도 빠지지 않게 목록을 적지 않고 hooks 와 scripts 폴더의 스크립트를 모두 본다.
foreach ($f in @(Get-ChildItem -LiteralPath (Join-Path $plugin 'hooks'), (Join-Path $plugin 'scripts') -Filter '*.ps1')) {
    Check "문법 오류 없이 읽힌다: $($f.Name)" {
        $tokens = $null; $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$errors)
        foreach ($e in $errors) { Write-Host "       $($e.Extent.StartLineNumber)행: $($e.Message)" }
        $errors.Count -eq 0
    }
}

# --- 훅의 제한 시간 --------------------------------------------------------
Write-Host ''
Write-Host '훅의 제한 시간'
$hookSrc = Get-Content (Join-Path $plugin 'hooks\session-check.ps1') -Raw

# 주석을 제외한 코드만 검사한다. 주석에 적힌 단어까지 코드로 세면 설명이 검사를
# 실패시킨다.
function Get-CodeOnly {
    param([string]$Text)
    ($Text -split "`n" | Where-Object { $_ -notmatch '^\s*#' }) -join "`n"
}
$hookCode = Get-CodeOnly $hookSrc

# 제한 시간은 점검에만 적용된다. 목록과 다른 곳을 찾은 뒤 동기화를 호출하는 것은 제한 시간
# 밖이라고 설계가 정했으므로, 그 경계 앞의 코드만 떼어 제한 시간 검사를 적용한다. 경계는 알릴
# 것이 없을 때 그대로 종료하는 줄이다.
$guard = '$notes.Count -eq 0'
$gi = $hookCode.IndexOf($guard)
$hookDetect = if ($gi -ge 0) { $hookCode.Substring(0, $gi) } else { $hookCode }
Check '점검과 동기화를 구분하는 경계가 있다' { $gi -ge 0 }

Check '세션 점검 훅이 하나뿐이다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    @($j.hooks.SessionStart).Count -eq 1 -and @($j.hooks.SessionStart[0].hooks).Count -eq 1
}
Check '훅을 pwsh 로 실행한다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $j.hooks.SessionStart[0].hooks[0].command -eq 'pwsh'
}
# 한 문자열로 적으면 터미널이 그것을 다시 나누므로, 사용자 이름에 공백이 포함된 PC 에서
# 플러그인 경로가 깨진다. 나눠 적으면 터미널을 거치지 않는다.
Check '명령과 인자를 나눠 적는다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $all = @($j.hooks.SessionStart[0].hooks) + @($j.hooks.PreToolUse | ForEach-Object { $_.hooks })
    @($all | Where-Object { $_.command -ne 'pwsh' -or @($_.args).Count -lt 6 }).Count -eq 0
}
# matcher 는 도구 이름만 거른다. 명령 내용을 거르는 것은 if 이고, 이것이 없으면
# 도커도 python3 도 아닌 명령마다 프로그램이 실행된다.
Check '도구 훅마다 if 규칙이 적용되어 있다' {
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
# 점검이 외부 프로그램을 호출하면 목록과 다른 곳이 없는 세션까지 그 비용을 치른다. 동기화를
# 호출하는 것은 이 검사 뒤의 코드이고, 목록과 다른 곳이 있는 세션에서만 실행된다. 승인된 것은
# 최신 버전을 확인하는 curl.exe 하나다. 그 밖의 것이 보이면 실패가 아니라 사용자에게 물을 것이다.
Ask '점검의 외부 프로그램이 승인된 curl.exe 뿐이다' {
    # & 뒤가 변수나 괄호면 스크립트 블록 호출이라 뺀다. 이름으로 부르는 것만 프로그램이다.
    $calls = @([regex]::Matches($hookDetect, '(?m)^[^#\r\n]*?&\s*([A-Za-z][\w.\-]*)') | ForEach-Object { $_.Groups[1].Value })
    (@($calls | Where-Object { $_ -ne 'curl.exe' }).Count -eq 0) -and
    ($hookDetect -notmatch 'Start-Process') -and
    ($hookDetect -notmatch '(?m)^\s*(&\s*)?claude\s+plugin') -and
    ($hookDetect -notmatch 'Get-FileHash')
}
# 점검이 사용하는 네트워크는 최신 버전을 확인하는 요청 하나뿐이다. REST API 는 IP 하나에
# 시간당 60회라 사내 PC 들이 나눠 쓰면 금방 소진된다. 새 호출이 보이면 사용자에게 물을 것이다.
Ask '훅의 네트워크 요청이 승인된 최신 버전 확인 하나뿐이다' {
    (@([regex]::Matches($hookCode, '&\s*curl\.exe')).Count -eq 1) -and
    ($hookCode -notmatch 'Invoke-WebRequest|Invoke-RestMethod|api\.github\.com|System\.Net\.') -and
    ($hookCode -match 'info/refs\?service=git-upload-pack')
}
# 'curl' 은 Invoke-WebRequest 의 별칭이다. 제한 시간이 없으면 망이 멈춘 PC 에서 세션 시작이
# 함께 멈춘다. -f 가 없으면 401 응답 본문을 성공으로 읽는다.
Check 'GitHub 요청을 curl.exe 로 제한 시간 2초와 -f 를 두고 적는다' { $hookCode -match '&\s*curl\.exe -s -f -m 2\b' }
Check '네트워크 시간을 훅 자체의 실행 시간에 포함하지 않는다' {
    $hookCode -match '(?s)\$sw\.Stop\(\).{0,120}Get-RemoteHead.{0,120}\$sw\.Start\(\)'
}
# 허용하는 쓰기는 기록 파일 2개(느림 $over, 오류 $log)뿐이다. 명령 이름뿐 아니라
# [IO.File]::WriteAllText 같은 .NET 쓰기까지 줄마다 찾고, 그 줄이 허용한 파일을 가리키지
# 않으면 위반으로 센다.
function Get-HookWriteViolations {
    param([string]$Code)
    $write = '\[(System\.)?IO\.File\]::(WriteAll\w+|Append\w+|Create\w*|Open\w*|Delete|Move|Copy|Replace)|' +
             '\b(Set-Content|Add-Content|Clear-Content|Out-File|New-Item|Remove-Item|Move-Item|Copy-Item|Rename-Item|Tee-Object)\b|' +
             '(?<![0-9])>>?\s*(?!\$null\b)[\$''"\w]'
    @($Code -split "`n" | Where-Object { $_ -match $write -and $_ -notmatch '\$(over|log)\b' })
}
Check '훅이 아무 파일도 고치지 않는다 (기록 파일 2개는 제외한다)' {
    (Get-HookWriteViolations $hookCode).Count -eq 0
}
# 위 검사가 실제로 위반을 잡는지 쓰기 수단마다 한 줄씩 넣은 복사본으로 본다.
Check '쓰기 검사가 쓰기 수단마다 위반을 잡는다' {
    $bad = @(
        "[System.IO.File]::WriteAllText('x', 'y')", "[IO.File]::WriteAllLines(`$p, `$l)",
        "[System.IO.File]::AppendAllText(`$p, 'y')", "'y' | Out-File -LiteralPath `$p",
        "Add-Content -LiteralPath `$p -Value 'y'", "Set-Content `$p 'y'",
        "New-Item -ItemType File `$p", "Remove-Item -LiteralPath `$p", "'y' > `$p", "'y' >> `$p"
    )
    $missed = @($bad | Where-Object { (Get-HookWriteViolations ($hookCode + "`n" + $_)).Count -eq 0 })
    if ($missed.Count -gt 0) { Write-Host "       잡지 못한 줄: $($missed -join ' | ')" }
    $missed.Count -eq 0
}
# 기록 파일이 끝없이 커지면 그것도 이 PC 를 바꾸는 것이다.
Check '느림 기록은 덧붙이지 않고 덮어쓴다' { $hookCode -match 'WriteAllText\(\$over' }
Check '오류 기록은 20줄까지만 남긴다'   { $hookCode -match '\$keep\.Count -gt 20' }
# 점검 표에 적은 질문을 훅이 모두 확인해야 한다. 표에만 있고 훅에 없는 질문은 그
# 차이를 아무도 알아채지 못한다.
Check '훅이 점검 표의 질문을 모두 확인한다' {
    $spec2 = Get-Content (Join-Path $repo 'docs\superpowers\specs\2026-09-06-control-tower-design.md') -Raw -Encoding UTF8
    # 표 머리에 바로 붙여 잡는다. 절 머리부터 잡으면 표 앞 문단에서 끊긴다.
    $tbl = [regex]::Match($spec2, "(?s)\| 질문 \| 확인하는 곳 \|.*?(?=\r?\n\r?\n)").Value
    $rows = @([regex]::Matches($tbl, "(?m)^\|(?!-)")).Count - 1   # 머리 줄을 뺀다
    $asked = @([regex]::Matches($hookSrc, "(?m)^\s*# --- 질문 ")).Count
    # 한 주석이 질문 2개를 덮는 곳이 있어 주석 수가 아니라 번호의 최댓값을 센다.
    # 그때 앞말에 따라 '과' 도 쓰고 '와' 도 쓴다.
    $nums = @([regex]::Matches($hookSrc, '# --- 질문 (\d+)(?:[과와] (\d+))?')) |
            ForEach-Object { [int]$_.Groups[1].Value; if ($_.Groups[2].Success) { [int]$_.Groups[2].Value } }
    ($asked -gt 0) -and (($nums | Measure-Object -Maximum).Maximum -eq $rows)
}
Check '훅이 CLAUDE.md 의 사내 지침을 비교한다' {
    ($hookCode -match 'claude-md-ko\.md') -and ($hookCode -match 'BEGIN AX')
}
# 5.1 의 문법 제약은 더 지키지 않고, 5.1 로 되돌아가지 않았는지만 본다.
# 훅이 powershell.exe 로 실행되면 한국어가 ANSI 로 읽혀 조용히 깨진다.
Check '훅이 5.1 을 호출하지 않는다' {
    ($hookCode -notmatch 'powershell\.exe') -and ($hookCode -match 'pwsh')
}

# --- 한글이 깨지지 않는다 -----------------------------------------
Write-Host ''
Write-Host '한글'
# BOM 을 붙이지 않는다. 7 은 BOM 없이도 UTF-8 로 읽고, BOM 이 없으면 5.1 로 잘못 실행했을 때
# 한글이 조용히 깨지지 않고 그 줄에서 문법 오류로 드러난다.
foreach ($f in @((Join-Path $plugin 'hooks\session-check.ps1'), (Join-Path $plugin 'scripts\sync.ps1'),
                 (Join-Path $plugin 'hooks\python3-guard.ps1'), (Join-Path $plugin 'hooks\docker-cert-reminder.ps1'))) {
    Check "UTF-8 BOM 이 없다: $(Split-Path $f -Leaf)" {
        $b = [System.IO.File]::ReadAllBytes($f)
        -not ($b.Length -ge 3 -and $b[0] -eq 239 -and $b[1] -eq 187 -and $b[2] -eq 191)
    }
    Check "한글이 깨지지 않고 읽힌다: $(Split-Path $f -Leaf)" {
        (Get-Content -LiteralPath $f -Raw -Encoding UTF8) -match '[가-힣]'
    }
}
# 이 검사는 파일 맨 앞에서 콘솔을 UTF-8 로 맞추고, 그 설정은 자식 프로그램에도 이어질 수 있다.
# 그러면 스크립트가 스스로 UTF-8 출력을 설정하지 않아도 출력 대조 검사가 통과하지만, 클로드 코드가
# 실행할 때는 코드페이지가 949 인 PC 에서 한글이 깨진다. 그래서 설정이 코드에 있는지를 따로 본다.
# 스크립트가 늘어도 빠지지 않게 목록을 적지 않고 hooks 와 scripts 폴더의 스크립트를 모두 본다.
foreach ($f in @(Get-ChildItem -LiteralPath (Join-Path $plugin 'hooks'), (Join-Path $plugin 'scripts') -Filter '*.ps1')) {
    Check "출력 인코딩을 UTF-8 로 맞춘다: $($f.Name)" {
        (Get-CodeOnly (Get-Content -LiteralPath $f.FullName -Raw)).Contains('[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)')
    }
}

# --- 훅과 동기화가 같은 확인값을 낸다 --------------------------------------
Write-Host ''
Write-Host '확인값이 훅과 동기화에서 같다'
Check '세션 점검 훅과 동기화가 같은 확인값 함수를 쓴다' {
    $a = ([regex]::Match($hookSrc, '(?s)function Get-CheapHash \{.*?\n\}')).Value
    $s = Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw
    $b = ([regex]::Match($s, '(?s)function Get-CheapHash \{.*?\n\}')).Value
    # 주석은 다를 수 있으므로 계산하는 줄만 비교한다
    $strip = { param($t) ($t -split "`n" | Where-Object { $_ -notmatch '^\s*#' }) -join "`n" }
    (& $strip $a).Trim() -eq (& $strip $b).Trim()
}

# --- 동기화가 이전 훅 연결만 제거한다 --------------------------------------
# hooks 항목이 없는 그룹에서 Get-Prop 이 $null 을 돌려주면 @() 가 그것을 원소 하나로 세어 없는
# 속성에 값을 넣으려 한다(2026-09-28 다른 직원 PC 에서 단계 7 실패). 사용자가 써 둔 그룹은
# 모양과 관계없이 그대로 남아야 한다.
Write-Host ''
Write-Host '동기화가 이전 훅 연결만 제거한다'
$syncSrcH = Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw
foreach ($fn in @('Get-Prop', 'Remove-RetiredHookEntries')) {
    . ([scriptblock]::Create(([regex]::Match($syncSrcH, "(?s)function $fn \{.*?\n\}")).Value))
}
$retiredH = @([pscustomobject]@{ file = 'docker-cert-reminder.ps1'; pathContains = 'corp-certs' })
$oldH = '{ "type": "command", "command": "pwsh -File C:\\Users\\u\\AppData\\Local\\corp-certs\\docker-cert-reminder.ps1" }'
$newH = '{ "type": "command", "command": "pwsh -File C:\\Users\\u\\.claude\\plugins\\cache\\kiwoom-ax\\kw-control-tower\\x\\hooks\\docker-cert-reminder.ps1" }'
function Invoke-HookPrune([string]$Json) {
    $h = $Json | ConvertFrom-Json
    $n = Remove-RetiredHookEntries $h $retiredH
    # 저장했다 다시 읽은 모양으로 비교한다. 동기화는 이것을 settings.json 에 쓴다.
    @{ Removed = $n; Hooks = ($h | ConvertTo-Json -Depth 20 | ConvertFrom-Json) }
}
Check 'hooks 항목이 없는 그룹을 만나도 멈추지 않고 그 그룹에 hooks 를 새로 만들지 않는다' {
    $r = Invoke-HookPrune "{ `"PreToolUse`": [ { `"matcher`": `"Bash`" }, { `"matcher`": `"Write`", `"hooks`": [ $oldH, $newH ] } ] }"
    $g = @($r.Hooks.PreToolUse)
    ($r.Removed -eq 1) -and ($g.Count -eq 2) -and ($g[0].matcher -eq 'Bash') -and
        ($null -eq $g[0].PSObject.Properties['hooks']) -and (@($g[1].hooks).Count -eq 1) -and
        (@($g[1].hooks)[0].command -like '*kiwoom-ax*')
}
Check '그룹 배열 안의 null 은 그대로 남는다' {
    $r = Invoke-HookPrune "{ `"PreToolUse`": [ null, { `"matcher`": `"Write`", `"hooks`": [ $oldH, $newH ] } ] }"
    $g = @($r.Hooks.PreToolUse)
    ($r.Removed -eq 1) -and ($g.Count -eq 2) -and ($null -eq $g[0]) -and (@($g[1].hooks).Count -eq 1)
}
Check 'hooks 가 빈 배열인 그룹은 그대로 남는다' {
    $r = Invoke-HookPrune "{ `"PreToolUse`": [ { `"matcher`": `"Bash`", `"hooks`": [] }, { `"matcher`": `"Write`", `"hooks`": [ $oldH ] } ] }"
    $g = @($r.Hooks.PreToolUse)
    ($r.Removed -eq 1) -and ($g.Count -eq 1) -and ($g[0].matcher -eq 'Bash') -and ($null -ne $g[0].PSObject.Properties['hooks'])
}
Check '이전 훅과 새 훅이 섞인 그룹에서 이전 훅만 제거하고 다른 이벤트는 그대로 둔다' {
    $r = Invoke-HookPrune "{ `"PreToolUse`": [ { `"matcher`": `"Write`", `"hooks`": [ $oldH, $newH ] } ], `"Stop`": [ { `"hooks`": [ { `"type`": `"command`", `"command`": `"echo hi`" } ] } ] }"
    ($r.Removed -eq 1) -and (@(@($r.Hooks.PreToolUse)[0].hooks).Count -eq 1) -and
        (@(@($r.Hooks.PreToolUse)[0].hooks)[0].command -like '*kiwoom-ax*') -and
        (@(@($r.Hooks.Stop)[0].hooks)[0].command -eq 'echo hi')
}

# --- 세션 점검 훅이 가짜 홈에서 아무 말도 하지 않는다 -----------------------
Write-Host ''
Write-Host '세션 점검 훅의 동작'
$fake = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path (Join-Path $fake '.claude\plugins') | Out-Null
# 동기화 스크립트를 뺀 복사본으로 훅을 실행한다. 훅은 자기 폴더 옆의 scripts\sync.ps1 을 호출하므로,
# 진짜 폴더의 훅을 실행하면 가짜 홈에서도 진짜 동기화가 실행된다.
$quietRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-q-" + [guid]::NewGuid().ToString('n').Substring(0,8))
Copy-Item -LiteralPath $plugin -Destination $quietRoot -Recurse
Remove-Item -LiteralPath (Join-Path $quietRoot 'scripts\sync.ps1')

Check '설정 파일이 하나도 없으면 조용히 종료한다' {
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command @"
`$env:USERPROFILE='$fake'; `$env:CLAUDE_PLUGIN_ROOT='$quietRoot'
& '$quietRoot\hooks\session-check.ps1'
"@ 2>&1
    # 목록은 읽히지만 필수 플러그인이 없으므로 알림은 낸다. 다만 오류 없이 종료해야 한다.
    $LASTEXITCODE -eq 0
}

Check '목록이 없으면 아무 말도 하지 않는다' {
    $empty = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-empty-" + [guid]::NewGuid().ToString('n').Substring(0,8))
    New-Item -ItemType Directory -Force -Path $empty | Out-Null
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command @"
`$env:USERPROFILE='$fake'; `$env:CLAUDE_PLUGIN_ROOT='$empty'
& '$quietRoot\hooks\session-check.ps1'
"@ 2>&1
    Remove-Item -LiteralPath $empty -Recurse -Force -ErrorAction SilentlyContinue
    [string]::IsNullOrWhiteSpace(($out | Out-String).Trim())
}

# 그냥 출력하면 클로드 맥락에만 전달되고 사용자 화면에는 보이지 않는다. 할 말이 있으면 훅 JSON
# 한 줄로 내고 systemMessage 와 additionalContext 를 둘 다 채운다.
Check '할 말이 있으면 훅 JSON 으로 사용자와 클로드에게 함께 낸다' {
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command @"
`$env:USERPROFILE='$fake'; `$env:CLAUDE_PLUGIN_ROOT='$quietRoot'
& '$quietRoot\hooks\session-check.ps1'
"@ 2>&1
    $lines = @($out | ForEach-Object { "$_" } | Where-Object { $_.Trim() })
    $j = $null
    try { $j = ($lines -join "`n") | ConvertFrom-Json } catch { }
    ($lines.Count -eq 1) -and $j -and $j.systemMessage -and
    ($j.hookSpecificOutput.hookEventName -eq 'SessionStart') -and
    ($j.hookSpecificOutput.additionalContext.StartsWith($j.systemMessage))
}

# 제한 시간을 넘겨도 실패가 아니라 측정값을 보이고 사용자에게 물을 것으로 남긴다. 측정값을 기록하는지는 따로 검사한다.
$slowNote = ''
Ask '훅 자체의 실행 시간이 200밀리초를 넘지 않는다' {
    $slow = Join-Path $fake '.claude\kw-control-tower.slow'
    Remove-Item -LiteralPath $slow -ErrorAction SilentlyContinue
    & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command @"
`$env:USERPROFILE='$fake'; `$env:CLAUDE_PLUGIN_ROOT='$quietRoot'
& '$quietRoot\hooks\session-check.ps1'
"@ 2>&1 | Out-Null
    if (Test-Path -LiteralPath $slow) { $script:slowNote = (Get-Content -LiteralPath $slow -Raw).Trim(); Write-Host "       측정값: $script:slowNote" }
    -not (Test-Path -LiteralPath $slow)
}
Check '훅 자체의 실행 시간이 200밀리초를 넘으면 측정값을 기록한다' { $hookCode -match 'kw-control-tower\.slow' -and $hookCode -match 'ElapsedMilliseconds -gt 200' }

Check '훅이 스스로 오류를 남기지 않았다' {
    -not (Test-Path -LiteralPath (Join-Path $fake '.claude\kw-control-tower.error'))
}

Remove-Item -LiteralPath $fake -Recurse -Force -ErrorAction SilentlyContinue

# --- 동기화가 미리보기에서 아무것도 바꾸지 않는다 --------------------------
Write-Host ''
Write-Host '동기화의 미리보기'
$syncSrc = Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw
Check '미리보기가 한 일처럼 적지 않는다' { $syncSrc -match '실행하지 않음 · 미리보기' }
Check '설치되지 않은 것에만 install 을 쓴다'    { $syncSrc -match "if \(-not \`$onDisk\)" -and $syncSrc -match "'plugin', 'enable'" }
# 파이썬을 다루는 단계처럼 클로드를 다루는 단계도 클로드가 없을 때 무엇이 없는지 알아듣게
# 말해야 한다. 이름으로 부르면 터미널 오류가 그대로 나온다.
Check '클로드를 이름이 아니라 찾아 둔 경로로 부른다' {
    ($syncSrc -match '\$script:ClaudeExe = \(Get-Command claude') -and
    ($syncSrc -match '\$file = \$script:ClaudeExe') -and
    ($syncSrc -notmatch '& claude @ClaudeArgs')
}
Check '클로드가 없으면 무엇이 없는지 말한다' {
    ($syncSrc -match '클로드 코드 찾기 실패: PATH 에 claude 없음') -and ($syncSrc -match '클로드 코드를 찾을 수 없습니다\.')
}
Check '다시 활성화한 것을 따로 적는다'         { $syncSrc -match '다시 활성화한 것' }
Check '스킬 이름을 허용 목록으로 막는다'    { $syncSrc -match "\^\[A-Za-z0-9\._-\]\+\$" }
Check '삭제하기 전에 백업을 남긴다'          { $syncSrc -match 'Copy-Item' -and $syncSrc -match 'kw-control-tower-backups' }
Check '삭제 판정이 조건 3개를 함께 본다'    { $syncSrc -match "\`$subdirs\.Count -eq 0\) -and \(\`$files\.Count -eq 1\) -and \(\`$files\[0\]\.Name -eq 'SKILL\.md'\)" }

# 점검과 같은 규칙으로 비어 있으면 넣는다. 파이썬의 기본 인코딩으로는 판정하지 않는다.
# sys.getdefaultencoding() 은 파이썬 3 에서 언제나 utf-8 이라 한 번도 넣지 못한다.
Check 'PYTHONUTF8 이 비어 있으면 넣고 0 과 1 은 그대로 둔다' {
    $ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $plugin 'scripts\sync.ps1'), [ref]$null, [ref]$null)
    $fn  = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Resolve-Utf8Action' }, $true)
    if ($null -eq $fn) { return $false }
    . ([scriptblock]::Create($fn.Extent.Text))
    ((Resolve-Utf8Action $null) -eq 'set') -and ((Resolve-Utf8Action '') -eq 'set') -and
    ((Resolve-Utf8Action '1') -eq 'keep') -and ((Resolve-Utf8Action '0') -eq 'keep') -and
    ((Resolve-Utf8Action 'x') -eq 'fail')
}
Check '동기화가 파이썬 기본 인코딩으로 판정하지 않는다' { $syncSrc -notmatch 'getdefaultencoding' }

# 점검은 라이브러리 목록의 확인값으로 판정한다. 동기화도 확인값이 같으면 pip 을 호출하지 않아,
# 설치기가 모든 단계를 실행할 때 사내 프록시를 거치는 pip 이 매번 실행되지 않게 한다.
Check '라이브러리 목록이 같으면 pip 을 호출하지 않는다' {
    $b = [regex]::Match($syncSrc, "(?s)Show '4\..*?(?=Show '5\.)").Value
    $gate = $b.IndexOf("`$state['requirements'] -eq `$newHash")
    ($gate -ge 0) -and ($gate -lt $b.IndexOf('pip install')) -and ($b -match '--retries 1')
}

# --- 목록이 지킬 조건 -------------------------------------------------------
Write-Host ''
Write-Host '목록'
$mf = Get-Content (Join-Path $plugin 'manifest.json') -Raw | ConvertFrom-Json
# kw-dashboard 는 배포를 권장인 kw-devops 에 맡기므로 같은 등급이다. kw-doc-formats 는 공식
# document-skills 를 기반으로 하는 보정 스킬이라 기본 스킬이 늘 있어야 한다(2026-09-30 사용자 결정).
Check 'kw-dashboard 는 권장이고 document-skills 는 필수다' {
    (@($mf.suggested) -contains 'kw-dashboard@kiwoom-ax') -and (@($mf.required) -notcontains 'kw-dashboard@kiwoom-ax') -and
    (@($mf.required) -contains 'document-skills@anthropic-agent-skills') -and (@($mf.suggested) -notcontains 'document-skills@anthropic-agent-skills')
}
Check '필수 플러그인의 마켓플레이스가 목록에 등록되어 있다' {
    $mkNames = @($mf.marketplaces | ForEach-Object { $_.name })
    @($mf.required | Where-Object { $mkNames -notcontains ($_ -split '@')[1] }).Count -eq 0
}
# replacedBy 는 이 PC 에 실제로 설치될 플러그인 이름이어야 한다. 마켓플레이스 이름을 잘못 적으면
# installed_plugins.json 의 항목 이름과 맞지 않아 단계 7 이 대체가 아직 없다며 계속 건너뛴다. 그러면
# 이전에 복사해 둔 스킬이 남아 같은 스킬을 2번 불러오고, 화면에는 이유가 틀린 안내만 표시된다.
Check 'replacedBy 가 이 PC 에 실제로 설치될 플러그인을 가리킨다' {
    # 컨트롤 타워 자신은 목록에 없다. 설치기가 설치하고, 이 스크립트는 그 안에서 실행된다.
    $willHave = @($mf.required) + @($mf.suggested) + @('kw-control-tower@kiwoom-ax')
    $named    = @(@($mf.retiredPlugins) + @($mf.retiredSkills) |
                  Where-Object { $_.replacedBy } | ForEach-Object { $_.replacedBy })
    @($named | Where-Object { $willHave -notcontains $_ }).Count -eq 0
}
Check '정리 항목마다 언제 넣었는지 적혀 있다' {
    $all = @($mf.retiredPlugins) + @($mf.retiredMarketplaces) + @($mf.retiredSkills) + @($mf.retiredHooks)
    @($all | Where-Object { -not $_.since }).Count -eq 0
}
Check '폐기한 훅은 이름과 경로를 함께 적는다' {
    @($mf.retiredHooks | Where-Object { -not $_.file -or -not $_.pathContains }).Count -eq 0
}
# JSON 형식이 맞는 것과 목록의 형식이 맞는 것은 다르다. 항목 이름을 하나 잘못 적으면 JSON 형식
# 오류는 없고 그 목록만 조용히 비어, 아무것도 하지 않고 성공으로 끝난다.
$manifestKeys = @('marketplaces','required','suggested','retiredPlugins','retiredMarketplaces','retiredSkills','retiredHooks')
Check '목록에 있어야 할 항목이 모두 있다' {
    @($manifestKeys | Where-Object { $null -eq $mf.PSObject.Properties[$_] }).Count -eq 0
}
Check '동기화가 항목이 빠진 목록에서 멈춘다' {
    @($manifestKeys | Where-Object { $syncSrc -notmatch [regex]::Escape("'$_'") }).Count -eq 0 -and
    ($syncSrc -match '목록에 항목 없음')
}
Check '세션 점검 훅도 항목이 빠진 목록에서 종료한다' { $hookCode -match "목록에 항목 없음: \`$k" }

$badManifest = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-bad-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path $badManifest | Out-Null
# 홈도 가짜로 준다. 훅은 항목이 빠진 목록을 만나면 종료하면서 기록을 남기므로, 진짜
# USERPROFILE 을 전달하면 실제 프로필의 kw-control-tower.error 가 커져 이 파일 첫 줄의
# "이 PC 를 바꾸지 않는다" 를 어긴다.
$badHome = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-badhome-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path (Join-Path $badHome '.claude') | Out-Null
Check '항목이 빠진 목록으로는 세션 점검 훅이 아무 말도 하지 않는다' {
    '{ "marketplaces": [], "required": [] }' | Set-Content -LiteralPath (Join-Path $badManifest 'manifest.json')
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$badHome'; `$env:CLAUDE_PLUGIN_ROOT='$badManifest'; & '$quietRoot\hooks\session-check.ps1'" 2>&1
    [string]::IsNullOrWhiteSpace(($out | Out-String).Trim())
}
# 기록이 가짜 홈 안에 남아야 샌드박스가 성립한다. 위 검사는 훅이 조용한지만 보고
# 어디에 적었는지는 보지 않는다.
Check '종료하며 남긴 기록이 가짜 홈 안에 남는다' {
    Test-Path -LiteralPath (Join-Path $badHome '.claude\kw-control-tower.error')
}
Remove-Item -LiteralPath $badManifest -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $badHome -Recurse -Force -ErrorAction SilentlyContinue
# 이 마켓플레이스는 자기 코드 저장소 안의 플러그인만 배포한다. 외부 코드 저장소를 플러그인
# 원본으로 가리키면 SSH 로 내려받으려다 사내 PC 에서 실패한다(2026-09-06 확인).
Check '마켓플레이스가 외부 코드 저장소를 원본으로 가리키지 않는다' {
    $mk = Get-Content (Join-Path $repo '.claude-plugin\marketplace.json') -Raw | ConvertFrom-Json
    @($mk.plugins | Where-Object { $_.source -isnot [string] -or -not $_.source.StartsWith('./') }).Count -eq 0
}
# required 에 적은 것이 마켓플레이스 목록(marketplace.json)에 없으면 이름으로 설치할 수 없다.
# 배포 전에는 드러나지 않고 사내 PC 마다 동기화가 설치에 실패하면서 드러난다. 고칠 곳이 2곳이라
# 한 곳만 고치기 쉬우므로 지킬 조건으로 고정한다.
Check '필수 목록의 플러그인이 마켓플레이스 목록에도 있다' {
    $mk2 = Get-Content (Join-Path $repo '.claude-plugin\marketplace.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $sold = @($mk2.plugins | ForEach-Object { $_.name })
    $bad = @()
    foreach ($id in @($mf.required) + @($mf.suggested)) {
        if ($id -notlike '*@kiwoom-ax') { continue }   # 외부 마켓플레이스는 여기서 확인할 수 없다
        if ($sold -notcontains $id.Split('@')[0]) { $bad += $id }
    }
    $bad.Count -eq 0
}
# 먼저 제거하고 설치가 실패하면 그 플러그인이 아예 없는 PC 가 된다. 그래서 대체자를
# 지킬 조건으로 요구한다.
Check '정리할 플러그인에는 대체자가 적혀 있다' {
    @($mf.retiredPlugins | Where-Object { -not $_.replacedBy }).Count -eq 0
}
Check '동기화가 대체를 확인한 뒤에 제거한다' {
    $syncSrc -match '대체할 \$by 가 아직 설치되지 않아'
}
# 마켓플레이스에도 플러그인과 같은 대체 가드를 둔다. 없으면 설치가 실패해 이전 플러그인이 그대로
# 남은 PC 에서 마켓플레이스만 제거되어, 설치된 플러그인의 출처가 사라진다.
Check '동기화가 남은 플러그인이 있는 마켓플레이스를 제거하지 않는다' {
    $syncSrc -match '가 아직 설치되어 있어 그대로 둡니다'
}

# --- python3 가드 -----------------------------------------------------------
Write-Host ''
Write-Host 'python3 가드'
$guard = Join-Path $plugin 'hooks\python3-guard.ps1'
$fake2 = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-g-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path (Join-Path $fake2 '.claude') | Out-Null

function Invoke-Guard {
    # 판정은 가드가 호출할 때 한다. 검사는 KWCT_PYTHON3_PROBE 로 판정을 주입해 이 PC 의 python3 에
    # 기대지 않는다. 빈 값을 주면 주입하지 않고 실제 판정 경로를 실행한다.
    param([string]$Command, [string]$Verdict = 'redirector')
    $payload = @{ tool_name = 'Bash'; tool_input = @{ command = $Command } } | ConvertTo-Json -Compress
    $probe = if ($Verdict) { "`$env:KWCT_PYTHON3_PROBE='$Verdict'; " } else { '' }
    return ($payload | & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$fake2'; $probe& '$guard'" 2>&1 | Out-String)
}

Check '맨 앞의 python3 을 막는다'            { (Invoke-Guard 'python3 -c "print(1)"') -match 'deny' }
Check '판정이 가짜 python3 이 아니면 막지 않는다' { -not ((Invoke-Guard 'python3 -c "print(1)"' 'real') -match 'deny') }
Check 'python3 이 없으면 막지 않는다'           { -not ((Invoke-Guard 'python3 -c "print(1)"' 'absent') -match 'deny') }
Check 'python 은 막지 않는다'                 { -not ((Invoke-Guard 'python -c "print(1)"') -match 'deny') }
Check 'py -3 은 막지 않는다'                  { -not ((Invoke-Guard 'py -3 -c "print(1)"') -match 'deny') }
Check 'python312 처럼 이름이 다르면 막지 않는다' { -not ((Invoke-Guard 'python312 -V') -match 'deny') }
Check 'python3.12 도 막지 않는다'              { -not ((Invoke-Guard 'python3.12 -V') -match 'deny') }
Check 'wsl 안의 python3 은 막지 않는다'        { -not ((Invoke-Guard 'wsl python3 -c "print(1)"') -match 'deny') }
Check 'docker exec 안의 python3 도 막지 않는다' { -not ((Invoke-Guard 'docker exec c python3 -V') -match 'deny') }
Check '따옴표 안의 python3 은 막지 않는다'     { -not ((Invoke-Guard 'echo "run python3 later"') -match 'deny') }
Check '파이프 뒤의 python3 은 막는다'          { (Invoke-Guard 'cat x | python3 -') -match 'deny' }
Check '앞에 VAR=값 이 붙어도 막는다'           { (Invoke-Guard 'FOO=1 python3 -V') -match 'deny' }
# 이전 버전이 상태 파일에 적은 판정이 남아 있어도 가드는 그것을 보지 않는다.
Check '가드가 상태 파일을 읽지 않는다' { (Get-Content $guard -Raw) -notmatch 'kw-control-tower\.state' }
Check '이전 판정 줄이 남아 있어도 주입한 판정을 따른다' {
    'python3=redirector' | Set-Content -LiteralPath (Join-Path $fake2 '.claude\kw-control-tower.state')
    -not ((Invoke-Guard 'python3 -V' 'real') -match 'deny')
}
# 주입 없이 실제 경로를 실행해도 가드가 스스로 실패하지 않는다. 실패하면 기록을 남긴다.
Check '실제 판정 경로가 오류 없이 끝난다' {
    Remove-Item -LiteralPath (Join-Path $fake2 '.claude\kw-control-tower.error') -ErrorAction SilentlyContinue
    $null = Invoke-Guard 'python3 -V' ''
    -not (Test-Path -LiteralPath (Join-Path $fake2 '.claude\kw-control-tower.error'))
}
Check '동기화가 python3 을 판정하지 않는다' { $syncSrc -notmatch 'fsutil' }

Remove-Item -LiteralPath $fake2 -Recurse -Force -ErrorAction SilentlyContinue

# --- 사용자 파일을 쓸 때 ----------------------------------------------------
Write-Host ''
Write-Host '사용자 파일 쓰기'
# settings.json 은 사용자 파일이다. 통째로 다시 쓰므로 아래를 지켜야 한다.
# disciplined-coder 도 settings.json·known_marketplaces.json 에 <파일>.bak 을 남긴다. 이름을 구분해 서로의 백업을 덮어쓰지 않는다.
Check '고치기 전에 백업을 남긴다'        { $syncSrc.Contains('Copy-Item -LiteralPath $Path -Destination "$Path.kw.bak"') }
Check '다시 읽을 수 없는 것은 쓰지 않는다' { $syncSrc.Contains('$null = $json | ConvertFrom-Json') }
Check '임시 파일에 쓰고 옮긴다'          { $syncSrc -match '\$Path\.kwtmp' -and $syncSrc -match 'Move-Item' }
Check 'BOM 없이 쓴다'                    { $syncSrc -match 'UTF8Encoding\(\$false\)' }
# 파일이 없는 것과 형식 오류는 다르다. 오류를 무시하면 망가진 설정을 가진 PC 에서 동기화가
# 아무것도 하지 않고 "바꾼 것이 없습니다" 라고 말한다.
Check '형식 오류인 JSON 은 무시하지 않고 오류로 멈춘다' {
    ($syncSrc -match 'catch \{ throw "JSON 형식 오류: ') -and
    ($hookCode -match 'catch \{ throw "JSON 형식 오류: ')
}

$brokenHome = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-brk-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path (Join-Path $brokenHome '.claude\plugins') | Out-Null
'{ not json' | Set-Content -LiteralPath (Join-Path $brokenHome '.claude\settings.json')
Check '망가진 설정에서 세션 점검 훅은 조용하고 기록을 남긴다' {
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$brokenHome'; `$env:CLAUDE_PLUGIN_ROOT='$quietRoot'; & '$quietRoot\hooks\session-check.ps1'" 2>&1
    ([string]::IsNullOrWhiteSpace(($out | Out-String).Trim())) -and
    (Test-Path -LiteralPath (Join-Path $brokenHome '.claude\kw-control-tower.error'))
}
Remove-Item -LiteralPath $brokenHome -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $quietRoot -Recurse -Force -ErrorAction SilentlyContinue

# --- 훅이 동기화를 호출한다 ---------------------------------------------------
Write-Host ''
Write-Host '훅이 동기화를 호출한다'
# 동기화는 사람이 아니라 훅이 호출한다. 알림을 읽고 명령을 입력하는 사람이 없으면 점검이
# 아무것도 바꾸지 못하기 때문이다. 그 밖에는 설치기 9단계가 같은 스크립트를 직접 호출한다.
Check '훅이 동기화 스크립트를 호출한다'    { $hookCode -match 'sync\.ps1' }
Check '훅이 호출하는 스크립트가 실재한다'  { Test-Path -LiteralPath (Join-Path $plugin 'scripts\sync.ps1') }
# 목록과 다른 곳이 없으면 동기화를 호출하지 않는다. 이 경계가 사라지면 모든 세션이 동기화의
# 비용을 치른다. 사용자가 직접 해야 하는 것도 동기화를 호출하지 않는다. 호출하면 로그인하지 않은
# PC 에서 매 세션 동기화가 실행되고도 아무것도 고치지 못한다.
Check '직접 할 일과 동기화가 고칠 것을 나눠 적는다' {
    ($hookCode -match '\$asks\s*=\s*New-Object') -and ($hookCode -match '\$notes\s*=\s*New-Object')
}
Check '동기화를 호출할지는 notes 만 보고 정한다' {
    $hookCode -match '\$notes\.Count -eq 0[^
]*\}\s*(#[^
]*)?'
}
# 상태에 따라 달라지는 안내를 CLAUDE.md 의 사내 지침에 두면, 완료한 사람도 매 세션 읽고 하지
# 않은 사람은 읽고 건너뛰어도 아무 일이 없다. 그런 안내는 점검이 맡는다.
Check '사내 지침 템플릿에 GitHub 로그인 안내가 없다' {
    $tplSrc = Get-Content (Join-Path $plugin 'templates\claude-md-ko.md') -Raw -Encoding UTF8
    $tplSrc -notmatch 'gh auth login'
}
Check '점검이 GitHub 로그인을 확인한다' {
    ($hookCode -match 'hosts\.yml') -and ($hookCode -match 'gh auth login')
}
Check '동기화는 GitHub 로그인을 다루지 않는다' {
    (Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw) -notmatch 'gh auth login'
}
# 클로드가 대신 실행하면 gh 가 브라우저를 열지 않으므로 코드 입력 페이지를 먼저 연다.
# 메일 읽기 권한은 git 명의를 GitHub 계정에 맞추는 데 쓰고, 기본 로그인에는 없다.
Check '로그인 안내가 코드 입력 페이지를 먼저 열고 메일 읽기 권한을 함께 받는다' {
    $hookCode -match "\`$loginCommand = 'start https://github\.com/login/device; gh auth login --web [^']*--clipboard --scopes user:email'"
}
# 로그인 명령은 세션 점검 훅과 명의 스크립트 2곳에 있다. 훅이 로그인됐다고 본 PC 에서도 토큰이
# 만료됐으면 스크립트가 로그인을 안내해야 하기 때문이다. 둘이 다르면 안내가 두 갈래가 된다.
Check '세션 점검 훅과 명의 스크립트가 같은 로그인 명령을 낸다' {
    $re = "\`$loginCommand = '([^']+)'"
    $a = [regex]::Match($hookCode, $re).Groups[1].Value
    $b = [regex]::Match((Get-Content (Join-Path $plugin 'scripts\git-identity.ps1') -Raw -Encoding UTF8), $re).Groups[1].Value
    $a -and ($a -eq $b)
}
# 명의가 비어 있으면 클로드가 대화 맥락에 있는 클로드 계정 메일로 채운다(이슈 #28).
Check '사내 지침 템플릿이 맥락의 메일로 git 명의를 채우지 말라고 한다' {
    $tplSrc = Get-Content (Join-Path $plugin 'templates\claude-md-ko.md') -Raw -Encoding UTF8
    ($tplSrc -match 'user\.email') -and ($tplSrc -match '채우지 않는다')
}
# 점검은 외부 프로그램을 늘리지 않는다. 명의는 git 을 실행하지 않고 파일에서 읽는다.
Check '점검이 git 을 실행하지 않고 .gitconfig 를 직접 읽는다' {
    ($hookDetect -match "Join-Path \`$userHome '\.gitconfig'") -and ($hookDetect -notmatch '(?m)^[^#\r\n]*\bgit\s+config\b')
}

Check '동기화 호출이 경계 뒤에 있다' {
    $g2 = $hookCode.IndexOf('$notes.Count -eq 0')
    $s2 = $hookCode.IndexOf('sync.ps1')
    ($g2 -ge 0) -and ($s2 -gt $g2)
}
# 동기화가 실패해도 세션을 막지 않는다. 훅은 언제나 0 으로 종료한다.
Check '동기화 호출을 감싸 두고 0 으로 종료한다' {
    ($hookCode -match 'catch') -and ($hookCode.TrimEnd().EndsWith('exit 0'))
}
# 없앤 명령과 그 이름의 스킬이 남아 있으면 호출하는 곳이 2곳이 되어 곧 서로 달라진다.
Check '없앤 명령 파일이 남아 있지 않다'   { -not (Test-Path -LiteralPath (Join-Path $plugin 'commands\kw-sync.md')) }
Check '같은 이름의 스킬이 남아 있지 않다' { -not (Test-Path -LiteralPath (Join-Path $plugin 'skills\kw-sync')) }
# 세션 점검 훅과 동기화가 내려받은 마켓플레이스의 버전을 서로 다르게 읽으면, 훅이 알린 것을
# 동기화가 고칠 수 없다.
Check '세션 점검 훅과 동기화가 같은 함수로 내려받은 마켓플레이스의 버전을 읽는다' {
    $syncSrc2 = Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw
    ($hookSrc -match 'function Get-MarketplaceHead') -and ($syncSrc2 -match 'function Get-MarketplaceHead')
}
# 읽기 전용 자동 변수에 값을 넣으면 그 블록 전체가 실패한다.
Check '읽기 전용 자동 변수를 쓰지 않는다' {
    ($hookSrc -notmatch '\$pid\b') -and ((Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw) -notmatch '\$pid\b')
}

# --- 훅이 표준입력을 읽는 방식 ---------------------------------------------
Write-Host ''
Write-Host '표준입력'
# [Console]::In 은 콘솔 코드페이지로 해석한다. 한국어 윈도우는 949 라 클로드가 보내는
# UTF-8 한글이 깨지고 따옴표 짝이 어긋나 JSON 을 읽지 못한다. 그러면 가드가 판정하지 못해
# 한글이 포함된 명령만 빠져나간다(2026-09-19, 949 와 65001 로 확인).
foreach ($h in @('python3-guard.ps1', 'docker-cert-reminder.ps1')) {
    $src = Get-Content (Join-Path $plugin (Join-Path 'hooks' $h)) -Raw
    Check "표준입력을 UTF-8 로 직접 읽는다: $h" {
        ($src -match 'OpenStandardInput') -and ($src -notmatch '\$Console\]::In\.ReadToEnd')
    }
}
# 5.1 의 ConvertFrom-Json 은 예외 메시지에 입력 전체를 포함한다. 그대로 적으면 명령 전문과
# 세션 기록 경로가 오류 기록 파일에 쌓인다.
Check '가드가 예외 메시지를 전부 남기지 않는다' {
    $src = Get-Content (Join-Path $plugin 'hooks\python3-guard.ps1') -Raw
    $src -match 'Substring\(0, 120\)'
}

# 짝 없는 BEGIN 이 있으면 수정하지 않는다. 그대로 두면 다음 실행에서 그 BEGIN 이 새 블록의
# END 와 짝지어져 둘 사이의 사용자 글이 모두 삭제된다. 블록 개수는 1개로 맞으므로 개수를
# 세는 검사로는 잡지 못한다.
Check '짝 없는 BEGIN 을 만나면 멈춘다' { $syncSrc -match "END 가 없는 '# BEGIN AX'" }
Check '시작 표시 줄 수와 짝 수를 비교한다' { $syncSrc.Contains('$opens -gt $pairs') }

# 클로드 코드는 시작할 때 플러그인을 읽으므로, 설치하거나 업데이트하거나 활성화하거나 제거한
# 것은 그 세션에 적용되지 않는다. 그래서 플러그인을 바꾸는 호출마다 재시작 깃발을 설정한다.
Check '플러그인을 바꾸는 곳마다 재시작 깃발을 설정한다' {
    $calls = @([regex]::Matches($syncSrc, "Invoke-Claude @\('plugin', '(install|update|enable|uninstall)'")).Count
    $flags = @([regex]::Matches($syncSrc, '\$script:Restart = \$true')).Count
    ($calls -gt 0) -and ($calls -eq $flags)
}
Check '동기화가 재시작하라고 알린다' {
    $syncSrc -match '다시 켜야 새 버전이 적용됩니다'
}
# 훅이 문구로 판정하면 문구가 늘 때마다 함께 고쳐야 한다. 재시작 여부는 동기화가 정한다.
Check '훅은 문구로 재시작을 판정하지 않는다' {
    $hookCode -notmatch '플러그인을 깔았습니다'
}

# --- AX 블록 조립 ------------------------------------------------------------
Write-Host ''
Write-Host 'AX 블록 조립'
# 답변 원칙과 금지어 목록은 필수 플러그인 disciplined-coder 가 불러온다(2026-10-05 사용자 결정).
# AX 블록은 사내 지침만 @import 한다. 동기화와 훅의 함수를 따로 꺼내 실제로 조립해 본다.
Check 'disciplined-coder 가 필수이고 그 마켓플레이스가 목록에 있다' {
    $mf = Get-Content (Join-Path $plugin 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    (@($mf.required) -contains 'disciplined-coder@chshin-tools') -and
    (@($mf.marketplaces | Where-Object { $_.name -eq 'chshin-tools' -and $_.repo -eq 'chshin84/disciplined-coder' }).Count -eq 1)
}
$assembled = @{}
foreach ($pair in @(@{ Name = '동기화'; Path = 'scripts\sync.ps1' }, @{ Name = '세션 점검 훅'; Path = 'hooks\session-check.ps1' })) {
    $ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $plugin $pair.Path), [ref]$null, [ref]$null)
    $fn  = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-AxBlock' }, $true)
    $fc  = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Get-AxCopies' }, $true)
    Check "$($pair.Name)에 Get-AxBlock 과 Get-AxCopies 가 있다" { ($null -ne $fn) -and ($null -ne $fc) }
    if ($null -eq $fn -or $null -eq $fc) { continue }
    . ([scriptblock]::Create($fn.Extent.Text))
    . ([scriptblock]::Create($fc.Extent.Text))
    $block = Get-AxBlock
    $assembled[$pair.Name] = "$block|$(@(Get-AxCopies) -join ',')"
    Check "$($pair.Name): 사내 지침만 불러온다" {
        $block -match '(?s)^# BEGIN AX[^\n]*\n@kw-ax/claude-md-ko\.md\n# END AX[^\n]*$'
    }
    Check "$($pair.Name): 복사본 목록이 블록이 불러오는 파일과 같다" { (@(Get-AxCopies) -join ',') -eq 'claude-md-ko.md' }
}
Check '동기화와 세션 점검 훅이 같은 블록과 복사본 목록을 쓴다' { $assembled['동기화'] -eq $assembled['세션 점검 훅'] }
# 블록이 가리키는 파일이 템플릿에 없으면 @import 가 아무것도 불러오지 않고, 그 상태를 아무도 알 수 없다.
Check '블록이 불러오는 파일이 템플릿에 있다' { Test-Path -LiteralPath (Join-Path $plugin 'templates\claude-md-ko.md') }
# 블록을 동기화가 만들므로 템플릿에 시작 표시 줄이나 끝 표시 줄이 있으면 복사본을 불러오는 순간
# 그 줄이 한 벌 더 생긴다.
Check '사내 지침 템플릿에 시작 표시 줄과 끝 표시 줄이 없다' {
    (Get-Content (Join-Path $plugin 'templates\claude-md-ko.md') -Raw -Encoding UTF8) -notmatch '(?m)^#\s*(BEGIN|END) AX'
}
Check '동기화가 블록을 쓰기 전에 템플릿을 kw-ax 로 복사한다' {
    $c = $syncSrc.IndexOf("Join-Path `$cfg 'kw-ax'")
    ($c -ge 0) -and ($c -lt $syncSrc.IndexOf('$block = Get-AxBlock'))
}
Check '훅이 kw-ax 복사본을 템플릿과 대조한다' { $hookCode -match "Join-Path `\`$cfg 'kw-ax'" }
# 공용 블록을 쓰던 이전 버전의 흔적이 남으면 금지어 목록을 2번 불러온다.
Check '동기화가 공용 블록을 새로 쓰지 않는다' { $syncSrc -notmatch "'# BEGIN korean-banned-words" }
Check '동기화가 kw-ax 복사본을 가리키는 이전 공용 블록을 삭제한다' { $syncSrc.Contains('if ($original -match $reShared)') }

# --- 도커 인증서 안내 -------------------------------------------------------
Write-Host ''
Write-Host '도커 인증서 안내'
$dockerHook = Join-Path $plugin 'hooks\docker-cert-reminder.ps1'
$dockerSrc  = Get-Content $dockerHook -Raw
# 플러그인 훅은 모든 PC 에 똑같이 연결되므로, 번들이 없는 PC 인지는 훅 자신이 판정해야 한다.
Check '번들이 없으면 아무 말도 하지 않는다' { $dockerSrc -match 'Test-Path -LiteralPath \$bundleFile\)\) \{ exit 0 \}' }
Check '어떤 상황에도 호출을 막지 않는다' { $dockerSrc -notmatch "permissionDecision" }
# 번들 위치를 코드에 고정하면 설치기가 번들을 옮길 때 이 훅만 이전 위치를 가리킨 채 남는다.
Check '번들 위치를 환경 변수에서 읽는다' { $dockerSrc -match '\$env:SSL_CERT_FILE' }
# 콘솔 코드페이지가 949 면 한국어 안내가 cp949 로 나가 클로드가 UTF-8 로 읽을 때 깨진다.
# 같은 플러그인의 세션 점검 훅도 같은 설정을 쓴다.
Check '도커 안내 훅이 나가는 인코딩을 UTF-8 로 맞춘다' {
    $dockerSrc.Contains('[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)')
}
# 주석은 빼고 본다. 왜 이렇게 바뀌었는지 설명하려면 이전 경로를 적을 수밖에 없는데,
# 그것까지 막으면 이유를 적지 말라는 검사가 된다.
Check '번들 위치를 코드에 고정하지 않는다' {
    $codeOnly = (($dockerSrc -split "`n") | Where-Object { $_ -notmatch '^\s*#' }) -join "`n"
    $codeOnly -notmatch 'LOCALAPPDATA'
}
# 안내에 적히는 마운트 경로도 그 변수에서 와야 한다. 판정만 고치고 안내 문구를 그대로 두면
# 훅은 옳게 동작하면서 사용자에게는 없는 폴더를 마운트하라고 안내한다.
Check '안내 문구의 경로도 실제 번들 폴더다' {
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
# 임시 폴더로 둔다. 경로가 코드에 고정되어 있으면 이 검사가 실패한다.
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
# 접두로 찾는다는 것은 표시 줄 뒤쪽의 괄호 문구가 바뀌어도 같은 블록으로 알아본다는 뜻이다.
# 전체 줄 일치로 찾으면 이전 문구를 찾지 못하고 블록을 하나 더 붙인다.
Check '시작 표시 줄과 끝 표시 줄을 접두로 찾는다' { $syncSrc.Contains('^#\s*BEGIN AX\b') -and $syncSrc.Contains('^#\s*END AX[^\r\n]*') }
Check '시작 표시 줄과 끝 표시 줄 바깥은 수정하지 않는다' { $syncSrc -match '시작 표시 줄과 끝 표시 줄 바깥은 수정하지 않았습니다' }
Check 'CLAUDE.md 를 고치기 전에 백업을 남긴다' { $syncSrc -match '\$target\.bak' }
Check '잠금 폴더 이름을 상대와 맞춘다' { $syncSrc -match '\$target\.lock' -and $syncSrc -match "lock\.gate" }
Check '오래 사용 중인 잠금은 강제로 가져온다' { $syncSrc -match 'heldsince' -and $syncSrc -match '\-ge 10' }
Check '다른 프로그램의 잠금은 삭제하지 않는다' { $syncSrc -match "\`$owner -eq \`$token" }
Check '줄바꿈을 대상 파일에 맞춘다'    { $syncSrc -match '\$nl' }
# 블록이 2개가 되면 다음 실행이 자기 블록을 찾지 못해 또 하나를 붙인다. 사용자 파일이므로
# 그 상태로 두느니 쓰지 않는다.
Check '쓰기 전에 블록이 1개인지 확인한다' { $syncSrc -match 'AX 블록 수 오류: 1개여야 하나' }
# 블록이 2개면 정규식이 첫 것만 보고 "이미 같다" 로 끝나 중복이 조용히 남는다.
Check '블록이 2개 이상이면 1개로 줄인다' { $syncSrc -match '개 있어 하나로 줄였습니다' }
Check '훅도 블록 개수를 센다'            { $hookCode -match '개 있습니다' }
# 메모리에서 고친 것과 파일에 있던 것을 비교하면 "이미 같다" 로 끝나 쓰지 않는다.
Check '비교 대상은 파일에 있던 것이다' {
    ($syncSrc -match '\$merged -eq \$fileNow') -and ($syncSrc -notmatch '\$merged -eq \$original')
}
Check '쓴 뒤에도 다시 확인한다'        { $syncSrc -match '쓴 뒤 AX 블록 수 오류: 1개 아님' }
# 상대가 .gate 폴더를 만든 채 종료되면 .gate 폴더가 남아, 삭제하지 않으면 반복을 다 쓰고 단계 6 이
# 실패한다. 폴더 생성 시각은 파일 시스템이 이전 값을 다시 붙일 수 있어 쓰지 않고, 연속으로 만들지
# 못한 횟수로 판정한다.
Check '남은 .gate 폴더를 삭제한다' { $syncSrc -match '\$gateMiss -ge 200' }
# 잠금 폴더는 상태 파일을 읽기 전에 만든다. 뒤에 만들면 직전 동기화가 적은 상태를 이전 값으로 덮어쓴다.
Check '동기화 잠금을 상태 파일 읽기 전에 만든다' {
    $l = $syncSrc.IndexOf("'kw-control-tower.sync.lock'"); $s = $syncSrc.IndexOf('$state = @{}')
    ($l -ge 0) -and ($s -gt $l)
}

# --- 문서와 코드를 대조한다 ---------------------------------------------------
Write-Host ''
Write-Host '문서와 코드'
# 문서에 적은 단계 수는 사람이 세지 않고 코드와 대조한다.
$spec = Get-Content (Join-Path $repo 'docs\superpowers\specs\2026-09-06-control-tower-design.md') -Raw -Encoding UTF8
$readme = Get-Content (Join-Path $repo 'README.md') -Raw -Encoding UTF8

$codeSteps = @([regex]::Matches($syncSrc, "(?m)^Show '(\d+)\.")) | ForEach-Object { [int]$_.Groups[1].Value }
Check '동기화의 단계 번호가 1부터 빠짐없이 이어진다' {
    ($codeSteps.Count -gt 0) -and (@(1..$codeSteps.Count | Where-Object { $codeSteps -notcontains $_ }).Count -eq 0)
}
Check '설계 문서가 코드와 같은 수로 센다' {
    $m = [regex]::Match($spec, '단계는 (\d+)개이고 각각 독립이며')
    $m.Success -and ([int]$m.Groups[1].Value -eq $codeSteps.Count)
}
Check '설계 문서의 단계 목록이 코드와 같은 수다' {
    $body = [regex]::Match($spec, "(?s)## 동기화가 고친다.*?(?=`r?`n## )").Value
    @([regex]::Matches($body, '(?m)^\d+\. \*\*')).Count -eq $codeSteps.Count
}
Check 'README 가 코드와 같은 수로 센다' {
    $m = [regex]::Match($readme, '단계는 (\d+)개이고')
    $m.Success -and ([int]$m.Groups[1].Value -eq $codeSteps.Count)
}
# 설계 문서는 살아 있는 설계다. 코드가 바뀌었는데 이전 문장이 남으면 다음 사람이 이전 규칙을 따른다.
Check '설계 문서에 바뀐 규칙의 이전 문장이 남아 있지 않다' {
    ($spec -notmatch '사내 것은 필수라 없으면 알리고') -and
    ($spec -notmatch '세션 시작 훅에는 매처가 없다') -and ($spec -notmatch '없다\. 도구 매처가 붙는 훅이 아니다') -and
    ($spec -notmatch '\| 설정한다 \| 물어서 설정한다 \|') -and
    ($spec -notmatch '파이썬에게 기본 인코딩을 물어 `utf-8`이 아닐 때만') -and
    ($spec -notmatch '"required": \[ "kw-doc-formats@kiwoom-ax" \]')
}
# 세션 점검 훅이 호출하는 동기화 스크립트가 이 플러그인 안에 있어야 한다. 밖을 가리키면 플러그인을
# 옮기거나 제거한 PC 에서 알림만 표시되고 아무것도 고쳐지지 않는다.
Check '세션 점검 훅이 자기 플러그인 안의 동기화 스크립트를 호출한다' {
    $hookCode -match 'Split-Path -Parent \$PSScriptRoot'
}

# --- 다시 쓰지 않는 말 --------------------------------------------------------
# 용어는 docs\style-guide.md 에서만 정한다. 그 파일의 「## 다시 쓰지 않는 말」 절에 백틱으로 적은
# 말이 컨트롤 타워의 파일, README, 설계 문서에 다시 들어오면 실패한다. 말을 여기에 옮겨 적지 않고
# 그 절에서 읽으므로 목록을 고치면 이 검사도 함께 바뀐다. style-guide.md 는 그 말을 나열하는
# 파일이라 검사 대상에 넣지 않는다. 목록을 읽지 못해 말이 0개이면 검사가 아무것도 보지 않으므로
# 실패로 본다.
Write-Host ''
Write-Host '다시 쓰지 않는 말'
$styleGuide = Get-Content (Join-Path $repo 'docs\style-guide.md') -Raw -Encoding UTF8
$bannedSection = [regex]::Match($styleGuide, '(?s)## 다시 쓰지 않는 말\r?\n(.*?)(?=\r?\n## |\z)').Groups[1].Value
$bannedWords = @([regex]::Matches($bannedSection, '`([^`]+)`') | ForEach-Object { $_.Groups[1].Value })
$wordCheckFiles = @(Get-ChildItem -LiteralPath $plugin -Recurse -File -Force |
                    Where-Object { $_.Extension -in '.ps1', '.json', '.md', '.txt' } | ForEach-Object { $_.FullName }) +
                  @((Join-Path $repo 'README.md'), (Join-Path $repo 'docs\superpowers\specs\2026-09-06-control-tower-design.md'))
Check '컨트롤 타워의 파일과 README 와 설계 문서에 다시 쓰지 않는 말이 없다' {
    if ($bannedWords.Count -eq 0) { Write-Host "       docs\style-guide.md 의 「## 다시 쓰지 않는 말」 절에서 말을 읽지 못함" }
    $hits = 0
    foreach ($f in $wordCheckFiles) {
        $lines = @(Get-Content -LiteralPath $f -Encoding UTF8)
        for ($i = 0; $i -lt $lines.Count; $i++) {
            foreach ($w in $bannedWords) {
                if ($lines[$i].Contains($w)) {
                    Write-Host "       $([System.IO.Path]::GetRelativePath($repo, $f)) $($i + 1)행: $w"
                    $hits++
                }
            }
        }
    }
    ($bannedWords.Count -gt 0) -and ($hits -eq 0)
}

# --- 최신 버전 점검 ---------------------------------------------------------
Write-Host ''
Write-Host '최신 버전 점검'
$syncCode = Get-CodeOnly $syncSrc
# 내려받은 마켓플레이스의 HEAD 를 읽으려면 .git\HEAD 가 가리키는 ref 파일을 찾아가야 한다.
# 슬래시를 빈 문자열로 바꾸면 refs/heads/main 이 refsheadsmain 이 되어 언제나 없는
# 파일을 가리키고, 최신 버전이 아닌 것을 조용히 한 번도 알리지 않는다. Join-Path 는
# 슬래시를 그대로 받으므로 바꿀 것이 없다.
foreach ($pair in @(@{ Name = '세션 점검 훅'; Src = $hookCode }, @{ Name = '동기화'; Src = $syncCode })) {
    Check "ref 경로에서 슬래시를 삭제하지 않는다: $($pair.Name)" {
        $pair.Src -notmatch "Replace\('/', ''\)"
    }
}
# 훅과 동기화 스크립트가 같은 값을 봐야 세션 점검 훅이 알린 것을 동기화가 고친다. 한쪽만 고치면 훅은
# 최신 버전이 아니라고 하는데 동기화는 업데이트할 것이 없다고 하는 상태가 된다.
Check '세션 점검 훅과 동기화가 같은 방식으로 ref 를 읽는다' {
    ($hookCode -match 'Join-Path \$g \(\$line\.Substring\(5\)\)') -and
    ($syncCode -match 'Join-Path \$g \(\$line\.Substring\(5\)\)')
}

# info/refs 응답의 첫 줄은 4자리 길이 접두사가 sha 앞에 붙는다. 접두사를 sha 로
# 잘못 잡으면 매 세션 최신 버전이 아니라고 나와 동기화가 되풀이된다. 실제 응답의 첫 줄 형식으로 본다.
Check 'GitHub 의 최신 버전 번호를 바르게 읽는다' {
    $fn = [regex]::Match($hookSrc, '(?s)function Get-RemoteHead \{.*?\n\}').Value
    $sha = '811b47e87fec64c141e23ef69634eafb638b4d40'
    $body = "001e# service=git-upload-pack`n0000" + "0155$sha HEAD`0multi_ack symref=HEAD:refs/heads/main`n" +
            "003f$sha refs/heads/main`n0000"
    $got = & {
        function curl.exe { $global:LASTEXITCODE = 0; $body -split "`n" }
        . ([scriptblock]::Create($fn))
        Get-RemoteHead 'https://github.com/x/y.git'
    }
    $got -eq $sha
}
Check '최신 버전을 읽지 못하면 $null 을 돌려준다' {
    $fn = [regex]::Match($hookSrc, '(?s)function Get-RemoteHead \{.*?\n\}').Value
    $got = & {
        function curl.exe { $global:LASTEXITCODE = 22; 'Unauthorized' }
        . ([scriptblock]::Create($fn))
        Get-RemoteHead 'https://github.com/x/y.git'
    }
    $null -eq $got
}
# 주소는 마켓플레이스 등록의 source 에서 만든다. 브랜치나 태그를 지정한 마켓플레이스를 GitHub 의
# 기본 브랜치와 비교하면 매 세션 다르다고 나오므로 GitHub 를 읽지 않는다.
Check 'GitHub 주소를 source 에서 만들고 ref 가 있으면 만들지 않는다' {
    $fn = [regex]::Match($hookSrc, '(?s)function Get-RemoteUrl \{.*?\n\}').Value
    $gp = [regex]::Match($hookSrc, '(?s)function Get-Prop \{.*?\n\}').Value
    & {
        . ([scriptblock]::Create($gp)); . ([scriptblock]::Create($fn))
        ((Get-RemoteUrl ([pscustomobject]@{ source = 'github'; repo = 'a/b' })) -eq 'https://github.com/a/b.git') -and
        ((Get-RemoteUrl ([pscustomobject]@{ source = 'git'; url = 'https://h/x.git' })) -eq 'https://h/x.git') -and
        ($null -eq (Get-RemoteUrl ([pscustomobject]@{ source = 'git'; url = 'git@h:x.git' }))) -and
        ($null -eq (Get-RemoteUrl ([pscustomobject]@{ source = 'github'; repo = 'a/b'; ref = 'v1' })))
    }
}
# 재시작 안내의 첫 줄은 disciplined-coder 와 같은 형식이다. 훅이 클로드에게 주는 지시도
# 같은 문구를 찾으라고 하므로, 한쪽만 바뀌면 클로드가 재시작을 요청하지 않는다.
Check '재시작 안내가 합의한 형식이고 이전 버전과 새 버전을 적는다' {
    ($syncCode -match "'kw-control-tower: 다시 켜야 새 버전이 적용됩니다\.'") -and
    ($hookCode -match "'kw-control-tower: 다시 켜야 새 버전이 적용됩니다\.'") -and
    ($syncCode -match "'kw-control-tower: 플러그인 버전 알림'") -and
    ($syncCode -match '\$mv\.Old\.Substring\(0, 7\)\) → \$newShort')
}
Check '동기화가 기록 파일을 삭제하지 않는다' {
    $syncCode -notmatch 'Remove-Item[^\r\n]*(seenPath|statePath|kw-control-tower\.(seen|state))'
}
# 세션마다 다시 시도하므로(2026-10-12 사용자 결정) 세션 점검 훅은 지난 실패 기록을 보고 건너뛰지 않는다.
Check '세션 점검 훅이 최신 버전을 동기화에 전달하고 지난 실패 기록으로 건너뛰지 않는다' {
    ($hookCode -notmatch 'stuck-\$mkName') -and
    ($hookCode -match 'KWCT_REMOTE_HEAD') -and ($syncCode -match 'KWCT_REMOTE_HEAD')
}

# --- 최신 버전 확인의 조건들 ------------------------------------------------
# 훅 복사본의 curl.exe 호출을 테스트용 가짜 프로그램으로 바꿔 가짜 홈에서 실행한다. 가짜 프로그램은
# GitHub 와 같은 형식의 응답(길이 접두사와 NUL 이 섞인 줄)을 내거나 실패한다. 복사본에는 동기화
# 스크립트가 없어 실제로 고치지 않는다.
Write-Host ''
Write-Host '최신 버전 확인의 조건들'
$scn = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-scn-" + [guid]::NewGuid().ToString('n').Substring(0,8))
$stub = Join-Path $scn 'curl-stub.ps1'
New-Item -ItemType Directory -Force -Path $scn | Out-Null
@'
if ($env:KWCT_STUB -eq 'fail') { exit 22 }
$sha = $env:KWCT_STUB
[Console]::Out.Write("001e# service=git-upload-pack`n0000" + "0155$sha HEAD`0multi_ack symref=HEAD:refs/heads/main`n003f$sha refs/heads/main`n0000")
exit 0
'@ | Set-Content -LiteralPath $stub -Encoding UTF8
$shaOld = 'c875eb136526601501928d8cb888b258cf04f366'
$shaNew = '811b47e87fec64c141e23ef69634eafb638b4d40'

function New-Root([string]$Leaf, [string]$Sync, [string]$Day) {
    # 이 플러그인의 폴더 이름이 곧 실행 중인 버전이다. 자동 업데이트 판정이 그것을 본다.
    # $Sync 를 주면 동기화 스크립트 자리에 그 테스트용 가짜 프로그램을 둔다. 주지 않으면 동기화
    # 스크립트를 삭제해 훅이 찾지 못하게 한다.
    # $Day 는 복사본이 오늘로 볼 요일이다. 요일마다 복사본을 따로 둔다.
    $r = if ($Sync) { Join-Path $scn "root-sync-$Day\$Leaf" } else { Join-Path $scn "root-$Day\$Leaf" }
    if (-not (Test-Path $r)) {
        Copy-Item -LiteralPath $plugin -Destination $r -Recurse
        if ($Sync) { $Sync | Set-Content -LiteralPath (Join-Path $r 'scripts\sync.ps1') -Encoding UTF8 }
        else { Remove-Item -LiteralPath (Join-Path $r 'scripts\sync.ps1') }
        $h = Join-Path $r 'hooks\session-check.ps1'
        $t = [System.IO.File]::ReadAllText($h)
        $t = $t.Replace('& curl.exe -s -f -m 2 "$Url/info/refs?service=git-upload-pack"', "& pwsh -NoProfile -File '$stub'")
        $t = $t.Replace('(Get-Date).DayOfWeek', "[DayOfWeek]::$Day")
        [System.IO.File]::WriteAllText($h, $t, (New-Object System.Text.UTF8Encoding($false)))
    }
    $r
}
function Invoke-Scenario {
    # 가짜 홈을 만들고 훅을 실행해 사용자에게 보일 본문을 돌려준다.
    param([string]$Installed, [string]$Remote, [hashtable]$Source = @{ source = 'github'; repo = 'KiwoomAX/kw-plugins' },
          [string]$Clone, [string]$State, [string]$Seen, [string]$Version, [string]$Leaf = 'c875eb136526',
          [string]$Other, [string]$OtherUpdated, [switch]$NoGh, [string]$Sync,
          [string]$GitConfig, [switch]$Context, [string]$Day = 'Monday', [string[]]$Leftover = @())
    # -Context 를 주면 사용자에게 보일 본문 대신 클로드에게만 가는 지시를 돌려준다.
    # -Day 는 훅이 오늘로 볼 요일이다. 명의 안내가 월요일에만 표시되므로 기본을 월요일로 둔다.
    $home2 = Join-Path $scn ("h-" + [guid]::NewGuid().ToString('n').Substring(0,6))
    # 로그인 여부는 APPDATA 아래 hosts.yml 로 판정한다. 미로그인을 흉내 낼 때는 빈 폴더를 준다.
    $app = Join-Path $home2 'appdata'
    New-Item -ItemType Directory -Force -Path (Join-Path $app 'GitHub CLI') | Out-Null
    if (-not $NoGh) { 'github.com:' | Set-Content (Join-Path $app 'GitHub CLI\hosts.yml') }
    $pd = Join-Path $home2 '.claude\plugins'
    New-Item -ItemType Directory -Force -Path (Join-Path $pd 'cache\x') | Out-Null
    $ver = if ($Version) { $Version } else { $Installed.Substring(0, 12) }
    $plug = @{ 'kw-control-tower@kiwoom-ax' = @(@{ installPath = (Join-Path $pd 'cache\x'); gitCommitSha = $Installed; version = $ver; lastUpdated = '2000-01-01T00:00:00Z' }) }
    if ($Other) { $plug['other@elsewhere'] = @(@{ installPath = (Join-Path $pd 'cache\x'); version = $Other; lastUpdated = $OtherUpdated }) }
    @{ version = 2; plugins = $plug } | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $pd 'installed_plugins.json')
    @{ 'kiwoom-ax' = @{ source = $Source; autoUpdate = $true } } | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $pd 'known_marketplaces.json')
    if ($Clone) {
        $g = Join-Path $pd 'marketplaces\kiwoom-ax\.git'
        New-Item -ItemType Directory -Force -Path (Join-Path $g 'refs\heads') | Out-Null
        'ref: refs/heads/main' | Set-Content (Join-Path $g 'HEAD')
        $Clone | Set-Content (Join-Path $g 'refs\heads\main')
    }
    if ($State) { $State | Set-Content (Join-Path $home2 '.claude\kw-control-tower.state') }
    foreach ($lo in $Leftover) {
        # '이름|fresh' 는 방금 바뀐 폴더다. 그 밖에는 15분 전에 바뀐 것으로 둔다.
        $n, $age = $lo -split '\|'
        $dir = New-Item -ItemType Directory -Force -Path (Join-Path $pd "marketplaces\$n")
        if ($age -ne 'fresh') { $dir.LastWriteTime = (Get-Date).AddMinutes(-15) }
    }
    if ($Seen)  { $Seen  | Set-Content (Join-Path $home2 '.claude\kw-control-tower.seen') }
    if ($GitConfig) { [System.IO.File]::WriteAllText((Join-Path $home2 '.gitconfig'), $GitConfig, (New-Object System.Text.UTF8Encoding($false))) }
    $root = New-Root $Leaf $Sync $Day
    $env:KWCT_STUB = $Remote
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$home2'; `$env:APPDATA='$app'; `$env:CLAUDE_PLUGIN_ROOT='$root'; & '$root\hooks\session-check.ps1'" 2>&1
    Remove-Item Env:\KWCT_STUB
    $txt = ($out | ForEach-Object { "$_" }) -join "`n"
    try {
        $j = $txt | ConvertFrom-Json
        if ($Context) { return $j.hookSpecificOutput.additionalContext }
        return $j.systemMessage
    } catch { return $txt }
}
$late = '설치된 플러그인이 최신 버전이 아닙니다'

Check 'GitHub 에 새 버전이 있으면 최신 버전이 아니라고 알린다' {
    (Invoke-Scenario -Installed $shaOld -Remote $shaNew) -match $late
}
Check 'GitHub 와 같으면 최신 버전이 아니라고 하지 않는다' {
    (Invoke-Scenario -Installed $shaNew -Remote $shaNew) -notmatch $late
}
Check 'GitHub 를 읽지 못하면 내려받은 마켓플레이스와 비교한다' {
    ((Invoke-Scenario -Installed $shaOld -Remote 'fail' -Clone $shaNew) -match $late) -and
    ((Invoke-Scenario -Installed $shaOld -Remote 'fail' -Clone $shaOld) -notmatch $late)
}
Check 'ref 를 지정한 마켓플레이스는 GitHub 대신 내려받은 마켓플레이스와 비교한다' {
    $src = @{ source = 'github'; repo = 'KiwoomAX/kw-plugins'; ref = 'v1' }
    (Invoke-Scenario -Installed $shaOld -Remote $shaNew -Source $src -Clone $shaOld) -notmatch $late
}
# 그날 3번 실패했거나 제한 시간에 막혔으면 그날은 다시 시도하지 않는다(2026-10-12 사용자 결정).
$today = Get-Date -Format 'yyyy-MM-dd'
Check '그날 3번 실패했으면 동기화를 호출하지 않고 명령을 알린다' {
    $o = Invoke-Scenario -Installed $shaOld -Remote $shaNew -State "updateFails=$today;3"
    ($o -match '(?m)^kw-control-tower: 플러그인 버전 알림') -and ($o -match '오늘 업데이트가 막혀') -and ($o -notmatch $late) -and
    ($o -match 'kw-control-tower@kiwoom-ax : c875eb1 → 811b47e') -and ($o -match '(?m)^\s+claude plugin update kw-control-tower@kiwoom-ax')
}
Check '3번 미만이거나 날짜가 지났으면 다시 시도한다' {
    $a = Invoke-Scenario -Installed $shaOld -Remote $shaNew -State "updateFails=$today;2"
    $b = Invoke-Scenario -Installed $shaOld -Remote $shaNew -State 'updateFails=2000-01-01;3'
    ($a -match $late) -and ($b -match $late) -and ("$a$b" -notmatch '오늘 업데이트가 막혀')
}
# 마켓플레이스 교체에 실패해 남은 폴더는 마켓플레이스를 구분하지 않고 동기화에 전달한다(2026-10-12 사용자 결정).
Check '마켓플레이스 교체에 실패해 남은 폴더를 알린다' {
    (Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -Leftover 'other.bak', 'x..clone') -match '남은 폴더가 있습니다: (other\.bak, x\.\.clone|x\.\.clone, other\.bak)'
}
Check '방금 바뀐 교체 폴더와 등록된 이름의 폴더는 알리지 않는다' {
    (Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -Leftover 'other.bak|fresh', 'kiwoom-ax') -notmatch '남은 폴더'
}
# 세션마다 업데이트를 시도한다(2026-10-12 사용자 결정). 이전 버전이 적은 실패 기록이 남아 있어도 건너뛰지 않는다.
Check '같은 최신 버전으로 실패한 기록이 있어도 다시 시도한다' {
    $o = Invoke-Scenario -Installed $shaOld -Remote $shaNew -State "stuck-kiwoom-ax=$shaNew"
    ($o -match $late) -and ($o -notmatch '이미 갱신에 실패해')
}
# 다른 곳(클로드 코드의 자동 업데이트, disciplined-coder)이 업데이트한 플러그인은 알리지 않는다.
# 업데이트는 그것을 실행한 훅이 그 세션에서만 알린다(2026-09-29 사용자 결정). 이전 버전 기억 파일이
# 남은 PC 에서 예전이면 알렸을 2가지 경우를 본다.
Check '자동 업데이트가 업데이트한 우리 플러그인을 알리지 않는다' {
    $a = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Seen 'kw-control-tower@kiwoom-ax=c875eb136526' -Leaf '811b47e87fec'
    $b = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Seen 'kw-control-tower@kiwoom-ax=c875eb136526' -Leaf 'c875eb136526'
    ("$a$b" -notmatch '플러그인 버전 알림') -and ("$a$b" -notmatch '다시 켜야') -and ("$a$b" -notmatch 'c875eb1 → 811b47e')
}
Check '다른 플러그인이 업데이트된 것을 알리지 않는다' {
    $o = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -Other 'bbbbbbbbbbbb' -OtherUpdated '2999-01-01T00:00:00Z' `
            -Seen "kw-control-tower@kiwoom-ax=811b47e87fec`nother@elsewhere=aaaaaaaaaaaa"
    ($o -notmatch 'other@elsewhere') -and ($o -notmatch '다시 켜야')
}
# 세션 점검 훅의 알림은 짧게 둔다(2026-09-29 사용자 결정). 로그인 안내는 한 줄이고 동기화를
# 호출하지 않는다. 동기화를 호출하면 목록과 다른 곳의 나열과 진행 출력 대신 동기화의 짧은 결과만 붙인다.
$syncStub = @'
param([switch]$Brief, [switch]$WhatIfOnly, [string]$Steps, [int]$BudgetSeconds)
if ($Brief) {
    Write-Host 'kw-control-tower: 다시 켜야 새 버전이 적용됩니다.'
    Write-Host '  - kw-control-tower@kiwoom-ax : c875eb1 → 811b47e'
} else { Write-Host '1. 마켓플레이스를 등록하고 최신 버전으로 업데이트합니다.' }
'@
Check '로그인하지 않은 PC 에는 로그인 안내를 한 줄로 알린다' {
    $o = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -NoGh
    $gh = @($o -split "`n" | Where-Object { $_ -match 'GitHub|gh auth|초대' })
    ($gh.Count -eq 1) -and ($gh[0] -match '^KW 컨트롤 타워: 사내 GitHub 로그인이 필요합니다\. .*gh auth login --web')
}
Check '로그인한 PC 에는 로그인 안내를 내지 않는다' {
    (Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec') -notmatch 'gh auth login'
}
# 명의가 비어 있는지만 보면 이미 다른 사람의 메일이 적힌 PC 를 정상으로 본다. 그래서 사용자가
# 승인한 메일과 지금 메일이 같은지를 본다. 승인은 명의 스크립트가 같은 파일에 적는다.
$idLine = 'git 명의'
$idSet = "[user]`n`tname = 홍길동`n`temail = hong@kiwoomam.com`n"
$idApproved = $idSet + "[kw-control-tower]`n`tapprovedEmail = hong@kiwoomam.com`n"
Check 'git 명의가 비어 있으면 확인을 안내한다' {
    (Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec') -match "(?m)^KW 컨트롤 타워: $idLine.*비어 있습니다"
}
Check '승인하지 않은 명의가 적혀 있으면 그 메일을 보이고 확인을 안내한다' {
    (Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -GitConfig $idSet) -match "(?m)^KW 컨트롤 타워: $idLine.*hong@kiwoomam\.com"
}
Check '승인한 명의와 같으면 안내하지 않는다' {
    (Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -GitConfig $idApproved) -notmatch $idLine
}
Check '승인한 뒤 메일이 바뀌면 다시 안내한다' {
    $cfg = "[user]`n`tname = 홍길동`n`temail = ax@kiwoomam.com`n[kw-control-tower]`n`tapprovedEmail = hong@kiwoomam.com`n"
    (Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -GitConfig $cfg) -match "$idLine.*ax@kiwoomam\.com"
}
# 요일 규칙의 근거는 설계 문서의 「명의 안내는 월요일에만 낸다」에 있다.
# 시나리오는 복사본의 요일 판정을 바꿔 끼워 실행한다. 원본의 그 글자가 바뀌면 치환이 조용히
# 빗나가 실제 실행 요일을 따르므로, 글자가 그대로인지 먼저 본다.
Check '명의 안내의 요일 판정이 시나리오가 바꿔 끼우는 글자 그대로다' {
    $hookCode -match '-not \$idOk -and \(Get-Date\)\.DayOfWeek -eq \[DayOfWeek\]::Monday'
}
# 명의가 비어 있으면 월요일이 아닌 날에도 이슈 #28 을 막는 규칙이 매 세션 클로드에게 간다.
# 화면에는 내지 않고, 클로드가 먼저 언급하지 않게 Send-Hook 이 규칙 앞에 붙이는 머리말로 구분한다.
$quietLead = '사용자에게 먼저 언급하지 말고'
Check '월요일이 아니어도 명의가 비어 있으면 화면에 내지 않고 클로드에게만 보호 규칙을 준다' {
    $o = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -Day 'Tuesday'
    $c = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -Day 'Tuesday' -Context
    ($o -notmatch $idLine) -and ($c -match $quietLead) -and ($c -match 'git-identity\.ps1') -and ($c -match '대화 맥락')
}
# 명의가 적혀 있으면 git commit 이 그대로 성공해 클로드가 명의를 채울 일이 없다. 승인 전이어도 규칙을 주지 않는다.
Check '월요일이 아니면 승인 전 명의가 적혀 있어도 안내도 보호 규칙도 내지 않는다' {
    $o = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -GitConfig $idSet -Day 'Tuesday'
    $c = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -GitConfig $idSet -Day 'Tuesday' -Context
    ($o -notmatch $idLine) -and ($c -notmatch $quietLead) -and ($c -notmatch 'git-identity\.ps1')
}
Check '승인한 명의면 요일과 상관없이 보호 규칙을 주지 않는다' {
    $c = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -GitConfig $idApproved -Day 'Tuesday' -Context
    ($c -notmatch $quietLead) -and ($c -notmatch 'git-identity\.ps1')
}
# 가짜 홈은 목록과 다른 곳이 늘 있어 화면에 낼 말이 없는 세션을 시나리오로 만들 수 없다. 그래서
# Send-Hook 을 떼어 화면에 낼 말 없이 규칙만 있는 세션을 본다.
function Invoke-SendHook([string[]]$Screen, [string[]]$Rules) {
    $fn = [regex]::Match($hookSrc, '(?s)function Send-Hook \{.*?\n\}').Value
    & {
        $say = New-Object System.Collections.ArrayList; foreach ($s in $Screen) { [void]$say.Add($s) }
        $quietRules = New-Object System.Collections.ArrayList; foreach ($r in $Rules) { [void]$quietRules.Add($r) }
        $askHints = @(); $syncLog = $null; $restartLine = 'kw-control-tower: 다시 켜야 새 버전이 적용됩니다.'
        . ([scriptblock]::Create($fn))
        Send-Hook
    }
}
Check '화면에 낼 말 없이 규칙만 있으면 화면 알림과 먼저 전하라는 지시 없이 규칙만 준다' {
    $j = Invoke-SendHook -Rules @('규칙 하나.') | ConvertFrom-Json
    $ctx = $j.hookSpecificOutput.additionalContext
    ($null -eq $j.PSObject.Properties['systemMessage']) -and ($ctx -match $quietLead) -and
        ($ctx -match '규칙 하나') -and ($ctx -notmatch '먼저 전하라')
}
Check '화면에 낼 말이 있으면 규칙은 머리말을 붙여 따로 준다' {
    $j = Invoke-SendHook -Screen @('KW 컨트롤 타워: 알림.') -Rules @('규칙 하나.') | ConvertFrom-Json
    $ctx = $j.hookSpecificOutput.additionalContext
    ($j.systemMessage -eq 'KW 컨트롤 타워: 알림.') -and ($j.systemMessage -notmatch '규칙 하나') -and
        ($ctx -match '먼저 전하라') -and ($ctx -match "$quietLead.*규칙 하나")
}
Check '화면에 낼 말도 규칙도 없으면 아무것도 내지 않는다' {
    $null -eq (Invoke-SendHook)
}
Check '월요일이 아니어도 로그인 안내는 낸다' {
    (Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -NoGh -Day 'Tuesday') -match 'gh auth login'
}
# git 은 섹션과 항목 이름의 대소문자를 구분하지 않고, 따옴표와 줄 끝 주석을 값에서 뺀다. 훅이 다르게 읽으면
# 승인한 PC 에서도 안내가 끝나지 않는다.
Check '대소문자와 따옴표와 주석이 달라도 같은 명의로 읽는다' {
    $cfg = "# 메모`n[User]`n`tName = `"홍길동`"`n`tEMAIL = hong@kiwoomam.com ; 사내 메일`n[kw-control-tower]`n`tapprovedemail = hong@kiwoomam.com`n"
    (Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -GitConfig $cfg) -notmatch $idLine
}
# 로그인 전에는 명의를 GitHub 에서 읽을 수 없다. 안내를 2개 내지 않고, 클로드가 로그인 뒤에 이어 가게 한다.
# 로그인은 사람이 브라우저에서 승인할 때까지 끝나지 않으므로 기본 제한 시간 2분으로는 중단된다.
Check '로그인하지 않은 PC 에는 명의 안내를 따로 내지 않고 로그인 뒤에 이어 가게 한다' {
    $o = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -NoGh
    $c = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -NoGh -Context
    ($o -notmatch $idLine) -and ($c -match 'git-identity\.ps1') -and ($c -match 'Ctrl\+V') -and ($c -match '10분')
}
Check '명의 안내는 클로드에게 승인을 받은 뒤에만 적용하라고 한다' {
    $c = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -Context
    ($c -match 'git-identity\.ps1') -and ($c -match '-Apply') -and ($c -match '승인')
}
# 훅은 모두 -ExecutionPolicy Bypass 로 실행된다. 명의 스크립트는 클로드의 터미널에서 따로 실행되어
# 그것을 물려받지 않으므로, 정책이 Restricted 나 AllSigned 인 PC 에서 거부된다(PR #42 리뷰).
Check '명의 스크립트를 실행 정책을 우회해 실행하라고 한다' {
    $c = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -Context
    $c -match 'pwsh -NoProfile -ExecutionPolicy Bypass -File "[^"]*git-identity\.ps1"'
}
# 이미 로그인한 직원은 처음 한 번 메일 읽기 권한을 더한다. 그것도 브라우저 승인을 기다리므로
# 로그인과 같은 안내가 없으면 기본 제한 시간 2분에 중단된다(PR #42 리뷰).
Check '로그인한 PC 의 명의 안내에도 권한 추가의 붙여 넣기 안내와 제한 시간이 있다' {
    $c = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -Context
    ($c -match '권한') -and ($c -match 'Ctrl\+V') -and ($c -match '10분')
}
# 가짜 홈은 목록과 다른 곳이 늘 있어 "로그인 안내만 있는 PC" 를 만들 수 없다. 동기화를 호출하는
# 조건이 목록과 다른 곳을 모은 $notes 하나뿐인지를 코드에서 본다.
Check '로그인 안내는 동기화를 호출하는 조건이 아니다' {
    ($hookCode -match '(?m)^if \(\$notes\.Count -eq 0\) \{ Send-Hook; exit 0 \}') -and
        ($hookCode -notmatch '\$notes\.Add\([^)]*GitHub')
}
Check '동기화를 호출하면 짧은 결과만 붙이고 목록과 다른 곳의 나열과 진행 출력은 붙이지 않는다' {
    $o = Invoke-Scenario -Installed $shaOld -Remote $shaNew -Sync $syncStub
    ($o -match '(?m)^kw-control-tower: 다시 켜야 새 버전이 적용됩니다\.') -and
        ($o -match 'kw-control-tower@kiwoom-ax : c875eb1 → 811b47e') -and
        ($o -notmatch $late) -and ($o -notmatch '사내 설정과 다릅니다') -and ($o -notmatch '마켓플레이스를 등록하고')
}
# 점검은 무엇이 다른지 안다. 그것을 전달하지 않으면 다른 곳 하나에 모든 단계가 실행된다.
$stepsStub = @'
param([switch]$Brief, [switch]$WhatIfOnly, [string]$Steps, [int]$BudgetSeconds)
Write-Host 'kw-control-tower: 사내 설정을 동기화했습니다.'
Write-Host "  - steps=$Steps budget=$BudgetSeconds"
'@
Check '점검이 목록과 다른 단계만 동기화에 전달한다' {
    $o = Invoke-Scenario -Installed $shaOld -Remote $shaNew -Sync $stepsStub -Leaf 'a1a1a1a1a1a1'
    $m = [regex]::Match($o, 'steps=([\d,]+)')
    $got = if ($m.Success) { @($m.Groups[1].Value.Split(',') | ForEach-Object { [int]$_ }) } else { @() }
    # 가짜 홈은 최신 버전 아님(1,2)과 필수 미설치(2)와 kw-ax 복사본 없음(6)을 늘 가지고, 이전 스킬·훅(7)은 없다.
    ($got -contains 1) -and ($got -contains 2) -and ($got -contains 6) -and ($got -notcontains 7)
}
# 목록과 다른 곳을 적는 곳이 하나라도 Add-Note 를 거치지 않으면 단계 번호가 빠져 그곳을 동기화하지 못한다.
Check '점검이 찾은 다른 곳은 모두 단계 번호와 함께 적힌다' { @([regex]::Matches($hookCode, '\$notes\.Add\(')).Count -eq 1 }
# 같은 원인으로 이미 실패한 단계만 남았으면 동기화를 호출하지 않고 알리기만 한다.
$fnPrint = [regex]::Match($hookSrc, '(?s)function Get-StuckPrint \{.*?\n\}').Value
Check '같은 원인으로 실패한 단계만 남으면 동기화를 호출하지 않는다' {
    . ([scriptblock]::Create($fnPrint))
    $all = (1..7 | ForEach-Object { "stuck-step$_=$(Get-StuckPrint $plugin $_)" }) -join "`n"
    $o = Invoke-Scenario -Installed $shaNew -Remote $shaNew -Sync $stepsStub -Leaf 'b2b2b2b2b2b2' -State $all
    ($o -notmatch 'steps=') -and ($o -match '같은 원인으로 이미 실패해 다시 시도하지 않았습니다')
}
Check '동기화와 훅이 같은 확인값을 만든다' {
    $a = [regex]::Match($hookSrc, '(?s)function Get-StuckPrint \{.*?\n\}').Value
    $b = [regex]::Match((Get-Content (Join-Path $plugin 'scripts\sync.ps1') -Raw), '(?s)function Get-StuckPrint \{.*?\n\}').Value
    $a -and ($a -eq $b)
}
# --- git 명의 스크립트 ------------------------------------------------------
# gh 자리에 테스트용 가짜 프로그램을 두고 가짜 홈에서 실행한다. 스크립트는 ~/.gitconfig 만 고치므로
# 진짜 설정을 수정하지 않는다. 가짜 프로그램은 KWCT_GH_USER 가 fail 이면 로그인되지 않은 것을,
# KWCT_GH_EMAILS 가 scope 면 메일 읽기 권한이 없는 것을 흉내 낸다.
Write-Host ''
Write-Host 'git 명의 스크립트'
$idScript = Join-Path $plugin 'scripts\git-identity.ps1'
Check '메일은 인증된 사내 메일을 먼저 고르고 없으면 주 메일을 고른다' {
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($idScript, [ref]$null, [ref]$null)
    $fn  = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Select-CommitEmail' }, $true)
    if ($null -eq $fn) { return $false }
    . ([scriptblock]::Create($fn.Extent.Text))
    $mk = { param($e, $p, $v) [pscustomobject]@{ email = $e; primary = $p; verified = $v } }
    $corp = '@kiwoomam.com'
    $a = Select-CommitEmail @((& $mk 'me@gmail.com' $true $true), (& $mk 'hong@kiwoomam.com' $false $true)) $corp
    $b = Select-CommitEmail @((& $mk 'hong@kiwoomam.com' $false $false), (& $mk 'me@gmail.com' $true $true)) $corp
    $c = Select-CommitEmail @((& $mk 'x@kiwoomam.com' $false $true), (& $mk 'y@KiwoomAM.com' $true $true)) $corp
    $d = Select-CommitEmail @((& $mk 'me@gmail.com' $false $false)) $corp
    ($a -eq 'hong@kiwoomam.com') -and ($b -eq 'me@gmail.com') -and ($c -eq 'y@KiwoomAM.com') -and ($null -eq $d)
}
$ghBin = Join-Path $scn 'gh-bin'
New-Item -ItemType Directory -Force -Path $ghBin | Out-Null
@'
$a = $args -join ' '
if ($a -eq 'api user') {
    if ($env:KWCT_GH_USER -eq 'fail') { 'gh: To get started with GitHub CLI, please run:  gh auth login'; exit 4 }
    '{"login":"hong","name":"홍길동","id":1}'; exit 0
}
if ($a -eq 'api user/emails') {
    if ($env:KWCT_GH_EMAILS -eq 'scope') { 'gh: This API operation needs the "user" scope.'; exit 1 }
    $env:KWCT_GH_EMAILS; exit 0
}
exit 1
'@ | Set-Content -LiteralPath (Join-Path $ghBin 'gh.ps1') -Encoding UTF8
function Invoke-Identity {
    # 가짜 홈에서 명의 스크립트를 실행해 출력과 종료 코드와 남은 .gitconfig 를 돌려준다.
    # git 은 HOME 이 있으면 그 아래 .gitconfig 를 전역 설정으로 읽는다. 기본은 가짜 홈과 같게 두고,
    # -GitHome 을 주면 git 이 다른 파일을 읽는 PC 를 흉내 낸다.
    param([string]$Emails, [string]$GitConfig, [string]$ArgText, [string]$User, [string]$GitHome)
    $h = Join-Path $scn ("i-" + [guid]::NewGuid().ToString('n').Substring(0,6))
    New-Item -ItemType Directory -Force -Path $h | Out-Null
    $gitHomeDir = if ($GitHome) { $GitHome } else { $h }
    $cfgPath = Join-Path $h '.gitconfig'
    if ($GitConfig) { [System.IO.File]::WriteAllText($cfgPath, $GitConfig, (New-Object System.Text.UTF8Encoding($false))) }
    $env:KWCT_GH_EMAILS = $Emails
    $env:KWCT_GH_USER = $User
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$h'; `$env:HOME='$gitHomeDir'; `$env:PATH='$ghBin;' + `$env:PATH; & '$idScript' $ArgText; exit `$LASTEXITCODE" 2>&1
    $code = $LASTEXITCODE
    Remove-Item Env:\KWCT_GH_EMAILS, Env:\KWCT_GH_USER -ErrorAction SilentlyContinue
    @{
        Out    = ($out | ForEach-Object { "$_" }) -join "`n"
        Code   = $code
        Config = if (Test-Path -LiteralPath $cfgPath) { [System.IO.File]::ReadAllText($cfgPath) } else { $null }
    }
}
$emailsJson = '[{"email":"me@gmail.com","primary":true,"verified":true},{"email":"hong@kiwoomam.com","primary":false,"verified":true}]'
Check '제안할 때는 지금 값과 GitHub 계정의 값을 보이고 아무것도 적지 않는다' {
    $before = "[user]`n`temail = ax@kiwoomam.com`n"
    $r = Invoke-Identity -Emails $emailsJson -GitConfig $before
    ($r.Code -eq 0) -and ($r.Out -match 'ax@kiwoomam\.com') -and ($r.Out -match '홍길동') -and
        ($r.Out -match 'pwsh -NoProfile -ExecutionPolicy Bypass -File "[^"]+" -Apply -Name "홍길동" -Email "hong@kiwoomam\.com"') -and
        ($r.Config -eq $before)
}
Check '메일 읽기 권한이 없으면 권한을 더하는 명령을 알리고 멈춘다' {
    $r = Invoke-Identity -Emails 'scope'
    ($r.Code -eq 3) -and ($r.Out -match 'start https://github\.com/login/device; gh auth refresh -h github\.com -s user:email --clipboard') -and
        ($null -eq $r.Config)
}
Check '로그인되어 있지 않으면 로그인 명령을 알리고 멈춘다' {
    $r = Invoke-Identity -Emails $emailsJson -User 'fail'
    ($r.Code -eq 2) -and ($r.Out -match 'gh auth login --web') -and ($null -eq $r.Config)
}
Check '이미 승인한 값이 GitHub 계정과 같으면 바꿀 것이 없다고 한다' {
    $r = Invoke-Identity -Emails $emailsJson -GitConfig $idApproved
    ($r.Code -eq 0) -and ($r.Out -match '바꿀 것이 없습니다') -and ($r.Out -notmatch '-Apply')
}
# 스크립트가 적는 항목과 훅이 읽는 항목이 다르면 승인해도 안내가 끝나지 않는다. 둘을 이어서 실행한다.
Check '승인한 값을 적으면 세션 점검 훅이 더 묻지 않는다' {
    $r = Invoke-Identity -ArgText "-Apply -Name '홍길동' -Email 'hong@kiwoomam.com'"
    ($r.Code -eq 0) -and $r.Config -and
        ((Invoke-Scenario -Installed $shaNew -Remote $shaNew -Leaf '811b47e87fec' -GitConfig $r.Config) -notmatch $idLine)
}
Check '메일 형식이 아니면 적지 않고 실패한다' {
    $r = Invoke-Identity -ArgText "-Apply -Name '홍길동' -Email 'not-an-email'"
    ($r.Code -ne 0) -and ($null -eq $r.Config)
}
# HOME 이 따로 있거나 홈 폴더가 다른 드라이브인 PC 에서는 git 이 ~/.gitconfig 가 아닌 파일을 읽는다.
# 그때 승인을 적으면 훅의 안내는 사라지는데 체크포인트는 여전히 다른 명의로 남는다. 승인을 적기 전에
# git 이 실제로 읽는 값을 확인하고, 다르면 승인을 적지 않고 어느 파일인지 알린다(PR #42 리뷰).
Check 'git 이 다른 전역 설정을 읽으면 승인을 적지 않고 그 사실을 알린다' {
    $other = Join-Path $scn ("g-" + [guid]::NewGuid().ToString('n').Substring(0,6))
    New-Item -ItemType Directory -Force -Path $other | Out-Null
    $r = Invoke-Identity -ArgText "-Apply -Name '홍길동' -Email 'hong@kiwoomam.com'" -GitHome $other
    ($r.Code -ne 0) -and ($r.Config -match 'hong@kiwoomam\.com') -and ($r.Config -notmatch '(?i)approvedEmail') -and
        ($r.Out -match 'HOME')
}
Remove-Item -LiteralPath $scn -Recurse -Force -ErrorAction SilentlyContinue

# --- 동기화의 업데이트 기록 -------------------------------------------------
# 동기화가 업데이트에 성공하면 재시작을 안내하는지, 실패하면 버전 알림을 내고 다시 시도하는지
# 실제로 실행해 확인한다. PATH 앞에 테스트용 가짜 프로그램 claude.ps1 을 둔다. 동기화는 단계 1·2 와
# 마무리만 떼어 실행한다. 나머지 단계는 파이썬을 설치하고 진짜 레지스트리를 수정해 가짜 홈에 가둘 수 없다.
Write-Host ''
Write-Host '동기화의 업데이트 기록'
$sy = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-sync-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path (Join-Path $sy 'bin') | Out-Null
# 테스트용 가짜 프로그램은 .cmd 가 아니라 .ps1 로 둔다. .cmd 가 호출하는 pwsh 가 스토어 버전이면
# 가짜 홈에서 "Access is denied." 로 실행되지 않는다. .ps1 은 동기화의 프로그램 안에서 실행되고
# 출력과 종료 코드를 그대로 돌려준다.
@'
if ($env:STUB_LOG) { Add-Content -LiteralPath $env:STUB_LOG -Value ($args -join ' ') }
$a = $args
$pd = Join-Path $env:USERPROFILE '.claude\plugins'
if ($a[0] -eq 'plugin' -and $a[1] -eq 'marketplace' -and $a[2] -eq 'update') {
    if ($env:STUB_SLEEP) { Start-Sleep -Seconds ([int]$env:STUB_SLEEP) }
    if ($env:STUB_MK -eq 'fail') { exit 1 }
    if ($env:STUB_MK -eq 'inuse') {
        'Could not replace the marketplace directory at X because it is in use; the existing copy was kept and the next refresh will try again.'
        exit 1
    }
    if ($a[3] -eq 'kiwoom-ax') { Set-Content -LiteralPath (Join-Path $pd 'marketplaces\kiwoom-ax\.git\refs\heads\main') $env:STUB_NEW }
    exit 0
}
if ($a[0] -eq 'plugin' -and $a[1] -eq 'install') {
    if ($env:STUB_INSTALL_FAIL -and $a[2] -eq $env:STUB_INSTALL_FAIL) { exit 1 }
    $f = Join-Path $pd 'installed_plugins.json'
    $j = Get-Content -LiteralPath $f -Raw | ConvertFrom-Json
    $j.plugins | Add-Member -NotePropertyName $a[2] -NotePropertyValue @(@{ installPath = (Join-Path $pd 'cache\x'); gitCommitSha = $env:STUB_NEW }) -Force
    $j | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $f
    exit 0
}
if ($a[0] -eq 'plugin' -and $a[1] -eq 'update') {
    if ($env:STUB_UP -eq 'fail') { exit 1 }
    $f = Join-Path $pd 'installed_plugins.json'
    $j = Get-Content -LiteralPath $f -Raw | ConvertFrom-Json
    foreach ($s in @($j.plugins.($a[2]))) { $s.gitCommitSha = $env:STUB_NEW; $s.version = $env:STUB_NEW.Substring(0, 12) }
    $j | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $f
    exit 0
}
exit 0
'@ | Set-Content -LiteralPath (Join-Path $sy 'bin\claude.ps1') -Encoding UTF8
$syncText = [System.IO.File]::ReadAllText((Join-Path $plugin 'scripts\sync.ps1'))
$cut3 = $syncText.IndexOf('# ---------------------------------------------------------------- 단계 3')
$cutEnd = $syncText.IndexOf('# ---------------------------------------------------------------- 마무리')
$syncCut = Join-Path $sy 'sync-cut.ps1'
Check '동기화를 단계 1·2 와 마무리로 뗄 수 있다' { ($cut3 -gt 0) -and ($cutEnd -gt $cut3) }
[System.IO.File]::WriteAllText($syncCut, $syncText.Substring(0, $cut3) + $syncText.Substring($cutEnd), (New-Object System.Text.UTF8Encoding($false)))

# 동기화 시나리오의 가짜 PC 에 설치되어 있는 플러그인이다. 업데이트 알림 줄 개수 같은 기대값은
# 숫자로 적지 않고 이 목록에서 센다. 플러그인을 추가할 때 이 목록만 고치면 된다.
$script:ScenarioIds = @('kw-control-tower@kiwoom-ax', 'kw-doc-formats@kiwoom-ax', 'kw-devops@kiwoom-ax', 'kw-dashboard@kiwoom-ax',
                        'kw-design@kiwoom-ax', 'document-skills@anthropic-agent-skills', 'disciplined-coder@chshin-tools')

function Invoke-SyncScenario {
    # 가짜 홈에서 떼어 낸 동기화를 실행하고 출력과 상태 파일과 설치된 플러그인의 버전을 돌려준다.
    param([string]$Mk = 'ok', [string]$Up = 'ok', [string]$State = '', [switch]$Brief, [string]$Steps = '', [int]$Budget = 0, [int]$Sleep = 0, [string]$Bin = '',
          [switch]$NoRanOnce, [string]$InstallFail = '', [string[]]$Drop = @(), [string]$Lock = '', [switch]$CloneCurrent, [string]$RealClone = '',
          [string[]]$Leftover = @())
    $h = Join-Path $sy ("h-" + [guid]::NewGuid().ToString('n').Substring(0,6))
    $pd = Join-Path $h '.claude\plugins'
    New-Item -ItemType Directory -Force -Path (Join-Path $pd 'cache\x') | Out-Null
    $ids = $script:ScenarioIds
    $plug = @{}; $en = @{}
    foreach ($id in $ids) {
        $plug[$id] = @(@{ installPath = (Join-Path $pd 'cache\x'); gitCommitSha = $shaOld; version = $shaOld.Substring(0, 12) })
        $en[$id] = $true
    }
    foreach ($d in $Drop) { $plug.Remove($d) }
    @{ version = 2; plugins = $plug } | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $pd 'installed_plugins.json')
    @{ enabledPlugins = $en } | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $h '.claude\settings.json')
    @{ 'kiwoom-ax' = @{ source = @{ source = 'github'; repo = 'KiwoomAX/kw-plugins' }; autoUpdate = $true } } |
        ConvertTo-Json -Depth 5 | Set-Content (Join-Path $pd 'known_marketplaces.json')
    $g = Join-Path $pd 'marketplaces\kiwoom-ax\.git'
    New-Item -ItemType Directory -Force -Path (Join-Path $g 'refs\heads') | Out-Null
    'ref: refs/heads/main' | Set-Content (Join-Path $g 'HEAD')
    $(if ($CloneCurrent) { $shaNew } else { $shaOld }) | Set-Content (Join-Path $g 'refs\heads\main')
    if ($RealClone) {
        # git 으로 실제로 내려받은 마켓플레이스를 둔다. 원본 코드 저장소에 체크포인트 2개를 만들고
        # 첫 체크포인트에서 내려받은 뒤 원본만 앞으로 보낸다.
        # $RealClone 이 'badjson' 이면 2번째 체크포인트의 마켓플레이스 파일이 JSON 형식이 아니다.
        $src = Join-Path $h 'src'; $mkDir = Split-Path -Parent $g
        Remove-Item -LiteralPath $mkDir -Recurse -Force
        New-Item -ItemType Directory -Force -Path (Join-Path $src '.claude-plugin') | Out-Null
        $git = @('-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'init.defaultBranch=main')
        & git -C $src init -q 2>&1 | Out-Null
        '{"name":"kiwoom-ax"}' | Set-Content (Join-Path $src '.claude-plugin\marketplace.json')
        & git -C $src add -A; & git @git -C $src commit -q -m one 2>&1 | Out-Null
        & git clone -q "file:///$($src -replace '\\', '/')" $mkDir 2>&1 | Out-Null
        $(if ($RealClone -eq 'badjson') { '{ broken' } else { '{"name":"kiwoom-ax","v":2}' }) | Set-Content (Join-Path $src '.claude-plugin\marketplace.json')
        & git -C $src add -A; & git @git -C $src commit -q -m two 2>&1 | Out-Null
    }
    $(if ($NoRanOnce) { $State } else { "ranOnce=2026-01-01`n$State" }).Trim() | Set-Content (Join-Path $h '.claude\kw-control-tower.state')
    foreach ($lo in $Leftover) {
        $n, $age = $lo -split '\|'
        $dir = New-Item -ItemType Directory -Force -Path (Join-Path $pd "marketplaces\$n")
        'x' | Set-Content (Join-Path $dir.FullName 'f.txt')
        if ($age -ne 'fresh') { $dir.LastWriteTime = (Get-Date).AddMinutes(-15) }
    }
    $lockDir = Join-Path $h '.claude\kw-control-tower.sync.lock'
    if ($Lock) {
        New-Item -ItemType Directory -Force -Path $lockDir | Out-Null
        if ($Lock -eq 'stale') { (Get-Item -LiteralPath $lockDir).CreationTime = (Get-Date).AddMinutes(-15) }
    }
    $env:STUB_MK = $Mk; $env:STUB_UP = $Up; $env:STUB_NEW = $shaNew; $env:KWCT_REMOTE_HEAD = "kiwoom-ax=$shaNew"; $env:STUB_LOG = Join-Path $h 'calls.log'
    $env:STUB_SLEEP = if ($Sleep) { "$Sleep" } else { '' }
    $env:STUB_INSTALL_FAIL = $InstallFail
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$h'; `$env:CLAUDE_PLUGIN_ROOT='$plugin'; `$env:PATH='$(if ($Bin) { $Bin } else { "$sy\bin" });' + `$env:PATH; & '$syncCut' $(if ($Brief) { '-Brief' }) $(if ($Steps) { "-Steps '$Steps'" }) $(if ($Budget) { "-BudgetSeconds $Budget" }); exit `$LASTEXITCODE" 2>&1
    $code = $LASTEXITCODE
    $log = Join-Path $h '.claude\kw-control-tower.sync.log'
    foreach ($v in 'STUB_MK', 'STUB_UP', 'STUB_NEW', 'KWCT_REMOTE_HEAD', 'STUB_LOG', 'STUB_SLEEP', 'STUB_INSTALL_FAIL') { Remove-Item "Env:\$v" -ErrorAction SilentlyContinue }
    $ip = Get-Content (Join-Path $pd 'installed_plugins.json') -Raw | ConvertFrom-Json
    @{
        Out   = ($out | ForEach-Object { "$_" }) -join "`n"
        State = (Get-Content (Join-Path $h '.claude\kw-control-tower.state') -Raw)
        Sha   = @($ip.plugins.'kw-control-tower@kiwoom-ax')[0].gitCommitSha
        Log   = $(if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Raw -Encoding UTF8 } else { '' })
        Calls = $(if (Test-Path -LiteralPath (Join-Path $h 'calls.log')) { Get-Content -LiteralPath (Join-Path $h 'calls.log') -Raw } else { '' })
        LockLeft = (Test-Path -LiteralPath $lockDir)
        Code  = $code
        Dirs  = @(Get-ChildItem -LiteralPath (Join-Path $pd 'marketplaces') -Directory -Force | ForEach-Object Name)
        Clone = $(if ($RealClone) { "$(& git -C (Join-Path $pd 'marketplaces\kiwoom-ax') rev-parse HEAD)".Trim() } else { '' })
        Src   = $(if ($RealClone) { "$(& git -C (Join-Path $h 'src') rev-parse HEAD)".Trim() } else { '' })
    }
}

$r = Invoke-SyncScenario -State "stuck-kiwoom-ax=$shaNew"
Check '업데이트에 성공하면 플러그인이 최신 버전으로 업데이트된다' { $r.Sha -eq $shaNew }
Check '이전 버전이 적은 마켓플레이스 실패 기록을 삭제한다' { $r.State -notmatch 'stuck-kiwoom-ax' }
Check '업데이트에 성공하면 재시작을 이전 버전 → 새 버전으로 안내한다' {
    ($r.Out -match '(?m)^kw-control-tower: 다시 켜야 새 버전이 적용됩니다\.') -and ($r.Out -match 'kw-control-tower@kiwoom-ax : c875eb1 → 811b47e')
}
$r = Invoke-SyncScenario -Steps '6'
Check '전달받은 단계가 아니면 실행하지 않는다' {
    ($r.Sha -eq $shaOld) -and [string]::IsNullOrWhiteSpace($r.Calls) -and ($r.Out -match '이 단계는 고칠 것이 없어 건너뜁니다')
}
$r = Invoke-SyncScenario -Steps '1,2'
Check '전달받은 단계는 실행한다' { $r.Sha -eq $shaNew }
# 훅의 제한 시간은 90초다. 동기화가 그것을 넘기면 알림이 사라진다고 보고, 동기화 스스로 멈추고 남은
# 단계를 다음 세션으로 미룬다. .ps1 가짜 프로그램은 이 프로그램 안에서 실행되어 한 호출 안에서는
# 중단할 수 없다.
$r = Invoke-SyncScenario -Budget 3 -Sleep 4 -Brief
Check '제한 시간을 넘기면 남은 호출을 하지 않고 다음 세션으로 미룬다' {
    ($r.Sha -eq $shaOld) -and ($r.Out -match '다음 세션으로 미뤘습니다') -and ($r.Calls -notmatch 'plugin update')
}
# 진짜 claude.exe 호출은 제한 시간을 넘기면 동기화가 중단한다. 인자와 표준입력에 관계없이 30초를
# 기다리는 claude.cmd 를 두고 확인한다. .cmd 는 CreateProcess 가 cmd.exe 로 실행한다.
$hang = Join-Path $sy 'hang'
New-Item -ItemType Directory -Force -Path $hang | Out-Null
'@ping -n 30 127.0.0.1 >nul' | Set-Content -LiteralPath (Join-Path $hang 'claude.cmd') -Encoding ascii
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$hangRun = Invoke-SyncScenario -Budget 3 -Bin $hang -Steps '1'
$sw.Stop()
Check '제한 시간을 넘긴 claude 호출을 중단한다' {
    ($sw.Elapsed.TotalSeconds -lt 20) -and ($hangRun.Out -match '제한 시간이 다 되어 멈췄습니다')
}
$r = Invoke-SyncScenario -Steps '2' -Drop 'document-skills@anthropic-agent-skills' -InstallFail 'document-skills@anthropic-agent-skills'
Check '단계가 실패하면 그 단계의 확인값을 적는다' { $r.State -match '(?m)^stuck-step2=[0-9A-F]{32}\s*$' }
# 마켓플레이스 업데이트는 세션마다 다시 시도한다. 확인값을 적으면 그날 단계 1 이 보류된다.
$r = Invoke-SyncScenario -Mk 'fail' -Steps '1'
Check '마켓플레이스를 업데이트하지 못해도 단계 확인값을 적지 않는다' { $r.State -notmatch 'stuck-step1' }
# 다른 프로그램이 내려받은 마켓플레이스 폴더를 사용 중이어서 클로드 코드가 교체하지 못하면 그 안에서
# git 으로 업데이트한다(2026-10-12).
$r = Invoke-SyncScenario -Mk 'inuse' -Steps '1' -RealClone 'ok'
Check '내려받은 마켓플레이스 폴더가 사용 중이면 그 안에서 git 으로 업데이트한다' {
    ($r.Clone -eq $r.Src) -and ($r.Out -notmatch '마켓플레이스를 업데이트하지 못했습니다') -and ($r.State -match '(?m)^refreshed=')
}
$r = Invoke-SyncScenario -Mk 'inuse' -Steps '1' -RealClone 'badjson'
Check '받아 둔 체크포인트의 마켓플레이스 파일에 형식 오류가 있으면 업데이트하지 않고 실패로 알린다' {
    ($r.Clone -ne $r.Src) -and ($r.Out -match '마켓플레이스를 업데이트하지 못했습니다')
}
$r = Invoke-SyncScenario -Mk 'fail' -Steps '1' -RealClone 'ok'
Check '폴더가 사용 중이어서가 아닌 실패에는 git 으로 업데이트하지 않는다' { $r.Clone -ne $r.Src }
# 내려받은 마켓플레이스가 이전 버전이라 단계 2 가 업데이트할 것이 없다고 본 실행도 최신 버전까지
# 업데이트하지 못했으면 실패해야 재시도가 멈추지 않는다.
$r = Invoke-SyncScenario -Steps '2'
Check '최신 버전까지 업데이트하지 못하면 0 이 아닌 코드로 종료한다' { ($r.Sha -eq $shaOld) -and ($r.Code -ne 0) }
$r = Invoke-SyncScenario -Mk 'inuse' -Steps '1' -RealClone 'ok' -Budget 20
Check '남은 시간이 모자라면 git 으로 업데이트하지 않는다' { $r.Clone -ne $r.Src }
$r = Invoke-SyncScenario -Steps '1' -State 'stuck-step1=00000000000000000000000000000000'
Check '단계가 성공하면 확인값을 삭제한다' { $r.State -notmatch 'stuck-step1' }
# 매번 제한 시간을 넘기는 단계를 클로드 코드를 시작할 때마다 다시 실행하지 않게, 중단된 단계도 그날은
# 다시 호출하지 않는다.
Check '제한 시간에 중단된 단계도 확인값을 적는다' { $hangRun.State -match '(?m)^stuck-step1=' }
# 시간이 모자라 시작하지 못한 호출은 실패로 적지 않는다. 원인이 앞 단계에 있다.
$r = Invoke-SyncScenario -Budget 3 -Sleep 4 -Steps '1'
Check '시작하지 못해 미룬 단계는 확인값을 적지 않는다' { $r.State -notmatch 'stuck-step1' }
# 권장은 플러그인마다 한 번이다. 하나가 실패해도 성공한 것은 기록되고, 실패한 것만 다시 해 본다.
$r = Invoke-SyncScenario -NoRanOnce -Steps '2' -InstallFail 'playwright@claude-plugins-official'
Check '권장 설치에 성공한 것만 기록한다' {
    ($r.State -match '(?m)^suggestedDone=.*superpowers@claude-plugins-official') -and
    ($r.State -notmatch 'playwright@claude-plugins-official')
}
# 권장 하나의 실패는 단계 2 전체를 막지 않는다. 막으면 같은 날 필수 플러그인 교정까지 보류된다.
Check '권장 설치 실패는 단계 확인값을 남기지 않는다' { $r.State -notmatch 'stuck-step2' }
# 기록된 것은 사용자가 제거한 뒤에도 다시 설치하지 않는다.
$r = Invoke-SyncScenario -NoRanOnce -Steps '2' -Drop 'kw-dashboard@kiwoom-ax' `
        -State 'suggestedDone=kw-devops@kiwoom-ax;kw-dashboard@kiwoom-ax;superpowers@claude-plugins-official;playwright@claude-plugins-official;frontend-design@claude-plugins-official'
Check '기록된 권장 플러그인은 제거해도 다시 설치하지 않는다' { $r.Calls -notmatch 'plugin install kw-dashboard' }
# ranOnce 만 있는 이전 버전의 PC 는 전환 때의 권장 목록을 처리한 것으로 본다. 그 목록의 것은 다시
# 설치하지 않고, 전환 뒤 권장에 새로 올린 것은 한 번 설치한다.
$r = Invoke-SyncScenario -Steps '2' -Drop 'superpowers@claude-plugins-official'
Check 'ranOnce 만 있는 PC 에서 이전 권장은 제거했으면 다시 설치하지 않는다' { $r.Calls -notmatch 'plugin install superpowers' }
$r = Invoke-SyncScenario -Steps '2' -Drop 'kw-dashboard@kiwoom-ax'
Check 'ranOnce 만 있는 PC 에도 새 권장은 한 번 설치한다' { $r.Calls -match 'plugin install kw-dashboard@kiwoom-ax' }
$r = Invoke-SyncScenario -Steps '1,2'
Check '동기화가 끝나면 잠금을 삭제한다' { ($r.Sha -eq $shaNew) -and -not $r.LockLeft }
$r = Invoke-SyncScenario -Steps '1,2' -Lock 'fresh'
Check '다른 동기화가 실행 중이면 건너뛴다' { ($r.Sha -eq $shaOld) -and ($r.Out -match '이번에는 건너뜁니다') -and ($r.Code -eq 0) }
$r = Invoke-SyncScenario -Steps '1,2' -Lock 'stale'
Check '10분 넘은 잠금은 삭제하고 실행한다' { ($r.Sha -eq $shaNew) -and -not $r.LockLeft }
# 제한 시간에 중단된 실행도 잠금을 남기지 않는다. 위의 중단 시나리오를 다시 실행한다.
$r = Invoke-SyncScenario -Budget 3 -Bin $hang -Steps '1'
Check '제한 시간에 중단된 실행도 잠금을 삭제한다' { -not $r.LockLeft }

$r = Invoke-SyncScenario -Up 'fail'
Check 'plugin update 가 실패해도 마켓플레이스 실패 기록을 남기지 않는다' { $r.State -notmatch 'stuck-kiwoom-ax' }
Check 'plugin update 가 실패하면 재시작 대신 버전 알림과 명령을 낸다' {
    ($r.Out -notmatch '다시 켜야 새 버전이 적용됩니다') -and ($r.Out -match '(?m)^kw-control-tower: 플러그인 버전 알림') -and
    ($r.Out -match 'kw-control-tower@kiwoom-ax : c875eb1 → 811b47e') -and ($r.Out -match '(?m)^\s+claude plugin update kw-control-tower@kiwoom-ax')
}

$r = Invoke-SyncScenario -Mk 'fail'
Check '마켓플레이스를 업데이트하지 못해도 최신 버전으로 알린다' {
    ($r.Out -match 'kw-control-tower@kiwoom-ax : c875eb1 → 811b47e') -and
    ($r.Out -match '(?m)^\s+claude plugin marketplace update kiwoom-ax')
}

# 세션 점검 훅은 동기화를 -Brief 로 호출한다. 진행 출력은 기록 파일로 가고 화면에는 재시작
# 안내와 업데이트한 플러그인 한 줄씩만 남는다.
$r = Invoke-SyncScenario -Brief
Check '짧게 부르면 재시작 안내 아래 한 일을 한 줄씩만 낸다' {
    $lines = @($r.Out -split "`n" | Where-Object { $_.Trim() })
    ($lines[0] -eq 'kw-control-tower: 다시 켜야 새 버전이 적용됩니다.') -and
        (@($lines | Select-Object -Skip 1 | Where-Object { $_ -notmatch '^  - ' }).Count -eq 0) -and
        (@($lines | Where-Object { $_ -match ' : c875eb1 → 811b47e$' }).Count -eq @($script:ScenarioIds | Where-Object { $_ -like '*@kiwoom-ax' }).Count) -and
        (([regex]::Matches($r.Out, 'kw-control-tower@kiwoom-ax')).Count -eq 1)
}
Check '짧게 부르면 진행 출력을 기록 파일에 남긴다' {
    ($r.Log -match '1\. 마켓플레이스를 등록하고') -and ($r.Log -match '플러그인을 새 버전으로 업데이트했습니다')
}
$r = Invoke-SyncScenario -Brief -Up 'fail'
Check '짧게 불러도 업데이트 실패는 명령과 함께 한 번만 알린다' {
    ($r.Out -match '(?m)^kw-control-tower: 플러그인 버전 알림') -and
        ($r.Out -match '(?m)^\s+claude plugin update kw-control-tower@kiwoom-ax') -and
        (([regex]::Matches($r.Out, 'kw-control-tower@kiwoom-ax')).Count -eq 2) -and ($r.Out -notmatch '마켓플레이스를 등록하고')
}
# 업데이트는 세션마다 시도하되 하루 3번 실패하거나 제한 시간에 막히면 다음 날로 미룬다(2026-10-12 사용자 결정).
$today = Get-Date -Format 'yyyy-MM-dd'
$r = Invoke-SyncScenario -Brief -Up 'fail'
Check '첫 실패는 횟수만 적고 다음 세션에 다시 시도한다고 알린다' {
    ($r.State -match "(?m)^updateFails=$today;1\s*$") -and ($r.Out -match '다음 세션을 시작할 때 다시 시도합니다\. 오늘 1/3')
}
$r = Invoke-SyncScenario -Brief -Up 'fail' -State "updateFails=$today;2"
Check '그날 3번째 실패면 다음 날로 미룬다고 알린다' {
    ($r.State -match "(?m)^updateFails=$today;3\s*$") -and ($r.Out -match '오늘은 더 시도하지 않습니다')
}
$r = Invoke-SyncScenario -Brief -Up 'fail' -State 'updateFails=2000-01-01;3'
Check '날짜가 바뀌면 실패 횟수를 1 부터 다시 센다' { $r.State -match "(?m)^updateFails=$today;1\s*$" }
$r = Invoke-SyncScenario -Budget 3 -Sleep 4 -Brief
Check '제한 시간에 막히면 바로 다음 날로 미룬다' {
    ($r.State -match "(?m)^updateFails=$today;3\s*$") -and ($r.Out -match '날짜가 바뀐 뒤 처음 시작하는 세션에서')
}
$r = Invoke-SyncScenario -Brief -State "updateFails=$today;2"
Check '업데이트에 성공하면 실패 횟수를 삭제한다' { ($r.Sha -eq $shaNew) -and ($r.State -notmatch 'updateFails') }
Check '훅과 동기화의 하루 실패 허용 횟수가 같다' {
    ($syncCode -match '\$script:MaxFails = 3\b') -and ($hookCode -match "\[int\]\`$fN -ge 3\)")
}
# 남은 교체 폴더는 마켓플레이스를 구분하지 않고 삭제한다. 등록된 이름과 방금 바뀐 폴더는 남긴다.
$r = Invoke-SyncScenario -Steps '1' -Leftover 'kiwoom-ax.bak', 'other..clone', 'third.bak|fresh', 'keep'
Check '남은 마켓플레이스 교체 폴더를 삭제한다' {
    ($r.Dirs -notcontains 'kiwoom-ax.bak') -and ($r.Dirs -notcontains 'other..clone') -and
    ($r.Dirs -contains 'third.bak') -and ($r.Dirs -contains 'keep') -and ($r.Dirs -contains 'kiwoom-ax')
}
# 이전 단계 8 이 적은 줄을 동기화가 삭제한다. 남기면 읽는 곳이 없는 줄이 상태 파일에 영영 남는다.
$r = Invoke-SyncScenario -State "python3=redirector`npython3Target=C:\x\python3.exe"
Check '동기화가 이전 python3 판정 줄을 삭제한다' { $r.State -notmatch '(?m)^python3' }
Remove-Item -LiteralPath $sy -Recurse -Force -ErrorAction SilentlyContinue

# --- 출력 스타일 -------------------------------------------------------------
Write-Host ''
Write-Host '출력 스타일'
# 동기화의 앞머리와 단계 8 과 마무리만 떼어 가짜 홈에서 실행한다. 클로드를 다루는 단계가 없어
# 테스트용 가짜 프로그램이 필요 없다.
$os = Join-Path ([System.IO.Path]::GetTempPath()) ("kwct-os-" + [guid]::NewGuid().ToString('n').Substring(0,8))
New-Item -ItemType Directory -Force -Path $os | Out-Null
$cut1 = $syncText.IndexOf('# ---------------------------------------------------------------- 단계 1')
$cut8 = $syncText.IndexOf('# ---------------------------------------------------------------- 단계 8')
$osCut = Join-Path $os 'sync-os.ps1'
[System.IO.File]::WriteAllText($osCut, $syncText.Substring(0, $cut1) + $syncText.Substring($cut8), (New-Object System.Text.UTF8Encoding($false)))

function Invoke-OutputStyle {
    # $Settings 가 $null 이면 settings.json 을 만들지 않는다. 문자열이면 그대로 쓴다.
    param($Settings)
    $h = Join-Path $os ("h-" + [guid]::NewGuid().ToString('n').Substring(0,6))
    New-Item -ItemType Directory -Force -Path (Join-Path $h '.claude') | Out-Null
    $sp = Join-Path $h '.claude\settings.json'
    if ($null -ne $Settings) { [System.IO.File]::WriteAllText($sp, $Settings, (New-Object System.Text.UTF8Encoding($false))) }
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$h'; `$env:CLAUDE_PLUGIN_ROOT='$plugin'; & '$osCut' -Brief -Steps '8'; exit `$LASTEXITCODE" 2>&1
    @{
        Code = $LASTEXITCODE
        Out  = ($out | ForEach-Object { "$_" }) -join "`n"
        Text = $(if (Test-Path -LiteralPath $sp) { [System.IO.File]::ReadAllText($sp) } else { $null })
        Bak  = (Test-Path -LiteralPath "$sp.kw.bak")
    }
}

$r = Invoke-OutputStyle '{ "model": "opus", "enabledPlugins": { "a@b": true } }'
Check '항목이 없으면 Concise 를 넣고 다른 항목은 그대로 둔다' {
    $j = $r.Text | ConvertFrom-Json
    ($j.outputStyle -ceq 'Concise') -and ($j.model -eq 'opus') -and ($j.enabledPlugins.'a@b' -eq $true)
}
Check '넣기 전에 백업을 남긴다' { $r.Bak }
Check '넣었으면 백업 경로와 되돌리는 법을 한 줄로 알린다' {
    $r.Out -match '(?m)^  - 전역 설정에 "outputStyle": "Concise" 를 적용했습니다\(백업: .+settings\.json\.kw\.bak\)\. 되돌리려면 값을 "default" 로 바꾸십시오\.$'
}
$r = Invoke-OutputStyle '{ "outputStyle": "default" }'
Check '항목이 있으면 값이 무엇이든 그대로 두고 말하지 않는다' {
    ($r.Text -match '"outputStyle": "default"') -and -not $r.Bak -and [string]::IsNullOrWhiteSpace($r.Out)
}
$r = Invoke-OutputStyle '{ "outputStyle": '
Check 'JSON 이 깨져 있으면 고치지 않는다' { ($r.Text -eq '{ "outputStyle": ') -and -not $r.Bak -and ($r.Code -ne 0) }
$r = Invoke-OutputStyle $null
Check 'settings.json 이 없으면 만들지 않는다' { ($null -eq $r.Text) -and [string]::IsNullOrWhiteSpace($r.Out) }

# 점검은 항목이 없을 때만 단계 8 을 전달한다. 동기화 스크립트를 뺀 복사본으로 훅을 실행하면 목록과
# 다른 곳의 나열이 그대로 나온다.
$osQuiet = Join-Path $os 'quiet'
Copy-Item -LiteralPath $plugin -Destination $osQuiet -Recurse
Remove-Item -LiteralPath (Join-Path $osQuiet 'scripts\sync.ps1')
function Invoke-HookWith([string]$Settings) {
    $h = Join-Path $os ("k-" + [guid]::NewGuid().ToString('n').Substring(0,6))
    New-Item -ItemType Directory -Force -Path (Join-Path $h '.claude\plugins') | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $h '.claude\settings.json'), $Settings, (New-Object System.Text.UTF8Encoding($false)))
    $out = & $ps7 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "`$env:USERPROFILE='$h'; `$env:CLAUDE_PLUGIN_ROOT='$osQuiet'; & '$osQuiet\hooks\session-check.ps1'" 2>&1
    ($out | ForEach-Object { "$_" }) -join "`n"
}
Check '점검이 outputStyle 항목이 없으면 알린다' { (Invoke-HookWith '{}') -match 'outputStyle 이 없습니다' }
Check '점검이 outputStyle 항목이 있으면 말하지 않는다' { (Invoke-HookWith '{ "outputStyle": "default" }') -notmatch 'outputStyle' }
Remove-Item -LiteralPath $os -Recurse -Force -ErrorAction SilentlyContinue

# --- 동기화가 끝까지 간다 ---------------------------------------------------
Write-Host ''
Write-Host '동기화가 끝까지 간다'
# 동기화는 네트워크와 pip 을 거치므로 오래 걸린다. 훅이 동기화가 끝날 때까지 기다리므로 훅의 제한
# 시간이 짧으면 중간에 중단된다. 보통의 PC 가 한 번에 끝낼 만큼 제한 시간을 둔다.
Check '세션 점검 훅의 제한 시간이 동기화를 끝낼 만큼이다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $j.hooks.SessionStart[0].hooks[0].timeout -ge 90
}
Check '훅이 동기화에 훅의 제한 시간보다 짧은 제한 시간을 전달한다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    $m = [regex]::Match($hookCode, '-BudgetSeconds (\d+)')
    $m.Success -and ([int]$m.Groups[1].Value -lt $j.hooks.SessionStart[0].hooks[0].timeout)
}
# 중단된 claude 가 표준입력을 기다리지 않게 바로 닫는다.
Check '동기화가 claude 의 표준입력을 바로 닫는다' { $syncSrc -match '\$p\.StandardInput\.Close\(\)' }
# 설치와 업데이트는 클로드 코드를 재시작해야 적용되므로 /clear 나 resume 에서 다시 동기화해도 이 세션에는
# 적용되지 않는다. 시작할 때만 실행한다.
Check '세션 점검 훅은 클로드 코드를 시작할 때만 실행된다' {
    $j = Get-Content (Join-Path $plugin 'hooks\hooks.json') -Raw | ConvertFrom-Json
    (@($j.hooks.SessionStart).Count -eq 1) -and ($j.hooks.SessionStart[0].matcher -eq 'startup')
}
# 훅 출력은 훅이 끝난 뒤에 한 번에 보인다. 동기화 전에 "기다려 달라" 고 적어도 동기화가 끝난
# 뒤에야 읽히므로, 대신 동기화의 결과가 출력에 포함되는지를 본다.
Check '동기화의 출력을 훅 출력에 포함한다' {
    $hookCode -match 'foreach \(\$line in \$out\) \{ \[void\]\$say\.Add'
}
# 상태를 마지막에 한 번만 적으면 제한 시간에 막혀 중단된 실행이 아무것도 하지 않은 것으로 남아,
# 다음 세션이 처음부터 다시 실행하고 그것이 끝없이 되풀이된다. 단계는 저마다 독립이고 여러 번
# 실행해도 결과가 같으므로 단계가 끝날 때마다 적어 거기까지의 진행을 남긴다.
$stepBodies = @([regex]::Split($syncCode, "(?m)^Show '\d+\. ") | Select-Object -Skip 1)
Check '단계 조각이 단계 수와 같다' { $stepBodies.Count -eq $codeSteps.Count }
Check '단계마다 끝에서 상태를 적는다' {
    @($stepBodies | Where-Object { $_ -notmatch '(?m)^Save-State\b' }).Count -eq 0
}
# 적는 곳이 단계 안에 있기만 해서는 모자란다. 상태를 고치고 나서 적어야 한다.
# 적고 나서 고치면 그 값은 다음 단계가 끝날 때까지 디스크에 남지 않아, 그 사이에
# 실행이 끊기면 유실된다.
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
# 적는 곳이 여럿이면 한 곳만 고쳐지고 나머지가 이전 방식으로 남는다.
Check '상태 파일을 적는 곳이 한 곳이다' {
    @([regex]::Matches($syncCode, 'Out-File -LiteralPath \$statePath')).Count -eq 1
}

# --- 검사가 이 PC 를 바꾸지 않는다 ------------------------------------------
Write-Host ''
Write-Host '검사가 이 PC 를 바꾸지 않는다'
# 훅을 호출하는 검사는 홈을 반드시 가짜로 준다. 진짜 USERPROFILE 을 전달하면 훅이 남기는
# 기록이 사용자의 프로필에 쌓이고, 그것을 보는 검사가 없어 아무도 모른다.
Check '훅을 호출하는 검사가 진짜 홈을 전달하지 않는다' {
    $self = Get-Content $PSCommandPath -Raw -Encoding UTF8
    $self -notmatch "USERPROFILE='\`$env:USERPROFILE'"
}

# 진짜 플러그인 폴더의 훅을 실행하면 훅이 옆의 진짜 동기화 스크립트를 찾아 호출한다. 가짜 홈에는
# 필수 플러그인이 없어 목록과 다른 곳이 늘 생기므로 동기화가 실행되고, 이 PC 의 파이썬과 레지스트리가 바뀐다.
Check '훅을 호출하는 검사가 진짜 플러그인 폴더의 훅을 실행하지 않는다' {
    $self = Get-Content $PSCommandPath -Raw -Encoding UTF8
    $self -notmatch '''\$plugin\\hooks\\session-check\.ps1'''
}

# --- 마켓플레이스 검증 ------------------------------------------------------
# 코드 저장소 전체를 여기서 한 번만 검증한다. 플러그인별 검사는 같은 검증을 따로 실행하지 않는다.
Write-Host ''
Write-Host '마켓플레이스 검증'
Push-Location $repo
try { $null = & claude plugin validate ./ 2>&1 | Out-String; $validateCode = $LASTEXITCODE } finally { Pop-Location }
Check 'claude plugin validate 가 0 으로 끝난다(경고는 허용)' { $validateCode -eq 0 }

# --- 결과 -----------------------------------------------------------------
[Console]::OutputEncoding = $consoleEncoding
Write-Host ''
if ($script:AskList.Count -gt 0) {
    Write-Host "사용자에게 물을 것 $($script:AskList.Count) 건 (실패가 아니다)" -ForegroundColor Yellow
    foreach ($a in $script:AskList) { Write-Host "  - $a" }
}
if ($script:FailList.Count -eq 0) {
    Write-Host "통과 $($script:Pass) 건, 실패 없음" -ForegroundColor Green
    exit 0
}
Write-Host "통과 $($script:Pass) 건, 실패 $($script:FailList.Count) 건" -ForegroundColor Red
foreach ($f in $script:FailList) { Write-Host "  - $f" }
exit 1
