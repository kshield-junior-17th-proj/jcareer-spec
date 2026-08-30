[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackendConfig,

    [Parameter(Mandatory = $true)]
    [string]$ApprovalFile,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string]$ClientToken,

    [Parameter(Mandatory = $true)]
    [ValidateSet('JCAREER_WINDOWS_IMAGE_BUILD_APPROVED')]
    [string]$ActivationAcknowledgement,

    [ValidateRange(15, 120)]
    [int]$PollSeconds = 30
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$terraformRelative = 'terraform/workplace-images'
$terraformRoot = (Resolve-Path (Join-Path $repoRoot $terraformRelative)).Path
$workDir = Join-Path $terraformRoot '.terraform'
$definitionReceipt = Join-Path $workDir 'last-apply-receipt.json'
$privateInventory = Join-Path $workDir 'last-image-build.private.json'
$observationFile = Join-Path $workDir 'last-image-build-observation.json'
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
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
    $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = $sha.ComputeHash($bytes) }
    finally { $sha.Dispose() }
    return -join ($hash | ForEach-Object { $_.ToString('x2') })
}

function ConvertTo-CanonicalValue {
    param([AllowNull()]$Value)
    if ($null -eq $Value) { return $null }

    if ($Value -is [System.Collections.IDictionary]) {
        $names = [System.Collections.Generic.List[string]]::new()
        foreach ($key in $Value.Keys) { $names.Add([string]$key) }
        $names.Sort([StringComparer]::Ordinal)
        $ordered = [ordered]@{}
        foreach ($name in $names) {
            $ordered[$name] = ConvertTo-CanonicalValue $Value[$name]
        }
        return $ordered
    }

    if ($Value -is [pscustomobject]) {
        $names = [System.Collections.Generic.List[string]]::new()
        foreach ($property in $Value.PSObject.Properties) { $names.Add([string]$property.Name) }
        $names.Sort([StringComparer]::Ordinal)
        $ordered = [ordered]@{}
        foreach ($name in $names) {
            $ordered[$name] = ConvertTo-CanonicalValue $Value.PSObject.Properties[$name].Value
        }
        return $ordered
    }

    if ($Value -is [System.Collections.IEnumerable] -and $Value -isnot [string]) {
        $items = @()
        foreach ($item in $Value) { $items += ,(ConvertTo-CanonicalValue $item) }
        return ,$items
    }

    return $Value
}

function ConvertTo-CanonicalJson {
    param([Parameter(Mandatory = $true)]$Value)
    $canonical = ConvertTo-CanonicalValue $Value
    return ($canonical | ConvertTo-Json -Depth 100 -Compress)
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
    if ($stderr) { Write-Warning 'AWS CLI emitted a diagnostic while returning successful JSON; diagnostic text was suppressed.' }
    return (($output -join "`n") | ConvertFrom-Json)
}

