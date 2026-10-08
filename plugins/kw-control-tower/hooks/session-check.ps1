# 세션 시작 훅. 이 PC 가 manifest.json 과 불일치한 곳을 감지하고, 고칠 수 있는 것이
# 있으면 맞춤(sync.ps1)을 호출한다. 사용자가 직접 해야 하는 것은 알리기만 한다.
#
# 감지는 다섯 가지 계약을 지킨다.
# - 세션 시작에 도는 훅은 이것 하나다.
# - 외부 프로세스를 새로 호출하려면 개발할 때 사용자에게 먼저 묻는다. 승인된 것은
#   원격 커밋을 읽는 curl.exe 하나다(2026-09-25 사용자 승인).
# - 네트워크에는 우리 배포처의 원격 커밋을 읽는 요청만 내보낸다.
# - 읽는 파일을 새로 늘리려면 개발할 때 사용자에게 먼저 묻는다.
# - 몸통이 200밀리초를 넘으면 그 값을 kw-control-tower.slow 에 남긴다. 네트워크 시간은
#   몸통에 포함하지 않는다.
#
# 감지는 설정 파일을 고치지 않고 세션을 막지 않는다. 스스로 실패하면 사용자에게 아무것도
# 표시하지 않고 종료한다.
#
# PowerShell 7 을 전제한다(2026-09-19 사용자 결정). 설치기가 7 을 winget 으로 설치하고,
# 그래도 없으면 아무것도 설치하지 않고 끝나므로 7 이 없는 PC 에는 이 훅도 없다. 5.1 을
# 버린 근거는 설계 문서 「무엇으로 쓰나」에 있다.

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'

# BOM 을 붙이지 않는다. 7 은 BOM 없이도 UTF-8 로 읽고, 5.1 로 잘못 호출하면 한글이 조용히
# 깨지는 대신 파싱 오류로 그 줄에서 드러난다. 출력 인코딩은 명시한다. 콘솔 코드페이지는
# 7 에서도 윈도 기본을 따르는 때가 있다.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$script:Budget = @{ Files = 0; Registry = 0 }

function Get-CheapHash {
    # MD5 를 직접 호출한다. Get-FileHash 보다 아홉 배 빠르다(8ms 대 72ms).
    # 파일이 바뀌었는지만 구분하므로 암호 강도는 필요 없다.
    # .NET 의 문자열 해시는 프로세스마다 시드가 달라 쓸 수 없다.
    param([string]$Path)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        return [System.BitConverter]::ToString($md5.ComputeHash($bytes)).Replace('-', '')
    } finally { $md5.Dispose() }
}

function Get-StuckPrint {
    # 실패한 원인이 같은지를 목록 파일 둘의 내용과 날짜와 단계 번호로 구분한다. 목록이 바뀌거나
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
    # 못 읽으면 던져서 catch 가 자국을 남기게 한다. 삼키면 설정이 망가진 PC 와 정상 PC 가
    # 구별되지 않는다.
    param([string]$Path)
    $script:Budget.Files++
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json) }
    catch { throw "JSON 으로 안 읽힙니다: $Path" }
}

function Get-Prop {
    # PSCustomObject 에서 이름으로 값을 꺼낸다. 없는 이름이면 $null 이다.
    #
    # null 조건 연산자(?.)로 줄이지 않는다. PowerShell 의 ?. 은 C# 과 달리 바로 뒤의 멤버
    # 접근 하나만 막아서, $Object?.PSObject.Properties[$Name] 은 $Object 가 $null 일 때
    # "null 배열로 인덱싱할 수 없습니다" 로 던진다.
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $null }
    return $p.Value
}

function Test-Marketplace {
    # 배포처가 두 파일 가운데 어디에 등록되어 있는지 확인한다.
    param($Settings, $Known, [string]$Name)
    $a = Get-Prop (Get-Prop $Settings 'extraKnownMarketplaces') $Name
    $b = Get-Prop (Get-Prop $Known   'marketplaces')            $Name
    if ($null -eq $b) { $b = Get-Prop $Known $Name }
    return @{ InSettings = ($null -ne $a); InKnown = ($null -ne $b); Settings = $a; Known = $b }
}

# 사내 문안 블록을 조립한다. 맞춤(sync.ps1)에도 같은 함수가 있다. 둘이 다르게
# 조립하면 맞춤이 쓴 블록을 훅이 다르다고 알린다. 원칙과 금지어 목록은 필수 플러그인인
# disciplined-coder 가 싣는다(2026-10-05 사용자 결정).
function Get-AxBlock {
    return "# BEGIN AX 설치 (자동 생성 블록이므로 직접 고치지 마십시오)`n@kw-ax/claude-md-ko.md`n# END AX 설치"
}

# kw-ax 로 복사하고 대조할 템플릿이다. 맞춤(sync.ps1)에도 같은 함수가 있다.
function Get-AxCopies { return @('claude-md-ko.md') }

