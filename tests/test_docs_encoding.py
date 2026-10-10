import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Lead bytes produced when UTF-8 text is saved through a Windows-1252 round trip
# (for example an em dash or middle dot becoming "â€”" or "Â·").
MOJIBAKE_LEADS = ('\u00c2', '\u00c3', '\u00e2')


def double_encoded_lines(text):
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        for index, character in enumerate(line):
            if character in MOJIBAKE_LEADS and index + 1 < len(line) and ord(line[index + 1]) > 127:
                found.append(number)
                break
    return found


class DocsEncodingTests(unittest.TestCase):
    def test_tracked_text_contains_no_double_encoded_characters(self):
        files = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                               text=True, encoding='utf-8', errors='replace')
        self.assertEqual(files.returncode, 0, 'git ls-files must list the tracked files')
        tracked = files.stdout.split()
        self.assertTrue(tracked, 'the repository must track files')
        failures = []
        for name in tracked:
            path = ROOT / name
            try:
                text = path.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                continue  # binaries and generated assets are out of scope
            for number in double_encoded_lines(text):
                failures.append(f'{name}:{number}')
        self.assertEqual(failures, [],
            'Double-encoded characters found (save files as UTF-8): ' + ', '.join(failures[:20]))


if __name__ == '__main__':
    unittest.main()
