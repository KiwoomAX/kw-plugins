#Requires -Version 7.0
# Contract tests for the kw-github plugin.
#   pwsh -NoProfile -ExecutionPolicy Bypass -File .\tests\test_github.ps1
#
# Only the core contracts live here: registration, the scripts the skills call,
# ASCII JSON output, one commit -> upload run against a local bare remote, the
# guard, and that the session start hook never pushes. The full pytest suite
# (timeouts, push races, fake gh responses) stays on the maintainer's PC because
# it swaps Python internals that PowerShell cannot reach (decided 2026-10-21).

$ErrorActionPreference = 'Stop'
$Repo      = Split-Path -Parent $PSScriptRoot
$PluginDir = Join-Path $Repo 'plugins/kw-github'
$Scripts   = Join-Path $PluginDir 'scripts'
$Hooks     = Join-Path $PluginDir 'hooks'

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
# Runs a plugin script and returns its stdout. The scripts print ASCII-only JSON.
function Invoke-Py([string[]]$ArgList, [string]$StdIn = $null, [string]$Cwd = $null) {
    $psi = [Diagnostics.ProcessStartInfo]::new('python')
    foreach ($a in $ArgList) { $psi.ArgumentList.Add($a) }
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.RedirectStandardInput = $true
    $psi.StandardOutputEncoding = [Text.Encoding]::UTF8
    $psi.StandardInputEncoding = [Text.UTF8Encoding]::new($false)
    if ($Cwd) { $psi.WorkingDirectory = $Cwd }
    $p = [Diagnostics.Process]::Start($psi)
    if ($StdIn) { $p.StandardInput.Write($StdIn) }
    $p.StandardInput.Close()
    $out = $p.StandardOutput.ReadToEnd()
    $null = $p.StandardError.ReadToEnd()
    $p.WaitForExit()
    return $out
}
function Invoke-Git([string]$Dir, [string[]]$ArgList) {
    $out = & git -C $Dir @ArgList 2>&1
    if ($LASTEXITCODE -ne 0) { throw "git $($ArgList -join ' ') failed: $out" }
    return ($out -join "`n")
}

$PluginName = 'kw-github'
$PluginId   = 'kw-github@kiwoom-ax'

Write-Host '--- manifests ---'
$pluginJson = Read-JsonOrNull (Join-Path $PluginDir '.claude-plugin/plugin.json')
$mkt        = Read-JsonOrNull (Join-Path $Repo '.claude-plugin/marketplace.json')
$manifest   = Read-JsonOrNull (Join-Path $Repo 'plugins/kw-control-tower/manifest.json')

Assert "plugin.json name is $PluginName" ($pluginJson.name -eq $PluginName)
$entry = $null
if ($mkt -and $mkt.plugins) { $entry = @($mkt.plugins) | Where-Object { $_.name -eq $PluginName } | Select-Object -First 1 }
Assert "the marketplace ships $PluginName" ($null -ne $entry)
Assert 'the plugin source is an in-repo path' ($null -ne $entry -and $entry.source -eq './plugins/kw-github')
Assert 'both descriptions are the same text' ($null -ne $pluginJson.description -and $null -ne $entry -and $pluginJson.description -eq $entry.description)
Assert 'plugin.json carries no version (commit-based auto update)' ($null -ne $pluginJson -and $null -eq $pluginJson.PSObject.Properties['version'])
# Required: every PC on this list is a developer PC, and the plugin keeps company code from reaching GitHub unchecked (decided 2026-10-22).
Assert "the control tower requires $PluginId" ($null -ne $manifest -and @($manifest.required) -contains $PluginId)
Assert "the control tower does not also suggest $PluginId" ($null -ne $manifest -and @($manifest.suggested) -notcontains $PluginId)

# The always-loaded company instructions point Claude at the two skills, so they trigger in any folder.
$axTemplate = Read-TextOrEmpty (Join-Path $Repo 'plugins/kw-control-tower/templates/claude-md-ko.md')
Assert 'the company instructions name both kw-github skills' (($axTemplate -match 'kw-github:starting-feature-repo') -and ($axTemplate -match 'kw-github:saving-work'))

