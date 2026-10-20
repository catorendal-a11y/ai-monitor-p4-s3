param(
    [string]$CommandDirectory = (Join-Path $env:LOCALAPPDATA 'Programs\NOVA Terminal\bin'),
    [ValidateSet('User','Process')][string]$EnvironmentScope = 'User',
    # Windows Run value written by the Start at sign-in setting; tests use a throwaway name.
    [string]$RunValueName = 'LimitBuddy',
    [switch]$RegisterOnly,
    [switch]$Uninstall
)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskBin = [IO.Path]::GetFullPath($CommandDirectory).TrimEnd('\')
# limitbuddy is the command; nova stays as an alias for existing hooks and statuslines.
$taskCommands = @('limitbuddy','nova')
$taskFiles = @($taskCommands | ForEach-Object { (Join-Path $taskBin ($_ + '.cmd')), (Join-Path $taskBin ($_ + '-launcher.ps1')) })
$taskOwner = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($taskRoot))
$taskMarker = 'AI_MONITOR_TERMINAL_OWNER=' + $taskOwner

function Update-TerminalPath([bool]$Remove) {
    $taskOldPath = [Environment]::GetEnvironmentVariable('Path', $EnvironmentScope)
    $taskParts = @($taskOldPath -split ';' | Where-Object { $_ -and $_.Trim().TrimEnd('\') -ine $taskBin })
    if (-not $Remove) { $taskParts += $taskBin }
    $taskNewPath = $taskParts -join ';'
    if ($taskNewPath -cne $taskOldPath) {
        [Environment]::SetEnvironmentVariable('Path', $taskNewPath, $EnvironmentScope)
    }
    if ($EnvironmentScope -eq 'User') {
        # Refresh this process and notify Explorer; existing parent shells need reopening.
        $taskCurrentParts = @($env:Path -split ';' | Where-Object { $_ -and $_.Trim().TrimEnd('\') -ine $taskBin })
        if (-not $Remove) { $taskCurrentParts += $taskBin }
        $env:Path = $taskCurrentParts -join ';'
        if (-not ('AiMonitorTerminal.Environment' -as [type])) {
            Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace AiMonitorTerminal {
  public static class Environment {
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint message, UIntPtr wparam,
        string lparam, uint flags, uint timeout, out UIntPtr result);
  }
}
'@
        }
        $taskBroadcastResult = [UIntPtr]::Zero
        [void][AiMonitorTerminal.Environment]::SendMessageTimeout([IntPtr]0xffff,0x1a,
            [UIntPtr]::Zero,'Environment',2,1000,[ref]$taskBroadcastResult)
    }
}

if ($Uninstall) {
    # Remove each surviving file owned by this exact installation. A partial install
    # must be repairable without touching another installation or a custom command.
    $taskOwned = @($taskFiles | Where-Object {
        (Test-Path -LiteralPath $_) -and
        (Get-Content -LiteralPath $_ -Raw).Contains($taskMarker)
    })
    if ($taskOwned.Count -gt 0) {
        foreach ($taskFile in $taskOwned) { Remove-Item -LiteralPath $taskFile }
        $taskForeign = @($taskFiles | Where-Object { Test-Path -LiteralPath $_ })
        if ($taskForeign.Count -eq 0) { Update-TerminalPath $true }
        Write-Output 'Removed this installation''s limitbuddy and nova commands.'
    }
    # Remove the Start at sign-in entry too, but only when it starts this folder: a leftover entry
    # would try to launch a deleted interpreter at every sign-in.
    $taskRunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    $taskRun = (Get-ItemProperty -LiteralPath $taskRunKey -Name $RunValueName -ErrorAction SilentlyContinue).$RunValueName
    $taskOwnScript = '"' + (Join-Path $taskRoot 'tools\aim_control.py') + '" --start-host'
    if (($taskRun -is [string]) -and $taskRun.EndsWith($taskOwnScript,[StringComparison]::OrdinalIgnoreCase)) {
        Remove-ItemProperty -LiteralPath $taskRunKey -Name $RunValueName
        Write-Output 'Removed this installation''s Start at sign-in entry.'
    }
    exit 0
}

if (-not (Test-Path -LiteralPath (Join-Path $taskRoot 'AI-Monitor-Terminal.bat'))) {
    throw 'The complete LimitBuddy package is required. Keep Install-LimitBuddy.ps1 beside the launcher.'
}
foreach ($taskFile in $taskFiles) {
    if ((Test-Path -LiteralPath $taskFile) -and
        -not (Get-Content -LiteralPath $taskFile -Raw).Contains('AI_MONITOR_TERMINAL_OWNER=')) {
        throw ('An unrelated command exists: ' + (Split-Path -Leaf $taskFile) + '. No command or PATH entry was changed.')
    }
}
if (-not $RegisterOnly) {
    & (Join-Path $taskRoot 'setup.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Terminal dependency setup failed. No command was installed.' }
}
New-Item -ItemType Directory -Path $taskBin -Force | Out-Null
foreach ($taskName in $taskCommands) {
    $taskCmdText = @"
@echo off
rem $taskMarker
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0$taskName-launcher.ps1" %*
exit /b %errorlevel%
"@
    $taskPsText = @"
# $taskMarker
`$taskRoot = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('$taskOwner'))
& (Join-Path `$taskRoot 'AI-Monitor-Terminal.bat') @args
exit `$LASTEXITCODE
"@
    [IO.File]::WriteAllText((Join-Path $taskBin ($taskName + '-launcher.ps1')),$taskPsText,[Text.Encoding]::ASCII)
    [IO.File]::WriteAllText((Join-Path $taskBin ($taskName + '.cmd')),$taskCmdText,[Text.Encoding]::ASCII)
}
Update-TerminalPath $false
Write-Output 'Installed limitbuddy for this Windows user (nova still works). Open a new terminal and run: limitbuddy'
