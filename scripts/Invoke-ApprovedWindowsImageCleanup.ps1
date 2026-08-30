[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackendConfig,

    [Parameter(Mandatory = $true)]
    [string]$ApprovalFile,

    [Parameter(Mandatory = $true)]
    [string]$BuildObservation,

    [Parameter(Mandatory = $true)]
    [string]$PrivateInventory,

    [Parameter(Mandatory = $true)]
    [string]$EndpointBackendConfig,

    [Parameter(Mandatory = $true)]
    [string]$EndpointDispositionObservation,

    [string]$EndpointTeardownReceipt = '',

    [Parameter(Mandatory = $true)]
    [ValidateSet('JCAREER_WINDOWS_IMAGE_ARTIFACT_CLEANUP_APPROVED')]
    [string]$ActivationAcknowledgement,

    [ValidateRange(15, 120)]
    [int]$PollSeconds = 30
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$terraformRelative = 'terraform/workplace-images'
$endpointTerraformRelative = 'terraform/workplace-endpoints'
$terraformRoot = (Resolve-Path (Join-Path $repoRoot $terraformRelative)).Path
$workDir = Join-Path $terraformRoot '.terraform'
$cleanupReceipt = Join-Path $workDir 'last-image-cleanup-receipt.json'
$recoveryRecordRoot = Join-Path $workDir 'image-deleted-recovery'
$legacyRecoveryObservationFile = Join-Path $workDir 'last-image-deleted-recovery-observation.json'
$legacyRecoveryReceiptFile = Join-Path $workDir 'last-image-deleted-recovery-receipt.json'
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
$script:artifactOperationLeaseMutex = $null
$script:artifactOperationLeaseAcquired = $false
$script:artifactOperationLeaseName = ''
$script:awsExecutable = ''
$script:terraformExecutable = ''
$script:pythonExecutable = ''
$script:inputSnapshotSet = $null
$snapshotModule = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot 'scripts/JCareer-ProtectedInputSnapshot.psm1')).Path
Microsoft.PowerShell.Core\Import-Module $snapshotModule -Force -ErrorAction Stop

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
        [IO.File]::WriteAllText($temporaryPath, ($Value | ConvertTo-Json -Depth $Depth), $utf8WithoutBom)
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

function Test-AnyRecoveryRecord {
    if (
        [IO.File]::Exists($legacyRecoveryObservationFile) -or
        [IO.File]::Exists($legacyRecoveryReceiptFile)
    ) { return $true }
    if (-not [IO.Directory]::Exists($recoveryRecordRoot)) { return $false }
    foreach ($path in [IO.Directory]::EnumerateFiles(
        $recoveryRecordRoot, '*.json', [IO.SearchOption]::AllDirectories
    )) {
        if ($path) { return $true }
    }
    return $false
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

function Get-RegionBoundOutputKeys {
    param([Parameter(Mandatory = $true)]$ImageDocument)

    $keys = @()
    foreach ($outputAmi in @($ImageDocument.image.outputResources.amis)) {
        $region = [string]$outputAmi.region
        $amiId = [string]$outputAmi.image
        if (
            $region -notmatch '^[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+$' -or
            $amiId -notmatch '^ami-[0-9a-f]+$'
        ) {
            throw 'Live Image Builder output contains an invalid region-bound AMI descriptor.'
        }
        $keys += ('{0}:{1}' -f $region, $amiId)
    }
    if (@($keys | Sort-Object -Unique).Count -ne $keys.Count) {
        throw 'Live Image Builder output contains a duplicate region-bound AMI descriptor.'
    }
    return @($keys | Sort-Object)
}

function Test-ExactStringSet {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Observed,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Expected
    )
    if ($Observed.Count -ne $Expected.Count) { return $false }
    return @(Compare-Object -ReferenceObject @($Expected) -DifferenceObject @($Observed)).Count -eq 0
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
    if ($exitCode -ne 0) { throw (Protect-Diagnostic ((@($output) + @($stderr)) -join "`n")) }
    if ($stderr) { Write-Warning 'AWS CLI emitted a diagnostic while returning successful JSON; diagnostic text was suppressed.' }
    return (($output -join "`n") | ConvertFrom-Json)
}

