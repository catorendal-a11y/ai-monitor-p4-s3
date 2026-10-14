#!/bin/sh
set -eu
umask 077
task_project_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
task_python=${PYTHON:-python3}
task_venv_python="$task_project_root/.venv/bin/python"
if [ ! -x "$task_venv_python" ]; then
    "$task_python" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 or later is required"'
    "$task_python" -m venv "$task_project_root/.venv"
fi
"$task_venv_python" -m pip install --upgrade 'pip==26.2.1'
"$task_venv_python" -m pip install -r "$task_project_root/tools/requirements.txt"
if [ ! -e "$task_project_root/tools/aim_host.json" ]; then
    cp "$task_project_root/tools/aim_host.example.json" "$task_project_root/tools/aim_host.json"
fi
printf '%s\n' 'Setup complete. Open the menu with .venv/bin/python tools/aim_control.py'
printf '%s\n' 'Local configuration: tools/aim_host.json (ignored by Git). No hardware was flashed.'
