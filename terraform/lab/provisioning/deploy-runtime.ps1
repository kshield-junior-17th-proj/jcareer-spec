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

    [string]$BedrockAcknowledgement = '',

    [switch]$EnableOpenDartLive,

    [string]$OpenDartAcknowledgement = '',

    [string]$OpenDartBackendConfig = '',

    [string]$OpenDartApplyReceipt = '',

    [switch]$RunOpenDartLiveSmoke,

    [ValidatePattern('^(?:|[0-9]{8})$')]
    [string]$OpenDartDemoCorpCode = '',

    [string]$OpenDartDemoCompanyName = '',

    [string]$OpenDartCallAcknowledgement = '',

    [switch]$EnableAwsHttpsPreview,

    [string]$HttpsPreviewAcknowledgement = '',

    [switch]$PreserveInstanceOnFailure
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($EnableBedrockLive) {
    if ($BedrockAcknowledgement -ne 'JCAREER_SYNTHETIC_BEDROCK_APPROVED') {
        throw 'Bedrock live requires the separate JCAREER_SYNTHETIC_BEDROCK_APPROVED acknowledgement.'
    }
}
if ($EnableOpenDartLive) {
    if ($OpenDartAcknowledgement -ne 'JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED') {
        throw 'OpenDART live requires the separate JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED acknowledgement.'
    }
    if (-not $OpenDartBackendConfig -or -not $OpenDartApplyReceipt) {
        throw 'OpenDART live requires the approved serverless runtime backend configuration and apply receipt.'
    }
}
elseif ($RunOpenDartLiveSmoke) {
    throw '-RunOpenDartLiveSmoke requires -EnableOpenDartLive.'
}
if ($RunOpenDartLiveSmoke) {
    if ($OpenDartCallAcknowledgement -ne 'JCAREER_SYNTHETIC_ONLY') {
        throw 'OpenDART live smoke requires the separate synthetic-call acknowledgement.'
    }
    $normalisedDemoCompanyName = (($OpenDartDemoCompanyName -split '\s+') -join ' ').Trim()
    if ($OpenDartDemoCorpCode -notmatch '^[0-9]{8}$' -or $normalisedDemoCompanyName.Length -lt 2 -or $normalisedDemoCompanyName.Length -gt 120) {
        throw 'OpenDART live smoke requires an 8-digit corp code and the exact 2-120 character public company name.'
    }
}
if ($EnableAwsHttpsPreview -and $HttpsPreviewAcknowledgement -ne 'JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED') {
    throw 'AWS HTTPS preview requires the separate JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED acknowledgement.'
}

function Resolve-RequiredApplication {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Microsoft.PowerShell.Core\Get-Command `
        -Name $Name `
        -CommandType Application `
        -ErrorAction SilentlyContinue |
        Microsoft.PowerShell.Utility\Select-Object -First 1
    if ($null -eq $command -or -not [IO.File]::Exists([string]$command.Source)) {
        throw "$Name is required as a native application."
    }
    return [IO.Path]::GetFullPath([string]$command.Source)
}

$script:awsPath = Resolve-RequiredApplication -Name 'aws.exe'
$script:tarPath = Resolve-RequiredApplication -Name 'tar.exe'
$script:terraformPath = ''
$script:pythonPath = ''
if ($EnableOpenDartLive) {
    $script:terraformPath = Resolve-RequiredApplication -Name 'terraform.exe'
    $script:pythonPath = Resolve-RequiredApplication -Name 'python.exe'
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
$script:openDartBackendConfig = ''
$script:openDartApplyReceipt = ''
$script:openDartArtifactSha256 = ''
$script:openDartRuntime = $null
$script:labRoleName = ''
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
        '\b(i|vpc|subnet|sg|igw|rtb|eni|vol|nat|eipalloc|ami|snap)-[0-9a-f]+\b',
        '[REDACTED_RESOURCE_ID]',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $protected = [regex]::Replace(
        $protected,
        '(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)',
        '[REDACTED_IP]'
    )
    $protected = [regex]::Replace($protected, '\bvo_[A-Za-z0-9]+\b', '[REDACTED_VPC_ORIGIN_ID]')
    $protected = [regex]::Replace($protected, '\bE[A-Z0-9]{10,}\b', '[REDACTED_CLOUDFRONT_ID]')
    $protected = [regex]::Replace(
        $protected,
        '\b[a-z0-9.-]+\.cloudfront\.net\b',
        '[REDACTED_CLOUDFRONT_DOMAIN]',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    return $protected
}

function Invoke-AwsCli {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $previousErrorAction = $ErrorActionPreference
    try {
        # Windows PowerShell can turn ordinary native stderr into a terminating
        # ErrorRecord. AWS CLI exit status is the contract, so collect both
        # streams before deciding whether the command failed.
        $ErrorActionPreference = 'Continue'
        $result = @(& $script:awsPath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        $diagnostic = Protect-Diagnostic ($result -join [Environment]::NewLine)
        throw "AWS CLI command failed: $diagnostic"
    }
    return $result
}

function Invoke-LocalCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $result = @(& $FilePath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        $diagnostic = Protect-Diagnostic ($result -join [Environment]::NewLine)
        throw "$Label failed: $diagnostic"
    }
    return $result
}

function Test-ExactStringSet {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Observed,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Expected
    )

    if ($Observed.Count -ne $Expected.Count) { return $false }
    return @(
        Compare-Object -ReferenceObject @($Expected | Sort-Object) `
            -DifferenceObject @($Observed | Sort-Object)
    ).Count -eq 0
}

