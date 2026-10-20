"""Single version source for host tools and build scripts.

FW_VERSION lives in src/config.h (firmware). Every build script parses it
through this module so encoding and format handling cannot drift between
copies. Host/runtime code (the Codex handshake; the desktop app later) imports
HOST_VERSION instead: frozen executables have no src/config.h beside them, so
the constant is embedded here. tests/test_project_version.py and the release
build both assert HOST_VERSION == FW_VERSION, which keeps firmware, installer,
executable resources and release notes on one version.
"""
from pathlib import Path
import re

# Runtime identity of the Windows host tools. Must equal FW_VERSION in
# src/config.h; the sync test and the release build enforce this.
HOST_VERSION = 'v1.19.1-rc25'

_VERSION_DEFINE = re.compile(r'#define\s+FW_VERSION\s+"(v\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.]+)?)"')


def fw_version(root):
    """Read FW_VERSION from src/config.h under root.

    UTF-8 with BOM tolerance (editors on Windows add one) and pre-release
    tolerant ('v1.19.0-rc1' parses instead of crashing the caller).
    """
    path = Path(root) / 'src' / 'config.h'
    try:
        text = path.read_text(encoding='utf-8-sig')
    except OSError as error:
        raise ValueError('src/config.h is unreadable: ' + str(error)) from None
    match = _VERSION_DEFINE.search(text)
    if not match:
        raise ValueError('No #define FW_VERSION "vX.Y.Z" found in src/config.h')
    return match.group(1)


def numeric_version(version):
    """Strip the leading 'v': 'v1.18.3' -> '1.18.3' (installer and handshake style)."""
    return version[1:] if version.startswith('v') else version


def version_tuple(version):
    """Numeric (major, minor, patch) from 'vX.Y.Z[-suffix]'; the suffix is ignored."""
    match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)(?:[-+].*)?', version)
    if not match:
        raise ValueError('Unsupported version format: ' + version)
    numbers = tuple(int(part) for part in match.groups())
    if any(part > 65535 for part in numbers):
        raise ValueError('Windows version components must be between 0 and 65535')
    return numbers


def windows_version_resource(version):
    """PyInstaller --version-file content generated from the project version.

    Replaces the hand-maintained scripts/windows_version.txt, which drifted
    behind the firmware version for several releases.
    """
    numbers = (*version_tuple(version), 0)
    return (
        '# Generated from FW_VERSION by tools/project_version.py; do not edit.\n'
        'VSVersionInfo(\n'
        '  ffi=FixedFileInfo(filevers=' + repr(numbers) + ', prodvers=' + repr(numbers) + ',\n'
        "                   mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
        "  kids=[StringFileInfo([StringTable('040904B0', [\n"
        "    StringStruct('CompanyName', 'AI Monitor contributors'),\n"
        "    StringStruct('FileDescription', 'AI Monitor Windows companion'),\n"
        "    StringStruct('FileVersion', '" + numeric_version(version) + "'),\n"
        "    StringStruct('ProductName', 'AI Monitor'),\n"
        "    StringStruct('ProductVersion', '" + numeric_version(version) + "'),\n"
        "    StringStruct('LegalCopyright', 'AI Monitor contributors. MIT; third-party licenses included.')\n"
        '  ])]), VarFileInfo([VarStruct(\'Translation\', [1033, 1200])])]\n'
        ')\n'
    )
