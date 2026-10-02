# git 커밋 명의를 GitHub 계정에 맞춘다. 세션 시작 알림이 명의를 확인하라고 할 때 클로드가 실행한다.
#
#   pwsh -NoProfile -File git-identity.ps1                                    제안만 낸다. 아무것도 안 바꾼다
#   pwsh -NoProfile -File git-identity.ps1 -Apply -Name <이름> -Email <메일>   사용자가 승인한 값을 적는다
#
# 제안과 적용을 나눈 것은 그 사이에 사용자 승인을 두기 위해서다. 명의가 비어 있으면 클로드가
# 대화 맥락에 있는 클로드 계정 메일로 채우는데, 클로드 계정을 여럿이 같이 쓰는 PC 에서는 그것이
# 남의 메일이다. 그렇게 직원의 커밋이 AX 팀 직원 이름으로 올라갔다(이슈 #28).
#
# 제안하는 메일은 GitHub 계정에 등록되고 인증된 메일 가운데 사내 메일이다. 인증된 메일이어야
# GitHub 이 그 커밋을 그 계정으로 연결한다. 메일 목록은 user:email 권한이 있어야 읽히는데
# gh auth login 의 기본 권한에는 없다. 없으면 권한을 더하는 명령을 알리고 멈춘다.
#
# 적는 곳은 ~/.gitconfig 하나로 고정한다. 세션 시작 알림이 git 을 실행하지 않고 그 파일을 직접
# 읽어 승인 여부를 판정하므로, git config --global 이 다른 위치(XDG)에 적으면 안내가 끝나지 않는다.
#
# 종료 코드는 0 이 제안을 냈거나 적은 것, 1 이 실패, 2 가 로그인 필요, 3 이 메일 읽기 권한 필요다.

param(
    [switch]$Apply,
    [string]$Name,
    [string]$Email
)

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'
# gh 가 내는 이름이 한글이면 콘솔 코드페이지로 읽혀 깨진다. 알림 훅과 같은 이유로 UTF-8 로 맞춘다.
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$corpDomain  = '@kiwoomam.com'
$approvedKey = 'kw-control-tower.approvedEmail'
$gitConfig   = Join-Path $env:USERPROFILE '.gitconfig'
# 알림 훅(session-check.ps1)에도 같은 명령이 있다. 글자 그대로 같아야 한다. 왜 페이지를 먼저
# 여는지와 왜 user:email 을 받는지는 그 훅의 주석에 있다.
$loginCommand = 'start https://github.com/login/device; gh auth login --web --git-protocol https --skip-ssh-key --clipboard --scopes user:email'
$scopeCommand = 'start https://github.com/login/device; gh auth refresh -h github.com -s user:email --clipboard'

function Select-CommitEmail($Emails, [string]$Domain) {
    # 인증된 메일만 본다. 사내 메일이 있으면 그중 주 메일을, 주 메일이 아니면 첫째를 고른다.
    # 사내 메일이 없으면 주 메일을 고른다. 고를 것이 없으면 $null 이다.
    $verified = @($Emails | Where-Object { $_.verified -eq $true })
    $corp = @($verified | Where-Object { "$($_.email)".ToLowerInvariant().EndsWith($Domain.ToLowerInvariant()) })
    $pick = @($corp | Where-Object { $_.primary -eq $true }) + $corp + @($verified | Where-Object { $_.primary -eq $true })
    if ($pick.Count -eq 0) { return $null }
    return $pick[0].email
}

function Invoke-Native([string]$Exe, [string[]]$ArgList) {
    # 네이티브 명령의 표준 오류를 출력에 합쳐 돌려준다. 이 범위에서만 Stop 을 풀어, 표준 오류
    # 한 줄이 예외로 바뀌어 종료 코드를 보기 전에 스크립트가 죽지 않게 한다.
    $ErrorActionPreference = 'Continue'
    $out = & $Exe @ArgList 2>&1 | ForEach-Object { "$_" }
    return @{ Code = $LASTEXITCODE; Text = ($out -join "`n") }
}

function Get-GitValue([string]$Key) {
    $r = Invoke-Native $script:Git @('config', '--file', $gitConfig, '--get', $Key)
    if ($r.Code -ne 0) { return $null }
    return $r.Text.Trim()
}

