[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^SESSION-[A-Z0-9_-]{8,64}$')]
    [string]$SessionRef
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = 'C:\ProgramData\JCareerLab'
$sessionFile = Join-Path $root 'session.json'
$desktop = [Environment]::GetFolderPath('CommonDesktopDirectory')
$shortcut = Join-Path $desktop 'J-Career approved preview.lnk'
$legacyShortcut = Join-Path $desktop 'J-Career approved preview.url'
$taskName = "JCareerSessionExpiry-$SessionRef"
$profilesRoot = Join-Path $root 'EdgeProfiles'
$edgeProfile = [IO.Path]::GetFullPath((Join-Path $profilesRoot $SessionRef))
$profilesRootFull = [IO.Path]::GetFullPath($profilesRoot + [IO.Path]::DirectorySeparatorChar)
if (-not $edgeProfile.StartsWith($profilesRootFull, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Edge profile cleanup path escaped the approved root.'
}

if (Test-Path -LiteralPath $sessionFile) {
    $session = Get-Content -LiteralPath $sessionFile -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([string]$session.session_ref -ne $SessionRef) {
        throw 'Requested cleanup does not match the configured session.'
    }
}

$edgeProcesses = @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" -ErrorAction SilentlyContinue |
    Where-Object { [string]$_.CommandLine -match [regex]::Escape($edgeProfile) })
foreach ($edgeProcess in $edgeProcesses) {
    Stop-Process -Id ([int]$edgeProcess.ProcessId) -Force -ErrorAction SilentlyContinue
}
Get-Process -Name 'msedge' -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
if ($edgeProcesses.Count -gt 0 -or (Test-Path -LiteralPath $edgeProfile)) {
    Start-Sleep -Seconds 2
}
if (Test-Path -LiteralPath $edgeProfile) {
    Remove-Item -LiteralPath $edgeProfile -Recurse -Force
}
foreach ($path in @($shortcut, $legacyShortcut, $sessionFile)) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
    }
}
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
Write-Output 'JCAREER_SESSION_REMOVED=PASS'
& "$env:SystemRoot\System32\shutdown.exe" /s /t 30 /d p:0:0 /c 'J-Career consultant session cleanup'
if ($LASTEXITCODE -ne 0) {
    throw 'Windows shutdown scheduling failed.'
}
Write-Output 'JCAREER_WINDOWS_OS_SHUTDOWN=SCHEDULED_30_SECONDS'
