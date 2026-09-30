# 이 PC 를 manifest.json 에 맞춘다. 세션 시작 알림 훅과 설치기 9단계가 호출한다.
#
# 단계는 저마다 독립이고 멱등이다. 한 단계가 실패해도 나머지는 돈다.
# 무엇을 했는지 마지막에 요약하고, 사용자가 끈 것을 되켰으면 그것을 따로 적는다.
#
# 이행 첫째 단계라 CLAUDE.md 단계(단계 6)은 아직 없다. 설치기가 그 일을 하고 있어
# 둘이 같은 블록을 쓰게 되기 때문이다.

[CmdletBinding()]
param(
    [switch]$WhatIfOnly,
    # 세션 시작 훅이 켠다. 진행 출력을 화면 대신 로그 파일에 적고, 화면에는 결과만 낸다.
    # 2026-09-29 재현에서 같은 네 플러그인이 여섯 번 되풀이되어 알림이 55줄이 됐다.
    [switch]$Brief,
    # 세션 시작 훅이 불일치한 단계 번호를 쉼표로 넘긴다. 넘기지 않으면(설치기) 모두 실행한다.
    [string]$Steps = '',
    # 세션 시작 훅이 넘긴다. 0 이면 상한이 없다(설치기).
    [int]$BudgetSeconds = 0
)

Set-StrictMode -Off
$ErrorActionPreference = 'Continue'

# 플러그인이 바뀌면 참이 된다. 클로드 코드는 켤 때 플러그인을 읽으므로 이 실행에서
# 깔거나 옮기거나 켜거나 걷은 것은 이 세션에 안 실린다. 마지막에 한 줄로 알린다.
#
# 알림 훅이 이 스크립트의 출력에서 문구를 찾아 판정하던 것을 그만두고 여기로 옮겼다.
# 문구가 늘 때마다 훅의 정규식을 함께 고쳐야 했는데 실제로 셋이 빠져 있었다. 갱신과
# 되켜기와 걷어내기다. 무엇이 재시작을 호출하는지는 그 일을 하는 곳이 안다.
$script:Restart = $false
$script:Did      = New-Object System.Collections.ArrayList
$script:Reenab   = New-Object System.Collections.ArrayList
$script:Failed   = New-Object System.Collections.ArrayList
$script:Moved    = New-Object System.Collections.ArrayList   # 새 버전으로 옮긴 설치본과 옛 커밋
$script:UpdateFailed = New-Object System.Collections.ArrayList   # 못 옮긴 설치본과 옮기려던 커밋
$script:Log      = New-Object System.Collections.ArrayList   # -Brief 일 때 화면 대신 모은 진행 출력
$script:Covered  = New-Object System.Collections.ArrayList   # 실패 가운데 다른 알림이 이미 말한 것
$script:FailedSteps = New-Object System.Collections.ArrayList
# 넘겼는데 비어 있으면 실행할 단계가 없다. 넘기지 않은 것과 구분해, 감지가 번호를 빠뜨린 불일치 하나가
# 모든 단계를 실행하게 만들지 않는다.
$script:StepsGiven = $PSBoundParameters.ContainsKey('Steps')
$script:Want = @($Steps.Split(',') | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ })
$script:Ran = New-Object System.Collections.ArrayList   # 이번 실행에서 실행한 단계
$script:Current = 0                                      # 지금 실행 중인 단계
$script:Deadline = if ($BudgetSeconds -gt 0) { (Get-Date).AddSeconds($BudgetSeconds) } else { $null }
# 단계를 새로 시작하려면 남아 있어야 하는 초다. pip 과 CLAUDE.md 잠금 대기는 중간에 끊지 못한다.
$script:Margin = [Math]::Min(20, [int][Math]::Floor($BudgetSeconds / 3))
$script:Deferred = New-Object System.Collections.ArrayList        # 상한에 닿아 미룬 단계
$script:TimedOutSteps = New-Object System.Collections.ArrayList   # 상한에 끊긴 호출이 있던 단계
function Get-Remaining {
    if ($null -eq $script:Deadline) { return [int]::MaxValue }
    return [int][Math]::Floor(($script:Deadline - (Get-Date)).TotalSeconds)
}

# 진행 출력은 모두 여기를 거친다. -Brief 면 모았다가 마무리에서 로그 파일에 쓴다.
function Show {
    param([string]$m, [string]$Color)
    if ($Brief) { [void]$script:Log.Add($m); return }
    if ($Color) { Write-Host $m -ForegroundColor $Color } else { Write-Host $m }
}
function Say  { param([string]$m) Show "  $m" }
function Note {
    # 미리보기에서는 한 일이 없으므로 한 일처럼 적지 않는다.
    # -Moved 는 요약에 안 넣는다. 옮긴 설치본은 재시작 안내가 커밋과 함께 적는다.
    param([string]$m, [switch]$Moved)
    if ($WhatIfOnly) { $m = "[안 함 · 미리보기] $m" }
    if (-not $Moved) { [void]$script:Did.Add($m) }
    Show "  + $m" 'Green'
}
function Fail {
    # -Covered 는 버전 알림처럼 다른 알림이 이미 말하는 실패다. 짧은 출력에서 한 번만 말한다.
    param([string]$step, [string]$m, [switch]$Covered, [switch]$NoStuck)
    [void]$script:Failed.Add("$step : $m")
    # 다른 알림이 이미 다루는 실패(갱신 실패는 stuck-<배포처>)와 단계 전체를 보류할 일이 아닌 실패
    # (권장 플러그인 하나의 설치 실패)는 단계 지문으로 적지 않는다.
    if (-not $Covered -and -not $NoStuck -and $step -match '^\d+$') { [void]$script:FailedSteps.Add([int]$step) }
    if ($Covered) { [void]$script:Covered.Add("$step : $m") }
    Show "  ! $m" 'Yellow'
}

try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

function Get-CheapHash {
    # 알림 훅과 글자 그대로 같은 계산이어야 한다. 다르면 고쳐도 알림이 안 꺼진다.
    param([string]$Path)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        return [System.BitConverter]::ToString($md5.ComputeHash($bytes)).Replace('-', '')
    } finally { $md5.Dispose() }
}

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

