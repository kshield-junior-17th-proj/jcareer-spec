[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('JCAREER_SYNTHETIC_SERVERLESS_MLOPS_APPROVED')]
    [string]$ActivationAcknowledgement,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^i-[0-9a-f]+$')]
    [string]$InstanceId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$')]
    [string]$ArtifactBucketName,

    [ValidateSet('ap-northeast-2')]
    [string]$Region = 'ap-northeast-2',

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{64}$')]
    [string]$ProviderAccountSha256,

    [ValidatePattern('^run-[a-z0-9](?:[a-z0-9-]{0,46}[a-z0-9])?$')]
    [string]$RunId = ('run-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')),

    [switch]$Apply,

    [switch]$Invoke
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($Invoke -and -not $Apply) {
    throw '-Invoke is accepted only together with -Apply. Plan-only is the default.'
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$terraformDirectory = 'terraform/serverless-mlops'
$snapshotModulePath = Join-Path $repoRoot 'scripts/JCareer-ProtectedInputSnapshot.psm1'
if (-not [IO.File]::Exists($snapshotModulePath)) {
    throw 'The protected input snapshot module is unavailable.'
}
Microsoft.PowerShell.Core\Import-Module -Name $snapshotModulePath -Force
$systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$taskTemp = Join-Path $systemTemp ('jcareer-serverless-mlops-' + [Guid]::NewGuid().ToString('N'))
$taskTempFull = [IO.Path]::GetFullPath($taskTemp)
if (-not $taskTempFull.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Temporary path escaped the system temporary directory.'
}
New-Item -ItemType Directory -Path $taskTempFull | Out-Null

$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
$script:ssmRequestIndex = 0
$script:ToolPaths = @{}
$script:PlanSnapshotSet = $null
$script:PendingSuccessMessages = @()
$featureFiles = @(
    'dataset_manifest.json',
    'ranking_dataset.csv',
    'source_read_receipt.json'
)
$resultFiles = @(
    'challenger_model.json',
    'dataset_manifest.json',
    'evaluation_observations.json',
    'pipeline_run_receipt.json',
    'ranking_dataset.csv',
    'source_read_receipt.json'
)

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
    $protected = [regex]::Replace(
        $protected,
        '\b(AKIA|ASIA)[A-Z0-9]{16}\b',
        '[REDACTED_ACCESS_KEY]'
    )
    $protected = [regex]::Replace(
        $protected,
        '(?i)(password|passwd|secret|token|authorization)=?[^\s,;]+',
        '$1=[REDACTED_SECRET]'
    )
    $protected = [regex]::Replace(
        $protected,
        '(?i)("?(?:accesskeyid|secretaccesskey|sessiontoken|password|authorization)"?\s*[:=]\s*)("[^"]+"|[^\s,;]+)',
        '$1[REDACTED_SECRET]'
    )
    $protected = [regex]::Replace(
        $protected,
        '(?i)Bearer\s+[A-Za-z0-9._~+/-]+=*',
        'Bearer [REDACTED_SECRET]'
    )
    $protected = [regex]::Replace(
        $protected,
        'https?://[^\s"'']+',
        '[REDACTED_URL]'
    )
    return $protected
}

function Protect-PlanJson {
    param([Parameter(Mandatory = $true)][string]$Text)

    # Keep the JSON grammar intact. Diagnostic secret patterns are intentionally
    # not reused because IAM action names such as GetAuthorizationToken are data,
    # not credentials, and must remain parseable for the plan allowlist checker.
    $protected = [regex]::Replace($Text, '\b\d{12}\b', '[REDACTED_ACCOUNT]')
    $protected = [regex]::Replace(
        $protected,
        'arn:(aws|aws-us-gov|aws-cn):[^\s"'']+',
        '[REDACTED_ARN]',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $protected = [regex]::Replace(
        $protected,
        '\b(AKIA|ASIA)[A-Z0-9]{16}\b',
        '[REDACTED_ACCESS_KEY]'
    )
    return $protected
}

function Resolve-RequiredExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('aws', 'docker', 'python', 'tar', 'terraform')]
        [string]$Name
    )

    $candidates = @(
        Microsoft.PowerShell.Core\Get-Command -Name $Name -All -ErrorAction SilentlyContinue
    )
    $explicitCandidates = @(
        Microsoft.PowerShell.Core\Get-Command -Name "$Name.exe" -All -ErrorAction SilentlyContinue
    )
    if (@($candidates | Where-Object { $_.CommandType -ne 'Application' }).Count -ne 0 -or
        @($explicitCandidates | Where-Object { $_.CommandType -ne 'Application' }).Count -ne 0) {
        throw "$Name command resolution is shadowed by a function, alias, script, or cmdlet."
    }
    $selected = @($explicitCandidates | Where-Object { $_.CommandType -eq 'Application' }) |
        Select-Object -First 1
    if ($null -eq $selected) {
        throw "$Name.exe is required."
    }
    $path = [IO.Path]::GetFullPath([string]$selected.Source)
    if (-not [IO.Path]::IsPathRooted($path) -or
        -not [string]::Equals([IO.Path]::GetExtension($path), '.exe', [StringComparison]::OrdinalIgnoreCase) -or
        -not [IO.File]::Exists($path) -or
        (([IO.File]::GetAttributes($path) -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "$Name did not resolve to one direct absolute executable file."
    }
    return $path
}

function Get-BytesSha256 {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = $sha.ComputeHash($Bytes) }
    finally { $sha.Dispose() }
    return ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
}

