Microsoft.PowerShell.Core\Set-StrictMode -Version Latest
$script:staleRecoveryLeases = @{}
$script:activeSnapshotSets = @{}

function Get-JCareerSnapshotDirectoryKey {
    param([Parameter(Mandatory = $true)][string]$Directory)
    return [IO.Path]::GetFullPath($Directory).TrimEnd('\', '/').ToUpperInvariant()
}

function Get-JCareerActiveSnapshotRecord {
    param([Parameter(Mandatory = $true)]$SnapshotSet)
    foreach ($key in @($script:activeSnapshotSets.Keys)) {
        $record = $script:activeSnapshotSets[$key]
        if ([object]::ReferenceEquals($record.SnapshotSet, $SnapshotSet)) {
            return $record
        }
    }
    return $null
}

function Test-JCareerSnapshotSetMatchesActiveRecord {
    param(
        [Parameter(Mandatory = $true)]$SnapshotSet,
        [Parameter(Mandatory = $true)]$Record
    )
    try {
        if (
            $SnapshotSet.CleanupObserved -or
            -not $SnapshotSet.Lease.Acquired -or
            -not [object]::ReferenceEquals($SnapshotSet.Lease, $Record.Lease) -or
            -not [object]::ReferenceEquals($SnapshotSet, $Record.SnapshotSet) -or
            -not [string]::Equals(
                (Get-JCareerSnapshotDirectoryKey -Directory ([string]$SnapshotSet.Directory)),
                (Get-JCareerSnapshotDirectoryKey -Directory ([string]$Record.Directory)),
                [StringComparison]::Ordinal
            ) -or
            -not [string]::Equals(
                ([IO.Path]::GetFullPath([string]$SnapshotSet.Root).TrimEnd('\', '/')),
                ([IO.Path]::GetFullPath([string]$Record.Root).TrimEnd('\', '/')),
                [StringComparison]::OrdinalIgnoreCase
            ) -or
            -not [string]::Equals(
                ([string]$SnapshotSet.Prefix),
                ([string]$Record.Prefix),
                [StringComparison]::Ordinal
            )
        ) {
            return $false
        }
        return (Test-JCareerDirectSnapshotPath `
            -Root ([string]$SnapshotSet.Root) `
            -Prefix ([string]$SnapshotSet.Prefix) `
            -Directory ([string]$SnapshotSet.Directory))
    }
    catch { return $false }
}

function New-JCareerCurrentUserFileAcl {
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

function Get-JCareerStreamSha256 {
    param([Parameter(Mandatory = $true)][IO.Stream]$Stream)
    $Stream.Position = 0
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = $sha.ComputeHash($Stream) }
    finally { $sha.Dispose() }
    return ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
}

function Get-JCareerSnapshotLeaseName {
    param([Parameter(Mandatory = $true)][string]$Directory)
    $canonical = [IO.Path]::GetFullPath($Directory).ToUpperInvariant()
    $bytes = [Text.Encoding]::UTF8.GetBytes($canonical)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = $sha.ComputeHash($bytes) }
    finally { $sha.Dispose() }
    $hash = ([BitConverter]::ToString($digest)).Replace('-', '').ToLowerInvariant()
    return 'Global\JCareerProtectedSnapshot-' + $hash
}

function New-JCareerSnapshotLease {
    param([Parameter(Mandatory = $true)][string]$Directory)
    $mutex = $null
    $acquired = $false
    $abandoned = $false
    try {
        $createdNew = $false
        $mutex = [Threading.Mutex]::new(
            $false,
            (Get-JCareerSnapshotLeaseName -Directory $Directory),
            [ref]$createdNew
        )
        try { $acquired = $mutex.WaitOne(0) }
        catch [Threading.AbandonedMutexException] {
            $acquired = $true
            $abandoned = $true
        }
        if (-not $acquired) {
            throw 'The protected snapshot lease is held by an active operation.'
        }
        return [pscustomobject]@{
            Mutex = $mutex
            Acquired = $true
            WasAbandoned = $abandoned
        }
    }
    catch {
        $failure = $_
        if ($null -ne $mutex) {
            if ($acquired) {
                try { $mutex.ReleaseMutex() } catch {}
            }
            try { $mutex.Dispose() } catch {}
        }
        throw $failure
    }
}

function Release-JCareerSnapshotLease {
    param([Parameter(Mandatory = $true)]$Lease)
    if ($Lease.Acquired -and $null -ne $Lease.Mutex) {
        $Lease.Mutex.ReleaseMutex()
        $Lease.Acquired = $false
    }
    if ($null -ne $Lease.Mutex) {
        $Lease.Mutex.Dispose()
        $Lease.Mutex = $null
    }
}

function New-JCareerProtectedSnapshotSet {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RootPath,
        [ValidatePattern('^[a-z0-9-]{3,40}$')][string]$Prefix = 'jcareer-input'
    )
    $root = [IO.Path]::GetFullPath($RootPath)
    if (-not [IO.Directory]::Exists($root)) { throw 'Protected snapshot root does not exist.' }
    $leaf = $Prefix + '-' + [Guid]::NewGuid().ToString('N')
    $directory = [IO.Path]::GetFullPath(
        (Microsoft.PowerShell.Management\Join-Path $root $leaf)
    )
    $rootPrefix = $root.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $directory.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Protected snapshot directory escaped its root.'
    }
    $lease = New-JCareerSnapshotLease -Directory $directory
    $directoryCreated = $false
    $activeKey = Get-JCareerSnapshotDirectoryKey -Directory $directory
    $registered = $false
    try {
        Microsoft.PowerShell.Management\New-Item -ItemType Directory -Path $directory | Microsoft.PowerShell.Core\Out-Null
        $directoryCreated = $true
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
        Microsoft.PowerShell.Security\Set-Acl -LiteralPath $directory -AclObject $acl
        $snapshotSet = [pscustomobject]@{
            Directory = $directory
            Root = $root
            Prefix = $Prefix
            Streams = [Collections.Generic.List[object]]::new()
            Count = 0
            CleanupObserved = $false
            Lease = $lease
        }
        if ($script:activeSnapshotSets.ContainsKey($activeKey)) {
            throw 'The protected snapshot directory is already registered as active.'
        }
        $script:activeSnapshotSets.Add($activeKey, [pscustomobject]@{
            SnapshotSet = $snapshotSet
            Directory = $directory
            Root = $root
            Prefix = $Prefix
            Lease = $lease
        })
        $registered = $true
        return $snapshotSet
    }
    catch {
        $initializationFailure = $_
        $cleanupFailure = $null
        if ($registered) {
            $script:activeSnapshotSets.Remove($activeKey)
            $registered = $false
        }
        if ($directoryCreated -and [IO.Directory]::Exists($directory)) {
            try {
                $attributes = [IO.File]::GetAttributes($directory)
                if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw 'Refusing to recurse into a reparse-point snapshot directory.'
                }
                Microsoft.PowerShell.Management\Remove-Item -LiteralPath $directory -Recurse -Force
                if ([IO.Directory]::Exists($directory)) {
                    throw 'The failed snapshot directory remains present.'
                }
            }
            catch { $cleanupFailure = $_ }
        }
        try { Release-JCareerSnapshotLease -Lease $lease }
        catch {
            if ($null -eq $cleanupFailure) { $cleanupFailure = $_ }
        }
        if ($null -ne $cleanupFailure) {
            throw 'Protected snapshot initialization failed and exact-directory cleanup was not observed.'
        }
        throw $initializationFailure
    }
}

function Add-JCareerProtectedSnapshotFile {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]$SnapshotSet,
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$DestinationName
    )
    if (-not [IO.File]::Exists($Source)) { throw 'A required protected-snapshot source is unavailable.' }
    $activeRecord = Get-JCareerActiveSnapshotRecord -SnapshotSet $SnapshotSet
    if (
        $null -eq $activeRecord -or
        -not (Test-JCareerSnapshotSetMatchesActiveRecord -SnapshotSet $SnapshotSet -Record $activeRecord) -or
        -not [IO.Directory]::Exists([string]$SnapshotSet.Directory) -or
        -not (Test-JCareerProtectedSnapshotDirectoryAcl -Directory ([string]$SnapshotSet.Directory)) -or
        -not (Test-JCareerSnapshotTreeHasNoReparsePoints -Directory ([string]$SnapshotSet.Directory))
    ) {
        throw 'Protected snapshot set is not active.'
    }
    if (
        [string]::IsNullOrWhiteSpace($DestinationName) -or
        $DestinationName.Length -gt 512 -or
        [IO.Path]::IsPathRooted($DestinationName)
    ) {
        throw 'Protected snapshot destination must be one bounded relative path.'
    }
    $destinationSegments = @($DestinationName -split '[\\/]')
    if (
        $destinationSegments.Count -gt 16 -or
        @($destinationSegments | Where-Object {
            $_ -in @('', '.', '..') -or $_ -notmatch '^[A-Za-z0-9_.-]{1,80}$'
        }).Count -ne 0
    ) {
        throw 'Protected snapshot destination contains an invalid path segment.'
    }
    $sourcePath = [IO.Path]::GetFullPath($Source)
    $destinationPath = [IO.Path]::GetFullPath(
        (Microsoft.PowerShell.Management\Join-Path ([string]$SnapshotSet.Directory) $DestinationName)
    )
    $directoryPrefix = ([string]$SnapshotSet.Directory).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $destinationPath.StartsWith($directoryPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Protected snapshot file escaped its directory.'
    }
    $destinationDirectory = [IO.Path]::GetDirectoryName($destinationPath)
    if (-not [IO.Directory]::Exists($destinationDirectory)) {
        [IO.Directory]::CreateDirectory($destinationDirectory) | Microsoft.PowerShell.Core\Out-Null
    }
    if (
        -not (Test-JCareerSnapshotSetMatchesActiveRecord -SnapshotSet $SnapshotSet -Record $activeRecord) -or
        -not (Test-JCareerProtectedSnapshotDirectoryAcl -Directory ([string]$SnapshotSet.Directory)) -or
        -not (Test-JCareerSnapshotTreeHasNoReparsePoints -Directory ([string]$SnapshotSet.Directory))
    ) {
        throw 'Protected snapshot tree changed after destination preparation.'
    }
    $sourceStream = $null
    $destinationStream = $null
    $snapshotReadLock = $null
    try {
        $sourceStream = [IO.File]::Open(
            $sourcePath, [IO.FileMode]::Open,
            [IO.FileAccess]::Read, [IO.FileShare]::Read
        )
        $sourceLength = [long]$sourceStream.Length
        $sourcePreHash = Get-JCareerStreamSha256 -Stream $sourceStream
        $sourceStream.Position = 0
        $destinationStream = [IO.FileStream]::new(
            $destinationPath,
            [IO.FileMode]::CreateNew,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [IO.FileShare]::Read,
            4096,
            [IO.FileOptions]::SequentialScan,
            (New-JCareerCurrentUserFileAcl)
        )
        $sourceStream.CopyTo($destinationStream)
        $destinationStream.Flush($true)
        if ([long]$destinationStream.Length -ne $sourceLength) {
            throw 'Protected snapshot length differs from its source.'
        }
        $snapshotHash = Get-JCareerStreamSha256 -Stream $destinationStream
        $sourcePostHash = Get-JCareerStreamSha256 -Stream $sourceStream
        if ($sourcePreHash -ne $snapshotHash -or $sourcePreHash -ne $sourcePostHash) {
            throw 'Protected snapshot source changed during capture.'
        }
        $destinationStream.Dispose()
        $destinationStream = $null
        $snapshotReadLock = [IO.File]::Open(
            $destinationPath, [IO.FileMode]::Open,
            [IO.FileAccess]::Read, [IO.FileShare]::Read
        )
        if ([long]$snapshotReadLock.Length -ne $sourceLength) {
            throw 'Protected snapshot length changed before read locking.'
        }
        $snapshotLockedHash = Get-JCareerStreamSha256 -Stream $snapshotReadLock
        if ($snapshotLockedHash -ne $sourcePreHash) {
            throw 'Protected snapshot changed before read locking.'
        }
        $snapshotReadLock.Position = 0
        $SnapshotSet.Streams.Add($snapshotReadLock)
        $SnapshotSet.Count = [int]$SnapshotSet.Count + 1
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

function Test-JCareerDirectSnapshotPath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Prefix,
        [Parameter(Mandatory = $true)][string]$Directory
    )
    try {
        $canonicalRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
        $canonicalDirectory = [IO.Path]::GetFullPath($Directory).TrimEnd('\', '/')
        $parent = [IO.Path]::GetFullPath(
            [IO.Path]::GetDirectoryName($canonicalDirectory)
        ).TrimEnd('\', '/')
        $leaf = [IO.Path]::GetFileName($canonicalDirectory)
        $leafPattern = '^' + [regex]::Escape($Prefix) + '-[0-9a-f]{32}$'
        return (
            [string]::Equals(
                $parent,
                $canonicalRoot,
                [StringComparison]::OrdinalIgnoreCase
            ) -and
            $leaf -cmatch $leafPattern
        )
    }
    catch { return $false }
}

function Test-JCareerProtectedSnapshotDirectoryAcl {
    param([Parameter(Mandatory = $true)][string]$Directory)
    try {
        $attributes = [IO.File]::GetAttributes($Directory)
        if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            return $false
        }
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl = Microsoft.PowerShell.Security\Get-Acl -LiteralPath $Directory
        $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier])
        if ($owner.Value -ne $identity.Value -or -not $acl.AreAccessRulesProtected) {
            return $false
        }
        $rules = @(
            $acl.GetAccessRules(
                $true,
                $true,
                [Security.Principal.SecurityIdentifier]
            )
        )
        if ($rules.Count -ne 1) { return $false }
        $rule = $rules[0]
        $expectedInheritance = (
            [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
            [Security.AccessControl.InheritanceFlags]::ObjectInherit
        )
        return (
            $rule.IdentityReference.Value -eq $identity.Value -and
            $rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
            $rule.FileSystemRights -eq [Security.AccessControl.FileSystemRights]::FullControl -and
            $rule.InheritanceFlags -eq $expectedInheritance -and
            $rule.PropagationFlags -eq [Security.AccessControl.PropagationFlags]::None -and
            -not $rule.IsInherited
        )
    }
    catch { return $false }
}

function Test-JCareerSnapshotTreeHasNoReparsePoints {
    param([Parameter(Mandatory = $true)][string]$Directory)
    try {
        $pending = [Collections.Generic.Stack[string]]::new()
        $pending.Push([IO.Path]::GetFullPath($Directory))
        while ($pending.Count -gt 0) {
            $current = $pending.Pop()
            foreach ($entry in [IO.Directory]::EnumerateFileSystemEntries($current)) {
                $attributes = [IO.File]::GetAttributes($entry)
                if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    return $false
                }
                if (($attributes -band [IO.FileAttributes]::Directory) -ne 0) {
                    $pending.Push($entry)
                }
            }
        }
        return $true
    }
    catch { return $false }
}

function Remove-JCareerStaleProtectedSnapshotSet {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$RootPath,
        [Parameter(Mandatory = $true)]
        [ValidatePattern('^[a-z0-9-]{3,40}$')]
        [string]$Prefix,
        [Parameter(Mandatory = $true)][string]$SnapshotDirectory,
        [Parameter(Mandatory = $true)]
        [ValidateSet('JCAREER_STALE_SNAPSHOT_RECOVERY_APPROVED')]
        [string]$RecoveryAcknowledgement
    )
    $root = [IO.Path]::GetFullPath($RootPath)
    $directory = [IO.Path]::GetFullPath($SnapshotDirectory).TrimEnd('\', '/')
    if (-not [IO.Directory]::Exists($root)) {
        throw 'Protected snapshot recovery root does not exist.'
    }
    if (-not (Test-JCareerDirectSnapshotPath -Root $root -Prefix $Prefix -Directory $directory)) {
        throw 'Stale snapshot recovery requires one exact direct-child GUID path.'
    }
    if (-not [IO.Directory]::Exists($directory)) {
        throw 'Stale snapshot recovery target does not exist.'
    }

    $leaseKey = Get-JCareerSnapshotDirectoryKey -Directory $directory
    if ($script:activeSnapshotSets.ContainsKey($leaseKey)) {
        throw 'Stale snapshot recovery refuses a snapshot set registered as active in this process.'
    }
    if ($script:staleRecoveryLeases.ContainsKey($leaseKey)) {
        $lease = $script:staleRecoveryLeases[$leaseKey]
    }
    else {
        $lease = New-JCareerSnapshotLease -Directory $directory
        $script:staleRecoveryLeases[$leaseKey] = $lease
    }
    $directoryRemoved = $false
    try {
        if (-not (Test-JCareerProtectedSnapshotDirectoryAcl -Directory $directory)) {
            throw 'Stale snapshot recovery target owner or protected ACL is invalid.'
        }
        if (-not (Test-JCareerSnapshotTreeHasNoReparsePoints -Directory $directory)) {
            throw 'Stale snapshot recovery refuses a tree containing a reparse point.'
        }
        if (
            -not (Test-JCareerDirectSnapshotPath -Root $root -Prefix $Prefix -Directory $directory) -or
            -not (Test-JCareerProtectedSnapshotDirectoryAcl -Directory $directory) -or
            -not (Test-JCareerSnapshotTreeHasNoReparsePoints -Directory $directory)
        ) {
            throw 'Stale snapshot recovery target changed before removal.'
        }
        Microsoft.PowerShell.Management\Remove-Item -LiteralPath $directory -Recurse -Force
        if ([IO.Directory]::Exists($directory)) {
            throw 'Stale snapshot recovery did not remove the exact target.'
        }
        $directoryRemoved = $true
    }
    finally {
        if ($directoryRemoved) {
            Release-JCareerSnapshotLease -Lease $lease
            $script:staleRecoveryLeases.Remove($leaseKey)
        }
    }
}

function Remove-JCareerProtectedSnapshotSet {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)]$SnapshotSet)
    $activeRecord = Get-JCareerActiveSnapshotRecord -SnapshotSet $SnapshotSet
    if (
        $null -eq $activeRecord -or
        -not (Test-JCareerSnapshotSetMatchesActiveRecord -SnapshotSet $SnapshotSet -Record $activeRecord)
    ) {
        throw 'Protected snapshot cleanup refused an unregistered or changed snapshot-set object.'
    }
    $errors = [Collections.Generic.List[string]]::new()
    $remaining = [Collections.Generic.List[object]]::new()
    foreach ($stream in @($SnapshotSet.Streams)) {
        try { $stream.Dispose() }
        catch {
            $errors.Add('snapshot stream disposal failed')
            $remaining.Add($stream)
        }
    }
    $SnapshotSet.Streams.Clear()
    foreach ($stream in $remaining) { $SnapshotSet.Streams.Add($stream) }
    if ($SnapshotSet.Streams.Count -eq 0 -and [IO.Directory]::Exists([string]$SnapshotSet.Directory)) {
        try {
            if (
                -not (Test-JCareerSnapshotSetMatchesActiveRecord -SnapshotSet $SnapshotSet -Record $activeRecord) -or
                -not (Test-JCareerProtectedSnapshotDirectoryAcl -Directory ([string]$SnapshotSet.Directory)) -or
                -not (Test-JCareerSnapshotTreeHasNoReparsePoints -Directory ([string]$SnapshotSet.Directory))
            ) {
                throw 'Snapshot cleanup target path, ACL, or tree changed before removal.'
            }
            Microsoft.PowerShell.Management\Remove-Item -LiteralPath ([string]$SnapshotSet.Directory) -Recurse -Force
        }
        catch { $errors.Add('snapshot directory removal failed') }
    }
    if ([IO.Directory]::Exists([string]$SnapshotSet.Directory)) {
        $errors.Add('snapshot directory remains present')
    }
    if ($errors.Count -ne 0) {
        throw 'Protected snapshot cleanup was not fully observed; its lease remains held for retry.'
    }
    try { Release-JCareerSnapshotLease -Lease $SnapshotSet.Lease }
    catch { throw 'Protected snapshot directory was removed but its lease release was not observed.' }
    $activeKey = Get-JCareerSnapshotDirectoryKey -Directory ([string]$activeRecord.Directory)
    $script:activeSnapshotSets.Remove($activeKey)
    $SnapshotSet.CleanupObserved = $true
}

Microsoft.PowerShell.Core\Export-ModuleMember -Function @(
    'New-JCareerProtectedSnapshotSet',
    'Add-JCareerProtectedSnapshotFile',
    'Remove-JCareerProtectedSnapshotSet',
    'Remove-JCareerStaleProtectedSnapshotSet'
)
