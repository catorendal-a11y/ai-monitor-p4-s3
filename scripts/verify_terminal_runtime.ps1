param([Parameter(Mandatory=$true)][string]$Root)
$ErrorActionPreference = 'Stop'
$taskRuntime = [IO.Path]::GetFullPath((Join-Path $Root 'runtime')).TrimEnd('\')
$taskManifest = Join-Path $taskRuntime 'manifest.json'
if (-not (Test-Path -LiteralPath $taskManifest)) { throw 'Bundled runtime is incomplete. Extract the complete release again.' }
if ((Get-Item -LiteralPath $taskManifest).Length -gt 4194304) { throw 'Runtime manifest is too large.' }
if ((Get-Item -LiteralPath $taskRuntime).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked runtime directories are refused.' }
$taskEntries = @(Get-ChildItem -LiteralPath $taskRuntime -Recurse -Force)
foreach ($taskEntry in $taskEntries) {
    if ($taskEntry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked runtime files are refused.' }
}
$taskData = Get-Content -LiteralPath $taskManifest -Raw -Encoding UTF8 | ConvertFrom-Json
if ($taskData.schema -ne 1 -or $taskData.python_version -cne '3.13.16' -or
    $taskData.python_archive_sha256 -cne '97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297') {
    throw 'Unsupported bundled Python runtime.'
}
$taskKnown = @{}
foreach ($taskProperty in $taskData.files.PSObject.Properties) {
    $taskName = [string]$taskProperty.Name
    if (-not $taskName -or [IO.Path]::IsPathRooted($taskName) -or $taskName -match '[\:]' -or
        ($taskName.Split('/') -contains '..') -or $taskProperty.Value -cnotmatch '^[a-f0-9]{64}$') { throw 'Unsafe runtime manifest entry.' }
    $taskFile = [IO.Path]::GetFullPath((Join-Path $taskRuntime $taskName.Replace('/','\')))
    if (-not $taskFile.StartsWith($taskRuntime + '\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Runtime path escaped its directory.' }
    $taskStream = [IO.File]::OpenRead($taskFile)
    $taskHasher = [Security.Cryptography.SHA256]::Create()
    try { $taskHash = [BitConverter]::ToString($taskHasher.ComputeHash($taskStream)).Replace('-','').ToLowerInvariant() }
    finally { $taskStream.Dispose(); $taskHasher.Dispose() }
    if ($taskHash -cne $taskProperty.Value) {
        throw 'A bundled runtime file changed. Extract the complete release again.'
    }
    $taskKnown[$taskFile] = $true
}
foreach ($taskEntry in $taskEntries) {
    if ($taskEntry.PSIsContainer -or $taskEntry.FullName -ieq $taskManifest -or $taskKnown.ContainsKey($taskEntry.FullName)) { continue }
    $taskRelative = $taskEntry.FullName.Substring($taskRuntime.Length + 1)
    if ($taskRelative -match '(^|\\)__pycache__\\[^\\]+\.pyc$') { continue }
    throw 'Unexpected files in the bundled runtime. Extract the complete release again.'
}
$taskPython = Join-Path $taskRuntime 'python.exe'
if (-not $taskKnown.ContainsKey($taskPython)) { throw 'The bundled interpreter is missing.' }
Write-Output $taskPython
