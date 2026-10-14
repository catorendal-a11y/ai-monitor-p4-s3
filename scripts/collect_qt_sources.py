"""Collect corresponding source for the unmodified Qt/PySide 6.10.2 runtime."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

SOURCES = {
    'qtbase': ('https://github.com/qt/qtbase/archive/000d6c62f7880bb8d3054724e8da0b8ae244130e.tar.gz',
               '2bffe7325cd32454a7a03548a4afad0e31b9cc3087a37867cb6c9f6ad4024f37'),
    'qtsvg': ('https://github.com/qt/qtsvg/archive/b925029db51aff0b17a48f5939cb83c27932d0cb.tar.gz',
              'b77b5463d71f86f81dff940cfcabb0803d61a39019a08a3f9e3c680c885806b5'),
    'qtimageformats': ('https://github.com/qt/qtimageformats/archive/076fb82c55321e42beeae62d9e3ca8c4bb71439c.tar.gz',
                      'def2a34d170375276dc27d093383b9da03be7031cdb9b9f1e797c67e12c98f75'),
    'pyside-setup': ('https://github.com/pyside/pyside-setup/archive/057cda38d369d042c59fd48544398cb917540718.tar.gz',
                     'e87189dc0fbce16d0203774fb369d43dabc8eb999fd946e5cbe7308d7c85cc56'),
}


def collect(destination: Path, cached: Path | None = None) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name, (url, digest) in SOURCES.items():
        filename = name + '-6.10.2.tar.gz'
        target = destination / filename
        source = cached / filename if cached else target
        if source.is_file():
            data = source.read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read(100 * 1024 * 1024 + 1)
        if len(data) > 100 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != digest:
            raise RuntimeError('Corresponding source verification failed: ' + name)
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
    print('Verified corresponding source for Qt/PySide 6.10.2.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('work/qt-source'))
    parser.add_argument('--cached', type=Path)
    args = parser.parse_args()
    collect(args.output, args.cached)
