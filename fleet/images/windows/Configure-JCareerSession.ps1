[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^https://[A-Za-z0-9.-]+(?:\:[0-9]{1,5})?(?:/.*)?$')]
    [string]$PreviewUrl,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{64}$')]
    [string]$ApprovedPreviewUrlSha256,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^SESSION-[A-Z0-9_-]{8,64}$')]
    [string]$SessionRef,

    [Parameter(Mandatory = $true)]
    [ValidateSet('WIN-01', 'WIN-02', 'WIN-03')]
    [string]$EndpointRef,

    [Parameter(Mandatory = $true)]
    [string]$ExpiresAt
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-Sha256Text {
    param([Parameter(Mandatory = $true)][string]$Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $bytes = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)) }
    finally { $sha.Dispose() }
    return -join ($bytes | ForEach-Object { $_.ToString('x2') })
}

$parsedPreview = [uri]$PreviewUrl
if (
    $parsedPreview.Scheme -ne 'https' -or
    $parsedPreview.UserInfo -or
    $parsedPreview.Query -or
    $parsedPreview.Fragment
) {
    throw 'Preview URL must be credential-free HTTPS without user info, query, or fragment.'
}
$previewHash = Get-Sha256Text $PreviewUrl
if ($previewHash -ne $ApprovedPreviewUrlSha256) {
    throw 'Preview URL does not match the approved SHA-256 binding.'
}
if ($PreviewUrl -match '[\s`"]') {
    throw 'Preview URL contains characters that are unsafe for the Edge shortcut.'
}
try { $expiry = [DateTimeOffset]::Parse($ExpiresAt) }
catch { throw 'Session expiry must be a timezone-aware ISO-8601 value.' }
$now = [DateTimeOffset]::UtcNow
if ($expiry.Offset -ne [TimeSpan]::Zero) {
    throw 'Session expiry must use UTC.'
}
if ($expiry -le $now.AddMinutes(15) -or $expiry -gt $now.AddHours(8)) {
    throw 'Session expiry must be at least 15 minutes ahead and no more than eight hours ahead.'
}

$root = 'C:\ProgramData\JCareerLab'
$desktop = [Environment]::GetFolderPath('CommonDesktopDirectory')
$cleanupScript = Join-Path $root 'Remove-JCareerSession.ps1'
$sessionFile = Join-Path $root 'session.json'
if (-not (Test-Path -LiteralPath (Join-Path $root 'image-manifest.json'))) {
    throw 'J-Career image contract is not installed.'
}
if (-not (Test-Path -LiteralPath $cleanupScript)) {
    throw 'J-Career session cleanup contract is not installed.'
}
if (Test-Path -LiteralPath $sessionFile) {
    $existingSession = Get-Content -LiteralPath $sessionFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if (
        [string]$existingSession.session_ref -ne $SessionRef -or
        [string]$existingSession.endpoint_ref -ne $EndpointRef
    ) {
        throw 'A different consultant session must be cleaned before reconfiguration.'
    }
}

$edgeCandidates = @(
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
)
$edge = @($edgeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -Unique)
if ($edge.Count -lt 1) {
    throw 'Microsoft Edge is unavailable.'
}
$edgeSignature = Get-AuthenticodeSignature -LiteralPath $edge[0]
if (
    $edgeSignature.Status -ne 'Valid' -or
    $null -eq $edgeSignature.SignerCertificate -or
    [string]$edgeSignature.SignerCertificate.Subject -notmatch '(^|,\s*)O=Microsoft Corporation(,|$)'
) {
    throw 'Microsoft Edge is not signed by the expected Microsoft publisher.'
}

$profilesRoot = Join-Path $root 'EdgeProfiles'
$edgeProfile = Join-Path $profilesRoot $SessionRef
[IO.Directory]::CreateDirectory($edgeProfile) | Out-Null
$shortcut = Join-Path $desktop 'J-Career approved preview.lnk'
$legacyShortcut = Join-Path $desktop 'J-Career approved preview.url'
if (Test-Path -LiteralPath $legacyShortcut) {
    Remove-Item -LiteralPath $legacyShortcut -Force
}
$shell = New-Object -ComObject WScript.Shell
try {
    $edgeShortcut = $shell.CreateShortcut($shortcut)
    $edgeShortcut.TargetPath = $edge[0]
    $edgeShortcut.Arguments = "--user-data-dir=`"$edgeProfile`" --no-first-run --new-window `"$PreviewUrl`""
    $edgeShortcut.WorkingDirectory = Split-Path -Parent $edge[0]
    $edgeShortcut.IconLocation = "$($edge[0]),0"
    $edgeShortcut.Description = 'J-Career approved synthetic preview'
    $edgeShortcut.Save()
}
finally {
    if ($null -ne $shell) {
        [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) | Out-Null
    }
}

[ordered]@{
    schema_version = 'jcareer-consultant-session-v2'
    session_ref = $SessionRef
    endpoint_ref = $EndpointRef
    preview_origin = $parsedPreview.GetLeftPart([System.UriPartial]::Authority)
    preview_url_sha256 = $previewHash
    browser = 'MICROSOFT_EDGE_EXPLICIT_SHORTCUT'
    browser_profile_path_sha256 = Get-Sha256Text $edgeProfile
    configured_at = $now.ToString('o')
    expires_at = $expiry.ToUniversalTime().ToString('o')
    credentials_recorded = $false
} | ConvertTo-Json | Set-Content -LiteralPath $sessionFile -Encoding UTF8

$taskName = "JCareerSessionExpiry-$SessionRef"
$actionArguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$cleanupScript`" -SessionRef $SessionRef"
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $actionArguments
$trigger = New-ScheduledTaskTrigger -Once -At $expiry.LocalDateTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -User 'SYSTEM' -RunLevel Highest -Force | Out-Null

Write-Output 'JCAREER_SESSION_CONFIGURED=PASS_CREDENTIAL_FREE_URL'
