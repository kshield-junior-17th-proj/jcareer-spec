[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackendConfig,
    [Parameter(Mandatory = $true)][string]$ApprovalFile,
    [Parameter(Mandatory = $true)][string]$BuildObservation,
    [Parameter(Mandatory = $true)][string]$PrivateInventory,
    [Parameter(Mandatory = $true)][string]$EndpointBackendConfig,
    [Parameter(Mandatory = $true)][string]$EndpointDispositionObservation,
    [string]$EndpointTeardownReceipt = '',
    [Parameter(Mandatory = $true)]
    [ValidateSet('JCAREER_WINDOWS_IMAGE_DELETED_RECOVERY_OBSERVATION_APPROVED')]
    [string]$ActivationAcknowledgement
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Import-Module (Join-Path $PSScriptRoot 'JCareer-ProtectedInputSnapshot.psm1') `
    -Force -ErrorAction Stop
$imageTerraformRelative = 'terraform/workplace-images'
$endpointTerraformRelative = 'terraform/workplace-endpoints'
$workDirectory = Join-Path (Resolve-Path (Join-Path $repoRoot $imageTerraformRelative)).Path '.terraform'
$normalCleanupReceipt = Join-Path $workDirectory 'last-image-cleanup-receipt.json'
$recoveryRecordRoot = Join-Path $workDirectory 'image-deleted-recovery'
$legacyRecoveryObservationFile = Join-Path $workDirectory 'last-image-deleted-recovery-observation.json'
$legacyRecoveryReceiptFile = Join-Path $workDirectory 'last-image-deleted-recovery-receipt.json'
$recoveryObservationFile = ''
$recoveryReceiptFile = ''
$utf8WithoutBom = [Text.UTF8Encoding]::new($false)
$script:artifactOperationLeaseMutex = $null
$script:artifactOperationLeaseAcquired = $false
$script:artifactOperationLeaseName = ''
$script:awsExecutable = ''
$script:terraformExecutable = ''
$script:pythonExecutable = ''

function New-ProtectedEmptyFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string]$AclTemplatePath = ''
    )
    $stream = [IO.File]::Open(
        $Path,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::None
    )
    $stream.Dispose()
    if ($AclTemplatePath -and [IO.File]::Exists($AclTemplatePath)) {
        Set-Acl -LiteralPath $Path -AclObject (Get-Acl -LiteralPath $AclTemplatePath)
        return
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [Security.AccessControl.FileSecurity]::new()
    $acl.SetOwner($identity)
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $identity,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow
    ))
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Write-JsonUtf8NoBom {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value,
        [ValidateRange(2, 100)][int]$Depth = 10
    )
    $fullPath = [IO.Path]::GetFullPath($Path)
    $directory = [IO.Path]::GetDirectoryName($fullPath)
    $temporaryPath = Join-Path $directory ('.jcareer-json-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        New-ProtectedEmptyFile -Path $temporaryPath -AclTemplatePath $fullPath
        [IO.File]::WriteAllText(
            $temporaryPath,
            ($Value | ConvertTo-Json -Depth $Depth),
            $utf8WithoutBom
        )
        if ([IO.File]::Exists($fullPath)) {
            [IO.File]::Replace($temporaryPath, $fullPath, $null)
        }
        else { [IO.File]::Move($temporaryPath, $fullPath) }
    }
    finally {
        if ([IO.File]::Exists($temporaryPath)) { [IO.File]::Delete($temporaryPath) }
    }
}

function Get-Sha256Text {
    param([Parameter(Mandatory = $true)][string]$Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)) }
    finally { $sha.Dispose() }
    return -join ($hash | ForEach-Object { $_.ToString('x2') })
}

function Protect-Diagnostic {
    param([AllowEmptyString()][string]$Text)
    $protected = $Text -replace '(?<!\d)\d{12}(?!\d)', '[REDACTED_ACCOUNT]'
    $protected = $protected -replace 'arn:aws[^\s"'']+', '[REDACTED_ARN]'
    $protected = $protected -replace '(?:AKIA|ASIA)[A-Z0-9]{16}', '[REDACTED_ACCESS_KEY]'
    $protected = $protected -replace '\b(i|vpc|subnet|sg|ami|snap)-[0-9a-f]+\b', '[REDACTED_RESOURCE_ID]'
    $protected = $protected -replace '(?i)\bs3://[^\s"'']+', '[REDACTED_S3_LOCATION]'
    $protected = $protected -replace '(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])', '[REDACTED_IP]'
    $protected = $protected -replace '(?i)\b(bucket|key|dynamodb_table|profile|role_arn|workspace_key_prefix|owner|session(?:id)?|user(?:name)?)(\s*[=:]\s*)(?:"[^"]*"|''[^'']*''|[^\s,]+)', '$1$2[REDACTED_VALUE]'
    $protected = $protected -replace '(?i)\b(S3 bucket|object key|DynamoDB table)\s+(?:"[^"]*"|''[^'']*'')', '$1 [REDACTED_VALUE]'
    $protected = $protected -replace '(?i)(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![0-9a-f:])', '[REDACTED_IPV6]'
    return $protected
}

function Invoke-AwsJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $stderrPath = Join-Path ([IO.Path]::GetTempPath()) ('jcareer-aws-stderr-' + [Guid]::NewGuid().ToString('N') + '.txt')
    $previous = $ErrorActionPreference
    $output = @()
    $stderr = ''
    $exitCode = -1
    try {
        New-ProtectedEmptyFile -Path $stderrPath
        $ErrorActionPreference = 'Continue'
        $output = @(& $script:awsExecutable @Arguments 2> $stderrPath)
        $exitCode = $LASTEXITCODE
        if ([IO.File]::Exists($stderrPath)) { $stderr = [IO.File]::ReadAllText($stderrPath) }
    }
    finally {
        $ErrorActionPreference = $previous
        if ([IO.File]::Exists($stderrPath)) { [IO.File]::Delete($stderrPath) }
    }
    if ($exitCode -ne 0) {
        throw (Protect-Diagnostic ((@($output) + @($stderr)) -join "`n"))
    }
    if ($stderr) {
        Write-Warning 'AWS CLI emitted a diagnostic while returning successful JSON; diagnostic text was suppressed.'
    }
    return (($output -join "`n") | ConvertFrom-Json)
}