function Write-Observation {
    param(
        [Parameter(Mandatory = $true)][string]$State,
        [Parameter(Mandatory = $true)][string]$BuildArnHash,
        [string]$AmiId = '',
        [int]$AmiCount = 0,
        [int]$SnapshotCount = 0,
        [bool]$AmiPrivate = $false,
        [bool]$Encrypted = $false,
        [bool]$TagsVerified = $false,
        [bool]$TestsEnabled = $false,
        [int]$ResidualBuildInstances = -1,
        [int]$AmiLaunchPermissionCount = -1,
        [int]$SnapshotCreateVolumePermissionCount = -1,
        [bool]$SharingPermissionsVerified = $false
    )
    $observation = [ordered]@{
        schema_version = 'jcareer-windows-image-build-observation-v1'
        observation_state = $State
        approval_ref = $approval.approval_ref
        image_build_ref = $approval.image_build_ref
        pipeline_arn_sha256 = $pipelineHash
        pipeline_configuration_sha256 = $pipelineConfigurationHash
        image_build_arn_sha256 = $BuildArnHash
        definition_apply_receipt_sha256 = $definitionReceiptHash
        image_source_sha256 = $approval.image_source_sha256
        client_token_sha256 = $clientTokenHash
        region = 'ap-northeast-2'
        ami_id = $AmiId
        ami_count = $AmiCount
        snapshot_count = $SnapshotCount
        ami_private = $AmiPrivate
        storage_encrypted = $Encrypted
        lineage_tags_verified = $TagsVerified
        image_tests_enabled = $TestsEnabled
        residual_build_instance_count = $ResidualBuildInstances
        ami_launch_permission_count = $AmiLaunchPermissionCount
        snapshot_create_volume_permission_count = $SnapshotCreateVolumePermissionCount
        sharing_permissions_verified = $SharingPermissionsVerified
        observed_at = [DateTimeOffset]::UtcNow.ToString('o')
        synthetic_data_only = $true
        human_release_recorded = $false
        raw_arn_or_account_included = $false
    }
    Write-JsonUtf8NoBom -Path $observationFile -Value $observation
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
if (-not (Test-Path -LiteralPath $definitionReceipt -PathType Leaf)) {
    throw 'The exact-plan Image Builder definition apply receipt is missing.'
}
New-Item -ItemType Directory -Path $workDir -Force | Out-Null
$script:inputSnapshotSet = New-JCareerProtectedSnapshotSet -RootPath ([IO.Path]::GetTempPath()) -Prefix 'jcareer-image-build'
$backendSource = (Resolve-Path $BackendConfig).Path
$approvalSource = (Resolve-Path $ApprovalFile).Path
$definitionReceiptSource = $definitionReceipt
$backendCheckerSource = (Resolve-Path (Join-Path $repoRoot 'scripts/check_terraform_backend_config.py')).Path
$operationCheckerSource = (Resolve-Path (Join-Path $repoRoot 'scripts/check_windows_image_operation_approval.py')).Path
$receiptCheckerSource = (Resolve-Path (Join-Path $repoRoot 'scripts/check_windows_image_receipt.py')).Path
$resolvedBackend = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $backendSource -DestinationName 'backend.hcl'
$resolvedApproval = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $approvalSource -DestinationName 'approval.json'
$definitionReceipt = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $definitionReceiptSource -DestinationName 'definition-receipt.json'
$backendChecker = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $backendCheckerSource -DestinationName 'check-backend.py'
$operationChecker = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $operationCheckerSource -DestinationName 'check_windows_image_operation_approval.py'
$receiptChecker = Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet -Source $receiptCheckerSource -DestinationName 'check_windows_image_receipt.py'
$protectedSourceRoot = Join-Path $script:inputSnapshotSet.Directory 'source-root'
$imageSourcePaths = @(
    'fleet/images/endpoint_image_contract.yaml',
    'fleet/images/windows/build-component.yaml',
    'fleet/images/windows/test-component.yaml',
    'fleet/images/windows/Configure-JCareerSession.ps1',
    'fleet/images/windows/Remove-JCareerSession.ps1'
)
foreach ($relativeSourcePath in $imageSourcePaths) {
    Add-JCareerProtectedSnapshotFile -SnapshotSet $script:inputSnapshotSet `
        -Source (Join-Path $repoRoot $relativeSourcePath) `
        -DestinationName (Join-Path 'source-root' $relativeSourcePath) | Out-Null
}
$backendSource = $null
$approvalSource = $null
$definitionReceiptSource = $null
$backendCheckerSource = $null
$operationCheckerSource = $null
$receiptCheckerSource = $null
if ($script:inputSnapshotSet.Count -ne 11) { throw 'Image-build protected input snapshot set is incomplete.' }
& $script:pythonExecutable -E -s -S -B $backendChecker --config $resolvedBackend --terraform-root workplace-images
if ($LASTEXITCODE -ne 0) { throw 'Remote backend configuration failed its contract.' }
$backendHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedBackend).Hash.ToLowerInvariant()
$definitionReceiptHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $definitionReceipt).Hash.ToLowerInvariant()
$clientTokenHash = Get-Sha256Text $ClientToken
$approval = Get-Content -LiteralPath $resolvedApproval -Raw -Encoding UTF8 | ConvertFrom-Json
$definitionReceiptDocument = Get-Content -LiteralPath $definitionReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
if (
    $definitionReceiptDocument.schema_version -ne 'jcareer-redacted-terraform-apply-receipt-v1' -or
    $definitionReceiptDocument.scope -ne 'workplace-windows-image' -or
    $definitionReceiptDocument.result -ne 'APPLY_COMMAND_COMPLETED' -or
    $definitionReceiptDocument.backend_config_sha256 -ne $backendHash -or
    $definitionReceiptDocument.protected_input_snapshot_count -ne 7 -or
    $definitionReceiptDocument.local_snapshot_cleanup_observed -ne $true
) {
    throw 'The Image Builder definition apply receipt does not match this backend and completed scope.'
}