$awsCommand = Get-Command 'aws.exe' -CommandType Application -ErrorAction Stop | Select-Object -First 1
$terraformCommand = Get-Command 'terraform.exe' -CommandType Application -ErrorAction Stop | Select-Object -First 1
$pythonCommand = Get-Command 'python.exe' -CommandType Application -ErrorAction Stop | Select-Object -First 1
$script:awsExecutable = [IO.Path]::GetFullPath([string]$awsCommand.Source)
$script:terraformExecutable = [IO.Path]::GetFullPath([string]$terraformCommand.Source)
$script:pythonExecutable = [IO.Path]::GetFullPath([string]$pythonCommand.Source)
foreach ($executable in @($script:awsExecutable, $script:terraformExecutable, $script:pythonExecutable)) {
    if (-not [IO.File]::Exists($executable)) { throw 'One required application path is invalid.' }
}
$awsVersion = @(& $script:awsExecutable --version 2>&1)
if ($LASTEXITCODE -ne 0 -or ($awsVersion -join '') -notmatch '^aws-cli/2\.') {
    throw 'AWS CLI v2 is required.'
}
try {
$script:inputSnapshotSet = New-JCareerProtectedSnapshotSet -RootPath ([IO.Path]::GetTempPath()) -Prefix 'jcareer-image-cleanup'
$backendSource = (Resolve-Path $BackendConfig).Path
$approvalSource = (Resolve-Path $ApprovalFile).Path
$observationSource = (Resolve-Path $BuildObservation).Path
$inventorySource = (Resolve-Path $PrivateInventory).Path
$endpointBackendSource = (Resolve-Path $EndpointBackendConfig).Path
$endpointDispositionSource = (Resolve-Path $EndpointDispositionObservation).Path
$endpointReceiptSource = if ($EndpointTeardownReceipt) { (Resolve-Path $EndpointTeardownReceipt).Path } else { '' }
$backendCheckerSource = (Resolve-Path (Join-Path $repoRoot 'scripts/check_terraform_backend_config.py')).Path
$operationCheckerSource = (Resolve-Path (Join-Path $repoRoot 'scripts/check_windows_image_operation_approval.py')).Path
$receiptCheckerSource = (Resolve-Path (Join-Path $repoRoot 'scripts/check_windows_image_receipt.py')).Path
$resolvedBackend = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $backendSource -DestinationName 'image-backend.hcl'
$resolvedApproval = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $approvalSource -DestinationName 'approval.json'
$resolvedObservation = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $observationSource -DestinationName 'build-observation.json'
$resolvedInventory = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $inventorySource -DestinationName 'private-inventory.json'
$resolvedEndpointBackend = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $endpointBackendSource -DestinationName 'endpoint-backend.hcl'
$resolvedEndpointDisposition = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $endpointDispositionSource -DestinationName 'endpoint-disposition.json'
$backendChecker = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $backendCheckerSource -DestinationName 'check-backend.py'
$operationChecker = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $operationCheckerSource -DestinationName 'check_windows_image_operation_approval.py'
$receiptChecker = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $receiptCheckerSource -DestinationName 'check_windows_image_receipt.py'
$resolvedEndpointReceipt = if ($endpointReceiptSource) {
    Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $endpointReceiptSource -DestinationName 'endpoint-teardown-receipt.json'
}
else { '' }
$expectedSnapshotCount = if ($resolvedEndpointReceipt) { 10 } else { 9 }
if ($script:inputSnapshotSet.Count -ne $expectedSnapshotCount) {
    throw 'Image-cleanup protected input snapshot set is incomplete.'
}
$backendSource = $null
$approvalSource = $null
$observationSource = $null
$inventorySource = $null
$endpointBackendSource = $null
$endpointDispositionSource = $null
$endpointReceiptSource = $null
$backendCheckerSource = $null
$operationCheckerSource = $null
$receiptCheckerSource = $null

& $script:pythonExecutable -E -s -S -B $backendChecker --config $resolvedBackend --terraform-root workplace-images
if ($LASTEXITCODE -ne 0) { throw 'Remote backend configuration failed its contract.' }
$canonicalBackendOutput = @(
    & $script:pythonExecutable -E -s -S -B $backendChecker `
        --config $resolvedBackend --terraform-root workplace-images `
        --print-canonical-sha256 2>&1
)
$canonicalBackendHash = ($canonicalBackendOutput -join '').Trim()
if ($LASTEXITCODE -ne 0 -or $canonicalBackendHash -notmatch '^[0-9a-f]{64}$') {
    throw 'Image logical backend identity could not be derived.'
}
$backendHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedBackend).Hash.ToLowerInvariant()
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
if (Test-Path -LiteralPath $cleanupReceipt -PathType Leaf) {
    throw 'A prior image-cleanup receipt requires human disposition before another cleanup.'
}
if (Test-AnyRecoveryRecord) {
    throw 'A deleted-state recovery record requires human disposition before normal cleanup.'
}
$observationHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedObservation).Hash.ToLowerInvariant()
$inventoryHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedInventory).Hash.ToLowerInvariant()
$endpointDispositionHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedEndpointDisposition).Hash.ToLowerInvariant()
$approval = Get-Content -LiteralPath $resolvedApproval -Raw -Encoding UTF8 | ConvertFrom-Json
$observation = Get-Content -LiteralPath $resolvedObservation -Raw -Encoding UTF8 | ConvertFrom-Json
$inventory = Get-Content -LiteralPath $resolvedInventory -Raw -Encoding UTF8 | ConvertFrom-Json
if (
    $observation.schema_version -ne 'jcareer-windows-image-build-observation-v1' -or
    $observation.human_release_recorded -ne $false -or
    [string]$observation.observation_state -notin @(
        'AVAILABLE_PENDING_HUMAN_REVIEW',
        'ARTIFACTS_DISCOVERED_VALIDATION_FAILED',
        'TERMINAL_NONRELEASABLE_INVENTORY_COMPLETE',
        'AVAILABLE_WITHOUT_DISCOVERABLE_ARTIFACTS'
    ) -or
    (
        $observation.observation_state -eq 'AVAILABLE_PENDING_HUMAN_REVIEW' -and
        (
            $observation.ami_launch_permission_count -ne 0 -or
            $observation.snapshot_create_volume_permission_count -ne 0 -or
            $observation.sharing_permissions_verified -ne $true
        )
    ) -or
    $inventory.schema_version -ne 'jcareer-windows-image-private-inventory-v2' -or
    $inventory.inventory_complete -ne $true -or
    $inventory.contains_account_scoped_identifiers -ne $true
) {
    throw 'Build observation or private inventory contract is invalid.'
}

