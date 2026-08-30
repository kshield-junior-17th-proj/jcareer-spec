[CmdletBinding(DefaultParameterSetName = 'Plan')]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('serverless-opendart', 'workplace-images', 'workplace-endpoints')]
    [string]$Root,

    [Parameter(Mandatory = $true, ParameterSetName = 'Plan')]
    [Parameter(Mandatory = $true, ParameterSetName = 'Apply')]
    [string]$BackendConfig,

    [Parameter(Mandatory = $true, ParameterSetName = 'Plan')]
    [string]$VarFile,

    [Parameter(Mandatory = $true, ParameterSetName = 'Apply')]
    [switch]$Apply,

    [Parameter(Mandatory = $true, ParameterSetName = 'Apply')]
    [string]$ApprovalFile,

    [Parameter(ParameterSetName = 'Apply')]
    [ValidatePattern('^[0-9a-f]{64}$')]
    [string]$ArtifactSha256 = '',

    [Parameter(ParameterSetName = 'Plan')]
    [Parameter(ParameterSetName = 'Apply')]
    [string]$ImageReceipt = '',

    [Parameter(ParameterSetName = 'Plan')]
    [Parameter(ParameterSetName = 'Apply')]
    [string]$BuildObservation = ''
)

$ErrorActionPreference = 'Stop'
Microsoft.PowerShell.Core\Set-StrictMode -Version Latest
$repoRoot = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $PSScriptRoot '..')).Path
$rootMap = @{
    'serverless-opendart' = @{
        Path = 'terraform/serverless-opendart'
        Scope = 'serverless-opendart'
        Checker = 'scripts/check_serverless_opendart_static.py'
    }
    'workplace-images' = @{
        Path = 'terraform/workplace-images'
        Scope = 'workplace-windows-image'
        Checker = 'scripts/check_workplace_images_static.py'
    }
    'workplace-endpoints' = @{
        Path = 'terraform/workplace-endpoints'
        Scope = 'workplace-windows-endpoints'
        Checker = 'scripts/check_workplace_endpoints_static.py'
    }
}
$selected = $rootMap[$Root]
$terraformRoot = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot $selected.Path)).Path
if (-not $terraformRoot.StartsWith($repoRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Terraform root resolved outside the repository.'
}
$workDir = Microsoft.PowerShell.Management\Join-Path $terraformRoot '.terraform'
Microsoft.PowerShell.Management\New-Item -ItemType Directory -Path $workDir -Force | Microsoft.PowerShell.Core\Out-Null
$savedPlanFile = Microsoft.PowerShell.Management\Join-Path $workDir 'jcareer-approved.tfplan'
$planFile = $savedPlanFile
$planJson = Microsoft.PowerShell.Management\Join-Path $workDir 'jcareer-approved.json'
$receiptFile = Microsoft.PowerShell.Management\Join-Path $workDir 'last-apply-receipt.json'
$planBindingFile = Microsoft.PowerShell.Management\Join-Path $workDir 'jcareer-approved.bindings.json'
$legacyApplyOperationJournalFile = Microsoft.PowerShell.Management\Join-Path $workDir 'jcareer-apply-operation-journal.json'
$legacyTeardownOperationJournalFile = Microsoft.PowerShell.Management\Join-Path $workDir 'jcareer-teardown-operation-journal.json'
$operationJournalFile = ''
$utf8WithoutBom = [Text.UTF8Encoding]::new($false)
$script:terraformExecutable = ''
$script:pythonExecutable = ''
$script:awsExecutable = ''
$script:backendLeaseMutex = $null
$script:backendLeaseAcquired = $false
$script:protectedSnapshotStreams = @()
$script:protectedSnapshotDirectory = ''
$script:protectedSnapshotCount = 0
$script:localSnapshotCleanupObserved = $false
$script:planJsonReadLock = $null
$script:operationJournalStarted = $false
$script:operationJournalDocument = $null
$script:sharedLedgerDirectory = ''

function New-ProtectedEmptyFile {
    param([Parameter(Mandatory = $true)][string]$Path, [string]$AclTemplatePath = '')
    $acl = if ($AclTemplatePath -and [IO.File]::Exists($AclTemplatePath)) {
        Microsoft.PowerShell.Security\Get-Acl -LiteralPath $AclTemplatePath
    }
    else { New-CurrentUserFileAcl }
    $stream = [IO.FileStream]::new(
        $Path,
        [IO.FileMode]::CreateNew,
        [Security.AccessControl.FileSystemRights]::FullControl,
        [IO.FileShare]::None,
        4096,
        [IO.FileOptions]::None,
        $acl
    )
    $stream.Dispose()
}

function New-CurrentUserFileAcl {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [Security.AccessControl.FileSecurity]::new()
    $acl.SetOwner($identity)
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $identity, [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow
    ))
    return $acl
}

function New-ProtectedDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)
    Microsoft.PowerShell.Management\New-Item -ItemType Directory -Path $Path | Microsoft.PowerShell.Core\Out-Null
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($identity)
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $identity,
        [Security.AccessControl.FileSystemRights]::FullControl,
        ([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit),
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    ))
    Microsoft.PowerShell.Security\Set-Acl -LiteralPath $Path -AclObject $acl
}

function New-OperatorLedgerDirectoryAcl {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($identity)
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $identity,
        [Security.AccessControl.FileSystemRights]::FullControl,
        ([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit),
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    ))
    return $acl
}

function Assert-OperatorLedgerDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)
    $fullPath = [IO.Path]::GetFullPath($Path)
    if (-not [IO.Directory]::Exists($fullPath)) { throw 'The shared Terraform operator ledger directory is unavailable.' }
    $attributes = [IO.File]::GetAttributes($fullPath)
    if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'The shared Terraform operator ledger directory must not be a reparse point.'
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = Microsoft.PowerShell.Security\Get-Acl -LiteralPath $fullPath
    $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier])
    $rules = @($acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    $expectedInheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
    if (
        $owner.Value -ne $identity.Value -or
        -not $acl.AreAccessRulesProtected -or
        -not $acl.AreAccessRulesCanonical -or
        $rules.Count -ne 1
    ) {
        throw 'The shared Terraform operator ledger directory ACL is not operator-only.'
    }
    $rule = $rules[0]
    if (
        $rule.IsInherited -or
        $rule.IdentityReference.Value -ne $identity.Value -or
        $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
        [int]($rule.FileSystemRights) -ne [int][Security.AccessControl.FileSystemRights]::FullControl -or
        $rule.InheritanceFlags -ne $expectedInheritance -or
        $rule.PropagationFlags -ne [Security.AccessControl.PropagationFlags]::None
    ) {
        throw 'The shared Terraform operator ledger directory ACL rule is not exact.'
    }
}