function Get-StringSha256 {
    param([Parameter(Mandatory = $true)][string]$Value)

    return Get-BytesSha256 -Bytes ([Text.Encoding]::UTF8.GetBytes($Value))
}

function Get-ExactFileSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = [IO.File]::Open(
        [IO.Path]::GetFullPath($Path),
        [IO.FileMode]::Open,
        [IO.FileAccess]::Read,
        [IO.FileShare]::Read
    )
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $digest = $sha.ComputeHash($stream) }
        finally { $sha.Dispose() }
    }
    finally { $stream.Dispose() }
    return ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$ReturnOutput
    )

    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& $FilePath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        $diagnostic = Protect-Diagnostic (($output | Select-Object -Last 30) -join [Environment]::NewLine)
        throw "$Label failed (exit=$exitCode). $diagnostic"
    }
    if ($ReturnOutput) {
        return $output
    }
}

function Invoke-AwsCli {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$ReturnOutput
    )

    if (-not $script:ToolPaths.ContainsKey('aws')) {
        throw 'The absolute AWS CLI path has not been resolved.'
    }
    return Invoke-CheckedCommand -Label $Label -FilePath $script:ToolPaths.aws -Arguments $Arguments -ReturnOutput:$ReturnOutput
}

function Get-ObservedProviderAccountSha256 {
    $accountOutput = Invoke-AwsCli -Label 'Provider account binding check' -Arguments @(
        'sts', 'get-caller-identity', '--region', $Region,
        '--query', 'Account', '--output', 'text', '--no-cli-pager'
    ) -ReturnOutput
    try {
        $account = (($accountOutput -join '').Trim())
        if ($account -notmatch '^\d{12}$') {
            throw 'The provider account identity was empty, placeholder-like, or malformed.'
        }
        return Get-StringSha256 -Value $account
    }
    finally {
        $account = $null
        $accountOutput = $null
    }
}

function Assert-ProviderAccountBinding {
    param([Parameter(Mandatory = $true)][string]$Phase)

    if ($ProviderAccountSha256 -notmatch '^[0-9a-f]{64}$' -or
        $ProviderAccountSha256 -match '^([0-9a-f])\1{63}$') {
        throw 'provider_account_sha256 is empty, malformed, or placeholder-like.'
    }
    $observed = Get-ObservedProviderAccountSha256
    if (-not [string]::Equals($observed, $ProviderAccountSha256, [StringComparison]::Ordinal)) {
        throw "Provider account binding changed before $Phase."
    }
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][object]$Value
    )

    $content = $Value | ConvertTo-Json -Depth 12 -Compress
    [IO.File]::WriteAllText($Path, $content, $utf8WithoutBom)
}

