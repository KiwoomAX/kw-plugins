# 세션 시작 알림. 이 PC가 manifest.json 과 어긋난 곳을 말하기만 한다.
#
# 계약 다섯을 지킨다. 세션 시작에 도는 훅은 이것 하나이고, 외부 프로세스를 안 부르고,
# 네트워크에 안 나가고, 파일 여덟과 레지스트리 값 하나만 읽고, 몸통이 200밀리초를
# 넘으면 그 값을 상태 파일에 남긴다.
#
# 아무것도 고치지 않는다. 세션을 막지 않는다. 스스로 실패하면 조용히 물러난다.
# Windows PowerShell 5.1 에서도 돌아야 하므로 7 전용 문법을 쓰지 않는다.

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'

# 이 파일은 UTF-8 BOM 으로 저장한다. BOM 이 없으면 5.1 이 본문을 ANSI 로 읽어
# 한글 문자열이 깨진 채 출력된다. 나가는 쪽도 UTF-8 로 맞춘다.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$script:Budget = @{ Files = 0; Registry = 0 }

function Get-CheapHash {
    # MD5 를 직접 부른다. 이 PC 에서 8ms 이고 Get-FileHash 명령은 72ms 다. 아홉 배다.
    # 파일이 바뀌었는지만 가리므로 암호 강도는 필요 없다.
    # 손으로 FNV-1a 를 돌리는 길은 막혀 있다. 5.1 은 uint64 곱셈이 넘칠 때 감싸지
    # 않고 던진다. .NET 의 문자열 해시는 프로세스마다 시드가 달라 못 쓴다.
    param([string]$Path)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    try {
        $bytes = [System.IO.File]::ReadAllBytes($Path)
        return [System.BitConverter]::ToString($md5.ComputeHash($bytes)).Replace('-', '')
    } finally { $md5.Dispose() }
}

function Read-Json {
    # 없는 것과 못 읽는 것을 가른다. 없으면 $null 이고 그것은 정상일 수 있다.
    # 못 읽으면 던진다. 사용자에게는 그래도 조용히 물러나지만, 삼키면 망가진
    # 설정을 가진 PC 와 아무 문제 없는 PC 가 구별되지 않는다. 던져서 catch 가
    # 자국을 남기게 한다.
    param([string]$Path)
    $script:Budget.Files++
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    try { return (Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json) }
    catch { throw "JSON 으로 안 읽힙니다: $Path" }
}

function Get-Prop {
    # PSCustomObject 에서 이름으로 값을 꺼낸다. 5.1 에는 null 조건 연산자가 없다.
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $null }
    return $p.Value
}

function Test-Marketplace {
    # 배포처가 두 파일 가운데 어디에 등록되어 있는지 센다.
    param($Settings, $Known, [string]$Name)
    $a = Get-Prop (Get-Prop $Settings 'extraKnownMarketplaces') $Name
    $b = Get-Prop (Get-Prop $Known   'marketplaces')            $Name
    if ($null -eq $b) { $b = Get-Prop $Known $Name }
    return @{ InSettings = ($null -ne $a); InKnown = ($null -ne $b); Settings = $a; Known = $b }
}

