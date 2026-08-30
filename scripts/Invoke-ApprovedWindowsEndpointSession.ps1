[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackendConfig,

    [Parameter(Mandatory = $true)]
    [string]$ApprovalFile,

    [Parameter(Mandatory = $true)]
    [string]$EndpointApplyReceipt,

    [Parameter(Mandatory = $true)]
    [string]$ImageReceipt,

    [Parameter(Mandatory = $true)]
    [string]$BuildObservation,

    [Parameter(Mandatory = $true)]
    [string]$PreviewUrl,

    [Parameter(Mandatory = $true)]
    [Security.SecureString]$PreviewBootstrapToken,

    [Parameter(Mandatory = $true)]
    [ValidateSet('JCAREER_THREE_WINDOWS_CONSULTANT_SESSIONS_APPROVED')]
    [string]$ActivationAcknowledgement,

    [switch]$OpenInteractiveTunnels
)

$ErrorActionPreference = 'Stop'
Microsoft.PowerShell.Core\Set-StrictMode -Version Latest
$repoRoot = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $PSScriptRoot '..')).Path
$terraformRelative = 'terraform/workplace-endpoints'
$workDirectory = Microsoft.PowerShell.Management\Join-Path (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot $terraformRelative)).Path '.terraform'
$observationFile = Microsoft.PowerShell.Management\Join-Path $workDirectory 'last-consultant-session-observation.json'
$failureObservationFile = Microsoft.PowerShell.Management\Join-Path $workDirectory 'last-consultant-session-failure-observation.json'
$configureScriptSource = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot 'fleet/images/windows/Configure-JCareerSession.ps1')).Path
$removeScriptSource = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot 'fleet/images/windows/Remove-JCareerSession.ps1')).Path
$backendCheckerSource = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot 'scripts/check_terraform_backend_config.py')).Path
$approvalCheckerSource = (Microsoft.PowerShell.Management\Resolve-Path (Microsoft.PowerShell.Management\Join-Path $repoRoot 'scripts/check_windows_endpoint_session_approval.py')).Path
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$taskTemporary = [IO.Path]::GetFullPath((Microsoft.PowerShell.Management\Join-Path $temporaryRoot ('jcareer-endpoint-session-' + [Guid]::NewGuid().ToString('N'))))
$utf8WithoutBom = [Text.UTF8Encoding]::new($false)
if (-not $taskTemporary.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Temporary session path escaped the system temporary directory.'
}

$script:requestIndex = 0
$script:tunnelRecords = @()
$script:configuredSessions = @()
$script:remoteCleanupCompletedRefs = @{}
$script:removeScriptHash = $null
$script:remoteCleanupCompleted = $false
$script:completed = $false
$script:lastTunnelCleanupResult = $null
$script:tunnelCleanupObservations = @{}
$script:configurationReceiptsObservedRefs = @{}
$script:approvalLeaseMutex = $null
$script:approvalLeaseAcquired = $false
$script:approvalLeaseName = ''
$script:awsExecutable = ''
$script:terraformExecutable = ''
$script:pythonExecutable = ''
$script:mstscExecutable = ''
$script:approvalFileSha256 = ''
$script:protectedSnapshotStreams = @()
$script:protectedSnapshotCount = 0
$script:protectedSnapshotDirectory = ''
$script:localSnapshotCleanupObserved = $false
$script:localSnapshotCleanupRetryRequired = $false
$script:localTaskTemporaryCleanupObserved = $false
$script:localTaskTemporaryCleanupRetryRequired = $false

function Get-Sha256Text {
    param([Parameter(Mandatory = $true)][string]$Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)) }
    finally { $sha.Dispose() }
    return -join ($hash | ForEach-Object { $_.ToString('x2') })
}

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

function New-CurrentUserFileAcl {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [Security.AccessControl.FileSecurity]::new()
    $acl.SetOwner($identity)
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
        $identity,
        [Security.AccessControl.FileSystemRights]::FullControl,
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

function Get-StreamSha256 {
    param([Parameter(Mandatory = $true)][IO.Stream]$Stream)
    $Stream.Position = 0
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = $sha.ComputeHash($Stream) }
    finally { $sha.Dispose() }
    return ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
}