function Get-EndpointStateCount {
    $addresses = @(
        & $script:terraformExecutable -chdir=$endpointTerraformRelative `
            state list -no-color 2>&1
    )
    if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($addresses -join "`n")) }
    return @($addresses | Where-Object {
        -not [string]::IsNullOrWhiteSpace([string]$_)
    }).Count
}

function Get-RecoverySnapshot {
    param(
        [Parameter(Mandatory = $true)][string]$BuildArn,
        [Parameter(Mandatory = $true)][array]$AmiArtifacts
    )
    $image = Invoke-AwsJson @(
        'imagebuilder', 'get-image', '--region', 'ap-northeast-2',
        '--image-build-version-arn', $BuildArn, '--output', 'json', '--no-cli-pager'
    )
    if (
        [string]$image.image.arn -ne $BuildArn -or
        [string]$image.image.state.status -ne 'DELETED'
    ) {
        throw 'The exact Image Builder build was not returned in DELETED state.'
    }

    $activeStates = 'pending,running,shutting-down,stopping,stopped'
    $activeInstanceCount = 0
    foreach ($artifact in $AmiArtifacts) {
        $active = Invoke-AwsJson @(
            'ec2', 'describe-instances', '--region', [string]$artifact.region,
            '--filters', "Name=image-id,Values=$([string]$artifact.ami_id)",
            "Name=instance-state-name,Values=$activeStates",
            '--output', 'json', '--no-cli-pager'
        )
        $activeInstanceCount += @(
            $active.Reservations | ForEach-Object { $_.Instances }
        ).Count
    }

    $residualAmiCount = 0
    foreach ($artifact in $AmiArtifacts) {
        try {
            $document = Invoke-AwsJson @(
                'ec2', 'describe-images', '--region', [string]$artifact.region,
                '--image-ids', [string]$artifact.ami_id,
                '--output', 'json', '--no-cli-pager'
            )
            $residualAmiCount += @($document.Images).Count
        }
        catch {
            $message = Protect-Diagnostic $_.Exception.Message
            if ($message -notmatch 'InvalidAMIID\.NotFound') { throw $message }
        }
    }

    $residualSnapshotCount = 0
    foreach ($artifact in $AmiArtifacts) {
        foreach ($snapshotId in @($artifact.snapshot_ids)) {
            try {
                $document = Invoke-AwsJson @(
                    'ec2', 'describe-snapshots', '--region', [string]$artifact.region,
                    '--snapshot-ids', [string]$snapshotId,
                    '--output', 'json', '--no-cli-pager'
                )
                $residualSnapshotCount += @($document.Snapshots).Count
            }
            catch {
                $message = Protect-Diagnostic $_.Exception.Message
                if ($message -notmatch 'InvalidSnapshot\.NotFound') { throw $message }
            }
        }
    }
    return [pscustomobject]@{
        ActiveInstanceCount = $activeInstanceCount
        ResidualAmiCount = $residualAmiCount
        ResidualSnapshotCount = $residualSnapshotCount
    }
}

function Assert-FileHashUnchanged {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Expected
    )
    $observed = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($observed -ne $Expected) { throw 'An approval-bound input changed during recovery observation.' }
}