$init = @(& $script:terraformExecutable -chdir=$terraformRelative init -reconfigure -input=false -lockfile=readonly "-backend-config=$resolvedBackend" 2>&1)
if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($init -join "`n")) }
$pipelineOutput = @(& $script:terraformExecutable -chdir=$terraformRelative output -raw pipeline_arn 2>&1)
if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($pipelineOutput -join "`n")) }
$pipelineArn = ($pipelineOutput -join '').Trim()
if ($pipelineArn -notmatch '^arn:aws:imagebuilder:ap-northeast-2:\d{12}:image-pipeline/[a-z0-9-_]+$') {
    throw 'Terraform output did not contain one expected Image Builder pipeline ARN.'
}
$pipelineHash = Get-Sha256Text $pipelineArn

$pipeline = Invoke-AwsJson @('imagebuilder', 'get-image-pipeline', '--region', 'ap-northeast-2', '--image-pipeline-arn', $pipelineArn, '--output', 'json', '--no-cli-pager')
if ($pipeline.imagePipeline.status -ne 'ENABLED') { throw 'The approved image pipeline is not enabled.' }
$recipeArn = [string]$pipeline.imagePipeline.imageRecipeArn
$infrastructureArn = [string]$pipeline.imagePipeline.infrastructureConfigurationArn
$distributionArn = [string]$pipeline.imagePipeline.distributionConfigurationArn
$recipe = Invoke-AwsJson @('imagebuilder', 'get-image-recipe', '--region', 'ap-northeast-2', '--image-recipe-arn', $recipeArn, '--output', 'json', '--no-cli-pager')
$infrastructure = Invoke-AwsJson @('imagebuilder', 'get-infrastructure-configuration', '--region', 'ap-northeast-2', '--infrastructure-configuration-arn', $infrastructureArn, '--output', 'json', '--no-cli-pager')
$distribution = Invoke-AwsJson @('imagebuilder', 'get-distribution-configuration', '--region', 'ap-northeast-2', '--distribution-configuration-arn', $distributionArn, '--output', 'json', '--no-cli-pager')
if (
    [string]$pipeline.imagePipeline.arn -ne $pipelineArn -or
    [string]$recipe.imageRecipe.arn -ne $recipeArn -or
    [string]$infrastructure.infrastructureConfiguration.arn -ne $infrastructureArn -or
    [string]$distribution.distributionConfiguration.arn -ne $distributionArn
) {
    throw 'The Image Builder configuration graph did not resolve to the pipeline-referenced resources.'
}
$pipelineConfiguration = [ordered]@{
    distribution_configuration = $distribution.distributionConfiguration
    image_pipeline = $pipeline.imagePipeline
    image_recipe = $recipe.imageRecipe
    infrastructure_configuration = $infrastructure.infrastructureConfiguration
}
$pipelineConfigurationHash = Get-Sha256Text (ConvertTo-CanonicalJson $pipelineConfiguration)