function Assert-NonDestructivePlan {
    param(
        [Parameter(Mandatory = $true)][string]$PlanPath,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($null -eq $script:PlanSnapshotSet) {
        throw 'The protected saved-plan snapshot set is unavailable.'
    }
    Assert-ProviderAccountBinding -Phase "$Label plan capture"
    $lockedPlanPath = Add-JCareerProtectedSnapshotFile `
        -SnapshotSet $script:PlanSnapshotSet `
        -Source $PlanPath `
        -DestinationName "$Label.tfplan"
    $planOutput = Invoke-CheckedCommand -Label "$Label plan JSON" -FilePath $script:ToolPaths.terraform -Arguments @(
        "-chdir=$terraformDirectory", 'show', '-json', $lockedPlanPath
    ) -ReturnOutput
    $jsonPath = Join-Path $taskTempFull "$Label-plan.redacted.json"
    try {
        $redactedPlanJson = Protect-PlanJson ($planOutput -join [Environment]::NewLine)
        [IO.File]::WriteAllText($jsonPath, $redactedPlanJson, $utf8WithoutBom)
    }
    finally {
        $redactedPlanJson = $null
        $planOutput = $null
    }
    $lockedJsonPath = Add-JCareerProtectedSnapshotFile `
        -SnapshotSet $script:PlanSnapshotSet `
        -Source $jsonPath `
        -DestinationName "$Label-plan.redacted.json"
    $document = [IO.File]::ReadAllText($lockedJsonPath) | Microsoft.PowerShell.Utility\ConvertFrom-Json
    $changes = @($document.resource_changes)
    $destructive = @(
        $changes | Where-Object { @($_.change.actions).Contains('delete') }
    )
    if ($destructive.Count -gt 0) {
        throw "$Label plan contains delete or replacement actions; execution is blocked."
    }
    Invoke-CheckedCommand -Label "$Label allowlist" -FilePath $script:ToolPaths.python -Arguments @(
        'scripts/check_serverless_mlops_static.py', '--plan', $lockedJsonPath
    )
    $createCount = @($changes | Where-Object { @($_.change.actions).Contains('create') }).Count
    $updateCount = @($changes | Where-Object { @($_.change.actions).Contains('update') }).Count
    $noOpCount = @($changes | Where-Object { @($_.change.actions).Contains('no-op') }).Count
    Write-Host "[plan:$Label] create=$createCount update=$updateCount delete=0 no-op=$noOpCount"

    $contextPath = Join-Path $taskTempFull "$Label-execution-context.json"
    $planSha256 = Get-ExactFileSha256 -Path $lockedPlanPath
    $jsonSha256 = Get-ExactFileSha256 -Path $lockedJsonPath
    Write-JsonFile -Path $contextPath -Value @{
        schema_version                    = 'jcareer-serverless-mlops-plan-context-v1'
        label                             = $Label
        provider_account_sha256           = $ProviderAccountSha256
        activation_acknowledgement_sha256 = Get-StringSha256 -Value $ActivationAcknowledgement
        region                            = $Region
        run_id                            = $RunId
        artifact_bucket_name_sha256       = Get-StringSha256 -Value $ArtifactBucketName
        plan_sha256                       = $planSha256
        plan_json_sha256                  = $jsonSha256
    }
    $lockedContextPath = Add-JCareerProtectedSnapshotFile `
        -SnapshotSet $script:PlanSnapshotSet `
        -Source $contextPath `
        -DestinationName "$Label-execution-context.json"
    return [pscustomobject]@{
        Label = $Label
        PlanPath = $lockedPlanPath
        JsonPath = $lockedJsonPath
        ContextPath = $lockedContextPath
        PlanSha256 = $planSha256
        JsonSha256 = $jsonSha256
    }
}

function Assert-SavedPlanExecutionContext {
    param(
        [Parameter(Mandatory = $true)]$Context,
        [Parameter(Mandatory = $true)][string]$Phase
    )

    Assert-ProviderAccountBinding -Phase $Phase
    $document = [IO.File]::ReadAllText([string]$Context.ContextPath) |
        Microsoft.PowerShell.Utility\ConvertFrom-Json
    $expectedProperties = @(
        'activation_acknowledgement_sha256',
        'artifact_bucket_name_sha256',
        'label',
        'plan_json_sha256',
        'plan_sha256',
        'provider_account_sha256',
        'region',
        'run_id',
        'schema_version'
    )
    $observedProperties = @($document.PSObject.Properties.Name | Sort-Object)
    if (($observedProperties -join "`n") -cne (($expectedProperties | Sort-Object) -join "`n")) {
        throw 'The protected saved-plan execution context schema changed.'
    }
    if ($document.schema_version -cne 'jcareer-serverless-mlops-plan-context-v1' -or
        $document.label -cne [string]$Context.Label -or
        $document.provider_account_sha256 -cne $ProviderAccountSha256 -or
        $document.activation_acknowledgement_sha256 -cne (Get-StringSha256 -Value $ActivationAcknowledgement) -or
        $document.region -cne $Region -or
        $document.run_id -cne $RunId -or
        $document.artifact_bucket_name_sha256 -cne (Get-StringSha256 -Value $ArtifactBucketName) -or
        $document.plan_sha256 -cne [string]$Context.PlanSha256 -or
        $document.plan_json_sha256 -cne [string]$Context.JsonSha256) {
        throw 'The protected saved-plan execution context no longer matches operator approval.'
    }
    if ((Get-ExactFileSha256 -Path ([string]$Context.PlanPath)) -cne [string]$Context.PlanSha256 -or
        (Get-ExactFileSha256 -Path ([string]$Context.JsonPath)) -cne [string]$Context.JsonSha256) {
        throw 'The locked saved plan or its redacted JSON changed before execution.'
    }
}

function Get-TerraformOutput {
    param([Parameter(Mandatory = $true)][string]$Name)

    $value = Invoke-CheckedCommand -Label 'Terraform managed output' -FilePath $script:ToolPaths.terraform -Arguments @(
        "-chdir=$terraformDirectory", 'output', '-raw', $Name
    ) -ReturnOutput
    return (($value -join '').Trim())
}

function Invoke-RemoteCommand {
    param(
        [Parameter(Mandatory = $true)][string[]]$Commands,
        [Parameter(Mandatory = $true)][string]$Comment,
        [int]$TimeoutSeconds = 900,
        [switch]$ReturnOutput
    )

    $script:ssmRequestIndex += 1
    $requestPath = Join-Path $taskTempFull ("ssm-{0:D4}.json" -f $script:ssmRequestIndex)
    Write-JsonFile -Path $requestPath -Value @{
        DocumentName   = 'AWS-RunShellScript'
        InstanceIds    = @($InstanceId)
        Comment        = $Comment
        TimeoutSeconds = $TimeoutSeconds
        Parameters     = @{ commands = $Commands }
    }
    $commandIdOutput = Invoke-AwsCli -Label 'SSM command dispatch' -Arguments @(
        'ssm', 'send-command', '--region', $Region,
        '--cli-input-json', "file://$requestPath",
        '--query', 'Command.CommandId', '--output', 'text', '--no-cli-pager'
    ) -ReturnOutput
    $commandId = (($commandIdOutput -join '').Trim())
    if ($commandId -notmatch '^[0-9a-f-]{36}$') {
        throw 'SSM returned an invalid command handle.'
    }

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds + 120)
    $invocation = $null
    do {
        Start-Sleep -Seconds 3
        $raw = & $script:ToolPaths.aws ssm get-command-invocation --region $Region `
            --command-id $commandId --instance-id $InstanceId --output json --no-cli-pager 2>&1
        if ($LASTEXITCODE -eq 0) {
            $invocation = (($raw -join [Environment]::NewLine) | ConvertFrom-Json)
            if ($invocation.Status -in @('Success', 'Cancelled', 'TimedOut', 'Failed', 'Cancelling')) {
                break
            }
        }
    } while ([DateTime]::UtcNow -lt $deadline)

    if ($null -eq $invocation -or $invocation.Status -ne 'Success') {
        $status = if ($null -eq $invocation) { 'unavailable' } else { [string]$invocation.Status }
        $diagnostic = if ($null -eq $invocation) { '' } else { [string]$invocation.StandardErrorContent }
        throw "Remote command failed during $Comment (status=$status). $(Protect-Diagnostic $diagnostic)"
    }
    if ($ReturnOutput) {
        return [string]$invocation.StandardOutputContent
    }
}

