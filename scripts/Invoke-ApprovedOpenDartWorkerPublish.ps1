[CmdletBinding(DefaultParameterSetName = 'Prepare')]
param(
    [Parameter(Mandatory)][ValidateSet('Prepare','Review','Publish')][string]$Mode,
    [Parameter(Mandatory)][ValidatePattern('^PUBLISH-[A-Z0-9_-]{8,64}$')][string]$OperationRef,
    [Parameter(Mandatory)][ValidatePattern('^(?:[0-9a-f]{40}|[0-9a-f]{64})$')][string]$SourceRevision,
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9][a-z0-9._-]{15,127}$')][string]$ImageTag,
    [Parameter(Mandatory)][string]$PreparationReceipt,
    [Parameter(Mandatory)][string]$ScanReport,
    [Parameter(Mandatory)][string]$ScanPolicyFile,
    [ValidatePattern('^(?:UNKNOWN|LOW|MEDIUM|HIGH|CRITICAL)(?:,(?:UNKNOWN|LOW|MEDIUM|HIGH|CRITICAL))*$')]
    [string]$SeveritySelection = 'UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL',
    [string]$ScannerExecutable = 'trivy.exe',
    [string]$JournalDirectory = (Join-Path $env:LOCALAPPDATA 'JCareerOpenDartWorkerPublisher-v1'),
    [Parameter(Mandatory,ParameterSetName='Prepare')][string]$PreparationAcknowledgement,
    [Parameter(Mandatory,ParameterSetName='Review')][string]$ReviewAcknowledgement,
    [Parameter(Mandatory,ParameterSetName='Review')][string]$ApprovalDraft,
    [Parameter(Mandatory,ParameterSetName='Publish')][string]$ApprovalFile,
    [Parameter(Mandatory,ParameterSetName='Review')]
    [Parameter(Mandatory,ParameterSetName='Publish')][string]$BackendConfig,
    [Parameter(Mandatory,ParameterSetName='Review')]
    [Parameter(Mandatory,ParameterSetName='Publish')][string]$BootstrapApplyReceipt,
    [Parameter(Mandatory,ParameterSetName='Publish')][string]$PrivateImageUriPath,
    [Parameter(Mandatory,ParameterSetName='Publish')][string]$PublishReceipt
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$script:TrustedRepositoryRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$script:JournalPath = ''
$script:ArtifactRoot = ''
$script:JournalOwned = $false
$script:CurrentStep = 'INITIALIZATION'

if ($Mode -cne $PSCmdlet.ParameterSetName) {
    throw 'Mode must match the exact Prepare, Review, or Publish parameter set.'
}

# Auditable workflow sentinels: docker build; trivy image;
# terraform output -raw ecr_repository_url; get-caller-identity; ecr batch-get-image; docker push;
# ecr describe-images.  Actual invocations below use argument arrays.

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-TextSha256([string]$Value) {
    $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
    $hasher = [Security.Cryptography.SHA256]::Create()
    try {
        $hash = $hasher.ComputeHash($bytes)
        return -join ($hash | ForEach-Object { $_.ToString('x2') })
    }
    finally {
        $hasher.Dispose()
    }
}

function Assert-NoReparsePathChain([string]$Path, [string]$Label) {
    $current = [IO.Path]::GetFullPath($Path)
    while (-not [string]::IsNullOrWhiteSpace($current)) {
        if ((Test-Path -LiteralPath $current) -and ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "$Label path chain contains a reparse point"
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $current) { break }
        $current = $parent
    }
}

function New-CurrentUserFileAcl {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [Security.AccessControl.FileSecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $identity, [Security.AccessControl.FileSystemRights]::FullControl,
        [Security.AccessControl.AccessControlType]::Allow
    ))
    return $acl
}

function Protect-CurrentUserDirectory([string]$Path) {
    Assert-NoReparsePathChain $Path 'private directory'
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $item = Get-Item -LiteralPath $Path -Force
    $acl = $item.GetAccessControl([Security.AccessControl.AccessControlSections]::Access)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($existingRule in @($acl.Access)) {
        $null = $acl.RemoveAccessRuleSpecific($existingRule)
    }
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $identity, [Security.AccessControl.FileSystemRights]::FullControl,
        ([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit),
        [Security.AccessControl.PropagationFlags]::None,
        [Security.AccessControl.AccessControlType]::Allow
    ))
    $item.SetAccessControl($acl)
}

function Resolve-ExistingFile([string]$Path, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw "$Label path is required" }
    Assert-NoReparsePathChain $Path $Label
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer -and -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        return $item.FullName
    }
    throw "$Label must be a non-reparse regular file"
}

function Resolve-EmptyDestination([string]$Path, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw "$Label path is required" }
    $full = [IO.Path]::GetFullPath($Path)
    if (Test-Path -LiteralPath $full) { throw "$Label already exists; overwrite is forbidden" }
    $parent = Split-Path -Parent $full
    if ([string]::IsNullOrWhiteSpace($parent) -or -not (Test-Path -LiteralPath $parent -PathType Container)) {
        throw "$Label parent directory must already exist"
    }
    $parentItem = Get-Item -LiteralPath $parent -Force
    Assert-NoReparsePathChain $parent $Label
    if ($parentItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "$Label parent cannot be a reparse point" }
    return $full
}

function Write-NewUtf8([string]$Path, [string]$Text) {
    $stream = [IO.FileStream]::new(
        $Path, [IO.FileMode]::CreateNew, [Security.AccessControl.FileSystemRights]::WriteData,
        [IO.FileShare]::None, 4096, [IO.FileOptions]::None,
        (New-CurrentUserFileAcl)
    )
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes($Text)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally { $stream.Dispose() }
}

function Copy-NewProtectedFile([string]$Source, [string]$Destination, [string]$Label) {
    $resolvedSource = Resolve-ExistingFile $Source $Label
    if (Test-Path -LiteralPath $Destination) { throw "$Label protected destination already exists" }
    $sourceStream = [IO.File]::Open(
        $resolvedSource, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read
    )
    $destinationStream = $null
    try {
        $destinationStream = [IO.FileStream]::new(
            $Destination, [IO.FileMode]::CreateNew,
            [Security.AccessControl.FileSystemRights]::WriteData,
            [IO.FileShare]::None, 65536, [IO.FileOptions]::SequentialScan,
            (New-CurrentUserFileAcl)
        )
        $sourceStream.CopyTo($destinationStream, 65536)
        $destinationStream.Flush($true)
    } finally {
        if ($null -ne $destinationStream) { $destinationStream.Dispose() }
        $sourceStream.Dispose()
    }
    if ((Get-FileSha256 $resolvedSource) -ne (Get-FileSha256 $Destination)) {
        throw "$Label changed while the protected snapshot was created"
    }
    return [IO.Path]::GetFullPath($Destination)
}

