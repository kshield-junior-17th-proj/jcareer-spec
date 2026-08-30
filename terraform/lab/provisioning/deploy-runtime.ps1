[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^i-[0-9a-f]+$')]
    [string]$InstanceId,

    [Parameter(Mandatory = $true)]
    [ValidateSet('JCAREER_SYNTHETIC_LAB_APPROVED')]
    [string]$ActivationAcknowledgement,

    [ValidateSet('ap-northeast-2')]
    [string]$Region = 'ap-northeast-2',

    [ValidateSet('apac.amazon.nova-lite-v1:0')]
    [string]$BedrockModelId = 'apac.amazon.nova-lite-v1:0',

    [switch]$EnableBedrockLive,

    [string]$BedrockAcknowledgement = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($EnableBedrockLive) {
    if ($BedrockAcknowledgement -ne 'JCAREER_SYNTHETIC_BEDROCK_APPROVED') {
        throw 'Bedrock live requires the separate JCAREER_SYNTHETIC_BEDROCK_APPROVED acknowledgement.'
    }
    throw 'Bedrock live is blocked until a container-scoped credential boundary is approved and implemented.'
}
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw 'AWS CLI is required, but this script never retrieves or prints credentials.'
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$taskTemp = Join-Path $systemTemp ('jcareer-lab-' + [Guid]::NewGuid().ToString('N'))
$taskTempFull = [IO.Path]::GetFullPath($taskTemp)
if (-not $taskTempFull.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Temporary path escaped the system temporary directory.'
}
New-Item -ItemType Directory -Path $taskTempFull | Out-Null

$script:requestIndex = 0
$script:validatedTarget = $false
$buildxVersion = 'v0.36.1'
$buildxSha256 = '48af8a397ebd60178778bf63611dbcebe5f5e7a9be90eb9147b24b9587455778'

function Protect-Diagnostic {
    param([AllowEmptyString()][string]$Text)

    $protected = [regex]::Replace($Text, '\b\d{12}\b', '[REDACTED_ACCOUNT]')
    $protected = [regex]::Replace(
        $protected,
        'arn:(aws|aws-us-gov|aws-cn):[^\s"'']+',
        '[REDACTED_ARN]',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $protected = [regex]::Replace(
        $protected,
        '\b(i|vpc|subnet|sg|igw|rtb|eni|vol)-[0-9a-f]+\b',
        '[REDACTED_RESOURCE_ID]',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $protected = [regex]::Replace(
        $protected,
        '(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)',
        '[REDACTED_IP]'
    )
    return $protected
}

function Invoke-AwsCli {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $result = & aws @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        $diagnostic = Protect-Diagnostic ($result -join [Environment]::NewLine)
        throw "AWS CLI command failed: $diagnostic"
    }
    return $result
}

function Invoke-RemoteCommand {
    param(
        [Parameter(Mandatory = $true)][string[]]$Commands,
        [Parameter(Mandatory = $true)][string]$Comment,
        [int]$TimeoutSeconds = 900
    )

    $script:requestIndex += 1
    $requestPath = Join-Path $taskTempFull ("ssm-{0:D4}.json" -f $script:requestIndex)
    $request = @{
        DocumentName  = 'AWS-RunShellScript'
        InstanceIds   = @($InstanceId)
        Comment       = $Comment
        TimeoutSeconds = $TimeoutSeconds
        Parameters    = @{ commands = $Commands }
    }
    $requestJson = $request | ConvertTo-Json -Depth 8
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($requestPath, $requestJson, $utf8WithoutBom)

    $commandId = (Invoke-AwsCli -Arguments @(
        'ssm', 'send-command', '--region', $Region,
        '--cli-input-json', "file://$requestPath",
        '--query', 'Command.CommandId', '--output', 'text'
    ) | Select-Object -First 1).Trim()

    $commandDeadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds + 120)
    $invocation = $null
    do {
        Start-Sleep -Seconds 3
        $invocationJson = & aws ssm get-command-invocation --region $Region `
            --command-id $commandId --instance-id $InstanceId --output json 2>&1
        if ($LASTEXITCODE -eq 0) {
            $invocation = (($invocationJson -join [Environment]::NewLine) | ConvertFrom-Json)
            if ($invocation.Status -in @('Success', 'Cancelled', 'TimedOut', 'Failed', 'Cancelling')) {
                break
            }
        }
    } while ([DateTime]::UtcNow -lt $commandDeadline)

    if ($null -eq $invocation) {
        throw "Remote command status was unavailable during '$Comment'."
    }
    if ($invocation.Status -ne 'Success') {
        $diagnostic = [string]$invocation.StandardErrorContent
        if ([string]::IsNullOrWhiteSpace($diagnostic)) {
            $diagnostic = [string]$invocation.StandardOutputContent
        }
        $diagnostic = Protect-Diagnostic $diagnostic
        throw "Remote command failed during '$Comment' (status=$($invocation.Status)): $diagnostic"
    }
    return [string]$invocation.StandardOutputContent
}

function Get-ValidatedLabInstance {
    $raw = Invoke-AwsCli -Arguments @(
        'ec2', 'describe-instances', '--region', $Region,
        '--instance-ids', $InstanceId, '--output', 'json', '--no-cli-pager'
    )
    $document = (($raw -join [Environment]::NewLine) | ConvertFrom-Json)
    $instances = @(
        $document.Reservations |
            ForEach-Object { $_.Instances } |
            Where-Object { $null -ne $_ }
    )
    if ($instances.Count -ne 1) {
        throw 'The target did not resolve to exactly one EC2 instance.'
    }

    $instance = $instances[0]
    $tags = @{}
    foreach ($tag in @($instance.Tags)) {
        $tags[[string]$tag.Key] = [string]$tag.Value
    }
    $requiredTags = @{
        Project    = 'jcareer'
        jk_layer   = 'lab'
        jk_purpose = 'synthetic-runtime-validation'
    }
    foreach ($entry in $requiredTags.GetEnumerator()) {
        if ($tags[$entry.Key] -ne $entry.Value) {
            throw "The target is missing required lab tag $($entry.Key)=$($entry.Value)."
        }
    }
    if ([string]$instance.State.Name -ne 'running') {
        throw 'The validated lab instance is not running.'
    }
    if ([string]$instance.InstanceType -ne 't3.small') {
        throw 'The validated lab instance must be t3.small; smaller runtime capacity is unverified.'
    }
    $profileArn = [string]$instance.IamInstanceProfile.Arn
    if ([string]::IsNullOrWhiteSpace($profileArn)) {
        throw 'The validated lab instance has no IAM instance profile.'
    }
    $instanceName = [string]$tags['Name']
    $profileName = ($profileArn.TrimEnd('/') -split '/')[-1]
    if ([string]::IsNullOrWhiteSpace($instanceName) -or $profileName -ne $instanceName) {
        throw 'The validated lab instance profile does not match the reviewed runtime Name tag.'
    }
    if ($EnableBedrockLive -and $tags['jk_bedrock_live'] -ne 'true') {
        throw 'Bedrock live was requested, but the instance was not planned with jk_bedrock_live=true.'
    }
    return $instance
}

try {
    Write-Host '[preflight] Validating the target instance tags, state, type, and Bedrock plan flag...'
    Get-ValidatedLabInstance | Out-Null
    $script:validatedTarget = $true

    Write-Host '[1/6] Waiting for the short-lived lab instance to register with SSM...'
    $onlineDeadline = [DateTime]::UtcNow.AddMinutes(10)
    do {
        $ping = Invoke-AwsCli -Arguments @(
            'ssm', 'describe-instance-information', '--region', $Region,
            '--filters', "Key=InstanceIds,Values=$InstanceId",
            '--query', 'InstanceInformationList[0].PingStatus', '--output', 'text'
        )
        if (($ping | Select-Object -First 1).Trim() -eq 'Online') { break }
        Start-Sleep -Seconds 10
    } while ([DateTime]::UtcNow -lt $onlineDeadline)
    if ([DateTime]::UtcNow -ge $onlineDeadline) {
        throw 'The lab instance did not become available in SSM within 10 minutes.'
    }

    Invoke-RemoteCommand -Comment 'Wait for J-Career lab bootstrap' -TimeoutSeconds 720 -Commands @(
        'set -euo pipefail',
        'for attempt in $(seq 1 60); do if test -f /var/lib/jcareer-lab/bootstrap-ready && docker compose version >/dev/null 2>&1; then exit 0; fi; sleep 10; done',
        'echo "bootstrap did not complete; recent cloud-init output follows" >&2',
        'tail -n 80 /var/log/cloud-init-output.log >&2 || true',
        'exit 1'
    ) | Out-Null

    Invoke-RemoteCommand -Comment 'Check J-Career lab host capacity' -Commands @(
        'set -euo pipefail',
        'memory_kib=$(awk ''/MemTotal/ {print $2}'' /proc/meminfo)',
        'disk_kib=$(df -Pk / | awk ''NR == 2 {print $4}'')',
        'test "$memory_kib" -ge 1800000 || { echo "less than 1.8 GiB host memory" >&2; exit 1; }',
        'test "$disk_kib" -ge 8388608 || { echo "less than 8 GiB root disk available" >&2; exit 1; }',
        'swapon --show=NAME --noheadings | grep -Fx /var/lib/jcareer-lab.swap >/dev/null'
    ) | Out-Null

    Write-Host '[2/8] Installing the checksum-pinned Docker Buildx plugin...'
    Invoke-RemoteCommand -Comment 'Install checksum-pinned Docker Buildx' -TimeoutSeconds 300 -Commands @(
        'set -euo pipefail',
        "buildx_version='$buildxVersion'",
        "buildx_sha256='$buildxSha256'",
        'buildx_path=/usr/local/lib/docker/cli-plugins/docker-buildx',
        'buildx_tmp=/tmp/docker-buildx',
        'trap ''rm -f "$buildx_tmp"'' EXIT',
        'curl --fail --silent --show-error --location "https://github.com/docker/buildx/releases/download/$buildx_version/buildx-$buildx_version.linux-amd64" --output "$buildx_tmp"',
        'echo "$buildx_sha256  $buildx_tmp" | sha256sum --check --strict',
        'install -m 0755 "$buildx_tmp" "$buildx_path"',
        'docker buildx version | grep -F "${buildx_version#v}"'
    ) | Out-Null

    Write-Host '[3/8] Packaging the synthetic runtime (no repository credentials or .env files)...'
    $archivePath = Join-Path $taskTempFull 'jcareer-runtime.tgz'
    Push-Location $repoRoot
    try {
        & tar.exe -czf $archivePath `
            --exclude='.env' --exclude='.env.*' --exclude='node_modules' `
            --exclude='__pycache__' --exclude='*.pyc' --exclude='.git' `
            src/runtime terraform/lab/provisioning
        if ($LASTEXITCODE -ne 0) { throw 'Failed to package the runtime.' }
    }
    finally {
        Pop-Location
    }

    $archiveSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()

    $encoded = [Convert]::ToBase64String([IO.File]::ReadAllBytes($archivePath))
    $chunkSize = 12000
    $chunks = for ($offset = 0; $offset -lt $encoded.Length; $offset += $chunkSize) {
        $length = [Math]::Min($chunkSize, $encoded.Length - $offset)
        $encoded.Substring($offset, $length)
    }

    Write-Host ("[4/8] Transferring {0} bounded SSM chunks..." -f $chunks.Count)
    Invoke-RemoteCommand -Comment 'Prepare J-Career runtime transfer' -Commands @(
        'set -euo pipefail',
        'rm -f /tmp/jcareer-runtime.b64 /tmp/jcareer-runtime.tgz'
    ) | Out-Null
    for ($index = 0; $index -lt $chunks.Count; $index++) {
        Invoke-RemoteCommand -Comment ("Transfer J-Career runtime chunk {0}/{1}" -f ($index + 1), $chunks.Count) -Commands @(
            "printf '%s' '$($chunks[$index])' >> /tmp/jcareer-runtime.b64"
        ) | Out-Null
    }

    $provider = if ($EnableBedrockLive) { 'bedrock' } else { 'local-synthetic-stub' }
    $allowBedrockLive = $EnableBedrockLive.ToString().ToLowerInvariant()
    Write-Host ("[5/8] Building and starting the six-service runtime with provider={0}..." -f $provider)
    $environmentCommand = @"
printf '%s\n' 'LLM_PROVIDER=$provider' 'ALLOW_BEDROCK_LIVE=$allowBedrockLive' 'BEDROCK_REGION=$Region' 'BEDROCK_MODEL_ID=$BedrockModelId' 'WEB_BIND_ADDRESS=127.0.0.1' 'ASIS_RAW_PROMPT_LOG=true' "SESSION_SIGNING_KEY=`$session_key" > .env
"@.Trim()
    $deployCommands = @(
        'set -euo pipefail',
        'rm -rf /opt/jcareer-release',
        'install -d -m 0750 /opt/jcareer-release',
        'base64 -d /tmp/jcareer-runtime.b64 > /tmp/jcareer-runtime.tgz',
        "echo '$archiveSha256  /tmp/jcareer-runtime.tgz' | sha256sum --check --strict",
        'tar -xzf /tmp/jcareer-runtime.tgz -C /opt/jcareer-release',
        'rm -f /tmp/jcareer-runtime.b64 /tmp/jcareer-runtime.tgz',
        'cd /opt/jcareer-release/src/runtime',
        'umask 077',
        'session_key=$(openssl rand -hex 32)',
        $environmentCommand,
        'chmod 0600 .env',
        'export COMPOSE_PARALLEL_LIMIT=1',
        'docker compose -f compose.yaml -f ../../terraform/lab/provisioning/lab.compose.override.yaml up --build -d --wait --wait-timeout 420'
    )
    Invoke-RemoteCommand -Comment 'Deploy J-Career synthetic runtime' -Commands $deployCommands -TimeoutSeconds 1200 | Out-Null

    Write-Host '[6/8] Running provider-aware two-sided runtime checks on the validated lab instance...'
    $smokeCommand = "JCAREER_EXPECTED_EXPLANATION_PROVIDER='$provider' JCAREER_EXPECTED_BEDROCK_LIVE='$allowBedrockLive' JCAREER_CHECK_INTERNAL_SERVICES=true python3 tests/lab_remote_smoke.py"
    $smokeOutput = Invoke-RemoteCommand -Comment 'Verify J-Career synthetic runtime' -Commands @(
        'set -euo pipefail',
        'cd /opt/jcareer-release/src/runtime',
        $smokeCommand
    ) -TimeoutSeconds 300
    if ($smokeOutput -notmatch 'J-Career lab remote smoke: PASS') {
        throw 'Remote smoke command completed without the expected PASS marker.'
    }

    Write-Host '[7/8] Verifying logical member/company database role boundaries...'
    $databaseOutput = Invoke-RemoteCommand -Comment 'Verify J-Career database boundary' -Commands @(
        'set -euo pipefail',
        'cd /opt/jcareer-release/src/runtime',
        'python3 tests/database_boundary.py'
    ) -TimeoutSeconds 300
    if ($databaseOutput -notmatch 'J-Career member/company database boundary: PASS') {
        throw 'Database boundary command completed without the expected PASS marker.'
    }

    Write-Host '[8/8] PASS - runtime checks completed; connect only through an approved SSM local tunnel.'
}
catch {
    $failure = $_
    if ($script:validatedTarget) {
        Write-Warning 'Deployment or verification failed; requesting a fail-safe stop for the validated lab instance.'
        try {
            Invoke-AwsCli -Arguments @(
                'ec2', 'stop-instances', '--region', $Region,
                '--instance-ids', $InstanceId, '--no-cli-pager'
            ) | Out-Null
        }
        catch {
            $stopDiagnostic = Protect-Diagnostic ([string]$_.Exception.Message)
            Write-Warning "The fail-safe stop request also failed: $stopDiagnostic"
        }
    }
    throw $failure
}
finally {
    if (Test-Path -LiteralPath $taskTempFull) {
        $resolvedTemp = [IO.Path]::GetFullPath($taskTempFull)
        if ($resolvedTemp.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
    }
}
