[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('JCAREER_SYNTHETIC_LAB_APPROVED')]
    [string]$ActivationAcknowledgement,

    [ValidateSet('ap-northeast-2')]
    [string]$Region = 'ap-northeast-2',

    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$terraformDirectory = 'terraform/lab'
$planRelativePath = '.terraform/tfplan-one-command'
$planJsonRelativePath = '.terraform/plan-one-command.json'
$planJsonPath = Join-Path $repoRoot (Join-Path $terraformDirectory $planJsonRelativePath)
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)

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
        '\b(i|vpc|subnet|sg|igw|rtb|eni)-[0-9a-f]+\b',
        '[REDACTED_RESOURCE_ID]',
        [Text.RegularExpressions.RegexOptions]::IgnoreCase
    )
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

foreach ($tool in @('aws', 'terraform', 'python')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "$tool is required."
    }
}

$previousAutomation = [Environment]::GetEnvironmentVariable('TF_IN_AUTOMATION', 'Process')
$previousAcknowledgement = [Environment]::GetEnvironmentVariable(
    'TF_VAR_activation_acknowledgement',
    'Process'
)
$previousBedrock = [Environment]::GetEnvironmentVariable('TF_VAR_enable_bedrock_live', 'Process')

Push-Location $repoRoot
try {
    [Environment]::SetEnvironmentVariable('TF_IN_AUTOMATION', '1', 'Process')
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_activation_acknowledgement',
        $ActivationAcknowledgement,
        'Process'
    )
    [Environment]::SetEnvironmentVariable('TF_VAR_enable_bedrock_live', 'false', 'Process')

    Write-Host '[1/9] AWS credential and fixed-region preflight...'
    Invoke-CheckedCommand -Label 'AWS credential preflight' -FilePath 'aws' -Arguments @(
        'sts', 'get-caller-identity', '--region', $Region, '--output', 'json', '--no-cli-pager'
    )

    $terraformVersionOutput = Invoke-CheckedCommand `
        -Label 'Terraform version' `
        -FilePath 'terraform' `
        -Arguments @('version', '-json') `
        -ReturnOutput
    $terraformVersion = (($terraformVersionOutput -join [Environment]::NewLine) | ConvertFrom-Json).terraform_version
    if ($terraformVersion -ne '1.15.9') {
        throw "Terraform 1.15.9 is required; observed $terraformVersion."
    }

    Write-Host '[2/9] Exact lab source boundary and regression tests...'
    Invoke-CheckedCommand -Label 'lab static checker' -FilePath 'python' `
        -Arguments @('scripts/check_lab_static.py') -ShowOutput
    Invoke-CheckedCommand -Label 'lab static tests' -FilePath 'python' `
        -Arguments @('-m', 'unittest', 'tests.test_lab_static') -ShowOutput

    Write-Host '[3/9] Terraform init, format, and validate...'
    Invoke-CheckedCommand -Label 'terraform init' -FilePath 'terraform' -Arguments @(
        "-chdir=$terraformDirectory", 'init', '-input=false', '-no-color'
    )
    Invoke-CheckedCommand -Label 'terraform fmt check' -FilePath 'terraform' -Arguments @(
        "-chdir=$terraformDirectory", 'fmt', '-check', '-no-color'
    )
    Invoke-CheckedCommand -Label 'terraform validate' -FilePath 'terraform' -Arguments @(
        "-chdir=$terraformDirectory", 'validate', '-no-color'
    )

    Write-Host '[4/9] Creating a saved plan without printing account or resource identifiers...'
    Invoke-CheckedCommand -Label 'terraform saved plan' -FilePath 'terraform' -Arguments @(
        "-chdir=$terraformDirectory", 'plan', '-input=false', '-no-color', "-out=$planRelativePath"
    )
    $planJsonOutput = Invoke-CheckedCommand `
        -Label 'terraform plan JSON' `
        -FilePath 'terraform' `
        -Arguments @("-chdir=$terraformDirectory", 'show', '-json', $planRelativePath) `
        -ReturnOutput
    $planJson = $planJsonOutput -join [Environment]::NewLine
    [IO.File]::WriteAllText($planJsonPath, $planJson, $utf8WithoutBom)

    Write-Host '[5/9] Cost, exposure, and exact-resource allowlist check...'
    Invoke-CheckedCommand -Label 'lab budget guard' -FilePath 'python' -Arguments @(
        'scripts/check_lab_budget.py', '--plan', $planJsonPath
    ) -ShowOutput

    $planDocument = $planJson | ConvertFrom-Json
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

    if (-not $Apply) {
        Write-Host '[6/9] PLAN-ONLY PASS - no AWS resource was changed.'
        Write-Host 'Re-run this same command with -Apply after reviewing the guarded plan.'
        return
    }

    Write-Host '[6/9] Applying only the checked saved plan...'
    Invoke-CheckedCommand -Label 'terraform apply saved plan' -FilePath 'terraform' -Arguments @(
        "-chdir=$terraformDirectory", 'apply', '-input=false', '-no-color', $planRelativePath
    )

    Write-Host '[7/9] Reading the managed runtime target without printing its identifier...'
    $instanceOutput = Invoke-CheckedCommand `
        -Label 'terraform runtime output' `
        -FilePath 'terraform' `
        -Arguments @("-chdir=$terraformDirectory", 'output', '-raw', 'runtime_instance_id') `
        -ReturnOutput
    $instanceId = (($instanceOutput -join '').Trim())
    if ($instanceId -notmatch '^i-[0-9a-f]+$') {
        throw 'Terraform did not return a valid managed runtime target.'
    }

    Write-Host '[8/9] Deploying the six-service synthetic runtime through SSM...'
    & (Join-Path $PSScriptRoot 'deploy-runtime.ps1') `
        -InstanceId $instanceId `
        -ActivationAcknowledgement $ActivationAcknowledgement `
        -Region $Region

    Write-Host '[9/9] PASS - AWS lab and remote smoke checks completed.'
    Write-Host 'Access remains private: use the documented SSM loopback tunnel; do not enter real data.'
}
finally {
    Pop-Location
    [Environment]::SetEnvironmentVariable('TF_IN_AUTOMATION', $previousAutomation, 'Process')
    [Environment]::SetEnvironmentVariable(
        'TF_VAR_activation_acknowledgement',
        $previousAcknowledgement,
        'Process'
    )
    [Environment]::SetEnvironmentVariable('TF_VAR_enable_bedrock_live', $previousBedrock, 'Process')
}
