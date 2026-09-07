#Requires -Version 7.0
# Contract tests for the kw-doc-formats plugin.
#   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tests\test_doc_formats.ps1
#
# The plugin moved into this repo on 2026-09-07. It used to live in
# KiwoomAX/KW-doc-formats and be published by its own marketplace; both plugins
# are shipped by kiwoom-ax now and the source is an in-repo path.

$ErrorActionPreference = 'Stop'
$Repo   = Split-Path -Parent $PSScriptRoot
# 폴더 경로를 $Plugin 으로 두면 안 된다. PowerShell 은 변수 이름의 대소문자를 안
# 가려서, 아래에서 plugin.json 을 담는 $plugin 과 같은 변수가 된다. 경로가 조용히
# JSON 객체로 덮이고 한참 뒤 Join-Path 에서 엉뚱한 오류로 터진다.
$PluginDir = Join-Path $Repo 'plugins/kw-doc-formats'

$script:Pass = 0
$script:Fail = 0
function Assert($label, $cond) {
    if ($cond) { $script:Pass++; Write-Host "PASS  $label" -ForegroundColor Green }
    else       { $script:Fail++; Write-Host "FAIL  $label" -ForegroundColor Red }
}
# Reads JSON if the file exists, else $null, so a missing file is a FAIL line
# and not a crash before the totals print.
function Read-JsonOrNull($path) {
    if (Test-Path $path) { return (Get-Content $path -Raw | ConvertFrom-Json) }
    return $null
}
function Read-TextOrEmpty($path) {
    if (Test-Path $path) { return [IO.File]::ReadAllText($path) }
    return ''
}

$PluginName = 'kw-doc-formats'
$PluginId   = 'kw-doc-formats@kiwoom-ax'

Write-Host '--- manifests ---'
$pluginJson   = Join-Path $PluginDir '.claude-plugin/plugin.json'
$mktJson      = Join-Path $Repo   '.claude-plugin/marketplace.json'
$manifestJson = Join-Path $Repo   'plugins/kw-control-tower/manifest.json'
Assert 'plugin.json exists' (Test-Path $pluginJson)
Assert 'marketplace.json exists' (Test-Path $mktJson)
$plugin   = Read-JsonOrNull $pluginJson
$mkt      = Read-JsonOrNull $mktJson
$manifest = Read-JsonOrNull $manifestJson

Assert "plugin.json name is $PluginName" ($plugin.name -eq $PluginName)

# The marketplace ships more than this plugin, so the entry is looked up by
# name rather than by position.
$entry = $null
if ($mkt -and $mkt.plugins) { $entry = @($mkt.plugins) | Where-Object { $_.name -eq $PluginName } | Select-Object -First 1 }
Assert "the marketplace ships $PluginName" ($null -ne $entry)

# An in-repo relative path is the only form used here. A cross-repo object
# source written as { source: github, repo: ... } resolves over SSH and dies on
# a machine with no key; see the comment in marketplace.json.
Assert 'the plugin source is an in-repo path' ($null -ne $entry -and $entry.source -eq './plugins/kw-doc-formats')
Assert 'both descriptions are the same text' ($null -ne $plugin.description -and $null -ne $entry -and $plugin.description -eq $entry.description)
Assert 'plugin.json carries no version (commit-based auto update)' ($null -ne $plugin -and $null -eq $plugin.PSObject.Properties['version'])

# The list that requires this plugin now lives in the same repo, so the id is
# cross-checked here instead of being pinned by hand against another one. The
# hand-pinned version went stale: kw_install stopped holding the list and
# nothing failed.
Assert "the control tower requires $PluginId" ($null -ne $manifest -and @($manifest.required) -contains $PluginId)