function Copy-ProtectedInput([string]$Source, [string]$Name, [string]$Label) {
    if ([string]::IsNullOrWhiteSpace($script:ArtifactRoot)) { throw 'protected artifact root is not initialized' }
    if ($Name -notmatch '^[a-z0-9][a-z0-9._-]{2,80}$') { throw 'protected input name is invalid' }
    return Copy-NewProtectedFile $Source (Join-Path $script:ArtifactRoot $Name) $Label
}

function Write-AtomicJournal([string]$Text) {
    $journalParent = Split-Path -Parent $script:JournalPath
    $temporary = Join-Path $journalParent (
        ([IO.Path]::GetFileName($script:JournalPath)) + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    )
    $backup = Join-Path $journalParent (
        ([IO.Path]::GetFileName($script:JournalPath)) + '.' + [Guid]::NewGuid().ToString('N') + '.bak'
    )
    Write-NewUtf8 $temporary $Text
    [IO.File]::Replace($temporary, $script:JournalPath, $backup)
    if (Test-Path -LiteralPath $backup) { [IO.File]::Delete($backup) }
}

function Resolve-Application([string]$Name, [string]$Label) {
    $command = Get-Command $Name -CommandType Application -ErrorAction Stop | Select-Object -First 1
    $resolved = Resolve-ExistingFile ([IO.Path]::GetFullPath([string]$command.Source)) $Label
    Assert-NoReparsePathChain $resolved $Label
    return $resolved
}

function Invoke-Captured([string]$Executable, [string[]]$Arguments, [string]$Label) {
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5 surfaces normal native stderr (for example Docker
        # progress) as RemoteException records when the caller uses Stop.
        $ErrorActionPreference = 'Continue'
        $value = (& $Executable @Arguments 2>&1 | Out-String).Trim()
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) { throw "$Label failed; raw command output was suppressed" }
    return $value
}

function Assert-Hex64([string]$Value, [string]$Label) {
    if ($Value -notmatch '^[0-9a-f]{64}$') { throw "$Label is not a lowercase SHA-256" }
}

function Start-Journal([string]$ModeName) {
    if (-not (Test-Path -LiteralPath $JournalDirectory)) {
        New-Item -ItemType Directory -Path $JournalDirectory | Out-Null
    }
    Assert-NoReparsePathChain $JournalDirectory 'journal directory'
    Protect-CurrentUserDirectory $JournalDirectory
    $journalRoot = (Get-Item -LiteralPath $JournalDirectory -Force).FullName
    if ((Get-Item -LiteralPath $journalRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'journal directory cannot be a reparse point'
    }
    $key = Get-TextSha256 "$OperationRef|$ModeName"
    $journalPath = Join-Path $journalRoot "$key.json"
    $artifactRoot = Join-Path $journalRoot $key
    if ((Test-Path -LiteralPath $journalPath) -or (Test-Path -LiteralPath $artifactRoot)) {
        throw 'operation reference and mode already have retained artifacts; human disposition is required'
    }
    New-Item -ItemType Directory -Path $artifactRoot | Out-Null
    Protect-CurrentUserDirectory $artifactRoot
    $initial = [ordered]@{
        schema_version = 'jcareer-opendart-worker-publisher-journal-v1'
        operation_ref_sha256 = (Get-TextSha256 $OperationRef)
        mode = $ModeName
        state = 'STARTED_FAIL_OR_INTERRUPT_REQUIRES_HUMAN_DISPOSITION'
        local_artifact_cleanup_claimed = $false
        updated_at = [DateTimeOffset]::UtcNow.ToString('o')
    }
    Write-NewUtf8 $journalPath ($initial | ConvertTo-Json -Depth 4)
    $script:JournalPath = $journalPath
    $script:ArtifactRoot = $artifactRoot
    $script:JournalOwned = $true
}

function Set-Journal([string]$State) {
    $entry = [ordered]@{
        schema_version = 'jcareer-opendart-worker-publisher-journal-v1'
        operation_ref_sha256 = (Get-TextSha256 $OperationRef)
        mode = $Mode
        state = $State
        local_artifact_cleanup_claimed = $false
        updated_at = [DateTimeOffset]::UtcNow.ToString('o')
    }
    Write-AtomicJournal ($entry | ConvertTo-Json -Depth 4)
}

function Get-SourceFiles([string]$Root) {
    $runtime = Join-Path $Root 'src/runtime'
    $fixed = @(
        (Join-Path $runtime 'opendart_worker/Dockerfile'),
        (Join-Path $runtime 'opendart_worker/requirements.txt'),
        (Join-Path $runtime 'opendart_worker/handler.py')
    )
    $app = Get-ChildItem -LiteralPath (Join-Path $runtime 'api/app') -Recurse -File |
        Where-Object { $_.Extension -eq '.py' -and -not ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) } |
        ForEach-Object { $_.FullName }
    $all = @($fixed + $app)
    foreach ($path in $all) { Resolve-ExistingFile $path 'source file' | Out-Null }
    return @($all | Sort-Object -Unique)
}