$checkerArguments = @(
    $operationChecker, 'cleanup',
    '--approval', $resolvedApproval,
    '--backend-config-sha256', $backendHash,
    '--build-observation', $resolvedObservation,
    '--secure-inventory', $resolvedInventory,
    '--endpoint-backend-config', $resolvedEndpointBackend,
    '--endpoint-disposition-observation', $resolvedEndpointDisposition,
    '--require-approved'
)
if ($resolvedEndpointReceipt) {
    $checkerArguments += @('--endpoint-teardown-receipt', $resolvedEndpointReceipt)
}
& $script:pythonExecutable -E -s -S -B @checkerArguments
if ($LASTEXITCODE -ne 0) { throw 'Human image cleanup approval did not match this exact artifact set.' }

& $script:pythonExecutable -E -s -S -B $backendChecker --config $resolvedEndpointBackend --terraform-root workplace-endpoints
if ($LASTEXITCODE -ne 0) { throw 'Endpoint backend configuration failed its contract.' }

$init = @(& $script:terraformExecutable -chdir=$terraformRelative init -reconfigure -input=false -lockfile=readonly "-backend-config=$resolvedBackend" 2>&1)
if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($init -join "`n")) }
$roleOutput = @(& $script:terraformExecutable -chdir=$terraformRelative output -raw lifecycle_execution_role_name 2>&1)
if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($roleOutput -join "`n")) }
$roleName = ($roleOutput -join '').Trim()
if ($roleName -notmatch '^[A-Za-z0-9+=,.@_-]{3,64}$') { throw 'Lifecycle execution role name is invalid.' }