& $script:pythonExecutable -E -s -S -B $operationChecker build `
    --approval $resolvedApproval --root $protectedSourceRoot `
    --backend-config-sha256 $backendHash `
    --definition-apply-receipt $definitionReceipt `
    --pipeline-arn-sha256 $pipelineHash `
    --pipeline-configuration-sha256 $pipelineConfigurationHash `
    --client-token-sha256 $clientTokenHash --require-approved
if ($LASTEXITCODE -ne 0) { throw 'Human image-build approval did not match this exact operation.' }

$buildSubnetId = [string]$infrastructure.infrastructureConfiguration.subnetId
$buildSecurityGroupIds = @($infrastructure.infrastructureConfiguration.securityGroupIds)
if (
    $buildSubnetId -notmatch '^subnet-[0-9a-f]+$' -or
    $buildSecurityGroupIds.Count -ne 1 -or
    [string]$buildSecurityGroupIds[0] -notmatch '^sg-[0-9a-f]+$'
) {
    throw 'Approved Image Builder infrastructure does not bind one subnet and one security group.'
}
$subnetDocument = Invoke-AwsJson @(
    'ec2', 'describe-subnets', '--region', 'ap-northeast-2',
    '--subnet-ids', $buildSubnetId, '--output', 'json', '--no-cli-pager'
)
$securityGroupDocument = Invoke-AwsJson @(
    'ec2', 'describe-security-groups', '--region', 'ap-northeast-2',
    '--group-ids', [string]$buildSecurityGroupIds[0], '--output', 'json', '--no-cli-pager'
)
$buildSubnets = @($subnetDocument.Subnets)
$buildSecurityGroups = @($securityGroupDocument.SecurityGroups)
if (
    $buildSubnets.Count -ne 1 -or
    $buildSubnets[0].State -ne 'available' -or
    $buildSubnets[0].MapPublicIpOnLaunch -ne $false -or
    $buildSecurityGroups.Count -ne 1 -or
    [string]$buildSecurityGroups[0].VpcId -ne [string]$buildSubnets[0].VpcId -or
    @($buildSecurityGroups[0].IpPermissions).Count -ne 0
) {
    throw 'Image Builder requires one available no-public-IP subnet and one same-VPC zero-ingress security group.'
}

$prior = Invoke-AwsJson @('imagebuilder', 'list-image-pipeline-images', '--region', 'ap-northeast-2', '--image-pipeline-arn', $pipelineArn, '--output', 'json', '--no-cli-pager')
if (@($prior.imageSummaryList).Count -ne 0) {
    throw 'This single-use pipeline already has an image history; clean it before another approved build.'
}

