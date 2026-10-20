"""A readable, stable name and color for an opaque session id: no content, identical on PC and device."""
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from session_identity import HUES, identity

NAME = re.compile(r'[A-Z][a-z]{2,6} [A-Z][a-z]{2,6}')


class SessionIdentityTests(unittest.TestCase):
    def test_the_same_id_always_gets_the_same_name_and_hue(self):
        session = 'a' * 64
        self.assertEqual(identity(session), identity(session))

    def test_name_is_two_short_words_that_fit_the_device_label(self):
        for number in range(500):
            label, hue = identity(f'{number:064x}')
            self.assertRegex(label, NAME)
            self.assertLessEqual(len(label), 15)        # the device label buffer holds 15 characters
            self.assertTrue(0 <= hue < HUES)

    def test_names_and_hues_are_spread_out(self):
        pairs = {identity(f'{number:064x}') for number in range(3000)}
        self.assertGreater(len({label for label, _ in pairs}), 450)   # of 576 possible names
        self.assertEqual({hue for _, hue in pairs}, set(range(HUES)))

    def test_known_ids_keep_their_names_across_versions(self):
        # Changing the algorithm would rename every running session: pin it.
        self.assertEqual(identity('opaque_1'), ('Eager Badger', 9))
        self.assertEqual(identity('0' * 64), ('Dusty Gecko', 0))
        self.assertEqual(identity('a91f2c08'), ('Jolly Beaver', 4))

    def test_only_opaque_identifiers_are_accepted(self):
        for bad in ('', 'x' * 65, 'has space', 'ünicode', 'a/b', None, 7, b'abc'):
            with self.assertRaises(ValueError):
                identity(bad)


if __name__ == '__main__':
    unittest.main()