function Assert-ExactRecord {
    param(
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)][string]$TimestampField
    )
    $actualNames = @($Actual.PSObject.Properties.Name | Sort-Object)
    $expectedNames = @($Expected.Keys | Sort-Object)
    if (@(Compare-Object $expectedNames $actualNames).Count -ne 0) {
        throw 'Existing recovery record keys differ from the exact schema.'
    }
    try { [void][DateTimeOffset]::Parse([string]$Actual.$TimestampField) }
    catch { throw 'Existing recovery record timestamp is invalid.' }
    $Expected[$TimestampField] = [string]$Actual.$TimestampField
    foreach ($name in $expectedNames) {
        $left = $Actual.$name | ConvertTo-Json -Depth 20 -Compress
        $right = $Expected[$name] | ConvertTo-Json -Depth 20 -Compress
        if ($left -cne $right) { throw 'Existing recovery record conflicts with the current exact inputs.' }
    }
}

$awsCommand = Get-Command 'aws.exe' -CommandType Application -ErrorAction Stop |
    Select-Object -First 1
$terraformCommand = Get-Command 'terraform.exe' -CommandType Application -ErrorAction Stop |
    Select-Object -First 1
$pythonCommand = Get-Command 'python.exe' -CommandType Application -ErrorAction Stop |
    Select-Object -First 1
$script:awsExecutable = [IO.Path]::GetFullPath([string]$awsCommand.Source)
$script:terraformExecutable = [IO.Path]::GetFullPath([string]$terraformCommand.Source)
$script:pythonExecutable = [IO.Path]::GetFullPath([string]$pythonCommand.Source)
foreach ($executable in @(
    $script:awsExecutable, $script:terraformExecutable, $script:pythonExecutable
)) {
    if (-not [IO.File]::Exists($executable)) { throw 'One required application path is invalid.' }
}
$awsVersion = @(& $script:awsExecutable --version 2>&1)
if ($LASTEXITCODE -ne 0 -or ($awsVersion -join '') -notmatch '^aws-cli/2\.') {
    throw 'AWS CLI v2 is required for read-only deleted-state recovery observation.'
}

