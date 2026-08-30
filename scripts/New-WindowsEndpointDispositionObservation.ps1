[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$EndpointBackendConfig,

    [Parameter(Mandatory = $true)]
    [string]$PrivateInventory,

    [string]$EndpointTeardownReceipt = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Import-Module (Join-Path $PSScriptRoot 'JCareer-ProtectedInputSnapshot.psm1') `
    -Force -ErrorAction Stop
$endpointTerraformRelative = 'terraform/workplace-endpoints'
$imageTerraformRoot = (Resolve-Path (Join-Path $repoRoot 'terraform/workplace-images')).Path
$outputDirectory = Join-Path $imageTerraformRoot '.terraform'
$outputFile = Join-Path $outputDirectory 'last-endpoint-disposition-observation.json'
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
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
    $result = @()
    $stderr = ''
    $exitCode = -1
    try {
        New-ProtectedEmptyFile -Path $stderrPath
        $ErrorActionPreference = 'Continue'
        $result = @(& $script:awsExecutable @Arguments 2> $stderrPath)
        $exitCode = $LASTEXITCODE
        if ([IO.File]::Exists($stderrPath)) { $stderr = [IO.File]::ReadAllText($stderrPath) }
    }
    finally {
        $ErrorActionPreference = $previous
        if ([IO.File]::Exists($stderrPath)) { [IO.File]::Delete($stderrPath) }
    }
    if ($exitCode -ne 0) { throw (Protect-Diagnostic ((@($result) + @($stderr)) -join "`n")) }
    if ($stderr) { Write-Warning 'AWS CLI emitted a diagnostic while returning successful JSON; diagnostic text was suppressed.' }
    return (($result -join "`n") | ConvertFrom-Json)
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

$resolvedBackend = (Resolve-Path $EndpointBackendConfig).Path
$resolvedInventory = (Resolve-Path $PrivateInventory).Path
$resolvedTeardown = if ($EndpointTeardownReceipt) {
    (Resolve-Path $EndpointTeardownReceipt).Path
}
else { '' }
$backendCheckerSource = (Resolve-Path (
    Join-Path $repoRoot 'scripts/check_terraform_backend_config.py'
)).Path
$endpointCheckerSource = (Resolve-Path (
    Join-Path $repoRoot 'scripts/check_workplace_endpoints_static.py'
)).Path
$snapshotSet = $null
try {
    $snapshotSet = New-JCareerProtectedSnapshotSet `
        -RootPath ([IO.Path]::GetTempPath()) -Prefix 'jcareer-disposition'
    $snapshotBackend = Add-JCareerProtectedSnapshotFile `
        -SnapshotSet $snapshotSet -Source $resolvedBackend `
        -DestinationName 'endpoint-backend.tfbackend'
    $snapshotInventory = Add-JCareerProtectedSnapshotFile `
        -SnapshotSet $snapshotSet -Source $resolvedInventory `
        -DestinationName 'private-inventory.json'
    $snapshotBackendChecker = Add-JCareerProtectedSnapshotFile `
        -SnapshotSet $snapshotSet -Source $backendCheckerSource `
        -DestinationName 'check-terraform-backend-config.py'
    $snapshotEndpointChecker = Add-JCareerProtectedSnapshotFile `
        -SnapshotSet $snapshotSet -Source $endpointCheckerSource `
        -DestinationName 'check-workplace-endpoints-static.py'
    $snapshotTeardown = if ($resolvedTeardown) {
        Add-JCareerProtectedSnapshotFile `
            -SnapshotSet $snapshotSet -Source $resolvedTeardown `
            -DestinationName 'endpoint-teardown-receipt.json'
    }
    else { '' }
    $expectedSnapshotCount = if ($snapshotTeardown) { 5 } else { 4 }
    if ($snapshotSet.Count -ne $expectedSnapshotCount) {
        throw 'Endpoint-disposition protected input snapshot set is incomplete.'
    }

    & $script:pythonExecutable -E -s -S -B $snapshotBackendChecker `
        --config $snapshotBackend --terraform-root workplace-endpoints
    if ($LASTEXITCODE -ne 0) { throw 'Endpoint backend configuration failed its contract.' }
    & $script:pythonExecutable -E -s -S -B $snapshotEndpointChecker --root $repoRoot
    if ($LASTEXITCODE -ne 0) { throw 'Endpoint source boundary failed its contract.' }

    $endpointBackendHash = (
        Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotBackend
    ).Hash.ToLowerInvariant()
    $inventory = Get-Content -LiteralPath $snapshotInventory -Raw -Encoding UTF8 |
        ConvertFrom-Json
    if (
        $inventory.schema_version -ne 'jcareer-windows-image-private-inventory-v2' -or
        $inventory.inventory_complete -ne $true -or
        $inventory.contains_account_scoped_identifiers -ne $true -or
        [string]$inventory.image_build_ref -notmatch '^IMAGE-[A-Z0-9_-]{8,64}$'
    ) {
        throw 'Private image inventory does not satisfy the exact source boundary.'
    }
    $amiIds = @($inventory.ami_ids)
    $amiArtifacts = @($inventory.ami_artifacts)
    if ($amiIds.Count -gt 8 -or $amiArtifacts.Count -ne $amiIds.Count) {
        throw 'Private image inventory must contain 0..8 region-bound AMIs.'
    }
    $regionBoundAmiKeys = @()
    foreach ($artifact in $amiArtifacts) {
        if (
            [string]$artifact.region -notmatch '^[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+$' -or
            [string]$artifact.ami_id -notmatch '^ami-[0-9a-f]+$'
        ) {
            throw 'Private image inventory contains an invalid region-bound AMI.'
        }
        $regionBoundAmiKeys += (
            '{0}:{1}' -f [string]$artifact.region, [string]$artifact.ami_id
        )
    }
    if (@($regionBoundAmiKeys | Sort-Object -Unique).Count -ne $regionBoundAmiKeys.Count) {
        throw 'Private image inventory contains a duplicate region-bound AMI.'
    }

    $init = @(
        & $script:terraformExecutable -chdir=$endpointTerraformRelative init `
            -reconfigure -input=false -lockfile=readonly `
            "-backend-config=$snapshotBackend" 2>&1
    )
    if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($init -join "`n")) }
    $stateAddresses = @(
        & $script:terraformExecutable -chdir=$endpointTerraformRelative state list `
            -no-color 2>&1
    )
    if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($stateAddresses -join "`n")) }
    $stateCount = @($stateAddresses | Where-Object {
        -not [string]::IsNullOrWhiteSpace([string]$_)
    }).Count
    if ($stateCount -ne 0) {
        throw 'Endpoint Terraform state is not empty; complete an approved endpoint teardown first.'
    }

    $activeStates = 'pending,running,shutting-down,stopping,stopped'
    $activeCount = 0
    foreach ($artifact in $amiArtifacts) {
        $active = Invoke-AwsJson @(
            'ec2', 'describe-instances', '--region', [string]$artifact.region,
            '--filters', "Name=image-id,Values=$([string]$artifact.ami_id)",
            "Name=instance-state-name,Values=$activeStates",
            '--output', 'json', '--no-cli-pager'
        )
        $activeCount += @(
            $active.Reservations | ForEach-Object { $_.Instances }
        ).Count
    }
    if ($activeCount -ne 0) {
        throw 'One or more active EC2 instances still reference the approved AMI.'
    }

    $teardownHash = ''
    $mode = 'EMPTY_STATE_AND_SCOPED_ACTIVE_ZERO'
    if ($snapshotTeardown) {
        $teardown = Get-Content -LiteralPath $snapshotTeardown -Raw -Encoding UTF8 |
            ConvertFrom-Json
        if (
            $teardown.schema_version -ne 'jcareer-redacted-terraform-teardown-receipt-v1' -or
            [string]$teardown.scope -notin @(
                'workplace-windows-endpoints-teardown',
                'workplace-windows-endpoints-recovery-teardown'
            ) -or
            $teardown.result -ne 'DELETE_ONLY_PLAN_APPLIED' -or
            $teardown.backend_config_sha256 -ne $endpointBackendHash -or
            $teardown.resource_identifiers_included -ne $false -or
            $teardown.protected_input_snapshot_count -ne 10 -or
            $teardown.local_snapshot_cleanup_observed -ne $true
        ) {
            throw 'Endpoint teardown receipt does not match this backend and scope.'
        }
        $teardownHash = (
            Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotTeardown
        ).Hash.ToLowerInvariant()
        $mode = 'TEARDOWN_RECEIPT_AND_SCOPED_ACTIVE_ZERO'
    }

    $amiSetHash = Get-Sha256Text ((@($regionBoundAmiKeys | Sort-Object) -join "`n"))
    $observation = [ordered]@{
        schema_version = 'jcareer-windows-endpoint-disposition-observation-v1'
        scope = 'workplace-windows-endpoint-disposition'
        observation_mode = $mode
        observed_at = [DateTimeOffset]::UtcNow.ToString('o')
        endpoint_backend_config_sha256 = $endpointBackendHash
        image_build_ref = [string]$inventory.image_build_ref
        ami_set_sha256 = $amiSetHash
        endpoint_terraform_state_resource_count = $stateCount
        active_instance_count = $activeCount
        endpoint_teardown_receipt_sha256 = $teardownHash
        raw_identifiers_included = $false
        whole_account_zero_claimed = $false
    }
    Remove-JCareerProtectedSnapshotSet -SnapshotSet $snapshotSet
    $snapshotSet = $null
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    Write-JsonUtf8NoBom -Path $outputFile -Value $observation
}
finally {
    if ($null -ne $snapshotSet) {
        Remove-JCareerProtectedSnapshotSet -SnapshotSet $snapshotSet
    }
}
Write-Output 'ENDPOINT_DISPOSITION_OBSERVED=EMPTY_STATE_AND_SCOPED_ACTIVE_ZERO'
Write-Output 'A human may now bind this redacted observation to a separate image-cleanup approval.'
