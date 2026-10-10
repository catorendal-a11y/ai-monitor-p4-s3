"""Real standalone Codex installation smoke test on a disposable Windows CI runner."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import codex_support as support


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-ci', action='store_true', required=True)
    parser.parse_args()
    # The vendor installer can update the user PATH. Never run this test on a
    # developer's PC; its entire runner/profile must be disposable.
    if os.name != 'nt' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('This test requires a disposable GitHub-hosted Windows runner.')
    scratch = ROOT/'work'; scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='codex-onboarding-', dir=scratch) as directory:
        target = Path(directory).resolve()
        assert target.is_relative_to(scratch.resolve())
        home = target/'state'; home.mkdir()
        local = target/'local'; local.mkdir()
        roaming = target/'roaming'; roaming.mkdir()
        binary = target/'bin'
        previous = dict(os.environ)
        try:
            for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'CODEX_ACCESS_TOKEN',
                        'OPENAI_IDENTITY_TOKEN_FILE', 'OPENAI_WORKLOAD_IDENTITY_CONTEXT'):
                os.environ.pop(key, None)
            os.environ.update(CODEX_HOME=str(home), CODEX_INSTALL_DIR=str(binary),
                CODEX_NON_INTERACTIVE='1', LOCALAPPDATA=str(local), APPDATA=str(roaming),
                PATH=str(Path(os.environ['SystemRoot'])/'System32'))
            assert support.codex_command() is None, 'The test unexpectedly found an existing CLI'
            answers = iter(('y', 'n')); prompts = []
            def answer(question):
                prompts.append(question)
                return next(answers)
            # Install for real, check login for real, decline personal sign-in.
            assert support.setup_codex(answer) is False
            command = support.codex_command()
            assert command == [str(binary/'codex.exe')], 'Standalone native CLI was not discovered'
            assert len(prompts) == 2 and 'Install' in prompts[0] and 'sign-in' in prompts[1]
            subprocess.run(command+['--version'], check=True, timeout=15)
            status = subprocess.run(command+['login','status'], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            assert status.returncode != 0, 'A clean test profile unexpectedly has account credentials'
        finally:
            os.environ.clear(); os.environ.update(previous)
    print('PASS: real standalone CLI install/discovery with no Node or Python on PATH; personal sign-in was declined. No model turn or USB write was requested.')


if __name__ == '__main__': main()