function Read-Json {
    # 없는 것과 못 읽는 것을 구분한다. 없으면 $null 이고 그것은 정상일 수 있다.
    # 못 읽으면 던진다. 삼키면 망가진 설정을 가진 PC 에서 이 스크립트가 아무것도
    # 안 하고 "바꾼 것이 없습니다" 라고 말한다. 설치기도 같은 이유로 못 읽는
    # settings.json 위에 절대 안 쓴다.
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json) }
    catch { throw "JSON 으로 안 읽힙니다. 손으로 고친 뒤 다시 돌리십시오: $Path" }
}
function Get-Prop {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $null }
    return $p.Value
}
function Get-SuggestedDone {
    # 한 번 처리한 권장 플러그인이다. 옛 버전은 ranOnce 하나로 권장 분기를 통째로 닫았으므로, 그 표시만
    # 있는 PC 는 이행 때(2026-09-30)의 권장 목록을 처리한 것으로 본다. 그 PC 에서 사용자가 지운 것을
    # 되살리지 않고, 그 뒤에 권장에 올린 것은 한 번 깔기 위해서다.
    param($State)
    if ($State.ContainsKey('suggestedDone')) { return @($State['suggestedDone'].Split(';') | Where-Object { $_ }) }
    if ($State.ContainsKey('ranOnce')) {
        return @('kw-devops@kiwoom-ax', 'superpowers@claude-plugins-official', 'document-skills@anthropic-agent-skills',
                 'playwright@claude-plugins-official', 'frontend-design@claude-plugins-official')
    }
    return @()
}
function Save-Json {
    # 남이 써 둔 것을 지우지 않으려고 통째로 읽어 고친 뒤 그대로 다시 쓴다.
    #
    # 셋을 지킨다. 고치기 전에 사본을 남기고, 다시 읽히지 않을 것은 안 쓰고,
    # 사람이 읽을 수 있는 글자로 쓴다.
    param($Object, [string]$Path)

    $json = ($Object | ConvertTo-Json -Depth 30)

    # 다시 안 읽힐 것은 안 쓴다. 사용자 설정을 잃느니 이 단계를 실패로 두는 편이 낫다.
    $null = $json | ConvertFrom-Json

    if (Test-Path -LiteralPath $Path) {
        Copy-Item -LiteralPath $Path -Destination "$Path.kw.bak" -Force
    }
    $tmp = "$Path.kwtmp"
    [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}
function Remove-RetiredHookEntries {
    # settings.json 의 hooks 절에서 옛 훅 연결만 걷고 걷은 개수를 돌려준다.
    #
    # 옛 훅이 없는 그룹은 모양이 어떻든 손대지 않는다. hooks 키가 없는 그룹이나 배열 안의
    # null 에서 이 단계가 멈추면 매 세션 같은 실패가 되풀이된다. 2026-09-28 에 다른 직원
    # PC 에서 그렇게 됐다. 옛 훅만 들어 있던 그룹은 빈 껍데기가 되므로 통째로 걷는다.
    param($Hooks, $Retired)
    $removed = 0
    foreach ($evt in @($Hooks.PSObject.Properties.Name)) {
        if ($null -eq $Hooks.$evt) { continue }
        $keptGroups = New-Object System.Collections.ArrayList
        foreach ($g in @($Hooks.$evt)) {
            $entries = Get-Prop $g 'hooks'
            if ($null -eq $entries) { [void]$keptGroups.Add($g); continue }
            $keptEntries = New-Object System.Collections.ArrayList
            foreach ($e in @($entries)) {
                $blob = ''
                try { $blob = ($e | ConvertTo-Json -Depth 10 -Compress) } catch { }
                $isOld = $false
                foreach ($h in $Retired) {
                    $file = Get-Prop $h 'file'
                    $pathBit = Get-Prop $h 'pathContains'
                    if ($file -and $pathBit -and $blob -and $blob.Contains($file) -and $blob.Contains($pathBit)) { $isOld = $true }
                }
                if ($isOld) { $removed++ } else { [void]$keptEntries.Add($e) }
            }
            if ($keptEntries.Count -eq @($entries).Count) { [void]$keptGroups.Add($g); continue }
            if ($keptEntries.Count -gt 0) {
                $g.hooks = @($keptEntries)
                [void]$keptGroups.Add($g)
            }
        }
        $Hooks.$evt = @($keptGroups)
    }
    return $removed
}
function Want([int]$n) {
    # 넘겨받은 단계만 실행한다. 넘겨받지 않았으면 모두 실행한다. 남은 시간이 여유보다 적으면
    # 다음 세션으로 미룬다.
    if ($script:StepsGiven -and $script:Want -notcontains $n) { return $false }
    if ((Get-Remaining) -lt [Math]::Max(1, $script:Margin)) { [void]$script:Deferred.Add($n); return $false }
    [void]$script:Ran.Add($n)
    $script:Current = $n
    return $true
}
function Resolve-Utf8Action([string]$Current) {
    # 비어 있으면 넣는다. 1 이면 할 일이 없고, 0 은 사용자가 끈 것이라 그대로 둔다.
    if ([string]::IsNullOrEmpty($Current)) { return 'set' }
    if ($Current -eq '1' -or $Current -eq '0') { return 'keep' }
    return 'fail'
}
function Invoke-Claude {
    # 클로드를 이름으로 호출하지 않고 시작할 때 한 번 찾아 둔 절대 경로로 호출한다.
    # 남은 시간만큼만 기다리고 넘으면 프로세스 트리째 끊는다.
    # -Optional 은 끊겨도 단계 전체를 끊긴 것으로 적지 않는 호출이다(권장 플러그인 설치).
    param([string[]]$ClaudeArgs, [switch]$Optional)
    if ($WhatIfOnly) { Say "[미리보기] claude $($ClaudeArgs -join ' ')"; return $true }
    if (-not $script:ClaudeExe) { throw '클로드 코드를 못 찾았습니다. claude 가 PATH 에 있어야 합니다.' }
    $left = Get-Remaining
    if ($left -le 0) {
        # 시작하지 않은 호출은 미룬 것이다. 끊긴 것으로 적으면 앞 단계 탓에 이 단계가 그날 보류된다.
        Say "시간 상한에 닿아 실행하지 않았습니다: claude $($ClaudeArgs -join ' ')"
        [void]$script:Deferred.Add($script:Current)
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
        if (-not $Optional) { [void]$script:TimedOutSteps.Add($script:Current) }
        # 쓰기 도중에 끊었으면 설정 파일이 반쯤 쓰였을 수 있다. 읽히는지 보고 못 읽으면 알린다.
        foreach ($cf in @((Join-Path $pluginsDir 'installed_plugins.json'), $knownPath)) {
            try { $null = Read-Json $cf } catch { Fail "$script:Current" "끊은 뒤 설정 파일을 읽지 못합니다. 클로드 코드를 다시 켜 확인해 주십시오: $cf" }
        }
        return $false
    }
    foreach ($l in (($outTask.Result + "`n" + $errTask.Result) -split "`r?`n")) { if ($l) { Say $l } }
    return ($p.ExitCode -eq 0)
}

$userHome = $env:USERPROFILE
if ([string]::IsNullOrEmpty($userHome)) { Write-Error '윈도가 아닙니다. 이 스크립트는 윈도 전용입니다.'; exit 1 }

# 사내 문안 블록을 조립한다. 블록은 문안을 직접 싣지 않고 ~/.claude/kw-ax/ 에 복사한
# 템플릿을 @import 로 싣는다. 템플릿이 바뀌어도 블록은 그대로라 CLAUDE.md 를 다시 쓰지 않는다.
# CLAUDE.md 에 disciplined-coder 블록이 있으면 답변 원칙과 한국어 지시사항과 금지어 목록을
# 그쪽이 실으므로 사내 문안만 싣는다.
# 점검 훅에도 같은 함수가 있다. 둘이 다르게 조립하면 맞춤이 쓴 블록을 훅이 다르다고 알린다.
function Get-AxBlock([string]$claudeMd) {
    $files = @('claude-md-ko.md')
    if ($claudeMd -notmatch '(?m)^#\s*BEGIN disciplined-coder\b') {
        $files += @('claude-md-ko-principles.md', 'korean-banned-words.md')
    }
    $lines = @('# BEGIN AX 설치 (자동 생성 블록 — 직접 고치지 마십시오)') + @($files | ForEach-Object { "@kw-ax/$_" }) + @('# END AX 설치')
    return $lines -join "`n"
}

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

function Get-MarketplaceHead {
    # 배포처 사본이 받아 둔 버전을 읽는다. 알림 훅의 같은 이름 함수와 같은 것을 본다.
    # 둘이 다른 값을 보면 알림이 말한 것을 맞춤이 못 고치는 PC 가 생긴다.
    param([string]$Dir)
    $g = Join-Path $Dir '.git'
    $h = Join-Path $g 'HEAD'
    if (Test-Path -LiteralPath $h) {
        $line = (Get-Content -LiteralPath $h -Raw -Encoding UTF8).Trim()
        if ($line.StartsWith('ref: ')) {
            $refFile = Join-Path $g ($line.Substring(5))
            if (Test-Path -LiteralPath $refFile) {
                return (Get-Content -LiteralPath $refFile -Raw -Encoding UTF8).Trim()
            }
            return $null
        }
        return $line
    }
    $gcs = Join-Path $Dir '.gcs-sha'
    if (Test-Path -LiteralPath $gcs) { return (Get-Content -LiteralPath $gcs -Raw -Encoding UTF8).Trim() }
    return $null
}

$root = $env:CLAUDE_PLUGIN_ROOT
if ([string]::IsNullOrEmpty($root)) { $root = Split-Path -Parent $PSScriptRoot }

$cfg          = Join-Path $userHome '.claude'
$pluginsDir   = Join-Path $cfg 'plugins'
$settingsPath = Join-Path $cfg 'settings.json'
$knownPath    = Join-Path $pluginsDir 'known_marketplaces.json'
$statePath    = Join-Path $cfg 'kw-control-tower.state'
$backupDir    = Join-Path $cfg 'kw-control-tower-backups'

$manifest = Read-Json (Join-Path $root 'manifest.json')
if ($null -eq $manifest) { Write-Error "목록 파일을 못 읽었습니다: $root\manifest.json"; exit 1 }

# 읽히는 것과 형식이 맞는 것은 다르다. 키 이름을 하나 잘못 적으면 JSON 으로는
# 읽히고 그 목록만 조용히 비어, 아무것도 안 하고 성공으로 끝난다. 있어야 할 칸이
# 다 있는지 보고 없으면 멈춘다. 값이 비어 있는 것은 정상이라 개수는 안 본다.
$required = @('marketplaces', 'required', 'suggested', 'retiredPlugins',
              'retiredMarketplaces', 'retiredSkills', 'retiredHooks')
$missing = @($required | Where-Object { $null -eq $manifest.PSObject.Properties[$_] })
if ($missing.Count -gt 0) {
    Write-Error "목록 파일에 칸이 빠졌습니다: $($missing -join ', ') — $root\manifest.json"
    exit 1
}

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

# 상태 파일에는 단계가 기억해야 하는 것만 적는다. 라이브러리 목록 해시(requirements), 받아온 시각
# (refreshed), 권장 기록(suggestedDone), 배포처별 갱신 실패(stuck-<배포처>), 단계별 실패 지문
# (stuck-step<N>)이다. 옛 버전이 적은 ranOnce 는 권장 기록을 이행할 때만 읽는다.
$state = @{}
if (Test-Path -LiteralPath $statePath) {
    foreach ($line in (Get-Content -LiteralPath $statePath -Encoding UTF8)) {
        $i = $line.IndexOf('=')
        if ($i -gt 0) { $state[$line.Substring(0, $i)] = $line.Substring($i + 1) }
    }
}
# 옛 버전의 단계 8 이 적던 python3 판정이다. 가드가 호출할 때 직접 판정하므로 남은 줄을 지운다.
$state.Remove('python3'); $state.Remove('python3Target')
$script:Refreshed = $false

# 단계가 끝날 때마다 호출한다. 훅의 예산에 막혀 도중에 죽더라도 거기까지의 진행이
# 디스크에 남아 다음 세션이 이어받는다. 마지막에 한 번만 적던 때에는 죽은 실행이
# 아무것도 안 한 것으로 남아, 같은 반쪽 실행이 매 세션 되풀이됐다.
#
# 세션 시작 훅은 불일치한 단계만 넘기고 설치기는 모두 실행한다. 단계는 멱등이라 다시 실행해도 해가 없다.
function Save-State {
    if ($WhatIfOnly) { return }
    $lines = foreach ($k in $state.Keys) { "$k=$($state[$k])" }
    $lines | Out-File -LiteralPath $statePath -Encoding UTF8
}

$script:ClaudeExe = (Get-Command claude -ErrorAction SilentlyContinue).Source

Show ''
Show 'KW 컨트롤 타워 맞춤' 'Cyan'
Show ''
if (-not $script:ClaudeExe -and -not $WhatIfOnly) {
    Show '  클로드 코드를 못 찾았습니다. 플러그인을 다루는 단계 셋은 건너뜁니다.' 'Yellow'
    Show '  나머지 단계는 그대로 돕니다.'
}

# ---------------------------------------------------------------- 단계 1
Show '1. 배포처를 등록하고 최신으로 받아옵니다.'
if (Want 1) {
try {
    $settings = Read-Json $settingsPath
    if ($null -eq $settings) { throw "settings.json 을 못 읽었습니다." }
    $known = Read-Json $knownPath

    foreach ($mk in @($manifest.marketplaces)) {
        $name = Get-Prop $mk 'name'
        $repo = Get-Prop $mk 'repo'
        $ours = ((Get-Prop $mk 'ours') -eq $true)

        $inSettings = ($null -ne (Get-Prop (Get-Prop $settings 'extraKnownMarketplaces') $name))
        $knownRoot  = Get-Prop $known 'marketplaces'
        if ($null -eq $knownRoot) { $knownRoot = $known }
        $inKnown    = ($null -ne (Get-Prop $knownRoot $name))

        if (-not $inSettings -and -not $inKnown) {
            if (Invoke-Claude @('plugin', 'marketplace', 'add', $repo)) { Note "배포처를 등록했습니다: $name" }
            else { Fail '1' "배포처 등록에 실패했습니다: $name" }
            continue
        }

        # 자동 갱신은 우리 배포처만 켠다. 남의 배포처의 그 값은 언제나 사용자의 것이다.
        if (-not $ours) { continue }

        $settings = Read-Json $settingsPath
        $known    = Read-Json $knownPath
        $a = Get-Prop (Get-Prop $settings 'extraKnownMarketplaces') $name
        $kr = Get-Prop $known 'marketplaces'; if ($null -eq $kr) { $kr = $known }
        $b = Get-Prop $kr $name

        $wrote = $false
        if ($null -ne $a -and (Get-Prop $a 'autoUpdate') -ne $true) {
            if (-not $WhatIfOnly) {
                $a | Add-Member -NotePropertyName 'autoUpdate' -NotePropertyValue $true -Force
                Save-Json $settings $settingsPath
            }
            $wrote = $true
        }
        if ($null -ne $b -and (Get-Prop $b 'autoUpdate') -ne $true) {
            if (-not $WhatIfOnly) {
                $b | Add-Member -NotePropertyName 'autoUpdate' -NotePropertyValue $true -Force
                Save-Json $known $knownPath
            }
            $wrote = $true
        }
        if ($wrote) { Note "자동 갱신을 켰습니다: $name" }

        # 자동 갱신을 켜 두어도 사본이 최신이 되지는 않는다. 2026-09-19 에 이 PC 에서
        # 자동 갱신이 켜진 배포처 둘이 각각 다른 단계에서 멈춰 있는 것을 확인했다.
        # 하나는 사본을 받아 놓고 설치본을 안 옮겼고, 다른 하나는 사본이 26일째
        # 안 움직였다. 그래서 여기서 직접 받아온다.
        if (-not $WhatIfOnly) {
            if (Invoke-Claude @('plugin', 'marketplace', 'update', $name)) {
                $script:Refreshed = $true
            } else { Fail '1' "배포처를 받아오지 못했습니다: $name" }
        } else { Say "$name : 배포처를 받아옵니다." }
    }
} catch { Fail '1' $_.Exception.Message }

# 받아온 시각을 적는다. 알림이 이 값을 보고 오래 안 받아왔는지 판정한다. 저장소에
# 새 커밋이 없어 사본이 안 움직이는 때에도 이 값은 움직이므로 알림이 되풀이되지 않는다.
if ($script:Refreshed) { $state['refreshed'] = (Get-Date -Format o) }
} else { Say '넘겨받은 불일치가 없어 넘어갑니다.' }
Save-State

# ---------------------------------------------------------------- 단계 2
Show '2. 필수 플러그인을 맞춥니다.'
if (Want 2) {
try {
    $installed = Read-Json (Join-Path $pluginsDir 'installed_plugins.json')
    $settings  = Read-Json $settingsPath
    $installedOf = Get-Prop $installed 'plugins'
    $enabled     = Get-Prop $settings 'enabledPlugins'

    foreach ($id in @($manifest.required)) {
        $entry = Get-Prop $installedOf $id
        $onDisk = $false
        if ($null -ne $entry) {
            foreach ($scope in @($entry)) {
                $p = Get-Prop $scope 'installPath'
                if ($p -and (Test-Path -LiteralPath $p)) { $onDisk = $true }
            }
        }

        if (-not $onDisk) {
            # 안 깔린 것에만 install 을 쓴다. install 은 사용자가 꺼 둔 값을 true 로 덮는다.
            #
            # id 가 바뀐 플러그인이 이 분기로 온다. 새 id 에는 켜짐 키가 없어 "안 깔림" 으로
            # 판정되기 때문이다. 그때 사용자가 옛 id 를 꺼 두었다면 install 이 그 뜻을 조용히
            # 뒤집는다. 켜는 것 자체는 회사가 필수로 정했으니 맞지만, 말 없이 넘어가면 아래
            # '되켠 것' 이 비어 사용자가 자기 결정이 뒤집힌 줄 모른다.
            $wasOff = $false
            foreach ($rp in @($manifest.retiredPlugins)) {
                if ((Get-Prop $rp 'replacedBy') -ne $id) { continue }
                $oldId = Get-Prop $rp 'id'
                if ($oldId -and (Get-Prop $enabled $oldId) -eq $false) { $wasOff = $true }
            }
            if (Invoke-Claude @('plugin', 'install', $id)) {
                Note "플러그인을 깔았습니다: $id"
                $script:Restart = $true
                if ($wasOff) { [void]$script:Reenab.Add("$id (옛 이름으로 꺼 두셨던 것입니다)") }
            }
            else { Fail '2' "설치에 실패했습니다: $id" }
            continue
        }

        if ((Get-Prop $enabled $id) -ne $true) {
            if (Invoke-Claude @('plugin', 'enable', $id)) {
                Note "꺼져 있던 필수 플러그인을 다시 켰습니다: $id"
                $script:Restart = $true
                [void]$script:Reenab.Add($id)
            } else { Fail '2' "다시 켜지 못했습니다: $id" }
        }
    }

    # 권장은 플러그인마다 한 번만 깐다. 깔았거나 이미 있던 것은 suggestedDone 에 적고, 사용자가
    # 나중에 지워도 다시 깔지 않는다. uninstall 은 흔적을 모두 지워 지운 것과 처음 보는 것이
    # 구별되지 않으므로 이 기록이 유일한 근거다. 설치에 실패한 것만 다음에 다시 해 본다.
    $done = @(Get-SuggestedDone $state)
    foreach ($id in @($manifest.suggested)) {
        if ($done -contains $id) { continue }
        if ($null -ne (Get-Prop $installedOf $id)) { $done += $id; continue }
        if (Invoke-Claude @('plugin', 'install', $id) -Optional) {
            Note "권장 플러그인을 깔았습니다: $id"
            $script:Restart = $true
            $done += $id
        }
        else { Fail '2' "권장 플러그인 설치에 실패했습니다: $id" -NoStuck }
    }
    if (-not $WhatIfOnly) { $state['suggestedDone'] = ($done -join ';') }

    # 우리 배포처에서 온 것이 사본보다 뒤처졌으면 옮긴다. 자동 갱신이 해 주기로 되어
    # 있는 일인데 실제로는 멈추는 것을 확인했다. install 은 이미 깔린 것에 안 쓴다.
    # 사용자가 꺼 둔 값을 true 로 덮기 때문이고, 버전만 옮기는 것은 update 다.
    $ipNow = Read-Json (Join-Path $pluginsDir 'installed_plugins.json')
    $ipOf  = Get-Prop $ipNow 'plugins'
    foreach ($mk in @($manifest.marketplaces)) {
        if ((Get-Prop $mk 'ours') -ne $true) { continue }
        $mkName = Get-Prop $mk 'name'
        $head = Get-MarketplaceHead (Join-Path (Join-Path $pluginsDir 'marketplaces') $mkName)
        if (-not $head -or $null -eq $ipOf) { continue }
        foreach ($pluginId in @($ipOf.PSObject.Properties.Name)) {
            if (-not $pluginId.EndsWith("@$mkName")) { continue }
            $behind = $null
            foreach ($scope in @(Get-Prop $ipOf $pluginId)) {
                $sha = Get-Prop $scope 'gitCommitSha'
                if ($sha -and -not $head.StartsWith($sha) -and -not $sha.StartsWith($head)) { $behind = $sha }
            }
            if (-not $behind) { continue }
            if (Invoke-Claude @('plugin', 'update', $pluginId)) {
                Note "설치본을 새 버전으로 옮겼습니다: $pluginId" -Moved
                $script:Restart = $true
                [void]$script:Moved.Add(@{ Id = $pluginId; Old = $behind })
            }
            else {
                Fail '2' "설치본을 못 옮겼습니다: $pluginId" -Covered
                [void]$script:UpdateFailed.Add(@{ Id = $pluginId; Mk = $mkName; Old = $behind; Target = $head })
            }
        }
    }

    # 알림 훅이 넘긴 원격 커밋까지 옮겼는지 적는다. 못 옮겼으면 훅은 같은 원격 커밋으로
    # 맞춤을 다시 호출하지 않는다. 배포처를 받아오지 못해 사본이 옛 커밋에 머문 때도
    # 여기서 잡힌다. 위 반복은 사본과 견주므로 그때는 옮길 것이 없다고 보기 때문이다.
    $remoteOf = @{}
    foreach ($pair in ("$env:KWCT_REMOTE_HEAD" -split ';')) {
        $i = $pair.IndexOf('=')
        if ($i -gt 0) { $remoteOf[$pair.Substring(0, $i)] = $pair.Substring($i + 1) }
    }
    if ($remoteOf.Count -gt 0 -and -not $WhatIfOnly) {
        $ipOf = Get-Prop (Read-Json (Join-Path $pluginsDir 'installed_plugins.json')) 'plugins'
        foreach ($mkName in @($remoteOf.Keys)) {
            $late = $false
            if ($null -ne $ipOf) {
                foreach ($pluginId in @($ipOf.PSObject.Properties.Name)) {
                    if (-not $pluginId.EndsWith("@$mkName")) { continue }
                    foreach ($scope in @(Get-Prop $ipOf $pluginId)) {
                        $sha = Get-Prop $scope 'gitCommitSha'
                        if ($sha -and -not $remoteOf[$mkName].StartsWith($sha)) {
                            $late = $true
                            # 배포처를 못 받아와 위 반복이 옮길 것이 없다고 본 설치본도 알린다.
                            # 이미 실패로 적은 것은 원격 커밋으로 목표만 바꾼다.
                            $known = @($script:UpdateFailed | Where-Object { $_.Id -eq $pluginId })
                            if ($known.Count -gt 0) { $known[0].Target = $remoteOf[$mkName] }
                            else { [void]$script:UpdateFailed.Add(@{ Id = $pluginId; Mk = $mkName; Old = $sha; Target = $remoteOf[$mkName] }) }
                        }
                    }
                }
            }
            # 원격 커밋 탓으로 못 옮겼다고 적는 조건은 두 가지다. 사본이 원격 커밋에 있어야 하고(이번 실행에서
            # 단계 1 로 받아왔거나 사본이 이미 원격 커밋과 같다), 단계 1·2 가 끊기지도 미뤄지지도 않아야 한다.
            # 사본이 옛것이면 단계 2 는 옮길 것이 없다고 보므로, 그때 적으면 새 커밋이 생길 때까지 재시도하지 않는다.
            # 사본이 이미 최신이면 알림은 단계 2 만 넘기므로, 단계 1 을 요구하면 update 실패가 기록되지 않는다.
            $cloneHead = Get-MarketplaceHead (Join-Path (Join-Path $pluginsDir 'marketplaces') $mkName)
            $cloneOk = ($script:Ran -contains 1) -or
                ($cloneHead -and $remoteOf[$mkName] -and ($remoteOf[$mkName].StartsWith($cloneHead) -or $cloneHead.StartsWith($remoteOf[$mkName])))
            $clean = $cloneOk -and -not (@(1, 2) | Where-Object { ($script:TimedOutSteps -contains $_) -or ($script:Deferred -contains $_) })
            if ($late -and $clean) { $state["stuck-$mkName"] = $remoteOf[$mkName] }
            elseif (-not $late) { $state.Remove("stuck-$mkName") }
        }
    }
} catch { Fail '2' $_.Exception.Message }
} else { Say '넘겨받은 불일치가 없어 넘어갑니다.' }
Save-State

# ---------------------------------------------------------------- 단계 3
Show '3. 더 안 쓰는 플러그인과 배포처를 정리합니다.'
if (Want 3) {
try {
    # 플러그인을 먼저 걷고 배포처를 나중에 걷는다. 배포처를 먼저 지우면 그 플러그인을
    # 이름으로 못 호출한다.
    $installed = Read-Json (Join-Path $pluginsDir 'installed_plugins.json')
    $settings  = Read-Json $settingsPath
    $installedOf = Get-Prop $installed 'plugins'
    $enabled     = Get-Prop $settings 'enabledPlugins'

    foreach ($p in @($manifest.retiredPlugins)) {
        $id = Get-Prop $p 'id'
        if (-not $id) { continue }
        if (-not ((Get-Prop $installedOf $id) -or ($null -ne (Get-Prop $enabled $id)))) { continue }

        # 대체가 확인된 뒤에만 걷는다. 먼저 걷고 설치가 실패하면 그 플러그인이 아예
        # 없는 PC 가 된다. 2026-09-06 에 이 PC 에서 실제로 그렇게 됐다. 단계 2 가
        # 새 이름을 못 깔았는데 이 단계가 옛 이름을 걷어, 문서 스킬이 사라졌다.
        $by = Get-Prop $p 'replacedBy'
        if ($by) {
            $ipNow = Read-Json (Join-Path $pluginsDir 'installed_plugins.json')
            $entryNow = Get-Prop (Get-Prop $ipNow 'plugins') $by
            $replacedOnDisk = $false
            foreach ($scope in @($entryNow)) {
                $pth = Get-Prop $scope 'installPath'
                if ($pth -and (Test-Path -LiteralPath $pth)) { $replacedOnDisk = $true }
            }
            if (-not $replacedOnDisk) {
                Say "$id : 대체할 $by 가 아직 안 깔려 있어 그대로 둡니다."
                continue
            }
        }

        if (Invoke-Claude @('plugin', 'uninstall', $id)) { Note "플러그인을 걷었습니다: $id"; $script:Restart = $true }
        else { Fail '3' "걷지 못했습니다: $id" }
    }

    foreach ($mk in @($manifest.retiredMarketplaces)) {
        $name = Get-Prop $mk 'name'
        if (-not $name) { continue }
        $settings = Read-Json $settingsPath
        $known    = Read-Json $knownPath
        $kr = Get-Prop $known 'marketplaces'; if ($null -eq $kr) { $kr = $known }
        $present = ($null -ne (Get-Prop (Get-Prop $settings 'extraKnownMarketplaces') $name)) -or ($null -ne (Get-Prop $kr $name))

        # 그 배포처에서 온 플러그인이 아직 깔려 있으면 등록을 안 걷는다. 위의 플러그인
        # 분기가 대체를 못 찾아 건너뛰었을 때 여기만 걷히면, 옛 플러그인은 깔린 채
        # 배포처만 사라진 PC 가 된다. 플러그인에만 대체 가드를 적용하고 배포처에 적용하지 않은 것이
        # 그 비대칭이었다. 남은 것이 없을 때만 걷는다.
        $ipNow = Read-Json (Join-Path $pluginsDir 'installed_plugins.json')
        $ipOf  = Get-Prop $ipNow 'plugins'
        $left  = @()
        if ($null -ne $ipOf) { $left = @($ipOf.PSObject.Properties.Name | Where-Object { $_ -like "*@$name" }) }
        if ($left.Count -gt 0) {
            Say "$name : 이 배포처에서 온 $($left -join ', ') 가 아직 깔려 있어 그대로 둡니다."
            continue
        }

        if ($present) {
            if (Invoke-Claude @('plugin', 'marketplace', 'remove', $name)) { Note "배포처를 걷었습니다: $name" }
            else { Fail '3' "배포처를 걷지 못했습니다: $name" }
        }
    }
} catch { Fail '3' $_.Exception.Message }
} else { Say '넘겨받은 불일치가 없어 넘어갑니다.' }
Save-State

# ---------------------------------------------------------------- 단계 4
Show '4. 파이썬 라이브러리를 맞춥니다.'
if (Want 4) {
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
            # 연결이 안 될 때 재시도로 수십 초를 쓰지 않게 대기와 재시도를 줄인다. 세션 시작 상한이 pip 은 끊지 못한다.
            $pipOut = & $py.Source -m pip install --quiet --disable-pip-version-check --timeout 10 --retries 1 -r $req 2>&1
            if ($LASTEXITCODE -ne 0) {
                foreach ($l in $pipOut) { Say $l }
                throw "pip 이 코드 $LASTEXITCODE 로 끝났습니다."
            }
            Note '파이썬 라이브러리를 목록에 맞췄습니다.'
            $state['requirements'] = $newHash
        }
    }
} catch { Fail '4' $_.Exception.Message }
} else { Say '넘겨받은 불일치가 없어 넘어갑니다.' }
Save-State

