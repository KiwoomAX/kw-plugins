#Requires -Version 7.0
# Contract tests for the kw-dashboard plugin.
#   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tests\test_dashboard.ps1
#
# The skill guides work inside repos made from KiwoomAX/dashboard-template. The
# template's code comments, types and console warnings already teach the shell;
# the skill carries only what the code cannot say.

$ErrorActionPreference = 'Stop'
$Repo      = Split-Path -Parent $PSScriptRoot
$PluginDir = Join-Path $Repo 'plugins/kw-dashboard'
$SkillDir  = Join-Path $PluginDir 'skills/building-kiwoom-dashboard'

$script:Pass = 0
$script:Fail = 0
function Assert($label, $cond) {
    if ($cond) { $script:Pass++; Write-Host "PASS  $label" -ForegroundColor Green }
    else       { $script:Fail++; Write-Host "FAIL  $label" -ForegroundColor Red }
}
function Read-JsonOrNull($path) {
    if (Test-Path $path) { return (Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json) }
    return $null
}
function Read-TextOrEmpty($path) {
    if (Test-Path $path) { return [IO.File]::ReadAllText($path) }
    return ''
}

$PluginName = 'kw-dashboard'
$PluginId   = 'kw-dashboard@kiwoom-ax'

Write-Host '--- manifests ---'
$pluginJson = Read-JsonOrNull (Join-Path $PluginDir '.claude-plugin/plugin.json')
$mkt        = Read-JsonOrNull (Join-Path $Repo '.claude-plugin/marketplace.json')
$manifest   = Read-JsonOrNull (Join-Path $Repo 'plugins/kw-control-tower/manifest.json')

Assert "plugin.json name is $PluginName" ($pluginJson.name -eq $PluginName)
$entry = $null
if ($mkt -and $mkt.plugins) { $entry = @($mkt.plugins) | Where-Object { $_.name -eq $PluginName } | Select-Object -First 1 }
Assert "the marketplace ships $PluginName" ($null -ne $entry)
Assert 'the plugin source is an in-repo path' ($null -ne $entry -and $entry.source -eq './plugins/kw-dashboard')
Assert 'both descriptions are the same text' ($null -ne $pluginJson.description -and $null -ne $entry -and $pluginJson.description -eq $entry.description)
Assert 'plugin.json carries no version (commit-based auto update)' ($null -ne $pluginJson -and $null -eq $pluginJson.PSObject.Properties['version'])
Assert "the control tower requires $PluginId" ($null -ne $manifest -and @($manifest.required) -contains $PluginId)

Write-Host '--- skill ---'
$md = Join-Path $SkillDir 'SKILL.md'
Assert 'SKILL.md ships' (Test-Path $md)
$text = Read-TextOrEmpty $md
$name = ([regex]::Match($text, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
Assert 'frontmatter name matches the folder' ($name -eq 'building-kiwoom-dashboard')
$desc = ([regex]::Match($text, '(?m)^description:\s*(.+)$')).Groups[1].Value
Assert 'description says when to open the skill' ($desc -match '^Use when ')
# A plain YAML scalar ends at ": " or " #"; the rest of the description would be lost.
Assert 'description is a safe plain scalar' (-not ($desc -match ': | #'))

# A reference file that SKILL.md does not link is never opened.
$refs = @('moving-existing-dashboard.md')
foreach ($ref in $refs) {
    Assert "$ref ships" (Test-Path (Join-Path $SkillDir $ref))
    Assert "SKILL.md links $ref" ($text -match [regex]::Escape("]($ref)"))
}
$refText = @($refs | ForEach-Object { Read-TextOrEmpty (Join-Path $SkillDir $_) }) -join "`n"
$allText = $text + "`n" + $refText

Assert 'no skill file points at a personal skills folder' (-not ($allText -match '~/\.claude'))
Assert 'no skill file calls python3' (-not ($allText -match '\bpython3\b'))
Assert 'skill documents carry no build-history notes' (-not ($allText -match '\b20\d\d-\d\d-\d\d\b|\(실측|실측\)|쓰던 때|섞여 있던'))

# The skill starts people from the template repo and hands deploys to the
# deploy skill. Both names must stay real.
Assert 'the skill names the template repo' ($text -match 'KiwoomAX/dashboard-template')
Assert 'the deploy skill it hands off to ships in this marketplace' (
    ($allText -match 'deploying-kiwoom-service') -and
    (Test-Path (Join-Path $Repo 'plugins/kw-devops/skills/deploying-kiwoom-service/SKILL.md')))

Write-Host '--- claude plugin validate ---'
Push-Location $Repo
try {
    $null = & claude plugin validate ./ 2>&1 | Out-String
    $code = $LASTEXITCODE
} finally { Pop-Location }
Assert 'claude plugin validate exits 0 (warnings allowed)' ($code -eq 0)

Write-Host ''
Write-Host ("PASS={0} FAIL={1}" -f $script:Pass, $script:Fail)
if ($script:Fail -ne 0) { exit 1 }