Write-Host '--- hooks ---'
$hooksJson = Read-JsonOrNull (Join-Path $Hooks 'hooks.json')
$start = @($hooksJson.hooks.SessionStart)
Assert 'the session start hook runs on startup and resume' ($start.Count -eq 1 -and $start[0].matcher -eq 'startup|resume')
Assert 'the guard watches both shell tools' (@($hooksJson.hooks.PreToolUse)[0].matcher -eq 'Bash|PowerShell')
Assert 'a session end hook clears this session mark' ($null -ne $hooksJson.hooks.SessionEnd)
$commands = @($hooksJson.hooks.PSObject.Properties.Value | ForEach-Object { $_.hooks } | ForEach-Object { $_.command })
foreach ($c in $commands) {
    $rel = ([regex]::Match($c, '\$\{CLAUDE_PLUGIN_ROOT\}/([^"]+)')).Groups[1].Value
    Assert "hook runs python, not python3, on an existing file: $rel" (
        $c.StartsWith('python ') -and -not ($c -match '\bpython3\b') -and $rel -and (Test-Path (Join-Path $PluginDir $rel)))
}

Write-Host '--- skills ---'
foreach ($skill in @('starting-feature-repo', 'saving-work')) {
    $text = Read-TextOrEmpty (Join-Path $PluginDir "skills/$skill/SKILL.md")
    $name = ([regex]::Match($text, '(?m)^name:\s*(\S+)\s*$')).Groups[1].Value
    Assert "$skill frontmatter name matches the folder" ($name -eq $skill)
    Assert "$skill does not call python3" (-not ($text -match '\bpython3\b'))
    $called = @([regex]::Matches($text, '\$\{CLAUDE_PLUGIN_ROOT\}/scripts/([\w.]+\.py)') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
    foreach ($f in $called) { Assert "$skill calls a script that ships: $f" (Test-Path (Join-Path $Scripts $f)) }
}
$saving = Read-TextOrEmpty (Join-Path $PluginDir 'skills/saving-work/SKILL.md')
# The push question is the sentence the user fixed; everything else in the skill may be reworded.
Assert 'saving-work asks before every push with the fixed question' ($saving -match [regex]::Escape('지금까지 작업을 GitHub에 올릴까요? 올리면 회사 GitHub(KiwoomAX)에 저장됩니다.'))
$starting = Read-TextOrEmpty (Join-Path $PluginDir 'skills/starting-feature-repo/SKILL.md')
Assert 'starting-feature-repo creates nothing on GitHub' (-not ($starting -match 'gh repo create|gh issue create'))

Write-Host '--- ASCII JSON output ---'
# PowerShell set to cp949 garbles UTF-8 Korean held in a variable, so the scripts print \uXXXX only.
$plain = Join-Path ([IO.Path]::GetTempPath()) ("kwgh-한글-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $plain | Out-Null
try {
    foreach ($cmd in @(@('commit', '--message', '저장', '--branch', 'feat/x'), @('prepare-upload'), @('upload', '--task', '1', '--title', '제목'), @('review-upload'))) {
        $out = Invoke-Py (@((Join-Path $Scripts 'save_work.py'), $cmd[0], '--repo', $plain) + @($cmd | Select-Object -Skip 1))
        $json = $null; try { $json = $out | ConvertFrom-Json } catch { }
        Assert "save_work $($cmd[0]) prints ASCII JSON" ($out.Trim() -and ($out -cmatch '^[\x00-\x7F]*$') -and $null -ne $json -and $json.status)
    }
} finally { Remove-Item -LiteralPath $plain -Recurse -Force -ErrorAction SilentlyContinue }

Write-Host '--- commit and upload against a local remote ---'
$work = Join-Path ([IO.Path]::GetTempPath()) ("kwgh-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
$repoDir = Join-Path $work 'repo'
$remote  = Join-Path $work 'remote.git'
New-Item -ItemType Directory -Path $repoDir | Out-Null
try {
    $null = Invoke-Git $work @('init', '-q', '--bare', '-b', 'main', $remote)
    $null = Invoke-Git $repoDir @('init', '-q', '-b', 'main')
    foreach ($kv in @(@('user.email', 't@example.com'), @('user.name', 't'), @('core.autocrlf', 'false'))) { $null = Invoke-Git $repoDir (@('config') + $kv) }
    # origin keeps a real GitHub address; insteadOf sends fetch and push to the local bare remote.
    $url = 'https://github.com/KiwoomAX/kwgh-test.git'
    $null = Invoke-Git $repoDir @('remote', 'add', 'origin', $url)
    $null = Invoke-Git $repoDir @('config', "url.$($remote.Replace('\', '/')).insteadOf", $url)
    [IO.File]::WriteAllText((Join-Path $repoDir '.kiwoom-feature'), "name=kwgh-test`ntitle=시험`nissue=1`n")
    [IO.File]::WriteAllText((Join-Path $repoDir 'a.py'), "x = 1`n")
    [IO.File]::WriteAllText((Join-Path $repoDir 'nav.csv'), "d,v`n1,2`n")

    $first = Invoke-Py @((Join-Path $Scripts 'save_work.py'), 'commit', '--repo', $repoDir, '--message', '작업 폴더 준비') | ConvertFrom-Json
    Assert 'the first commit lands on main' ($first.status -eq 'committed' -and $first.branch -eq 'main')
    Assert 'a data file is left out of the commit' (-not ((Invoke-Git $repoDir @('ls-files')) -match 'nav\.csv'))

    [IO.File]::WriteAllText((Join-Path $repoDir 'b.py'), "y = 2`n")
    $second = Invoke-Py @((Join-Path $Scripts 'save_work.py'), 'commit', '--repo', $repoDir, '--message', '화면 추가', '--branch', 'feat/x') | ConvertFrom-Json
    Assert 'later commits go to a work branch' ($second.status -eq 'committed' -and $second.branch -eq 'feat/x' -and $second.unpushed)
    Assert 'commit does not push' (-not ((Invoke-Git $remote @('for-each-ref', '--format=%(refname)')) -match 'refs/heads'))

    $up = Invoke-Py @((Join-Path $Scripts 'save_work.py'), 'upload', '--repo', $repoDir, '--task', '7', '--title', '화면 추가') | ConvertFrom-Json
    Assert 'upload finishes' ($up.status -eq 'uploaded')
    $parents = (Invoke-Git $remote @('log', '-1', '--format=%P', 'main')).Trim().Split(' ')
    $body = Invoke-Git $remote @('log', '-1', '--format=%B', 'main')
    Assert 'main gets a --no-ff merge commit' ($parents.Count -eq 2)
    Assert 'the merge commit closes the task issue and links the feature issue' ($body -match '(?m)^closes #7$' -and $body -match '(?m)^#1$')
    Assert 'the merged work branch is deleted on both sides' (
        -not ((Invoke-Git $remote @('branch', '--list')) -match 'feat/x') -and -not ((Invoke-Git $repoDir @('branch', '--list')) -match 'feat/x'))

    Write-Host '--- guard ---'
    $deny = Invoke-Py @((Join-Path $Hooks 'git_guard.py')) (@{ tool_name = 'Bash'; cwd = $repoDir; session_id = 'kwgh-test'; tool_input = @{ command = 'git push origin main' } } | ConvertTo-Json -Compress)
    Assert 'the guard denies a direct git push in a feature folder' ($deny -match '"deny"')
    $allow = Invoke-Py @((Join-Path $Hooks 'git_guard.py')) (@{ tool_name = 'Bash'; cwd = $repoDir; session_id = 'kwgh-test'; tool_input = @{ command = 'git switch -c feat/y' } } | ConvertTo-Json -Compress)
    Assert 'the guard lets branch commands through' (-not $allow.Trim())

    Write-Host '--- session start ---'
    $before = (Invoke-Git $remote @('rev-parse', 'main')).Trim()
    [IO.File]::WriteAllText((Join-Path $repoDir 'c.py'), "z = 3`n")
    $ctx = Invoke-Py @((Join-Path $Hooks 'session_start.py')) (@{ cwd = $repoDir; session_id = 'kwgh-test' } | ConvertTo-Json -Compress)
    $context = ($ctx | ConvertFrom-Json).hookSpecificOutput.additionalContext
    Assert 'the session start hook commits leftovers and asks before uploading' ($context -match [regex]::Escape('「push 질문」 절'))
    Assert 'the session start hook never pushes' ((Invoke-Git $remote @('rev-parse', 'main')).Trim() -eq $before)
} finally { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }

Write-Host ''
Write-Host ("PASS={0} FAIL={1}" -f $script:Pass, $script:Fail)
if ($script:Fail -gt 0) { exit 1 }