# ---------------------------------------------------------------- 단계 5
Show '5. PYTHONUTF8 을 봅니다.'
if (Want 5) {
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
} else { Say '넘겨받은 불일치가 없어 넘어갑니다.' }
Save-State

# ---------------------------------------------------------------- 단계 6
Show '6. CLAUDE.md 의 사내 문안 블록을 맞춥니다.'
if (Want 6) {

try {
    $tplDir = Join-Path $root 'templates'
    $tpl    = Join-Path $tplDir 'claude-md-ko.md'
    if (-not (Test-Path -LiteralPath $tpl)) { throw "문안 템플릿이 없습니다: $tpl" }

    $utf8 = New-Object System.Text.UTF8Encoding($false)

    # 블록이 @import 로 싣는 파일을 먼저 복사하고 그다음에 블록을 쓴다. 순서가 반대면
    # 블록이 아직 없는 파일을 가리키는 세션이 생기고, @import 는 없는 파일을 알리지 않는다.
    $target = Join-Path $userHome '.claude\CLAUDE.md'
    $axDir = Join-Path $cfg 'kw-ax'
    if (-not $WhatIfOnly -and -not (Test-Path -LiteralPath $axDir)) { New-Item -ItemType Directory -Path $axDir | Out-Null }
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

    $lock   = "$target.lock"

    # 잠금 규약을 disciplined-coder 와 맞춘다. 같은 파일을 둘이 고치므로 서로
    # 배제되어야 한다. 규약은 폴더를 만드는 것이 곧 잠그는 것이고, 문지기 폴더를
    # 따로 두어 나이를 보는 것과 빼앗는 것 사이가 벌어지지 않게 한다.
    $token = [guid]::NewGuid().ToString('n')
    $held  = $false
    if (-not $WhatIfOnly) {
        $gateMiss = 0
        for ($tick = 0; $tick -lt 600; $tick++) {
            $gate = "$lock.gate"
            try {
                New-Item -ItemType Directory -Path $gate -ErrorAction Stop | Out-Null
                $gateMiss = 0
                try {
                    New-Item -ItemType Directory -Path $lock -ErrorAction Stop | Out-Null
                    [System.IO.File]::WriteAllText((Join-Path $lock 'heldsince'), [string][int][double]::Parse((Get-Date -UFormat %s)))
                    [System.IO.File]::WriteAllText((Join-Path $lock 'owner'), $token)
                    $held = $true
                } catch {
                    # 이미 누가 잡고 있다. 열 초를 넘게 잡고 있으면 빼앗는다.
                    $born = 0
                    try { $born = [int](Get-Content -LiteralPath (Join-Path $lock 'heldsince') -ErrorAction Stop) } catch { }
                    $now = [int][double]::Parse((Get-Date -UFormat %s))
                    if ($born -eq 0 -or ($now - $born) -ge 10) { Remove-Item -LiteralPath $lock -Recurse -Force -ErrorAction SilentlyContinue }
                }
                Remove-Item -LiteralPath $gate -Recurse -Force -ErrorAction SilentlyContinue
            } catch {
                # 상대가 문지기를 만든 채 종료되면 문지기가 남는다. 문지기는 잠금을 잡는 순간에만 쥐므로
                # 연속으로 200번(약 10초) 못 만들면 남은 것으로 보고 치운다.
                $gateMiss++
                if ($gateMiss -ge 200) { Remove-Item -LiteralPath $gate -Recurse -Force -ErrorAction SilentlyContinue; $gateMiss = 0 }
                Start-Sleep -Milliseconds 50; continue
            }
            if ($held) { break }
            Start-Sleep -Milliseconds 50
        }
        if (-not $held) { throw "CLAUDE.md 의 잠금을 못 잡았습니다: $lock" }
    }

    try {
        # 파일에 실제로 들어 있는 것($fileNow)과 고쳐 나가는 것($original)을 구분한다.
        # 둘을 한 변수로 두면, 메모리에서 고친 뒤 그 고친 것과 결과를 견주게 되어
        # "이미 같다" 로 끝나고 파일은 안 고쳐진다. 실제로 그렇게 됐다.
        $fileNow = ''
        if (Test-Path -LiteralPath $target) { $fileNow = [System.IO.File]::ReadAllText($target, $utf8) }
        $original = $fileNow
        $block = Get-AxBlock $fileNow

        # 옛 버전은 금지어 목록을 AX 블록 바깥의 공용 블록으로 실었다. 지금은
        # disciplined-coder 가 없을 때 AX 블록 안에 싣는다. 그때 옛 공용 블록이 남아
        # 있으면 목록이 두 벌 실리므로, 우리 목록을 가리키는 공용 블록만 걷는다.
        # disciplined-coder 가 있으면 공용 블록은 그쪽 것이라 건드리지 않는다.
        $reShared = '(?ms)^#\s*BEGIN korean-banned-words\b[^\r\n]*\r?\n@kw-ax/korean-banned-words\.md\r?\n#\s*END korean-banned-words[^\r\n]*(\r?\n)?'
        if ($original -notmatch '(?m)^#\s*BEGIN disciplined-coder\b' -and $original -match $reShared) {
            $original = [regex]::Replace($original, $reShared, '') -replace '(\r?\n){3,}', '$1$1'
            Note 'CLAUDE.md 에서 옛 금지어 공용 블록을 걷습니다. 목록은 이제 사내 문안 블록 안에 실립니다.'
        }

        # 템플릿의 줄바꿈은 깃이 어떻게 체크아웃했는지에 따라 달라진다. 그대로 쓰면 PC 마다
        # 한 번씩 줄바꿈만 바꾸는 헛수고를 하고, 파일의 줄바꿈이 섞이게 된다.
        # 대상 파일이 쓰는 줄바꿈에 맞춘다. 파일이 없으면 윈도 기본인 CRLF 다.
        $nl = "`r`n"
        if ($fileNow -and ([regex]::Matches($fileNow, "`r`n").Count -eq 0)) { $nl = "`n" }
        $block = ($block -replace "`r`n", "`n")
        if ($nl -eq "`r`n") { $block = ($block -replace "`n", "`r`n") }

        # 마커는 아스키 접두로만 찾는다. 뒤는 한국어라 괄호 안 문구가 바뀌어도 살아남는다.
        $reBlock = '(?ms)^#\s*BEGIN AX\b.*?^#\s*END AX[^\r\n]*'

        # 블록이 둘 이상이면 먼저 하나로 줄인다. 안 그러면 이 아래 정규식이 첫 블록만
        # 보고 "이미 같다" 로 끝나, 중복이 조용히 남는다. 지우는 것은 우리 마커 사이뿐이라
        # 사용자가 쓴 것은 안 건드린다. 첫 것을 남기고 뒤엣것을 걷는다.
        # 짝 없는 BEGIN 이 있으면 손대지 않는다. 그대로 두면 다음 실행에서 그 BEGIN 이
        # 새 블록의 END 와 짝지어져, 둘 사이의 사용자 글이 통째로 지워진다. 실제로
        # 재현했다. 두 번째 실행에서 사라진다. 블록을 세는 검사는 이것을 못 잡는다.
        # 세어 보면 하나가 맞기 때문이다.
        $opens = @([regex]::Matches($original, '(?m)^#\s*BEGIN AX\b')).Count
        $pairs = @([regex]::Matches($original, $reBlock)).Count
        if ($opens -gt $pairs) {
            throw "CLAUDE.md 에 END 가 없는 '# BEGIN AX' 가 있습니다. 손대지 않았습니다. 그 줄을 지우거나 '# END AX 설치' 를 짝지어 주십시오."
        }

        $blocks = @([regex]::Matches($original, $reBlock))
        if ($blocks.Count -gt 1) {
            for ($i = $blocks.Count - 1; $i -ge 1; $i--) {
                $original = $original.Remove($blocks[$i].Index, $blocks[$i].Length)
            }
            $original = ($original -replace '(\r?\n){3,}', ($nl + $nl))
            Note "CLAUDE.md 에 사내 문안 블록이 $($blocks.Count) 개 있어 하나로 줄였습니다."
        }

        if ($original -match $reBlock) {
            $merged = [regex]::Replace($original, $reBlock, { $block })
            $mode = '고쳤습니다'
        } elseif ($original.Trim()) {
            $merged = $original.TrimEnd() + $nl + $nl + $block + $nl
            $mode = '뒤에 붙였습니다'
        } else {
            $merged = $block + $nl
            $mode = '새로 만들었습니다'
        }

        if ($merged -eq $fileNow) { Say '이미 템플릿과 같습니다.' }
        elseif ($WhatIfOnly) { Say "[미리보기] CLAUDE.md 의 사내 문안 블록을 $mode" }
        else {
            # 쓰기 전에 결과를 본다. 블록이 하나가 아니면 다음 실행이 자기 블록을 못
            # 찾아 사본을 하나 더 붙인다. 사용자 파일이라 그렇게 두느니 안 쓴다.
            $count = @([regex]::Matches($merged, $reBlock)).Count
            if ($count -ne 1) { throw "블록이 하나여야 하는데 $count 개가 됩니다. CLAUDE.md 를 안 고쳤습니다." }

            if ($fileNow) { [System.IO.File]::WriteAllText("$target.bak", $fileNow, $utf8) }
            [System.IO.File]::WriteAllText($target, $merged, $utf8)

            # 쓴 뒤에도 본다. 사본이 있으니 되돌릴 수 있고, 조용히 망가뜨리는 것보다
            # 무엇이 잘못됐는지 말하는 편이 낫다.
            $after = [System.IO.File]::ReadAllText($target, $utf8)
            if (@([regex]::Matches($after, $reBlock)).Count -ne 1) {
                throw "쓴 뒤에 블록이 하나가 아닙니다. 사본이 $target.bak 에 있습니다."
            }
            Note "CLAUDE.md 의 사내 문안 블록을 $mode. 마커 바깥은 안 건드렸습니다."
        }
    } finally {
        if ($held) {
            $owner = ''
            try { $owner = (Get-Content -LiteralPath (Join-Path $lock 'owner') -Raw -ErrorAction Stop).Trim() } catch { }
            # 빼앗긴 잠금을 남의 것인 줄 모르고 지우지 않는다.
            if ($owner -eq $token) { Remove-Item -LiteralPath $lock -Recurse -Force -ErrorAction SilentlyContinue }
        }
    }
} catch { Fail '6' $_.Exception.Message }
} else { Say '넘겨받은 불일치가 없어 넘어갑니다.' }
Save-State