# Re-read the complete pipeline graph and its mutable network attributes after
# approval, immediately before the one permitted start mutation.
$refreshedPipeline = Invoke-AwsJson @('imagebuilder', 'get-image-pipeline', '--region', 'ap-northeast-2', '--image-pipeline-arn', $pipelineArn, '--output', 'json', '--no-cli-pager')
$refreshedRecipe = Invoke-AwsJson @('imagebuilder', 'get-image-recipe', '--region', 'ap-northeast-2', '--image-recipe-arn', $recipeArn, '--output', 'json', '--no-cli-pager')
$refreshedInfrastructure = Invoke-AwsJson @('imagebuilder', 'get-infrastructure-configuration', '--region', 'ap-northeast-2', '--infrastructure-configuration-arn', $infrastructureArn, '--output', 'json', '--no-cli-pager')
$refreshedDistribution = Invoke-AwsJson @('imagebuilder', 'get-distribution-configuration', '--region', 'ap-northeast-2', '--distribution-configuration-arn', $distributionArn, '--output', 'json', '--no-cli-pager')
$refreshedConfiguration = [ordered]@{
    distribution_configuration = $refreshedDistribution.distributionConfiguration
    image_pipeline = $refreshedPipeline.imagePipeline
    image_recipe = $refreshedRecipe.imageRecipe
    infrastructure_configuration = $refreshedInfrastructure.infrastructureConfiguration
}
if (
    $refreshedPipeline.imagePipeline.status -ne 'ENABLED' -or
    (Get-Sha256Text (ConvertTo-CanonicalJson $refreshedConfiguration)) -ne $pipelineConfigurationHash
) {
    throw 'The approved Image Builder pipeline graph changed before the start mutation.'
}
$refreshedSubnetId = [string]$refreshedInfrastructure.infrastructureConfiguration.subnetId
$refreshedSecurityGroupIds = @($refreshedInfrastructure.infrastructureConfiguration.securityGroupIds)
if (
    $refreshedSubnetId -ne $buildSubnetId -or
    $refreshedSecurityGroupIds.Count -ne 1 -or
    [string]$refreshedSecurityGroupIds[0] -ne [string]$buildSecurityGroupIds[0]
) {
    throw 'The approved Image Builder network binding changed before the start mutation.'
}
$refreshedSubnet = Invoke-AwsJson @(
    'ec2', 'describe-subnets', '--region', 'ap-northeast-2',
    '--subnet-ids', $refreshedSubnetId, '--output', 'json', '--no-cli-pager'
)
$refreshedSecurityGroup = Invoke-AwsJson @(
    'ec2', 'describe-security-groups', '--region', 'ap-northeast-2',
    '--group-ids', [string]$refreshedSecurityGroupIds[0], '--output', 'json', '--no-cli-pager'
)
if (
    @($refreshedSubnet.Subnets).Count -ne 1 -or
    $refreshedSubnet.Subnets[0].State -ne 'available' -or
    $refreshedSubnet.Subnets[0].MapPublicIpOnLaunch -ne $false -or
    @($refreshedSecurityGroup.SecurityGroups).Count -ne 1 -or
    [string]$refreshedSecurityGroup.SecurityGroups[0].VpcId -ne [string]$refreshedSubnet.Subnets[0].VpcId -or
    @($refreshedSecurityGroup.SecurityGroups[0].IpPermissions).Count -ne 0
) {
    throw 'The Image Builder network observation changed before the start mutation.'
}
$approvalExpiry = [DateTimeOffset]::Parse([string]$approval.expires_at)
if ([DateTimeOffset]::UtcNow -ge $approvalExpiry) {
    throw 'The image-build approval expired before the start mutation.'
}

$started = Invoke-AwsJson @('imagebuilder', 'start-image-pipeline-execution', '--region', 'ap-northeast-2', '--image-pipeline-arn', $pipelineArn, '--client-token', $ClientToken, '--output', 'json', '--no-cli-pager')
$buildArn = [string]$started.imageBuildVersionArn
if ($buildArn -notmatch '^arn:aws:imagebuilder:ap-northeast-2:\d{12}:image/[a-z0-9-_]+/\d+\.\d+\.\d+/\d+$') {
    throw 'Image Builder did not return one expected build-version ARN.'
}
$buildArnHash = Get-Sha256Text $buildArn
$private = [ordered]@{
    schema_version = 'jcareer-windows-image-private-inventory-v2'
    image_build_ref = $approval.image_build_ref
    pipeline_arn = $pipelineArn
    image_build_version_arn = $buildArn
    ami_artifacts = @()
    ami_ids = @()
    snapshot_ids = @()
    inventory_complete = $false
    last_observed_build_state = 'STARTED'
    created_at = [DateTimeOffset]::UtcNow.ToString('o')
    contains_account_scoped_identifiers = $true
    storage_protection = 'OPERATOR_FILESYSTEM_RESPONSIBILITY'
}
Write-JsonUtf8NoBom -Path $privateInventory -Value $private

