[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('JCAREER_SYNTHETIC_LAB_DESTROY_APPROVED')]
    [string]$DestroyAcknowledgement,

    [ValidateSet('ap-northeast-2')]
    [string]$Region = 'ap-northeast-2',

    [ValidatePattern('^(?:|[0-9a-f]{64})$')]
    [string]$ProviderAccountSha256 = '',

    [ValidatePattern('^(?:|[0-9a-f]{64})$')]
    [string]$ReviewedPlanSemanticSha256 = '',

    [ValidatePattern('^(?:|[0-9a-f]{64})$')]
    [string]$ReviewedSavedPlanSha256 = '',

    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$terraformDirectory = 'terraform/lab'
$planRelativePath = '.terraform/tfplan-destroy'
$planJsonRelativePath = '.terraform/plan-destroy.json'
$labDirectory = Join-Path $repoRoot $terraformDirectory
$planPath = Join-Path $labDirectory $planRelativePath
$planJsonPath = Join-Path $labDirectory $planJsonRelativePath
$planConsumptionMarkerPath = Join-Path $labDirectory '.terraform/jcareer-lab-plan-consumption.json'
$planOperationLockPath = Join-Path $labDirectory '.terraform/jcareer-lab-plan-operation.lock'
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
$script:destroySucceeded = $false
$script:destroyPlanConsumptionStarted = $false
$planReadLock = $null
$planJsonReadLock = $null
$planMutex = $null
$planMutexAcquired = $false
$planOperationLock = $null
$plannedProviderAccountSha256 = ''

if (
    $ProviderAccountSha256 -match '^([0-9a-f])\1{63}$' -or
    ($Apply -and [string]::IsNullOrWhiteSpace($ProviderAccountSha256))
) {
    throw 'Destroy apply requires a non-placeholder provider account SHA-256 from a reviewed plan-only run.'
}
if ($ReviewedPlanSemanticSha256 -match '^([0-9a-f])\1{63}$') {
    throw 'Destroy apply rejects a placeholder semantic plan SHA-256.'
}
if ($ReviewedSavedPlanSha256 -match '^([0-9a-f])\1{63}$') {
    throw 'Destroy apply rejects a placeholder saved-plan SHA-256.'
}

$baseManagedAddresses = @(
    'aws_budgets_budget.lab',
    'aws_iam_instance_profile.runtime',
    'aws_iam_role.runtime',
    'aws_iam_role_policy_attachment.ssm',
    'aws_instance.runtime',
    'aws_internet_gateway.lab',
    'aws_route.internet',
    'aws_route_table.public',
    'aws_route_table_association.public',
    'aws_security_group.runtime',
    'aws_subnet.public',
    'aws_vpc.lab',
    'aws_vpc_security_group_egress_rule.internet'
)
$httpsPreviewAddresses = @(
    'aws_cloudfront_distribution.preview[0]',
    'aws_cloudfront_function.preview_gate[0]',
    'aws_cloudfront_vpc_origin.preview[0]',
    'aws_eip.preview_nat[0]',
    'aws_nat_gateway.preview[0]',
    'aws_route.private_preview_internet[0]',
    'aws_route_table.private_preview[0]',
    'aws_route_table_association.private_preview[0]',
    'aws_subnet.private_preview[0]',
    'aws_vpc_security_group_ingress_rule.cloudfront_preview[0]'
)
$bedrockAddresses = @(
    'aws_iam_role_policy.bedrock[0]'
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
        '\b(i|vpc|subnet|sg|igw|rtb|eni|vol|nat|eipalloc|ami|snap)-[0-9a-f]+\b',
        '[REDACTED_RESOURCE_ID]',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $protected = [regex]::Replace(
        $protected,
        '\bvo_[A-Za-z0-9]+\b',
        '[REDACTED_VPC_ORIGIN_ID]'
    )
    $protected = [regex]::Replace(
        $protected,
        '\bE[A-Z0-9]{10,}\b',
        '[REDACTED_CLOUDFRONT_ID]'
    )
    $protected = [regex]::Replace(
        $protected,
        '\b[a-z0-9.-]+\.cloudfront\.net\b',
        '[REDACTED_CLOUDFRONT_DOMAIN]',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
    $protected = [regex]::Replace(
        $protected,
        '(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)',
        '[REDACTED_IP]'
    )
    return $protected
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
        $diagnostic = Protect-Diagnostic (
            ($output | Select-Object -Last 40) -join [Environment]::NewLine
        )
        throw "$Label failed (exit=$exitCode).`n$diagnostic"
    }
    if ($ReturnOutput) {
        return $output
    }
}