$buildArn = [string]$inventory.image_build_version_arn
if ($buildArn -notmatch '^arn:aws:imagebuilder:ap-northeast-2:\d{12}:image/[a-z0-9-_]+/\d+\.\d+\.\d+/\d+$') {
    throw 'Private inventory does not contain one expected image build ARN.'
}
$current = Invoke-AwsJson @('imagebuilder', 'get-image', '--region', 'ap-northeast-2', '--image-build-version-arn', $buildArn, '--output', 'json', '--no-cli-pager')
$currentState = [string]$current.image.state.status
if ($currentState -notin @('AVAILABLE', 'FAILED', 'CANCELLED', 'DEPRECATED', 'DISABLED')) {
    throw 'Image artifacts cannot be cleaned before the build reaches a terminal state.'
}
$amiIds = @($inventory.ami_ids)
$amiArtifacts = @($inventory.ami_artifacts)
if ($amiIds.Count -gt 8 -or $amiArtifacts.Count -ne $amiIds.Count) {
    throw 'Private image inventory must contain 0..8 region-bound AMIs.'
}
$inventoryOutputKeys = @(
    $amiArtifacts |
        ForEach-Object { '{0}:{1}' -f [string]$_.region, [string]$_.ami_id } |
        Sort-Object
)
$liveOutputKeys = @(Get-RegionBoundOutputKeys -ImageDocument $current)
if (-not (Test-ExactStringSet -Observed $liveOutputKeys -Expected $inventoryOutputKeys)) {
    throw 'Live Image Builder output does not exactly match the approved region-bound AMI inventory.'
}
$inventoryState = [string]$inventory.last_observed_build_state
if (
    [string]$observation.observation_state -eq 'TERMINAL_NONRELEASABLE_INVENTORY_COMPLETE' -and
    (
        $inventoryState -notin @('FAILED', 'CANCELLED', 'DEPRECATED', 'DISABLED') -or
        $currentState -ne $inventoryState
    )
) {
    throw 'Non-releasable terminal observation does not match the current and inventoried build state.'
}
if (
    [string]$observation.observation_state -ne 'TERMINAL_NONRELEASABLE_INVENTORY_COMPLETE' -and
    ($inventoryState -ne 'AVAILABLE' -or $currentState -ne 'AVAILABLE')
) {
    throw 'Available-build cleanup evidence does not match the current and inventoried build state.'
}
if (
    [string]$observation.observation_state -eq 'AVAILABLE_WITHOUT_DISCOVERABLE_ARTIFACTS' -and
    $liveOutputKeys.Count -ne 0
) {
    throw 'Artifact-free observation cannot authorize cleanup of a build with live AMI output.'
}

# Re-read the endpoint backend and AMI consumers after approval, immediately before mutation.
$endpointInit = @(& $script:terraformExecutable -chdir=$endpointTerraformRelative init -reconfigure -input=false -lockfile=readonly "-backend-config=$resolvedEndpointBackend" 2>&1)
if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($endpointInit -join "`n")) }
$endpointStateAddresses = @(& $script:terraformExecutable -chdir=$endpointTerraformRelative state list -no-color 2>&1)
if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($endpointStateAddresses -join "`n")) }
$endpointStateCount = @($endpointStateAddresses | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) }).Count
if ($endpointStateCount -ne 0) {
    throw 'Endpoint Terraform state changed after approval; artifact cleanup was not started.'
}
$preMutationImage = Invoke-AwsJson @(
    'imagebuilder', 'get-image', '--region', 'ap-northeast-2',
    '--image-build-version-arn', $buildArn, '--output', 'json', '--no-cli-pager'
)
$preMutationKeys = @(Get-RegionBoundOutputKeys -ImageDocument $preMutationImage)
if (
    [string]$preMutationImage.image.state.status -ne $currentState -or
    -not (Test-ExactStringSet -Observed $preMutationKeys -Expected $inventoryOutputKeys)
) {
    throw 'Image Builder state or output changed immediately before the lifecycle mutation.'
}
$activeStates = 'pending,running,shutting-down,stopping,stopped'
$activeInstanceCount = 0
foreach ($artifact in $amiArtifacts) {
    $active = Invoke-AwsJson @(
        'ec2', 'describe-instances', '--region', [string]$artifact.region,
        '--filters', "Name=image-id,Values=$([string]$artifact.ami_id)",
        "Name=instance-state-name,Values=$activeStates",
        '--output', 'json', '--no-cli-pager'
    )
    $activeInstanceCount += @($active.Reservations | ForEach-Object { $_.Instances }).Count
}
if ($activeInstanceCount -ne 0) {
    throw 'An inventory AMI gained an active instance immediately before cleanup; artifact cleanup was not started.'
}
$cleanupToken = Get-Sha256Text ("$($approval.approval_ref):$inventoryHash")
$approvalExpiry = [DateTimeOffset]::Parse([string]$approval.expires_at)
if ([DateTimeOffset]::UtcNow -ge $approvalExpiry) {
    throw 'The image-cleanup approval expired before the lifecycle mutation.'
}
if (
    (Test-Path -LiteralPath $cleanupReceipt -PathType Leaf) -or
    (Test-AnyRecoveryRecord)
) {
    throw 'A competing cleanup or recovery record appeared before mutation; human disposition is required.'
}
$started = Invoke-AwsJson @(
    'imagebuilder', 'start-resource-state-update', '--region', 'ap-northeast-2',
    '--resource-arn', $buildArn, '--state', 'status=DELETED',
    '--execution-role', $roleName,
    '--include-resources', 'amis=true,snapshots=true,containers=false',
    '--client-token', $cleanupToken, '--output', 'json', '--no-cli-pager'
)
$executionId = [string]$started.lifecycleExecutionId
if (
    $executionId -notmatch '^lce-[0-9a-fA-F-]{36}$' -or
    [string]$started.resourceArn -ne $buildArn
) {
    throw 'Image Builder did not bind one lifecycle execution to the exact approved build ARN.'
}
$deadline = $approvalExpiry
do {
    $execution = Invoke-AwsJson @('imagebuilder', 'get-lifecycle-execution', '--region', 'ap-northeast-2', '--lifecycle-execution-id', $executionId, '--output', 'json', '--no-cli-pager')
    $state = [string]$execution.lifecycleExecution.state.status
    if ($state -in @('SUCCESS', 'FAILED', 'CANCELLED')) { break }
    if ([DateTimeOffset]::UtcNow -ge $deadline) {
        throw 'Cleanup observation deadline expired; no additional mutation was attempted.'
    }
    Start-Sleep -Seconds $PollSeconds
} while ($true)
if ($state -ne 'SUCCESS') { throw "Image artifact cleanup reached terminal state: $state" }
$deletedImage = Invoke-AwsJson @(
    'imagebuilder', 'get-image', '--region', 'ap-northeast-2',
    '--image-build-version-arn', $buildArn, '--output', 'json', '--no-cli-pager'
)
if ([string]$deletedImage.image.state.status -ne 'DELETED') {
    throw 'Lifecycle execution succeeded but the exact image build was not observed in DELETED state.'
}