function New-ProtectedSourceSnapshot([string]$Root) {
    Assert-NoReparsePathChain $Root 'repository root'
    $runtime = [IO.Path]::GetFullPath((Join-Path $Root 'src/runtime'))
    $runtimePrefix = $runtime.TrimEnd('\') + '\'
    $snapshot = Join-Path $script:ArtifactRoot 'source'
    New-Item -ItemType Directory -Path $snapshot | Out-Null
    $manifest = [Text.StringBuilder]::new()
    $entries = @()
    foreach ($source in (Get-SourceFiles $Root)) {
        $sourceFull = [IO.Path]::GetFullPath($source)
        if (-not $sourceFull.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'source escaped runtime root'
        }
        $relative = $sourceFull.Substring($runtimePrefix.Length).Replace('\','/')
        if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative)) {
            throw 'source escaped runtime root'
        }
        $destination = Join-Path $snapshot $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        $null = Copy-NewProtectedFile $source $destination 'source file'
        $bytes = [IO.File]::ReadAllBytes($destination)
        $fileSha = Get-FileSha256 $destination
        [void]$manifest.Append("$relative`t$($bytes.Length)`t$fileSha`n")
        $entries += [pscustomobject]@{ Relative = $relative; Bytes = $bytes }
    }
    $archive = Join-Path $script:ArtifactRoot 'jcareer-opendart-worker-source-v1.jca'
    $stream = [IO.FileStream]::new(
        $archive, [IO.FileMode]::CreateNew,
        [Security.AccessControl.FileSystemRights]::WriteData,
        [IO.FileShare]::None, 65536, [IO.FileOptions]::SequentialScan,
        (New-CurrentUserFileAcl)
    )
    $writer = $null
    try {
        $writer = [IO.BinaryWriter]::new($stream, [Text.UTF8Encoding]::new($false), $true)
        $writer.Write([Text.Encoding]::ASCII.GetBytes("jcareer-opendart-worker-source-v1`n"))
        foreach ($entry in $entries) {
            $pathBytes = [Text.Encoding]::UTF8.GetBytes($entry.Relative)
            $writer.Write([int]$pathBytes.Length); $writer.Write($pathBytes)
            $writer.Write([long]$entry.Bytes.Length); $writer.Write($entry.Bytes)
        }
        $writer.Flush(); $stream.Flush($true)
    } finally { if ($null -ne $writer) { $writer.Dispose() }; $stream.Dispose() }
    return [pscustomobject]@{
        Root = $snapshot
        Count = $entries.Count
        TreeSha = (Get-TextSha256 $manifest.ToString())
        ArchiveSha = (Get-FileSha256 $archive)
        DockerfileSha = (Get-FileSha256 (Join-Path $snapshot 'opendart_worker/Dockerfile'))
        RequirementsSha = (Get-FileSha256 (Join-Path $snapshot 'opendart_worker/requirements.txt'))
    }
}

