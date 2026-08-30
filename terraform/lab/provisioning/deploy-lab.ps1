[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('JCAREER_SYNTHETIC_LAB_APPROVED')]
    [string]$ActivationAcknowledgement,

    [ValidateSet('ap-northeast-2')]
    [string]$Region = 'ap-northeast-2',

    [ValidatePattern('^(?:|[0-9a-f]{64})$')]
    [string]$ProviderAccountSha256 = '',

    [ValidatePattern('^(?:|[0-9a-f]{64})$')]
    [string]$ReviewedPlanSemanticSha256 = '',

    [ValidatePattern('^(?:|[0-9a-f]{64})$')]
    [string]$ReviewedSavedPlanSha256 = '',

    [switch]$Apply,

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

    [Security.SecureString]$HttpsPreviewBootstrapToken,

    [switch]$OpenPreview
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$terraformDirectory = 'terraform/lab'
$planRelativePath = '.terraform/tfplan-one-command'
$planJsonRelativePath = '.terraform/plan-one-command.json'
$labDirectory = Join-Path $repoRoot $terraformDirectory
$planPath = Join-Path $labDirectory $planRelativePath
$planJsonPath = Join-Path $labDirectory $planJsonRelativePath
$planConsumptionMarkerPath = Join-Path $labDirectory '.terraform/jcareer-lab-plan-consumption.json'
$planOperationLockPath = Join-Path $labDirectory '.terraform/jcareer-lab-plan-operation.lock'
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
$script:previewToken = ''
$script:previewTokenSha256 = ''
$script:runtimeTarget = ''
$script:applyAttempted = $false
$script:planConsumptionStarted = $false
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
    throw 'Apply requires a non-placeholder provider account SHA-256 from a reviewed plan-only run.'
}
if (
    $ReviewedPlanSemanticSha256 -match '^([0-9a-f])\1{63}$' -or
    ($Apply -and [string]::IsNullOrWhiteSpace($ReviewedPlanSemanticSha256))
) {
    throw 'Apply requires a non-placeholder semantic plan SHA-256 from a reviewed plan-only run.'
}
if (
    $ReviewedSavedPlanSha256 -match '^([0-9a-f])\1{63}$' -or
    ($Apply -and [string]::IsNullOrWhiteSpace($ReviewedSavedPlanSha256))
) {
    throw 'Apply requires a non-placeholder saved-plan SHA-256 from a reviewed plan-only run.'
}

if ($EnableBedrockLive -and $BedrockAcknowledgement -ne 'JCAREER_SYNTHETIC_BEDROCK_APPROVED') {
    throw 'Bedrock live requires the separate JCAREER_SYNTHETIC_BEDROCK_APPROVED acknowledgement.'
}
if ($EnableOpenDartLive -and $OpenDartAcknowledgement -ne 'JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED') {
    throw 'OpenDART live requires the separate JCAREER_SYNTHETIC_OPENDART_LIVE_APPROVED acknowledgement.'
}
if ($EnableOpenDartLive -and $Apply -and (-not $OpenDartBackendConfig -or -not $OpenDartApplyReceipt)) {
    throw 'Applying an OpenDART-linked lab requires the approved serverless backend and apply receipt.'
}
if ($RunOpenDartLiveSmoke -and (-not $Apply -or -not $EnableOpenDartLive)) {
    throw 'OpenDART live smoke requires both -Apply and -EnableOpenDartLive.'
}
if ($RunOpenDartLiveSmoke) {
    $normalisedDemoCompanyName = (($OpenDartDemoCompanyName -split '\s+') -join ' ').Trim()
    if (
        $OpenDartCallAcknowledgement -ne 'JCAREER_SYNTHETIC_ONLY' -or
        $OpenDartDemoCorpCode -notmatch '^[0-9]{8}$' -or
        $normalisedDemoCompanyName.Length -lt 2 -or
        $normalisedDemoCompanyName.Length -gt 120
    ) {
        throw 'OpenDART live smoke requires its call acknowledgement, 8-digit corp code, and exact public company name.'
    }
}