function Test-ExactAddressSet {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Observed,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Expected
    )

    if ($Observed.Count -ne $Expected.Count) {
        return $false
    }
    if ($Observed.Count -eq 0) {
        return $true
    }
    $difference = @(
        Compare-Object `
            -ReferenceObject @($Expected | Sort-Object) `
            -DifferenceObject @($Observed | Sort-Object)
    )
    return $difference.Count -eq 0
}

function Test-ReviewedAddressSubset {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Observed,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$ReviewedUnion
    )

    if ($Observed.Count -eq 0) { return $false }
    return @($Observed | Where-Object { $_ -notin $ReviewedUnion }).Count -eq 0
}

function Remove-KnownArtifact {
    param([Parameter(Mandatory = $true)][string]$Path)

    $resolvedLab = [IO.Path]::GetFullPath($labDirectory).TrimEnd('\') + '\'
    $candidate = [IO.Path]::GetFullPath($Path)
    if (-not $candidate.StartsWith($resolvedLab, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Artifact cleanup target escaped terraform/lab.'
    }
    if ([IO.File]::Exists($candidate)) {
        [IO.File]::Delete($candidate)
    }
}

function Open-ReadLockedFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $stream = $null
    try {
        $stream = [IO.File]::Open(
            $Path,
            [IO.FileMode]::Open,
            [IO.FileAccess]::Read,
            [IO.FileShare]::Read
        )
        if ($stream.Length -le 0) {
            throw "$Label is empty."
        }
        return $stream
    }
    catch {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
        throw
    }
}

function Get-ReadLockedSha256 {
    param([Parameter(Mandatory = $true)][IO.FileStream]$Stream)

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $Stream.Position = 0
        $digest = $sha256.ComputeHash($Stream)
        return -join ($digest | ForEach-Object { $_.ToString('x2') })
    }
    finally {
        $Stream.Position = 0
        $sha256.Dispose()
    }
}

function Get-TextSha256 {
    param([Parameter(Mandatory = $true)][string]$Text)

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $digest = $sha256.ComputeHash($utf8WithoutBom.GetBytes($Text))
        return -join ($digest | ForEach-Object { $_.ToString('x2') })
    }
    finally {
        $sha256.Dispose()
    }
}

function Assert-NoPendingLabPlanConsumption {
    if ([IO.File]::Exists($planConsumptionMarkerPath)) {
        throw 'A prior lab plan-consumption marker remains; inspect state and obtain human cleanup disposition before continuing.'
    }
    $planDirectory = [IO.Path]::GetDirectoryName($planConsumptionMarkerPath)
    if ([IO.Directory]::Exists($planDirectory)) {
        $pendingArtifacts = @(
            [IO.Directory]::EnumerateFiles(
                $planDirectory,
                '*.consuming-*',
                [IO.SearchOption]::TopDirectoryOnly
            )
        )
        if ($pendingArtifacts.Count -gt 0) {
            throw 'Prior consumed-plan artifacts remain; inspect state and obtain human cleanup disposition before continuing.'
        }
    }
}

function New-LabPlanConsumptionMarker {
    param(
        [Parameter(Mandatory = $true)][string]$OperationId,
        [Parameter(Mandatory = $true)][ValidateSet('CREATE', 'DESTROY')][string]$Kind
    )

    $markerPayload = [ordered]@{
        schema_version = 1
        operation_id   = $OperationId
        kind           = $Kind
        state          = 'IN_PROGRESS_REVIEWED_PLAN_CONSUMPTION'
    } | Microsoft.PowerShell.Utility\ConvertTo-Json -Compress
    $markerBytes = $utf8WithoutBom.GetBytes($markerPayload)
    $markerStream = [IO.File]::Open(
        $planConsumptionMarkerPath,
        [IO.FileMode]::CreateNew,
        [IO.FileAccess]::Write,
        [IO.FileShare]::None
    )
    try {
        $markerStream.Write($markerBytes, 0, $markerBytes.Length)
        $markerStream.Flush($true)
    }
    finally {
        $markerStream.Dispose()
    }
}

