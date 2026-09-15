#Requires -Version 7.0
# Contract tests for the kw-devops plugin.
#   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tests\test_devops.ps1
#
# deploying-kiwoom-service moved in from a personal copy under ~/.claude/skills
# on 2026-09-14. That copy called its script by that path and with python3;
# neither holds once the skill ships inside a plugin on a Windows PC.

$ErrorActionPreference = 'Stop'
$Repo      = Split-Path -Parent $PSScriptRoot
$PluginDir = Join-Path $Repo 'plugins/kw-devops'
$SkillDir  = Join-Path $PluginDir 'skills/deploying-kiwoom-service'

$script:Pass = 0
$script:Fail = 0
function Assert($label, $cond) {
    if ($cond) { $script:Pass++; Write-Host "PASS  $label" -ForegroundColor Green }
    else       { $script:Fail++; Write-Host "FAIL  $label" -ForegroundColor Red }
}
function Read-JsonOrNull($path) {
    if (Test-Path $path) { return (Get-Content $path -Raw | ConvertFrom-Json) }
    return $null
}

$PluginName = 'kw-devops'
$PluginId   = 'kw-devops@kiwoom-ax'

Write-Host '--- manifests ---'
$pluginJson = Read-JsonOrNull (Join-Path $PluginDir '.claude-plugin/plugin.json')
$mkt        = Read-JsonOrNull (Join-Path $Repo '.claude-plugin/marketplace.json')
$manifest   = Read-JsonOrNull (Join-Path $Repo 'plugins/kw-control-tower/manifest.json')

Assert "plugin.json name is $PluginName" ($pluginJson.name -eq $PluginName)
$entry = $null
if ($mkt -and $mkt.plugins) { $entry = @($mkt.plugins) | Where-Object { $_.name -eq $PluginName } | Select-Object -First 1 }
Assert "the marketplace ships $PluginName" ($null -ne $entry)
Assert 'the plugin source is an in-repo path' ($null -ne $entry -and $entry.source -eq './plugins/kw-devops')
Assert 'both descriptions are the same text' ($null -ne $pluginJson.description -and $null -ne $entry -and $pluginJson.description -eq $entry.description)
Assert 'plugin.json carries no version (commit-based auto update)' ($null -ne $pluginJson -and $null -eq $pluginJson.PSObject.Properties['version'])
Assert "the control tower requires $PluginId" ($null -ne $manifest -and @($manifest.required) -contains $PluginId)

