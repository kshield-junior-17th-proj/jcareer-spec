param(
    [string]$ChromePath = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
)

$ErrorActionPreference = 'Stop'
$asisRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $asisRoot '..\..')).Path
$indexPath = Join-Path $asisRoot 'index.html'
$temporaryHtml = Join-Path $asisRoot '.pdf-source.html'
$temporaryPdf = Join-Path ([System.IO.Path]::GetTempPath()) ('jcareer-asis-' + [guid]::NewGuid().ToString('N') + '.pdf')
$temporaryProfile = Join-Path ([System.IO.Path]::GetTempPath()) ('jcareer-pdf-profile-' + [guid]::NewGuid().ToString('N'))
$targetPdf = Join-Path $asisRoot 'JCAREER_ASIS_SYSTEM_SPEC.pdf'
$publicBase = [Uri]'https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/'
$server = $null

if (-not (Test-Path -LiteralPath $ChromePath)) {
    throw "Chrome not found: $ChromePath"
}

$source = (Get-Content -Raw -Encoding UTF8 $indexPath).Replace("`r`n", "`n").Replace("`r", "`n")
$sourceBytes = [Text.Encoding]::UTF8.GetBytes($source)
$hasher = [Security.Cryptography.SHA256]::Create()
try {
    $sourceHash = ([BitConverter]::ToString($hasher.ComputeHash($sourceBytes))).Replace('-', '').ToLowerInvariant()
} finally {
    $hasher.Dispose()
}

# Keep images local for deterministic rendering while making every PDF link public.
$pdfHtml = [regex]::Replace(
    $source,
    '(<a\b[^>]*?\shref=")([^"]+)(")',
    {
        param($match)
        $href = $match.Groups[2].Value
        if ($href.StartsWith('#') -or $href -match '^(?:https?:|mailto:|tel:)') {
            return $match.Value
        }
        $absolute = [Uri]::new($publicBase, $href).AbsoluteUri
        return $match.Groups[1].Value + $absolute + $match.Groups[3].Value
    },
    [Text.RegularExpressions.RegexOptions]::IgnoreCase
)
[IO.File]::WriteAllText($temporaryHtml, $pdfHtml, [Text.UTF8Encoding]::new($false))

$probe = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$probe.Start()
$port = ([Net.IPEndPoint]$probe.LocalEndpoint).Port
$probe.Stop()

try {
    $python = (Get-Command python).Source
    $server = Start-Process -FilePath $python -ArgumentList @('-m', 'http.server', $port, '--bind', '127.0.0.1') -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru
    $url = "http://127.0.0.1:$port/terraform/asis/.pdf-source.html"
    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 1
            if ($response.StatusCode -eq 200) { $ready = $true; break }
        } catch {
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $ready) { throw 'Temporary PDF source server did not become ready.' }

    New-Item -ItemType Directory -Path $temporaryProfile | Out-Null
    $chrome = Start-Process -FilePath $ChromePath -ArgumentList @(
        '--headless=new',
        '--disable-gpu',
        '--no-pdf-header-footer',
        "--user-data-dir=$temporaryProfile",
        "--print-to-pdf=$temporaryPdf",
        $url
    ) -WindowStyle Hidden -Wait -PassThru
    if ($chrome.ExitCode -ne 0) { throw "Chrome PDF process failed with exit code $($chrome.ExitCode)." }
    if (-not (Test-Path -LiteralPath $temporaryPdf) -or (Get-Item -LiteralPath $temporaryPdf).Length -lt 1024) {
        throw 'Chrome did not create a valid PDF artifact.'
    }

    [IO.File]::AppendAllText(
        $temporaryPdf,
        "`n% JCAREER_HTML_SOURCE: terraform/asis/index.html`n% JCAREER_HTML_SHA256: $sourceHash`n",
        [Text.Encoding]::ASCII
    )
    Move-Item -LiteralPath $temporaryPdf -Destination $targetPdf -Force
    Write-Output "generated JCAREER_ASIS_SYSTEM_SPEC.pdf (source sha256 $sourceHash)"
} finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -Force }
    if (Test-Path -LiteralPath $temporaryHtml) { Remove-Item -LiteralPath $temporaryHtml -Force }
    if (Test-Path -LiteralPath $temporaryPdf) { Remove-Item -LiteralPath $temporaryPdf -Force }
    $resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $resolvedProfile = [IO.Path]::GetFullPath($temporaryProfile)
    if ((Test-Path -LiteralPath $resolvedProfile) -and $resolvedProfile.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase) -and ([IO.Path]::GetFileName($resolvedProfile)).StartsWith('jcareer-pdf-profile-')) {
        Remove-Item -LiteralPath $resolvedProfile -Recurse -Force
    }
}