$residualAmiCount = 0
foreach ($artifact in $amiArtifacts) {
    try {
        $document = Invoke-AwsJson @(
            'ec2', 'describe-images', '--region', [string]$artifact.region,
            '--image-ids', [string]$artifact.ami_id, '--output', 'json', '--no-cli-pager'
        )
        $residualAmiCount += @($document.Images).Count
    }
    catch {
        $message = Protect-Diagnostic $_.Exception.Message
        if ($message -notmatch 'InvalidAMIID\.NotFound') { throw $message }
    }
}
$residualSnapshotCount = 0
foreach ($artifact in $amiArtifacts) {
    foreach ($snapshotId in @($artifact.snapshot_ids)) {
        try {
            $snapshotDocument = Invoke-AwsJson @(
                'ec2', 'describe-snapshots', '--region', [string]$artifact.region,
                '--snapshot-ids', [string]$snapshotId, '--output', 'json', '--no-cli-pager'
            )
            $residualSnapshotCount += @($snapshotDocument.Snapshots).Count
        }
        catch {
            $message = Protect-Diagnostic $_.Exception.Message
            if ($message -notmatch 'InvalidSnapshot\.NotFound') { throw $message }
        }
    }
}
if ($residualAmiCount -ne 0 -or $residualSnapshotCount -ne 0) {
    throw 'Approved artifact cleanup completed but scoped residual AMIs or snapshots remain.'
}

Remove-JCareerProtectedSnapshotSet -SnapshotSet $script:inputSnapshotSet

$receipt = [ordered]@{
    schema_version = 'jcareer-windows-image-cleanup-receipt-v1'
    scope = 'workplace-windows-image-artifact-cleanup'
    approval_ref = $approval.approval_ref
    build_observation_sha256 = $observationHash
    secure_inventory_sha256 = $inventoryHash
    endpoint_disposition_observation_sha256 = $endpointDispositionHash
    lifecycle_execution_id_sha256 = Get-Sha256Text $executionId
    scoped_residual_ami_count = $residualAmiCount
    scoped_residual_snapshot_count = $residualSnapshotCount
    completed_at = [DateTimeOffset]::UtcNow.ToString('o')
    raw_identifiers_included = $false
    whole_account_zero_claimed = $false
}
Write-JsonUtf8NoBom -Path $cleanupReceipt -Value $receipt
Write-Output 'IMAGE_ARTIFACT_CLEANUP=PASS_SCOPED_RESIDUAL_ZERO'
Write-Output 'This receipt covers only the approved build artifact set, not the entire AWS account.'
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
    if ($null -ne $script:inputSnapshotSet -and -not $script:inputSnapshotSet.CleanupObserved) {
        Remove-JCareerProtectedSnapshotSet -SnapshotSet $script:inputSnapshotSet
    }
}