# ---------------------------------------------------------------- 단계 7
Show '7. 더 안 쓰는 스킬 사본과 훅 연결을 정리합니다.'
if (Want 7) {
try {
    $skillsRoot = Join-Path $cfg 'skills'
    foreach ($s in @($manifest.retiredSkills)) {
        $name = Get-Prop $s 'name'
        $by   = Get-Prop $s 'replacedBy'
        if ([string]::IsNullOrEmpty($name)) { continue }
        # 이름은 허용 목록으로 막는다. 거부 목록이 아니라 허용 목록이라 예상 못 한 것이 안 샌다.
        if ($name -notmatch '^[A-Za-z0-9._-]+$' -or $name -eq '.' -or $name -eq '..') {
            throw "스킬 이름이 폴더 이름 하나가 아닙니다: '$name'"
        }
        $dir = Join-Path $skillsRoot $name
        if (-not (Test-Path -LiteralPath $dir)) { continue }

        # 대체가 확인된 뒤에만 지운다. 먼저 지우고 설치가 실패하면 그 스킬이 없는 PC 가 된다.
        if ($by) {
            $ip = Read-Json (Join-Path $pluginsDir 'installed_plugins.json')
            if ($null -eq (Get-Prop (Get-Prop $ip 'plugins') $by)) {
                Say "$name : 대체할 $by 가 아직 안 깔려 있어 그대로 둡니다."
                continue
            }
        }

        $files   = @(Get-ChildItem -LiteralPath $dir -Recurse -Force -File)
        $subdirs = @(Get-ChildItem -LiteralPath $dir -Recurse -Force -Directory)

        if ($subdirs.Count -eq 0 -and $files.Count -eq 0) {
            if (-not $WhatIfOnly) { Remove-Item -LiteralPath $dir -Recurse -Force }
            Note "$name : 빈 폴더라 지웠습니다. 뜰 사본이 없습니다."
            continue
        }
        # 판정은 셋을 함께 본다. 하위 폴더 없음과 파일 하나와 그 이름이 SKILL.md 인 것이다.
        $onlySkill = ($subdirs.Count -eq 0) -and ($files.Count -eq 1) -and ($files[0].Name -eq 'SKILL.md')
        if (-not $onlySkill) {
            Say "$name : SKILL.md 말고 다른 것이 있어 그대로 둡니다."
            continue
        }
        if ($WhatIfOnly) { Say "[미리보기] $dir 를 사본 뜬 뒤 지웁니다."; continue }
        if (-not (Test-Path -LiteralPath $backupDir)) { New-Item -ItemType Directory -Force -Path $backupDir | Out-Null }
        Copy-Item -LiteralPath $files[0].FullName -Destination (Join-Path $backupDir "$name.SKILL.md.bak") -Force
        Remove-Item -LiteralPath $dir -Recurse -Force
        Note "$name : 사본을 뜨고 지웠습니다."
    }

    # 훅 연결은 파일 이름이 아니라 경로로 구분한다. 이 플러그인이 거는 훅의 파일 이름이
    # 옛것과 같아서, 이름으로 걷으면 맞춤이 매번 자기 연결을 지운다. 옛것은 설치기가
    # %LOCALAPPDATA%\corp-certs\ 아래에 놓은 사본을 가리키고 새것은 플러그인 캐시를
    # 가리키므로 경로가 구분된다.
    $retiredHooks = @($manifest.retiredHooks)
    if ($retiredHooks.Count -gt 0) {
        $settings = Read-Json $settingsPath
        $hooks = Get-Prop $settings 'hooks'
        $removed = 0
        if ($null -ne $hooks) { $removed = Remove-RetiredHookEntries $hooks $retiredHooks }
        if ($removed -gt 0) {
            if ($WhatIfOnly) { Say "[미리보기] 옛 훅 연결 $removed 개를 걷습니다." }
            else { Save-Json $settings $settingsPath; Note "옛 훅 연결 $removed 개를 걷었습니다. 같은 일은 이 플러그인의 훅이 이어서 합니다." }
        }
    }
} catch { Fail '7' $_.Exception.Message }
} else { Say '넘겨받은 불일치가 없어 넘어갑니다.' }
Save-State

