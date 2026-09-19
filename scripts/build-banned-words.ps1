# KiwoomAX/korean-banned-words 의 데이터에서 사내 배포용 금지어 목록을 만든다.
#
#   pwsh -File scripts\build-banned-words.ps1
#
# 데이터는 data\korean-banned-words.json 에 사본으로 둔다. 그 저장소의 Actions 가
# 바뀔 때마다 이 저장소에 PR 을 열어 사본과 생성물을 함께 갱신한다. 사본을 두는 것은
# 검사가 네트워크에 안 나가게 하기 위해서다. 검사는 사람이 손으로 돌리므로 사내망에서
# 막히면 아무도 안 돌린다.
#
# 검색 방식은 match 값에 따라 달라지지 않는다. 둘 다 그 글자가 들어 있으면 걸린다.
# 한국어는 조사가 붙어 '재다가'·'재다를' 이 되므로 단어 경계로 막으면 놓친다.
# match 는 데이터 저장소 안에서만 뜻이 있다. forms 는 활용형을 다 적을 책임이 있고
# fragment 는 어간만 적으면 된다는 표시다. 그래서 여기서는 banned 의 원소를 전부
# 검색어로 내보내고 match 는 보지 않는다.

[CmdletBinding()]
param(
    # 만들지 않고 지금 파일과 같은지만 본다. 검사가 이 갈래로 부른다.
    [switch]$Check
)

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$repo = Split-Path -Parent $PSScriptRoot
$src  = Join-Path $repo 'data\korean-banned-words.json'
$dst  = Join-Path $repo 'plugins\kw-control-tower\templates\korean-banned-words.md'

if (-not (Test-Path -LiteralPath $src)) { throw "데이터 사본이 없습니다: $src" }

$utf8 = New-Object System.Text.UTF8Encoding($false)
$data = [System.IO.File]::ReadAllText($src, $utf8) | ConvertFrom-Json

# 칸이 빠진 데이터로 만들면 그 항목만 조용히 사라진다. 멈추고 말한다.
foreach ($k in @('schema', 'categories', 'entries', 'rules')) {
    if ($null -eq $data.PSObject.Properties[$k]) { throw "데이터에 '$k' 칸이 없습니다." }
}
if ($data.schema -ne 1) { throw "모르는 schema 입니다: $($data.schema). 이 스크립트는 1 만 압니다." }

function Get-DisplayWidth {
    # 한글은 글자 하나가 두 칸으로 보인다. 글자 수로 맞추면 화살표가 들쭉날쭉해진다.
    # 한글 음절과 한중일 기호와 전각 문자를 두 칸으로 센다.
    param([string]$Text)
    $w = 0
    foreach ($ch in $Text.ToCharArray()) {
        $c = [int]$ch
        if (($c -ge 0x1100 -and $c -le 0x115F) -or ($c -ge 0x2E80 -and $c -le 0xA4CF) -or
            ($c -ge 0xAC00 -and $c -le 0xD7A3) -or ($c -ge 0xF900 -and $c -le 0xFAFF) -or
            ($c -ge 0xFE30 -and $c -le 0xFE6F) -or ($c -ge 0xFF00 -and $c -le 0xFF60) -or
            ($c -ge 0xFFE0 -and $c -le 0xFFE6)) { $w += 2 } else { $w += 1 }
    }
    return $w
}

$lines = New-Object System.Collections.ArrayList
function Add-Line { param([string]$s = '') [void]$lines.Add($s) }

Add-Line '# 한국어 금지어 목록'
Add-Line ''
Add-Line '이 파일은 생성물이다. 고치려면 KiwoomAX/korean-banned-words 의 데이터를 고친다.'
Add-Line '여기를 손으로 고치면 scripts\build-banned-words.ps1 -Check 가 떨어진다.'
Add-Line ''
Add-Line '답변과 산출물에 아래 왼쪽 단어를 쓰지 않는다. 오른쪽을 쓴다.'
Add-Line ''
Add-Line '사람의 판단에 맡기지 않는다. 내보내기 전에 문자열로 검색해서 거른다. 코드와 파일 이름과'
Add-Line '인용은 대상이 아니다. 산출물은 보고서·제안서·인수인계·발표자료처럼 사람이 읽으려고'
Add-Line '만드는 문서를 말한다.'

# 분류 순서는 데이터가 정한다. 여기서 다시 정렬하면 두 소비자의 절 순서가 갈린다.
foreach ($cat in $data.categories) {
    $rows = @($data.entries | Where-Object { $_.category -eq $cat.id -and $_.enabled })
    if ($rows.Count -eq 0) { continue }

    Add-Line ''
    Add-Line "## $($cat.title)"
    Add-Line ''
    Add-Line '```'

    # 화살표를 세로로 맞춘다. 왼쪽이 가장 긴 것에 맞추되, 한글은 글자 하나가 두 칸으로
    # 보이므로 글자 수가 아니라 표시 너비로 센다.
    #
    # 맞추는 폭에 상한을 둔다. '걸다' 처럼 조사까지 적은 구가 스물셋인 항목이 있어서,
    # 그것에 맞추면 그 분류의 모든 줄이 이백 칸 넘게 벌어져 통째로 안 읽힌다. 상한을
    # 넘는 줄은 혼자 길어지고 나머지는 서로 맞는다.
    $cap = 44
    $pairs = foreach ($e in $rows) {
        $right = if ($e.replace) { ($e.replace -join ' · ') } else { $e.instruction }
        [pscustomobject]@{ Left = ($e.banned -join ' · '); Right = $right }
    }
    $fit = @($pairs | ForEach-Object { Get-DisplayWidth $_.Left } | Where-Object { $_ -le $cap })
    $max = if ($fit.Count -gt 0) { ($fit | Measure-Object -Maximum).Maximum } else { 0 }
    foreach ($p in $pairs) {
        $w = Get-DisplayWidth $p.Left
        $pad = if ($w -le $max) { ' ' * ($max - $w + 3) } else { '   ' }
        Add-Line "$($p.Left)$pad→   $($p.Right)"
    }
    Add-Line '```'
}

$liveRules = @($data.rules | Where-Object { $_.enabled })
if ($liveRules.Count -gt 0) {
    Add-Line ''
    Add-Line '## 단어가 아닌 규칙'
    foreach ($r in $liveRules) {
        Add-Line ''
        Add-Line $r.text
    }
}

$made = ($lines -join "`r`n") + "`r`n"

if ($Check) {
    if (-not (Test-Path -LiteralPath $dst)) { Write-Host "없습니다: $dst"; exit 1 }
    $have = [System.IO.File]::ReadAllText($dst, $utf8)
    if ($have -eq $made) { Write-Host '같습니다.'; exit 0 }
    Write-Host '데이터에서 다시 만든 것과 다릅니다. 손으로 고쳤거나 사본이 낡았습니다.' -ForegroundColor Yellow
    exit 1
}

[System.IO.File]::WriteAllText($dst, $made, $utf8)
Write-Host "만들었습니다: $dst"
Write-Host "  항목 $(@($data.entries | Where-Object { $_.enabled }).Count) 개, 규칙 $($liveRules.Count) 개"
