"""Effective Claude profile paths shared by explicit setup and numeric readers."""
import os
from pathlib import Path


def config_root(home=None):
    # Explicit homes are fixture/application injections, isolated from user env.
    if home is not None:
        return Path(home)/'.claude'
    return Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home()/'.claude').expanduser()