$pollDeadline = [DateTimeOffset]::Parse([string]$approval.poll_deadline_at)
$cleanupDeadline = [DateTimeOffset]::Parse([string]$approval.cleanup_deadline_at)
$cancelRequested = $false
$cancelTerminalDeadline = $null
do {
    $imageResult = Invoke-AwsJson @('imagebuilder', 'get-image', '--region', 'ap-northeast-2', '--image-build-version-arn', $buildArn, '--output', 'json', '--no-cli-pager')
    $state = [string]$imageResult.image.state.status
    $private.last_observed_build_state = $state
    Write-JsonUtf8NoBom -Path $privateInventory -Value $private
    if ($state -in @('AVAILABLE', 'FAILED', 'CANCELLED', 'DEPRECATED', 'DISABLED')) { break }
    if (-not $cancelRequested -and [DateTimeOffset]::UtcNow -ge $pollDeadline) {
        Invoke-AwsJson @('imagebuilder', 'cancel-image-creation', '--region', 'ap-northeast-2', '--image-build-version-arn', $buildArn, '--client-token', $ClientToken, '--output', 'json', '--no-cli-pager') | Out-Null
        Write-Observation -State 'CANCEL_REQUESTED_AT_APPROVED_DEADLINE' -BuildArnHash $buildArnHash
        $cancelRequested = $true
        $candidateDeadline = [DateTimeOffset]::UtcNow.AddMinutes(15)
        $cancelTerminalDeadline = if ($candidateDeadline -lt $cleanupDeadline) {
            $candidateDeadline
        }
        else { $cleanupDeadline }
    }
    if (
        $cancelRequested -and
        $null -ne $cancelTerminalDeadline -and
        [DateTimeOffset]::UtcNow -ge [DateTimeOffset]$cancelTerminalDeadline
    ) {
        Write-Observation -State 'CANCEL_REQUESTED_TERMINAL_NOT_OBSERVED' -BuildArnHash $buildArnHash
        throw 'Cancellation was requested but a terminal build state was not observed within the bounded wait.'
    }
    Start-Sleep -Seconds $PollSeconds
} while ($true)

$outputAmis = @($imageResult.image.outputResources.amis)
$artifactDocuments = @{}
foreach ($outputAmi in $outputAmis) {
    $artifactRegion = [string]$outputAmi.region
    $artifactAmiId = [string]$outputAmi.image
    if (
        $artifactRegion -notmatch '^[a-z]{2}(?:-gov)?-[a-z]+-[0-9]+$' -or
        $artifactAmiId -notmatch '^ami-[0-9a-f]+$'
    ) {
        Write-JsonUtf8NoBom -Path $privateInventory -Value $private
        Write-Observation -State 'ARTIFACT_DESCRIPTOR_VALIDATION_FAILED' -BuildArnHash $buildArnHash `
            -AmiCount @($private.ami_ids).Count -SnapshotCount @($private.snapshot_ids).Count
        throw 'Image Builder returned an invalid AMI artifact descriptor.'
    }
    if (@($private.ami_artifacts | Where-Object {
        [string]$_.region -eq $artifactRegion -and [string]$_.ami_id -eq $artifactAmiId
    }).Count -ne 0) {
        Write-Observation -State 'ARTIFACT_DESCRIPTOR_VALIDATION_FAILED' -BuildArnHash $buildArnHash `
            -AmiCount @($private.ami_ids).Count -SnapshotCount @($private.snapshot_ids).Count
        throw 'Image Builder returned a duplicate region-bound AMI artifact descriptor.'
    }
    $private.ami_artifacts += [ordered]@{
        region = $artifactRegion
        ami_id = $artifactAmiId
        snapshot_ids = @()
    }
    $private.ami_ids += $artifactAmiId
    Write-JsonUtf8NoBom -Path $privateInventory -Value $private
}

