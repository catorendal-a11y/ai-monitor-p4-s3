param([string]$Python = '', [switch]$BuildTools, [switch]$FlashTools)
$ErrorActionPreference = 'Stop'
$taskProjectRoot = $PSScriptRoot
if ((Test-Path -LiteralPath (Join-Path $taskProjectRoot 'runtime')) -and -not $BuildTools) {
    $taskBundledPython = & (Join-Path $taskProjectRoot 'scripts\verify_terminal_runtime.ps1') -Root $taskProjectRoot
    & $taskBundledPython -B -c 'import serial, psutil, textual, cryptography, lz4, esptool'
    if ($LASTEXITCODE -ne 0) { throw 'Bundled dependencies could not load. Extract the complete Windows x64 release again.' }
    $taskBundledConfig = Join-Path $taskProjectRoot 'tools\aim_host.json'
    if (-not (Test-Path -LiteralPath $taskBundledConfig)) {
        Copy-Item -LiteralPath (Join-Path $taskProjectRoot 'tools\aim_host.example.json') -Destination $taskBundledConfig
    }
    Write-Output 'Bundled Python and dependencies verified. No downloads or separate Python installation are required.'
    return
}
$taskVenv = Join-Path $taskProjectRoot '.venv'
$taskVenvPython = Join-Path $taskVenv 'Scripts\python.exe'
if (Test-Path -LiteralPath $taskVenvPython) {
    $taskVenvValid = $false
    try {
        & $taskVenvPython -c 'import sys, pathlib, pip; assert sys.version_info >= (3, 10); assert pathlib.Path(sys.prefix).resolve() == pathlib.Path(sys.argv[1]).resolve()' $taskVenv 1>$null 2>$null
        $taskVenvValid = $LASTEXITCODE -eq 0
    } catch { }
    if (-not $taskVenvValid) {
        throw 'The existing .venv is unusable or belongs to another folder. Rename .venv to keep a backup, then run setup.ps1 again, or use the Windows release. Local settings were preserved.'
    }
}
if (-not (Test-Path -LiteralPath $taskVenvPython)) {
    $taskCandidates = @()
    if ($Python) { $taskCandidates += $Python }
    $taskLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($taskLauncher) {
        try {
            $taskDetected = & $taskLauncher.Source -3 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0) { $taskCandidates += $taskDetected }
        } catch { }
    }
    $taskPathPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($taskPathPython -and $taskPathPython.Source -notlike '*\WindowsApps\*') { $taskCandidates += $taskPathPython.Source }
    $taskCandidates += (Join-Path $env:USERPROFILE '.platformio\penv\Scripts\python.exe')
    $taskSelectedPython = $null
    foreach ($taskCandidate in $taskCandidates | Select-Object -Unique) {
        try { & $taskCandidate -c 'import sys; assert sys.version_info >= (3, 10)' 1>$null 2>$null } catch { continue }
        if ($LASTEXITCODE -eq 0) { $taskSelectedPython = $taskCandidate; break }
    }
    if (-not $taskSelectedPython) { throw 'Python 3.10+ was not found. Install Python from https://www.python.org/downloads/windows/ and run again.' }
    & $taskSelectedPython -m venv $taskVenv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the local virtual environment.' }
}
& $taskVenvPython -m pip install --upgrade 'pip==26.2.1'
if ($LASTEXITCODE -ne 0) { throw 'Package installer security update failed.' }
& $taskVenvPython -m pip install -r (Join-Path $taskProjectRoot 'tools\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if ($BuildTools) {
    & $taskVenvPython -m pip install 'platformio>=6.1,<7'
    if ($LASTEXITCODE -ne 0) { throw 'Build tool installation failed.' }
}
if ($FlashTools) {
    & $taskVenvPython -m pip install 'esptool==5.4.0'
    if ($LASTEXITCODE -ne 0) { throw 'Flash tool installation failed.' }
}
$taskLocalConfig = Join-Path $taskProjectRoot 'tools\aim_host.json'
if (-not (Test-Path -LiteralPath $taskLocalConfig)) {
    Copy-Item -LiteralPath (Join-Path $taskProjectRoot 'tools\aim_host.example.json') -Destination $taskLocalConfig
}
Write-Output 'Setup complete. Run Install-LimitBuddy.ps1 once, then open a new terminal and type limitbuddy.'
Write-Output 'For the terminal dashboard, double-click AI-Monitor-Terminal.bat. See docs/TERMINAL.md.'
Write-Output 'Local settings and keys were preserved. No hardware was flashed.'