function Complete-LabPlanConsumption {
    param(
        [Parameter(Mandatory = $true)][string]$OperationPlanPath,
        [Parameter(Mandatory = $true)][string]$OperationPlanJsonPath
    )

    foreach ($artifact in @($OperationPlanPath, $OperationPlanJsonPath)) {
        if (-not [IO.File]::Exists($artifact)) {
            throw 'A consumed plan artifact is missing; the durable consumption marker remains for human disposition.'
        }
        [IO.File]::Delete($artifact)
        if ([IO.File]::Exists($artifact)) {
            throw 'A consumed plan artifact could not be removed; the durable consumption marker remains for human disposition.'
        }
    }
    [IO.File]::Delete($planConsumptionMarkerPath)
    if ([IO.File]::Exists($planConsumptionMarkerPath)) {
        throw 'The durable plan-consumption marker could not be cleared after artifact cleanup.'
    }
}

function Get-PlanSemanticSha256 {
    param([Parameter(Mandatory = $true)][string]$PlanJson)

    $planDocument = $PlanJson | Microsoft.PowerShell.Utility\ConvertFrom-Json
    if ('timestamp' -notin @($planDocument.PSObject.Properties.Name)) {
        throw 'Terraform destroy plan JSON is missing its volatile timestamp field.'
    }
    $planDocument.PSObject.Properties.Remove('timestamp')
    $normalisedPlanProjection = $planDocument | Microsoft.PowerShell.Utility\ConvertTo-Json -Depth 100 -Compress
    return Get-TextSha256 -Text $normalisedPlanProjection
}

function Get-ObservedProviderAccountSha256 {
    $accountOutput = $null
    $account = $null
    try {
        $accountOutput = Invoke-CheckedCommand `
            -Label 'Provider account binding check' `
            -FilePath $awsPath `
            -Arguments @(
                'sts', 'get-caller-identity', '--region', $Region,
                '--query', 'Account', '--output', 'text', '--no-cli-pager'
            ) `
            -ReturnOutput
        $account = (($accountOutput -join '').Trim())
        if ($account -notmatch '^\d{12}$') {
            throw 'The provider account identity response was invalid.'
        }
        return Get-TextSha256 -Text $account
    }
    finally {
        $account = $null
        $accountOutput = $null
    }
}

function Assert-ProviderAccountBinding {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [Parameter(Mandatory = $true)][string]$Phase
    )

    if (
        $ExpectedSha256 -notmatch '^[0-9a-f]{64}$' -or
        $ExpectedSha256 -match '^([0-9a-f])\1{63}$'
    ) {
        throw 'The expected provider account SHA-256 is empty, malformed, or placeholder-like.'
    }
    $observedSha256 = Get-ObservedProviderAccountSha256
    if (-not [string]::Equals($observedSha256, $ExpectedSha256, [StringComparison]::Ordinal)) {
        throw "Provider account binding changed before $Phase."
    }
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

$awsPath = Resolve-RequiredApplication -Name 'aws.exe'
$terraformPath = Resolve-RequiredApplication -Name 'terraform.exe'
$pythonPath = Resolve-RequiredApplication -Name 'python.exe'

$previousAutomation = [Environment]::GetEnvironmentVariable('TF_IN_AUTOMATION', 'Process')
$previousAcknowledgement = [Environment]::GetEnvironmentVariable(
    'TF_VAR_activation_acknowledgement',
    'Process'
)
$previousBedrock = [Environment]::GetEnvironmentVariable('TF_VAR_enable_bedrock_live', 'Process')
$previousBedrockAcknowledgement = [Environment]::GetEnvironmentVariable(
    'TF_VAR_bedrock_live_acknowledgement',
    'Process'
)
$previousOpenDart = [Environment]::GetEnvironmentVariable('TF_VAR_enable_opendart_live', 'Process')
$previousOpenDartAcknowledgement = [Environment]::GetEnvironmentVariable(
    'TF_VAR_opendart_live_acknowledgement',
    'Process'
)
$previousHttpsPreview = [Environment]::GetEnvironmentVariable(
    'TF_VAR_enable_aws_https_preview',
    'Process'
)
$previousHttpsAcknowledgement = [Environment]::GetEnvironmentVariable(
    'TF_VAR_https_preview_acknowledgement',
    'Process'
)
$previousPreviewTokenDigest = [Environment]::GetEnvironmentVariable(
    'TF_VAR_preview_access_token_sha256',
    'Process'
)