Write-Host '--- skills ---'
$skillDirs = @(Get-ChildItem -Path (Join-Path $PluginDir 'skills') -Directory -ErrorAction SilentlyContinue)
Assert 'at least one skill ships' ($skillDirs.Count -gt 0)
foreach ($d in $skillDirs) {
    $md = Join-Path $d.FullName 'SKILL.md'
    Assert "$($d.Name) has SKILL.md" (Test-Path $md)
    $text = Read-TextOrEmpty $md
    $name = ([regex]::Match($text, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
    Assert "$($d.Name) frontmatter name matches the folder" ($name -eq $d.Name)
}

# Each rule must live in exactly one skill, and the skill that owns it must be
# reachable. These check placement, not wording: a body assertion says the rule
# is here, and its negative says the rule is not left behind somewhere else.
$Bodies = @{}
foreach ($d in $skillDirs) { $Bodies[$d.Name] = Read-TextOrEmpty (Join-Path $d.FullName 'SKILL.md') }
function Body($name) { if ($Bodies.ContainsKey($name)) { return $Bodies[$name] } return '' }
function Desc($name) { return ([regex]::Match((Body $name), '(?ms)^description:\s*(.+?)$')).Groups[1].Value }

foreach ($n in @('common', 'hwp', 'pdf', 'pptx', 'xlsx', 'docx')) {
    Assert "the $n skill ships" ($Bodies.ContainsKey($n))
}

# common owns encoding. Nothing else restates it.
Assert 'common carries the encoding section' ((Body 'common') -match '(?m)^## 파이썬으로 파일을 열 때는 인코딩을 반드시 적는다')
Assert 'common detects the encoding of incoming CSV' ((Body 'common') -match 'chardet')
Assert 'common writes CSV meant for Excel with a BOM' ((Body 'common') -match 'utf-8-sig')
Assert 'xlsx does not restate the CSV encoding rule' (-not ((Body 'xlsx') -match 'utf-8-sig'))

# xlsx owns the cell font size.
Assert 'xlsx fixes the cell font size at 11' ((Body 'xlsx') -match 'size=11')

# hwp owns the conversion of formats Claude cannot read.
Assert 'hwp drives the Hangul word processor' ((Body 'hwp') -match 'HWPFrame\.HwpObject')
Assert 'hwp covers legacy Office files' ((Body 'hwp') -match '\.doc')

# docx names the tools that exist on this PC.
Assert 'docx builds with python-docx' ((Body 'docx') -match 'python-docx')
Assert 'docx reads with markitdown' ((Body 'docx') -match 'markitdown')

# pdf owns page selection and PDF output.
Assert 'pdf prints through headless Edge' ((Body 'pdf') -match '--print-to-pdf')

# pptx owns the Korean deck defaults.
Assert 'pptx removes the glyph outline' ((Body 'pptx') -match 'fontFace|ln')

# A skill is only read when its description matches what the user is doing, and
# skills never chain on their own. Each format skill must name its official
# counterpart in the description, and point at common in the body.
foreach ($n in @('pdf', 'pptx', 'xlsx', 'docx')) {
    Assert "$n names document-skills:$n in its description" ((Desc $n) -match [regex]::Escape("document-skills:$n"))
}
foreach ($n in @('hwp', 'pdf', 'pptx', 'xlsx', 'docx')) {
    Assert "$n points at kw-doc-formats:common" ((Body $n) -match 'kw-doc-formats:common')
}

# The monolith is gone; no leftover may name it.
foreach ($d in $skillDirs) {
    Assert "$($d.Name) does not name the retired skill" (-not ((Body $d.Name) -match 'document-formats'))
}

Write-Host '--- claude plugin validate ---'
# Exit code is the verdict. The tool prints warnings for a missing version and
# author and still exits 0; an error exits non-zero. Run at the repo root so the
# whole marketplace is validated, both plugins included.
Push-Location $Repo
try {
    $null = & claude plugin validate ./ 2>&1 | Out-String
    $code = $LASTEXITCODE
} finally { Pop-Location }
Assert 'claude plugin validate exits 0 (warnings allowed)' ($code -eq 0)

Write-Host ''
Write-Host ("PASS={0} FAIL={1}" -f $script:Pass, $script:Fail)
if ($script:Fail -ne 0) { exit 1 }
