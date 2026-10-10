import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from token_activity import TokenReporter
import aim_host


class TokenActivityTests(unittest.TestCase):
    def test_temporarily_absent_request_is_not_counted_twice(self):
        clock = {"now": 100.0}
        reporter = TokenReporter(home=Path("unused"), clock=lambda: clock["now"])
        data = {"codex": {}, "zcode": {"request": 2000}}
        with patch.object(reporter, "read_counts", side_effect=lambda provider, path: data[provider]):
            self.assertEqual(reporter.poll()["delta"], 0)
            clock["now"] += 2; data["zcode"] = {}
            self.assertEqual(reporter.poll()["delta"], 0)
            clock["now"] += 2; data["zcode"] = {"request": 2000}
            self.assertEqual(reporter.poll()["delta"], 0)
            clock["now"] += 2; data["zcode"]["request"] += 50
            self.assertEqual(reporter.poll()["delta"], 50)

    def test_request_cache_is_bounded(self):
        clock = {"now": 100.0}
        reporter = TokenReporter(home=Path("unused"), clock=lambda: clock["now"])
        reporter.MAX_TRACKED = 3
        data = {"codex": {}, "zcode": {"a": 100, "b": 200}}
        with patch.object(reporter, "read_counts", side_effect=lambda provider, path: data[provider]):
            reporter.poll()
            clock["now"] += 2; data["zcode"] = {"c": 300, "d": 400}
            self.assertEqual(reporter.poll()["delta"], 700)
            self.assertEqual(len(reporter.previous["zcode"]), 3)
            clock["now"] += 2; data["zcode"] = {"d": 450, "e": 500}
            self.assertEqual(reporter.poll()["delta"], 550)
            self.assertEqual(len(reporter.previous["zcode"]), 3)

    def test_history_baseline_changes_reset_and_missing_sources(self):
        clock = {"now": 100.0}
        reporter = TokenReporter(home=Path("unused"), clock=lambda: clock["now"])
        data = {"codex": {"a": 1000}, "zcode": {"b": 2000}}
        with patch.object(reporter, "read_counts", side_effect=lambda provider, path: data[provider]):
            first = reporter.poll()
            self.assertEqual((first["delta"], first["seen"], first["sources"]), (0, False, 3))
            self.assertIsNone(reporter.poll())
            clock["now"] += 2; data["codex"]["a"] = 1200
            used = reporter.poll()
            self.assertEqual((used["delta"], used["idleSeconds"], used["seen"]), (200, 0, True))
            clock["now"] += 2; data["zcode"]["c"] = 50
            self.assertEqual(reporter.poll()["delta"], 50)
            clock["now"] += 2; data["codex"]["fork"] = 90000
            self.assertEqual(reporter.poll()["delta"], 0)  # do not count inherited thread history
            clock["now"] += 2; data["codex"]["a"] = 100
            self.assertEqual(reporter.poll()["delta"], 0)  # counter reset is not token consumption
            clock["now"] += 2; data["codex"]["a"] = 110
            self.assertEqual(reporter.poll()["delta"], 10)
            clock["now"] += 300
            self.assertEqual(reporter.poll()["idleSeconds"], 300)
            clock["now"] += 2; data["codex"] = data["zcode"] = None
            unavailable = reporter.poll()
            self.assertFalse(unavailable["known"])

    def test_readonly_numeric_database_adapters(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            for provider, relative, schema, insert in [
                ("codex", ".codex/state_5.sqlite", "CREATE TABLE threads(id TEXT,tokens_used INTEGER,updated_at_ms INTEGER)", "INSERT INTO threads VALUES('a',123,1)"),
                ("zcode", ".zcode/cli/db/db.sqlite", "CREATE TABLE model_usage(id TEXT,computed_total_tokens INTEGER,started_at INTEGER)", "INSERT INTO model_usage VALUES('b',456,1)")]:
                path = home / relative; path.parent.mkdir(parents=True, exist_ok=True)
                with sqlite3.connect(path) as database:
                    database.execute(schema); database.execute(insert)
                database.close()
                before = path.read_bytes()
                self.assertEqual(list(TokenReporter.read_counts(provider, path).values()), [123 if provider == "codex" else 456])
                self.assertEqual(path.read_bytes(), before)
            self.assertIsNone(TokenReporter.read_counts("codex", home / "missing.sqlite"))

    def test_windowless_logging_still_writes_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "host.log"
            with patch.object(aim_host, "LOG_PATH", path), patch.object(aim_host.sys, "stdout", None):
                aim_host.LOG("background host started")
            self.assertIn("background host started", path.read_text(encoding="utf-8"))

    def test_expensive_numeric_query_is_interrupted_without_changing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'large.sqlite'
            for provider, table, count_column, time_column in (
                    ('codex', 'threads', 'tokens_used', 'updated_at_ms'),
                    ('zcode', 'model_usage', 'computed_total_tokens', 'started_at')):
                with self.subTest(provider=provider):
                    with sqlite3.connect(path) as db:
                        db.execute(f'CREATE TABLE {table}(id TEXT,{count_column} INTEGER,{time_column} INTEGER)')
                        db.executemany(f'INSERT INTO {table} VALUES (?,?,?)',
                                       [(str(i), i, i) for i in range(1000)])
                    db.close()
                    before = path.read_bytes()
                    # Simulate an exhausted execution budget during a real unindexed sort.
                    with patch('token_activity.time.monotonic', side_effect=[0.0, 1.0]):
                        self.assertIsNone(TokenReporter.read_counts(provider, path))
                    self.assertEqual(path.read_bytes(), before)
                    self.assertIsNotNone(TokenReporter.read_counts(provider, path))


if __name__ == "__main__":
    unittest.main()
