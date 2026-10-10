# Desktop performance check

Controlled Windows offscreen measurements on October 10, 2026 compared tagged v1.17.2 with v1.18.1. Each version used the same synthetic Copilot/COM9999 configuration. Token-source polling was mocked; no accounts, provider API calls or USB writes were used. A 20 ms event-loop probe also contributes to the reported CPU use.

| Measurement | v1.17.2 | v1.18.1 |
| --- | --- | --- |
| Warm startup to constructed widgets, reverse-order repeat | 163 ms | 168 ms |
| Visible RSS, two samples | 67.9–68.9 MiB | 69.3–69.9 MiB |
| Minimized RSS, two samples | 68.2–69.4 MiB | 69.3–70.0 MiB |
| Event-loop delay p95, visible/minimized | About 2 ms | About 2 ms |
| UI status/token refreshes in a 10 s minimized phase | 4 | 0 |
| UI status/token refreshes in a 5 s minimized phase | 2 | 0 |

CPU was below 1% of one core in all fixture phases. At this low load, Windows CPU-time tick quantization and the probe dominate short samples, so the data does not establish a precise CPU percentage reduction. The reliable improvement is that hidden windows stop redundant GUI token/database polling while the independent host continues monitoring. Lightweight tray status runs every ten seconds. Restore starts a fresh local activity baseline instead of displaying a catch-up burst.

The first baseline startup took 454 ms and the first candidate 180 ms; DLL/file cache conditions differed. These values are not evidence of a startup speedup. The reverse-order warm repeat was effectively unchanged. Memory increased by about 1–2 MiB in the controlled source test; packaged/native rendering and real provider databases need separate measurements.

Run the reproducible fixture from the public source:

```text
python scripts/benchmark_desktop.py --seconds 10 --output work/desktop-performance.json
```

This measures GUI work, not network/provider latency or physical display rendering. It must not generate model requests or use real credentials. Runtime measurements on a user's PC should retain logs and identifiers locally, not include them in public exports.

## Packaged Windows check

The downloaded v1.18.1 installer was checked against its release hashes and installed over v1.17.2. Ten-second native GUI samples used existing numeric activity sources. GUI RSS was approximately 102 MiB visible and 107 MiB hidden; the hidden sample recorded 0.16% of one core. No GUI TCP listener was present. The same independent host processes remained connected through minimize, restore and Quit, with both selected providers reporting fresh quota health. These are short operational samples, not a controlled CPU/startup comparison, and they do not measure a long-term memory leak.

## Numeric-query execution budget

Codex and ZCode reads now use SQLite's progress handler with a 100 ms execution budget, matching the existing bounded OpenCode adapter. The row limit alone did not bound an unindexed sort. A finite synthetic one-million-row recursive numeric projection took 433–453 ms in three reads with the v1.18.1 adapter; the bounded adapter interrupted it in 106–111 ms. The database bytes were unchanged. Normal numeric queries remained readable; timeout reports an unavailable source rather than partial or fabricated usage.

The budget limits SQLite execution, not all filesystem access or lock waiting. Connection lock waiting retains its separate 150 ms timeout. Progress callbacks are periodic, so 100 ms is not a hard wall-clock guarantee. This stress fixture establishes bounded handling of a slow source, not a speedup for normal provider databases. Synthetic regression tests cover interruption, later successful reads and unchanged database contents.