function Initialize-SharedOperationLedger {
    param([Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$CanonicalBackendSha256)
    $localApplicationData = [Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    if (-not $localApplicationData -or -not [IO.Directory]::Exists($localApplicationData)) {
        throw 'The local application-data directory is unavailable.'
    }
    $localRoot = [IO.Path]::GetFullPath($localApplicationData).TrimEnd('\', '/')
    $ledgerDirectory = [IO.Path]::GetFullPath(
        (Microsoft.PowerShell.Management\Join-Path $localRoot 'JCareerTerraformOperatorLedger-v1')
    )
    $localPrefix = $localRoot + [IO.Path]::DirectorySeparatorChar
    if (-not $ledgerDirectory.StartsWith($localPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The shared Terraform operator ledger resolved outside local application data.'
    }
    if (-not [IO.Directory]::Exists($ledgerDirectory)) {
        [void][IO.Directory]::CreateDirectory($ledgerDirectory, (New-OperatorLedgerDirectoryAcl))
    }
    Assert-OperatorLedgerDirectory -Path $ledgerDirectory
    $script:sharedLedgerDirectory = $ledgerDirectory
    return Microsoft.PowerShell.Management\Join-Path $ledgerDirectory ('jcareer-terraform-active-' + $CanonicalBackendSha256 + '.json')
}

function Get-StreamSha256 {
    param([Parameter(Mandatory = $true)][IO.Stream]$Stream)
    $Stream.Position = 0
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = $sha.ComputeHash($Stream) }
    finally { $sha.Dispose() }
    return ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
}

function Get-ByteArraySha256 {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = $sha.ComputeHash($Bytes) }
    finally { $sha.Dispose() }
    return ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
}

function Copy-ProtectedStableFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$DestinationName
    )
    if (-not [IO.File]::Exists($Source)) { throw 'A required Terraform input is unavailable.' }
    $destinationPath = [IO.Path]::GetFullPath(
        (Microsoft.PowerShell.Management\Join-Path $script:protectedSnapshotDirectory $DestinationName)
    )
    $snapshotPrefix = $script:protectedSnapshotDirectory.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $destinationPath.StartsWith($snapshotPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'A Terraform input snapshot path escaped its protected directory.'
    }
    $sourceStream = $null
    $destinationStream = $null
    $snapshotReadLock = $null
    try {
        $sourceStream = [IO.File]::Open(
            [IO.Path]::GetFullPath($Source), [IO.FileMode]::Open,
            [IO.FileAccess]::Read, [IO.FileShare]::Read
        )
        $sourceLength = [long]$sourceStream.Length
        $sourcePreHash = Get-StreamSha256 -Stream $sourceStream
        $sourceStream.Position = 0
        $destinationStream = [IO.FileStream]::new(
            $destinationPath,
            [IO.FileMode]::CreateNew,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [IO.FileShare]::Read,
            4096,
            [IO.FileOptions]::SequentialScan,
            (New-CurrentUserFileAcl)
        )
        $sourceStream.CopyTo($destinationStream)
        $destinationStream.Flush($true)
        if ([long]$destinationStream.Length -ne $sourceLength) { throw 'A Terraform input snapshot length changed.' }
        $snapshotHash = Get-StreamSha256 -Stream $destinationStream
        $sourcePostHash = Get-StreamSha256 -Stream $sourceStream
        if ($sourcePreHash -ne $snapshotHash -or $sourcePreHash -ne $sourcePostHash) {
            throw 'A Terraform input changed during protected snapshot capture.'
        }
        $destinationStream.Dispose()
        $destinationStream = $null
        $snapshotReadLock = [IO.File]::Open(
            $destinationPath, [IO.FileMode]::Open,
            [IO.FileAccess]::Read, [IO.FileShare]::Read
        )
        if ([long]$snapshotReadLock.Length -ne $sourceLength) {
            throw 'A Terraform input snapshot length changed before read locking.'
        }
        $snapshotLockedHash = Get-StreamSha256 -Stream $snapshotReadLock
        if ($snapshotLockedHash -ne $sourcePreHash) {
            throw 'A Terraform input snapshot changed before read locking.'
        }
        $snapshotReadLock.Position = 0
        $script:protectedSnapshotStreams += $snapshotReadLock
        $script:protectedSnapshotCount += 1
        $snapshotReadLock = $null
        return $destinationPath
    }
    finally {
        if ($null -ne $sourceStream) { $sourceStream.Dispose() }
        if ($null -ne $destinationStream) {
            $destinationStream.Dispose()
            if ([IO.File]::Exists($destinationPath)) { [IO.File]::Delete($destinationPath) }
        }
        if ($null -ne $snapshotReadLock) {
            $snapshotReadLock.Dispose()
            if ([IO.File]::Exists($destinationPath)) { [IO.File]::Delete($destinationPath) }
        }
    }
}