function Set-GitValue([string]$Key, [string]$Value) {
    $r = Invoke-Native $script:Git @('config', '--file', $gitConfig, $Key, $Value)
    if ($r.Code -ne 0) { throw "git config 실패: $Key ($gitConfig) — $($r.Text)" }
}

$script:Git = (Get-Command git -ErrorAction SilentlyContinue).Source
if (-not $script:Git) { throw 'git 없음: PATH 에서 git 을 찾지 못함 — 설치기를 다시 실행해야 함' }

if ($Apply) {
    # 승인받은 값을 그대로 적는다. 승인은 사용자가 했으므로 GitHub 계정과 다시 견주지 않는다.
    if ([string]::IsNullOrWhiteSpace($Name)) { throw '이름 없음: -Name 이 비어 있음 — 사용자가 승인한 이름을 넘겨야 함' }
    if ($Email -notmatch '^[^@\s]+@[^@\s]+\.[^@\s]+$') { throw "메일 형식 아님: -Email '$Email' — 사용자가 승인한 메일을 넘겨야 함" }
    Set-GitValue 'user.name' $Name
    Set-GitValue 'user.email' $Email
    Set-GitValue $approvedKey $Email
    Write-Output "git 커밋 명의를 적었습니다: user.name = $Name, user.email = $Email ($gitConfig)"
    exit 0
}

$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) { throw 'gh 없음: PATH 에서 GitHub CLI 를 찾지 못함 — 설치기를 다시 실행해야 함' }

$user = Invoke-Native $gh @('api', 'user')
if ($user.Code -ne 0) {
    Write-Output 'GitHub 에 로그인되어 있지 않습니다. 다음을 실행하고 열리는 페이지에 Ctrl+V 로 코드를 붙여 넣은 뒤 이 스크립트를 다시 실행하십시오.'
    Write-Output "  $loginCommand"
    Write-Output "gh 의 응답: $($user.Text)"
    exit 2
}
$account = $user.Text | ConvertFrom-Json

$emails = Invoke-Native $gh @('api', 'user/emails')
if ($emails.Code -ne 0) {
    Write-Output 'GitHub 계정의 메일 목록을 읽을 권한이 없습니다. 다음을 실행하고 열리는 페이지에 Ctrl+V 로 코드를 붙여 넣은 뒤 이 스크립트를 다시 실행하십시오.'
    Write-Output "  $scopeCommand"
    Write-Output "gh 의 응답: $($emails.Text)"
    exit 3
}
$proposedEmail = Select-CommitEmail ($emails.Text | ConvertFrom-Json) $corpDomain
if (-not $proposedEmail) { throw "인증된 메일 없음: GitHub 계정 $($account.login) — GitHub 설정의 Emails 에서 메일 인증이 필요함" }
$proposedName = if ($account.name) { $account.name } else { $account.login }

$curName     = Get-GitValue 'user.name'
$curEmail    = Get-GitValue 'user.email'
$curApproved = Get-GitValue $approvedKey
$show = { param($v) if ($v) { $v } else { '(비어 있음)' } }

if (($curName -eq $proposedName) -and ($curEmail -eq $proposedEmail) -and ($curApproved -eq $curEmail)) {
    Write-Output "git 커밋 명의가 이미 GitHub 계정($($account.login))과 같고 승인되어 있습니다. 바꿀 것이 없습니다."
    exit 0
}

Write-Output "지금 git 커밋 명의 ($gitConfig)"
Write-Output "  user.name  = $(& $show $curName)"
Write-Output "  user.email = $(& $show $curEmail)"
Write-Output "GitHub 계정($($account.login))에 맞춘 제안"
Write-Output "  user.name  = $proposedName"
Write-Output "  user.email = $proposedEmail"
if (-not $account.name) { Write-Output '  GitHub 프로필에 이름이 없어 계정 이름을 제안합니다.' }
Write-Output '사용자가 승인하면 아래를 실행한다. 사용자가 다른 값을 고르면 그 값으로 바꿔 실행한다.'
Write-Output "  pwsh -NoProfile -File `"$PSCommandPath`" -Apply -Name `"$proposedName`" -Email `"$proposedEmail`""
exit 0