function Copy-ProtectedStableFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$DestinationName
    )
    if (-not [IO.File]::Exists($Source)) { throw 'A required snapshot source is unavailable.' }
    if (-not $script:protectedSnapshotDirectory) { throw 'The protected snapshot directory is unavailable.' }
    $sourcePath = [IO.Path]::GetFullPath($Source)
    $destinationPath = [IO.Path]::GetFullPath(
        (Microsoft.PowerShell.Management\Join-Path $script:protectedSnapshotDirectory $DestinationName)
    )
    $snapshotPrefix = $script:protectedSnapshotDirectory.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $destinationPath.StartsWith($snapshotPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'A protected snapshot path escaped its directory.'
    }
    $sourceStream = $null
    $destinationStream = $null
    $snapshotReadLock = $null
    try {
        $sourceStream = [IO.File]::Open(
            $sourcePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read
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
        if ([long]$destinationStream.Length -ne $sourceLength) {
            throw 'A protected snapshot length did not match its source.'
        }
        $snapshotHash = Get-StreamSha256 -Stream $destinationStream
        $sourcePostHash = Get-StreamSha256 -Stream $sourceStream
        if (
            $sourcePreHash -ne $snapshotHash -or
            $sourcePreHash -ne $sourcePostHash
        ) {
            throw 'A required input changed while its protected snapshot was captured.'
        }
        $destinationStream.Dispose()
        $destinationStream = $null
        $snapshotReadLock = [IO.File]::Open(
            $destinationPath, [IO.FileMode]::Open,
            [IO.FileAccess]::Read, [IO.FileShare]::Read
        )
        if ([long]$snapshotReadLock.Length -ne $sourceLength) {
            throw 'A protected snapshot length changed before its read lock was established.'
        }
        $snapshotLockedHash = Get-StreamSha256 -Stream $snapshotReadLock
        if ($snapshotLockedHash -ne $sourcePreHash) {
            throw 'A protected snapshot changed before its read lock was established.'
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

function Remove-ProtectedInputSnapshots {
    $disposeErrors = [Collections.Generic.List[string]]::new()
    $remainingStreams = [Collections.Generic.List[object]]::new()
    foreach ($stream in @($script:protectedSnapshotStreams)) {
        try { $stream.Dispose() }
        catch {
            $disposeErrors.Add('snapshot stream disposal failed')
            $remainingStreams.Add($stream)
        }
    }
    $script:protectedSnapshotStreams = @($remainingStreams)
    if (
        $script:protectedSnapshotStreams.Count -eq 0 -and
        $script:protectedSnapshotDirectory -and
        (Microsoft.PowerShell.Management\Test-Path -LiteralPath $script:protectedSnapshotDirectory)
    ) {
        try {
            Microsoft.PowerShell.Management\Remove-Item -LiteralPath $script:protectedSnapshotDirectory -Recurse -Force
        }
        catch { $disposeErrors.Add('snapshot directory removal failed') }
    }
    if (
        $script:protectedSnapshotDirectory -and
        (Microsoft.PowerShell.Management\Test-Path -LiteralPath $script:protectedSnapshotDirectory)
    ) {
        $disposeErrors.Add('snapshot directory remains present')
    }
    if ($disposeErrors.Count -ne 0) {
        $script:localSnapshotCleanupRetryRequired = $true
        throw 'Protected input snapshot cleanup was not fully observed.'
    }
    $script:localSnapshotCleanupObserved = $true
    $script:localSnapshotCleanupRetryRequired = $false
}

function Assert-SessionApprovalActive {
    param([Parameter(Mandatory = $true)]$Approval)
    try {
        $expiry = [DateTimeOffset]::Parse(
            [string]$Approval.session_expires_at,
            [Globalization.CultureInfo]::InvariantCulture,
            [Globalization.DateTimeStyles]::RoundtripKind
        )
    }
    catch { throw 'The protected approval snapshot has an invalid session expiry.' }
    if ([DateTimeOffset]::UtcNow -ge $expiry.ToUniversalTime()) {
        throw 'The protected consultant-session approval has expired.'
    }
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

function Get-SecureStringSha256 {
    param([Parameter(Mandatory = $true)][Security.SecureString]$Secret)
    $pointer = [IntPtr]::Zero
    $plainText = $null
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)
        $plainText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if ($plainText -notmatch '^[0-9a-f]{64}$') {
            throw 'Preview bootstrap token must be 64 lowercase hex characters.'
        }
        return Get-Sha256Text $plainText
    }
    finally {
        $plainText = $null
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

function Set-OneTimePreviewBootstrapClipboard {
    param(
        [Parameter(Mandatory = $true)][Security.SecureString]$Secret,
        [Parameter(Mandatory = $true)][string]$CleanPreviewUrl
    )
    $pointer = [IntPtr]::Zero
    $plainText = $null
    $bootstrapUrl = $null
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)
        $plainText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if ($plainText -notmatch '^[0-9a-f]{64}$') {
            throw 'Preview bootstrap token format changed after approval validation.'
        }
        $previewUri = [Uri]$CleanPreviewUrl
        $previewBase = $previewUri.GetLeftPart([UriPartial]::Authority) + '/'
        $bootstrapUrl = $previewBase + '?jcareer_preview=' + $plainText
        Microsoft.PowerShell.Management\Set-Clipboard -Value $bootstrapUrl
    }
    finally {
        $bootstrapUrl = $null
        $plainText = $null
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

function Clear-PreviewBootstrapClipboard {
    try { Microsoft.PowerShell.Management\Set-Clipboard -Value '' }
    catch { throw 'The local clipboard could not be cleared after bootstrap delivery.' }
}

function Remove-TaskTemporaryDirectory {
    if (-not (Test-Path -LiteralPath $taskTemporary)) { return }
    $resolvedTemporary = [IO.Path]::GetFullPath($taskTemporary)
    if (-not $resolvedTemporary.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Temporary cleanup path escaped the system temporary directory.'
    }
    Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
    if (Test-Path -LiteralPath $resolvedTemporary) {
        throw 'Temporary session artifacts were not observed as removed.'
    }
}

function Protect-Diagnostic {
    param([AllowEmptyString()][string]$Text)
    $protected = $Text -replace '(?<!\d)\d{12}(?!\d)', '[REDACTED_ACCOUNT]'
    $protected = $protected -replace 'arn:aws[^\s"'']+', '[REDACTED_ARN]'
    $protected = $protected -replace '(?:AKIA|ASIA)[A-Z0-9]{16}', '[REDACTED_ACCESS_KEY]'
    $protected = $protected -replace '\b(i|vpc|subnet|sg|ami|snap)-[0-9a-f]+\b', '[REDACTED_RESOURCE_ID]'
    $protected = $protected -replace '(?i)(jcareer_preview=)[0-9a-f]{64}', '$1[REDACTED]'
    $protected = $protected -replace '\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '[REDACTED_UUID]'
    $protected = $protected -replace '\b[A-Za-z0-9+=,.@_-]+-[0-9a-f]{17}\b', '[REDACTED_SESSION_ID]'
    $protected = $protected -replace '(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])', '[REDACTED_IP]'
    $protected = $protected -replace '(?i)\bs3://[^\s"'']+', '[REDACTED_S3_LOCATION]'
    $protected = $protected -replace '(?i)(["''])(bucket|key|dynamodb_table|profile|role_arn|workspace_key_prefix|owner|session(?:_?id)?|user(?:_?name)?)\1(\s*[=:]\s*)(?:"(?:\\.|[^"\\])*"|''[^'']*''|[^\s,}\]]+)', '$1$2$1$3[REDACTED_VALUE]'
    $protected = $protected -replace '(?i)\b(bucket|key|dynamodb_table|profile|role_arn|workspace_key_prefix|owner|session(?:id)?|user(?:name)?)(\s*[=:]\s*)(?:"[^"]*"|''[^'']*''|[^\s,]+)', '$1$2[REDACTED_VALUE]'
    $protected = $protected -replace '(?i)\b(S3 bucket|object key|DynamoDB table)\s+(?:"[^"]*"|''[^'']*'')', '$1 [REDACTED_VALUE]'
    $protected = $protected -replace '(?i)(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![0-9a-f:])', '[REDACTED_IPV6]'
    return $protected
}

function Invoke-AwsJson {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $stderrPath = Join-Path $taskTemporary ('aws-stderr-' + [Guid]::NewGuid().ToString('N') + '.txt')
    $previous = $ErrorActionPreference
    $result = @()
    $stderr = ''
    $exitCode = -1
    try {
        if (-not (Test-Path -LiteralPath $taskTemporary -PathType Container)) {
            New-Item -ItemType Directory -Path $taskTemporary | Out-Null
        }
        New-ProtectedEmptyFile -Path $stderrPath
        $ErrorActionPreference = 'Continue'
        if (-not [IO.Path]::IsPathRooted($script:awsExecutable)) {
            throw 'The absolute AWS CLI application path is unavailable.'
        }
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

function Invoke-RemotePowerShell {
    param(
        [Parameter(Mandatory = $true)][string]$InstanceId,
        [Parameter(Mandatory = $true)][string[]]$Commands,
        [Parameter(Mandatory = $true)][string]$Comment
    )
    $script:requestIndex += 1
    if (-not (Test-Path -LiteralPath $taskTemporary -PathType Container)) {
        New-Item -ItemType Directory -Path $taskTemporary | Out-Null
    }
    $requestPath = Join-Path $taskTemporary ("request-{0:D2}.json" -f $script:requestIndex)
    $request = [ordered]@{
        DocumentName = 'AWS-RunPowerShellScript'
        InstanceIds = @($InstanceId)
        Comment = $Comment
        TimeoutSeconds = 300
        Parameters = @{ commands = $Commands }
    }
    Write-JsonUtf8NoBom -Path $requestPath -Value $request -Depth 8
    $sent = Invoke-AwsJson @(
        'ssm', 'send-command', '--region', 'ap-northeast-2',
        '--cli-input-json', "file://$requestPath", '--output', 'json', '--no-cli-pager'
    )
    $commandId = [string]$sent.Command.CommandId
    if ($commandId -notmatch '^[0-9a-f-]{36}$') { throw 'SSM did not return one command identifier.' }
    $deadline = [DateTimeOffset]::UtcNow.AddMinutes(7)
    $status = 'TimedOut'
    do {
        Start-Sleep -Seconds 3
        try {
            $result = Invoke-AwsJson @(
                'ssm', 'get-command-invocation', '--region', 'ap-northeast-2',
                '--command-id', $commandId, '--instance-id', $InstanceId,
                '--output', 'json', '--no-cli-pager'
            )
        }
        catch {
            if ([DateTimeOffset]::UtcNow -ge $deadline) { throw }
            continue
        }
        $status = [string]$result.Status
        if ($status -in @('Success', 'Cancelled', 'TimedOut', 'Failed', 'Cancelling')) { break }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    if ($status -ne 'Success') {
        throw "SSM endpoint configuration did not succeed: $status"
    }
    return [string]$result.StandardOutputContent
}

function Get-ActiveSsmSessions {
    param([Parameter(Mandatory = $true)][string]$Target)

    $document = Invoke-AwsJson @(
        'ssm', 'describe-sessions', '--region', 'ap-northeast-2', '--state', 'Active',
        '--filters', "key=Target,value=$Target", '--output', 'json', '--no-cli-pager'
    )
    return @($document.Sessions)
}

function Get-HistoricalSsmSessions {
    param([Parameter(Mandatory = $true)][string]$Target)

    $document = Invoke-AwsJson @(
        'ssm', 'describe-sessions', '--region', 'ap-northeast-2', '--state', 'History',
        '--filters', "key=Target,value=$Target", '--output', 'json', '--no-cli-pager'
    )
    return @($document.Sessions)
}

function Get-SsmSessionHistoryById {
    param([Parameter(Mandatory = $true)][string]$SessionId)

    $document = Invoke-AwsJson @(
        'ssm', 'describe-sessions', '--region', 'ap-northeast-2', '--state', 'History',
        '--filters', "key=SessionId,value=$SessionId", '--max-results', '2',
        '--output', 'json', '--no-cli-pager'
    )
    return @($document.Sessions)
}

function ConvertTo-SsmTimestampUtc {
    param([Parameter(Mandatory = $true)]$Value)

    $text = [string]$Value
    try { return [DateTimeOffset]::Parse($text).ToUniversalTime() }
    catch {
        $epochSeconds = 0.0
        if (-not [double]::TryParse(
            $text,
            [Globalization.NumberStyles]::Float,
            [Globalization.CultureInfo]::InvariantCulture,
            [ref]$epochSeconds
        )) {
            throw 'SSM session start timestamp is neither ISO-8601 nor Unix epoch seconds.'
        }
        return ([DateTimeOffset]'1970-01-01T00:00:00Z').AddSeconds($epochSeconds)
    }
}

function Test-SsmSessionMatchesRecord {
    param(
        [Parameter(Mandatory = $true)]$Session,
        [Parameter(Mandatory = $true)]$Record
    )

    if (
        [string]$Session.SessionId -notmatch '^[A-Za-z0-9_+=,.@-]{1,96}$' -or
        [string]$Session.Target -ne [string]$Record.InstanceId -or
        [string]$Session.Reason -ne [string]$Record.LaunchReason -or
        [string]$Session.DocumentName -ne 'AWS-StartPortForwardingSession' -or
        [string]$Session.Owner -ne [string]$Record.ExpectedOwner -or
        [string]$Session.SessionId -in @($Record.PriorSessionIds)
    ) {
        return $false
    }
    try {
        $started = ConvertTo-SsmTimestampUtc $Session.StartDate
    }
    catch { return $false }
    return (
        $started -ge ([DateTimeOffset]$Record.LaunchedAt).AddSeconds(-5) -and
        $started -le ([DateTimeOffset]$Record.BindingDeadline).AddSeconds(5)
    )
}

function Get-RecordSsmSessions {
    param(
        [Parameter(Mandatory = $true)]$Record,
        [switch]$IncludeHistory
    )

    $sessions = @(Get-ActiveSsmSessions -Target ([string]$Record.InstanceId))
    if ($IncludeHistory) {
        $sessions += @(Get-HistoricalSsmSessions -Target ([string]$Record.InstanceId))
    }
    return @(
        $sessions |
            Where-Object { Test-SsmSessionMatchesRecord -Session $_ -Record $Record } |
            Sort-Object -Property SessionId -Unique
    )
}

function Get-ProcessDescendantIdentities {
    param(
        [Parameter(Mandatory = $true)][int]$RootProcessId,
        [Parameter(Mandatory = $true)][long]$RootStartTimeUtcTicks
    )

    if ($RootStartTimeUtcTicks -le 0) {
        throw 'A positive root-process start identity is required for descendant discovery.'
    }
    $processes = @(
        CimCmdlets\Get-CimInstance Win32_Process |
            Select-Object ProcessId, ParentProcessId, Name, CreationDate
    )
    $pending = [Collections.Generic.Queue[int]]::new()
    $parentStartTicks = @{}
    $visited = [Collections.Generic.HashSet[int]]::new()
    $pending.Enqueue($RootProcessId)
    $parentStartTicks[$RootProcessId] = $RootStartTimeUtcTicks
    [void]$visited.Add($RootProcessId)
    $identities = @()
    while ($pending.Count -gt 0) {
        $parent = $pending.Dequeue()
        $parentStarted = [long]$parentStartTicks[$parent]
        foreach ($child in @($processes | Where-Object { [int]$_.ParentProcessId -eq $parent })) {
            $childId = [int]$child.ProcessId
            if ($visited.Contains($childId)) { continue }
            [void]$visited.Add($childId)
            $process = $null
            try {
                $snapshotStarted = [long]([DateTime]$child.CreationDate).ToUniversalTime().Ticks
                $process = Microsoft.PowerShell.Management\Get-Process -Id $childId -ErrorAction Stop
                $handle = $process.SafeHandle
                if ($handle.IsInvalid -or $handle.IsClosed) { continue }
                $refreshed = @(
                    CimCmdlets\Get-CimInstance Win32_Process -Filter "ProcessId = $childId" |
                        Select-Object ProcessId, ParentProcessId, Name, CreationDate
                )
                if ($refreshed.Count -ne 1) { continue }
                $refreshedStarted = [long]([DateTime]$refreshed[0].CreationDate).ToUniversalTime().Ticks
                if (
                    [int]$refreshed[0].ParentProcessId -ne $parent -or
                    $refreshedStarted -ne $snapshotStarted
                ) {
                    continue
                }
                $started = [long]$process.StartTime.ToUniversalTime().Ticks
                if (
                    $started -lt $parentStarted -or
                    [Math]::Abs($started - $refreshedStarted) -gt
                        [TimeSpan]::FromMilliseconds(100).Ticks
                ) {
                    continue
                }
                $identities += [pscustomobject]@{
                    ProcessId = $childId
                    ProcessName = [string]$process.ProcessName
                    StartTimeUtcTicks = $started
                    ParentProcessId = $parent
                    ParentStartTimeUtcTicks = $parentStarted
                    CimCreationTimeUtcTicks = $refreshedStarted
                }
                $parentStartTicks[$childId] = $started
                $pending.Enqueue($childId)
            }
            catch { continue }
            finally {
                if ($null -ne $process) { $process.Dispose() }
            }
        }
    }
    return @($identities | Sort-Object -Property StartTimeUtcTicks, ProcessId -Unique)
}

function Get-SessionManagerPluginDescendants {
    param(
        [Parameter(Mandatory = $true)][int]$RootProcessId,
        [Parameter(Mandatory = $true)][long]$RootStartTimeUtcTicks
    )

    return @(
        Get-ProcessDescendantIdentities `
            -RootProcessId $RootProcessId `
            -RootStartTimeUtcTicks $RootStartTimeUtcTicks |
            Where-Object { [string]$_.ProcessName -ieq 'session-manager-plugin' }
    )
}

function Test-ProcessIdentityActive {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][long]$StartTimeUtcTicks,
        [string]$ExpectedName = ''
    )

    $process = Microsoft.PowerShell.Management\Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $false }
    if ($ExpectedName -and [string]$process.ProcessName -ine $ExpectedName) { return $false }
    return [long]$process.StartTime.ToUniversalTime().Ticks -eq $StartTimeUtcTicks
}

function Stop-ExactProcessIdentity {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][long]$StartTimeUtcTicks,
        [Parameter(Mandatory = $true)][string]$ExpectedName
    )

    $process = Microsoft.PowerShell.Management\Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($null -eq $process) { return }
    try {
        $handle = $process.SafeHandle
        if ($handle.IsInvalid -or $handle.IsClosed) {
            throw 'Could not retain an exact process handle for cleanup.'
        }
        if (
            [string]$process.ProcessName -ine $ExpectedName -or
            [long]$process.StartTime.ToUniversalTime().Ticks -ne $StartTimeUtcTicks
        ) {
            return
        }
        $process.Kill()
        if (-not $process.WaitForExit(5000)) {
            throw 'The exact tracked process did not exit after termination.'
        }
    }
    finally { $process.Dispose() }
}

function Stop-RecordedRootProcess {
    param([Parameter(Mandatory = $true)]$Record)

    $process = $Record.ProcessObject
    if ($null -eq $process) {
        Stop-ExactProcessIdentity `
            -ProcessId ([int]$Record.ProcessId) `
            -StartTimeUtcTicks ([long]$Record.ProcessStartTimeUtcTicks) `
            -ExpectedName 'aws'
        return
    }
    $handle = $process.SafeHandle
    if ($handle.IsInvalid -or $handle.IsClosed -or $process.HasExited) { return }
    if (
        [int]$process.Id -ne [int]$Record.ProcessId -or
        [string]$process.ProcessName -ine 'aws' -or
        (
            [long]$Record.ProcessStartTimeUtcTicks -gt 0 -and
            [long]$process.StartTime.ToUniversalTime().Ticks -ne
                [long]$Record.ProcessStartTimeUtcTicks
        )
    ) {
        throw 'The retained root-process object no longer matches its launch identity.'
    }
    $process.Kill()
    if (-not $process.WaitForExit(5000)) {
        throw 'The retained AWS CLI process did not exit after termination.'
    }
}

function Update-TrackedProcessDescendants {
    param([Parameter(Mandatory = $true)]$Record)

    if ([long]$Record.ProcessStartTimeUtcTicks -le 0) {
        $root = $Record.ProcessObject
        if ($null -eq $root -or $root.HasExited) {
            throw 'The root process ended before its descendant identity was established.'
        }
        $rootHandle = $root.SafeHandle
        if ($rootHandle.IsInvalid -or $rootHandle.IsClosed) {
            throw 'The retained root-process handle is unavailable for descendant discovery.'
        }
        $Record['ProcessStartTimeUtcTicks'] = [long]$root.StartTime.ToUniversalTime().Ticks
    }
    $latest = @(
        Get-ProcessDescendantIdentities `
            -RootProcessId ([int]$Record.ProcessId) `
            -RootStartTimeUtcTicks ([long]$Record.ProcessStartTimeUtcTicks)
    )
    $Record['DescendantTrackingEstablished'] = $true
    foreach ($identity in $latest) {
        if (@($Record.ChildProcesses | Where-Object {
            [int]$_.ProcessId -eq [int]$identity.ProcessId -and
            [long]$_.StartTimeUtcTicks -eq [long]$identity.StartTimeUtcTicks
        }).Count -eq 0) {
            $Record.ChildProcesses += $identity
        }
    }
    $Record.PluginProcesses = @(
        $Record.ChildProcesses |
            Where-Object { [string]$_.ProcessName -ieq 'session-manager-plugin' }
    )
}

function Get-LocalPortListeners {
    param([Parameter(Mandatory = $true)][int]$LocalPort)

    return @(
        NetTCPIP\Get-NetTCPConnection -State Listen -ErrorAction Stop |
            Where-Object { [int]$_.LocalPort -eq $LocalPort } |
            Select-Object LocalAddress, LocalPort, OwningProcess
    )
}

function Get-LocalPortListenerProcessIds {
    param([Parameter(Mandatory = $true)][int]$LocalPort)

    return @(
        Get-LocalPortListeners -LocalPort $LocalPort |
            ForEach-Object { [int]$_.OwningProcess } |
            Sort-Object -Unique
    )
}

function Test-LocalPortClosed {
    param([Parameter(Mandatory = $true)][int]$LocalPort)

    return @(Get-LocalPortListeners -LocalPort $LocalPort).Count -eq 0
}

function Stop-EndpointTunnels {
    $results = @()
    $remainingRecords = @()
    $allErrors = [Collections.Generic.List[string]]::new()
    foreach ($record in @($script:tunnelRecords)) {
        $recordErrors = [Collections.Generic.List[string]]::new()
        $sessionIds = [Collections.Generic.List[string]]::new()
        $terminateResponsesObserved = 0
        $terminationObserved = @{}
        try {
            if ([string]$record.SessionId) {
                $sessionIds.Add([string]$record.SessionId)
            }
            else {
                $reconcileDeadline = [DateTimeOffset]::UtcNow.AddSeconds(15)
                $candidates = @()
                $lastReconcileError = ''
                do {
                    try {
                        $candidates = @(Get-RecordSsmSessions -Record $record -IncludeHistory)
                        $lastReconcileError = ''
                    }
                    catch { $lastReconcileError = Protect-Diagnostic $_.Exception.Message }
                    if ($candidates.Count -gt 0) { break }
                    Start-Sleep -Seconds 1
                } while ([DateTimeOffset]::UtcNow -lt $reconcileDeadline)
                if ($candidates.Count -eq 0) {
                    if ($lastReconcileError) { $recordErrors.Add($lastReconcileError) }
                }
                foreach ($candidate in $candidates) {
                    $sessionIds.Add([string]$candidate.SessionId)
                }
                if ($candidates.Count -eq 1) {
                    $record['SessionId'] = [string]$candidates[0].SessionId
                }
                if ($candidates.Count -ne 1) {
                    if ($candidates.Count -gt 1) {
                        $recordErrors.Add('More than one SSM session matched one tunnel launch; all candidates were selected for cleanup.')
                    }
                }
            }
        }
        catch { $recordErrors.Add((Protect-Diagnostic $_.Exception.Message)) }
        foreach ($sessionId in @($sessionIds)) {
            try {
                $active = @(
                    Get-ActiveSsmSessions -Target ([string]$record.InstanceId) |
                        Where-Object { [string]$_.SessionId -eq $sessionId }
                )
                if ($active.Count -gt 1) {
                    throw 'AWS returned duplicate active rows for one SSM session identifier.'
                }
                if ($active.Count -eq 1) {
                    $terminated = Invoke-AwsJson @(
                        'ssm', 'terminate-session', '--region', 'ap-northeast-2',
                        '--session-id', $sessionId, '--output', 'json', '--no-cli-pager'
                    )
                    if ([string]$terminated.SessionId -ne $sessionId) {
                        throw 'SSM terminate-session did not echo the exact requested session identifier.'
                    }
                    $terminateResponsesObserved += 1
                    $terminationObserved[$sessionId] = $true
                }
            }
            catch { $recordErrors.Add((Protect-Diagnostic $_.Exception.Message)) }
        }
        try {
            try {
                Update-TrackedProcessDescendants -Record $record
            }
            catch { $recordErrors.Add((Protect-Diagnostic $_.Exception.Message)) }
            try {
                Stop-RecordedRootProcess -Record $record
            }
            catch { $recordErrors.Add((Protect-Diagnostic $_.Exception.Message)) }
            try { Update-TrackedProcessDescendants -Record $record }
            catch { $recordErrors.Add((Protect-Diagnostic $_.Exception.Message)) }
            foreach ($childIdentity in @(
                $record.ChildProcesses | Sort-Object -Property StartTimeUtcTicks -Descending
            )) {
                try {
                    Stop-ExactProcessIdentity `
                        -ProcessId ([int]$childIdentity.ProcessId) `
                        -StartTimeUtcTicks ([long]$childIdentity.StartTimeUtcTicks) `
                        -ExpectedName ([string]$childIdentity.ProcessName)
                }
                catch { $recordErrors.Add((Protect-Diagnostic $_.Exception.Message)) }
            }
        }
        finally {
            # This finally intentionally exists at record scope: local cleanup is
            # attempted even when session reconciliation or termination failed.
        }

        $deadline = [DateTimeOffset]::UtcNow.AddSeconds(30)
        $sessionTerminalObserved = $false
        $processTreeClosedObserved = $false
        $localPortClosedObserved = $false
        $lastPollError = ''
        do {
            try {
                $lateCandidates = @(Get-RecordSsmSessions -Record $record -IncludeHistory)
                foreach ($candidate in $lateCandidates) {
                    $candidateId = [string]$candidate.SessionId
                    if ($candidateId -notin @($sessionIds)) { $sessionIds.Add($candidateId) }
                }
                if ($lateCandidates.Count -eq 1) {
                    $record['SessionId'] = [string]$lateCandidates[0].SessionId
                }
                elseif ($lateCandidates.Count -gt 1) {
                    $recordErrors.Add('Late reconciliation matched more than one SSM session; all candidates were selected for cleanup.')
                }
                foreach ($sessionId in @($sessionIds)) {
                    if (-not $terminationObserved.ContainsKey($sessionId)) {
                        $lateActive = @(
                            Get-ActiveSsmSessions -Target ([string]$record.InstanceId) |
                                Where-Object { [string]$_.SessionId -eq $sessionId }
                        )
                        if ($lateActive.Count -gt 1) {
                            throw 'AWS returned duplicate active rows during late session reconciliation.'
                        }
                        if ($lateActive.Count -eq 1) {
                            $lateTerminated = Invoke-AwsJson @(
                                'ssm', 'terminate-session', '--region', 'ap-northeast-2',
                                '--session-id', $sessionId, '--output', 'json', '--no-cli-pager'
                            )
                            if ([string]$lateTerminated.SessionId -ne $sessionId) {
                                throw 'Late SSM termination did not echo the exact requested session identifier.'
                            }
                            $terminateResponsesObserved += 1
                            $terminationObserved[$sessionId] = $true
                        }
                    }
                }
                $terminalRows = @()
                foreach ($sessionId in @($sessionIds)) {
                    $terminalRows += @(
                        Get-SsmSessionHistoryById -SessionId $sessionId |
                            Where-Object {
                                [string]$_.SessionId -eq $sessionId -and
                                [string]$_.Status -eq 'Terminated' -and
                                $null -ne $_.EndDate
                            }
                    )
                }
                $sessionTerminalObserved = (
                    $sessionIds.Count -gt 0 -and $terminalRows.Count -eq $sessionIds.Count
                )
                $rootActive = Test-ProcessIdentityActive `
                    -ProcessId ([int]$record.ProcessId) `
                    -StartTimeUtcTicks ([long]$record.ProcessStartTimeUtcTicks) `
                    -ExpectedName 'aws'
                $childActive = @(
                    $record.ChildProcesses | Where-Object {
                        Test-ProcessIdentityActive `
                            -ProcessId ([int]$_.ProcessId) `
                            -StartTimeUtcTicks ([long]$_.StartTimeUtcTicks) `
                            -ExpectedName ([string]$_.ProcessName)
                    }
                ).Count -ne 0
                $processTreeClosedObserved = (
                    [bool]$record.DescendantTrackingEstablished -and
                    -not $rootActive -and
                    -not $childActive
                )
                $localPortClosedObserved = Test-LocalPortClosed -LocalPort ([int]$record.LocalPort)
                $lastPollError = ''
            }
            catch {
                $lastPollError = Protect-Diagnostic $_.Exception.Message
                $sessionTerminalObserved = $false
                $processTreeClosedObserved = $false
                $localPortClosedObserved = $false
            }
            if ($sessionTerminalObserved -and $processTreeClosedObserved -and $localPortClosedObserved) { break }
            Start-Sleep -Seconds 2
        } while ([DateTimeOffset]::UtcNow -lt $deadline)

        if ($lastPollError) { $recordErrors.Add($lastPollError) }
        if (-not $sessionTerminalObserved) {
            if ($sessionIds.Count -eq 0) {
                $recordErrors.Add('The launched SSM session identifier remained unbound after repeated reconciliation.')
            }
            $recordErrors.Add('The exact SSM session was not observed in Terminated history with an end timestamp.')
        }
        if (-not $processTreeClosedObserved) {
            $recordErrors.Add('The exact AWS CLI or Session Manager plugin process identity remained active.')
        }
        if (-not $localPortClosedObserved) {
            $recordErrors.Add('The approved local port did not have a fail-closed no-listener observation.')
        }
        foreach ($message in @($recordErrors)) {
            $allErrors.Add("$([string]$record.EndpointRef): $message")
        }
        $results += [pscustomobject]@{
            EndpointRef = [string]$record.EndpointRef
            SessionIds = @($sessionIds)
            TerminateResponsesObserved = $terminateResponsesObserved
            SessionTerminalObserved = $sessionTerminalObserved
            ProcessTreeClosedObserved = $processTreeClosedObserved
            LocalPortClosedObserved = $localPortClosedObserved
        }
        $script:tunnelCleanupObservations[[string]$record.EndpointRef] = $results[-1]
        if (
            $recordErrors.Count -ne 0 -or
            -not $sessionTerminalObserved -or
            -not $processTreeClosedObserved -or
            -not $localPortClosedObserved
        ) {
            $remainingRecords += $record
        }
        elseif ($null -ne $record.ProcessObject) {
            $record.ProcessObject.Dispose()
            $record['ProcessObject'] = $null
        }
    }
    $script:tunnelRecords = @($remainingRecords)
    $summaryRecords = @($script:tunnelCleanupObservations.Values)
    $result = [pscustomobject]@{
        Records = $summaryRecords
        Errors = @($allErrors)
        SsmSessionsClosedObserved = @($summaryRecords | Where-Object { $_.SessionTerminalObserved }).Count
        ProcessTreesClosedObserved = @($summaryRecords | Where-Object { $_.ProcessTreeClosedObserved }).Count
        LocalPortsClosedObserved = @($summaryRecords | Where-Object { $_.LocalPortClosedObserved }).Count
        TerminateResponsesObserved = ($summaryRecords | Measure-Object -Property TerminateResponsesObserved -Sum).Sum
    }
    $script:lastTunnelCleanupResult = $result
    return $result
}