function Assert-ValidatedLabTarget {
    $raw = Invoke-AwsCli -Label 'Validated lab target lookup' -Arguments @(
        'ec2', 'describe-instances', '--region', $Region,
        '--instance-ids', $InstanceId, '--output', 'json', '--no-cli-pager'
    ) -ReturnOutput
    $document = (($raw -join [Environment]::NewLine) | ConvertFrom-Json)
    $instances = @($document.Reservations | ForEach-Object { $_.Instances } | Where-Object { $null -ne $_ })
    if ($instances.Count -ne 1) {
        throw 'The target did not resolve to exactly one EC2 instance.'
    }
    $instance = $instances[0]
    $tags = @{}
    foreach ($tag in @($instance.Tags)) {
        $tags[[string]$tag.Key] = [string]$tag.Value
    }
    foreach ($required in @{
        Project = 'jcareer'; jk_layer = 'lab'; jk_purpose = 'synthetic-runtime-validation'
    }.GetEnumerator()) {
        if ($tags[$required.Key] -ne $required.Value) {
            throw 'The target is not the Terraform-managed J-Career synthetic lab.'
        }
    }
    if ([string]$instance.State.Name -ne 'running') {
        throw 'The validated lab instance is not running.'
    }
}

function Send-ExporterSource {
    $archivePath = Join-Path $taskTempFull 'mlops-exporter.tgz'
    $remoteBase = "/tmp/jcareer-mlops-exporter-$RunId"
    Push-Location $repoRoot
    try {
        & $script:ToolPaths.tar -czf $archivePath `
            src/mlops/Dockerfile.exporter `
            src/mlops/requirements.txt `
            src/mlops/generate_synthetic_training.py `
            src/mlops/export_runtime_training.py
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to package the bounded exporter source.'
        }
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
    Invoke-RemoteCommand -Comment 'Prepare bounded MLOps exporter transfer' -Commands @(
        'set -euo pipefail',
        "test ! -e '$remoteBase.b64'",
        "test ! -e '$remoteBase.tgz'"
    )
    for ($index = 0; $index -lt $chunks.Count; $index++) {
        Invoke-RemoteCommand -Comment 'Transfer bounded MLOps exporter source' -Commands @(
            "printf '%s' '$($chunks[$index])' >> '$remoteBase.b64'"
        )
    }
    Invoke-RemoteCommand -Comment 'Verify bounded MLOps exporter source' -Commands @(
        'set -euo pipefail',
        "base64 -d '$remoteBase.b64' > '$remoteBase.tgz'",
        "echo '$archiveSha256  $remoteBase.tgz' | sha256sum --check --strict >/dev/null",
        "rm -f '$remoteBase.b64'"
    )
}

