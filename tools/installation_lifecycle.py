"""Bounded, installation-scoped upgrade/uninstall preparation.

Private configuration, history, account trust and unrelated integrations survive.
Only the installed console calls this module; no uninstall is started here.
"""
from pathlib import Path
import subprocess
from host_security import powershell_executable


def remove_startup_task(root):
    """Remove only the exact current-user task pointing at this installation."""
    executable=str(Path(root).resolve()/'AI-Monitor.exe').replace("'","''")
    script = r"""$ErrorActionPreference='Stop'; try {
$tasks=@(Get-ScheduledTask -TaskPath '\' -ErrorAction Stop | Where-Object {$_.TaskName -ceq 'AI Monitor Host'});
if ($tasks.Count -eq 0) { exit 0 }; if ($tasks.Count -ne 1) { exit 1 };
$task=$tasks[0]; $actions=@($task.Actions);
if ($actions.Count -ne 1 -or ([string]$actions[0].Execute).Trim('"') -ine '__EXECUTABLE__' -or $actions[0].Arguments -cne '--start-host') { exit 0 };
$user=$task.Principal.UserId;
if ($user -notmatch '^S-1-') { $user=([System.Security.Principal.NTAccount]::new($user)).Translate([System.Security.Principal.SecurityIdentifier]).Value };
if ($user -ne [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value) { exit 0 };
Unregister-ScheduledTask -TaskPath '\' -TaskName 'AI Monitor Host' -Confirm:$false -ErrorAction Stop;
if (@(Get-ScheduledTask -TaskPath '\' -ErrorAction Stop | Where-Object {$_.TaskName -ceq 'AI Monitor Host'}).Count) { exit 1 };
exit 0
} catch { exit 1 }""".replace('__EXECUTABLE__',executable)
    result=subprocess.run([powershell_executable(),'-NoProfile','-NonInteractive','-Command',script],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=12,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise RuntimeError('Could not verify removal of this installation startup task. Retry before uninstalling.')


def remove_integrations(root, home=None):
    """Reuse exact generated-hook ownership checks; no trust/config resets."""
    import provider_setup as providers
    from claude_permission_setup import update
    from claude_paths import config_root
    from codex_support import codex_home
    user=Path.home() if home is None else Path(home)
    codex=codex_home() if home is None else user/'.codex'
    # Avoid creating settings/markers for clients which have never been configured.
    if (codex/'hooks.json').exists(): providers.codex_session_link(root,remove=True,home=home)
    if (user/'.zcode/cli/config.json').exists(): providers.zcode_session_link(root,remove=True,home=home)
    if (config_root(home)/'settings.json').exists():
        providers.claude_session_link(root,remove=True,home=home)
        update(root,remove=True,home=home)
        state=providers.claude_link_state(root,home=home)
        if state=='installed': providers.claude_bridge(root,remove=True,home=home)
        elif state in ('invalid','unknown'): raise RuntimeError('Claude quota link could not be checked safely.')


def prepare(root, *, uninstall=False, home=None):
    """Raise on unconfirmed cleanup so installer keeps the helpers available."""
    from aim_control import stop_host, owned_hosts
    root=Path(root).resolve()
    stop_host(root,emit=lambda message:None)
    if owned_hosts(root): raise RuntimeError('This installation host is still running. Retry after it stops.')
    if uninstall:
        remove_startup_task(root)
        remove_integrations(root,home=home)
    # The startup task could have run while cleanup was in progress.
    if owned_hosts(root): raise RuntimeError('This installation host restarted. Stop it and retry.')