function Assert-JsonObject([string]$Path, [string]$Label) {
    try { $value = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { throw "$Label is not valid JSON" }
    if ($null -eq $value) { throw "$Label must be a JSON object" }
    return $value
}

function Assert-ExactObjectKeys([object]$Value, [string[]]$Expected, [string]$Label) {
    $actual = @($Value.PSObject.Properties.Name | Sort-Object)
    $wanted = @($Expected | Sort-Object)
    if (($actual -join "`n") -cne ($wanted -join "`n")) { throw "$Label exact-key mismatch" }
}

function Assert-NoRawIdentifierObject([object]$Value, [string]$Label) {
    $material = $Value | ConvertTo-Json -Depth 8 -Compress
    $forbidden = '(?:arn:aws:|AKIA[0-9A-Z]{16}|\b\d{12}\b|\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})'
    if ($material -match $forbidden) { throw "$Label contains a forbidden raw identifier" }
}

function Assert-BootstrapReceiptInline([object]$Receipt, [string]$BackendSha) {
    $keys = @(
        'schema_version','scope','approval_ref','saved_plan_sha256','backend_config_sha256',
        'artifact_sha256','build_observation_sha256','completed_at','resource_identifiers_included',
        'runtime_smoke_completed','protected_input_snapshot_count','local_snapshot_cleanup_observed','result'
    )
    Assert-ExactObjectKeys $Receipt $keys 'bootstrap receipt'
    if (
        $Receipt.schema_version -cne 'jcareer-redacted-terraform-apply-receipt-v1' -or
        $Receipt.scope -cne 'serverless-opendart' -or
        $Receipt.result -cne 'APPLY_COMMAND_COMPLETED' -or
        $Receipt.backend_config_sha256 -cne $BackendSha -or
        $null -ne $Receipt.artifact_sha256 -or $null -ne $Receipt.build_observation_sha256 -or
        $Receipt.resource_identifiers_included -ne $false -or
        $Receipt.runtime_smoke_completed -ne $false -or
        $Receipt.protected_input_snapshot_count -ne 7 -or
        $Receipt.local_snapshot_cleanup_observed -ne $true
    ) { throw 'bootstrap receipt failed the independent PowerShell boundary' }
    Assert-Hex64 ([string]$Receipt.saved_plan_sha256) 'bootstrap saved plan hash'
    try { $null = [DateTimeOffset]::Parse([string]$Receipt.completed_at) }
    catch { throw 'bootstrap receipt completed_at is invalid' }
    Assert-NoRawIdentifierObject $Receipt 'bootstrap receipt'
}

function Assert-PreparationInline([object]$Receipt) {
    $keys = @(
        'schema_version','scope','operation_ref','prepared_at','source_revision','source_tree_sha256',
        'source_archive_sha256','dockerfile_sha256','requirements_sha256','build_context_file_count',
        'local_image_id_sha256','scanner_executable_sha256','scanner_version_sha256',
        'scan_severity_selection','scan_policy_sha256','scan_report_sha256','scan_completed',
        'scan_decision_recorded','publish_attempted','raw_identifiers_included','result'
    )
    Assert-ExactObjectKeys $Receipt $keys 'preparation receipt'
    if (
        $Receipt.schema_version -cne 'jcareer-opendart-worker-preparation-v1' -or
        $Receipt.scope -cne 'serverless-opendart-worker-publish' -or
        $Receipt.operation_ref -cnotmatch '^PUBLISH-[A-Z0-9_-]{8,64}$' -or
        $Receipt.source_revision -cnotmatch '^(?:[0-9a-f]{40}|[0-9a-f]{64})$' -or
        $Receipt.scan_severity_selection -cnotmatch '^(?:UNKNOWN|LOW|MEDIUM|HIGH|CRITICAL)(?:,(?:UNKNOWN|LOW|MEDIUM|HIGH|CRITICAL))*$' -or
        [int64]$Receipt.build_context_file_count -lt 4 -or
        $Receipt.scan_completed -ne $true -or $Receipt.scan_decision_recorded -ne $false -or
        $Receipt.publish_attempted -ne $false -or $Receipt.raw_identifiers_included -ne $false -or
        $Receipt.result -cne 'AWAITING_HUMAN_SCAN_DISPOSITION'
    ) { throw 'preparation receipt failed the independent PowerShell boundary' }
    foreach ($key in @(
        'source_tree_sha256','source_archive_sha256','dockerfile_sha256','requirements_sha256',
        'local_image_id_sha256','scanner_executable_sha256','scanner_version_sha256',
        'scan_policy_sha256','scan_report_sha256'
    )) { Assert-Hex64 ([string]$Receipt.$key) $key }
    try { $null = [DateTimeOffset]::Parse([string]$Receipt.prepared_at) }
    catch { throw 'preparation receipt prepared_at is invalid' }
    Assert-NoRawIdentifierObject $Receipt 'preparation receipt'
}

function Assert-PublishApprovalInline([object]$Approval, [Collections.IDictionary]$Bindings) {
    $keys = @(
        'schema_version','scope','decision','approval_ref','reviewer_ref','approved_at','expires_at',
        'operation_ref','expected_region','backend_config_sha256','backend_file_sha256',
        'bootstrap_apply_receipt_sha256','provider_account_sha256','preparation_receipt_sha256',
        'source_revision','source_tree_sha256','source_archive_sha256','dockerfile_sha256',
        'requirements_sha256','local_image_id_sha256','image_tag','publisher_script_sha256',
        'approval_checker_sha256','backend_checker_sha256','python_executable_sha256',
        'aws_executable_sha256','docker_executable_sha256','terraform_executable_sha256',
        'scanner_executable_sha256','scanner_version_sha256','scan_severity_selection',
        'scan_policy_ref','scan_policy_sha256','scan_report_sha256','ecr_repository_url_sha256',
        'ecr_repository_configuration_sha256','scan_human_disposition','synthetic_data_only','notes'
    )
    Assert-ExactObjectKeys $Approval $keys 'publish approval'
    if (
        $Approval.schema_version -cne 'jcareer-opendart-worker-publish-approval-v1' -or
        $Approval.scope -cne 'serverless-opendart-worker-publish' -or
        $Approval.decision -cne 'APPROVED_FOR_SINGLE_PUBLISH' -or
        $Approval.approval_ref -cnotmatch '^APPROVAL-[A-Z0-9_-]{8,64}$' -or
        $Approval.reviewer_ref -cnotmatch '^reviewer:[a-z0-9_-]{6,64}$' -or
        $Approval.operation_ref -cnotmatch '^PUBLISH-[A-Z0-9_-]{8,64}$' -or
        $Approval.expected_region -cne 'ap-northeast-2' -or
        $Approval.approved_at -cnotmatch '(?:Z|[+-][0-9]{2}:[0-9]{2})$' -or
        $Approval.expires_at -cnotmatch '(?:Z|[+-][0-9]{2}:[0-9]{2})$' -or
        $Approval.source_revision -cnotmatch '^(?:[0-9a-f]{40}|[0-9a-f]{64})$' -or
        $Approval.image_tag -cnotmatch '^[a-z0-9][a-z0-9._-]{15,127}$' -or
        $Approval.scan_severity_selection -cnotmatch '^(?:UNKNOWN|LOW|MEDIUM|HIGH|CRITICAL)(?:,(?:UNKNOWN|LOW|MEDIUM|HIGH|CRITICAL))*$' -or
        $Approval.scan_policy_ref -cnotmatch '^policy:[a-z0-9_-]{6,64}$' -or
        $Approval.scan_human_disposition -cne 'HUMAN_APPROVED_FOR_SINGLE_SYNTHETIC_PUBLISH' -or
        $Approval.synthetic_data_only -ne $true -or $Approval.notes -isnot [string]
    ) { throw 'publish approval failed the independent PowerShell boundary' }
    foreach ($property in $Approval.PSObject.Properties) {
        if ($property.Name.EndsWith('_sha256')) { Assert-Hex64 ([string]$property.Value) $property.Name }
    }
    try {
        $approvedAt = [DateTimeOffset]::Parse([string]$Approval.approved_at)
        $expiresAt = [DateTimeOffset]::Parse([string]$Approval.expires_at)
    } catch { throw 'publish approval timestamp is invalid' }
    $now = [DateTimeOffset]::UtcNow
    if ($expiresAt -le $approvedAt -or ($expiresAt - $approvedAt).TotalHours -gt 24 -or $now -lt $approvedAt -or $now -gt $expiresAt) {
        throw 'publish approval is not within its positive 24-hour validity window'
    }
    foreach ($binding in $Bindings.GetEnumerator()) {
        if ([string]$Approval.($binding.Key) -cne [string]$binding.Value) {
            throw "publish approval binding mismatch: $($binding.Key)"
        }
    }
    Assert-NoRawIdentifierObject $Approval 'publish approval'
}

function Invoke-Prepare {
    if ($PreparationAcknowledgement -ne 'JCAREER_SYNTHETIC_OPENDART_SCAN_PREPARATION') {
        throw 'exact synthetic scan preparation acknowledgement is required'
    }
    $script:CurrentStep = 'START_JOURNAL'
    Start-Journal 'Prepare'
    $script:CurrentStep = 'RESOLVE_OUTPUTS'
    $receiptPath = Resolve-EmptyDestination $PreparationReceipt 'preparation receipt'
    $reportPath = Resolve-EmptyDestination $ScanReport 'scan report'
    $script:CurrentStep = 'PROTECT_INPUTS'
    $policyPath = Copy-ProtectedInput $ScanPolicyFile 'scan-policy.input' 'scan policy'
    $docker = Resolve-Application 'docker.exe' 'Docker executable'
    $scanner = Resolve-Application $ScannerExecutable 'Trivy executable'
    if ([IO.Path]::GetFileName($scanner) -notmatch '^trivy(?:\.exe)?$') { throw 'only the fixed Trivy scanner interface is supported' }
    $script:CurrentStep = 'SNAPSHOT_SOURCE'
    $snapshot = New-ProtectedSourceSnapshot $script:TrustedRepositoryRoot
    $localRef = "jcareer-opendart-worker-local:$ImageTag"
    $script:CurrentStep = 'CHECK_LOCAL_TAG'
    $existingLocal = Invoke-Captured $docker @('image','ls','--filter',"reference=$localRef",'--format={{.ID}}') 'local unique tag check'
    if (-not [string]::IsNullOrWhiteSpace($existingLocal)) { throw 'unique local image tag is already present' }
    $script:CurrentStep = 'BUILD_IMAGE'
    $null = Invoke-Captured $docker @('build','--platform','linux/amd64','--pull','--no-cache','-f',(Join-Path $snapshot.Root 'opendart_worker/Dockerfile'),'-t',$localRef,$snapshot.Root) 'docker build'
    $script:CurrentStep = 'QUERY_SCANNER_VERSION'
    $version = Invoke-Captured $scanner @('--version') 'scanner version query'
    $privateReportPath = Join-Path $script:ArtifactRoot 'scan-report.json'
    $script:CurrentStep = 'INITIALIZE_SCAN_REPORT'
    Write-NewUtf8 $privateReportPath ''
    $script:CurrentStep = 'SCAN_IMAGE'
    $null = Invoke-Captured $scanner @('image','--scanners','vuln','--format','json','--output',$privateReportPath,'--severity',$SeveritySelection,'--exit-code','0','--no-progress',$localRef) 'trivy image vulnerability scan'
    $script:CurrentStep = 'VALIDATE_SCAN_REPORT'
    $null = Assert-JsonObject $privateReportPath 'scan report'
    $null = Copy-NewProtectedFile $privateReportPath $reportPath 'scan report'
    $script:CurrentStep = 'INSPECT_IMAGE'
    $imageId = Invoke-Captured $docker @('image','inspect','--format={{.Id}}',$localRef) 'local image inspection'
    if ($imageId -notmatch '^sha256:[0-9a-f]{64}$') { throw 'local image inspection returned an unexpected shape' }
    $imagePlatform = Invoke-Captured $docker @('image','inspect','--format={{.Os}}/{{.Architecture}}',$localRef) 'local image platform inspection'
    if ($imagePlatform -ne 'linux/amd64') { throw 'worker image platform must be linux/amd64' }
    $receipt = [ordered]@{
        schema_version = 'jcareer-opendart-worker-preparation-v1'; scope = 'serverless-opendart-worker-publish'
        operation_ref = $OperationRef; prepared_at = [DateTimeOffset]::UtcNow.ToString('o'); source_revision = $SourceRevision
        source_tree_sha256 = $snapshot.TreeSha; source_archive_sha256 = $snapshot.ArchiveSha
        dockerfile_sha256 = $snapshot.DockerfileSha; requirements_sha256 = $snapshot.RequirementsSha
        build_context_file_count = $snapshot.Count; local_image_id_sha256 = (Get-TextSha256 $imageId)
        scanner_executable_sha256 = (Get-FileSha256 $scanner); scanner_version_sha256 = (Get-TextSha256 $version)
        scan_severity_selection = $SeveritySelection; scan_policy_sha256 = (Get-FileSha256 $policyPath)
        scan_report_sha256 = (Get-FileSha256 $reportPath); scan_completed = $true; scan_decision_recorded = $false
        publish_attempted = $false; raw_identifiers_included = $false; result = 'AWAITING_HUMAN_SCAN_DISPOSITION'
    }
    $script:CurrentStep = 'WRITE_RECEIPT'
    Write-NewUtf8 $receiptPath ($receipt | ConvertTo-Json -Depth 5)
    $script:CurrentStep = 'FINALIZE_JOURNAL'
    Set-Journal 'AWAITING_HUMAN_SCAN_DISPOSITION'
    Write-Output 'OPENDART_WORKER_PREPARATION=AWAITING_HUMAN_SCAN_DISPOSITION'
    Write-Output 'LOCAL_ARTIFACTS_RETAINED=HUMAN_DISPOSITION_REQUIRED'
}

function Invoke-ReviewOrPublish {
    $reviewOnly = $Mode -eq 'Review'
    if ($reviewOnly -and $ReviewAcknowledgement -ne 'JCAREER_SYNTHETIC_OPENDART_PUBLISH_BINDINGS_REVIEW') {
        throw 'exact synthetic publish-bindings review acknowledgement is required'
    }
    Start-Journal $Mode
    $draftPath = if ($reviewOnly) { Resolve-EmptyDestination $ApprovalDraft 'pending approval draft' } else { '' }
    $uriPath = if ($reviewOnly) { '' } else { Resolve-EmptyDestination $PrivateImageUriPath 'private image URI artifact' }
    $publishPath = if ($reviewOnly) { '' } else { Resolve-EmptyDestination $PublishReceipt 'publish receipt' }
    $backendPath = Copy-ProtectedInput $BackendConfig 'backend.hcl' 'backend config'
    $bootstrapPath = Copy-ProtectedInput $BootstrapApplyReceipt 'bootstrap-apply-receipt.json' 'bootstrap apply receipt'
    $prepPath = Copy-ProtectedInput $PreparationReceipt 'preparation-receipt.json' 'preparation receipt'
    $reportPath = Copy-ProtectedInput $ScanReport 'scan-report.input.json' 'scan report'
    $policyPath = Copy-ProtectedInput $ScanPolicyFile 'scan-policy.input' 'scan policy'
    $approvalPath = if ($reviewOnly) { '' } else { Copy-ProtectedInput $ApprovalFile 'publish-approval.json' 'approval' }
    $checker = Copy-ProtectedInput (Join-Path $script:TrustedRepositoryRoot 'scripts/check_opendart_worker_publish.py') 'check-publish.py' 'publish checker'
    $backendChecker = Copy-ProtectedInput (Join-Path $script:TrustedRepositoryRoot 'scripts/check_terraform_backend_config.py') 'check-backend.py' 'backend checker'
    $publisherScript = Copy-ProtectedInput $PSCommandPath 'publisher-script.ps1' 'publisher script'
    $python = Resolve-Application 'python.exe' 'Python executable'
    $aws = Resolve-Application 'aws.exe' 'AWS CLI executable'
    $docker = Resolve-Application 'docker.exe' 'Docker executable'
    $terraform = Resolve-Application 'terraform.exe' 'Terraform executable'
    $scanner = Resolve-Application $ScannerExecutable 'Trivy executable'
    if ([IO.Path]::GetFileName($scanner) -notmatch '^trivy(?:\.exe)?$') { throw 'only the fixed Trivy scanner interface is supported' }
    $backendSha = Invoke-Captured $python @('-I','-S','-B',$backendChecker,'--config',$backendPath,'--terraform-root','serverless-opendart','--print-canonical-sha256') 'private backend validation'
    Assert-Hex64 $backendSha 'canonical backend hash'
    $null = Invoke-Captured $python @('-I','-S','-B',$checker,'bootstrap','--receipt',$bootstrapPath,'--backend-config-sha256',$backendSha) 'bootstrap receipt validation'
    $null = Invoke-Captured $python @('-I','-S','-B',$checker,'preparation','--receipt',$prepPath) 'preparation receipt validation'
    $bootstrap = Assert-JsonObject $bootstrapPath 'bootstrap receipt'
    Assert-BootstrapReceiptInline $bootstrap $backendSha
    $prep = Assert-JsonObject $prepPath 'preparation receipt'
    Assert-PreparationInline $prep
    foreach ($binding in @{
        operation_ref=$OperationRef; source_revision=$SourceRevision; scan_severity_selection=$SeveritySelection
        scan_policy_sha256=(Get-FileSha256 $policyPath); scan_report_sha256=(Get-FileSha256 $reportPath)
    }.GetEnumerator()) { if ($prep.($binding.Key) -ne $binding.Value) { throw "preparation binding mismatch: $($binding.Key)" } }
    $account = Invoke-Captured $aws @('sts','get-caller-identity','--query','Account','--output','text','--no-cli-pager') 'provider identity query'
    if ($account -notmatch '^\d{12}$') { throw 'provider identity returned an unexpected shape' }
    $accountSha = Get-TextSha256 $account
    $bootstrapSha = Get-FileSha256 $bootstrapPath
    $prepSha = Get-FileSha256 $prepPath
    $localRef = "jcareer-opendart-worker-local:$ImageTag"
    $imageId = Invoke-Captured $docker @('image','inspect','--format={{.Id}}',$localRef) 'local image inspection'
    if ((Get-TextSha256 $imageId) -ne $prep.local_image_id_sha256) { throw 'prepared local image binding mismatch' }
    $imagePlatform = Invoke-Captured $docker @('image','inspect','--format={{.Os}}/{{.Architecture}}',$localRef) 'local image platform inspection'
    if ($imagePlatform -ne 'linux/amd64') { throw 'prepared worker image platform changed' }
    if ((Get-FileSha256 $scanner) -ne $prep.scanner_executable_sha256) { throw 'scanner executable binding mismatch' }
    $version = Invoke-Captured $scanner @('--version') 'scanner version query'
    if ((Get-TextSha256 $version) -ne $prep.scanner_version_sha256) { throw 'scanner version binding mismatch' }
    $tfRoot = Join-Path $script:TrustedRepositoryRoot 'terraform/serverless-opendart'
    $null = Invoke-Captured $terraform @("-chdir=$tfRoot",'init','-reconfigure',"-backend-config=$backendPath",'-lockfile=readonly','-input=false','-no-color') 'Terraform private state initialization'
    $state = Invoke-Captured $terraform @("-chdir=$tfRoot",'state','list','-no-color') 'bootstrap state read'
    $expectedState = @('aws_cloudwatch_log_group.worker[0]','aws_dynamodb_table.results[0]','aws_ecr_lifecycle_policy.worker[0]','aws_ecr_repository.worker[0]','aws_iam_role.worker[0]','aws_iam_role_policy.worker[0]','aws_sqs_queue.dead_letter[0]','aws_sqs_queue.refresh[0]')
    $actualState = @($state -split "`r?`n" | Where-Object { $_ } | Sort-Object)
    if (($actualState -join "`n") -ne (($expectedState | Sort-Object) -join "`n")) { throw 'approved backend is not the exact clean bootstrap state' }
    $repositoryUrl = Invoke-Captured $terraform @("-chdir=$tfRoot",'output','-raw','ecr_repository_url') 'approved state repository resolution'
    if ($repositoryUrl -notmatch '^\d{12}\.dkr\.ecr\.ap-northeast-2\.amazonaws\.com/[a-z0-9][a-z0-9._/-]*$') { throw 'repository output returned an unexpected shape' }
    if (-not $repositoryUrl.StartsWith("$account.dkr.ecr.ap-northeast-2.amazonaws.com/", [StringComparison]::Ordinal)) {
        throw 'repository output is not bound to the current provider account'
    }
    $registryHost,$repositoryName = $repositoryUrl -split '/',2
    $repositoryDescriptionText = Invoke-Captured $aws @(
        'ecr','describe-repositories','--region','ap-northeast-2','--repository-names',$repositoryName,
        '--output','json','--no-cli-pager'
    ) 'ECR repository configuration query'
    try { $repositoryDescription = $repositoryDescriptionText | ConvertFrom-Json }
    catch { throw 'ECR repository configuration is not valid JSON' }
    $repositories = @($repositoryDescription.repositories)
    if (
        $repositories.Count -ne 1 -or
        [string]$repositories[0].registryId -cne $account -or
        [string]$repositories[0].repositoryName -cne $repositoryName -or
        [string]$repositories[0].repositoryUri -cne $repositoryUrl -or
        [string]$repositories[0].imageTagMutability -cne 'IMMUTABLE' -or
        $repositories[0].imageScanningConfiguration.scanOnPush -ne $true -or
        [string]$repositories[0].encryptionConfiguration.encryptionType -cne 'AES256'
    ) { throw 'ECR repository configuration drifted from the approved bootstrap boundary' }
    $repositoryConfiguration = [ordered]@{
        repository_name_sha256 = (Get-TextSha256 $repositoryName)
        repository_url_sha256 = (Get-TextSha256 $repositoryUrl)
        image_tag_mutability = 'IMMUTABLE'
        scan_on_push = $true
        encryption_type = 'AES256'
    }
    $repositoryConfigurationSha = Get-TextSha256 ($repositoryConfiguration | ConvertTo-Json -Compress)
    $repositoryDescriptionText = $null
    $repositoryDescription = $null
    $repositories = $null
    $repositorySha = Get-TextSha256 $repositoryUrl
    $account = $null
    $approvalArgs = @('-I','-S','-B',$checker,'approval','--approval',$approvalPath)
    $bindings = [ordered]@{
        operation_ref=$OperationRef; expected_region='ap-northeast-2'; backend_config_sha256=$backendSha
        backend_file_sha256=(Get-FileSha256 $backendPath)
        bootstrap_apply_receipt_sha256=$bootstrapSha; provider_account_sha256=$accountSha
        preparation_receipt_sha256=$prepSha; source_revision=$SourceRevision; source_tree_sha256=$prep.source_tree_sha256
        source_archive_sha256=$prep.source_archive_sha256; dockerfile_sha256=$prep.dockerfile_sha256
        requirements_sha256=$prep.requirements_sha256; local_image_id_sha256=$prep.local_image_id_sha256
        image_tag=$ImageTag; publisher_script_sha256=(Get-FileSha256 $publisherScript)
        approval_checker_sha256=(Get-FileSha256 $checker); backend_checker_sha256=(Get-FileSha256 $backendChecker)
        python_executable_sha256=(Get-FileSha256 $python); aws_executable_sha256=(Get-FileSha256 $aws)
        docker_executable_sha256=(Get-FileSha256 $docker); terraform_executable_sha256=(Get-FileSha256 $terraform)
        scanner_executable_sha256=$prep.scanner_executable_sha256
        scanner_version_sha256=$prep.scanner_version_sha256; scan_severity_selection=$SeveritySelection
        scan_policy_sha256=$prep.scan_policy_sha256; scan_report_sha256=$prep.scan_report_sha256
        ecr_repository_url_sha256=$repositorySha; ecr_repository_configuration_sha256=$repositoryConfigurationSha
    }
    foreach ($binding in $bindings.GetEnumerator()) { $approvalArgs += @('--expected',"$($binding.Key)=$($binding.Value)") }
    if ($reviewOnly) {
        $draft = [ordered]@{
            schema_version='jcareer-opendart-worker-publish-approval-v1'; scope='serverless-opendart-worker-publish'
            decision='PENDING_HUMAN_DECISION'; approval_ref='APPROVAL-REPLACE_ME_0001'; reviewer_ref='reviewer:replace_me'
            approved_at='1970-01-01T00:00:00Z'; expires_at='1970-01-01T01:00:00Z'
            operation_ref=$OperationRef; expected_region='ap-northeast-2'; backend_config_sha256=$backendSha
            backend_file_sha256=$bindings.backend_file_sha256
            bootstrap_apply_receipt_sha256=$bootstrapSha; provider_account_sha256=$accountSha
            preparation_receipt_sha256=$prepSha; source_revision=$SourceRevision
            source_tree_sha256=$prep.source_tree_sha256; source_archive_sha256=$prep.source_archive_sha256
            dockerfile_sha256=$prep.dockerfile_sha256; requirements_sha256=$prep.requirements_sha256
            local_image_id_sha256=$prep.local_image_id_sha256; image_tag=$ImageTag
            publisher_script_sha256=$bindings.publisher_script_sha256
            approval_checker_sha256=$bindings.approval_checker_sha256
            backend_checker_sha256=$bindings.backend_checker_sha256
            python_executable_sha256=$bindings.python_executable_sha256
            aws_executable_sha256=$bindings.aws_executable_sha256
            docker_executable_sha256=$bindings.docker_executable_sha256
            terraform_executable_sha256=$bindings.terraform_executable_sha256
            scanner_executable_sha256=$prep.scanner_executable_sha256
            scanner_version_sha256=$prep.scanner_version_sha256; scan_severity_selection=$SeveritySelection
            scan_policy_ref='policy:replace_me'; scan_policy_sha256=$prep.scan_policy_sha256
            scan_report_sha256=$prep.scan_report_sha256; scan_human_disposition='PENDING_HUMAN_DECISION'
            ecr_repository_url_sha256=$repositorySha
            ecr_repository_configuration_sha256=$repositoryConfigurationSha; synthetic_data_only=$true
            notes='Fact-bound draft only. A human must review the scan and create a separately approved single-publish record.'
        }
        Write-NewUtf8 $draftPath ($draft | ConvertTo-Json -Depth 5)
        Set-Journal 'BINDINGS_CAPTURED_PENDING_HUMAN_DECISION'
        Write-Output 'OPENDART_WORKER_PUBLISH_REVIEW=PENDING_HUMAN_DECISION'
        Write-Output 'RAW_ACCOUNT_AND_REPOSITORY_IDENTIFIERS_NOT_EMITTED=true'
        return
    }
    $approval = Assert-JsonObject $approvalPath 'approval'
    Assert-PublishApprovalInline $approval $bindings
    $null = Invoke-Captured $python $approvalArgs 'human approval validation'
    $preflight = Invoke-Captured $aws @('ecr','batch-get-image','--region','ap-northeast-2','--repository-name',$repositoryName,'--image-ids',"imageTag=$ImageTag",'--output','json','--no-cli-pager') 'ECR unique tag check'
    $preflightJson = $preflight | ConvertFrom-Json
    if (@($preflightJson.images).Count -ne 0 -or @($preflightJson.failures).Count -ne 1 -or $preflightJson.failures[0].failureCode -ne 'ImageNotFound') { throw 'unique image tag is not confirmed absent' }
    $remoteTag = "$repositoryUrl`:$ImageTag"
    $dockerAuthDirectory = Join-Path $script:ArtifactRoot 'docker-auth'
    New-Item -ItemType Directory -Path $dockerAuthDirectory | Out-Null
    Protect-CurrentUserDirectory $dockerAuthDirectory
    $loginSucceeded = $false
    $dockerAuthCleanupObserved = $false
    $publishError = $null
    $digest = ''
    $pushReportedDigest = ''
    try {
        $loginPassword = Invoke-Captured $aws @('ecr','get-login-password','--region','ap-northeast-2','--no-cli-pager') 'ECR login token query'
        $loginOutput = ($loginPassword | & $docker --config $dockerAuthDirectory login --username AWS --password-stdin $registryHost 2>&1 | Out-String)
        $loginPassword = $null
        if ($LASTEXITCODE -ne 0) { throw 'docker registry login failed; raw output was suppressed' }
        $loginSucceeded = $true
        $null = Invoke-Captured $docker @('tag',$localRef,$remoteTag) 'docker image tag'
        $pushOutput = Invoke-Captured $docker @('--config',$dockerAuthDirectory,'push',$remoteTag) 'docker push'
        $reported = @([regex]::Matches($pushOutput, '(?im)digest:\s*(sha256:[0-9a-f]{64})') | ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique)
        $pushOutput = $null
        if ($reported.Count -ne 1) { throw 'docker push did not report exactly one immutable digest' }
        $pushReportedDigest = $reported[0]
        $digest = Invoke-Captured $aws @('ecr','describe-images','--region','ap-northeast-2','--repository-name',$repositoryName,'--image-ids',"imageTag=$ImageTag",'--query','imageDetails[0].imageDigest','--output','text','--no-cli-pager') 'ECR digest re-query'
        if ($digest -notmatch '^sha256:[0-9a-f]{64}$' -or $digest -cne $pushReportedDigest) {
            throw 'ECR digest does not match the digest reported by the approved push'
        }
    } catch {
        $publishError = $_
    } finally {
        $loginPassword = $null
        $loginOutput = $null
        $pushOutput = $null
        if ($loginSucceeded) {
            $logoutOutput = (& $docker --config $dockerAuthDirectory logout $registryHost 2>&1 | Out-String)
            $logoutExit = $LASTEXITCODE
            $logoutOutput = $null
            $configPath = Join-Path $dockerAuthDirectory 'config.json'
            if ($logoutExit -eq 0 -and (Test-Path -LiteralPath $configPath -PathType Leaf)) {
                [IO.File]::WriteAllText($configPath, '{}', [Text.UTF8Encoding]::new($false))
                $dockerAuthCleanupObserved = ((Get-Content -LiteralPath $configPath -Raw -Encoding UTF8) -ceq '{}')
            }
        }
    }
    if (-not $dockerAuthCleanupObserved) { throw 'dedicated Docker authentication cleanup was not observed' }
    if ($null -ne $publishError) { throw $publishError }
    $accountAfter = Invoke-Captured $aws @('sts','get-caller-identity','--query','Account','--output','text','--no-cli-pager') 'post-push provider identity query'
    if ((Get-TextSha256 $accountAfter) -ne $accountSha) { throw 'provider identity changed during publication' }
    $digestPinnedUri = "$repositoryUrl@$digest"
    Write-NewUtf8 $uriPath $digestPinnedUri
    $privateArtifactSha = Get-FileSha256 $uriPath
    $receipt = [ordered]@{
        schema_version='jcareer-redacted-opendart-worker-publish-receipt-v1'; scope='serverless-opendart-worker-publish'
        approval_ref=$approval.approval_ref; operation_ref=$OperationRef; completed_at=[DateTimeOffset]::UtcNow.ToString('o')
        approval_record_sha256=(Get-FileSha256 $approvalPath)
        backend_config_sha256=$backendSha; backend_file_sha256=$bindings.backend_file_sha256
        bootstrap_apply_receipt_sha256=$bootstrapSha; provider_account_sha256=$accountSha
        preparation_receipt_sha256=$prepSha; source_revision=$SourceRevision; source_tree_sha256=$prep.source_tree_sha256
        source_archive_sha256=$prep.source_archive_sha256; dockerfile_sha256=$prep.dockerfile_sha256
        requirements_sha256=$prep.requirements_sha256; publisher_script_sha256=$bindings.publisher_script_sha256
        approval_checker_sha256=$bindings.approval_checker_sha256; backend_checker_sha256=$bindings.backend_checker_sha256
        python_executable_sha256=$bindings.python_executable_sha256; aws_executable_sha256=$bindings.aws_executable_sha256
        docker_executable_sha256=$bindings.docker_executable_sha256; terraform_executable_sha256=$bindings.terraform_executable_sha256
        scan_policy_sha256=$prep.scan_policy_sha256
        scan_report_sha256=$prep.scan_report_sha256; repository_url_sha256=$repositorySha
        ecr_repository_configuration_sha256=$repositoryConfigurationSha
        image_tag_sha256=(Get-TextSha256 $ImageTag); docker_push_reported_digest=$pushReportedDigest; ecr_image_digest=$digest
        digest_pinned_uri_sha256=(Get-TextSha256 $digestPinnedUri); private_uri_artifact_sha256=$privateArtifactSha
        private_uri_artifact_created=$true; resource_identifiers_included=$false; protected_input_snapshot_count=9
        docker_auth_cleanup_observed=$dockerAuthCleanupObserved; local_artifact_cleanup_claimed=$false
        human_release_decision_created=$false; result='PUBLISH_COMPLETED_PENDING_RUNTIME_PLAN'
    }
    Write-NewUtf8 $publishPath ($receipt | ConvertTo-Json -Depth 5)
    Set-Journal 'PUBLISH_COMPLETED_PENDING_RUNTIME_PLAN'
    Write-Output 'OPENDART_WORKER_PUBLISH=PUBLISH_COMPLETED_PENDING_RUNTIME_PLAN'
    Write-Output 'LOCAL_ARTIFACTS_RETAINED=HUMAN_DISPOSITION_REQUIRED'
}

Assert-NoReparsePathChain $script:TrustedRepositoryRoot 'trusted repository root'
if (-not (Test-Path -LiteralPath $script:TrustedRepositoryRoot -PathType Container)) {
    throw 'trusted repository root is unavailable'
}
$expectedScriptPath = [IO.Path]::GetFullPath((Join-Path $script:TrustedRepositoryRoot 'scripts/Invoke-ApprovedOpenDartWorkerPublish.ps1'))
if (-not [string]::Equals([IO.Path]::GetFullPath($PSCommandPath), $expectedScriptPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'publisher must execute from its fixed trusted repository path'
}

try {
    if ($Mode -eq 'Prepare') { Invoke-Prepare } else { Invoke-ReviewOrPublish }
} catch {
    $failureType = $_.Exception.GetType().Name
    if ($script:JournalOwned -and $script:JournalPath -and (Test-Path -LiteralPath $script:JournalPath)) {
        Set-Journal 'FAILED_REQUIRES_HUMAN_DISPOSITION'
    }
    Write-Output "OPENDART_WORKER_PUBLISHER_FAILURE_STEP=$($script:CurrentStep)"
    Write-Output "OPENDART_WORKER_PUBLISHER_FAILURE_TYPE=$failureType"
    throw 'OpenDART worker publisher stopped fail-closed; inspect the redacted journal and retained artifacts manually'
}
