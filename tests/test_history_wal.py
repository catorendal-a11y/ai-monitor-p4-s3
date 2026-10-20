"""History database runs in WAL mode: the terminal's reads never block the host's writes."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from usage_history import connect, clear_history


def mode(database):
    return database.execute('PRAGMA journal_mode').fetchone()[0]


class HistoryWalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_new_database_is_created_in_wal_mode_and_readers_see_it(self):
        connect(self.folder, create=True).close()
        with closing(connect(self.folder)) as reader:
            self.assertEqual(mode(reader), 'wal')

    def test_reader_is_not_blocked_by_an_open_write_transaction(self):
        with closing(connect(self.folder, create=True)) as writer:
            writer.execute('BEGIN EXCLUSIVE')
            writer.execute("INSERT INTO tokens VALUES('codex',1,5)")
            with closing(connect(self.folder)) as reader:
                # Rollback-journal mode raises "database is locked" for readers during an exclusive lock.
                self.assertEqual(reader.execute('SELECT COUNT(*) FROM tokens').fetchone()[0], 0)
            writer.commit()
        with closing(connect(self.folder)) as reader:
            self.assertEqual(reader.execute('SELECT COUNT(*) FROM tokens').fetchone()[0], 1)

    def test_existing_rollback_database_is_migrated_by_the_next_writer(self):
        connect(self.folder, create=True).close()
        with closing(sqlite3.connect(self.folder / 'history.db')) as legacy:
            legacy.execute('PRAGMA journal_mode=DELETE')
        with closing(connect(self.folder)) as reader:
            self.assertEqual(mode(reader), 'delete')
        connect(self.folder, create=True).close()
        with closing(connect(self.folder)) as reader:
            self.assertEqual(mode(reader), 'wal')

    def test_unknown_file_is_still_rejected_and_left_unchanged(self):
        path = self.folder / 'history.db'; path.write_bytes(b'fixture unknown file')
        with self.assertRaises((ValueError, sqlite3.DatabaseError)):
            connect(self.folder, create=True)
        self.assertEqual(path.read_bytes(), b'fixture unknown file')

    def test_clear_history_leaves_no_rows_in_the_write_ahead_log(self):
        with closing(connect(self.folder, create=True)) as writer:
            with writer:
                writer.execute("INSERT INTO tokens VALUES('codex',1,12345)")
        # An idle reader (the terminal between refreshes) keeps the WAL file alive after the
        # writer closes, so deleted rows would otherwise stay readable in history.db-wal.
        idle_reader = connect(self.folder); self.addCleanup(idle_reader.close)
        idle_reader.execute('SELECT COUNT(*) FROM tokens').fetchone()
        clear_history(self.folder)
        wal = self.folder / 'history.db-wal'
        self.assertTrue(not wal.exists() or wal.stat().st_size == 0, 'deleted rows remain in the WAL')
        with closing(connect(self.folder)) as reader:
            self.assertEqual(reader.execute('SELECT COUNT(*) FROM tokens').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
