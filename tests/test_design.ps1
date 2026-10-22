#Requires -Version 7.0
# Contract tests for the kw-design plugin.
#   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tests\test_design.ps1
#
# The skill gives the default look of in-house web screens, a dashboard mockup
# template generated from KiwoomAX/dashboard-template, and a copy of its tokens.

$ErrorActionPreference = 'Stop'
$Repo      = Split-Path -Parent $PSScriptRoot
$PluginDir = Join-Path $Repo 'plugins/kw-design'
$SkillDir  = Join-Path $PluginDir 'skills/designing-kiwoom-frontend'

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

$PluginName = 'kw-design'
$PluginId   = 'kw-design@kiwoom-ax'

Write-Host '--- manifests ---'
$pluginJson = Read-JsonOrNull (Join-Path $PluginDir '.claude-plugin/plugin.json')
$mkt        = Read-JsonOrNull (Join-Path $Repo '.claude-plugin/marketplace.json')
$manifest   = Read-JsonOrNull (Join-Path $Repo 'plugins/kw-control-tower/manifest.json')

Assert "plugin.json name is $PluginName" ($pluginJson.name -eq $PluginName)
$entry = $null
if ($mkt -and $mkt.plugins) { $entry = @($mkt.plugins) | Where-Object { $_.name -eq $PluginName } | Select-Object -First 1 }
Assert "the marketplace ships $PluginName" ($null -ne $entry)
Assert 'the plugin source is an in-repo path' ($null -ne $entry -and $entry.source -eq './plugins/kw-design')
Assert 'both descriptions are the same text' ($null -ne $pluginJson.description -and $null -ne $entry -and $pluginJson.description -eq $entry.description)
Assert 'plugin.json carries no version (commit-based auto update)' ($null -ne $pluginJson -and $null -eq $pluginJson.PSObject.Properties['version'])
# The in-house guide in CLAUDE.md tells every session to read this skill, so every PC must have it.
Assert "the control tower requires $PluginId" ($null -ne $manifest -and @($manifest.required) -contains $PluginId)
$guide = Read-TextOrEmpty (Join-Path $Repo 'plugins/kw-control-tower/templates/claude-md-ko.md')
Assert 'the in-house guide names this skill' ($guide -match [regex]::Escape('kw-design:designing-kiwoom-frontend'))

Write-Host '--- skill ---'
$md = Join-Path $SkillDir 'SKILL.md'
Assert 'SKILL.md ships' (Test-Path $md)
$text = Read-TextOrEmpty $md
$name = ([regex]::Match($text, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
Assert 'frontmatter name matches the folder' ($name -eq 'designing-kiwoom-frontend')
$desc = ([regex]::Match($text, '(?m)^description:\s*(.+)$')).Groups[1].Value
Assert 'description says when to open the skill' ($desc -match '^Use when ')
Assert 'description is a safe plain scalar' (-not ($desc -match ': | #'))
Assert 'no skill file points at a personal skills folder' (-not ($text -match '~/\.claude'))
Assert 'no skill file calls python3' (-not ($text -match '\bpython3\b'))
Assert 'skill document carries no build-history notes' (-not ($text -match '\b20\d\d-\d\d-\d\d\b|\(실측|실측\)'))

# A template that SKILL.md does not link is never opened.
foreach ($t in @('templates/dashboard-mockup.html', 'templates/tokens.css')) {
    Assert "$t ships" (Test-Path (Join-Path $SkillDir $t))
    Assert "SKILL.md links $t" ($text -match [regex]::Escape("]($t)"))
}

Write-Host '--- templates ---'
$dash = Read-TextOrEmpty (Join-Path $SkillDir 'templates/dashboard-mockup.html')
# The brainstorming mockup window serves a file as-is only when it starts with a doctype.
Assert 'the dashboard template starts with a doctype' ($dash -match '^\s*<!doctype html>')
# Opened by double click, so nothing may load from outside the file.
$outside = @([regex]::Matches($dash, '(?:src|href)="([^"]+)"') | ForEach-Object { $_.Groups[1].Value } |
             Where-Object { -not ($_ -match '^(data:|#)') })
Assert 'the dashboard template loads nothing from outside the file' ($outside.Count -eq 0)
Assert 'the dashboard template carries the editable config and a page template' (($dash -match 'id="mockup-config"') -and ($dash -match '<template data-path="/"'))
Assert 'the dashboard template draws the shell from code' ($dash -match 'createRoot')
Write-Host ''
Write-Host ("PASS={0} FAIL={1}" -f $script:Pass, $script:Fail)
if ($script:Fail -ne 0) { exit 1 }