function Receive-FeatureSnapshot {
    $remote = Invoke-RemoteCommand -Comment 'Export feature-only synthetic snapshot' -TimeoutSeconds 900 -ReturnOutput -Commands @(
        'set -euo pipefail',
        "run_id='$RunId'",
        "source_archive='/tmp/jcareer-mlops-exporter-$RunId.tgz'",
        'work="/var/tmp/jcareer-mlops-${run_id}"',
        'image="jcareer-synthetic-exporter:${run_id}"',
        'cleanup() { docker image rm -f "$image" >/dev/null 2>&1 || true; rm -rf -- "$work"; rm -f -- "$source_archive"; }',
        'trap cleanup EXIT',
        'test ! -e "$work"',
        'install -d -m 0700 "$work/source" "$work/output"',
        'tar -xzf "$source_archive" -C "$work/source"',
        'docker network inspect jcareer-asis-runtime_default >/dev/null 2>&1',
        'api_container=$(docker ps --filter label=com.docker.compose.project=jcareer-asis-runtime --filter label=com.docker.compose.service=api --format ''{{.ID}}'')',
        'test -n "$api_container" && test "$(printf ''%s\n'' "$api_container" | wc -l)" -eq 1',
        'api_env=$(docker inspect --format ''{{range .Config.Env}}{{println .}}{{end}}'' "$api_container")',
        'member_url=$(printf ''%s\n'' "$api_env" | sed -n ''s/^MEMBER_DATABASE_URL=//p'')',
        'company_url=$(printf ''%s\n'' "$api_env" | sed -n ''s/^COMPANY_DATABASE_URL=//p'')',
        'unset api_env',
        'case "$member_url" in postgresql+psycopg://*@postgres:5432/jcareer_member) ;; *) exit 21 ;; esac',
        'case "$company_url" in postgresql+psycopg://*@postgres:5432/jcareer_company) ;; *) exit 22 ;; esac',
        'export MEMBER_DATABASE_URL="$member_url" COMPANY_DATABASE_URL="$company_url"',
        'unset member_url company_url',
        'docker build --quiet -f "$work/source/src/mlops/Dockerfile.exporter" -t "$image" "$work/source/src/mlops" >/dev/null 2>&1 || exit 23',
        'docker run --rm --network jcareer-asis-runtime_default --env MEMBER_DATABASE_URL --env COMPANY_DATABASE_URL -v "$work/output:/output" "$image" >/dev/null 2>&1 || exit 24',
        'unset MEMBER_DATABASE_URL COMPANY_DATABASE_URL',
        'actual=$(find "$work/output" -maxdepth 1 -type f -printf ''%f\n'' | LC_ALL=C sort)',
        'expected=$(printf ''%s\n'' dataset_manifest.json ranking_dataset.csv source_read_receipt.json)',
        'test "$actual" = "$expected"',
        'tar -czf "$work/feature-package.tgz" -C "$work/output" dataset_manifest.json ranking_dataset.csv source_read_receipt.json',
        'archive_size=$(stat -c %s "$work/feature-package.tgz")',
        'test "$archive_size" -le 12000 || { echo ''feature package exceeds bounded SSM response size'' >&2; exit 25; }',
        'archive_sha=$(sha256sum "$work/feature-package.tgz" | awk ''{print $1}'')',
        'printf ''JCAREER_FEATURE_PACKAGE_SHA256=%s\n'' "$archive_sha"',
        'printf ''JCAREER_FEATURE_PACKAGE_BEGIN\n''',
        'base64 -w0 "$work/feature-package.tgz"',
        'printf ''\nJCAREER_FEATURE_PACKAGE_END\n'''
    )
    $match = [regex]::Match(
        $remote,
        '(?ms)^JCAREER_FEATURE_PACKAGE_SHA256=([0-9a-f]{64})\r?\nJCAREER_FEATURE_PACKAGE_BEGIN\r?\n([A-Za-z0-9+/=]+)\r?\nJCAREER_FEATURE_PACKAGE_END\r?\n?$'
    )
    if (-not $match.Success) {
        throw 'The feature-only SSM response was missing, truncated, or contained unexpected output.'
    }
    $archivePath = Join-Path $taskTempFull 'feature-package.tgz'
    try {
        [IO.File]::WriteAllBytes($archivePath, [Convert]::FromBase64String($match.Groups[2].Value))
    }
    catch {
        throw 'The feature package was not valid base64.'
    }
    $observedSha = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($observedSha -ne $match.Groups[1].Value) {
        throw 'The feature package digest did not match the remote digest.'
    }
    $listing = @(& $script:ToolPaths.tar -tzf $archivePath 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw 'The feature package archive could not be inspected.'
    }
    $observedFiles = @($listing | ForEach-Object { ([string]$_).TrimStart('.').TrimStart('/') } | Sort-Object)
    if (($observedFiles -join "`n") -ne ($featureFiles -join "`n")) {
        throw 'The feature package contained files outside the exact three-file allowlist.'
    }
    $extractPath = Join-Path $taskTempFull 'feature-package'
    New-Item -ItemType Directory -Path $extractPath | Out-Null
    & $script:ToolPaths.tar -xzf $archivePath -C $extractPath
    if ($LASTEXITCODE -ne 0) {
        throw 'The feature package could not be extracted.'
    }
    return $extractPath
}

function Publish-FeatureSnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [Parameter(Mandatory = $true)][string]$ManagedBucket
    )

    $prefix = "mlops/sources/$RunId/"
    foreach ($name in $featureFiles) {
        $contentType = if ($name.EndsWith('.csv')) { 'text/csv; charset=utf-8' } else { 'application/json' }
        Invoke-AwsCli -Label 'Upload feature-only snapshot object' -Arguments @(
            's3api', 'put-object', '--region', $Region,
            '--bucket', $ManagedBucket,
            '--key', "$prefix$name",
            '--body', (Join-Path $Directory $name),
            '--server-side-encryption', 'AES256',
            '--if-none-match', '*',
            '--content-type', $contentType,
            '--output', 'json', '--no-cli-pager'
        )
    }
    return $prefix
}