if ($EnableAwsHttpsPreview) {
    if ($HttpsPreviewAcknowledgement -ne 'JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED') {
        throw 'AWS HTTPS preview requires the separate JCAREER_SYNTHETIC_HTTPS_PREVIEW_APPROVED acknowledgement.'
    }
    if ($null -eq $HttpsPreviewBootstrapToken) {
        throw 'HTTPS preview plan and apply require the same operator-retained SecureString bootstrap token.'
    }
    $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR(
        $HttpsPreviewBootstrapToken
    )
    try {
        $script:previewToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR(
            $tokenPointer
        )
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
    if ($script:previewToken -notmatch '^[0-9a-f]{64}$') {
        throw 'The operator-supplied HTTPS preview bootstrap token must be 64 lowercase hex characters.'
    }
    if ($script:previewToken -match '^([0-9a-f])\1{63}$') {
        throw 'The HTTPS preview bootstrap token must not be an obvious repeated-character placeholder.'
    }
    $tokenAlphabet = [Collections.Generic.HashSet[char]]::new()
    foreach ($tokenCharacter in $script:previewToken.ToCharArray()) {
        $null = $tokenAlphabet.Add($tokenCharacter)
    }
    if ($tokenAlphabet.Count -lt 8) {
        throw 'The HTTPS preview bootstrap token must use at least eight distinct hexadecimal characters.'
    }
    foreach ($period in @(1..32)) {
        $isPeriodic = $true
        for ($tokenIndex = $period; $tokenIndex -lt $script:previewToken.Length; $tokenIndex++) {
            if ($script:previewToken[$tokenIndex] -ne $script:previewToken[$tokenIndex % $period]) {
                $isPeriodic = $false
                break
            }
        }
        if ($isPeriodic) {
            throw 'The HTTPS preview bootstrap token must not be a repeated low-period pattern.'
        }
    }
    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $tokenDigestBytes = $sha256.ComputeHash(
            [Text.Encoding]::UTF8.GetBytes($script:previewToken)
        )
    }
    finally {
        $sha256.Dispose()
    }
    $script:previewTokenSha256 = -join (
        $tokenDigestBytes | ForEach-Object { $_.ToString('x2') }
    )
}
elseif ($OpenPreview) {
    throw '-OpenPreview requires -EnableAwsHttpsPreview.'
}
elseif ($null -ne $HttpsPreviewBootstrapToken) {
    throw '-HttpsPreviewBootstrapToken requires -EnableAwsHttpsPreview.'
}

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
    $protected = [regex]::Replace($protected, '\bvo_[A-Za-z0-9]+\b', '[REDACTED_VPC_ORIGIN_ID]')
    $protected = [regex]::Replace($protected, '\bE[A-Z0-9]{10,}\b', '[REDACTED_CLOUDFRONT_ID]')
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
    if (-not [string]::IsNullOrWhiteSpace($script:previewToken)) {
        $protected = $protected.Replace($script:previewToken, '[REDACTED_PREVIEW_TOKEN]')
    }
    if (-not [string]::IsNullOrWhiteSpace($script:previewTokenSha256)) {
        $protected = $protected.Replace(
            $script:previewTokenSha256,
            '[REDACTED_PREVIEW_DIGEST]'
        )
    }
    return $protected
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$ShowOutput,
        [switch]$ReturnOutput
    )

    $previousErrorAction = $ErrorActionPreference
    try {
        # Windows PowerShell turns ordinary native stderr (for example unittest dots)
        # into ErrorRecord objects when the caller uses Stop. The process exit code is
        # the contract here, so collect both streams without treating stderr as a throw.
        $ErrorActionPreference = 'Continue'
        $output = @(& $FilePath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        $diagnostic = Protect-Diagnostic (($output | Select-Object -Last 40) -join [Environment]::NewLine)
        throw "$Label failed (exit=$exitCode).`n$diagnostic"
    }
    if ($ShowOutput) {
        foreach ($line in $output) {
            Write-Host (Protect-Diagnostic ([string]$line))
        }
    }
    if ($ReturnOutput) {
        return $output
    }
}

