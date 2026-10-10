"""Real standalone Codex installation smoke test on a disposable Windows CI runner."""
import argparse
import os
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import codex_support as support


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-ci', action='store_true', required=True)
    parser.add_argument('--helper', type=Path, help='Optional compiled console helper to test instead of Python source')
    args = parser.parse_args()
    # The vendor installer can update the user PATH. Never run this test on a
    # developer's PC; its entire runner/profile must be disposable.
    if os.name != 'nt' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('This test requires a disposable GitHub-hosted Windows runner.')
    scratch = Path(os.environ['RUNNER_TEMP']).resolve()
    assert scratch.is_absolute() and scratch.is_dir() and not scratch.is_relative_to(ROOT.resolve())
    with tempfile.TemporaryDirectory(prefix='codex-onboarding-', dir=scratch) as directory:
        target = Path(directory).resolve()
        assert target.is_relative_to(scratch) and not target.is_relative_to(ROOT.resolve())
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
            if args.helper:
                monitor = target/'monitor'; (monitor/'tools').mkdir(parents=True)
                helper = monitor/'AI-Monitor-Console.exe'
                shutil.copy2(args.helper.resolve(strict=True), helper)
                (monitor/'tools/aim_host.json').write_text(json.dumps({'providers':['codex'],
                    'board':'guition-p4','port':'COM9999','interval_s':240,'zai_key':''}))
                result = subprocess.run([str(helper),'--setup-codex'], input='y\nn\n',
                    text=True, capture_output=True, timeout=600)
                # No real login was performed, so no credential output should exist.
                if result.returncode:
                    print(result.stdout); print(result.stderr)
                assert result.returncode == 0, 'Compiled Codex setup failed'
                assert 'Install the official Codex CLI now?' in result.stdout
                assert 'Open official Codex sign-in now?' in result.stdout
                assert 'Skipped' in result.stdout
            else:
                answers = iter(('y', 'n')); prompts = []
                def answer(question):
                    prompts.append(question)
                    return next(answers)
                # Install for real, check login for real, decline personal sign-in.
                assert support.setup_codex(answer) is False
                assert len(prompts) == 2 and 'Install' in prompts[0] and 'sign-in' in prompts[1]
            command = support.codex_command()
            assert command == [str(binary/'codex.exe')], 'Standalone native CLI was not discovered'
            subprocess.run(command+['--version'], check=True, timeout=15)
            status = subprocess.run(command+['login','status'], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            assert status.returncode != 0, 'A clean test profile unexpectedly has account credentials'
        finally:
            os.environ.clear(); os.environ.update(previous)
    route = 'compiled EXE' if args.helper else 'source'
    print(f'PASS ({route}): real standalone CLI install/discovery with no Node or Python on PATH; personal sign-in was declined. No model turn or USB write was requested.')


if __name__ == '__main__': main()