try {
    foreach ($artifact in @($private.ami_artifacts)) {
        $amiDoc = Invoke-AwsJson @(
            'ec2', 'describe-images', '--region', [string]$artifact.region,
            '--image-ids', [string]$artifact.ami_id, '--output', 'json', '--no-cli-pager'
        )
        $images = @($amiDoc.Images)
        if ($images.Count -ne 1) {
            throw 'An Image Builder AMI artifact did not resolve exactly once.'
        }
        $artifactSnapshotIds = @(
            $images[0].BlockDeviceMappings |
                ForEach-Object { $_.Ebs.SnapshotId } |
                Where-Object { $_ }
        )
        if ($artifactSnapshotIds.Count -lt 1) {
            throw 'An Image Builder AMI artifact has no observable EBS snapshot.'
        }
        $artifact['snapshot_ids'] = @($artifactSnapshotIds)
        $private.snapshot_ids += @($artifactSnapshotIds)
        $artifactDocuments[[string]$artifact.ami_id] = $images[0]
        Write-JsonUtf8NoBom -Path $privateInventory -Value $private
    }
    $private.inventory_complete = $true
    Write-JsonUtf8NoBom -Path $privateInventory -Value $private
}
catch {
    Write-Observation -State 'ARTIFACT_INVENTORY_DISCOVERY_FAILED' -BuildArnHash $buildArnHash `
        -AmiCount @($private.ami_ids).Count -SnapshotCount @($private.snapshot_ids).Count
    throw
}

if ($state -ne 'AVAILABLE') {
    Write-Observation -State 'TERMINAL_NONRELEASABLE_INVENTORY_COMPLETE' -BuildArnHash $buildArnHash `
        -AmiCount @($private.ami_ids).Count -SnapshotCount @($private.snapshot_ids).Count
    throw "Image build reached non-releasable terminal state with complete artifact inventory: $state"
}
if ($outputAmis.Count -lt 1) {
    Write-Observation -State 'AVAILABLE_WITHOUT_DISCOVERABLE_ARTIFACTS' -BuildArnHash $buildArnHash
    throw 'Image Builder reported AVAILABLE without a discoverable AMI artifact.'
}

$amiId = if ($private.ami_ids.Count -eq 1) { [string]$private.ami_ids[0] } else { '' }
$snapshotIds = @($private.snapshot_ids)
$amiPrivate = $false
$tagsVerified = $false
$storageEncrypted = $false
$testsEnabled = [bool]$imageResult.image.imageTestsConfiguration.imageTestsEnabled
$residualCount = -1
$amiLaunchPermissionCount = -1
$snapshotCreateVolumePermissionCount = -1