function Invoke-ConfiguredEndpointCleanup {
    if ($script:configuredSessions.Count -eq 0) {
        $script:remoteCleanupCompleted = $true
        return
    }
    if ([string]::IsNullOrWhiteSpace([string]$script:removeScriptHash)) {
        throw 'Remote cleanup cannot verify the approved cleanup script hash.'
    }
    $cleanupErrors = [Collections.Generic.List[string]]::new()
    foreach ($configured in @($script:configuredSessions)) {
        $endpointRef = [string]$configured.EndpointRef
        if ($script:remoteCleanupCompletedRefs.ContainsKey($endpointRef)) { continue }
        try {
            $cleanupCommands = @(
                "`$ErrorActionPreference = 'Stop'",
                "if ((Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\ProgramData\JCareerLab\Remove-JCareerSession.ps1').Hash.ToLowerInvariant() -ne '$($script:removeScriptHash)') { throw 'cleanup script hash mismatch' }",
                "& 'C:\ProgramData\JCareerLab\Remove-JCareerSession.ps1' -SessionRef '$([string]$configured.SessionRef)'"
            )
            $cleanupOutput = Invoke-RemotePowerShell `
                -InstanceId ([string]$configured.InstanceId) `
                -Commands $cleanupCommands `
                -Comment "Remove approved J-Career session $endpointRef"
            if (
                $cleanupOutput -notmatch 'JCAREER_SESSION_REMOVED=PASS' -or
                $cleanupOutput -notmatch 'JCAREER_WINDOWS_OS_SHUTDOWN=SCHEDULED_30_SECONDS'
            ) {
                throw "Remote session cleanup markers were not observed for $endpointRef."
            }
            $script:remoteCleanupCompletedRefs[$endpointRef] = $true
        }
        catch {
            $cleanupErrors.Add("${endpointRef}: $(Protect-Diagnostic $_.Exception.Message)")
        }
    }
    $script:remoteCleanupCompleted = (
        $script:remoteCleanupCompletedRefs.Count -eq $script:configuredSessions.Count
    )
    if ($cleanupErrors.Count -gt 0 -or -not $script:remoteCleanupCompleted) {
        throw ('Remote cleanup was not observed for every configured endpoint: ' + ($cleanupErrors -join ' | '))
    }
}

$trustedPowerShellCommands = @{
    'ConvertFrom-Json' = @('Cmdlet', 'Microsoft.PowerShell.Utility')
    'ConvertTo-Json' = @('Cmdlet', 'Microsoft.PowerShell.Utility')
    'ForEach-Object' = @('Cmdlet', 'Microsoft.PowerShell.Core')
    'Get-Acl' = @('Cmdlet', 'Microsoft.PowerShell.Security')
    'Get-Content' = @('Cmdlet', 'Microsoft.PowerShell.Management')
    'Get-FileHash' = @('Function', 'Microsoft.PowerShell.Utility')
    'Join-Path' = @('Cmdlet', 'Microsoft.PowerShell.Management')
    'Measure-Object' = @('Cmdlet', 'Microsoft.PowerShell.Utility')
    'New-Item' = @('Cmdlet', 'Microsoft.PowerShell.Management')
    'Out-Null' = @('Cmdlet', 'Microsoft.PowerShell.Core')
    'Read-Host' = @('Cmdlet', 'Microsoft.PowerShell.Utility')
    'Remove-Item' = @('Cmdlet', 'Microsoft.PowerShell.Management')
    'Resolve-Path' = @('Cmdlet', 'Microsoft.PowerShell.Management')
    'Select-Object' = @('Cmdlet', 'Microsoft.PowerShell.Utility')
    'Set-Acl' = @('Cmdlet', 'Microsoft.PowerShell.Security')
    'Set-StrictMode' = @('Cmdlet', 'Microsoft.PowerShell.Core')
    'Sort-Object' = @('Cmdlet', 'Microsoft.PowerShell.Utility')
    'Start-Sleep' = @('Cmdlet', 'Microsoft.PowerShell.Utility')
    'Test-Path' = @('Cmdlet', 'Microsoft.PowerShell.Management')
    'Where-Object' = @('Cmdlet', 'Microsoft.PowerShell.Core')
    'Write-Output' = @('Cmdlet', 'Microsoft.PowerShell.Utility')
    'Write-Warning' = @('Cmdlet', 'Microsoft.PowerShell.Utility')
}
foreach ($entry in $trustedPowerShellCommands.GetEnumerator()) {
    $resolvedCommand = @(
        Microsoft.PowerShell.Core\Get-Command ([string]$entry.Key) -All -ErrorAction Stop
    )[0]
    if (
        [string]$resolvedCommand.CommandType -ne [string]$entry.Value[0] -or
        [string]$resolvedCommand.ModuleName -ne [string]$entry.Value[1]
    ) {
        throw "A required PowerShell command is shadowed: $($entry.Key)"
    }
}

$awsCommand = Microsoft.PowerShell.Core\Get-Command 'aws.exe' -CommandType Application -ErrorAction Stop |
    Select-Object -First 1
$terraformCommand = Microsoft.PowerShell.Core\Get-Command 'terraform.exe' -CommandType Application -ErrorAction Stop |
    Select-Object -First 1
$pythonCommand = Microsoft.PowerShell.Core\Get-Command 'python.exe' -CommandType Application -ErrorAction Stop |
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
    throw 'AWS CLI v2 is required for consultant-session timestamp and plugin behavior.'
}
$awsExecutable = $script:awsExecutable
if ($OpenInteractiveTunnels) {
    if (-not (Microsoft.PowerShell.Core\Get-Command 'session-manager-plugin.exe' -CommandType Application -ErrorAction SilentlyContinue)) {
        throw 'Session Manager plugin is required for interactive RDP tunnels.'
    }
    $mstscCommand = Microsoft.PowerShell.Core\Get-Command 'mstsc.exe' -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $mstscCommand) {
        throw 'Windows Remote Desktop client is required for interactive tunnels.'
    }
    $script:mstscExecutable = [IO.Path]::GetFullPath([string]$mstscCommand.Source)
    if (-not (Microsoft.PowerShell.Core\Get-Command 'Microsoft.PowerShell.Management\Set-Clipboard' -CommandType Cmdlet -ErrorAction SilentlyContinue)) {
        throw 'Set-Clipboard is required for one-time preview bootstrap delivery.'
    }
    foreach ($command in @('NetTCPIP\Get-NetTCPConnection', 'CimCmdlets\Get-CimInstance')) {
        if (-not (Microsoft.PowerShell.Core\Get-Command $command -ErrorAction SilentlyContinue)) {
            throw "$command is required for fail-closed interactive tunnel cleanup."
        }
    }
}

try {
    New-Item -ItemType Directory -Path $taskTemporary | Out-Null
    $script:protectedSnapshotDirectory = Join-Path $taskTemporary 'protected-inputs'
    New-ProtectedDirectory -Path $script:protectedSnapshotDirectory
    $backendSource = (Resolve-Path $BackendConfig).Path
    $approvalSource = (Resolve-Path $ApprovalFile).Path
    $endpointReceiptSource = (Resolve-Path $EndpointApplyReceipt).Path
    $imageReceiptSource = (Resolve-Path $ImageReceipt).Path
    $buildObservationSource = (Resolve-Path $BuildObservation).Path
    $resolvedBackend = Copy-ProtectedStableFile -Source $backendSource -DestinationName 'backend.hcl'
    $resolvedApproval = Copy-ProtectedStableFile -Source $approvalSource -DestinationName 'approval.json'
    $resolvedEndpointReceipt = Copy-ProtectedStableFile -Source $endpointReceiptSource -DestinationName 'endpoint-apply-receipt.json'
    $resolvedImageReceipt = Copy-ProtectedStableFile -Source $imageReceiptSource -DestinationName 'image-receipt.json'
    $resolvedBuildObservation = Copy-ProtectedStableFile -Source $buildObservationSource -DestinationName 'build-observation.json'
    $configureScript = Copy-ProtectedStableFile -Source $configureScriptSource -DestinationName 'Configure-JCareerSession.ps1'
    $removeScript = Copy-ProtectedStableFile -Source $removeScriptSource -DestinationName 'Remove-JCareerSession.ps1'
    $backendChecker = Copy-ProtectedStableFile -Source $backendCheckerSource -DestinationName 'check_terraform_backend_config.py'
    $approvalChecker = Copy-ProtectedStableFile -Source $approvalCheckerSource -DestinationName 'check_windows_endpoint_session_approval.py'
    if ($script:protectedSnapshotCount -ne 9) {
        throw 'The protected consultant-session input snapshot set is incomplete.'
    }
    $backendSource = $null
    $approvalSource = $null
    $endpointReceiptSource = $null
    $imageReceiptSource = $null
    $buildObservationSource = $null
    $configureScriptSource = $null
    $removeScriptSource = $null
    $backendCheckerSource = $null
    $approvalCheckerSource = $null
    $previewBootstrapTokenHash = Get-SecureStringSha256 -Secret $PreviewBootstrapToken
    $canonicalBackendOutput = @(
        & $script:pythonExecutable $backendChecker `
            --config $resolvedBackend --terraform-root workplace-endpoints `
            --print-canonical-sha256 2>&1
    )
    $canonicalBackendHash = ($canonicalBackendOutput -join '').Trim()
    if ($LASTEXITCODE -ne 0 -or $canonicalBackendHash -notmatch '^[0-9a-f]{64}$') {
        throw 'Endpoint logical backend identity could not be derived.'
    }
    & $script:pythonExecutable $approvalChecker `
        --approval $resolvedApproval `
        --endpoint-backend-config $resolvedBackend `
        --endpoint-apply-receipt $resolvedEndpointReceipt `
        --image-receipt $resolvedImageReceipt `
        --build-observation $resolvedBuildObservation `
        --preview-url $PreviewUrl `
        --preview-bootstrap-token-sha256 $previewBootstrapTokenHash `
        --configure-script $configureScript `
        --remove-script $removeScript `
        --require-approved
    if ($LASTEXITCODE -ne 0) { throw 'Consultant session approval did not match the exact inputs.' }

    $approval = Get-Content -LiteralPath $resolvedApproval -Raw -Encoding UTF8 | ConvertFrom-Json
    $imageReceiptDocument = Get-Content -LiteralPath $resolvedImageReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
    if ([int]$approval.max_sessions -ne 3 -or @($approval.sessions).Count -ne 3) {
        throw 'The protected approval snapshot does not contain exactly three sessions.'
    }
    $previewHash = Get-Sha256Text $PreviewUrl
    $configureHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $configureScript).Hash.ToLowerInvariant()
    $removeHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $removeScript).Hash.ToLowerInvariant()
    $script:removeScriptHash = $removeHash

    New-Item -ItemType Directory -Path $workDirectory -Force | Out-Null
    $approvalFileHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedApproval).Hash.ToLowerInvariant()
    $script:approvalFileSha256 = $approvalFileHash
    $script:approvalLeaseName = 'Global\JCareerConsultantSession-' + $canonicalBackendHash
    $createdNew = $false
    try {
        $script:approvalLeaseMutex = [Threading.Mutex]::new(
            $false, $script:approvalLeaseName, [ref]$createdNew
        )
        try { $script:approvalLeaseAcquired = $script:approvalLeaseMutex.WaitOne(0) }
        catch [Threading.AbandonedMutexException] { $script:approvalLeaseAcquired = $true }
        if (-not $script:approvalLeaseAcquired) {
            throw 'The endpoint-backend lease is already held.'
        }
    }
    catch {
        if ($null -ne $script:approvalLeaseMutex) {
            $script:approvalLeaseMutex.Dispose()
            $script:approvalLeaseMutex = $null
        }
        throw 'Another local consultant-session operator holds the shared endpoint-backend lease.'
    }
    if (Test-Path -LiteralPath $observationFile -PathType Leaf) {
        throw 'A prior consultant-session observation must be retained or dispositioned by a person before another run can use this worktree.'
    }

    $init = @(& $script:terraformExecutable -chdir=$terraformRelative init -reconfigure -input=false "-backend-config=$resolvedBackend" 2>&1)
    if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($init -join "`n")) }
    $rawIds = @(& $script:terraformExecutable -chdir=$terraformRelative output -json endpoint_instance_ids 2>&1)
    if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($rawIds -join "`n")) }
    $instanceIds = @(($rawIds -join "`n") | ConvertFrom-Json)
    if ($instanceIds.Count -ne 3 -or @($instanceIds | Where-Object { $_ -notmatch '^i-[0-9a-f]+$' }).Count -ne 0) {
        throw 'Endpoint state did not resolve to exactly three EC2 instances.'
    }
    $rawSecurityGroup = @(& $script:terraformExecutable -chdir=$terraformRelative output -raw endpoint_security_group_id 2>&1)
    if ($LASTEXITCODE -ne 0) { throw (Protect-Diagnostic ($rawSecurityGroup -join "`n")) }
    $endpointSecurityGroupId = (($rawSecurityGroup -join '').Trim())
    if ($endpointSecurityGroupId -notmatch '^sg-[0-9a-f]+$') {
        throw 'Endpoint state did not resolve to one security group.'
    }

    $securityGroupDocument = Invoke-AwsJson @(
        'ec2', 'describe-security-groups', '--region', 'ap-northeast-2',
        '--group-ids', $endpointSecurityGroupId, '--output', 'json', '--no-cli-pager'
    )
    $securityGroups = @($securityGroupDocument.SecurityGroups)
    if ($securityGroups.Count -ne 1 -or @($securityGroups[0].IpPermissions).Count -ne 0) {
        throw 'The endpoint security group does not have exactly zero ingress permissions.'
    }

    $instanceDocument = Invoke-AwsJson (@(
        'ec2', 'describe-instances', '--region', 'ap-northeast-2', '--instance-ids'
    ) + $instanceIds + @('--output', 'json', '--no-cli-pager'))
    $instances = @($instanceDocument.Reservations | ForEach-Object { $_.Instances })
    if ($instances.Count -ne 3) { throw 'AWS did not return exactly three endpoint instances.' }

    $observations = @()
    foreach ($session in @($approval.sessions)) {
        Assert-SessionApprovalActive -Approval $approval
        $endpointRef = [string]$session.endpoint_ref
        $matching = @($instances | Where-Object {
            $tags = @{}
            foreach ($tag in @($_.Tags)) { $tags[[string]$tag.Key] = [string]$tag.Value }
            $tags['jk_endpoint_ref'] -eq $endpointRef
        })
        if ($matching.Count -ne 1) { throw "Endpoint lineage did not resolve once for $endpointRef." }
        $instance = $matching[0]
        $attachedSecurityGroups = @($instance.SecurityGroups)
        if (
            $attachedSecurityGroups.Count -ne 1 -or
            [string]$attachedSecurityGroups[0].GroupId -ne $endpointSecurityGroupId
        ) {
            throw "Endpoint does not have exactly the Terraform-bound security group for $endpointRef."
        }
        $instanceTags = @{}
        foreach ($tag in @($instance.Tags)) { $instanceTags[[string]$tag.Key] = [string]$tag.Value }
        if (
            [string]$instance.State.Name -ne 'running' -or
            [string]$instance.InstanceType -ne 't3.small' -or
            [string]$instance.ImageId -ne [string]$imageReceiptDocument.ami_id -or
            $instanceTags['jk_image_build_ref'] -ne [string]$imageReceiptDocument.image_build_ref -or
            $instanceTags['jk_os_contract'] -ne 'windows-server-desktop-simulation' -or
            $instanceTags['jk_access'] -ne 'ssm-only-no-inbound'
        ) {
            throw "Endpoint runtime lineage or state failed for $endpointRef."
        }
        $instanceId = [string]$instance.InstanceId
        $ssm = Invoke-AwsJson @(
            'ssm', 'describe-instance-information', '--region', 'ap-northeast-2',
            '--filters', "Key=InstanceIds,Values=$instanceId", '--output', 'json', '--no-cli-pager'
        )
        $managed = @($ssm.InstanceInformationList)
        if (
            $managed.Count -ne 1 -or
            [string]$managed[0].PingStatus -ne 'Online' -or
            [string]$managed[0].PlatformType -ne 'Windows' -or
            [string]::IsNullOrWhiteSpace([string]$managed[0].AgentVersion)
        ) {
            throw "Endpoint is not one online Windows managed node for $endpointRef."
        }

        $urlBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($PreviewUrl))
        $expiryBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes([string]$approval.session_expires_at))
        $remoteCommands = @(
            "`$ErrorActionPreference = 'Stop'",
            "if ((Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\ProgramData\JCareerLab\Configure-JCareerSession.ps1').Hash.ToLowerInvariant() -ne '$configureHash') { throw 'configure script hash mismatch' }",
            "if ((Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\ProgramData\JCareerLab\Remove-JCareerSession.ps1').Hash.ToLowerInvariant() -ne '$removeHash') { throw 'cleanup script hash mismatch' }",
            "foreach (`$serviceName in @('AmazonSSMAgent','TermService')) { if ((Get-Service -Name `$serviceName -ErrorAction Stop).Status -ne 'Running') { throw 'required service not running' } }",
            "if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port 3389 -InformationLevel Quiet)) { throw 'RDP loopback unavailable' }",
            "if ((Get-NetFirewallProfile).Enabled -contains `$false) { throw 'firewall profile disabled' }",
            "if (-not (Get-MpComputerStatus).RealTimeProtectionEnabled) { throw 'Defender real-time protection disabled' }",
            "`$edgeCandidates = @(`"`$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe`", `"`${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe`")",
            "`$edge = @(`$edgeCandidates | Where-Object { Test-Path -LiteralPath `$_ } | Select-Object -Unique)",
            "if (`$edge.Count -lt 1) { throw 'Microsoft Edge unavailable' }",
            "`$edgeSignature = Get-AuthenticodeSignature -LiteralPath `$edge[0]",
            "if (`$edgeSignature.Status -ne 'Valid' -or `$null -eq `$edgeSignature.SignerCertificate -or [string]`$edgeSignature.SignerCertificate.Subject -notmatch '(^|,\s*)O=Microsoft Corporation(,|$)') { throw 'Microsoft Edge publisher signature invalid' }",
            "`$url = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$urlBase64'))",
            "`$expiry = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$expiryBase64'))",
            "& 'C:\ProgramData\JCareerLab\Configure-JCareerSession.ps1' -PreviewUrl `$url -ApprovedPreviewUrlSha256 '$previewHash' -SessionRef '$([string]$session.session_ref)' -EndpointRef '$endpointRef' -ExpiresAt `$expiry",
            "Write-Output ('SESSION_JSON_SHA256=' + (Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\ProgramData\JCareerLab\session.json').Hash.ToLowerInvariant())"
        )
        $script:configuredSessions += [ordered]@{
            InstanceId = $instanceId
            SessionRef = [string]$session.session_ref
            EndpointRef = $endpointRef
        }
        $remoteOutput = Invoke-RemotePowerShell -InstanceId $instanceId `
            -Commands $remoteCommands -Comment "Configure approved J-Career session $endpointRef"
        $sessionHashMatch = [regex]::Match($remoteOutput, 'SESSION_JSON_SHA256=([0-9a-f]{64})')
        if (-not $sessionHashMatch.Success) { throw "Session receipt hash was not observed for $endpointRef." }
        $script:configurationReceiptsObservedRefs[$endpointRef] = $true
        $observations += [ordered]@{
            endpoint_ref = $endpointRef
            session_ref = [string]$session.session_ref
            instance_id_sha256 = Get-Sha256Text $instanceId
            ssm_online_observed = $true
            ssm_agent_version_sha256 = Get-Sha256Text ([string]$managed[0].AgentVersion)
            rdp_loopback_observed = $true
            firewall_profiles_enabled_observed = $true
            defender_realtime_observed = $true
            microsoft_edge_signature_observed = $true
            security_group_exact_match_observed = $true
            session_json_sha256 = $sessionHashMatch.Groups[1].Value
            local_port = [int]$session.local_port
        }
    }

    $receipt = [ordered]@{
        schema_version = 'jcareer-windows-consultant-session-observation-v1'
        scope = 'workplace-windows-consultant-session'
        approval_ref = [string]$approval.approval_ref
        approval_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedApproval).Hash.ToLowerInvariant()
        image_build_ref = [string]$imageReceiptDocument.image_build_ref
        os_contract = 'WINDOWS_SERVER_2022_DESKTOP_SIMULATION'
        preview_url_sha256 = $previewHash
        preview_bootstrap_token_sha256 = $previewBootstrapTokenHash
        bootstrap_delivery_method = 'RDP_CLIPBOARD_ONE_TIME'
        endpoint_security_group_id_sha256 = Get-Sha256Text $endpointSecurityGroupId
        endpoint_security_group_ingress_permissions_observed = 0
        configure_script_sha256 = $configureHash
        remove_script_sha256 = $removeHash
        configured_at = [DateTimeOffset]::UtcNow.ToString('o')
        expires_at = [string]$approval.session_expires_at
        endpoints = $observations
        interactive_tunnels_requested = [bool]$OpenInteractiveTunnels
        clipboard_bootstrap_deliveries_observed = 0
        tunnels_closed_observed = $false
        ssm_sessions_closed_observed = 0
        tunnel_process_trees_closed_observed = 0
        local_ports_closed_observed = 0
        ssm_terminate_responses_observed = 0
        tunnel_closure_observations = @()
        remote_cleanup_command_observed = $false
        gui_login_observed = $false
        preview_https_observed = $false
        credentials_included = $false
        raw_identifiers_included = $false
        synthetic_data_only = $true
        protected_input_snapshot_count = $script:protectedSnapshotCount
        local_snapshot_cleanup_observed = $false
        local_task_temporary_cleanup_observed = $false
    }
    if ($OpenInteractiveTunnels) {
        $callerIdentity = Invoke-AwsJson @(
            'sts', 'get-caller-identity', '--output', 'json', '--no-cli-pager'
        )
        $expectedSessionOwner = [string]$callerIdentity.Arn
        if ([string]::IsNullOrWhiteSpace($expectedSessionOwner)) {
            throw 'The AWS caller identity could not be bound to interactive SSM sessions.'
        }
        foreach ($session in @($approval.sessions)) {
            Assert-SessionApprovalActive -Approval $approval
            $endpointRef = [string]$session.endpoint_ref
            $instance = @($instances | Where-Object {
                @($_.Tags | Where-Object { $_.Key -eq 'jk_endpoint_ref' -and $_.Value -eq $endpointRef }).Count -eq 1
            })[0]
            if (-not (Test-LocalPortClosed -LocalPort ([int]$session.local_port))) {
                throw "The approved local port was already listening before launch for $endpointRef."
            }
            $parameters = "portNumber=3389,localPortNumber=$([int]$session.local_port)"
            $launchReason = '{0}:{1}' -f [string]$session.session_ref, [Guid]::NewGuid().ToString('N')
            $arguments = @(
                'ssm', 'start-session', '--region', 'ap-northeast-2',
                '--target', [string]$instance.InstanceId,
                '--document-name', 'AWS-StartPortForwardingSession',
                '--parameters', $parameters,
                '--reason', $launchReason
            )
            $priorSessions = @(
                Get-ActiveSsmSessions -Target ([string]$instance.InstanceId)
                Get-HistoricalSsmSessions -Target ([string]$instance.InstanceId)
            )
            $reasonPrefix = ([string]$session.session_ref) + ':'
            $priorApprovalSessions = @($priorSessions | Where-Object {
                [string]$_.Target -eq [string]$instance.InstanceId -and
                [string]$_.Owner -eq $expectedSessionOwner -and
                [string]$_.DocumentName -eq 'AWS-StartPortForwardingSession' -and
                (
                    [string]$_.Reason -eq [string]$session.session_ref -or
                    [string]$_.Reason -like ($reasonPrefix + '*')
                )
            })
            if ($priorApprovalSessions.Count -ne 0) {
                throw "The approved session reference was already observed for $endpointRef."
            }
            $priorSessionIds = @($priorSessions | ForEach-Object { [string]$_.SessionId })
            $launchedAt = [DateTimeOffset]::UtcNow
            $process = $null
            $recordRegistered = $false
            try {
                $process = Microsoft.PowerShell.Management\Start-Process -FilePath $awsExecutable -ArgumentList $arguments -WindowStyle Normal -PassThru
                $bindingDeadline = $launchedAt.AddSeconds(45)
                $record = [ordered]@{
                    EndpointRef = $endpointRef
                    InstanceId = [string]$instance.InstanceId
                    SessionRef = [string]$session.session_ref
                    LaunchReason = $launchReason
                    ExpectedOwner = $expectedSessionOwner
                    PriorSessionIds = @($priorSessionIds)
                    LaunchedAt = $launchedAt
                    BindingDeadline = $bindingDeadline
                    ProcessId = [int]$process.Id
                    ProcessStartTimeUtcTicks = 0
                    ProcessObject = $process
                    DescendantTrackingEstablished = $false
                    ChildProcesses = @()
                    PluginProcesses = @()
                    SessionId = ''
                    LocalPort = [int]$session.local_port
                }
                $script:tunnelRecords += $record
                $recordRegistered = $true
                $record['ProcessStartTimeUtcTicks'] = [long]$process.StartTime.ToUniversalTime().Ticks
            }
            catch {
                $launchError = $_.Exception
                if (-not $recordRegistered -and $null -ne $process) {
                    try {
                        $retainedHandle = $process.SafeHandle
                        if (-not $retainedHandle.IsInvalid -and -not $process.HasExited) {
                            $process.Kill()
                            [void]$process.WaitForExit(5000)
                        }
                    }
                    finally { $process.Dispose() }
                }
                throw $launchError
            }
            $deadline = $bindingDeadline
            $ready = $false
            do {
                Start-Sleep -Seconds 2
                if (-not (Test-ProcessIdentityActive `
                    -ProcessId ([int]$record.ProcessId) `
                    -StartTimeUtcTicks ([long]$record.ProcessStartTimeUtcTicks) `
                    -ExpectedName 'aws')) {
                    throw "The AWS CLI session process exited before tunnel binding for $endpointRef."
                }
                $newSessions = @(Get-RecordSsmSessions -Record $record)
                if ($newSessions.Count -gt 1) {
                    throw "More than one active SSM session matched the launch for $endpointRef."
                }
                if ($newSessions.Count -eq 1) {
                    $record['SessionId'] = [string]$newSessions[0].SessionId
                }
                Update-TrackedProcessDescendants -Record $record
                $pluginProcesses = @($record.PluginProcesses | Where-Object {
                    Test-ProcessIdentityActive `
                        -ProcessId ([int]$_.ProcessId) `
                        -StartTimeUtcTicks ([long]$_.StartTimeUtcTicks) `
                        -ExpectedName 'session-manager-plugin'
                })
                $listeners = @(Get-LocalPortListeners -LocalPort ([int]$session.local_port))
                $listenerProcessIds = @($listeners | ForEach-Object { [int]$_.OwningProcess } | Sort-Object -Unique)
                $pluginProcessIds = @($pluginProcesses | ForEach-Object { [int]$_.ProcessId })
                $listenersWithoutExactPluginIdentity = @($listeners | Where-Object {
                    $listenerProcessId = [int]$_.OwningProcess
                    $matches = @($pluginProcesses | Where-Object {
                        [int]$_.ProcessId -eq $listenerProcessId -and
                        (Test-ProcessIdentityActive `
                            -ProcessId ([int]$_.ProcessId) `
                            -StartTimeUtcTicks ([long]$_.StartTimeUtcTicks) `
                            -ExpectedName 'session-manager-plugin')
                    })
                    $matches.Count -ne 1
                })
                $listenerOwnershipBound = (
                    $listenerProcessIds.Count -gt 0 -and
                    @($listenerProcessIds | Where-Object { $_ -notin $pluginProcessIds }).Count -eq 0 -and
                    $listenersWithoutExactPluginIdentity.Count -eq 0 -and
                    @($listeners | Where-Object {
                        [string]$_.LocalAddress -notin @('127.0.0.1', '::1')
                    }).Count -eq 0
                )
                $ready = (
                    [string]$record.SessionId -and
                    $pluginProcesses.Count -gt 0 -and
                    $listenerOwnershipBound
                )
            } while (-not $ready -and [DateTimeOffset]::UtcNow -lt $deadline)
            if (-not $ready) { throw "SSM RDP tunnel did not become ready for $endpointRef." }
            Microsoft.PowerShell.Management\Start-Process -FilePath $script:mstscExecutable -ArgumentList "/v:127.0.0.1:$([int]$session.local_port)", '/prompt'
            try {
                Set-OneTimePreviewBootstrapClipboard `
                    -Secret $PreviewBootstrapToken -CleanPreviewUrl $PreviewUrl
                Write-Output "One-time preview bootstrap URL is on the local clipboard for $endpointRef."
                $bootstrapConfirmation = Read-Host `
                    "Paste it once into the Edge address bar for $endpointRef, then type BOOTSTRAP_PASTED"
                if ($bootstrapConfirmation -cne 'BOOTSTRAP_PASTED') {
                    throw "One-time bootstrap delivery was not confirmed for $endpointRef."
                }
                $receipt['clipboard_bootstrap_deliveries_observed'] =
                    [int]$receipt['clipboard_bootstrap_deliveries_observed'] + 1
            }
            finally {
                Clear-PreviewBootstrapClipboard
            }
        }
        Write-Output 'WINDOWS_ENDPOINT_TUNNELS=OPENED_THREE_INTERACTIVE'
        Write-Output 'Use only the separately controlled EC2 Windows credential; no password was created or printed.'
        $closeConfirmation = Read-Host `
            'Close all three RDP clients, then type CLOSE_AND_CLEANUP to stop tunnels and clean the endpoints'
        if ($closeConfirmation -cne 'CLOSE_AND_CLEANUP') {
            throw 'Interactive endpoint closure was not confirmed.'
        }
        $closeResult = Stop-EndpointTunnels
        if (@($closeResult.Errors).Count -ne 0) {
            throw ('Tunnel cleanup observations failed closed: ' + (@($closeResult.Errors) -join ' | '))
        }
        if (
            [int]$closeResult.SsmSessionsClosedObserved -ne 3 -or
            [int]$closeResult.ProcessTreesClosedObserved -ne 3 -or
            [int]$closeResult.LocalPortsClosedObserved -ne 3
        ) {
            throw 'Exactly three approved SSM tunnel close postconditions were not observed.'
        }
        $receipt['tunnels_closed_observed'] = $true
        $receipt['ssm_sessions_closed_observed'] = [int]$closeResult.SsmSessionsClosedObserved
        $receipt['tunnel_process_trees_closed_observed'] = [int]$closeResult.ProcessTreesClosedObserved
        $receipt['local_ports_closed_observed'] = [int]$closeResult.LocalPortsClosedObserved
        $receipt['ssm_terminate_responses_observed'] = [int]$closeResult.TerminateResponsesObserved
        $receipt['tunnel_closure_observations'] = @(
            $closeResult.Records | ForEach-Object {
                [ordered]@{
                    endpoint_ref = [string]$_.EndpointRef
                    session_id_sha256 = if (@($_.SessionIds).Count -eq 1) {
                        Get-Sha256Text ([string]$_.SessionIds[0])
                    } else { '' }
                    ssm_terminal_history_observed = [bool]$_.SessionTerminalObserved
                    process_tree_closed_observed = [bool]$_.ProcessTreeClosedObserved
                    local_port_closed_observed = [bool]$_.LocalPortClosedObserved
                }
            }
        )
        Invoke-ConfiguredEndpointCleanup
        $receipt['remote_cleanup_command_observed'] = $true
        Write-Output 'WINDOWS_ENDPOINT_INTERACTIVE_CLEANUP=THREE_COMMANDS_OBSERVED'
    }
    else {
        Write-Output 'WINDOWS_ENDPOINT_SESSION_CONFIGURED=THREE_READY_FOR_APPROVED_SSM_TUNNELS'
    }
    Write-Output 'GUI login and preview HTTPS remain NOT_OBSERVED until a consultant records a separate human observation.'
    Remove-ProtectedInputSnapshots
    $receipt['local_snapshot_cleanup_observed'] = $true
    Remove-TaskTemporaryDirectory
    $script:localTaskTemporaryCleanupObserved = $true
    $receipt['local_task_temporary_cleanup_observed'] = $true
    if (Test-Path -LiteralPath $failureObservationFile -PathType Leaf) {
        Remove-Item -LiteralPath $failureObservationFile -Force
    }
    New-Item -ItemType Directory -Path $workDirectory -Force | Out-Null
    Write-JsonUtf8NoBom -Path $observationFile -Value $receipt
    $script:completed = $true
}
finally {
    try {
        $failSafeTunnelResult = Stop-EndpointTunnels
        if (@($failSafeTunnelResult.Errors).Count -ne 0) {
            throw (@($failSafeTunnelResult.Errors) -join ' | ')
        }
    }
    catch {
        Write-Warning ('Fail-safe tunnel cleanup was not fully observed: ' + (Protect-Diagnostic $_.Exception.Message))
    }
    if (
        -not $script:completed -and
        -not $script:remoteCleanupCompleted -and
        $script:configuredSessions.Count -gt 0
    ) {
        try { Invoke-ConfiguredEndpointCleanup }
        catch {
            Write-Warning ('Fail-safe remote cleanup was not fully observed: ' + (Protect-Diagnostic $_.Exception.Message))
        }
    }
    if (-not $script:localSnapshotCleanupObserved) {
        try { Remove-ProtectedInputSnapshots }
        catch {
            $script:localSnapshotCleanupRetryRequired = $true
            Write-Warning 'Protected input snapshot cleanup was not fully observed.'
        }
    }
    if (-not $script:localTaskTemporaryCleanupObserved) {
        try {
            Remove-TaskTemporaryDirectory
            $script:localTaskTemporaryCleanupObserved = $true
            $script:localTaskTemporaryCleanupRetryRequired = $false
        }
        catch {
            $script:localTaskTemporaryCleanupRetryRequired = $true
            Write-Warning 'Temporary session artifact cleanup was not fully observed.'
        }
    }
    if (-not $script:completed) {
        try {
            New-Item -ItemType Directory -Path $workDirectory -Force | Out-Null
            $lastCleanup = $script:lastTunnelCleanupResult
            $cleanupRetryRequired = (
                @($script:tunnelRecords).Count -gt 0 -or
                (
                    $script:configuredSessions.Count -gt 0 -and
                    -not $script:remoteCleanupCompleted
                ) -or
                $script:localSnapshotCleanupRetryRequired -or
                $script:localTaskTemporaryCleanupRetryRequired
            )
            $failureObservation = [ordered]@{
                schema_version = 'jcareer-windows-consultant-session-failure-observation-v1'
                scope = 'workplace-windows-consultant-session'
                operation_state = 'OPERATION_FAILED'
                cleanup_state = if ($cleanupRetryRequired) {
                    'CLEANUP_RETRY_REQUIRED'
                } elseif (
                    @($script:tunnelRecords).Count -eq 0 -and
                    $script:configuredSessions.Count -eq 0
                ) {
                    'NO_CLEANUP_REQUIRED'
                } else { 'CLEANUP_OBSERVED_COMPLETE' }
                approval_sha256 = $script:approvalFileSha256
                observed_at = [DateTimeOffset]::UtcNow.ToString('o')
                tunnel_records_remaining = @($script:tunnelRecords).Count
                ssm_sessions_closed_observed = if ($null -ne $lastCleanup) {
                    [int]$lastCleanup.SsmSessionsClosedObserved
                } else { 0 }
                tracked_process_trees_closed_observed = if ($null -ne $lastCleanup) {
                    [int]$lastCleanup.ProcessTreesClosedObserved
                } else { 0 }
                local_ports_closed_observed = if ($null -ne $lastCleanup) {
                    [int]$lastCleanup.LocalPortsClosedObserved
                } else { 0 }
                remote_cleanup_endpoints_observed = $script:remoteCleanupCompletedRefs.Count
                configuration_attempted_endpoint_count = $script:configuredSessions.Count
                configuration_receipts_observed = $script:configurationReceiptsObservedRefs.Count
                cleanup_retry_required = $cleanupRetryRequired
                protected_input_snapshot_count = $script:protectedSnapshotCount
                local_snapshot_cleanup_observed = $script:localSnapshotCleanupObserved
                local_snapshot_cleanup_retry_required = $script:localSnapshotCleanupRetryRequired
                local_task_temporary_cleanup_observed = $script:localTaskTemporaryCleanupObserved
                local_task_temporary_cleanup_retry_required = $script:localTaskTemporaryCleanupRetryRequired
                raw_identifiers_included = $false
                diagnostic_text_included = $false
            }
            Write-JsonUtf8NoBom -Path $failureObservationFile -Value $failureObservation
        }
        catch {
            Write-Warning ('Fail-closed observation could not be persisted: ' + (Protect-Diagnostic $_.Exception.Message))
        }
    }
    try {
        foreach ($record in @($script:tunnelRecords)) {
            if ($null -ne $record.ProcessObject) {
                $record.ProcessObject.Dispose()
                $record['ProcessObject'] = $null
            }
        }
    }
    finally {
        try {
            if ($script:approvalLeaseAcquired -and $null -ne $script:approvalLeaseMutex) {
                $script:approvalLeaseMutex.ReleaseMutex()
                $script:approvalLeaseAcquired = $false
            }
        }
        catch { Write-Warning 'The local approval lease handle could not be disposed cleanly.' }
        try {
            if ($null -ne $script:approvalLeaseMutex) {
                $script:approvalLeaseMutex.Dispose()
                $script:approvalLeaseMutex = $null
            }
        }
        catch { Write-Warning 'The global approval lease handle could not be disposed cleanly.' }
    }
}