function Invoke-And-VerifyTrainer {
    param(
        [Parameter(Mandatory = $true)][string]$FunctionName,
        [Parameter(Mandatory = $true)][string]$TableName,
        [Parameter(Mandatory = $true)][string]$ManagedBucket,
        [Parameter(Mandatory = $true)][string]$SourcePrefix
    )

    $eventPath = Join-Path $taskTempFull 'invoke-event.json'
    $responsePath = Join-Path $taskTempFull 'invoke-response.json'
    Write-JsonFile -Path $eventPath -Value @{
        action        = 'train_challenger'
        run_id        = $RunId
        source_mode   = 'feature_snapshot'
        source_prefix = $SourcePrefix
    }
    Invoke-AwsCli -Label 'Invoke one-shot synthetic trainer' -Arguments @(
        'lambda', 'invoke', '--region', $Region,
        '--function-name', $FunctionName,
        '--cli-binary-format', 'raw-in-base64-out',
        '--payload', "fileb://$eventPath",
        '--cli-connect-timeout', '10', '--cli-read-timeout', '360',
        '--output', 'json', '--no-cli-pager',
        $responsePath
    )
    $response = Get-Content -Raw -LiteralPath $responsePath | ConvertFrom-Json
    if ($response.state -ne 'TRAINED_PENDING_HUMAN_REVIEW' -or
        [int]$response.artifact_count -ne 6 -or
        [bool]$response.runtime_ranking_wired -or
        [bool]$response.automatic_model_activation) {
        throw 'The Lambda response did not satisfy the bounded non-activation contract.'
    }

    $keyPath = Join-Path $taskTempFull 'ddb-key.json'
    Write-JsonFile -Path $keyPath -Value @{ run_id = @{ S = $RunId } }
    $terminalState = $null
    $deadline = [DateTime]::UtcNow.AddMinutes(2)
    do {
        $itemOutput = Invoke-AwsCli -Label 'Read synthetic run state' -Arguments @(
            'dynamodb', 'get-item', '--region', $Region,
            '--table-name', $TableName,
            '--key', "file://$keyPath",
            '--consistent-read',
            '--projection-expression', 'run_id,#s,artifact_count,runtime_ranking_wired,automatic_model_activation',
            '--expression-attribute-names', '{"#s":"state"}',
            '--output', 'json', '--no-cli-pager'
        ) -ReturnOutput
        $item = (($itemOutput -join [Environment]::NewLine) | ConvertFrom-Json).Item
        $terminalState = [string]$item.state.S
        if ($terminalState -in @('TRAINED_PENDING_HUMAN_REVIEW', 'FAILED_SAFE')) { break }
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($terminalState -ne 'TRAINED_PENDING_HUMAN_REVIEW') {
        throw "The one-shot run did not reach the expected terminal state (observed=$terminalState)."
    }
    if ([string]$item.artifact_count.S -ne '6' -or
        [string]$item.runtime_ranking_wired.S -ne 'false' -or
        [string]$item.automatic_model_activation.S -ne 'false') {
        throw 'The persisted run state did not satisfy the six-artifact non-activation contract.'
    }

    $keysOutput = Invoke-AwsCli -Label 'List bounded synthetic result objects' -Arguments @(
        's3api', 'list-objects-v2', '--region', $Region,
        '--bucket', $ManagedBucket,
        '--prefix', "mlops/runs/$RunId/",
        '--query', 'Contents[].Key', '--output', 'json', '--no-cli-pager'
    ) -ReturnOutput
    $keys = @(($keysOutput -join [Environment]::NewLine) | ConvertFrom-Json)
    $names = @($keys | ForEach-Object { ([string]$_ -split '/')[-1] } | Sort-Object)
    if (($names -join "`n") -ne ($resultFiles -join "`n")) {
        throw 'The result prefix did not contain exactly the six expected artifacts.'
    }
}

$previousEnvironment = @{
    TF_IN_AUTOMATION                    = [Environment]::GetEnvironmentVariable('TF_IN_AUTOMATION', 'Process')
    TF_VAR_deployment_stage             = [Environment]::GetEnvironmentVariable('TF_VAR_deployment_stage', 'Process')
    TF_VAR_activation_acknowledgement   = [Environment]::GetEnvironmentVariable('TF_VAR_activation_acknowledgement', 'Process')
    TF_VAR_artifact_bucket_name         = [Environment]::GetEnvironmentVariable('TF_VAR_artifact_bucket_name', 'Process')
    TF_VAR_lambda_image_uri             = [Environment]::GetEnvironmentVariable('TF_VAR_lambda_image_uri', 'Process')
    DOCKER_CONFIG                       = [Environment]::GetEnvironmentVariable('DOCKER_CONFIG', 'Process')
}

Push-Location $repoRoot
try {
    foreach ($tool in @('aws', 'docker', 'python', 'tar', 'terraform')) {
        $script:ToolPaths[$tool] = Resolve-RequiredExecutable -Name $tool
    }
    $script:PlanSnapshotSet = New-JCareerProtectedSnapshotSet `
        -RootPath $taskTempFull `
        -Prefix 'jcareer-mlops-plan'
    [Environment]::SetEnvironmentVariable('TF_IN_AUTOMATION', '1', 'Process')
    [Environment]::SetEnvironmentVariable('TF_VAR_deployment_stage', 'bootstrap', 'Process')
    [Environment]::SetEnvironmentVariable('TF_VAR_activation_acknowledgement', $ActivationAcknowledgement, 'Process')
    [Environment]::SetEnvironmentVariable('TF_VAR_artifact_bucket_name', $ArtifactBucketName, 'Process')
    [Environment]::SetEnvironmentVariable('TF_VAR_lambda_image_uri', '', 'Process')
    $dockerConfig = Join-Path $taskTempFull 'docker-config'
    New-Item -ItemType Directory -Path $dockerConfig | Out-Null
    [Environment]::SetEnvironmentVariable('DOCKER_CONFIG', $dockerConfig, 'Process')

    Write-Host '[1/9] Credential, source, and fixed-version preflight...'
    Assert-ProviderAccountBinding -Phase 'credential preflight'
    Invoke-CheckedCommand -Label 'serverless source guard' -FilePath $script:ToolPaths.python -Arguments @(
        'scripts/check_serverless_mlops_static.py'
    )
    Invoke-CheckedCommand -Label 'Terraform init' -FilePath $script:ToolPaths.terraform -Arguments @(
        "-chdir=$terraformDirectory", 'init', '-input=false', '-no-color'
    )
    Invoke-CheckedCommand -Label 'Terraform format check' -FilePath $script:ToolPaths.terraform -Arguments @(
        "-chdir=$terraformDirectory", 'fmt', '-check', '-no-color'
    )
    Invoke-CheckedCommand -Label 'Terraform validate' -FilePath $script:ToolPaths.terraform -Arguments @(
        "-chdir=$terraformDirectory", 'validate', '-no-color'
    )

    Write-Host '[2/9] Creating and checking the bootstrap saved plan...'
    $bootstrapPlan = Join-Path $taskTempFull 'bootstrap.tfplan'
    Assert-ProviderAccountBinding -Phase 'bootstrap plan'
    Invoke-CheckedCommand -Label 'Bootstrap saved plan' -FilePath $script:ToolPaths.terraform -Arguments @(
        "-chdir=$terraformDirectory", 'plan', '-input=false', '-no-color', "-out=$bootstrapPlan"
    )
    $bootstrapContext = Assert-NonDestructivePlan -PlanPath $bootstrapPlan -Label 'bootstrap'
    if (-not $Apply) {
        $script:PendingSuccessMessages = @(
            '[PLAN-ONLY PASS] No Terraform apply, image push, SSM export, S3 upload, or Lambda invocation occurred.',
            'Re-run with -Apply to deploy without invocation, or with both -Apply and -Invoke for the one-shot synthetic demonstration.'
        )
        return
    }

    Write-Host '[3/9] Applying only the checked bootstrap plan...'
    Assert-SavedPlanExecutionContext -Context $bootstrapContext -Phase 'bootstrap saved-plan apply'
    Invoke-CheckedCommand -Label 'Bootstrap saved-plan apply' -FilePath $script:ToolPaths.terraform -Arguments @(
        "-chdir=$terraformDirectory", 'apply', '-input=false', '-no-color', $bootstrapContext.PlanPath
    )
    $managedBucket = Get-TerraformOutput -Name 'artifact_bucket_name'
    if ($managedBucket -ne $ArtifactBucketName) {
        throw 'Terraform managed bucket output did not match the operator input.'
    }
    $repositoryUrl = Get-TerraformOutput -Name 'ecr_repository_url'
    if ($repositoryUrl -notmatch '^[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-z0-9/_-]+$') {
        throw 'Terraform returned an invalid managed ECR repository URL.'
    }
    $registry = ($repositoryUrl -split '/')[0]
    $repositoryName = ($repositoryUrl -split '/', 2)[1]

    Write-Host '[4/9] Building, scanning, and resolving the Lambda image to an immutable digest...'
    Assert-ProviderAccountBinding -Phase 'image build and registry mutation'
    $loginPassword = Invoke-AwsCli -Label 'ECR login token' -Arguments @(
        'ecr', 'get-login-password', '--region', $Region
    ) -ReturnOutput
    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $loginOutput = @(($loginPassword -join '') | & $script:ToolPaths.docker login --username AWS --password-stdin $registry 2>&1)
        $loginExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
        $loginPassword = $null
    }
    if ($loginExitCode -ne 0) {
        throw "ECR login failed. $(Protect-Diagnostic (($loginOutput | Select-Object -Last 10) -join ' '))"
    }
    $imageTag = $RunId
    Invoke-CheckedCommand -Label 'Lambda image build and push' -FilePath $script:ToolPaths.docker -Arguments @(
        'buildx', 'build', '--platform', 'linux/amd64', '--provenance=false',
        '--file', 'src/mlops/Dockerfile.lambda',
        '--tag', "${repositoryUrl}:$imageTag", '--push', 'src/mlops'
    )
    Invoke-AwsCli -Label 'Wait for ECR image scan' -Arguments @(
        'ecr', 'wait', 'image-scan-complete', '--region', $Region,
        '--repository-name', $repositoryName, '--image-id', "imageTag=$imageTag"
    )
    $scanOutput = Invoke-AwsCli -Label 'Read ECR image scan summary' -Arguments @(
        'ecr', 'describe-image-scan-findings', '--region', $Region,
        '--repository-name', $repositoryName, '--image-id', "imageTag=$imageTag",
        '--query', 'imageScanFindings.findingSeverityCounts', '--output', 'json', '--no-cli-pager'
    ) -ReturnOutput
    $scan = (($scanOutput -join [Environment]::NewLine) | ConvertFrom-Json)
    $criticalCount = if ($scan.PSObject.Properties.Name -contains 'CRITICAL') { [int]$scan.CRITICAL } else { 0 }
    $highCount = if ($scan.PSObject.Properties.Name -contains 'HIGH') { [int]$scan.HIGH } else { 0 }
    if ($criticalCount -gt 0 -or $highCount -gt 0) {
        throw 'The pushed image has HIGH or CRITICAL scan findings; runtime deployment is blocked.'
    }
    $digestOutput = Invoke-AwsCli -Label 'Resolve immutable image digest' -Arguments @(
        'ecr', 'describe-images', '--region', $Region,
        '--repository-name', $repositoryName, '--image-ids', "imageTag=$imageTag",
        '--query', 'imageDetails[0].imageDigest', '--output', 'text', '--no-cli-pager'
    ) -ReturnOutput
    $digest = (($digestOutput -join '').Trim())
    if ($digest -notmatch '^sha256:[0-9a-f]{64}$') {
        throw 'ECR did not return a valid immutable image digest.'
    }
    $pinnedImage = "$repositoryUrl@$digest"

    Write-Host '[5/9] Creating and checking the runtime saved plan...'
    [Environment]::SetEnvironmentVariable('TF_VAR_deployment_stage', 'runtime', 'Process')
    [Environment]::SetEnvironmentVariable('TF_VAR_lambda_image_uri', $pinnedImage, 'Process')
    $runtimePlan = Join-Path $taskTempFull 'runtime.tfplan'
    Assert-ProviderAccountBinding -Phase 'runtime plan'
    Invoke-CheckedCommand -Label 'Runtime saved plan' -FilePath $script:ToolPaths.terraform -Arguments @(
        "-chdir=$terraformDirectory", 'plan', '-input=false', '-no-color', "-out=$runtimePlan"
    )
    $runtimeContext = Assert-NonDestructivePlan -PlanPath $runtimePlan -Label 'runtime'
    Assert-SavedPlanExecutionContext -Context $runtimeContext -Phase 'runtime saved-plan apply'
    Invoke-CheckedCommand -Label 'Runtime saved-plan apply' -FilePath $script:ToolPaths.terraform -Arguments @(
        "-chdir=$terraformDirectory", 'apply', '-input=false', '-no-color', $runtimeContext.PlanPath
    )

    if (-not $Invoke) {
        $script:PendingSuccessMessages = @(
            '[DEPLOY PASS] Foundation and digest-pinned Lambda are deployed; no database export, S3 source upload, or Lambda invocation occurred.'
        )
        return
    }

    Write-Host '[6/9] Validating the running lab target without opening a database port...'
    Assert-SavedPlanExecutionContext -Context $runtimeContext -Phase 'synthetic invocation preparation'
    Assert-ValidatedLabTarget
    $pingOutput = Invoke-AwsCli -Label 'SSM online-state check' -Arguments @(
        'ssm', 'describe-instance-information', '--region', $Region,
        '--filters', "Key=InstanceIds,Values=$InstanceId",
        '--query', 'InstanceInformationList[0].PingStatus', '--output', 'text', '--no-cli-pager'
    ) -ReturnOutput
    if ((($pingOutput -join '').Trim()) -ne 'Online') {
        throw 'The validated lab target is not online in SSM.'
    }

    Write-Host '[7/9] Building an ephemeral exporter inside the existing Compose network...'
    Send-ExporterSource
    $snapshotDirectory = Receive-FeatureSnapshot

    Write-Host '[8/9] Uploading exactly three feature-only snapshot objects...'
    Assert-SavedPlanExecutionContext -Context $runtimeContext -Phase 'feature snapshot upload'
    $sourcePrefix = Publish-FeatureSnapshot -Directory $snapshotDirectory -ManagedBucket $managedBucket

    Write-Host '[9/9] Invoking once and verifying terminal state plus exactly six result objects...'
    Assert-SavedPlanExecutionContext -Context $runtimeContext -Phase 'one-shot Lambda invocation'
    $functionName = Get-TerraformOutput -Name 'lambda_function_name'
    $tableName = Get-TerraformOutput -Name 'run_table_name'
    Invoke-And-VerifyTrainer -FunctionName $functionName -TableName $tableName `
        -ManagedBucket $managedBucket -SourcePrefix $sourcePrefix
    $script:PendingSuccessMessages = @(
        '[DEMO PASS] Synthetic DB export, feature-only upload, one-shot training, pending-human-review state, and six-artifact result were observed.',
        'The challenger was not activated and cannot change runtime ranking.'
    )
}
finally {
    $finalizationFailure = $null
    if ($null -ne $script:PlanSnapshotSet) {
        try {
            Remove-JCareerProtectedSnapshotSet -SnapshotSet $script:PlanSnapshotSet
            $script:PlanSnapshotSet = $null
        }
        catch { $finalizationFailure = $_ }
    }
    Pop-Location
    foreach ($entry in $previousEnvironment.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, 'Process')
    }
    if ($null -eq $finalizationFailure -and (Test-Path -LiteralPath $taskTempFull)) {
        $resolvedTemp = [IO.Path]::GetFullPath($taskTempFull)
        if ($resolvedTemp.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase)) {
            try {
                Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
                if (Test-Path -LiteralPath $resolvedTemp) {
                    throw 'The exact operator temporary directory remains present.'
                }
            }
            catch { $finalizationFailure = $_ }
        }
    }
    if ($null -ne $finalizationFailure) {
        throw 'Protected saved-plan or temporary-file cleanup was not fully observed.'
    }
    foreach ($message in $script:PendingSuccessMessages) {
        Write-Host $message
    }
}