Write-Host '--- skill ---'
$md = Join-Path $SkillDir 'SKILL.md'
$py = Join-Path $SkillDir 'scripts/pick_port.py'
Assert 'SKILL.md ships' (Test-Path $md)
Assert 'pick_port.py ships under scripts/' (Test-Path $py)
$text = if (Test-Path $md) { [IO.File]::ReadAllText($md) } else { '' }
$name = ([regex]::Match($text, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
Assert 'frontmatter name matches the folder' ($name -eq 'deploying-kiwoom-service')

# The body was split so a port question does not load compose templates and log
# tables. A reference file that SKILL.md does not link is never opened.
$refs = @('compose-and-env.md', 'jenkins-logs.md', 'ax-requests.md', 'jenkinsfile.md', 'local-verify.md')
foreach ($ref in $refs) {
    Assert "$ref ships" (Test-Path (Join-Path $SkillDir $ref))
    Assert "SKILL.md links $ref" ($text -match [regex]::Escape("]($ref)"))
}
$refText = @($refs | ForEach-Object { $p = Join-Path $SkillDir $_; if (Test-Path $p) { [IO.File]::ReadAllText($p) } }) -join "`n"
$allText = $text + "`n" + $refText

# The plugin cache path differs per PC and per commit. Claude Code substitutes
# ${CLAUDE_SKILL_DIR} in SKILL.md only; a reference file opened with Read keeps
# the literal text. So every call lives in SKILL.md and goes through it.
Assert 'no skill file points at a personal skills folder' (-not ($allText -match '~/\.claude'))
$calls = [regex]::Matches($text, '(?m)^python\b.*pick_port\.py.*$')
Assert 'every pick_port.py call goes through CLAUDE_SKILL_DIR' ($calls.Count -gt 0 -and @($calls | Where-Object { $_.Value -notmatch '\$\{CLAUDE_SKILL_DIR\}/scripts/pick_port\.py' }).Count -eq 0)
$axCalls = [regex]::Matches($text, '(?m)^powershell\b.*request-ax\.ps1.*$')
Assert 'every request-ax.ps1 call goes through CLAUDE_SKILL_DIR' ($axCalls.Count -gt 0 -and @($axCalls | Where-Object { $_.Value -notmatch '"\$\{CLAUDE_SKILL_DIR\}/scripts/request-ax\.ps1"' }).Count -eq 0)
Assert 'reference files carry no CLAUDE_SKILL_DIR (not substituted there)' (-not ($refText -match 'CLAUDE_SKILL_DIR'))
# The control tower's python3 guard denies python3 on PCs where it is the Store
# redirector, so a python3 line in any skill file would be refused there.
Assert 'no skill file calls python3' (-not ($allText -match '\bpython3\b'))
# The skill carries what a deploy needs, not how each rule was found. Build
# history (dates, measurement notes, how things used to be) goes stale and is
# loaded on every run.
Assert 'skill documents carry no build-history notes' (-not ($allText -match '\b20\d\d-\d\d-\d\d\b|\(실측|실측\)|쓰던 때|섞여 있던'))

# The model copies these examples into a body file, so a broken example is a
# broken mail.
$axDocPath = Join-Path $SkillDir 'ax-requests.md'
$axDoc = if (Test-Path $axDocPath) { [IO.File]::ReadAllText($axDocPath) } else { '' }
$examples = @([regex]::Matches($axDoc, '(?s)```json\r?\n(.*?)```') | ForEach-Object { $_.Groups[1].Value })
$badExamples = @($examples | Where-Object { try { $null = $_ | ConvertFrom-Json; $false } catch { $true } })
Assert 'ax-requests.md example bodies parse as JSON' ($examples.Count -gt 0 -and $badExamples.Count -eq 0)

Write-Host '--- pick_port.py --check ---'
# Offline self-check: band arithmetic and the enum values the DB constraint holds.
$null = & python $py --check 2>&1 | Out-String
Assert 'pick_port.py --check exits 0' ($LASTEXITCODE -eq 0)

# A tool call reads stdout through a pipe. On a Korean Windows PC without
# PYTHONUTF8 that pipe is cp949, which has no en dash or em dash, and the script
# printed both and died after the network work was done. PYTHONIOENCODING forces
# the same encoding on any machine; --check prints the band label.
$env:PYTHONIOENCODING = 'cp949'
try {
    $null = & python $py --check 2>&1 | Out-String
    $cpCode = $LASTEXITCODE
} finally { Remove-Item Env:PYTHONIOENCODING }
Assert 'pick_port.py prints on a cp949 console' ($cpCode -eq 0)

Write-Host '--- request-ax.ps1 ---'
# The script mails AX-team requests through the shared renderer and sender. The
# tests swap both for fakes through two environment variables, so no real mail
# leaves and no shared folder is needed. The child runs in Windows PowerShell
# 5.1 because that is the shell a deploy PC is guaranteed to have.
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ax      = Join-Path $SkillDir 'scripts/request-ax.ps1'
$axText  = if (Test-Path $ax) { [IO.File]::ReadAllText($ax) } else { '' }
$axBytes = if (Test-Path $ax) { [IO.File]::ReadAllBytes($ax) } else { @() }
Assert 'request-ax.ps1 ships under scripts/' (Test-Path $ax)
Assert 'request-ax.ps1 has a UTF-8 BOM (5.1 reads Korean as cp949 otherwise)' ($axBytes.Count -ge 3 -and $axBytes[0] -eq 0xEF -and $axBytes[1] -eq 0xBB -and $axBytes[2] -eq 0xBF)
$Recipient = ([regex]::Match($axText, '(?m)^\$Recipient\s*=\s*''([^'']+)''')).Groups[1].Value
Assert 'request-ax.ps1 names one recipient' ($Recipient -match '^[^@\s]+@[^@\s]+$')
# Two failure paths are hard to provoke from a test; check the code carries them.
Assert 'a failed work-folder delete warns without changing the exit code' ($axText -match '\[경고\] 작업 폴더를 지우지 못했다')
Assert 'work-folder setup and attachment writing both map to exit 7' ([regex]::Matches($axText, '\$script:Stage = 7').Count -ge 2)

$Fake         = Join-Path ([IO.Path]::GetTempPath()) ('kwdevops-test-' + [guid]::NewGuid().ToString('N'))
$FakeRenderer = Join-Path $Fake 'renderer'
$FakeSender   = Join-Path $Fake 'send-mail.ps1'
$Capture      = Join-Path $Fake 'capture'
$ChildTemp    = Join-Path $Fake 'temp'
$Utf8Bom      = New-Object Text.UTF8Encoding $true
$Utf8NoBom    = New-Object Text.UTF8Encoding $false
$null = New-Item -ItemType Directory -Force (Join-Path $FakeRenderer 'formats'), (Join-Path $FakeRenderer 'scripts'), $ChildTemp

[IO.File]::WriteAllText((Join-Path $FakeRenderer 'formats/plain.js'), @'
const fs = require('fs');
const [, , input, out] = process.argv;
const mode = process.env.FAKE_RENDER || '';
if (mode === 'fail') { console.error('fake render failure'); process.exit(1); }
JSON.parse(fs.readFileSync(input, 'utf8'));
const T = require(require('path').join(__dirname, '..', 'lib', 'tokens.js'));
fs.writeFileSync(out, mode === 'empty' ? '' : `<html><body><table><tr><td style="font-family:${T.SERIF};">ok</td></tr></table></body></html>`);
'@, $Utf8NoBom)
[IO.File]::WriteAllText((Join-Path $FakeRenderer 'scripts/verify-outlook.js'), @'
process.exit(process.env.FAKE_VERIFY === 'fail' ? 1 : 0);
'@, $Utf8NoBom)
# The real renderer keeps its fonts in lib/tokens.js. The script swaps SERIF for SANS in its copy.
$null = New-Item -ItemType Directory -Force (Join-Path $FakeRenderer 'lib')
[IO.File]::WriteAllText((Join-Path $FakeRenderer 'lib/tokens.js'), @'
const SANS = "'Malgun Gothic',sans-serif";
const SERIF = "Georgia,serif";
module.exports = { SANS, SERIF };
'@, $Utf8NoBom)
$NoSerifRenderer = Join-Path $Fake 'renderer-noserif'
Copy-Item -Recurse $FakeRenderer $NoSerifRenderer
[IO.File]::WriteAllText((Join-Path $NoSerifRenderer 'lib/tokens.js'), @'
const SANS = "'Malgun Gothic',sans-serif";
module.exports = { SANS, SERIF: SANS };
'@, $Utf8NoBom)
[IO.File]::WriteAllText($FakeSender, @'
param([string[]]$To, [string]$Subject, [string]$HtmlPath, [string[]]$Attach = @())
if ($env:FAKE_SEND_THROW) { throw 'fake smtp failure' }
$null = New-Item -ItemType Directory -Force $env:FAKE_CAPTURE
@{ To = @($To); Subject = $Subject } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $env:FAKE_CAPTURE 'call.json')
Copy-Item -LiteralPath $HtmlPath (Join-Path $env:FAKE_CAPTURE 'body.html')
foreach ($a in $Attach) { Copy-Item -LiteralPath $a (Join-Path $env:FAKE_CAPTURE 'attach.env') }
'@, $Utf8Bom)

$Body    = Join-Path $Fake 'body.json'
$NotJson = Join-Path $Fake 'not-json.json'
$EnvOk   = Join-Path $Fake 'ok.env'
$EnvOpen = Join-Path $Fake 'open-quote.env'
$Blocker = Join-Path $Fake 'blocker.txt'
[IO.File]::WriteAllText($Body, '{"blocks":[{"type":"p","text":"시험 본문"}]}', $Utf8NoBom)
[IO.File]::WriteAllText($NotJson, 'this is not json', $Utf8NoBom)
[IO.File]::WriteAllText($Blocker, 'a file, so nothing can be created beneath it', $Utf8NoBom)
$envLines = @('# 주석 줄', 'A_KEY=alpha-secret', 'API_KEY=first-secret', 'export B_KEY = "값 1"', '', 'API_KEY=second-secret', 'UNRELATED=unrelated-secret', 'EMPTY_KEY=')
[IO.File]::WriteAllText($EnvOk, (($envLines -join "`r`n") + "`r`n"), $Utf8NoBom)
[IO.File]::WriteAllText($EnvOpen, "Q_KEY=`"open-secret`r`n", $Utf8NoBom)

$PsExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
function Invoke-Ax([hashtable]$EnvOverride, [string[]]$ArgList) {
    $ErrorActionPreference = 'Continue'   # 5.1 turns a child's stderr into a terminating error under Stop
    $old = @{}
    foreach ($k in $EnvOverride.Keys) { $old[$k] = [Environment]::GetEnvironmentVariable($k); Set-Item "Env:$k" $EnvOverride[$k] }
    try {
        # A seam that points anywhere but the test folder would send real mail.
        foreach ($v in @($env:KW_DEVOPS_MAIL_RENDERER, $env:KW_DEVOPS_MAIL_SENDER)) {
            if (-not $v -or -not $v.StartsWith($Fake)) { Write-Host "STOP  a mail seam points outside the test folder: '$v'" -ForegroundColor Red; exit 2 }
        }
        if (Test-Path $Capture) { Remove-Item $Capture -Recurse -Force }
        $out = & $PsExe -NoProfile -ExecutionPolicy Bypass -File $ax @ArgList 2>&1 | Out-String
        return [pscustomobject]@{ Code = $LASTEXITCODE; Out = $out; Sent = (Test-Path (Join-Path $Capture 'call.json')) }
    } finally {
        foreach ($k in $EnvOverride.Keys) {
            if ($null -eq $old[$k]) { Remove-Item "Env:$k" -ErrorAction SilentlyContinue } else { Set-Item "Env:$k" $old[$k] }
        }
    }
}

$saved = @{ R = $env:KW_DEVOPS_MAIL_RENDERER; S = $env:KW_DEVOPS_MAIL_SENDER; C = $env:FAKE_CAPTURE; T = $env:TEMP }
$env:KW_DEVOPS_MAIL_RENDERER = $FakeRenderer
$env:KW_DEVOPS_MAIL_SENDER   = $FakeSender
$env:FAKE_CAPTURE            = $Capture
$env:TEMP                    = $ChildTemp
$okArgs = @('-Subject', '시험 제목', '-BodyPath', $Body)
try {
    Assert 'blank -Subject exits 2'          ((Invoke-Ax @{} @('-Subject', ' ', '-BodyPath', $Body)).Code -eq 2)
    Assert 'missing -BodyPath file exits 2'  ((Invoke-Ax @{} @('-Subject', 'x', '-BodyPath', (Join-Path $Fake 'none.json'))).Code -eq 2)
    Assert 'a body that is not JSON exits 2' ((Invoke-Ax @{} @('-Subject', 'x', '-BodyPath', $NotJson)).Code -eq 2)
    Assert '-EnvSource alone exits 2'        ((Invoke-Ax @{} ($okArgs + @('-EnvSource', $EnvOk))).Code -eq 2)
    Assert '-EnvKeys alone exits 2'          ((Invoke-Ax @{} ($okArgs + @('-EnvKeys', 'A_KEY'))).Code -eq 2)
    Assert 'missing -EnvSource file exits 2' ((Invoke-Ax @{} ($okArgs + @('-EnvSource', (Join-Path $Fake 'none.env'), '-EnvKeys', 'A_KEY'))).Code -eq 2)

    $h = [IO.File]::Open($EnvOk, 'Open', 'ReadWrite', 'None')
    try { $r = Invoke-Ax @{} ($okArgs + @('-EnvSource', $EnvOk, '-EnvKeys', 'A_KEY')) } finally { $h.Dispose() }
    Assert 'an -EnvSource locked by another process exits 2' ($r.Code -eq 2)

    $r = Invoke-Ax @{} ($okArgs + @('-EnvSource', $EnvOpen, '-EnvKeys', 'Q_KEY'))
    Assert 'an unclosed quote exits 2 and names the key' ($r.Code -eq 2 -and $r.Out -match 'Q_KEY' -and $r.Out -notmatch 'open-secret')

    $noNode = (($env:Path -split ';') | Where-Object { $_ -and -not (Test-Path (Join-Path $_ 'node.exe')) }) -join ';'
    Assert 'no node on PATH exits 3'   ((Invoke-Ax @{ Path = $noNode } $okArgs).Code -eq 3)
    Assert 'a missing renderer exits 3' ((Invoke-Ax @{ KW_DEVOPS_MAIL_RENDERER = (Join-Path $Fake 'no-renderer') } $okArgs).Code -eq 3)
    Assert 'a missing sender exits 3'   ((Invoke-Ax @{ KW_DEVOPS_MAIL_SENDER = (Join-Path $Fake 'no-sender.ps1') } $okArgs).Code -eq 3)
    Assert 'a failing render exits 4'   ((Invoke-Ax @{ FAKE_RENDER = 'fail' } $okArgs).Code -eq 4)
    Assert 'an empty render exits 4'    ((Invoke-Ax @{ FAKE_RENDER = 'empty' } $okArgs).Code -eq 4)
    $r = Invoke-Ax @{ KW_DEVOPS_MAIL_RENDERER = $NoSerifRenderer } $okArgs
    Assert 'a renderer without a SERIF line exits 4 and sends nothing' ($r.Code -eq 4 -and -not $r.Sent)
    $r = Invoke-Ax @{ FAKE_VERIFY = 'fail' } $okArgs
    Assert 'a failing Outlook check exits 5 and sends nothing' ($r.Code -eq 5 -and -not $r.Sent)
    Assert 'a sender exception exits 6' ((Invoke-Ax @{ FAKE_SEND_THROW = '1' } $okArgs).Code -eq 6)
    Assert 'an unwritable TEMP exits 7' ((Invoke-Ax @{ TEMP = (Join-Path $Blocker 'sub') } $okArgs).Code -eq 7)
    $r = Invoke-Ax @{} ($okArgs + @('-EnvSource', $EnvOk, '-EnvKeys', 'NOPE_KEY'))
    Assert 'no requested key in the source exits 8 and sends nothing' ($r.Code -eq 8 -and -not $r.Sent)

    $locked = Join-Path $ChildTemp 'kwdevops-mail-locked'
    $null = New-Item -ItemType Directory -Force $locked
    $h = [IO.File]::Open((Join-Path $locked 'held.txt'), 'Create', 'ReadWrite', 'None')
    try {
        (Get-Item $locked).LastWriteTime = (Get-Date).AddHours(-2)
        $r = Invoke-Ax @{} $okArgs
    } finally { $h.Dispose(); Remove-Item $locked -Recurse -Force }
    Assert 'an old work folder that cannot be deleted only warns' ($r.Code -eq 0 -and $r.Out -match 'kwdevops-mail-locked')

    $old = Join-Path $ChildTemp 'kwdevops-mail-old'
    $null = New-Item -ItemType Directory -Force $old
    (Get-Item $old).LastWriteTime = (Get-Date).AddHours(-2)
    $r = Invoke-Ax @{} ($okArgs + @('-EnvSource', $EnvOk, '-EnvKeys', 'A_KEY,api_key,B_KEY,EMPTY_KEY,MISSING_KEY'))
    Assert 'a full request exits 0' ($r.Code -eq 0)
    $call = if ($r.Sent) { Get-Content -Raw -Encoding UTF8 (Join-Path $Capture 'call.json') | ConvertFrom-Json } else { $null }
    Assert 'the sender got the recipient constant and the subject' ($null -ne $call -and (@($call.To) -join ',') -eq $Recipient -and $call.Subject -eq '시험 제목')
    $bodyPath = Join-Path $Capture 'body.html'
    $bodyHtml = if (Test-Path $bodyPath) { [IO.File]::ReadAllText($bodyPath) } else { '' }
    Assert 'the rendered body uses the Gothic stack in place of the serif stack' ($bodyHtml -match 'Malgun Gothic' -and $bodyHtml -notmatch 'Georgia')
    $attPath  = Join-Path $Capture 'attach.env'
    $attBytes = if (Test-Path $attPath) { [IO.File]::ReadAllBytes($attPath) } else { @() }
    $attText  = if (Test-Path $attPath) { [IO.File]::ReadAllText($attPath) } else { '' }
    Assert 'the attachment holds only the requested keys, last value wins, key case from the source' ($attText -ceq "A_KEY=alpha-secret`nAPI_KEY=second-secret`nB_KEY=`"값 1`"`n")
    Assert 'the attachment has no BOM and no CR' ($attBytes.Count -gt 3 -and -not ($attBytes[0] -eq 0xEF -and $attBytes[1] -eq 0xBB) -and -not ($attBytes -contains 13))
    Assert 'keys left out are named' ($r.Out -match 'EMPTY_KEY' -and $r.Out -match 'MISSING_KEY')
    $leaked = @('alpha-secret', 'first-secret', 'second-secret', '값 1', 'unrelated-secret') | Where-Object { $r.Out -match [regex]::Escape($_) }
    Assert 'no value is printed' (@($leaked).Count -eq 0)
    Assert 'no work folder is left behind and the old one is gone' (@(Get-ChildItem $ChildTemp -Directory -Filter 'kwdevops-mail-*').Count -eq 0)
} finally {
    $env:KW_DEVOPS_MAIL_RENDERER = $saved.R
    $env:KW_DEVOPS_MAIL_SENDER   = $saved.S
    $env:FAKE_CAPTURE            = $saved.C
    $env:TEMP                    = $saved.T
    Remove-Item $Fake -Recurse -Force -ErrorAction SilentlyContinue
}

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