function Move-ProtectedOneShotFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$DestinationName
    )
    if (-not [IO.File]::Exists($Source)) { throw 'A required one-shot Terraform input is unavailable.' }
    $sourcePath = [IO.Path]::GetFullPath($Source)
    $destinationPath = [IO.Path]::GetFullPath(
        (Microsoft.PowerShell.Management\Join-Path $script:protectedSnapshotDirectory $DestinationName)
    )
    $snapshotPrefix = $script:protectedSnapshotDirectory.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $destinationPath.StartsWith($snapshotPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'A one-shot Terraform input path escaped its protected directory.'
    }
    if ([IO.File]::Exists($destinationPath)) { throw 'A one-shot Terraform input destination already exists.' }
    $sourceReadLock = $null
    $snapshotReadLock = $null
    try {
        $sourceReadLock = [IO.File]::Open(
            $sourcePath, [IO.FileMode]::Open,
            [IO.FileAccess]::Read, ([IO.FileShare]::Read -bor [IO.FileShare]::Delete)
        )
        $sourceLength = [long]$sourceReadLock.Length
        $sourceHash = Get-StreamSha256 -Stream $sourceReadLock
        $sourceReadLock.Position = 0
        Microsoft.PowerShell.Security\Set-Acl -LiteralPath $sourcePath -AclObject (New-CurrentUserFileAcl)
        # Both paths are under this Terraform root's .terraform directory, so this is a same-volume atomic consume.
        [IO.File]::Move($sourcePath, $destinationPath)
        Microsoft.PowerShell.Security\Set-Acl -LiteralPath $destinationPath -AclObject (New-CurrentUserFileAcl)
        $snapshotReadLock = [IO.File]::Open(
            $destinationPath, [IO.FileMode]::Open,
            [IO.FileAccess]::Read, [IO.FileShare]::Read
        )
        if ([long]$snapshotReadLock.Length -ne $sourceLength) {
            throw 'A consumed one-shot Terraform input length changed during its atomic move.'
        }
        $destinationHash = Get-StreamSha256 -Stream $snapshotReadLock
        if ($destinationHash -ne $sourceHash) {
            throw 'A consumed one-shot Terraform input changed during its atomic move.'
        }
        $snapshotReadLock.Position = 0
        $script:protectedSnapshotStreams += $snapshotReadLock
        $script:protectedSnapshotCount += 1
        $snapshotReadLock = $null
        return $destinationPath
    }
    finally {
        if ($null -ne $sourceReadLock) { $sourceReadLock.Dispose() }
        if ($null -ne $snapshotReadLock) { $snapshotReadLock.Dispose() }
    }
}

function Open-VerifiedPlanJsonReadLock {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Text
    )
    if ($null -ne $script:planJsonReadLock) { throw 'A plan JSON read lock is already active.' }
    $expectedBytes = $utf8WithoutBom.GetBytes($Text)
    $expectedLength = [long]$expectedBytes.Length
    $expectedHash = Get-ByteArraySha256 -Bytes $expectedBytes
    $readLock = $null
    try {
        $readLock = [IO.File]::Open(
            [IO.Path]::GetFullPath($Path), [IO.FileMode]::Open,
            [IO.FileAccess]::Read, [IO.FileShare]::Read
        )
        if ([long]$readLock.Length -ne $expectedLength) {
            throw 'The generated plan JSON length changed before checker read locking.'
        }
        $lockedHash = Get-StreamSha256 -Stream $readLock
        if ($lockedHash -ne $expectedHash) {
            throw 'The generated plan JSON changed before checker read locking.'
        }
        $readLock.Position = 0
        $script:planJsonReadLock = $readLock
        $readLock = $null
    }
    finally {
        if ($null -ne $readLock) { $readLock.Dispose() }
    }
}

function Close-VerifiedPlanJsonReadLock {
    if ($null -ne $script:planJsonReadLock) {
        $script:planJsonReadLock.Dispose()
        $script:planJsonReadLock = $null
    }
}

function Remove-ProtectedInputSnapshots {
    $errors = [Collections.Generic.List[string]]::new()
    $remainingStreams = [Collections.Generic.List[object]]::new()
    foreach ($stream in @($script:protectedSnapshotStreams)) {
        try { $stream.Dispose() }
        catch {
            $errors.Add('snapshot stream disposal failed')
            $remainingStreams.Add($stream)
        }
    }
    $script:protectedSnapshotStreams = @($remainingStreams)
    if (
        $script:protectedSnapshotStreams.Count -eq 0 -and
        $script:protectedSnapshotDirectory -and
        [IO.Directory]::Exists($script:protectedSnapshotDirectory)
    ) {
        try { Microsoft.PowerShell.Management\Remove-Item -LiteralPath $script:protectedSnapshotDirectory -Recurse -Force }
        catch { $errors.Add('snapshot directory removal failed') }
    }
    if ($script:protectedSnapshotDirectory -and [IO.Directory]::Exists($script:protectedSnapshotDirectory)) {
        $errors.Add('snapshot directory remains present')
    }
    if ($errors.Count -ne 0) { throw 'Terraform input snapshot cleanup was not fully observed.' }
    $script:localSnapshotCleanupObserved = $true
}