$resolvedBackend = (Resolve-Path $BackendConfig).Path
$resolvedApproval = (Resolve-Path $ApprovalFile).Path
$resolvedObservation = (Resolve-Path $BuildObservation).Path
$resolvedInventory = (Resolve-Path $PrivateInventory).Path
$resolvedEndpointBackend = (Resolve-Path $EndpointBackendConfig).Path
$resolvedEndpointDisposition = (Resolve-Path $EndpointDispositionObservation).Path
$resolvedEndpointTeardown = if ($EndpointTeardownReceipt) {
    (Resolve-Path $EndpointTeardownReceipt).Path
} else { '' }
New-Item -ItemType Directory -Path $workDirectory -Force | Out-Null
$backendCheckerSource = (Resolve-Path (
    Join-Path $repoRoot 'scripts/check_terraform_backend_config.py'
)).Path
$operationCheckerSource = (Resolve-Path (
    Join-Path $repoRoot 'scripts/check_windows_image_operation_approval.py'
)).Path
$receiptCheckerSource = (Resolve-Path (
    Join-Path $repoRoot 'scripts/check_windows_image_receipt.py'
)).Path
$snapshotSet = $null
$operationCompleted = $false
try {
$snapshotSet = New-JCareerProtectedSnapshotSet `
    -RootPath ([IO.Path]::GetTempPath()) -Prefix 'jcareer-image-recovery'
$snapshotBackend = Add-JCareerProtectedSnapshotFile `
    -SnapshotSet $snapshotSet -Source $resolvedBackend `
    -DestinationName 'image-backend.tfbackend'
$snapshotApproval = Add-JCareerProtectedSnapshotFile `
    -SnapshotSet $snapshotSet -Source $resolvedApproval `
    -DestinationName 'recovery-approval.json'
$snapshotObservation = Add-JCareerProtectedSnapshotFile `
    -SnapshotSet $snapshotSet -Source $resolvedObservation `
    -DestinationName 'build-observation.json'
$snapshotInventory = Add-JCareerProtectedSnapshotFile `
    -SnapshotSet $snapshotSet -Source $resolvedInventory `
    -DestinationName 'private-inventory.json'
$snapshotEndpointBackend = Add-JCareerProtectedSnapshotFile `
    -SnapshotSet $snapshotSet -Source $resolvedEndpointBackend `
    -DestinationName 'endpoint-backend.tfbackend'
$snapshotEndpointDisposition = Add-JCareerProtectedSnapshotFile `
    -SnapshotSet $snapshotSet -Source $resolvedEndpointDisposition `
    -DestinationName 'endpoint-disposition-observation.json'
$snapshotBackendChecker = Add-JCareerProtectedSnapshotFile `
    -SnapshotSet $snapshotSet -Source $backendCheckerSource `
    -DestinationName 'check_terraform_backend_config.py'
$snapshotOperationChecker = Add-JCareerProtectedSnapshotFile `
    -SnapshotSet $snapshotSet -Source $operationCheckerSource `
    -DestinationName 'check_windows_image_operation_approval.py'
$snapshotReceiptChecker = Add-JCareerProtectedSnapshotFile `
    -SnapshotSet $snapshotSet -Source $receiptCheckerSource `
    -DestinationName 'check_windows_image_receipt.py'
$snapshotEndpointTeardown = if ($resolvedEndpointTeardown) {
    Add-JCareerProtectedSnapshotFile `
        -SnapshotSet $snapshotSet -Source $resolvedEndpointTeardown `
        -DestinationName 'endpoint-teardown-receipt.json'
} else { '' }
$expectedSnapshotCount = if ($snapshotEndpointTeardown) { 10 } else { 9 }
if ($snapshotSet.Count -ne $expectedSnapshotCount) {
    throw 'Image-recovery protected input snapshot set is incomplete.'
}

$approvalHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotApproval).Hash.ToLowerInvariant()
$recoveryRunDirectory = Join-Path $recoveryRecordRoot $approvalHash
$recoveryObservationFile = Join-Path $recoveryRunDirectory 'observation.json'
$recoveryReceiptFile = Join-Path $recoveryRunDirectory 'receipt.json'
$backendHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotBackend).Hash.ToLowerInvariant()
$observationHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotObservation).Hash.ToLowerInvariant()
$inventoryHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotInventory).Hash.ToLowerInvariant()
$endpointBackendHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotEndpointBackend).Hash.ToLowerInvariant()
$endpointDispositionHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotEndpointDisposition).Hash.ToLowerInvariant()
$endpointTeardownHash = if ($snapshotEndpointTeardown) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotEndpointTeardown).Hash.ToLowerInvariant()
} else { '' }

& $script:pythonExecutable -E -s -S -B $snapshotBackendChecker `
    --config $snapshotBackend --terraform-root workplace-images
if ($LASTEXITCODE -ne 0) { throw 'Image backend configuration failed its contract.' }
$canonicalBackendOutput = @(
    & $script:pythonExecutable -E -s -S -B $snapshotBackendChecker `
        --config $snapshotBackend --terraform-root workplace-images `
        --print-canonical-sha256 2>&1
)
$canonicalBackendHash = ($canonicalBackendOutput -join '').Trim()
if ($LASTEXITCODE -ne 0 -or $canonicalBackendHash -notmatch '^[0-9a-f]{64}$') {
    throw 'Image logical backend identity could not be derived.'
}
$script:artifactOperationLeaseName = 'Global\JCareerImageArtifactOperation-' + $canonicalBackendHash
$createdNew = $false
try {
    $script:artifactOperationLeaseMutex = [Threading.Mutex]::new(
        $false, $script:artifactOperationLeaseName, [ref]$createdNew
    )
    try { $script:artifactOperationLeaseAcquired = $script:artifactOperationLeaseMutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $script:artifactOperationLeaseAcquired = $true }
    if (-not $script:artifactOperationLeaseAcquired) {
        throw 'The image-backend lease is already held.'
    }
}
catch {
    if ($null -ne $script:artifactOperationLeaseMutex) {
        $script:artifactOperationLeaseMutex.Dispose()
        $script:artifactOperationLeaseMutex = $null
    }
    throw 'Another local image cleanup or recovery operation holds the shared backend lease.'
}

try {
if (Test-Path -LiteralPath $normalCleanupReceipt -PathType Leaf) {
    throw 'A normal cleanup receipt already exists; use that record instead of recovery observation.'
}
if (
    (Test-Path -LiteralPath $legacyRecoveryObservationFile -PathType Leaf) -or
    (Test-Path -LiteralPath $legacyRecoveryReceiptFile -PathType Leaf)
) {
    throw 'A legacy fixed-path recovery record requires human disposition before recovery.'
}
if (
    (Test-Path -LiteralPath $recoveryReceiptFile -PathType Leaf) -and
    -not (Test-Path -LiteralPath $recoveryObservationFile -PathType Leaf)
) {
    throw 'A recovery receipt exists without its bound observation; human disposition is required.'
}

& $script:pythonExecutable -E -s -S -B $snapshotBackendChecker `
    --config $snapshotEndpointBackend --terraform-root workplace-endpoints
if ($LASTEXITCODE -ne 0) { throw 'Endpoint backend configuration failed its contract.' }
$checkerArguments = @(
    $snapshotOperationChecker, 'recovery',
    '--approval', $snapshotApproval,
    '--backend-config-sha256', $backendHash,
    '--build-observation', $snapshotObservation,
    '--secure-inventory', $snapshotInventory,
    '--endpoint-backend-config', $snapshotEndpointBackend,
    '--endpoint-disposition-observation', $snapshotEndpointDisposition,
    '--require-approved'
)
if ($snapshotEndpointTeardown) {
    $checkerArguments += @('--endpoint-teardown-receipt', $snapshotEndpointTeardown)
}
& $script:pythonExecutable -E -s -S -B @checkerArguments
if ($LASTEXITCODE -ne 0) { throw 'Read-only recovery approval did not match the exact inputs.' }

$approval = Get-Content -LiteralPath $snapshotApproval -Raw -Encoding UTF8 | ConvertFrom-Json
$inventory = Get-Content -LiteralPath $snapshotInventory -Raw -Encoding UTF8 | ConvertFrom-Json
$approvalStartedAt = [DateTimeOffset]::Parse([string]$approval.approved_at).ToUniversalTime()
$approvalExpiresAt = [DateTimeOffset]::Parse([string]$approval.expires_at).ToUniversalTime()
$buildArn = [string]$inventory.image_build_version_arn
if ($buildArn -notmatch '^arn:aws:imagebuilder:ap-northeast-2:\d{12}:image/[a-z0-9-_]+/\d+\.\d+\.\d+/\d+$') {
    throw 'Private inventory does not contain one expected image build ARN.'
}
$amiArtifacts = @($inventory.ami_artifacts)

$imageInit = @(
    & $script:terraformExecutable -chdir=$imageTerraformRelative init -reconfigure `
        -input=false -lockfile=readonly "-backend-config=$snapshotBackend" 2>&1
)
if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($imageInit -join "`n")) }
$endpointInit = @(
    & $script:terraformExecutable -chdir=$endpointTerraformRelative init -reconfigure `
        -input=false -lockfile=readonly "-backend-config=$snapshotEndpointBackend" 2>&1
)
if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($endpointInit -join "`n")) }

$firstEndpointStateCount = Get-EndpointStateCount
$first = Get-RecoverySnapshot -BuildArn $buildArn -AmiArtifacts $amiArtifacts
$secondEndpointStateCount = Get-EndpointStateCount
$second = Get-RecoverySnapshot -BuildArn $buildArn -AmiArtifacts $amiArtifacts
if (
    $firstEndpointStateCount -ne 0 -or
    $secondEndpointStateCount -ne 0 -or
    $first.ActiveInstanceCount -ne 0 -or
    $second.ActiveInstanceCount -ne 0 -or
    $first.ResidualAmiCount -ne 0 -or
    $second.ResidualAmiCount -ne 0 -or
    $first.ResidualSnapshotCount -ne 0 -or
    $second.ResidualSnapshotCount -ne 0
) {
    throw 'Read-only recovery requires repeated endpoint, active-instance, and scoped-residual zero observations.'
}

foreach ($binding in @(
    @($snapshotApproval, $approvalHash),
    @($snapshotBackend, $backendHash),
    @($snapshotObservation, $observationHash),
    @($snapshotInventory, $inventoryHash),
    @($snapshotEndpointBackend, $endpointBackendHash),
    @($snapshotEndpointDisposition, $endpointDispositionHash)
)) {
    Assert-FileHashUnchanged -Path $binding[0] -Expected $binding[1]
}
if ($snapshotEndpointTeardown) {
    Assert-FileHashUnchanged -Path $snapshotEndpointTeardown -Expected $endpointTeardownHash
}
if ([DateTimeOffset]::UtcNow -ge $approvalExpiresAt) {
    throw 'The recovery approval expired before the observation was recorded.'
}
if (Test-Path -LiteralPath $normalCleanupReceipt -PathType Leaf) {
    throw 'A normal cleanup receipt appeared during recovery; no recovery record was written.'
}
Remove-JCareerProtectedSnapshotSet -SnapshotSet $snapshotSet
$snapshotSet = $null
New-Item -ItemType Directory -Path $recoveryRunDirectory -Force | Out-Null

$observation = [ordered]@{
    schema_version = 'jcareer-windows-image-deleted-recovery-observation-v1'
    scope = 'workplace-windows-image-artifact-cleanup-recovery-observation'
    observation_mode = 'READ_ONLY_POST_DELETION_RECOVERY'
    approval_ref = [string]$approval.approval_ref
    approval_sha256 = $approvalHash
    image_build_ref = [string]$inventory.image_build_ref
    backend_config_sha256 = $backendHash
    endpoint_backend_config_sha256 = $endpointBackendHash
    build_observation_sha256 = $observationHash
    secure_inventory_sha256 = $inventoryHash
    endpoint_disposition_observation_sha256 = $endpointDispositionHash
    endpoint_teardown_receipt_sha256 = $endpointTeardownHash
    image_build_arn_sha256 = Get-Sha256Text $buildArn
    observed_live_image_state = 'DELETED'
    inventory_ami_count = @($inventory.ami_ids).Count
    inventory_snapshot_count = @($inventory.snapshot_ids).Count
    scoped_residual_ami_count = 0
    scoped_residual_snapshot_count = 0
    endpoint_terraform_state_resource_count = 0
    active_instance_count = 0
    observed_at = [DateTimeOffset]::UtcNow.ToString('o')
    aws_mutation_attempted = $false
    terraform_resource_mutation_attempted = $false
    terraform_initialization_performed = $true
    endpoint_terraform_state_read_performed = $true
    observation_record_state = 'OBSERVATION_ONLY_NOT_COMPLETION'
    completion_receipt_required = $true
    lifecycle_execution_observed = $false
    lifecycle_execution_success_asserted = $false
    cleanup_operation_success_asserted = $false
    raw_identifiers_included = $false
    whole_account_zero_claimed = $false
}
if (Test-Path -LiteralPath $recoveryObservationFile -PathType Leaf) {
    $existingObservation = Get-Content -LiteralPath $recoveryObservationFile -Raw -Encoding UTF8 |
        ConvertFrom-Json
    Assert-ExactRecord -Actual $existingObservation -Expected $observation -TimestampField 'observed_at'
}
else {
    Write-JsonUtf8NoBom -Path $recoveryObservationFile -Value $observation
}
$recordedObservation = Get-Content -LiteralPath $recoveryObservationFile -Raw -Encoding UTF8 |
    ConvertFrom-Json
$recordedObservationAt = [DateTimeOffset]::Parse(
    [string]$recordedObservation.observed_at
).ToUniversalTime()
if (
    $recordedObservationAt -lt $approvalStartedAt -or
    $recordedObservationAt -ge $approvalExpiresAt -or
    $recordedObservationAt -gt [DateTimeOffset]::UtcNow.AddSeconds(5)
) {
    throw 'Recovery observation timestamp is outside the approval window or in the future.'
}
$recoveryObservationHash = (
    Get-FileHash -Algorithm SHA256 -LiteralPath $recoveryObservationFile
).Hash.ToLowerInvariant()
if ([DateTimeOffset]::UtcNow -ge $approvalExpiresAt) {
    throw 'The recovery approval expired before the completion receipt was recorded.'
}

$receipt = [ordered]@{
    schema_version = 'jcareer-windows-image-cleanup-recovery-receipt-v1'
    scope = 'workplace-windows-image-artifact-cleanup-recovery-observation'
    approval_ref = [string]$approval.approval_ref
    approval_sha256 = $approvalHash
    recovery_observation_sha256 = $recoveryObservationHash
    backend_config_sha256 = $backendHash
    endpoint_backend_config_sha256 = $endpointBackendHash
    build_observation_sha256 = $observationHash
    secure_inventory_sha256 = $inventoryHash
    endpoint_disposition_observation_sha256 = $endpointDispositionHash
    endpoint_teardown_receipt_sha256 = $endpointTeardownHash
    result = 'READ_ONLY_DELETED_STATE_AND_SCOPED_RESIDUAL_ZERO_RECORDED'
    record_state = 'COMPLETE_READ_ONLY_RECOVERY_RECORD'
    recorded_at = [DateTimeOffset]::UtcNow.ToString('o')
    aws_or_terraform_resource_mutation_performed = $false
    terraform_initialization_performed = $true
    endpoint_terraform_state_read_performed = $true
    local_evidence_records_written = $true
    lifecycle_execution_id_included = $false
    lifecycle_execution_success_asserted = $false
    cleanup_operation_success_asserted = $false
    raw_identifiers_included = $false
    whole_account_zero_claimed = $false
}
if (Test-Path -LiteralPath $recoveryReceiptFile -PathType Leaf) {
    $existingReceipt = Get-Content -LiteralPath $recoveryReceiptFile -Raw -Encoding UTF8 |
        ConvertFrom-Json
    Assert-ExactRecord -Actual $existingReceipt -Expected $receipt -TimestampField 'recorded_at'
}
else {
    Write-JsonUtf8NoBom -Path $recoveryReceiptFile -Value $receipt
}
$recordedReceipt = Get-Content -LiteralPath $recoveryReceiptFile -Raw -Encoding UTF8 |
    ConvertFrom-Json
$recordedReceiptAt = [DateTimeOffset]::Parse(
    [string]$recordedReceipt.recorded_at
).ToUniversalTime()
if (
    $recordedReceiptAt -lt $recordedObservationAt -or
    $recordedReceiptAt -ge $approvalExpiresAt -or
    $recordedReceiptAt -gt [DateTimeOffset]::UtcNow.AddSeconds(5)
) {
    throw 'Recovery receipt timestamp is out of order, outside approval, or in the future.'
}

$operationCompleted = $true
}
finally {
    if ($script:artifactOperationLeaseAcquired -and $null -ne $script:artifactOperationLeaseMutex) {
        $script:artifactOperationLeaseMutex.ReleaseMutex()
        $script:artifactOperationLeaseAcquired = $false
    }
    if ($null -ne $script:artifactOperationLeaseMutex) {
        $script:artifactOperationLeaseMutex.Dispose()
        $script:artifactOperationLeaseMutex = $null
    }
}
}
finally {
    if ($null -ne $snapshotSet) {
        Remove-JCareerProtectedSnapshotSet -SnapshotSet $snapshotSet
    }
}
if ($operationCompleted) {
    Write-Output 'IMAGE_DELETED_RECOVERY_OBSERVATION=PASS_READ_ONLY_SCOPED_ZERO'
    Write-Output 'No lifecycle execution success, deletion cause, or whole-account zero is asserted.'
}