# ---------------------------------------------------------------- 마무리
# 실행한 단계마다 실패했거나 상한에 끊겼으면 지문을 적고, 끝까지 성공했으면 지운다. 시간이 모자라
# 중간에 미룬 단계는 원인이 앞 단계에 있을 수 있어 기록을 건드리지 않는다. 끊긴 단계는 끊긴 뒤의
# 호출이 미뤄지므로 미룬 단계에도 들지만, 원인이 그 단계에 있으므로 미룬 것보다 먼저 본다.
# 미뤄진 호출도 호출한 곳이 Fail 을 부르므로 실패는 미룬 것 뒤에 본다.
if (-not $WhatIfOnly) {
    foreach ($n in ($script:Ran | Sort-Object -Unique)) {
        if ($script:TimedOutSteps -contains $n) { $state["stuck-step$n"] = Get-StuckPrint $root $n; continue }
        if ($script:Deferred -contains $n) { continue }
        if ($script:FailedSteps -contains $n) { $state["stuck-step$n"] = Get-StuckPrint $root $n }
        else { $state.Remove("stuck-step$n") }
    }
}
Save-State

# 짧은 출력은 진행 출력을 로그 파일에 두고 결과만 낸다. 로그는 매번 덮어쓴다. 알고 싶은
# 것은 마지막 맞춤이 무엇을 했는가이다.
$logPath = Join-Path $cfg 'kw-control-tower.sync.log'
if ($Brief) {
    try { [System.IO.File]::WriteAllLines($logPath, [string[]]@($script:Log), (New-Object System.Text.UTF8Encoding($false))) } catch { }
}