function Invoke-HttpStatus {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $previousErrorAction = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& $script:curlPath @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    if ($exitCode -ne 0) {
        $diagnostic = Protect-Diagnostic (($output | Select-Object -Last 10) -join [Environment]::NewLine)
        throw "AWS HTTPS probe failed (exit=$exitCode).`n$diagnostic"
    }
    return (($output -join '').Trim())
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
        throw 'Terraform plan JSON is missing its volatile timestamp field.'
    }
    $planDocument.PSObject.Properties.Remove('timestamp')
    $normalisedPlanProjection = $planDocument | Microsoft.PowerShell.Utility\ConvertTo-Json -Depth 100 -Compress
    return Get-TextSha256 -Text $normalisedPlanProjection
}

function Get-RequiredPlanVariableValue {
    param(
        [Parameter(Mandatory = $true)][object]$PlanDocument,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $variablesProperty = $PlanDocument.PSObject.Properties['variables']
    if ($null -eq $variablesProperty) {
        throw 'Terraform plan JSON is missing its variables object.'
    }
    $variableProperty = $variablesProperty.Value.PSObject.Properties[$Name]
    if ($null -eq $variableProperty) {
        throw "Terraform plan JSON is missing required variable '$Name'."
    }
    $valueProperty = $variableProperty.Value.PSObject.Properties['value']
    if ($null -eq $valueProperty) {
        throw "Terraform plan JSON variable '$Name' is missing its value."
    }
    return $valueProperty.Value
}

function Convert-ObservedPlanBoolean {
    param(
        [Parameter(Mandatory = $true)][object]$Value,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($Value -is [bool]) {
        return [bool]$Value
    }
    if ($Value -is [string]) {
        if ([string]::Equals($Value, 'true', [StringComparison]::Ordinal)) {
            return $true
        }
        if ([string]::Equals($Value, 'false', [StringComparison]::Ordinal)) {
            return $false
        }
    }
    throw "Terraform plan variable '$Name' is not a canonical boolean value."
}

function Assert-PlanRuntimeIntent {
    param([Parameter(Mandatory = $true)][object]$PlanDocument)

    $expectedVariables = [ordered]@{
        activation_acknowledgement   = $ActivationAcknowledgement
        enable_bedrock_live          = [bool]$EnableBedrockLive
        bedrock_live_acknowledgement = $(if ($EnableBedrockLive) { $BedrockAcknowledgement } else { 'disabled' })
        enable_opendart_live          = [bool]$EnableOpenDartLive
        opendart_live_acknowledgement = $(if ($EnableOpenDartLive) { $OpenDartAcknowledgement } else { 'disabled' })
        enable_aws_https_preview      = [bool]$EnableAwsHttpsPreview
        https_preview_acknowledgement = $(if ($EnableAwsHttpsPreview) { $HttpsPreviewAcknowledgement } else { 'disabled' })
        preview_access_token_sha256   = $script:previewTokenSha256
    }
    foreach ($entry in $expectedVariables.GetEnumerator()) {
        $observed = Get-RequiredPlanVariableValue -PlanDocument $PlanDocument -Name $entry.Key
        if ($entry.Value -is [bool]) {
            $observedBoolean = Convert-ObservedPlanBoolean -Value $observed -Name $entry.Key
            if ($observedBoolean -ne [bool]$entry.Value) {
                throw "Reviewed saved plan does not match current runtime intent '$($entry.Key)'."
            }
        }
        elseif (-not [string]::Equals(
            [string]$observed,
            [string]$entry.Value,
            [StringComparison]::Ordinal
        )) {
            throw "Reviewed saved plan does not match current runtime intent '$($entry.Key)'."
        }
    }
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
$script:curlPath = ''
if ($EnableAwsHttpsPreview) {
    $script:curlPath = Resolve-RequiredApplication -Name 'curl.exe'
}

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
        $ActivationAcknowledgement,
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_enable_bedrock_live',
        $EnableBedrockLive.ToString().ToLowerInvariant(),
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_bedrock_live_acknowledgement',
        $(if ($EnableBedrockLive) { $BedrockAcknowledgement } else { 'disabled' }),
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_enable_opendart_live',
        $EnableOpenDartLive.ToString().ToLowerInvariant(),
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_opendart_live_acknowledgement',
        $(if ($EnableOpenDartLive) { $OpenDartAcknowledgement } else { 'disabled' }),
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_enable_aws_https_preview',
        $EnableAwsHttpsPreview.ToString().ToLowerInvariant(),
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_https_preview_acknowledgement',
        $(if ($EnableAwsHttpsPreview) { $HttpsPreviewAcknowledgement } else { 'disabled' }),
        'Process'
    )
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_preview_access_token_sha256',
        $script:previewTokenSha256,
        'Process'
    )

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

    Write-Host '[1/9] AWS credential, account-digest, and fixed-region preflight...'
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
    $terraformVersion = (($terraformVersionOutput -join [Environment]::NewLine) | ConvertFrom-Json).terraform_version
    if ($terraformVersion -ne '1.15.9') {
        throw "Terraform 1.15.9 is required; observed $terraformVersion."
    }

    Write-Host '[2/9] Exact lab source boundary and regression tests...'
    Invoke-CheckedCommand -Label 'lab static checker' -FilePath $pythonPath `
        -Arguments @('scripts/check_lab_static.py') -ShowOutput
    Invoke-CheckedCommand -Label 'lab static tests' -FilePath $pythonPath `
        -Arguments @('-m', 'unittest', 'tests.test_lab_static') -ShowOutput

    Write-Host '[3/9] Terraform init, format, and validate...'
    Invoke-CheckedCommand -Label 'terraform init' -FilePath $terraformPath -Arguments @(
        "-chdir=$terraformDirectory", 'init', '-input=false', '-no-color', '-lockfile=readonly'
    )
    Invoke-CheckedCommand -Label 'terraform fmt check' -FilePath $terraformPath -Arguments @(
        "-chdir=$terraformDirectory", 'fmt', '-check', '-no-color'
    )
    Invoke-CheckedCommand -Label 'terraform validate' -FilePath $terraformPath -Arguments @(
        "-chdir=$terraformDirectory", 'validate', '-no-color'
    )

    if ($Apply) {
        Write-Host '[4/9] Loading the retained human-reviewed saved plan; no re-plan is performed...'
        if (-not [IO.File]::Exists($planPath) -or -not [IO.File]::Exists($planJsonPath)) {
            throw 'Apply requires the retained saved plan and checked JSON from the plan-only run.'
        }
        $planReadLock = Open-ReadLockedFile -Path $planPath -Label 'Terraform saved plan'
        $validatedPlanSha256 = Get-ReadLockedSha256 -Stream $planReadLock
        if (-not [string]::Equals(
            $validatedPlanSha256,
            $ReviewedSavedPlanSha256,
            [StringComparison]::Ordinal
        )) {
            throw 'The retained saved-plan binary does not match the human-reviewed saved-plan digest.'
        }
        $planJsonReadLock = Open-ReadLockedFile -Path $planJsonPath -Label 'Terraform plan JSON'
        $validatedPlanJsonSha256 = Get-ReadLockedSha256 -Stream $planJsonReadLock
        $planJson = [IO.File]::ReadAllText($planJsonPath, [Text.Encoding]::UTF8)
        if ($validatedPlanJsonSha256 -ne (Get-TextSha256 -Text $planJson)) {
            throw 'Terraform plan JSON changed while its retained artifact was being locked.'
        }
    }
    else {
        Write-Host '[4/9] Creating a saved plan without printing account or resource identifiers...'
        Invoke-CheckedCommand -Label 'terraform saved plan' -FilePath $terraformPath -Arguments @(
            "-chdir=$terraformDirectory", 'plan', '-input=false', '-no-color', "-out=$planRelativePath"
        )
        $planReadLock = Open-ReadLockedFile -Path $planPath -Label 'Terraform saved plan'
        $validatedPlanSha256 = Get-ReadLockedSha256 -Stream $planReadLock
        $planJsonOutput = Invoke-CheckedCommand `
            -Label 'terraform plan JSON' `
            -FilePath $terraformPath `
            -Arguments @("-chdir=$terraformDirectory", 'show', '-json', $planRelativePath) `
            -ReturnOutput
        $planJson = $planJsonOutput -join [Environment]::NewLine
        [IO.File]::WriteAllText($planJsonPath, $planJson, $utf8WithoutBom)
        $planJsonReadLock = Open-ReadLockedFile -Path $planJsonPath -Label 'Terraform plan JSON'
        $validatedPlanJsonSha256 = Get-ReadLockedSha256 -Stream $planJsonReadLock
        if ($validatedPlanJsonSha256 -ne (Get-TextSha256 -Text $planJson)) {
            throw 'Terraform plan JSON changed before its read lock was established.'
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
        throw 'The retained saved plan does not match the human-reviewed semantic plan digest.'
    }

    $planDocument = $planJson | ConvertFrom-Json
    Assert-PlanRuntimeIntent -PlanDocument $planDocument

    Write-Host '[5/9] Cost, exposure, and exact-resource allowlist check...'
    Invoke-CheckedCommand -Label 'lab budget guard' -FilePath $pythonPath -Arguments @(
        'scripts/check_lab_budget.py', '--plan', $planJsonPath
    ) -ShowOutput

    $resourceChanges = @($planDocument.resource_changes)
    $destructiveChanges = @(
        $resourceChanges | Where-Object {
            @($_.change.actions).Contains('delete')
        }
    )
    if ($destructiveChanges.Count -gt 0) {
        throw "Saved plan contains $($destructiveChanges.Count) delete or replacement action(s); one-command apply is blocked."
    }
    $createCount = @($resourceChanges | Where-Object { @($_.change.actions).Contains('create') }).Count
    $updateCount = @($resourceChanges | Where-Object { @($_.change.actions).Contains('update') }).Count
    $noOpCount = @($resourceChanges | Where-Object { @($_.change.actions).Contains('no-op') }).Count
    Write-Host "[plan] create=$createCount update=$updateCount delete=0 no-op=$noOpCount"
    Assert-ProviderAccountBinding -ExpectedSha256 $plannedProviderAccountSha256 -Phase 'saved-plan review completion'

    if (-not $Apply) {
        Write-Host '[6/9] PLAN-ONLY PASS - no AWS resource was changed.'
        Write-Host "provider_account_sha256=$plannedProviderAccountSha256"
        Write-Host "reviewed_saved_plan_sha256=$validatedPlanSha256"
        Write-Host "reviewed_plan_semantic_sha256=$planSemanticSha256"
        Write-Host 'Re-run the same mode and retained HTTPS token, adding all three printed digests and -Apply after reviewing the guarded plan.'
        return
    }

    Write-Host '[6/9] Applying only the checked saved plan...'
    if (
        (Get-ReadLockedSha256 -Stream $planReadLock) -ne $validatedPlanSha256 -or
        (Get-ReadLockedSha256 -Stream $planJsonReadLock) -ne $validatedPlanJsonSha256
    ) {
        throw 'The saved plan or its checked JSON changed after validation; apply is blocked.'
    }
    $planJsonReadLock.Dispose()
    $planJsonReadLock = $null
    $planReadLock.Dispose()
    $planReadLock = $null
    $operationId = [Guid]::NewGuid().ToString('N')
    $operationPlanRelativePath = ".terraform/tfplan-one-command.consuming-$operationId"
    $operationPlanJsonRelativePath = ".terraform/plan-one-command.consuming-$operationId.json"
    $operationPlanPath = Join-Path $labDirectory $operationPlanRelativePath
    $operationPlanJsonPath = Join-Path $labDirectory $operationPlanJsonRelativePath
    New-LabPlanConsumptionMarker -OperationId $operationId -Kind 'CREATE'
    $script:planConsumptionStarted = $true
    [IO.File]::Move($planPath, $operationPlanPath)
    [IO.File]::Move($planJsonPath, $operationPlanJsonPath)
    $planReadLock = Open-ReadLockedFile -Path $operationPlanPath -Label 'Consumed Terraform saved plan'
    $planJsonReadLock = Open-ReadLockedFile -Path $operationPlanJsonPath -Label 'Consumed Terraform plan JSON'
    if (
        (Get-ReadLockedSha256 -Stream $planReadLock) -ne $validatedPlanSha256 -or
        (Get-ReadLockedSha256 -Stream $planJsonReadLock) -ne $validatedPlanJsonSha256
    ) {
        throw 'The operation-path saved plan or checked JSON changed; apply is blocked.'
    }
    Assert-ProviderAccountBinding -ExpectedSha256 $plannedProviderAccountSha256 -Phase 'Terraform apply'
    $script:applyAttempted = $true
    Invoke-CheckedCommand -Label 'terraform apply saved plan' -FilePath $terraformPath -Arguments @(
        "-chdir=$terraformDirectory", 'apply', '-input=false', '-no-color', $operationPlanRelativePath
    )
    Assert-ProviderAccountBinding -ExpectedSha256 $plannedProviderAccountSha256 -Phase 'apply completion recording'
    $planJsonReadLock.Dispose()
    $planJsonReadLock = $null
    $planReadLock.Dispose()
    $planReadLock = $null
    Complete-LabPlanConsumption `
        -OperationPlanPath $operationPlanPath `
        -OperationPlanJsonPath $operationPlanJsonPath
    $script:planConsumptionStarted = $false

    Write-Host '[7/9] Reading the managed runtime target and non-secret role handoff...'
    $instanceOutput = Invoke-CheckedCommand `
        -Label 'terraform runtime output' `
        -FilePath $terraformPath `
        -Arguments @("-chdir=$terraformDirectory", 'output', '-raw', 'runtime_instance_id') `
        -ReturnOutput
    $instanceId = (($instanceOutput -join '').Trim())
    if ($instanceId -notmatch '^i-[0-9a-f]+$') {
        throw 'Terraform did not return a valid managed runtime target.'
    }
    $script:runtimeTarget = $instanceId
    $roleOutput = Invoke-CheckedCommand `
        -Label 'terraform runtime role output' `
        -FilePath $terraformPath `
        -Arguments @("-chdir=$terraformDirectory", 'output', '-raw', 'runtime_role_name') `
        -ReturnOutput
    $runtimeRoleName = (($roleOutput -join '').Trim())
    if ($runtimeRoleName -notmatch '^[a-z0-9][a-z0-9_-]{2,63}$') {
        throw 'Terraform did not return the bounded non-secret runtime role name.'
    }
    Write-Host "runtime_role_name=$runtimeRoleName"

    Write-Host '[8/9] Deploying the six-service synthetic runtime through SSM...'
    & (Join-Path $PSScriptRoot 'deploy-runtime.ps1') `
        -InstanceId $instanceId `
        -ActivationAcknowledgement $ActivationAcknowledgement `
        -Region $Region `
        -EnableBedrockLive:$EnableBedrockLive `
        -BedrockAcknowledgement $BedrockAcknowledgement `
        -EnableOpenDartLive:$EnableOpenDartLive `
        -OpenDartAcknowledgement $OpenDartAcknowledgement `
        -OpenDartBackendConfig $OpenDartBackendConfig `
        -OpenDartApplyReceipt $OpenDartApplyReceipt `
        -RunOpenDartLiveSmoke:$RunOpenDartLiveSmoke `
        -OpenDartDemoCorpCode $OpenDartDemoCorpCode `
        -OpenDartDemoCompanyName $OpenDartDemoCompanyName `
        -OpenDartCallAcknowledgement $OpenDartCallAcknowledgement `
        -EnableAwsHttpsPreview:$EnableAwsHttpsPreview `
        -HttpsPreviewAcknowledgement $HttpsPreviewAcknowledgement

    Write-Host '[9/9] PASS - AWS lab and remote smoke checks completed.'
    if ($EnableAwsHttpsPreview) {
        $previewOutput = Invoke-CheckedCommand `
            -Label 'Terraform HTTPS preview output' `
            -FilePath $terraformPath `
            -Arguments @("-chdir=$terraformDirectory", 'output', '-raw', 'aws_https_preview_url') `
            -ReturnOutput
        $previewUrl = (($previewOutput -join '').Trim())
        if ($previewUrl -notmatch '^https://[a-z0-9.-]+\.cloudfront\.net/jobs$') {
            throw 'Terraform did not return a clean CloudFront HTTPS preview URL.'
        }
        Write-Host "AWS HTTPS preview: $previewUrl"
        Write-Host 'Synthetic data only. The shared preview cookie is not production per-user authentication.'
        Write-Host "Preview bootstrap approval SHA-256 (not a bearer): $($script:previewTokenSha256)"
        $previewUri = [Uri]$previewUrl
        $previewBase = $previewUri.GetLeftPart([UriPartial]::Authority) + '/'
        $bootstrapUrl = $previewBase + '?jcareer_preview=' + $script:previewToken
        $cookiePath = Join-Path ([IO.Path]::GetTempPath()) (
            'jcareer-preview-cookie-' + [Guid]::NewGuid().ToString('N') + '.txt'
        )
        try {
            $boundaryVerified = $false
            for ($attempt = 1; $attempt -le 12; $attempt++) {
                if (Test-Path -LiteralPath $cookiePath) {
                    Remove-Item -LiteralPath $cookiePath -Force
                }
                $unauthenticatedStatus = Invoke-HttpStatus -Arguments @(
                    '--silent', '--show-error', '--max-time', '30', '--output', 'NUL',
                    '--write-out', '%{http_code}', $previewUrl
                )
                $bootstrapStatus = Invoke-HttpStatus -Arguments @(
                    '--silent', '--show-error', '--max-time', '30', '--output', 'NUL',
                    '--cookie-jar', $cookiePath, '--write-out', '%{http_code}', $bootstrapUrl
                )
                $authenticatedStatus = Invoke-HttpStatus -Arguments @(
                    '--silent', '--show-error', '--max-time', '30', '--output', 'NUL',
                    '--cookie', $cookiePath, '--write-out', '%{http_code}', $previewUrl
                )
                if (
                    $unauthenticatedStatus -eq '403' -and
                    $bootstrapStatus -eq '302' -and
                    $authenticatedStatus -eq '200'
                ) {
                    $boundaryVerified = $true
                    break
                }
                if ($attempt -lt 12) {
                    Start-Sleep -Seconds 10
                }
            }
            if (-not $boundaryVerified) {
                throw (
                    'AWS HTTPS preview boundary returned unexpected statuses: ' +
                    "unauthenticated=$unauthenticatedStatus bootstrap=$bootstrapStatus " +
                    "authenticated=$authenticatedStatus"
                )
            }
            Write-Host 'AWS HTTPS boundary: unauthenticated=403 bootstrap=302 authenticated=200'
        }
        finally {
            if (Test-Path -LiteralPath $cookiePath) {
                Remove-Item -LiteralPath $cookiePath -Force
            }
        }
        if ($OpenPreview) {
            Microsoft.PowerShell.Management\Start-Process $bootstrapUrl
            Write-Host 'The gated AWS URL was opened in the operator browser without printing its bootstrap token.'
        }
    }
    else {
        Write-Host 'Access remains private: use the documented SSM loopback tunnel; do not enter real data.'
    }
}
catch {
    $failure = $_
    if (-not [string]::IsNullOrWhiteSpace($script:runtimeTarget)) {
        Write-Warning 'Post-apply lab verification failed; requesting a fail-safe stop for the validated runtime target.'
        try {
            Invoke-CheckedCommand -Label 'fail-safe runtime stop' -FilePath $awsPath -Arguments @(
                'ec2', 'stop-instances', '--region', $Region,
                '--instance-ids', $script:runtimeTarget, '--no-cli-pager'
            )
        }
        catch {
            Write-Warning (
                'The fail-safe stop request also failed: ' +
                (Protect-Diagnostic ([string]$_.Exception.Message))
            )
        }
        Write-Warning 'Stopping EC2 does not remove NAT or CloudFront; use the separately approved destroy wrapper.'
    }
    elseif ($script:applyAttempted) {
        Write-Warning 'Apply did not reach a validated runtime target; inspect state and use the separately approved destroy recovery path.'
    }
    if ($script:planConsumptionStarted) {
        Write-Warning 'Reviewed-plan consumption did not complete; the durable marker and operation artifacts remain for human state inspection and disposition.'
    }
    throw $failure
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
    $script:previewToken = ''
    $script:previewTokenSha256 = ''
}