function Read-KwState([string]$Path) {
    # 상태 파일을 한 번만 읽어 여러 질문이 나눠 쓴다.
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

function Read-GitIdentity([string]$Path) {
    # ~/.gitconfig 에서 커밋 명의와, 그 메일을 사용자가 승인한 기록을 읽는다. git 을 실행하지
    # 않고 파일을 직접 읽는다. 감지가 외부 프로세스를 늘리지 않는다는 계약 때문이다.
    # git 처럼 섹션과 키의 대소문자를 구분하지 않고, 따옴표와 줄 끝 주석을 값에서 뺀다.
    # include 로 다른 파일에 둔 값은 못 읽는다. 그런 PC 는 명의 스크립트가 승인한 값을 이
    # 파일에 다시 적으므로 한 번 확인하면 안내가 멈춘다.
    $id = @{ Name = $null; Email = $null; Approved = $null }
    $script:Budget.Files++
    if (-not (Test-Path -LiteralPath $Path)) { return $id }
    $section = ''
    foreach ($line in (Get-Content -LiteralPath $Path -Encoding UTF8)) {
        $t = $line.Trim()
        if ($t -match '^\[\s*([^\]\s"]+)') { $section = $Matches[1].ToLowerInvariant(); continue }
        if ($t -notmatch '^([A-Za-z][\w-]*)\s*=\s*(.*)$') { continue }
        $key = "$section.$($Matches[1].ToLowerInvariant())"
        $val = ($Matches[2] -replace '\s+[#;].*$', '').Trim().Trim('"')
        switch ($key) {
            'user.name'                      { $id.Name = $val }
            'user.email'                     { $id.Email = $val }
            'kw-control-tower.approvedemail' { $id.Approved = $val }
        }
    }
    return $id
}

function Get-MarketplaceHead {
    # 배포처 사본이 받아 둔 커밋을 디스크에서 읽는다.
    # git 사본은 HEAD 가 가리키는 ref 파일에 커밋이 있고, git 이 아닌 배포처는
    # .gcs-sha 파일 하나에 적어 둔다. 두 형식이 모두 실재하므로 둘 다 읽는다.
    param([string]$Dir)
    $g = Join-Path $Dir '.git'
    $h = Join-Path $g 'HEAD'
    $script:Budget.Files++
    if (Test-Path -LiteralPath $h) {
        $line = (Get-Content -LiteralPath $h -Raw -Encoding UTF8).Trim()
        if ($line.StartsWith('ref: ')) {
            $refFile = Join-Path $g ($line.Substring(5))
            $script:Budget.Files++
            if (Test-Path -LiteralPath $refFile) {
                return (Get-Content -LiteralPath $refFile -Raw -Encoding UTF8).Trim()
            }
            return $null
        }
        return $line
    }
    $gcs = Join-Path $Dir '.gcs-sha'
    $script:Budget.Files++
    if (Test-Path -LiteralPath $gcs) { return (Get-Content -LiteralPath $gcs -Raw -Encoding UTF8).Trim() }
    return $null
}

function Get-RemoteUrl {
    # 배포처 등록의 source 에서 원격 주소를 만든다. 원격을 읽을 수 없는 형식이면 $null 이다.
    # github 이면 저장소 이름으로 만들고, https 주소면 그대로 쓴다. 브랜치나 태그를 지정한
    # 배포처도 $null 이다. 원격 기본 브랜치와 비교하면 매 세션 다르다고 나와 맞춤이 되풀이된다.
    param($Source)
    if ($null -eq $Source -or (Get-Prop $Source 'ref')) { return $null }
    $repo = Get-Prop $Source 'repo'
    if ((Get-Prop $Source 'source') -eq 'github' -and $repo) { return "https://github.com/$repo.git" }
    $url = Get-Prop $Source 'url'
    if ($url -and $url.StartsWith('https://')) { return $url }
    return $null
}

function Get-RemoteHead {
    # 원격 저장소의 기본 브랜치 커밋을 읽는다. 못 읽으면 $null 이다.
    #
    # REST API 대신 git 이 쓰는 info/refs 를 curl.exe 로 읽는다. 감지가 외부 프로세스를
    # 호출하지 않는다는 계약의 유일한 예외다. 근거와 측정값은 설계 문서의 「원격은 git의
    # `info/refs`로 읽는다」와 그다음 문단에 있다.
    # 'curl' 로 적으면 Invoke-WebRequest 의 별칭이 되므로 반드시 curl.exe 로 적는다.
    # curl.exe 는 시스템 프록시를 읽지 않으므로 명시적 프록시만 있는 망에서는 실패하고,
    # 그때는 사본과 비교한다.
    #
    # 응답의 첫 ref 줄은 '<길이 4자><sha> HEAD\0<기능 목록>' 이다. ' HEAD' 바로 앞의
    # 40자를 잡으므로 길이 접두사가 sha 에 섞이지 않는다. 비공개 저장소의 401 은 -f 가
    # 실패로 돌려주고 그때도 $null 이다.
    param([string]$Url)
    try {
        $text = (& curl.exe -s -f -m 2 "$Url/info/refs?service=git-upload-pack" 2>$null) -join "`n"
        if ($LASTEXITCODE -ne 0) { return $null }
        $m = [regex]::Match($text, '([0-9a-f]{40}) HEAD')
        if ($m.Success) { return $m.Groups[1].Value }
    } catch { }
    return $null
}

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$notes = New-Object System.Collections.ArrayList   # 맞춤이 고칠 수 있는 것
$noteSteps = New-Object System.Collections.ArrayList   # $notes 와 같은 순서로 맞춤 단계 번호
function Add-Note([int[]]$Step, [string]$Text) {
    [void]$notes.Add($Text)
    [void]$noteSteps.Add($Step)
}
$asks  = New-Object System.Collections.ArrayList   # 사용자가 직접 해야 하는 것
$heldSay = New-Object System.Collections.ArrayList   # 오늘 갱신을 보류한 것
$askHints = New-Object System.Collections.ArrayList   # $asks 와 같은 순서로 클로드에게만 주는 지시
function Add-Ask([string]$Text, [string]$Hint) {
    [void]$asks.Add($Text)
    [void]$askHints.Add($Hint)
}
# 화면에 내지 않고 클로드에게만 주는 규칙. 매 세션 실려도 대화를 끊지 않게, 클로드가 먼저
# 꺼내지 않고 해당하는 작업을 할 때만 지키도록 Send-Hook 이 머리말을 붙인다.
$quietRules = New-Object System.Collections.ArrayList
function Add-QuietRule([string]$Rule) { [void]$quietRules.Add($Rule) }
$remoteOf = @{}          # 배포처 이름 → 원격 커밋. 맞춤에 넘긴다
$script:NetMs = 0        # 몸통에 포함하지 않는 네트워크 시간

try {
    $userHome = $env:USERPROFILE
    if ([string]::IsNullOrEmpty($userHome)) { exit 0 }   # 윈도가 아니면 종료한다
    $root = $env:CLAUDE_PLUGIN_ROOT
    if ([string]::IsNullOrEmpty($root)) { exit 0 }

    $cfg     = Join-Path $userHome '.claude'
    $plugins = Join-Path $cfg 'plugins'

    $manifest = Read-Json (Join-Path $root 'manifest.json')
    if ($null -eq $manifest) { exit 0 }   # 목록을 못 읽으면 아무 말도 안 한다

    # 읽히는 것과 형식이 맞는 것은 다르다. 칸이 빠진 목록으로 판정하면 그 질문만
    # 조용히 사라져, 불일치한 PC 를 정상으로 본다. 맞춤은 이때 멈추고 알리지만, 이 훅은
    # 세션을 어지럽히지 않도록 자국만 남기고 종료한다.
    foreach ($k in @('marketplaces', 'required', 'suggested', 'retiredPlugins',
                     'retiredMarketplaces', 'retiredSkills', 'retiredHooks')) {
        if ($null -eq $manifest.PSObject.Properties[$k]) { throw "목록 파일에 '$k' 칸이 없습니다." }
    }

    $settings  = Read-Json (Join-Path $cfg     'settings.json')
    $installed = Read-Json (Join-Path $plugins 'installed_plugins.json')
    $known     = Read-Json (Join-Path $plugins 'known_marketplaces.json')
    $kwState = Read-KwState (Join-Path $cfg 'kw-control-tower.state')

    $enabled     = Get-Prop $settings  'enabledPlugins'
    $installedOf = Get-Prop $installed 'plugins'

    # --- 질문 1과 2. 필수 플러그인이 설치되어 있나, 켜져 있나 ---------------
    # 두 질문은 답이 있는 파일도, 고치는 명령도 다르다. install 은 사용자가 꺼 둔 것을
    # true 로 덮으므로 설치된 것에는 쓰지 않는다.
    $missing  = New-Object System.Collections.ArrayList
    $disabled = New-Object System.Collections.ArrayList

    foreach ($id in @($manifest.required)) {
        $entry = Get-Prop $installedOf $id
        $onDisk = $false
        if ($null -ne $entry) {
            foreach ($scope in @($entry)) {
                $p = Get-Prop $scope 'installPath'
                if ($p -and (Test-Path -LiteralPath $p)) { $onDisk = $true }
            }
        }
        if (-not $onDisk) { [void]$missing.Add($id); continue }

        $state = Get-Prop $enabled $id
        if ($state -ne $true) { [void]$disabled.Add($id) }
    }

    if ($missing.Count -gt 0) {
        Add-Note 2 "필수 플러그인이 설치되어 있지 않습니다: $($missing -join ', ')"
    }
    if ($disabled.Count -gt 0) {
        Add-Note 2 "필수 플러그인이 꺼져 있습니다: $($disabled -join ', ')"
    }

    # --- 질문 3. 정리하기로 한 플러그인이 남았나 ---------------------------
    $staleP = New-Object System.Collections.ArrayList
    foreach ($p in @($manifest.retiredPlugins)) {
        $id = Get-Prop $p 'id'
        if (-not $id) { continue }
        if ((Get-Prop $installedOf $id) -or ($null -ne (Get-Prop $enabled $id))) { [void]$staleP.Add($id) }
    }
    if ($staleP.Count -gt 0) {
        Add-Note 3 "더 이상 쓰지 않는 플러그인이 남아 있습니다: $($staleP -join ', ')"
    }

    # --- 질문 4. 정리하기로 한 배포처가 남았나 -----------------------------
    $staleM = New-Object System.Collections.ArrayList
    foreach ($mk in @($manifest.retiredMarketplaces)) {
        $name = Get-Prop $mk 'name'
        if (-not $name) { continue }
        $m = Test-Marketplace $settings $known $name
        if ($m.InSettings -or $m.InKnown) { [void]$staleM.Add($name) }
    }
    if ($staleM.Count -gt 0) {
        Add-Note 3 "더 이상 쓰지 않는 배포처가 남아 있습니다: $($staleM -join ', ')"
    }

    # --- 질문 5. 우리 배포처의 자동 갱신이 두 곳 다 켜져 있나 ---------------
    # 두 파일은 서로 값을 주고받지 않는다. 그래서 두 곳 다 본다.
    $offAuto = New-Object System.Collections.ArrayList
    foreach ($mk in @($manifest.marketplaces)) {
        if ((Get-Prop $mk 'ours') -ne $true) { continue }   # 남의 배포처는 측정하지 않는다
        $name = Get-Prop $mk 'name'
        $m = Test-Marketplace $settings $known $name
        if (-not ($m.InSettings -or $m.InKnown)) { [void]$offAuto.Add("$name (등록 없음)"); continue }
        $a = Get-Prop $m.Settings 'autoUpdate'
        $b = Get-Prop $m.Known    'autoUpdate'
        if (($a -ne $true) -or ($b -ne $true)) { [void]$offAuto.Add($name) }
    }
    if ($offAuto.Count -gt 0) {
        Add-Note 1 "자동 갱신이 꺼져 있습니다: $($offAuto -join ', ')"
    }

    # --- 질문 6. 파이썬 라이브러리 목록이 바뀌었나 -------------------------
    # 예산 안에서 이 PC 를 직접 읽을 수 없는 것은 이것 하나뿐이라 해시로 측정한다.
    # 해시하는 대상은 파일이다. JSON 의 하위 트리를 해시하면 프로세스마다 값이 달라진다.
    $reqFile   = Join-Path $root 'requirements.txt'
    $script:Budget.Files++
    if (Test-Path -LiteralPath $reqFile) {
        $now = Get-CheapHash $reqFile
        $was = $kwState['requirements']
        if ($now -ne $was) {
            Add-Note 4 '파이썬 라이브러리 목록이 이 PC에 맞춰진 것과 다릅니다.'
        }
    }

    # --- 질문 7. PYTHONUTF8 이 설정되었나 ------------------------------------
    # 사용자가 일부러 0 으로 둔 것은 그대로 두는 것이 맞으므로 그때는 말하지 않는다.
    $script:Budget.Registry++
    $utf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'User')
    if ($null -eq $utf8) {
        Add-Note 5 'PYTHONUTF8 이 설정되어 있지 않습니다. 한글이 깨질 수 있습니다.'
    }

    # --- 질문 8. CLAUDE.md 의 사내 문안이 템플릿과 같나 ---------------------
    # 버전이나 해시가 아니라 글자를 비교한다. 줄바꿈 차이는 다름이 아니므로 맞춘 뒤에
    # 비교한다.
    $tpl = Join-Path $root 'templates\claude-md-ko.md'
    $mem = Join-Path $cfg 'CLAUDE.md'
    $script:Budget.Files += 2
    $u8 = New-Object System.Text.UTF8Encoding($false)
    # 블록은 kw-ax 의 사본을 @import 로 싣는다. 사본이 없으면 @import 가 알리지 않고
    # 아무것도 싣지 않으며, 낡으면 옛 문안이 실린다. CLAUDE.md 만 보아서는 둘 다 안 드러난다.
    # 맞춤이 Get-AxCopies 목록을 복사하므로 여기서도 같은 목록을 대조한다.
    $memText = if (Test-Path -LiteralPath $mem) { [System.IO.File]::ReadAllText($mem, $u8) } else { '' }
    if (Test-Path -LiteralPath $tpl) {
        $stale = New-Object System.Collections.ArrayList
        $tplDir = Split-Path -Parent $tpl
        foreach ($name in @(Get-AxCopies)) {
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
    if ((Test-Path -LiteralPath $tpl) -and (Test-Path -LiteralPath $mem)) {
        $now   = $memText
        $block = Get-AxBlock
        $re    = '(?ms)^#\s*BEGIN AX\b.*?^#\s*END AX[^\r\n]*'
        $found = [regex]::Match($now, $re)
        $norm  = { param($t) ($t -replace "`r`n", "`n").Trim() }
        $howMany = @([regex]::Matches($now, $re)).Count
        if (-not $found.Success) {
            Add-Note 6 'CLAUDE.md 에 사내 문안 블록이 없습니다.'
        } elseif ($howMany -gt 1) {
            # 개수를 따로 세는 것은 위 정규식이 첫 블록만 잡기 때문이다. 개수를 안
            # 보면 같은 블록이 둘인 파일이 "이미 같다" 로 읽혀 조용히 남는다.
            Add-Note 6 "CLAUDE.md 에 사내 문안 블록이 $howMany 개 있습니다."
        } elseif ((& $norm $found.Value) -ne (& $norm $block)) {
            Add-Note 6 'CLAUDE.md 의 사내 문안 블록이 배포된 것과 다릅니다.'
        }
    }

    # --- 질문 9와 10. 정리하기로 한 스킬과 훅이 남았나 ---------------------
    $staleS = New-Object System.Collections.ArrayList
    foreach ($s in @($manifest.retiredSkills)) {
        $name = Get-Prop $s 'name'
        if (-not $name) { continue }
        if (Test-Path -LiteralPath (Join-Path (Join-Path $cfg 'skills') $name)) { [void]$staleS.Add($name) }
    }
    if ($staleS.Count -gt 0) {
        Add-Note 7 "더 이상 쓰지 않는 스킬 사본이 남아 있습니다: $($staleS -join ', ')"
    }

    # 훅 연결은 파일 이름이 아니라 경로로 구분한다. 이 플러그인이 거는 훅의 파일 이름이
    # 옛것과 같아서, 이름만 보면 자기 연결을 은퇴한 연결로 오인한다.
    $staleH = New-Object System.Collections.ArrayList
    $hookBlob = ''
    try { $hookBlob = (Get-Prop $settings 'hooks' | ConvertTo-Json -Depth 20 -Compress) } catch { $hookBlob = '' }
    foreach ($h in @($manifest.retiredHooks)) {
        $file = Get-Prop $h 'file'
        $pathBit = Get-Prop $h 'pathContains'
        if ($file -and $pathBit -and $hookBlob -and $hookBlob.Contains($file) -and $hookBlob.Contains($pathBit)) {
            [void]$staleH.Add($file)
        }
    }
    if ($staleH.Count -gt 0) {
        Add-Note 7 "더 이상 쓰지 않는 훅 연결이 남아 있습니다: $($staleH -join ', ')"
    }

    # --- 질문 11. 우리 배포처에서 온 설치본이 원격보다 뒤처졌나 --------------
    # 자동 갱신이 켜져 있어도 설치본이 뒤처질 수 있어 직접 확인한다. 남의 배포처는 보지
    # 않는다. 남의 것을 언제 올릴지는 사용자가 정한다.
    #
    # 원격 커밋과 비교한다. 사본은 자동 갱신이 받아 와야 움직이는데, 자동 갱신은 세션 시작
    # 뒤에 늦게 도착하거나 오지 않는다. 원격을 읽지 못하거나 배포처가 브랜치나 태그를
    # 지정했으면 사본과 비교한다. 지정한 ref 를 원격 기본 브랜치와 비교하면 매 세션 다르다고
    # 나와 맞춤이 되풀이된다.
    #
    # 지난 세션에 같은 원격 커밋으로 옮기지 못했어도 세션마다 맞춤을 다시 호출한다(2026-10-12
    # 사용자 결정). 일시적인 실패로 갱신이 멈추지 않게 하기 위해서다. 다만 그날 세 번 실패했거나
    # 시간 상한에 막혔으면 맞춤이 updateFails 에 날짜와 횟수를 적고, 감지는 그날 갱신을 넘긴다.
    # 날짜가 바뀌면 다시 시도한다.
    $fDay, $fN = "$($kwState['updateFails'])" -split ';'
    $heldToday = ($fDay -eq (Get-Date -Format 'yyyy-MM-dd')) -and ([int]$fN -ge 3)
    $behind = New-Object System.Collections.ArrayList
    $cloneLate = $false
    foreach ($mk in @($manifest.marketplaces)) {
        if ((Get-Prop $mk 'ours') -ne $true) { continue }
        $mkName = Get-Prop $mk 'name'
        if (-not $mkName -or $null -eq $installedOf) { continue }
        $head = Get-MarketplaceHead (Join-Path (Join-Path $plugins 'marketplaces') $mkName)
        $m = Test-Marketplace $settings $known $mkName
        $src = Get-Prop $m.Known 'source'
        if ($null -eq $src) { $src = Get-Prop $m.Settings 'source' }
        $url = Get-RemoteUrl $src
        $remote = $null
        if ($url) {
            $sw.Stop()
            $net = [System.Diagnostics.Stopwatch]::StartNew()
            $remote = Get-RemoteHead $url
            $script:NetMs += $net.ElapsedMilliseconds
            $sw.Start()
        }
        $target = if ($remote) { $remote } else { $head }
        if (-not $target) { continue }
        if ($remote) { $remoteOf[$mkName] = $remote }
        # 사본이 원격보다 뒤일 때만 받아오기(단계 1)가 필요하다.
        if ($remote -and $head -and -not $remote.StartsWith($head) -and -not $head.StartsWith($remote)) { $cloneLate = $true }

        $late = New-Object System.Collections.ArrayList
        foreach ($pluginId in @($installedOf.PSObject.Properties.Name)) {
            if (-not $pluginId.EndsWith("@$mkName")) { continue }
            foreach ($scope in @(Get-Prop $installedOf $pluginId)) {
                $sha = Get-Prop $scope 'gitCommitSha'
                if (-not $sha) { continue }
                if (-not $target.StartsWith($sha) -and -not $sha.StartsWith($target)) {
                    [void]$late.Add(@{ Id = $pluginId; Sha = $sha })
                    break
                }
            }
        }
        if ($heldToday) {
            $to = $target.Substring(0, 7)
            foreach ($l in $late) { [void]$heldSay.Add("  - $($l.Id) : $($l.Sha.Substring(0, 7)) → $to") }
            [void]$heldSay.Add('  지금 옮기려면 아래를 실행해 주십시오.')
            [void]$heldSay.Add("      claude plugin marketplace update $mkName")
            foreach ($l in $late) { [void]$heldSay.Add("      claude plugin update $($l.Id)") }
        } else {
            foreach ($l in $late) { [void]$behind.Add($l.Id) }
        }
    }
    if ($behind.Count -gt 0) {
        Add-Note $(if ($cloneLate) { @(1, 2) } else { @(2) }) "설치본이 원격보다 뒤처져 있습니다: $(($behind | Select-Object -Unique) -join ', ')"
    }

    # --- 질문 12. 배포처 사본을 오래 받아오지 않았나 ------------------------
    # 원격을 읽지 못하는 PC 에서는 사본이 낡았는지 알 수 없으므로 마지막으로 받아온 시각을
    # 본다. 맞춤이 받아올 때마다 그 시각을 적으므로, 저장소에 새 커밋이 없어 사본이 움직이지
    # 않을 때에도 이 질문이 되풀이되지 않는다.
    $refreshed = $kwState['refreshed']
    $stale = $true
    if ($refreshed) {
        try { $stale = ([datetime]::Parse($refreshed) -lt (Get-Date).AddDays(-14)) } catch { $stale = $true }
    }
    if ($stale) {
        Add-Note 1 '배포처 사본을 14일 넘게 받아오지 않았습니다.'
    }

    # --- 질문 13. 사내 GitHub 로그인이 되어 있나 ---------------------------
    # 이것은 $asks 로 간다. 브라우저 승인이 필요해 맞춤이 대신할 수 없다. $notes 에 넣으면
    # 로그인하지 않은 PC 에서 매 세션 맞춤이 돌고도 아무것도 고치지 못한다.
    #
    # "고칠 수 있는 것만 확인한다" 는 규칙의 예외다. 사용자가 고칠 수 있고 고치면 멈추므로
    # 끌 수 없는 소음이 되지 않는다.
    #
    # 파일로 알 수 있는 것은 "로그인한 적 있다" 까지다. 토큰이 만료되거나 취소되어도 파일은
    # 남는다. 그것까지 확인하려면 gh 를 실행하고 네트워크에 나가야 한다.
    $script:Budget.Files++
    $ghHosts = Join-Path (Join-Path $env:APPDATA 'GitHub CLI') 'hosts.yml'
    $loggedIn = $false
    if (Test-Path -LiteralPath $ghHosts) {
        foreach ($line in (Get-Content -LiteralPath $ghHosts -Encoding UTF8)) {
            if ($line -match '^\s*github\.com\s*:') { $loggedIn = $true; break }
        }
    }
    # 클로드가 대신 실행하면 gh 가 브라우저를 열지 않으므로 코드 입력 페이지를 start 로 먼저
    # 연다. 두 명령을 ; 로 이었으므로 cmd 에서는 동작하지 않는다. 근거는 설계 문서의 「로그인
    # 명령은 코드 입력 페이지를 먼저 연다」에 있다. user:email 은 git 명의를 GitHub 계정의
    # 메일로 맞추는 데 쓰며 기본 로그인에는 없다.
    # 명의 스크립트(git-identity.ps1)에도 같은 명령이 있다. 글자 그대로 같아야 한다.
    $loginCommand = 'start https://github.com/login/device; gh auth login --web --git-protocol https --skip-ssh-key --clipboard --scopes user:email'

    # --- 질문 14. git 커밋 명의를 사용자가 확인했나 ------------------------
    # 명의가 비어 있으면 클로드가 대화 맥락에 있는 클로드 계정 메일로 채워, 직원의 커밋이 남의
    # 이름으로 올라간다(이슈 #28). 비어 있는지만 보면 이미 남의 메일이 든 PC 를 정상으로
    # 보므로, 지금 메일이 사용자가 승인한 메일과 같은지를 본다. 승인은 명의 스크립트가 같은
    # 파일에 적는다.
    #
    # 이것도 $asks 로 간다. 무엇이 본인 메일인지는 사용자가 승인해야 하므로 맞춤이 대신할 수
    # 없다. 로그인 전에는 GitHub 에서 메일을 읽을 수 없으므로 로그인 안내 하나만 내고,
    # 클로드가 로그인 뒤에 이어 간다. ~/.gitconfig 를 읽는 것은 2026-10-02 사용자 승인이다.
    $gitId = Read-GitIdentity (Join-Path $userHome '.gitconfig')
    $idOk = $gitId.Name -and $gitId.Email -and ($gitId.Approved -eq $gitId.Email)
    # 로그인과 메일 읽기 권한 추가는 사람이 브라우저에서 승인할 때까지 끝나지 않아, 도구의 기본
    # 시간 제한 2분으로는 끊긴다. 이미 로그인한 직원은 모두 처음 한 번 권한을 더하므로 명의 안내에도
    # 같은 지시를 붙인다(PR #42 리뷰).
    $browserHint = "먼저 '열리는 브라우저 페이지에 Ctrl+V 로 코드를 붙여 넣고 승인하십시오'라고 본문에 알리고, 시간 제한을 10분으로 두고 실행하라."
    # 훅은 모두 -ExecutionPolicy Bypass 로 돈다. 명의 스크립트는 클로드의 셸에서 따로 실행되어
    # 그것을 물려받지 않으므로 같은 옵션을 적는다(PR #42 리뷰).
    $idScript = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\git-identity.ps1'
    $idHint = "git 명의는 pwsh -NoProfile -ExecutionPolicy Bypass -File `"$idScript`" 로 제안을 받아 지금 값과 제안 값을 본문에 보이고, " +
              '사용자가 승인한 뒤에만 같은 스크립트를 -Apply -Name -Email 로 실행하라. 대화 맥락에 있는 이름이나 메일로 채우지 않는다. ' +
              "스크립트가 메일 읽기 권한을 더하는 명령을 알리면 그 명령을 실행할 때도 $browserHint"
    # 월요일이 아닌 날 명의가 비어 있으면 화면 안내 대신 클로드에게만 주는 보호 규칙. Send-Hook 이
    # "사용자에게 먼저 꺼내지 말고 해당하는 작업을 할 때만 지켜라" 는 머리말을 붙이므로 규칙 내용만 적는다.
    $idQuietRule = "git 명의가 비어 있다. 커밋하려는데 명의가 필요하면 대화 맥락에 있는 이름이나 메일로 채우지 말고, " +
                   "pwsh -NoProfile -ExecutionPolicy Bypass -File `"$idScript`" 로 제안을 받아 사용자가 승인한 뒤에 적용하라."

    if (-not $loggedIn) {
        # 한 줄로 낸다. 매 세션 표시되는 안내라 길면 아래의 다른 알림을 밀어낸다(2026-09-29 사용자 결정).
        $hint = "로그인 명령을 대신 실행할 때는 $browserHint"
        if (-not $idOk) { $hint += " 로그인이 끝나면 git 명의 확인으로 이어 간다. $idHint" }
        Add-Ask "사내 GitHub 로그인이 필요합니다. 다음을 실행하고 열리는 페이지에 Ctrl+V 로 코드를 붙여 넣으십시오: $loginCommand" $hint
    } elseif (-not $idOk -and (Get-Date).DayOfWeek -eq [DayOfWeek]::Monday) {
        # 월요일에만 안내한다. 근거와 부작용은 설계 문서 「명의 안내는 월요일에만 낸다」에 있다.
        $text = if ($gitId.Email) { "git 커밋 명의를 아직 확인하지 않았습니다(user.email: $($gitId.Email))." }
                else { 'git 커밋 명의(user.name · user.email)가 비어 있습니다.' }
        Add-Ask "$text 클로드에게 「git 명의 맞춰 줘」라고 하십시오." $idHint
    } elseif (-not $gitId.Name -or -not $gitId.Email) {
        # 명의가 들어 있으면 커밋이 그대로 성공해 클로드가 명의를 채울 일이 없으므로 비었을 때만 준다.
        Add-QuietRule $idQuietRule
    }

    # --- 질문 15. 전역 설정에 outputStyle 키가 있나 --------------------------
    # 키가 없을 때만 불일치로 본다. 값이 무엇이든 키가 있으면 사용자가 정한 것이라 말하지 않는다.
    # "default" 로 바꾼 사람에게 매 세션 Concise 를 다시 넣지 않기 위해서다(2026-10-12 사용자 결정).
    # settings.json 이 없으면 고칠 대상이 없으므로 말하지 않는다. 이미 읽은 파일이라 예산이 늘지 않는다.
    if ($null -ne $settings -and $null -eq $settings.PSObject.Properties['outputStyle']) {
        Add-Note 8 '전역 설정에 outputStyle 이 없습니다.'
    }

    # --- 질문 16. 배포처 교체에 실패해 남은 폴더가 있나 ---------------------
    # 클로드 코드가 배포처를 교체하다 실패하면 <이름>.bak 이나 <이름>..clone 폴더가 남고, 남은 .bak 은
    # 다음 교체를 멈춘다. 배포처를 구분하지 않고 본다(2026-10-12 사용자 결정). 10분 안에 바뀐 폴더는
    # 다른 창이 교체 중일 수 있어 세지 않는다. 맞춤 단계 1 이 같은 기준으로 지운다.
    $script:Budget.Files++
    $mkRoot = Join-Path $plugins 'marketplaces'
    $mkNames = @(if ($null -ne $known) { $known.PSObject.Properties.Name })
    $leftover = @(Get-ChildItem -LiteralPath $mkRoot -Directory -Force -ErrorAction SilentlyContinue | Where-Object {
        ($_.Name -match '(\.bak|\.\.clone)$') -and ($mkNames -notcontains $_.Name) -and
        (((Get-Date) - $_.LastWriteTime).TotalMinutes -ge 10)
    })
    if ($leftover.Count -gt 0) {
        Add-Note 1 "배포처 교체에 실패해 남은 폴더가 있습니다: $(($leftover | ForEach-Object Name) -join ', ')"
    }
}
catch {
    # 사용자에게는 아무것도 표시하지 않고 종료한다. 세션 시작을 훅의 사정으로 어지럽히지 않는다.
    # 다만 자국은 남긴다. 조용한 실패는 버그를 숨긴다.
    # 덧붙여 적는다. 같은 오류가 반복되는지가 원인을 구분하는 단서다. 계속 실패하는 PC 에서
    # 파일이 커지지 않게 마지막 20줄만 남긴다.
    try {
        $log = Join-Path (Join-Path $env:USERPROFILE '.claude') 'kw-control-tower.error'
        $line = "$(Get-Date -Format o) $($_.Exception.GetType().Name): $($_.Exception.Message) @ $($_.InvocationInfo.ScriptLineNumber)"
        $keep = @()
        if (Test-Path -LiteralPath $log) { $keep = @(Get-Content -LiteralPath $log -Encoding UTF8) }
        $keep = @($keep + $line)
        if ($keep.Count -gt 20) { $keep = $keep[($keep.Count - 20)..($keep.Count - 1)] }
        $keep | Out-File -LiteralPath $log -Encoding UTF8
    } catch { }
    exit 0
}

$sw.Stop()

# 예산을 넘겼으면 그 사실을 남긴다. 사용자가 고칠 것이 아니므로 알림에는 섞지 않는다.
#
# 덧붙이지 않고 덮어쓴다. 알고 싶은 것은 "요즘도 넘기는가"이고, 덧붙이면 콜드 스타트마다
# 한 줄씩 계속 쌓인다. 디스크 캐시가 비어 있는 첫 세션은 예산을 넘길 수 있다.
if ($sw.ElapsedMilliseconds -gt 200) {
    try {
        $over = Join-Path (Join-Path $env:USERPROFILE '.claude') 'kw-control-tower.slow'
        [System.IO.File]::WriteAllText($over,
            "$(Get-Date -Format o) $($sw.ElapsedMilliseconds)ms files=$($script:Budget.Files) net=$($script:NetMs)ms`r`n",
            (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
}

# --- 출력 -------------------------------------------------------------------
#
# 할 말을 모아 두었다가 끝에 훅 JSON 하나로 낸다. 그대로 출력하면 Claude 의 맥락에만 실리고
# 사용자 화면에는 보이지 않는다. systemMessage 는 사용자에게 표시하고, 같은 문장을
# additionalContext 로도 넣어 Claude 가 첫 답에서 재시작이나 직접 할 일을 전하게 한다.
# disciplined-coder 와 2026-09-25 에 이 형식으로 맞췄다.
$say = New-Object System.Collections.ArrayList
$syncLog = $null   # 맞춤을 불렀으면 그 진행 기록 파일. Claude 에게만 알린다.
$restartLine = 'kw-control-tower: 다시 켜야 새 버전이 적용됩니다.'
function Send-Hook {
    if ($say.Count -eq 0 -and $quietRules.Count -eq 0) { return }
    $ctx = @()
    $out = @{ hookSpecificOutput = @{ hookEventName = 'SessionStart' } }
    if ($say.Count -gt 0) {
        $text = ($say -join "`n").TrimEnd()
        $out.systemMessage = $text
        # 맞춤이 찍은 재시작 줄도 여기서 보므로 문구가 아니라 합의한 첫 줄 그대로를 찾는다.
        $alert = $text + "`n`n이 알림을 사용자의 첫 요청에 답하기 전에 먼저 전하라."
        if ($text.Contains($restartLine)) { $alert += ' 클로드 코드를 다시 켜 달라고 요구하라.' }
        if ($text -match '(?m)^\s+claude plugin ') { $alert += ' 적힌 명령을 대신 실행할지 물어라.' }
        foreach ($hint in $askHints) { if ($hint) { $alert += " $hint" } }
        if ($syncLog) { $alert += " 맞춤의 진행 기록은 $syncLog 에 있다." }
        $ctx += $alert
    }
    if ($quietRules.Count -gt 0) {
        $ctx += '다음 규칙은 사용자에게 먼저 꺼내지 말고, 해당하는 작업을 할 때만 지켜라. ' + ($quietRules -join ' ')
    }
    $out.hookSpecificOutput.additionalContext = $ctx -join "`n`n"
    $out | ConvertTo-Json -Depth 4 -Compress
}

# 다른 곳(클로드 코드의 자동 갱신, disciplined-coder)이 옮긴 설치본은 알리지 않는다. 갱신은
# 그것을 한 훅이 그 세션에서만 알린다(2026-09-29 사용자 결정). 알리면 disciplined-coder 가
# 이미 알린 갱신을 다음 세션에 한 번 더 알리게 된다. 오늘 보류한 갱신은 직접 실행할 명령이 있으므로
# 알린다. 첫 줄 형식은 disciplined-coder 와 2026-09-25 에 맞췄다.
if ($heldSay.Count -gt 0) {
    [void]$say.Add('kw-control-tower: 플러그인 버전 알림')
    [void]$say.Add('  오늘 갱신이 막혀 다시 시도하지 않았습니다. 날짜가 바뀐 뒤 처음 켜는 세션에서 다시 시도합니다.')
    foreach ($s in $heldSay) { [void]$say.Add($s) }
    [void]$say.Add('')
}

# 사용자가 직접 해야 하는 것을 먼저 말한다. 한 가지를 한 줄로 낸다. 직접 할 일은 맞춤을
# 호출하는 이유가 아니므로 아래의 맞춤과 무관하게 표시된다.
foreach ($a in $asks) { [void]$say.Add("KW 컨트롤 타워: $a") }
if ($asks.Count -gt 0 -and $notes.Count -gt 0) { [void]$say.Add('') }

if ($notes.Count -eq 0) { Send-Hook; exit 0 }   # 맞춤이 고칠 것이 없으면 맞춤을 안 호출한다

# --- 여기부터 예산 밖이다 ---------------------------------------------------
#
# 위의 감지까지가 예산 안이다. 불일치한 곳이 하나도 없으면 바로 위에서 끝나므로
# 평소 세션은 예산 그대로다. 아래는 불일치한 세션에서만 돌고, 맞춤은 외부 프로세스를
# 실행하고 네트워크에 나간다. 그 값을 치르기로 한 것은 사용자 결정이다.
#
# 알리기만 하면 알림을 읽고 명령을 실행하는 사람이 없을 때 아무것도 바뀌지 않는다.
#
# 맞춤은 멱등이다. 없거나 불일치한 것만 고치고 이미 맞는 것은 손대지 않는다. 실패해도
# 세션을 막지 않는다. 못 한 단계만 다음 세션에 다시 알리고 나머지는 조용하다.

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

# 자식 프로세스로 부른다. 같은 프로세스에서 호출하면 맞춤의 Write-Host 가 성공 스트림에
# 안 실려 못 잡는다. 둘 다 출력을 UTF-8 로 맞춰 두어 한국어가 안 깨진다.
$sync = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\sync.ps1'
if (-not (Test-Path -LiteralPath $sync)) {
    # 맞춤을 못 부를 때만 불일치 목록을 낸다. 맞춤이 돌면 그 결과가 무엇을 고쳤는지 말하므로
    # 목록을 함께 내면 같은 플러그인이 두 번 나온다.
    [void]$say.Add('KW 컨트롤 타워: 이 PC 가 사내 설정과 불일치합니다.')
    foreach ($n in $notes) { [void]$say.Add("  - $n") }
    [void]$say.Add('맞춤 스크립트를 못 찾아 고치지 못했습니다. 설치기를 다시 돌리십시오.')
    Send-Hook
    exit 0
}

try {
    # 감지가 읽은 원격 커밋을 넘긴다. 맞춤은 그 커밋까지 옮기지 못했으면 상태 파일에
    # 적고, 감지는 다음 세션에 그것을 보고 같은 실패로 맞춤을 다시 호출하지 않는다.
    $env:KWCT_REMOTE_HEAD = (@($remoteOf.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ';')
    # -Brief 로 부른다. 맞춤은 진행 출력을 로그 파일에 두고 결과만 낸다.
    $out = & pwsh -NoProfile -NonInteractive -File $sync -Brief -Steps ($runSteps -join ',') -BudgetSeconds 60 2>&1
    $syncLog = Join-Path $cfg 'kw-control-tower.sync.log'
    # 맞춤이 낸 결과를 그대로 전달한다. 다시 켜라는 안내도 맞춤이 낸다. 무엇이 재시작을
    # 요구하는지는 그 일을 하는 맞춤이 알므로 여기서 문구로 판정하지 않는다.
    foreach ($line in $out) { [void]$say.Add("$line") }
} catch {
    [void]$say.Add("맞춤을 돌리지 못했습니다: $($_.Exception.Message)")
}
Send-Hook
exit 0