if (-not $Brief) {
    Write-Host ''
    Write-Host '요약' -ForegroundColor Cyan
    if ($script:Did.Count -eq 0) { Write-Host '  바꾼 것이 없습니다. 이 PC 는 이미 목록과 같습니다.' }
    else { foreach ($d in $script:Did) { Write-Host "  - $d" } }
}

if ($script:Reenab.Count -gt 0 -and -not $Brief) {
    Write-Host ''
    Write-Host '되켠 것' -ForegroundColor Yellow
    Write-Host "  꺼져 있던 필수 플러그인을 다시 켰습니다: $($script:Reenab -join ', ')"
    Write-Host '  회사가 필수로 정한 것이라 되켭니다. 이 줄은 그것을 조용히 안 하려고 적습니다.'
}

# 첫 줄 형식은 disciplined-coder 와 2026-09-25 에 맞췄다. 두 플러그인이 한 세션에서 함께
# 재시작을 안내할 때 사용자가 같은 종류의 안내로 알아보게 하려는 것이다. 옮긴 설치본은
# 옛 커밋과 새 커밋을 일곱 자리로 적는다.
#
# 짧은 출력에서는 요약이 따로 없으므로 옮긴 설치본 밖에 한 일도 여기에 한 줄씩 적는다.
# 재시작이 필요 없는 일만 했으면 첫 줄을 바꾼다.
if ($script:Restart -or ($Brief -and $script:Did.Count -gt 0)) {
    if (-not $Brief) { Write-Host '' }
    if ($script:Restart) { Write-Host 'kw-control-tower: 다시 켜야 새 버전이 적용됩니다.' -ForegroundColor Cyan }
    else { Write-Host 'kw-control-tower: 사내 설정을 맞췄습니다.' -ForegroundColor Cyan }
    $ipAfter = Get-Prop (Read-Json (Join-Path $pluginsDir 'installed_plugins.json')) 'plugins'
    foreach ($mv in $script:Moved) {
        $new = $null
        foreach ($scope in @(Get-Prop $ipAfter $mv.Id)) { $s = Get-Prop $scope 'gitCommitSha'; if ($s) { $new = $s } }
        $newShort = if ($new) { $new.Substring(0, 7) } else { '(읽지 못함)' }
        Write-Host "  - $($mv.Id) : $($mv.Old.Substring(0, 7)) → $newShort"
    }
    if ($Brief) { foreach ($d in $script:Did) { Write-Host "  - $d" } }
    else { Write-Host '  클로드 코드는 켤 때 플러그인을 읽으므로 방금 바뀐 것은 이 세션에 적용되지 않습니다.' }
}