function Get-MarketplaceHead {
    # 배포처 사본이 받아 둔 판본을 읽는다. 네트워크에 안 나간다. 디스크에 이미 있다.
    # git 사본은 HEAD 가 가리키는 ref 파일에 커밋이 있고, git 이 아닌 배포처는
    # .gcs-sha 파일 하나에 적어 둔다. 이 PC 에 둘 다 있어 둘 다 읽는다.
    param([string]$Dir)
    $g = Join-Path $Dir '.git'
    $h = Join-Path $g 'HEAD'
    $script:Budget.Files++
    if (Test-Path -LiteralPath $h) {
        $line = (Get-Content -LiteralPath $h -Raw -Encoding UTF8).Trim()
        if ($line.StartsWith('ref: ')) {
            $refFile = Join-Path $g ($line.Substring(5).Replace('/', ''))
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

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$notes = New-Object System.Collections.ArrayList

try {
    $userHome = $env:USERPROFILE
    if ([string]::IsNullOrEmpty($userHome)) { exit 0 }   # 윈도가 아니면 물러난다
    $root = $env:CLAUDE_PLUGIN_ROOT
    if ([string]::IsNullOrEmpty($root)) { exit 0 }

    $cfg     = Join-Path $userHome '.claude'
    $plugins = Join-Path $cfg 'plugins'

    $manifest = Read-Json (Join-Path $root 'manifest.json')
    if ($null -eq $manifest) { exit 0 }   # 목록을 못 읽으면 아무 말도 안 한다

    # 읽히는 것과 형식이 맞는 것은 다르다. 칸이 빠진 목록으로 판정하면 그 물음만
    # 조용히 사라져, 어긋난 PC 를 정상으로 본다. 맞춤은 이때 멈추고 말하지만 이
    # 훅은 세션을 어지럽히지 않는 쪽이라 자국만 남기고 물러난다.
    foreach ($k in @('marketplaces', 'required', 'suggested', 'retiredPlugins',
                     'retiredMarketplaces', 'retiredSkills', 'retiredHooks')) {
        if ($null -eq $manifest.PSObject.Properties[$k]) { throw "목록 파일에 '$k' 칸이 없습니다." }
    }

    $settings  = Read-Json (Join-Path $cfg     'settings.json')
    $installed = Read-Json (Join-Path $plugins 'installed_plugins.json')
    $known     = Read-Json (Join-Path $plugins 'known_marketplaces.json')

    $enabled     = Get-Prop $settings  'enabledPlugins'
    $installedOf = Get-Prop $installed 'plugins'

    # --- 물음 1과 2. 필수 플러그인이 깔려 있나, 켜져 있나 -------------------
    # 두 물음이 다른 파일에 답이 있고 고치는 명령도 다르다. install 은 사용자가
    # 꺼 둔 것을 true 로 덮으므로 깔린 것에는 절대 안 쓴다.
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
        [void]$notes.Add("필수 플러그인이 안 깔려 있습니다: $($missing -join ', ')")
    }
    if ($disabled.Count -gt 0) {
        [void]$notes.Add("필수 플러그인이 꺼져 있습니다: $($disabled -join ', ')")
    }

    # --- 물음 3. 정리하기로 한 플러그인이 남았나 ---------------------------
    $staleP = New-Object System.Collections.ArrayList
    foreach ($p in @($manifest.retiredPlugins)) {
        $id = Get-Prop $p 'id'
        if (-not $id) { continue }
        if ((Get-Prop $installedOf $id) -or ($null -ne (Get-Prop $enabled $id))) { [void]$staleP.Add($id) }
    }
    if ($staleP.Count -gt 0) {
        [void]$notes.Add("더 안 쓰는 플러그인이 남아 있습니다: $($staleP -join ', ')")
    }

    # --- 물음 4. 정리하기로 한 배포처가 남았나 -----------------------------
    $staleM = New-Object System.Collections.ArrayList
    foreach ($mk in @($manifest.retiredMarketplaces)) {
        $name = Get-Prop $mk 'name'
        if (-not $name) { continue }
        $m = Test-Marketplace $settings $known $name
        if ($m.InSettings -or $m.InKnown) { [void]$staleM.Add($name) }
    }
    if ($staleM.Count -gt 0) {
        [void]$notes.Add("더 안 쓰는 배포처가 남아 있습니다: $($staleM -join ', ')")
    }

    # --- 물음 5. 우리 배포처의 자동 갱신이 두 곳 다 켜져 있나 ---------------
    # 두 파일은 서로 값을 주고받지 않는다. 그래서 두 곳 다 본다.
    $offAuto = New-Object System.Collections.ArrayList
    foreach ($mk in @($manifest.marketplaces)) {
        if ((Get-Prop $mk 'ours') -ne $true) { continue }   # 남의 배포처는 안 잰다
        $name = Get-Prop $mk 'name'
        $m = Test-Marketplace $settings $known $name
        if (-not ($m.InSettings -or $m.InKnown)) { [void]$offAuto.Add("$name (등록 없음)"); continue }
        $a = Get-Prop $m.Settings 'autoUpdate'
        $b = Get-Prop $m.Known    'autoUpdate'
        if (($a -ne $true) -or ($b -ne $true)) { [void]$offAuto.Add($name) }
    }
    if ($offAuto.Count -gt 0) {
        [void]$notes.Add("자동 갱신이 꺼져 있습니다: $($offAuto -join ', ')")
    }

    # --- 물음 6. 파이썬 라이브러리 목록이 바뀌었나 -------------------------
    # 예산 안에서 이 PC 를 직접 못 읽는 것이 이 하나뿐이라 해시로 잰다.
    # 재는 것은 파일이다. JSON 의 부분 트리를 해시하면 프로세스마다 값이 달라진다.
    $stateFile = Join-Path $cfg 'kw-control-tower.state'
    $reqFile   = Join-Path $root 'requirements.txt'
    $script:Budget.Files++
    if (Test-Path -LiteralPath $reqFile) {
        $now = Get-CheapHash $reqFile
        $was = $null
        $script:Budget.Files++
        if (Test-Path -LiteralPath $stateFile) {
            foreach ($line in (Get-Content -LiteralPath $stateFile -Encoding UTF8)) {
                if ($line -like 'requirements=*') { $was = $line.Substring(13) }
            }
        }
        if ($now -ne $was) {
            [void]$notes.Add('파이썬 라이브러리 목록이 이 PC에 맞춰진 것과 다릅니다.')
        }
    }

    # --- 물음 7. PYTHONUTF8 이 세워졌나 ------------------------------------
    # 사용자가 일부러 0 으로 둔 것은 그대로 두는 것이 맞으므로 그때는 말하지 않는다.
    $script:Budget.Registry++
    $utf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'User')
    if ($null -eq $utf8) {
        [void]$notes.Add('PYTHONUTF8 이 세워져 있지 않습니다. 한글이 깨질 수 있습니다.')
    }

    # --- 물음 8. CLAUDE.md 의 사내 문안이 템플릿과 같나 ---------------------
    # 이것이 감지 표에 있는데 훅에 없었다. 사내 문안을 손으로 고쳐도 아무도 모르는
    # 상태였다. 판본이나 해시가 아니라 글자를 견준다. 줄바꿈은 두 파일이 서로 다를
    # 수 있고 그것은 다름이 아니므로 맞춘 뒤에 견준다.
    $tpl = Join-Path $root 'templates\personal-memory-ko.md'
    $mem = Join-Path $cfg 'CLAUDE.md'
    $script:Budget.Files += 2
    if ((Test-Path -LiteralPath $tpl) -and (Test-Path -LiteralPath $mem)) {
        $u8 = New-Object System.Text.UTF8Encoding($false)
        $block = ([System.IO.File]::ReadAllText($tpl, $u8)).Trim()
        $now   = [System.IO.File]::ReadAllText($mem, $u8)
        $re    = '(?ms)^#\s*BEGIN AX\b.*?^#\s*END AX[^\r\n]*'
        $found = [regex]::Match($now, $re)
        $norm  = { param($t) ($t -replace "`r`n", "`n").Trim() }
        $howMany = @([regex]::Matches($now, $re)).Count
        if (-not $found.Success) {
            [void]$notes.Add('CLAUDE.md 에 사내 문안 블록이 없습니다.')
        } elseif ($howMany -gt 1) {
            # 개수를 따로 세는 것은 위 정규식이 첫 블록만 잡기 때문이다. 개수를 안
            # 보면 같은 블록이 둘인 파일이 "이미 같다" 로 읽혀 조용히 남는다.
            [void]$notes.Add("CLAUDE.md 에 사내 문안 블록이 $howMany 개 있습니다.")
        } elseif ((& $norm $found.Value) -ne (& $norm $block)) {
            [void]$notes.Add('CLAUDE.md 의 사내 문안 블록이 배포된 것과 다릅니다.')
        }
    }

    # --- 물음 9와 10. 정리하기로 한 스킬과 훅이 남았나 ---------------------
    $staleS = New-Object System.Collections.ArrayList
    foreach ($s in @($manifest.retiredSkills)) {
        $name = Get-Prop $s 'name'
        if (-not $name) { continue }
        if (Test-Path -LiteralPath (Join-Path (Join-Path $cfg 'skills') $name)) { [void]$staleS.Add($name) }
    }
    if ($staleS.Count -gt 0) {
        [void]$notes.Add("더 안 쓰는 스킬 사본이 남아 있습니다: $($staleS -join ', ')")
    }

    # 훅 배선은 파일 이름이 아니라 경로로 가른다. 이 플러그인이 거는 훅의 파일 이름이
    # 옛것과 같아서, 이름만 보면 자기 배선을 남의 것으로 센다.
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
        [void]$notes.Add("더 안 쓰는 훅 배선이 남아 있습니다: $($staleH -join ', ')")
    }

    # --- 물음 11. 우리 배포처에서 온 설치본이 사본보다 뒤처졌나 --------------
    # 자동 갱신이 사본을 새 커밋까지 받아 놓고도 설치본을 안 옮기는 것을 2026-09-19 에
    # 이 PC 에서 두 건 확인했다. 한쪽은 57 커밋 뒤처져 있었고 자동 갱신은 켜져 있었다.
    # 두 값이 다 디스크에 있으므로 네트워크에 안 나가고 비교할 수 있다.
    #
    # 남의 배포처는 안 본다. 회사가 필수로 정한 것만 최신이어야 하고, 남의 것을 언제
    # 올릴지는 사용자가 정한다.
    $behind = New-Object System.Collections.ArrayList
    foreach ($mk in @($manifest.marketplaces)) {
        if ((Get-Prop $mk 'ours') -ne $true) { continue }
        $mkName = Get-Prop $mk 'name'
        if (-not $mkName) { continue }
        $head = Get-MarketplaceHead (Join-Path (Join-Path $plugins 'marketplaces') $mkName)
        if (-not $head -or $null -eq $installedOf) { continue }
        foreach ($pluginId in @($installedOf.PSObject.Properties.Name)) {
            if (-not $pluginId.EndsWith("@$mkName")) { continue }
            foreach ($scope in @(Get-Prop $installedOf $pluginId)) {
                $sha = Get-Prop $scope 'gitCommitSha'
                if (-not $sha) { continue }
                if (-not $head.StartsWith($sha) -and -not $sha.StartsWith($head)) {
                    [void]$behind.Add($pluginId)
                    break
                }
            }
        }
    }
    if ($behind.Count -gt 0) {
        [void]$notes.Add("설치본이 배포처 사본보다 뒤처져 있습니다: $(($behind | Select-Object -Unique) -join ', ')")
    }

    # --- 물음 12. 배포처 사본을 오래 받아오지 않았나 ------------------------
    # 사본 자체가 낡았는지는 네트워크에 나가야 확실히 안다. 감지는 안 나가므로 대신
    # 마지막으로 받아온 시각을 본다. 맞춤이 받아올 때마다 그 시각을 적으므로, 저장소에
    # 새 커밋이 없어 사본이 안 움직이는 때에도 이 물음이 되풀이되지 않는다.
    $script:Budget.Files++
    $refreshed = $null
    if (Test-Path -LiteralPath $stateFile) {
        foreach ($line in (Get-Content -LiteralPath $stateFile -Encoding UTF8)) {
            if ($line -like 'refreshed=*') { $refreshed = $line.Substring(10) }
        }
    }
    $stale = $true
    if ($refreshed) {
        try { $stale = ([datetime]::Parse($refreshed) -lt (Get-Date).AddDays(-14)) } catch { $stale = $true }
    }
    if ($stale) {
        [void]$notes.Add('배포처 사본을 열나흘 넘게 받아오지 않았습니다.')
    }
}
catch {
    # 사용자에게는 조용히 물러난다. 세션 시작을 훅의 사정으로 어지럽히지 않는다.
    # 다만 자국은 남긴다. 조용한 실패가 개발 중에 버그 하나를 통째로 가렸다.
    # 여기는 덧붙인다. 같은 오류가 반복되는지가 원인을 가리기 때문이다. 다만 영원히
    # 실패하는 PC 에서 파일이 자라지 않게 마지막 스무 줄만 남긴다.
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

# 예산을 넘겼으면 그 사실을 남긴다. 알림에는 안 섞는다. 사용자가 고칠 것이 아니다.
#
# 덧붙이지 않고 덮어쓴다. 알고 싶은 것은 "요즘도 넘기는가"이지 넘긴 역사가 아니고,
# 덧붙이면 찬 시작마다 한 줄씩 영원히 쌓인다. 세션이 처음 열릴 때 한 번은 넘길 수
# 있다. 이 PC 에서 여덟 번을 재니 몸통이 다 200밀리초 안이었고 넘긴 것은 디스크가
# 식어 있던 첫 회뿐이었다.
if ($sw.ElapsedMilliseconds -gt 200) {
    try {
        $over = Join-Path (Join-Path $env:USERPROFILE '.claude') 'kw-control-tower.slow'
        [System.IO.File]::WriteAllText($over,
            "$(Get-Date -Format o) $($sw.ElapsedMilliseconds)ms files=$($script:Budget.Files)`r`n",
            (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
}

# --- 자동 갱신이 조용히 한 일을 보여준다 -----------------------------------
#
# 클로드 코드의 자동 갱신은 아무 말 없이 설치본을 새 판으로 옮긴다. 무엇이 언제
# 바뀌었는지 사용자가 알 길이 없었다. 지난 세션에 본 판본을 적어 두고 달라진 것만
# 알린다. 어긋난 곳이 하나도 없어도 이것은 말한다.
#
# 우리 배포처만 보지 않고 깔린 것을 다 본다. 사용자가 알고 싶은 것은 "무엇이 나도
# 모르게 바뀌었나" 이고 그 물음에 우리 것과 남의 것의 구별이 없다.
$changed = New-Object System.Collections.ArrayList
try {
    $seenFile = Join-Path $cfg 'kw-control-tower.seen'
    $seen = @{}
    if (Test-Path -LiteralPath $seenFile) {
        foreach ($line in (Get-Content -LiteralPath $seenFile -Encoding UTF8)) {
            $i = $line.IndexOf('=')
            if ($i -gt 0) { $seen[$line.Substring(0, $i)] = $line.Substring($i + 1) }
        }
    }
    $now = @{}
    if ($null -ne $installedOf) {
        foreach ($pluginId in @($installedOf.PSObject.Properties.Name)) {
            foreach ($scope in @(Get-Prop $installedOf $pluginId)) {
                $v = Get-Prop $scope 'version'
                if (-not $v) { $v = Get-Prop $scope 'gitCommitSha' }
                if ($v) { $now[$pluginId] = "$v"; break }
            }
        }
    }
    # 처음 도는 PC 에서는 깔린 것을 통째로 '바뀐 것' 으로 세게 된다. 그때는 적어만
    # 두고 말하지 않는다. 사용자가 방금 깐 것을 갱신이라고 알리면 거짓말이 된다.
    if ($seen.Count -gt 0) {
        foreach ($pluginId in @($now.Keys)) {
            if ($seen.ContainsKey($pluginId) -and $seen[$pluginId] -ne $now[$pluginId]) {
                [void]$changed.Add("$pluginId : $($seen[$pluginId]) -> $($now[$pluginId])")
            }
        }
    }
    if ($now.Count -gt 0) {
        $lines = foreach ($k in $now.Keys) { "$k=$($now[$k])" }
        [System.IO.File]::WriteAllLines($seenFile, [string[]]@($lines), (New-Object System.Text.UTF8Encoding($false)))
    }
} catch { }

if ($changed.Count -gt 0) {
    Write-Output 'KW 컨트롤 타워: 지난 세션 뒤로 아래가 새 판으로 바뀌었습니다.'
    foreach ($c in ($changed | Sort-Object)) { Write-Output "  - $c" }
    Write-Output '자동 갱신이 한 것이라 사용자가 부른 적이 없습니다. 새 판은 다음에 켤 때부터 실립니다.'
    if ($notes.Count -gt 0) { Write-Output '' }
}

if ($notes.Count -eq 0) { exit 0 }   # 이상이 없으면 아무 말도 안 하고 아무것도 안 고친다

Write-Output 'KW 컨트롤 타워: 이 PC가 사내 설정과 어긋난 곳이 있습니다.'
foreach ($n in $notes) { Write-Output "  - $n" }

# --- 여기부터 예산 밖이다 ---------------------------------------------------
#
# 위의 감지까지가 예산 안이다. 어긋난 곳이 하나도 없으면 바로 위에서 끝나므로
# 평소 세션은 예산 그대로다. 아래는 어긋난 세션에서만 돌고, 맞춤은 외부 프로세스를
# 띄우고 네트워크에 나간다. 그 값을 치르기로 한 것은 사용자 결정이다.
#
# 알리기만 하던 때에는 사내 목록에 새 플러그인이 더해진 것을 알고도 몇 주씩 안 깔린
# PC 가 남았다. 알림을 읽고 명령을 부르는 사람이 없으면 감지는 아무것도 바꾸지 않는다.
#
# 맞춤은 멱등이다. 없거나 어긋난 것만 고치고 이미 맞는 것은 손대지 않는다. 실패해도
# 세션을 막지 않는다. 못 한 단계만 다음 세션에 다시 알리고 나머지는 조용하다.
#
# 자식 프로세스로 부른다. 같은 프로세스에서 부르면 맞춤의 Write-Host 가 성공 스트림에
# 안 실려 못 잡는다. 둘 다 출력을 UTF-8 로 맞춰 두어 한국어가 안 깨진다.
$sync = Join-Path (Split-Path -Parent $PSScriptRoot) 'scripts\sync.ps1'
if (-not (Test-Path -LiteralPath $sync)) {
    Write-Output '맞춤 스크립트를 못 찾아 고치지 못했습니다. 설치기를 다시 돌리십시오.'
    exit 0
}

Write-Output ''
try {
    $out = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $sync 2>&1
    foreach ($line in $out) { Write-Output "$line" }
    # 새로 깐 것이 있을 때만 다시 켜라고 말한다. 클로드 코드는 시작할 때 플러그인을
    # 읽으므로 방금 깐 것은 이 세션에 안 실린다. 맞춤이 그 문구를 낼 때만 붙인다.
    if (($out | Out-String) -match '플러그인을 깔았습니다') {
        Write-Output ''
        Write-Output '새로 깐 플러그인은 클로드 코드를 다시 켜야 실립니다.'
    }
} catch {
    Write-Output "맞춤을 돌리지 못했습니다: $($_.Exception.Message)"
}
exit 0
