"""Readable, stable names for opaque session ids.

Sessions are identified by hashes, which nobody can recognize on a desk display. This derives a
two-word name and one of 12 colors from the id alone, so the PC terminal and the device show the
same one. It carries no content: nothing but the opaque id goes in, and the same id always gives
the same name. Collisions are possible (576 names x 12 colors) and are acceptable for the handful
of sessions shown at once; the id's tail stays visible as the exact identity.
"""
import re

ADJECTIVES = ('Amber', 'Azure', 'Brisk', 'Calm', 'Coral', 'Dusty', 'Eager', 'Fuzzy', 'Gentle', 'Golden',
              'Hazel', 'Jolly', 'Lucky', 'Mellow', 'Nimble', 'Olive', 'Plucky', 'Quiet', 'Rusty', 'Silver',
              'Sunny', 'Swift', 'Tidy', 'Witty')
ANIMALS = ('Badger', 'Beaver', 'Bison', 'Crane', 'Dolphin', 'Falcon', 'Ferret', 'Fox', 'Gecko', 'Heron',
           'Ibis', 'Koala', 'Lemur', 'Lynx', 'Marten', 'Otter', 'Panda', 'Parrot', 'Puffin', 'Raven',
           'Seal', 'Tiger', 'Walrus', 'Wombat')
HUES = 12
_OPAQUE = re.compile(r'[A-Za-z0-9_-]{1,64}')


def _fnv1a(data):
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def identity(session_id):
    """(name, hue) for an opaque session id; raises ValueError for anything else."""
    if not isinstance(session_id, str) or not _OPAQUE.fullmatch(session_id):
        raise ValueError('Invalid session id')
    value = _fnv1a(session_id.encode('ascii'))
    count = len(ADJECTIVES)
    return f'{ADJECTIVES[value % count]} {ANIMALS[value // count % len(ANIMALS)]}', value // (count * len(ANIMALS)) % HUES