function Get-OpenDartRuntimeConfiguration {
    param(
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[A-Za-z0-9+=,.@_-]{3,64}$')]
        [string]$ExpectedApiRoleName
    )
    $terraformRoot = Join-Path $repoRoot 'terraform/serverless-opendart'
    Invoke-LocalCommand -FilePath $script:terraformPath -Label 'OpenDART remote-backend init' -Arguments @(
        "-chdir=$terraformRoot", 'init', '-reconfigure', '-input=false', '-no-color',
        '-lockfile=readonly',
        "-backend-config=$($script:openDartBackendConfig)"
    ) | Out-Null
    $stateLines = Invoke-LocalCommand -FilePath $script:terraformPath -Label 'OpenDART state inventory' -Arguments @(
        "-chdir=$terraformRoot", 'state', 'list'
    )
    $observed = @(
        $stateLines |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_ } |
            Sort-Object -Unique
    )
    $expected = @(
        'aws_cloudwatch_log_group.worker[0]',
        'aws_dynamodb_table.results[0]',
        'aws_ecr_lifecycle_policy.worker[0]',
        'aws_ecr_repository.worker[0]',
        'aws_iam_role.worker[0]',
        'aws_iam_role_policy.api[0]',
        'aws_iam_role_policy.worker[0]',
        'aws_lambda_event_source_mapping.refresh[0]',
        'aws_lambda_function.worker[0]',
        'aws_sqs_queue.dead_letter[0]',
        'aws_sqs_queue.refresh[0]'
    )
    if (-not (Test-ExactStringSet -Observed $observed -Expected $expected)) {
        throw 'OpenDART wiring requires the exact 11-resource runtime-stage state.'
    }
    $stage = (
        Invoke-LocalCommand -FilePath $script:terraformPath -Label 'OpenDART deployment stage' -Arguments @(
            "-chdir=$terraformRoot", 'output', '-raw', 'deployment_stage'
        ) | Select-Object -First 1
    ).Trim()
    if ($stage -ne 'runtime') {
        throw 'OpenDART remote state is not in the runtime stage.'
    }
    $stateJson = Invoke-LocalCommand -FilePath $script:terraformPath -Label 'OpenDART state binding' -Arguments @(
        "-chdir=$terraformRoot", 'show', '-json'
    )
    $stateDocument = (($stateJson -join [Environment]::NewLine) | ConvertFrom-Json)
    $lambda = @(
        $stateDocument.values.root_module.resources |
            Where-Object { [string]$_.address -eq 'aws_lambda_function.worker[0]' }
    )
    if (
        $lambda.Count -ne 1 -or
        [string]$lambda[0].values.image_uri -notmatch "@sha256:$($script:openDartArtifactSha256)$"
    ) {
        throw 'OpenDART Lambda state is not bound to the approved image digest.'
    }
    $apiRolePolicy = @(
        $stateDocument.values.root_module.resources |
            Where-Object { [string]$_.address -eq 'aws_iam_role_policy.api[0]' }
    )
    if (
        $apiRolePolicy.Count -ne 1 -or
        [string]$apiRolePolicy[0].values.role -ne $ExpectedApiRoleName
    ) {
        throw 'OpenDART sender policy is not attached to the validated lab instance role.'
    }
    $environmentJson = Invoke-LocalCommand -FilePath $script:terraformPath -Label 'OpenDART runtime environment' -Arguments @(
        "-chdir=$terraformRoot", 'output', '-json', 'runtime_environment'
    )
    $environment = (($environmentJson -join [Environment]::NewLine) | ConvertFrom-Json)
    $expectedKeys = @(
        'OPENDART_DISPATCH_MODE',
        'OPENDART_PENDING_TIMEOUT_SECONDS',
        'OPENDART_REFRESH_QUEUE_NAME',
        'OPENDART_RESULT_TABLE_NAME'
    )
    $observedKeys = @($environment.PSObject.Properties.Name | Sort-Object)
    if (-not (Test-ExactStringSet -Observed $observedKeys -Expected $expectedKeys)) {
        throw 'OpenDART runtime environment output differs from the exact broker contract.'
    }
    $queueName = [string]$environment.OPENDART_REFRESH_QUEUE_NAME
    $tableName = [string]$environment.OPENDART_RESULT_TABLE_NAME
    $pendingSeconds = [string]$environment.OPENDART_PENDING_TIMEOUT_SECONDS
    if (
        [string]$environment.OPENDART_DISPATCH_MODE -ne 'serverless_queue' -or
        $queueName -notmatch '^[a-z0-9][a-z0-9_-]{2,74}\.fifo$' -or
        $tableName -notmatch '^[a-z0-9][a-z0-9_.-]{2,79}$' -or
        $pendingSeconds -notmatch '^[0-9]{3,5}$' -or
        [int]$pendingSeconds -lt 900 -or
        [int]$pendingSeconds -gt 86400
    ) {
        throw 'OpenDART runtime environment values are outside the reviewed broker boundary.'
    }
    return [PSCustomObject]@{
        QueueName = $queueName
        TableName = $tableName
        PendingTimeoutSeconds = $pendingSeconds
    }
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
        $invocationJson = @()
        $invocationExitCode = 1
        $previousErrorAction = $ErrorActionPreference
        try {
            # A newly accepted SSM command can briefly return
            # InvocationDoesNotExist. Treat that as a poll miss, not a script
            # failure, while preserving real terminal command states below.
            $ErrorActionPreference = 'Continue'
            $invocationJson = @(& $script:awsPath ssm get-command-invocation --region $Region `
                --command-id $commandId --instance-id $InstanceId --output json 2>&1)
            $invocationExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $previousErrorAction
        }
        if ($invocationExitCode -eq 0) {
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
    $profileRaw = Invoke-AwsCli -Arguments @(
        'iam', 'get-instance-profile', '--instance-profile-name', $profileName,
        '--output', 'json', '--no-cli-pager'
    )
    $profileDocument = (($profileRaw -join [Environment]::NewLine) | ConvertFrom-Json)
    $roles = @($profileDocument.InstanceProfile.Roles)
    if (
        [string]$profileDocument.InstanceProfile.InstanceProfileName -ne $profileName -or
        $roles.Count -ne 1 -or
        [string]$roles[0].RoleName -notmatch '^[A-Za-z0-9+=,.@_-]{3,64}$'
    ) {
        throw 'The validated lab instance profile must resolve to exactly one IAM role.'
    }
    $script:labRoleName = [string]$roles[0].RoleName
    $expectedBedrockTag = $EnableBedrockLive.ToString().ToLowerInvariant()
    if ($tags['jk_bedrock_live'] -ne $expectedBedrockTag) {
        throw 'The requested Bedrock mode does not match the Terraform-managed instance tag.'
    }
    $expectedOpenDartTag = $EnableOpenDartLive.ToString().ToLowerInvariant()
    if ($tags['jk_opendart_live'] -ne $expectedOpenDartTag) {
        throw 'The requested OpenDART mode does not match the Terraform-managed instance tag.'
    }
    $expectedPreviewTag = $EnableAwsHttpsPreview.ToString().ToLowerInvariant()
    if ($tags['jk_https_preview'] -ne $expectedPreviewTag) {
        throw 'The requested HTTPS preview mode does not match the Terraform-managed instance tag.'
    }
    return $instance
}

function Assert-PreviewIngressBoundary {
    param([Parameter(Mandatory = $true)]$Instance)

    $groupIds = @($Instance.SecurityGroups | ForEach-Object { [string]$_.GroupId })
    if ($groupIds.Count -ne 1) {
        throw 'The reviewed lab instance must have exactly one security group.'
    }
    $rawGroups = Invoke-AwsCli -Arguments @(
        'ec2', 'describe-security-groups', '--region', $Region,
        '--group-ids', $groupIds[0], '--output', 'json', '--no-cli-pager'
    )
    $groups = @((($rawGroups -join [Environment]::NewLine) | ConvertFrom-Json).SecurityGroups)
    if ($groups.Count -ne 1) {
        throw 'The runtime security group did not resolve exactly once.'
    }
    $permissions = @($groups[0].IpPermissions)

    if (-not $EnableAwsHttpsPreview) {
        if ($permissions.Count -ne 0) {
            throw 'Private lab mode requires zero security-group ingress permissions.'
        }
        return
    }

    $publicIpProperty = $Instance.PSObject.Properties['PublicIpAddress']
    if (
        $null -ne $publicIpProperty -and
        -not [string]::IsNullOrWhiteSpace([string]$publicIpProperty.Value)
    ) {
        throw 'HTTPS preview instance must not have a public IP.'
    }
    $rawSubnets = Invoke-AwsCli -Arguments @(
        'ec2', 'describe-subnets', '--region', $Region,
        '--subnet-ids', [string]$Instance.SubnetId, '--output', 'json', '--no-cli-pager'
    )
    $subnets = @((($rawSubnets -join [Environment]::NewLine) | ConvertFrom-Json).Subnets)
    if ($subnets.Count -ne 1 -or $subnets[0].MapPublicIpOnLaunch -ne $false) {
        throw 'HTTPS preview VPC origin must resolve to one subnet with public-IP mapping disabled.'
    }

    $rawServiceGroups = Invoke-AwsCli -Arguments @(
        'ec2', 'describe-security-groups', '--region', $Region,
        '--filters', "Name=vpc-id,Values=$([string]$Instance.VpcId)",
        'Name=group-name,Values=CloudFront-VPCOrigins-Service-SG',
        '--output', 'json', '--no-cli-pager'
    )
    $serviceGroups = @((($rawServiceGroups -join [Environment]::NewLine) | ConvertFrom-Json).SecurityGroups)
    if ($serviceGroups.Count -ne 1) {
        throw 'The CloudFront VPC origin service-managed security group did not resolve exactly once.'
    }
    $permission = if ($permissions.Count -eq 1) { $permissions[0] } else { $null }
    $sourceGroups = @()
    if ($null -ne $permission) {
        $sourceGroups = @($permission.UserIdGroupPairs)
    }
    $isExactBoundary = (
        $null -ne $permission -and
        [string]$permission.IpProtocol -eq 'tcp' -and
        [int]$permission.FromPort -eq 3000 -and
        [int]$permission.ToPort -eq 3000 -and
        $sourceGroups.Count -eq 1 -and
        [string]$sourceGroups[0].GroupId -eq [string]$serviceGroups[0].GroupId -and
        @($permission.IpRanges).Count -eq 0 -and
        @($permission.Ipv6Ranges).Count -eq 0 -and
        @($permission.PrefixListIds).Count -eq 0
    )
    if (-not $isExactBoundary) {
        throw 'HTTPS preview ingress is not restricted to the exact CloudFront VPC origin service SG on TCP/3000.'
    }
}

try {
    Write-Host '[preflight] Validating target tags, state, type, provider flags, and ingress boundary...'
    $validatedInstance = Get-ValidatedLabInstance
    # These tag, type, and instance-profile checks establish the bounded stop
    # target. Later ingress or linked-provider failures must still request stop.
    $script:validatedTarget = $true
    Assert-PreviewIngressBoundary -Instance $validatedInstance

    if ($EnableOpenDartLive) {
        $script:openDartBackendConfig = (Resolve-Path -LiteralPath $OpenDartBackendConfig).Path
        $script:openDartApplyReceipt = (Resolve-Path -LiteralPath $OpenDartApplyReceipt).Path
        $backendHash = (Get-FileHash -LiteralPath $script:openDartBackendConfig -Algorithm SHA256).Hash.ToLowerInvariant()
        Invoke-LocalCommand -FilePath $script:pythonPath -Label 'OpenDART backend contract' -Arguments @(
            (Join-Path $repoRoot 'scripts/check_terraform_backend_config.py'),
            '--config', $script:openDartBackendConfig,
            '--terraform-root', 'serverless-opendart'
        ) | Out-Null
        Invoke-LocalCommand -FilePath $script:pythonPath -Label 'OpenDART receipt binding' -Arguments @(
            (Join-Path $repoRoot 'scripts/check_opendart_runtime_binding.py'),
            '--receipt', $script:openDartApplyReceipt,
            '--backend-config-sha256', $backendHash
        ) | Out-Null
        $applyReceipt = Get-Content -LiteralPath $script:openDartApplyReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
        $script:openDartArtifactSha256 = [string]$applyReceipt.artifact_sha256
    }

    if ($EnableOpenDartLive) {
        $script:openDartRuntime = Get-OpenDartRuntimeConfiguration `
            -ExpectedApiRoleName $script:labRoleName
    }

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
        & $script:tarPath -czf $archivePath `
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
    $webBindAddress = if ($EnableAwsHttpsPreview) { '0.0.0.0' } else { '127.0.0.1' }
    $openDartEnvironmentTokens = "'OPENDART_DISPATCH_MODE=fixture_inline'"
    $composeFileArguments = '-f compose.yaml -f ../../terraform/lab/provisioning/lab.compose.override.yaml'
    $hostPreparationCommands = @()
    if ($EnableOpenDartLive) {
        $openDartEnvironmentTokens = (
            "'OPENDART_DISPATCH_MODE=serverless_queue' " +
            "'OPENDART_REFRESH_QUEUE_NAME=$($script:openDartRuntime.QueueName)' " +
            "'OPENDART_RESULT_TABLE_NAME=$($script:openDartRuntime.TableName)' " +
            "'OPENDART_PENDING_TIMEOUT_SECONDS=$($script:openDartRuntime.PendingTimeoutSeconds)'"
        )
        $composeFileArguments += ' -f ../../terraform/lab/provisioning/opendart-broker.compose.override.yaml'
        $hostPreparationCommands += @(
            'test ! -L /run/jcareer-opendart',
            "printf '%s\n' 'd /run/jcareer-opendart 0750 11001 11001 -' > /etc/tmpfiles.d/jcareer-opendart.conf",
            'systemd-tmpfiles --create /etc/tmpfiles.d/jcareer-opendart.conf',
            'test "$(stat -c ''%u:%g:%a'' /run/jcareer-opendart)" = "11001:11001:750"'
        )
    }
    if ($EnableBedrockLive) {
        $composeFileArguments += ' -f ../../terraform/lab/provisioning/bedrock-broker.compose.override.yaml'
        $hostPreparationCommands += @(
            'test ! -L /run/jcareer-bedrock',
            "printf '%s\n' 'd /run/jcareer-bedrock 0750 11002 11002 -' > /etc/tmpfiles.d/jcareer-bedrock.conf",
            'systemd-tmpfiles --create /etc/tmpfiles.d/jcareer-bedrock.conf',
            'test "$(stat -c ''%u:%g:%a'' /run/jcareer-bedrock)" = "11002:11002:750"'
        )
    }
    Write-Host ("[5/8] Building and starting the core runtime with provider={0}, OpenDART broker={1}..." -f $provider, $EnableOpenDartLive)
    $environmentCommand = @"
printf '%s\n' 'LLM_PROVIDER=$provider' 'ALLOW_BEDROCK_LIVE=$allowBedrockLive' 'BEDROCK_REGION=$Region' 'BEDROCK_MODEL_ID=$BedrockModelId' 'WEB_BIND_ADDRESS=$webBindAddress' 'ASIS_RAW_PROMPT_LOG=true' $openDartEnvironmentTokens "SESSION_SIGNING_KEY=`$session_key" > .env
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
        'session_key=$(openssl rand -hex 32)'
    ) + $hostPreparationCommands + @(
        $environmentCommand,
        'chmod 0600 .env',
        'export COMPOSE_PARALLEL_LIMIT=1',
        "docker compose $composeFileArguments up --build -d --wait --wait-timeout 420 --remove-orphans"
    )
    Invoke-RemoteCommand -Comment 'Deploy J-Career synthetic runtime' -Commands $deployCommands -TimeoutSeconds 1200 | Out-Null

    $boundaryCommands = @(
        'set -euo pipefail',
        'cd /opt/jcareer-release/src/runtime',
        "test `$(docker compose $composeFileArguments exec -T api id -u) -eq 11001",
        "docker compose $composeFileArguments exec -T api sh -c 'test `"`$AWS_EC2_METADATA_DISABLED`" = true && test -z `"`$AWS_ACCESS_KEY_ID`$AWS_SECRET_ACCESS_KEY`$AWS_SESSION_TOKEN`$AWS_WEB_IDENTITY_TOKEN_FILE`$AWS_ROLE_ARN`$AWS_SHARED_CREDENTIALS_FILE`$AWS_PROFILE`"'",
        "test `$(docker compose $composeFileArguments exec -T llm-gateway id -u) -eq 11002",
        "docker compose $composeFileArguments exec -T llm-gateway sh -c 'test `"`$AWS_EC2_METADATA_DISABLED`" = true && test -z `"`$AWS_ACCESS_KEY_ID`$AWS_SECRET_ACCESS_KEY`$AWS_SESSION_TOKEN`$AWS_WEB_IDENTITY_TOKEN_FILE`$AWS_ROLE_ARN`$AWS_SHARED_CREDENTIALS_FILE`$AWS_PROFILE`"'",
        "docker compose $composeFileArguments exec -T api sh -c 'test ! -e /run/jcareer-bedrock/broker.sock'",
        "docker compose $composeFileArguments exec -T llm-gateway sh -c 'test ! -e /run/jcareer-opendart/broker.sock'"
    )
    if ($EnableOpenDartLive) {
        $boundaryCommands += @(
            "opendart_id=`$(docker compose $composeFileArguments ps -q opendart-broker)",
            'test -n "$opendart_id"',
            'test "$(docker inspect -f ''{{.HostConfig.NetworkMode}}'' "$opendart_id")" = host',
            'test "$(stat -c ''%u:%g:%a'' /var/run/jcareer-opendart/broker.sock)" = 11001:11001:660',
            "docker compose $composeFileArguments exec -T api test -S /run/jcareer-opendart/broker.sock"
        )
    }
    if ($EnableBedrockLive) {
        $boundaryCommands += @(
            "bedrock_id=`$(docker compose $composeFileArguments ps -q bedrock-broker)",
            'test -n "$bedrock_id"',
            'test "$(docker inspect -f ''{{.HostConfig.NetworkMode}}'' "$bedrock_id")" = host',
            'test "$(stat -c ''%u:%g:%a'' /var/run/jcareer-bedrock/broker.sock)" = 11002:11002:660',
            "docker compose $composeFileArguments exec -T llm-gateway test -S /run/jcareer-bedrock/broker.sock"
        )
    }
    Invoke-RemoteCommand -Comment 'Verify J-Career AWS capability broker boundaries' -Commands $boundaryCommands -TimeoutSeconds 300 | Out-Null

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

    if ($RunOpenDartLiveSmoke) {
        $companyNameBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($normalisedDemoCompanyName))
        $openDartSmoke = Invoke-RemoteCommand -Comment 'Verify one approved OpenDART external call' -Commands @(
            'set -euo pipefail',
            'cd /opt/jcareer-release/src/runtime',
            "demo_company=`$(printf '%s' '$companyNameBase64' | base64 -d)",
            "CONFIRM_SYNTHETIC_OPENDART_CALL=JCAREER_SYNTHETIC_ONLY OPENDART_DEMO_CORP_CODE='$OpenDartDemoCorpCode' OPENDART_DEMO_COMPANY_NAME=`"`$demo_company`" python3 tests/opendart_live_smoke.py"
        ) -TimeoutSeconds 360
        if ($openDartSmoke -notmatch 'J-Career OpenDART live smoke: PASS') {
            throw 'OpenDART external call completed without the expected PASS marker.'
        }
        Write-Host 'OpenDART external call observation: PASS (public-company snapshot only; score effect NONE).'
    }

    if ($EnableAwsHttpsPreview) {
        Write-Host '[8/8] PASS - runtime checks completed; the gated AWS HTTPS entrypoint may now be verified.'
    }
    else {
        Write-Host '[8/8] PASS - runtime checks completed; connect only through an approved SSM local tunnel.'
    }
}
catch {
    $failure = $_
    if ($script:validatedTarget -and -not $PreserveInstanceOnFailure) {
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
    elseif ($script:validatedTarget) {
        Write-Warning 'Deployment or verification failed; the validated lab instance remains running by explicit operator request.'
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