# 갱신에 실패한 것은 재시작을 안내하지 않고 버전 알림으로 낸다. 형식은 disciplined-coder 와
# 맞췄다. 커밋은 옛 일곱 자리 → 새 일곱 자리로 적고 직접 실행할 명령을 붙인다.
if ($script:Deferred.Count -gt 0) {
    Write-Host "kw-control-tower: 시간 상한에 닿아 단계 $(($script:Deferred | Sort-Object -Unique) -join ', ') 는 다음 세션으로 미뤘습니다." -ForegroundColor Yellow
}
if ($script:UpdateFailed.Count -gt 0) {
    Write-Host ''
    Write-Host 'kw-control-tower: 플러그인 버전 알림' -ForegroundColor Yellow
    Write-Host '  갱신에 실패했습니다.'
    foreach ($u in $script:UpdateFailed) { Write-Host "  - $($u.Id) : $($u.Old.Substring(0, 7)) → $($u.Target.Substring(0, 7))" }
    Write-Host '  지금 옮기려면 아래를 실행해 주십시오.'
    foreach ($mk in @($script:UpdateFailed | ForEach-Object { $_.Mk } | Select-Object -Unique)) { Write-Host "      claude plugin marketplace update $mk" }
    foreach ($u in $script:UpdateFailed) { Write-Host "      claude plugin update $($u.Id)" }
}

if ($script:Failed.Count -gt 0) {
    if ($Brief) {
        # 버전 알림이 이미 말한 실패는 다시 적지 않는다. 종료 코드는 그대로 1 이다.
        $rest = @($script:Failed | Where-Object { $script:Covered -notcontains $_ })
        if ($rest.Count -gt 0) {
            Write-Host ''
            Write-Host "kw-control-tower: 맞추지 못한 것이 있습니다. 기록: $logPath" -ForegroundColor Yellow
            foreach ($f in $rest) { Write-Host "  - $f" }
        }
        exit 1
    }
    Write-Host ''
    Write-Host '못 한 것' -ForegroundColor Yellow
    foreach ($f in $script:Failed) { Write-Host "  - $f" }
    Write-Host '  못 한 단계만 다음 세션에 다시 알립니다. 나머지는 조용합니다.'
    exit 1
}
exit 0
} finally {
    if (-not $WhatIfOnly) { Remove-Item -LiteralPath $syncLock -Recurse -Force -ErrorAction SilentlyContinue }
}