Write-Observation -State 'ARTIFACTS_DISCOVERED_PENDING_VALIDATION' -BuildArnHash $buildArnHash `
    -AmiId $amiId -AmiCount $private.ami_ids.Count -SnapshotCount $snapshotIds.Count

try {
    if (
        $private.ami_artifacts.Count -ne 1 -or
        [string]$private.ami_artifacts[0].region -ne 'ap-northeast-2'
    ) {
        throw 'The build did not produce exactly one AMI in the approved region.'
    }
    $image = $artifactDocuments[$amiId]
    $amiPrivate = $image.Public -eq $false -and $image.State -eq 'available'
    if (-not $amiPrivate) {
        throw 'The output AMI is not one private available image.'
    }
    $tags = @{}
    foreach ($tag in @($image.Tags)) { $tags[[string]$tag.Key] = [string]$tag.Value }
    $tagsVerified = (
        $tags['jk_image_build_ref'] -eq [string]$approval.image_build_ref -and
        $tags['jk_image_state'] -eq 'BUILT_PENDING_HUMAN_RELEASE' -and
        $tags['jk_os_contract'] -eq 'windows-server-desktop-simulation'
    )
    if (-not $tagsVerified) { throw 'The output AMI lineage tags do not match the approved build.' }
    $snapshotArguments = @(
        'ec2', 'describe-snapshots', '--region', 'ap-northeast-2', '--snapshot-ids'
    ) + $snapshotIds + @('--output', 'json', '--no-cli-pager')
    $snapshots = Invoke-AwsJson $snapshotArguments
    $storageEncrypted = (
        @($snapshots.Snapshots).Count -eq $snapshotIds.Count -and
        @($snapshots.Snapshots | Where-Object { $_.Encrypted -ne $true }).Count -eq 0
    )
    if (-not $storageEncrypted) {
        throw 'The output AMI snapshot set is incomplete or not fully encrypted.'
    }
    $amiPermissions = Invoke-AwsJson @(
        'ec2', 'describe-image-attribute', '--region', 'ap-northeast-2',
        '--image-id', $amiId, '--attribute', 'launchPermission', '--output', 'json', '--no-cli-pager'
    )
    $amiLaunchPermissionCount = @($amiPermissions.LaunchPermissions).Count
    if ($amiLaunchPermissionCount -ne 0) {
        throw 'The output AMI has one or more launch permissions and cannot be observed as private-only.'
    }
    $snapshotCreateVolumePermissionCount = 0
    foreach ($snapshotId in $snapshotIds) {
        $snapshotPermissions = Invoke-AwsJson @(
            'ec2', 'describe-snapshot-attribute', '--region', 'ap-northeast-2',
            '--snapshot-id', [string]$snapshotId, '--attribute', 'createVolumePermission',
            '--output', 'json', '--no-cli-pager'
        )
        $snapshotCreateVolumePermissionCount += @($snapshotPermissions.CreateVolumePermissions).Count
    }
    if ($snapshotCreateVolumePermissionCount -ne 0) {
        throw 'One or more output snapshots have create-volume permissions and cannot be observed as private-only.'
    }
    $residual = Invoke-AwsJson @(
        'ec2', 'describe-instances', '--region', 'ap-northeast-2', '--filters',
        "Name=tag:jk_image_build_ref,Values=$($approval.image_build_ref)",
        'Name=instance-state-name,Values=pending,running,shutting-down,stopping,stopped',
        '--output', 'json', '--no-cli-pager'
    )
    $residualCount = @($residual.Reservations | ForEach-Object { $_.Instances }).Count
    if ($residualCount -ne 0) { throw 'A temporary Image Builder instance remains after the terminal build.' }
    if (-not $testsEnabled) {
        throw 'Image Builder did not report image tests enabled for this build.'
    }
}
catch {
    Write-Observation -State 'ARTIFACTS_DISCOVERED_VALIDATION_FAILED' -BuildArnHash $buildArnHash `
        -AmiId $amiId -AmiCount $private.ami_ids.Count -SnapshotCount $snapshotIds.Count `
        -AmiPrivate $amiPrivate -Encrypted $storageEncrypted -TagsVerified $tagsVerified `
        -TestsEnabled $testsEnabled -ResidualBuildInstances $residualCount `
        -AmiLaunchPermissionCount $amiLaunchPermissionCount `
        -SnapshotCreateVolumePermissionCount $snapshotCreateVolumePermissionCount
    throw
}

Remove-JCareerProtectedSnapshotSet -SnapshotSet $script:inputSnapshotSet

Write-Observation -State 'AVAILABLE_PENDING_HUMAN_REVIEW' -BuildArnHash $buildArnHash -AmiId $amiId `
    -AmiCount 1 -SnapshotCount $snapshotIds.Count -AmiPrivate $true -Encrypted $true `
    -TagsVerified $true -TestsEnabled $testsEnabled -ResidualBuildInstances $residualCount `
    -AmiLaunchPermissionCount $amiLaunchPermissionCount `
    -SnapshotCreateVolumePermissionCount $snapshotCreateVolumePermissionCount `
    -SharingPermissionsVerified $true

Write-Output 'IMAGE_BUILD_OBSERVED=PASS_PENDING_HUMAN_REVIEW'
Write-Output 'No endpoint was deployed. A human must review the observation before creating an endpoint image receipt.'
}
finally {
    if ($null -ne $script:inputSnapshotSet -and -not $script:inputSnapshotSet.CleanupObserved) {
        Remove-JCareerProtectedSnapshotSet -SnapshotSet $script:inputSnapshotSet
    }
}