function Write-ProtectedTextUtf8NoBom {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Text)
    $fullPath = [IO.Path]::GetFullPath($Path)
    $temporaryPath = Microsoft.PowerShell.Management\Join-Path ([IO.Path]::GetDirectoryName($fullPath)) ('.jcareer-write-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $writeStream = $null
    try {
        New-ProtectedEmptyFile -Path $temporaryPath -AclTemplatePath $fullPath
        $bytes = $utf8WithoutBom.GetBytes($Text)
        $writeStream = [IO.File]::Open($temporaryPath, [IO.FileMode]::Truncate, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $writeStream.Write($bytes, 0, $bytes.Length)
        $writeStream.Flush($true)
        $writeStream.Dispose()
        $writeStream = $null
        if ([IO.File]::Exists($fullPath)) { [IO.File]::Replace($temporaryPath, $fullPath, $null) }
        else { [IO.File]::Move($temporaryPath, $fullPath) }
    }
    finally {
        if ($null -ne $writeStream) { $writeStream.Dispose() }
        if ([IO.File]::Exists($temporaryPath)) { [IO.File]::Delete($temporaryPath) }
    }
}

function Write-NewProtectedTextUtf8NoBom {
    param([Parameter(Mandatory = $true)][string]$Path, [Parameter(Mandatory = $true)][string]$Text)
    $fullPath = [IO.Path]::GetFullPath($Path)
    if ([IO.File]::Exists($fullPath) -or [IO.Directory]::Exists($fullPath)) {
        throw 'An unresolved Terraform operation journal path already exists.'
    }
    $temporaryPath = Microsoft.PowerShell.Management\Join-Path ([IO.Path]::GetDirectoryName($fullPath)) ('.jcareer-journal-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $writeStream = $null
    try {
        New-ProtectedEmptyFile -Path $temporaryPath
        $bytes = $utf8WithoutBom.GetBytes($Text)
        $writeStream = [IO.File]::Open($temporaryPath, [IO.FileMode]::Truncate, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $writeStream.Write($bytes, 0, $bytes.Length)
        $writeStream.Flush($true)
        $writeStream.Dispose()
        $writeStream = $null
        [IO.File]::Move($temporaryPath, $fullPath)
    }
    finally {
        if ($null -ne $writeStream) { $writeStream.Dispose() }
        if ([IO.File]::Exists($temporaryPath)) { [IO.File]::Delete($temporaryPath) }
    }
}

function Start-OperationJournal {
    param(
        [Parameter(Mandatory = $true)][string]$PlanSha256,
        [Parameter(Mandatory = $true)][string]$ApprovalSha256,
        [Parameter(Mandatory = $true)][string]$ProviderAccountSha256
    )
    $script:operationJournalDocument = [ordered]@{
        schema_version = 'jcareer-terraform-apply-operation-journal-v2'
        scope = $selected.Scope
        operation_ref = 'operation:' + [Guid]::NewGuid().ToString('N')
        operation_state = 'IN_PROGRESS'
        outcome_state = 'OUTCOME_UNKNOWN'
        journal_cleanup_state = 'PENDING_RECEIPT'
        started_at = [DateTimeOffset]::UtcNow.ToString('o')
        saved_plan_sha256 = $PlanSha256
        backend_config_sha256 = $backendConfigHash
        logical_backend_sha256 = $canonicalBackendHash
        provider_account_sha256 = $ProviderAccountSha256
        approval_sha256 = $ApprovalSha256
        one_shot_plan_consumed = $true
        one_shot_backend_binding_consumed = $true
        one_shot_provider_account_binding_consumed = $true
        resource_identifiers_included = $false
    }
    Write-NewProtectedTextUtf8NoBom -Path $operationJournalFile -Text ($script:operationJournalDocument | Microsoft.PowerShell.Utility\ConvertTo-Json)
    $script:operationJournalStarted = $true
}

function Complete-OperationJournal {
    param(
        [Parameter(Mandatory = $true)][string]$ReceiptResult,
        [Parameter(Mandatory = $true)][string]$ReceiptSha256,
        [Parameter(Mandatory = $true)][string]$ReceiptText,
        [Parameter(Mandatory = $true)][bool]$LocalSnapshotCleanupObserved
    )
    if (-not $script:operationJournalStarted -or $null -eq $script:operationJournalDocument) {
        throw 'The Terraform operation journal was not started.'
    }
    $operationRef = [string]$script:operationJournalDocument['operation_ref']
    if ($operationRef -notmatch '^operation:[0-9a-f]{32}$') {
        throw 'The Terraform operation journal reference is invalid.'
    }
    $expectedReceiptHash = Get-ByteArraySha256 -Bytes $utf8WithoutBom.GetBytes($ReceiptText)
    if ($expectedReceiptHash -ne $ReceiptSha256) {
        throw 'The finalized Terraform receipt does not match its expected content.'
    }
    $script:operationJournalDocument['operation_state'] = 'COMPLETED'
    $script:operationJournalDocument['outcome_state'] = 'RECEIPT_FINALIZED'
    $script:operationJournalDocument['receipt_result'] = $ReceiptResult
    $script:operationJournalDocument['receipt_sha256'] = $ReceiptSha256
    $script:operationJournalDocument['completed_at'] = [DateTimeOffset]::UtcNow.ToString('o')

    if (-not $LocalSnapshotCleanupObserved) {
        $script:operationJournalDocument['journal_cleanup_state'] = 'CLEANUP_DISPOSITION_REQUIRED'
        Write-ProtectedTextUtf8NoBom -Path $operationJournalFile -Text ($script:operationJournalDocument | Microsoft.PowerShell.Utility\ConvertTo-Json)
        return
    }

    $operationId = $operationRef.Substring('operation:'.Length)
    $receiptArchiveName = 'jcareer-apply-receipt-' + $operationId + '.json'
    $journalArchiveName = 'jcareer-apply-operation-' + $operationId + '.completed.json'
    $receiptArchiveFile = Microsoft.PowerShell.Management\Join-Path $script:sharedLedgerDirectory $receiptArchiveName
    $journalArchiveFile = Microsoft.PowerShell.Management\Join-Path $script:sharedLedgerDirectory $journalArchiveName
    Write-NewProtectedTextUtf8NoBom -Path $receiptArchiveFile -Text $ReceiptText
    $receiptArchiveHash = (Microsoft.PowerShell.Utility\Get-FileHash -Algorithm SHA256 -LiteralPath $receiptArchiveFile).Hash.ToLowerInvariant()
    if ($receiptArchiveHash -ne $ReceiptSha256) {
        throw 'The archived Terraform receipt hash does not match the finalized receipt.'
    }

    $script:operationJournalDocument['journal_cleanup_state'] = 'ARCHIVED_READY_FOR_REMOVAL'
    $script:operationJournalDocument['receipt_archive_name'] = $receiptArchiveName
    $script:operationJournalDocument['receipt_archive_sha256'] = $receiptArchiveHash
    $script:operationJournalDocument['completed_journal_archive_name'] = $journalArchiveName
    $completedJournalText = $script:operationJournalDocument | Microsoft.PowerShell.Utility\ConvertTo-Json
    $expectedJournalHash = Get-ByteArraySha256 -Bytes $utf8WithoutBom.GetBytes($completedJournalText)
    Write-ProtectedTextUtf8NoBom -Path $operationJournalFile -Text $completedJournalText
    Write-NewProtectedTextUtf8NoBom -Path $journalArchiveFile -Text $completedJournalText
    $activeJournalHash = (Microsoft.PowerShell.Utility\Get-FileHash -Algorithm SHA256 -LiteralPath $operationJournalFile).Hash.ToLowerInvariant()
    $journalArchiveHash = (Microsoft.PowerShell.Utility\Get-FileHash -Algorithm SHA256 -LiteralPath $journalArchiveFile).Hash.ToLowerInvariant()
    if ($activeJournalHash -ne $expectedJournalHash -or $journalArchiveHash -ne $expectedJournalHash) {
        throw 'The completed Terraform journal archive does not match the active journal.'
    }
    [IO.File]::Delete($operationJournalFile)
    if ([IO.File]::Exists($operationJournalFile)) { throw 'The completed Terraform operation journal remains present.' }
    $script:operationJournalStarted = $false
    $script:operationJournalDocument = $null
}

function Protect-Diagnostic {
    param([AllowEmptyString()][string]$Text)
    $protected = $Text -replace '(?<!\d)\d{12}(?!\d)', '[REDACTED_ACCOUNT]'
    $protected = $protected -replace 'arn:aws[^\s"'']+', '[REDACTED_ARN]'
    $protected = $protected -replace '(?:AKIA|ASIA)[A-Z0-9]{16}', '[REDACTED_ACCESS_KEY]'
    $protected = $protected -replace '(?i)(password|secret|token|api[_-]?key)(\s*[=:]\s*)(?:"[^"]*"|''[^'']*''|[^\s,]+)', '$1$2[REDACTED]'
    $protected = $protected -replace '(?i)(["''])(bucket|key|dynamodb_table|profile|role_arn|workspace_key_prefix|owner|session(?:_?id)?|user(?:_?name)?)\1(\s*[=:]\s*)(?:"(?:\\.|[^"\\])*"|''[^'']*''|[^\s,}\]]+)', '$1$2$1$3[REDACTED_VALUE]'
    $protected = $protected -replace '(?i)\b(bucket|key|dynamodb_table|profile|role_arn|workspace_key_prefix)(\s*[=:]\s*)(?:"[^"]*"|''[^'']*''|[^\s,]+)', '$1$2[REDACTED_VALUE]'
    $protected = $protected -replace '(?i)\b(S3 bucket|object key|DynamoDB table)\s+(?:"[^"]*"|''[^'']*'')', '$1 [REDACTED_VALUE]'
    $protected = $protected -replace '(?i)s3://[^\s"'']+', '[REDACTED_S3_URI]'
    $protected = $protected -replace '(?<![0-9])(?:25[0-5]|2[0-4][0-9]|[01]?[0-9]?[0-9])(?:\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9]?[0-9])){3}(?![0-9])', '[REDACTED_IPV4]'
    $protected = $protected -replace '(?i)(?<![0-9a-f:])(?:[0-9a-f]{1,4}:){2,7}[0-9a-f]{0,4}(?![0-9a-f:])', '[REDACTED_IPV6]'
    $protected = $protected -replace '(?i)\b(owner|session(?:_?id)?|user(?:_?name)?)(\s*[=:]\s*)(?:"[^"]*"|''[^'']*''|[^\s,]+)', '$1$2[REDACTED_VALUE]'
    return $protected
}

function Invoke-CheckedOutput {
    param([scriptblock]$Command, [string]$Failure)
    $stderrPath = Microsoft.PowerShell.Management\Join-Path $workDir ('.jcareer-cli-stderr-' + [Guid]::NewGuid().ToString('N') + '.txt')
    try {
        New-ProtectedEmptyFile -Path $stderrPath
        $previousErrorActionPreference = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            $output = @(& $Command 2> $stderrPath)
            $exitCode = $LASTEXITCODE
        }
        finally { $ErrorActionPreference = $previousErrorActionPreference }
        $stderr = if ([IO.File]::Exists($stderrPath)) {
            [IO.File]::ReadAllText($stderrPath, $utf8WithoutBom)
        }
        else { '' }
        if ($exitCode -ne 0) {
            $safe = Protect-Diagnostic ((@($output) + @($stderr)) -join "`n")
            throw "$Failure`n$safe"
        }
        return $output
    }
    finally {
        if ([IO.File]::Exists($stderrPath)) { [IO.File]::Delete($stderrPath) }
    }
}

function Invoke-CheckedCommand {
    param([scriptblock]$Command, [string]$Failure)
    @(Invoke-CheckedOutput -Command $Command -Failure $Failure) | Microsoft.PowerShell.Core\Out-Null
}

function Get-ProviderAccountSha256 {
    $accountOutput = $null
    $account = $null
    try {
        $accountOutput = @(
            Invoke-CheckedOutput -Failure 'AWS provider account identity lookup failed.' -Command {
                & $script:awsExecutable sts get-caller-identity --query Account --output text --no-cli-pager
            }
        )
        $account = ($accountOutput -join '').Trim()
        if ($account -notmatch '^\d{12}$') {
            throw 'AWS provider account identity response was invalid.'
        }
        return Get-ByteArraySha256 -Bytes $utf8WithoutBom.GetBytes($account)
    }
    finally {
        $account = $null
        $accountOutput = $null
    }
}

$terraformCommand = Microsoft.PowerShell.Core\Get-Command 'terraform.exe' -CommandType Application -ErrorAction Stop | Microsoft.PowerShell.Utility\Select-Object -First 1
$pythonCommand = Microsoft.PowerShell.Core\Get-Command 'python.exe' -CommandType Application -ErrorAction Stop | Microsoft.PowerShell.Utility\Select-Object -First 1
$awsCommand = Microsoft.PowerShell.Core\Get-Command 'aws.exe' -CommandType Application -ErrorAction Stop | Microsoft.PowerShell.Utility\Select-Object -First 1
$script:terraformExecutable = [IO.Path]::GetFullPath([string]$terraformCommand.Source)
$script:pythonExecutable = [IO.Path]::GetFullPath([string]$pythonCommand.Source)
$script:awsExecutable = [IO.Path]::GetFullPath([string]$awsCommand.Source)
foreach ($executable in @($script:terraformExecutable, $script:pythonExecutable, $script:awsExecutable)) {
    if (-not [IO.File]::Exists($executable)) { throw 'One required application path is invalid.' }
}

Microsoft.PowerShell.Management\Push-Location $repoRoot
try {
    $script:protectedSnapshotDirectory = Microsoft.PowerShell.Management\Join-Path $workDir ('.jcareer-operation-' + [Guid]::NewGuid().ToString('N'))
    New-ProtectedDirectory -Path $script:protectedSnapshotDirectory
    $planJson = Microsoft.PowerShell.Management\Join-Path $script:protectedSnapshotDirectory 'plan.json'
    $backendSource = (Microsoft.PowerShell.Management\Resolve-Path $BackendConfig).Path
    $backendCheckerSource = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot 'scripts/check_terraform_backend_config.py')).Path
    $rootCheckerSource = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot $selected.Checker)).Path
    $deploymentCheckerSource = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot 'scripts/check_deployment_approval.py')).Path
    $resolvedBackendConfig = Copy-ProtectedStableFile -Source $backendSource -DestinationName 'backend.hcl'
    $backendChecker = Copy-ProtectedStableFile -Source $backendCheckerSource -DestinationName 'check-backend.py'
    $rootChecker = Copy-ProtectedStableFile -Source $rootCheckerSource -DestinationName 'check-root.py'
    $deploymentChecker = Copy-ProtectedStableFile -Source $deploymentCheckerSource -DestinationName 'check-approval.py'
    $backendSource = $null
    $backendCheckerSource = $null
    $rootCheckerSource = $null
    $deploymentCheckerSource = $null
    $canonicalBackendOutput = @(
        Invoke-CheckedOutput -Failure 'Terraform logical backend identity could not be derived.' -Command {
            & $script:pythonExecutable -E -s -S -B $backendChecker --config $resolvedBackendConfig --terraform-root $Root --print-canonical-sha256
        }
    )
    $canonicalBackendHash = ($canonicalBackendOutput -join '').Trim()
    if ($canonicalBackendHash -notmatch '^[0-9a-f]{64}$') {
        throw 'Terraform logical backend identity could not be derived.'
    }
    $operationJournalFile = Initialize-SharedOperationLedger -CanonicalBackendSha256 $canonicalBackendHash
    $createdNew = $false
    try {
        $script:backendLeaseMutex = [Threading.Mutex]::new(
            $false, ('Global\JCareerTerraformOperation-' + $canonicalBackendHash), [ref]$createdNew
        )
        try { $script:backendLeaseAcquired = $script:backendLeaseMutex.WaitOne(0) }
        catch [Threading.AbandonedMutexException] { $script:backendLeaseAcquired = $true }
        if (-not $script:backendLeaseAcquired) { throw 'The logical Terraform backend lease is already held.' }
    }
    catch {
        if ($null -ne $script:backendLeaseMutex) {
            $script:backendLeaseMutex.Dispose()
            $script:backendLeaseMutex = $null
        }
        throw 'Another local Terraform operator holds the shared logical-backend lease.'
    }
    foreach ($activeJournalFile in @(
        $operationJournalFile,
        $legacyApplyOperationJournalFile,
        $legacyTeardownOperationJournalFile
    )) {
        if ([IO.File]::Exists($activeJournalFile) -or [IO.Directory]::Exists($activeJournalFile)) {
            throw 'An unresolved Terraform apply or teardown operation journal exists. Reconcile the remote state and receipt before human disposition of the journal.'
        }
    }
    $planBinding = ''
    $providerAccountSha256 = ''
    if ($Apply) {
        if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $savedPlanFile -PathType Leaf)) {
            throw 'No saved plan exists. Run plan-only mode first.'
        }
        if (-not (Microsoft.PowerShell.Management\Test-Path -LiteralPath $planBindingFile -PathType Leaf)) {
            throw 'No saved backend/provider-account binding exists. Run plan-only mode first.'
        }
        $planBinding = Move-ProtectedOneShotFile -Source $planBindingFile -DestinationName 'plan-bindings.json'
        $planFile = Move-ProtectedOneShotFile -Source $savedPlanFile -DestinationName 'approved.tfplan'
    }
    $backendConfigHash = (Microsoft.PowerShell.Utility\Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedBackendConfig).Hash.ToLowerInvariant()
    $resolvedImageReceipt = ''
    $resolvedBuildObservation = ''
    $imageReceiptChecker = ''
    if ($Root -eq 'workplace-endpoints') {
        if (-not $ImageReceipt -or -not $BuildObservation) {
            throw 'workplace-endpoints requires a Windows image receipt and its bound build observation.'
        }
        $imageReceiptSource = (Microsoft.PowerShell.Management\Resolve-Path $ImageReceipt).Path
        $buildObservationSource = (Microsoft.PowerShell.Management\Resolve-Path $BuildObservation).Path
        $imageReceiptCheckerSource = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot 'scripts/check_windows_image_receipt.py')).Path
        $resolvedImageReceipt = Copy-ProtectedStableFile -Source $imageReceiptSource -DestinationName 'image-receipt.json'
        $resolvedBuildObservation = Copy-ProtectedStableFile -Source $buildObservationSource -DestinationName 'build-observation.json'
        $imageReceiptChecker = Copy-ProtectedStableFile -Source $imageReceiptCheckerSource -DestinationName 'check-image-receipt.py'
        $imageReceiptSource = $null
        $buildObservationSource = $null
        $imageReceiptCheckerSource = $null
    }
    $commonSnapshotCount = if ($Root -eq 'workplace-endpoints') { 7 } else { 4 }
    $preparedSnapshotCount = $commonSnapshotCount + $(if ($Apply) { 2 } else { 0 })
    if ($script:protectedSnapshotCount -ne $preparedSnapshotCount) {
        throw 'The common Terraform input/checker snapshot set is incomplete.'
    }

    if (-not $Apply) {
        $providerAccountSha256 = Get-ProviderAccountSha256
        $varFileSource = (Microsoft.PowerShell.Management\Resolve-Path $VarFile).Path
        $resolvedVarFile = Copy-ProtectedStableFile -Source $varFileSource -DestinationName 'terraform.tfvars'
        $varFileSource = $null
        if ($script:protectedSnapshotCount -ne ($commonSnapshotCount + 1)) {
            throw 'The plan-mode Terraform snapshot set is incomplete.'
        }
        $planFile = Microsoft.PowerShell.Management\Join-Path $script:protectedSnapshotDirectory 'candidate.tfplan'
        Invoke-CheckedCommand {
            & $script:terraformExecutable -chdir=$($selected.Path) init -reconfigure -lockfile=readonly -input=false "-backend-config=$resolvedBackendConfig"
        } 'Terraform remote-backend init failed.'
        Invoke-CheckedCommand { & $script:terraformExecutable -chdir=$($selected.Path) fmt -check } 'Terraform format check failed.'
        Invoke-CheckedCommand { & $script:terraformExecutable -chdir=$($selected.Path) validate } 'Terraform validate failed.'
        Invoke-CheckedCommand {
            & $script:terraformExecutable -chdir=$($selected.Path) plan -refresh=false -input=false -lock-timeout=60s "-var-file=$resolvedVarFile" "-out=$planFile"
        } 'Terraform saved-plan creation failed.'
        $show = @(
            Invoke-CheckedOutput -Failure 'Terraform saved-plan JSON conversion failed.' -Command {
                & $script:terraformExecutable -chdir=$($selected.Path) show -json $planFile
            }
        )
        $planJsonText = $show -join "`n"
        Write-ProtectedTextUtf8NoBom -Path $planJson -Text $planJsonText
        Open-VerifiedPlanJsonReadLock -Path $planJson -Text $planJsonText
        try {
            Invoke-CheckedCommand {
                & $script:pythonExecutable -E -s -S -B $rootChecker --root $repoRoot --plan $planJson
            } 'Saved plan failed the root-specific resource contract.'
            if ($Root -eq 'workplace-endpoints') {
                Invoke-CheckedCommand {
                    & $script:pythonExecutable -E -s -S -B $imageReceiptChecker --root $repoRoot --receipt $resolvedImageReceipt --build-observation $resolvedBuildObservation --plan-json $planJson --require-approved
                } 'Endpoint plan is not bound to a reviewed Windows image receipt.'
            }
        }
        finally { Close-VerifiedPlanJsonReadLock }
        $providerAccountAfterPlanSha256 = Get-ProviderAccountSha256
        if (-not [string]::Equals($providerAccountAfterPlanSha256, $providerAccountSha256, [StringComparison]::Ordinal)) {
            throw 'AWS provider account binding changed while creating the saved plan.'
        }
        $planHash = (Microsoft.PowerShell.Utility\Get-FileHash -Algorithm SHA256 -LiteralPath $planFile).Hash.ToLowerInvariant()
        if ([IO.File]::Exists($savedPlanFile)) { [IO.File]::Replace($planFile, $savedPlanFile, $null) }
        else { [IO.File]::Move($planFile, $savedPlanFile) }
        $planBindingDocument = [ordered]@{
            schema_version = 'jcareer-terraform-plan-bindings-v1'
            backend_config_sha256 = $backendConfigHash
            provider_account_sha256 = $providerAccountSha256
        }
        Write-ProtectedTextUtf8NoBom -Path $planBindingFile -Text ($planBindingDocument | Microsoft.PowerShell.Utility\ConvertTo-Json)
        Remove-ProtectedInputSnapshots
        Microsoft.PowerShell.Utility\Write-Output "PLAN_ONLY=PASS root=$Root"
        Microsoft.PowerShell.Utility\Write-Output "saved_plan_sha256=$planHash"
        Microsoft.PowerShell.Utility\Write-Output "provider_account_sha256=$providerAccountSha256"
        Microsoft.PowerShell.Utility\Write-Output 'No AWS changes were applied. A human must review this exact plan and create a separate approval record.'
        return
    }

    $approvalSource = (Microsoft.PowerShell.Management\Resolve-Path $ApprovalFile).Path
    $resolvedApproval = Copy-ProtectedStableFile -Source $approvalSource -DestinationName 'approval.json'
    $approvalSource = $null
    if ($script:protectedSnapshotCount -ne ($commonSnapshotCount + 3)) {
        throw 'The apply-mode Terraform snapshot set is incomplete.'
    }
    $planBindingDocument = Microsoft.PowerShell.Management\Get-Content -LiteralPath $planBinding -Raw -Encoding UTF8 | Microsoft.PowerShell.Utility\ConvertFrom-Json
    $planBindingKeys = @($planBindingDocument.PSObject.Properties.Name)
    $missingPlanBindingKeys = @(
        @('schema_version', 'backend_config_sha256', 'provider_account_sha256') |
            Microsoft.PowerShell.Core\Where-Object { $_ -notin $planBindingKeys }
    )
    if ($planBindingKeys.Count -ne 3 -or $missingPlanBindingKeys.Count -ne 0) {
        throw 'Saved plan binding keys differ from the exact schema.'
    }
    if ([string]$planBindingDocument.schema_version -cne 'jcareer-terraform-plan-bindings-v1') {
        throw 'Saved plan binding schema is invalid.'
    }
    $recordedBackendHash = [string]$planBindingDocument.backend_config_sha256
    if ($recordedBackendHash -ne $backendConfigHash) {
        throw 'Backend configuration differs from the one used for the saved plan.'
    }
    $recordedProviderAccountHash = [string]$planBindingDocument.provider_account_sha256
    if ($recordedProviderAccountHash -notmatch '^[0-9a-f]{64}$' -or $recordedProviderAccountHash -match '^([0-9a-f])\1{63}$') {
        throw 'Saved provider-account binding is empty, malformed, or placeholder-like.'
    }
    $providerAccountSha256 = Get-ProviderAccountSha256
    if (-not [string]::Equals($providerAccountSha256, $recordedProviderAccountHash, [StringComparison]::Ordinal)) {
        throw 'AWS provider account differs from the one used for the saved plan.'
    }
    Invoke-CheckedCommand {
        & $script:terraformExecutable -chdir=$($selected.Path) init -reconfigure -lockfile=readonly -input=false "-backend-config=$resolvedBackendConfig"
    } 'Terraform remote-backend init failed.'
    $show = @(
        Invoke-CheckedOutput -Failure 'Terraform saved-plan JSON conversion failed.' -Command {
            & $script:terraformExecutable -chdir=$($selected.Path) show -json $planFile
        }
    )
    $planJsonText = $show -join "`n"
    Write-ProtectedTextUtf8NoBom -Path $planJson -Text $planJsonText
    $plannedDeploymentStage = $null
    if ($Root -eq 'serverless-opendart') {
        $planDocument = ($show -join "`n") | Microsoft.PowerShell.Utility\ConvertFrom-Json
        $plannedDeploymentStage = $planDocument.planned_values.outputs.deployment_stage.value
        if ($plannedDeploymentStage -notin @('bootstrap', 'runtime')) {
            throw 'serverless-opendart apply accepts only a bootstrap or runtime saved plan.'
        }
    }
    $approvalArgs = @(
        $deploymentChecker,
        '--approval', $resolvedApproval,
        '--scope', $selected.Scope,
        '--plan', $planFile,
        '--plan-json', $planJson,
        '--backend-config-sha256', $backendConfigHash,
        '--provider-account-sha256', $providerAccountSha256,
        '--require-approved'
    )
    if ($Root -eq 'serverless-opendart' -and $plannedDeploymentStage -eq 'runtime') {
        if (-not $ArtifactSha256) { throw 'serverless-opendart runtime apply requires the exact Lambda image SHA-256.' }
        $approvalArgs += @('--artifact-sha256', $ArtifactSha256)
    }
    elseif ($Root -eq 'serverless-opendart' -and $ArtifactSha256) {
        throw 'serverless-opendart bootstrap apply must not carry a Lambda image SHA-256.'
    }
    Open-VerifiedPlanJsonReadLock -Path $planJson -Text $planJsonText
    try {
        Invoke-CheckedCommand {
            & $script:pythonExecutable -E -s -S -B $rootChecker --root $repoRoot --plan $planJson
        } 'Saved plan no longer matches the root-specific resource contract.'
        if ($Root -eq 'workplace-endpoints') {
            Invoke-CheckedCommand {
                & $script:pythonExecutable -E -s -S -B $imageReceiptChecker --root $repoRoot --receipt $resolvedImageReceipt --build-observation $resolvedBuildObservation --plan-json $planJson --require-approved
            } 'Endpoint plan is not bound to a reviewed Windows image receipt.'
        }
        Invoke-CheckedCommand { & $script:pythonExecutable -E -s -S -B @approvalArgs } 'Human approval record validation failed.'
    }
    finally { Close-VerifiedPlanJsonReadLock }

    $savedPlanHash = (Microsoft.PowerShell.Utility\Get-FileHash -Algorithm SHA256 -LiteralPath $planFile).Hash.ToLowerInvariant()
    $approvalHash = (Microsoft.PowerShell.Utility\Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedApproval).Hash.ToLowerInvariant()
    $buildObservationHash = if ($resolvedBuildObservation) {
        (Microsoft.PowerShell.Utility\Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedBuildObservation).Hash.ToLowerInvariant()
    }
    else { $null }
    $approval = Microsoft.PowerShell.Management\Get-Content -LiteralPath $resolvedApproval -Raw -Encoding UTF8 | Microsoft.PowerShell.Utility\ConvertFrom-Json
    $providerAccountBeforeApplySha256 = Get-ProviderAccountSha256
    if (-not [string]::Equals($providerAccountBeforeApplySha256, $providerAccountSha256, [StringComparison]::Ordinal)) {
        throw 'AWS provider account binding changed immediately before Terraform apply.'
    }
    Start-OperationJournal -PlanSha256 $savedPlanHash -ApprovalSha256 $approvalHash -ProviderAccountSha256 $providerAccountSha256
    Invoke-CheckedCommand {
        & $script:terraformExecutable -chdir=$($selected.Path) apply -input=false -lock-timeout=60s $planFile
    } 'Terraform apply failed.'
    $providerAccountAfterApplySha256 = Get-ProviderAccountSha256
    if (-not [string]::Equals($providerAccountAfterApplySha256, $providerAccountSha256, [StringComparison]::Ordinal)) {
        throw 'AWS provider account binding changed before apply completion could be recorded.'
    }

    $receipt = [ordered]@{
        schema_version = 'jcareer-redacted-terraform-apply-receipt-v1'
        scope = $selected.Scope
        approval_ref = $approval.approval_ref
        saved_plan_sha256 = $savedPlanHash
        backend_config_sha256 = $backendConfigHash
        artifact_sha256 = if ($ArtifactSha256) { $ArtifactSha256 } else { $null }
        build_observation_sha256 = $buildObservationHash
        completed_at = [DateTimeOffset]::UtcNow.ToString('o')
        result = $null
        resource_identifiers_included = $false
        runtime_smoke_completed = $false
        protected_input_snapshot_count = $script:protectedSnapshotCount
        local_snapshot_cleanup_observed = $false
    }
    $snapshotCleanupFailed = $false
    try {
        Remove-ProtectedInputSnapshots
        $receipt['local_snapshot_cleanup_observed'] = $true
    }
    catch { $snapshotCleanupFailed = $true }
    $receiptResult = if ($snapshotCleanupFailed) {
        'APPLY_COMMAND_COMPLETED_LOCAL_CLEANUP_UNOBSERVED'
    }
    else { 'APPLY_COMMAND_COMPLETED' }
    $receipt['result'] = $receiptResult
    $receiptText = $receipt | Microsoft.PowerShell.Utility\ConvertTo-Json
    Write-ProtectedTextUtf8NoBom -Path $receiptFile -Text $receiptText
    $receiptHash = (Microsoft.PowerShell.Utility\Get-FileHash -Algorithm SHA256 -LiteralPath $receiptFile).Hash.ToLowerInvariant()
    Complete-OperationJournal -ReceiptResult $receiptResult `
        -ReceiptSha256 $receiptHash `
        -ReceiptText $receiptText `
        -LocalSnapshotCleanupObserved (-not $snapshotCleanupFailed)
    if ($snapshotCleanupFailed) {
        throw 'Terraform apply completed, but protected local input cleanup was not observed; use the receipt and perform human disposition before retry.'
    }
    Microsoft.PowerShell.Utility\Write-Output "APPLY_COMMAND_COMPLETED root=$Root receipt=.terraform/last-apply-receipt.json"
    Microsoft.PowerShell.Utility\Write-Output 'Runtime, live provider calls, image build output, and endpoint usability still require separate observation receipts.'
}
finally {
    try { Close-VerifiedPlanJsonReadLock }
    catch { Microsoft.PowerShell.Utility\Write-Warning 'The protected plan JSON read lock was not cleanly released.' }
    if (Microsoft.PowerShell.Management\Test-Path -LiteralPath $planJson) {
        Microsoft.PowerShell.Management\Remove-Item -LiteralPath $planJson -Force
    }
    if (-not $script:localSnapshotCleanupObserved) {
        try { Remove-ProtectedInputSnapshots }
        catch { Microsoft.PowerShell.Utility\Write-Warning 'Protected Terraform input cleanup was not fully observed.' }
    }
    if ($script:backendLeaseAcquired -and $null -ne $script:backendLeaseMutex) {
        $script:backendLeaseMutex.ReleaseMutex()
        $script:backendLeaseAcquired = $false
    }
    if ($null -ne $script:backendLeaseMutex) {
        $script:backendLeaseMutex.Dispose()
        $script:backendLeaseMutex = $null
    }
    Microsoft.PowerShell.Management\Pop-Location
}
