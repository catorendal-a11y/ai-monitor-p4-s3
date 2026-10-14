$ErrorActionPreference = 'Stop'
$taskHostScript = Join-Path $PSScriptRoot 'aim_host.py'
$taskProject = Split-Path $PSScriptRoot -Parent
$taskCandidates = @((Join-Path $taskProject '.venv\Scripts\python.exe'), (Join-Path $env:USERPROFILE '.platformio\penv\Scripts\python.exe'))
$taskFallback = Get-Command python.exe -ErrorAction SilentlyContinue
if ($taskFallback) { $taskCandidates += $taskFallback.Source }
$taskPython = $null
foreach ($taskCandidate in $taskCandidates | Select-Object -Unique) {
    if (-not (Test-Path -LiteralPath $taskCandidate)) { continue }
    try { & $taskCandidate -c 'import serial, psutil' 1>$null 2>$null } catch { continue }
    if ($LASTEXITCODE -eq 0) { $taskPython = $taskCandidate; break }
}
if (-not $taskPython) { throw 'Python with the host dependencies was not found. Install tools/requirements.txt.' }
# The common backend validates setup and identifies the actual Python entry
# point before stopping a process. Never stop by command-line substring.
& $taskPython (Join-Path $PSScriptRoot 'aim_control.py') --start-host
if ($LASTEXITCODE -ne 0) { throw 'Host startup failed. Complete First-time setup and check the reported USB selection.' }