Push-Location $repoRoot
try {
    [Environment]::SetEnvironmentVariable('TF_IN_AUTOMATION', '1', 'Process')
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_activation_acknowledgement',
        'JCAREER_SYNTHETIC_LAB_APPROVED',
        'Process'
    )
    [Environment]::SetEnvironmentVariable('TF_VAR_enable_bedrock_live', 'false', 'Process')
    [Environment]::SetEnvironmentVariable('TF_VAR_bedrock_live_acknowledgement', 'disabled', 'Process')
    [Environment]::SetEnvironmentVariable('TF_VAR_enable_opendart_live', 'false', 'Process')
    [Environment]::SetEnvironmentVariable('TF_VAR_opendart_live_acknowledgement', 'disabled', 'Process')
    [Environment]::SetEnvironmentVariable('TF_VAR_enable_aws_https_preview', 'false', 'Process')
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_https_preview_acknowledgement',
        'disabled',
        'Process'
    )
    [Environment]::SetEnvironmentVariable('TF_VAR_preview_access_token_sha256', '', 'Process')

    $planDirectory = [IO.Path]::GetDirectoryName($planOperationLockPath)
    $null = [IO.Directory]::CreateDirectory($planDirectory)
    $planMutexName = 'Local\JCareerLabPlan-' + (
        Get-TextSha256 -Text ([IO.Path]::GetFullPath($labDirectory).ToLowerInvariant())
    )
    $planMutex = [Threading.Mutex]::new($false, $planMutexName)
    try {
        $planMutexAcquired = $planMutex.WaitOne([TimeSpan]::FromSeconds(30))
    }
    catch [Threading.AbandonedMutexException] {
        $planMutexAcquired = $true
    }
    if (-not $planMutexAcquired) {
        throw 'Another lab plan/apply/destroy operation holds the local execution mutex.'
    }
    try {
        $planOperationLock = [IO.File]::Open(
            $planOperationLockPath,
            [IO.FileMode]::OpenOrCreate,
            [IO.FileAccess]::ReadWrite,
            [IO.FileShare]::None
        )
    }
    catch {
        throw 'Another process holds the same-worktree lab plan operation lock.'
    }
    Assert-NoPendingLabPlanConsumption

    Write-Host '[1/7] Credential, account-digest, fixed-region, and Terraform-version preflight...'
    $plannedProviderAccountSha256 = Get-ObservedProviderAccountSha256
    if (
        -not [string]::IsNullOrWhiteSpace($ProviderAccountSha256) -and
        -not [string]::Equals($plannedProviderAccountSha256, $ProviderAccountSha256, [StringComparison]::Ordinal)
    ) {
        throw 'Current AWS provider account does not match the human-reviewed digest.'
    }
    $terraformVersionOutput = Invoke-CheckedCommand `
        -Label 'Terraform version' `
        -FilePath $terraformPath `
        -Arguments @('version', '-json') `
        -ReturnOutput
    $terraformVersion = (
        ($terraformVersionOutput -join [Environment]::NewLine) | ConvertFrom-Json
    ).terraform_version
    if ($terraformVersion -ne '1.15.9') {
        throw "Terraform 1.15.9 is required; observed $terraformVersion."
    }

    Write-Host '[2/7] Checking the reviewed lab source boundary...'
    Invoke-CheckedCommand -Label 'lab static checker' -FilePath $pythonPath -Arguments @(
        'scripts/check_lab_static.py'
    )
    Invoke-CheckedCommand -Label 'terraform init' -FilePath $terraformPath -Arguments @(
        "-chdir=$terraformDirectory", 'init', '-input=false', '-no-color', '-lockfile=readonly'
    )

    Write-Host '[3/7] Verifying the state contains exactly the base or HTTPS-preview graph...'
    $stateOutput = Invoke-CheckedCommand `
        -Label 'terraform state inventory' `
        -FilePath $terraformPath `
        -Arguments @("-chdir=$terraformDirectory", 'state', 'list') `
        -ReturnOutput
    $managedState = @(
        $stateOutput |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_ -and -not $_.StartsWith('data.') } |
            Sort-Object -Unique
    )
    if ($managedState.Count -eq 0) {
        if ($Apply) {
            Assert-ProviderAccountBinding -ExpectedSha256 $plannedProviderAccountSha256 -Phase 'empty-state destroy completion recording'
            $script:destroySucceeded = $true
            Write-Host '[7/7] PASS - state is already empty; known local artifacts were selected for cleanup.'
        }
        else {
            Write-Host '[6/7] PLAN-ONLY PASS - state is already empty; no cleanup or AWS delete was requested.'
            Write-Host "provider_account_sha256=$plannedProviderAccountSha256"
        }
        return
    }
    if ($Apply -and [string]::IsNullOrWhiteSpace($ReviewedPlanSemanticSha256)) {
        throw 'Destroy apply requires a semantic plan SHA-256 from a reviewed non-empty plan-only run.'
    }
    if ($Apply -and [string]::IsNullOrWhiteSpace($ReviewedSavedPlanSha256)) {
        throw 'Destroy apply requires a saved-plan SHA-256 from a reviewed non-empty plan-only run.'
    }
    $reviewedAddressUnion = @(
        $baseManagedAddresses + $bedrockAddresses + $httpsPreviewAddresses |
            Sort-Object -Unique
    )
    $expectedAddresses = $null
    $recoverySubset = $false
    if (Test-ExactAddressSet -Observed $managedState -Expected $baseManagedAddresses) {
        $expectedAddresses = $baseManagedAddresses
    }
    elseif (
        Test-ExactAddressSet `
            -Observed $managedState `
            -Expected @($baseManagedAddresses + $bedrockAddresses)
    ) {
        $expectedAddresses = @($baseManagedAddresses + $bedrockAddresses)
    }
    elseif (
        Test-ExactAddressSet `
            -Observed $managedState `
            -Expected @($baseManagedAddresses + $httpsPreviewAddresses)
    ) {
        $expectedAddresses = @($baseManagedAddresses + $httpsPreviewAddresses)
    }
    elseif (
        Test-ExactAddressSet `
            -Observed $managedState `
            -Expected @($baseManagedAddresses + $bedrockAddresses + $httpsPreviewAddresses)
    ) {
        $expectedAddresses = @($baseManagedAddresses + $bedrockAddresses + $httpsPreviewAddresses)
    }
    elseif (Test-ReviewedAddressSubset -Observed $managedState -ReviewedUnion $reviewedAddressUnion) {
        # An interrupted apply may leave only part of a reviewed graph. Preserve the
        # exact observed set as the only accepted saved-plan delete set so metered
        # NAT/EIP remnants retain a guarded recovery path.
        $expectedAddresses = @($managedState)
        $recoverySubset = $true
    }
    else {
        throw (
            'Destroy is blocked: managed state contains an address outside the reviewed ' +
            '13/14 base-or-Bedrock or 23/24 private-origin HTTPS-preview graph union.'
        )
    }
    if ($recoverySubset) {
        Write-Warning (
            'Interrupted-apply recovery mode: the non-empty reviewed-graph subset will be ' +
            'accepted only if the saved destroy plan deletes that exact observed set.'
        )
    }

    if ($Apply) {
        Write-Host '[4/7] Loading the retained human-reviewed saved destroy plan; no re-plan is performed...'
        if (-not [IO.File]::Exists($planPath) -or -not [IO.File]::Exists($planJsonPath)) {
            throw 'Destroy apply requires the retained saved plan and checked JSON from the plan-only run.'
        }
        $planReadLock = Open-ReadLockedFile -Path $planPath -Label 'Terraform saved destroy plan'
        $validatedPlanSha256 = Get-ReadLockedSha256 -Stream $planReadLock
        if (-not [string]::Equals(
            $validatedPlanSha256,
            $ReviewedSavedPlanSha256,
            [StringComparison]::Ordinal
        )) {
            throw 'The retained saved destroy-plan binary does not match the human-reviewed saved-plan digest.'
        }
        $planJsonReadLock = Open-ReadLockedFile -Path $planJsonPath -Label 'Terraform destroy plan JSON'
        $validatedPlanJsonSha256 = Get-ReadLockedSha256 -Stream $planJsonReadLock
        $planJson = [IO.File]::ReadAllText($planJsonPath, [Text.Encoding]::UTF8)
        if ($validatedPlanJsonSha256 -ne (Get-TextSha256 -Text $planJson)) {
            throw 'Terraform destroy plan JSON changed while its retained artifact was being locked.'
        }
    }
    else {
        Write-Host '[4/7] Creating a saved destroy plan without printing resource identifiers...'
        Invoke-CheckedCommand -Label 'terraform saved destroy plan' -FilePath $terraformPath -Arguments @(
            "-chdir=$terraformDirectory", 'plan', '-destroy', '-input=false', '-no-color',
            "-out=$planRelativePath"
        )
        $planReadLock = Open-ReadLockedFile -Path $planPath -Label 'Terraform saved destroy plan'
        $validatedPlanSha256 = Get-ReadLockedSha256 -Stream $planReadLock
        $planJsonOutput = Invoke-CheckedCommand `
            -Label 'terraform destroy plan JSON' `
            -FilePath $terraformPath `
            -Arguments @("-chdir=$terraformDirectory", 'show', '-json', $planRelativePath) `
            -ReturnOutput
        $planJson = $planJsonOutput -join [Environment]::NewLine
        [IO.File]::WriteAllText($planJsonPath, $planJson, $utf8WithoutBom)
        $planJsonReadLock = Open-ReadLockedFile -Path $planJsonPath -Label 'Terraform destroy plan JSON'
        $validatedPlanJsonSha256 = Get-ReadLockedSha256 -Stream $planJsonReadLock
        if ($validatedPlanJsonSha256 -ne (Get-TextSha256 -Text $planJson)) {
            throw 'Terraform destroy plan JSON changed before its read lock was established.'
        }
    }
    $planSemanticSha256 = Get-PlanSemanticSha256 -PlanJson $planJson
    if (
        $Apply -and
        -not [string]::Equals(
            $planSemanticSha256,
            $ReviewedPlanSemanticSha256,
            [StringComparison]::Ordinal
        )
    ) {
        throw 'The retained destroy plan does not match the human-reviewed semantic plan digest.'
    }

    Write-Host '[5/7] Checking the saved plan contains only the exact managed deletes...'
    $planDocument = $planJson | ConvertFrom-Json
    $managedChanges = @(
        $planDocument.resource_changes |
            Where-Object { [string]$_.mode -ne 'data' }
    )
    $deleteAddresses = @()
    foreach ($change in $managedChanges) {
        $actions = @($change.change.actions)
        if ($actions.Count -ne 1 -or [string]$actions[0] -ne 'delete') {
            throw 'Destroy is blocked: the saved plan contains a managed action other than delete.'
        }
        $deleteAddresses += [string]$change.address
    }
    $deleteAddresses = @($deleteAddresses | Sort-Object -Unique)
    if (-not (Test-ExactAddressSet -Observed $deleteAddresses -Expected $expectedAddresses)) {
        throw 'Destroy is blocked: saved-plan deletes differ from the exact observed managed state.'
    }
    Write-Host "[plan] managed deletes=$($deleteAddresses.Count); create=0 update=0"
    Assert-ProviderAccountBinding -ExpectedSha256 $plannedProviderAccountSha256 -Phase 'saved destroy-plan review completion'

    if (-not $Apply) {
        Write-Host '[6/7] PLAN-ONLY PASS - no AWS resource was changed.'
        Write-Host "provider_account_sha256=$plannedProviderAccountSha256"
        Write-Host "reviewed_saved_plan_sha256=$validatedPlanSha256"
        Write-Host "reviewed_plan_semantic_sha256=$planSemanticSha256"
        Write-Host 'Re-run with all three printed digests, -Apply, and the same mandatory destroy acknowledgement.'
        return
    }

    Write-Host '[6/7] Applying only the checked saved destroy plan...'
    if (
        (Get-ReadLockedSha256 -Stream $planReadLock) -ne $validatedPlanSha256 -or
        (Get-ReadLockedSha256 -Stream $planJsonReadLock) -ne $validatedPlanJsonSha256
    ) {
        throw 'The saved destroy plan or its checked JSON changed after validation; apply is blocked.'
    }
    $planJsonReadLock.Dispose()
    $planJsonReadLock = $null
    $planReadLock.Dispose()
    $planReadLock = $null
    $operationId = [Guid]::NewGuid().ToString('N')
    $operationPlanRelativePath = ".terraform/tfplan-destroy.consuming-$operationId"
    $operationPlanJsonRelativePath = ".terraform/plan-destroy.consuming-$operationId.json"
    $operationPlanPath = Join-Path $labDirectory $operationPlanRelativePath
    $operationPlanJsonPath = Join-Path $labDirectory $operationPlanJsonRelativePath
    New-LabPlanConsumptionMarker -OperationId $operationId -Kind 'DESTROY'
    $script:destroyPlanConsumptionStarted = $true
    [IO.File]::Move($planPath, $operationPlanPath)
    [IO.File]::Move($planJsonPath, $operationPlanJsonPath)
    $planReadLock = Open-ReadLockedFile -Path $operationPlanPath -Label 'Consumed Terraform destroy plan'
    $planJsonReadLock = Open-ReadLockedFile -Path $operationPlanJsonPath -Label 'Consumed Terraform destroy plan JSON'
    if (
        (Get-ReadLockedSha256 -Stream $planReadLock) -ne $validatedPlanSha256 -or
        (Get-ReadLockedSha256 -Stream $planJsonReadLock) -ne $validatedPlanJsonSha256
    ) {
        throw 'The operation-path destroy plan or checked JSON changed; apply is blocked.'
    }
    Assert-ProviderAccountBinding -ExpectedSha256 $plannedProviderAccountSha256 -Phase 'Terraform destroy apply'
    Invoke-CheckedCommand -Label 'terraform apply saved destroy plan' -FilePath $terraformPath -Arguments @(
        "-chdir=$terraformDirectory", 'apply', '-input=false', '-no-color', $operationPlanRelativePath
    )
    Assert-ProviderAccountBinding -ExpectedSha256 $plannedProviderAccountSha256 -Phase 'destroy completion recording'
    $planJsonReadLock.Dispose()
    $planJsonReadLock = $null
    $planReadLock.Dispose()
    $planReadLock = $null
    Complete-LabPlanConsumption `
        -OperationPlanPath $operationPlanPath `
        -OperationPlanJsonPath $operationPlanJsonPath
    $script:destroyPlanConsumptionStarted = $false

    $remainingStateOutput = Invoke-CheckedCommand `
        -Label 'terraform post-destroy state inventory' `
        -FilePath $terraformPath `
        -Arguments @("-chdir=$terraformDirectory", 'state', 'list') `
        -ReturnOutput
    $remainingManaged = @(
        $remainingStateOutput |
            ForEach-Object { ([string]$_).Trim() } |
            Where-Object { $_ -and -not $_.StartsWith('data.') }
    )
    if ($remainingManaged.Count -ne 0) {
        throw 'Post-destroy verification failed: Terraform state is not empty.'
    }
    $script:destroySucceeded = $true
    Write-Host '[7/7] PASS - exact lab graph deleted and Terraform state verified empty.'
}
finally {
    if ($null -ne $planJsonReadLock) {
        $planJsonReadLock.Dispose()
    }
    if ($null -ne $planReadLock) {
        $planReadLock.Dispose()
    }
    if ($null -ne $planOperationLock) {
        $planOperationLock.Dispose()
    }
    if ($script:destroyPlanConsumptionStarted) {
        Write-Warning 'Reviewed destroy-plan consumption did not complete; the durable marker and operation artifacts remain for human state inspection and disposition.'
    }
    if ($planMutexAcquired) {
        $planMutex.ReleaseMutex()
        $planMutexAcquired = $false
    }
    if ($null -ne $planMutex) {
        $planMutex.Dispose()
    }
    Pop-Location
    [Environment]::SetEnvironmentVariable('TF_IN_AUTOMATION', $previousAutomation, 'Process')
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_activation_acknowledgement',
        $previousAcknowledgement,
        'Process'
    )
    [Environment]::SetEnvironmentVariable('TF_VAR_enable_bedrock_live', $previousBedrock, 'Process')
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_bedrock_live_acknowledgement',
        $previousBedrockAcknowledgement,
        'Process'
    )
    [Environment]::SetEnvironmentVariable('TF_VAR_enable_opendart_live', $previousOpenDart, 'Process')
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_opendart_live_acknowledgement',
        $previousOpenDartAcknowledgement,
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_enable_aws_https_preview',
        $previousHttpsPreview,
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_https_preview_acknowledgement',
        $previousHttpsAcknowledgement,
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_preview_access_token_sha256',
        $previousPreviewTokenDigest,
        'Process'
    )

    if ($script:destroySucceeded) {
        foreach ($artifact in @(
            (Join-Path $labDirectory $planRelativePath),
            $planJsonPath
        )) {
            Remove-KnownArtifact -Path $artifact
        }
    }
    if ($script:destroySucceeded) {
        foreach ($artifact in @(
            (Join-Path $labDirectory '.terraform/tfplan-one-command'),
            (Join-Path $labDirectory '.terraform/plan-one-command.json'),
            (Join-Path $labDirectory 'terraform.tfstate.backup')
        )) {
            Remove-KnownArtifact -Path $artifact
        }
    }
}
