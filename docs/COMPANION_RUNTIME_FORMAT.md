# Companion runtime format and cache checkpoint

The P4 experiment selects **raw LZ4 blocks** for the experimental version-1 runtime cache,
decoded into the existing **RGB565+A8** layout. Built-in NOVA/ORBIT remain the production fallback.
The normal P4 companion UI now uses these built-in compressed frames through a startup-allocated
PSRAM cache. External runtime pack ingestion remains disabled; S3 retains the raw built-ins.
This is not a physical S3 validation or a change to the existing USB/AIM1 domain.

## Physical comparison

All twelve committed poses were exported with byte/hash checks, then measured on the identified
JC4880P443C_I_W_Y at 360 MHz. Each pose/codec ran five decodes; SHA-256 verified every output.
Timing excludes hashing. The benchmark is standalone, without display, BLE or SD workloads.

| Codec | Payload for all 12 poses | Median of pose medians | Slowest pose median | Extra decoder state used |
| --- | ---: | ---: | ---: | ---: |
| Raw copy | 3,349,656 bytes | 11,350.5 us | 13,637 us | 0 |
| Byte RLE | 1,925,271 bytes | 11,703.5 us | 13,523 us | 0 |
| LZ4 | 519,579 bytes | 12,033.5 us | 13,740 us | 0 |
| Zlib/Deflate | 249,490 bytes | 12,792 us | 14,269 us | 10,992 bytes |

These are medians, not p95/max latency. The standalone benchmark reserves one inflater for its
batch; the last column identifies state used by each codec, not total per-trial allocation.
State excludes task stack, library/allocator overhead and the decoded output buffer.
Exact working-UI peak memory still needs integration measurements.
The data artifact is [p4-assets-2026-10-13.json](../.ecc/benchmarks/p4-assets-2026-10-13.json).

LZ4 saves **2,830,077 bytes (84.5%)** of delivered image payload versus raw data. It decodes close
to raw-copy time, without Deflate's persistent inflater state. That leaves internal RAM available
for live-agent UI and secure USB permission work. RLE offers much less compression for similar measured latency.
Deflate remains a valid later delivery alternative if smaller transfers become more valuable than
the extra state/decoder path. No fictional throughput or S3 timing is inferred from the P4 results.

Delivery is one versioned manifest per companion, with at most eight frames and strict bounds.
The aggregate payload above is not a twelve-frame runtime manifest. The earlier prototype folder
comparison includes metadata and places the LZ4 alternative below the conservative 1.8 MB limit;
real single-companion pack tooling must still verify its complete delivered size.

## Actual PSRAM cache experiment

The new boot-time `PsramCache` uses two 64-byte-aligned slots, a pinned LVGL LZ4 decoder and
actual mbedTLS SHA-256 checks of both encoded and decoded bytes. A separate P4 experiment loaded
all six NOVA frames while pinning the active frame across replacements:

- Reserved pool: **630,528 bytes** (two 315,264-byte slots).
- Six verified loads: **117,783 us total**, approximately **19,630.5 us per load**, including both hashes.
- Bad encoded hash rejected; truncated LZ4 with a valid hash of the truncated input rejected.
- The pinned active image remained hash-correct after both failures.

Allocation happens during initialization, not lazily in `load` or rendering. The pool and frame
descriptors must outlive their bindings; all bindings must detach before destroying an owner.
Production P4 allocates this pool once at startup. All twelve poses remain available compressed.
One raw work pose per companion stays in flash as a safe fallback if allocation, validation or
decoding fails; thumbnails and provider logos are unchanged. External packs remain disabled.

## Rendering and ownership

`CompanionRenderer` now accepts a generic descriptor/origin view while preserving the existing
NOVA/ORBIT API. It also restores the desired source if another owner changed the LVGL image.
`ImageBinding` owns two stable descriptors and explicit frame pins. It rejects another image/cache
target and rejects sharing a boolean pin between bindings. Swapping source drops the old LVGL
cache entry before retiring its storage; detach restores the fallback and its original canvas origin.
Object deletion and binding destruction release ownership. Source pixels cannot alias the decode
destination, and unknown poses or oversized encoded frames are rejected.

This binding supports the current synchronous, single software draw unit only. Other LVGL task/draw
models fail closed until an explicit completion fence is implemented. Caller/UI-task ownership is
mandatory. No transport callback can update LVGL, and no permission/live state enters `aim::Snapshot`.

Native LVGL tests cover swaps, conflicting owners, delete/destructor cleanup, fallback origins,
same-slot position updates, changed external sources and invalid indices. The real cache backend
was tested on P4 memory. The production renderer additionally verifies pixel-identical decoding
of all twelve built-ins in native LVGL, stable crop origins, no per-tick decode, pin retirement and
raw fallback on failed integrity validation. Working-UI measurement is recorded below when verified.

## Reproduce the developer experiment

```text
node scripts/export_companion_frames.cjs --output work/asset-benchmark-input
python scripts/export_asset_benchmark.py --frames work/asset-benchmark-input --robot nova --output work/asset-target-fixtures/asset_fixtures.h --cc gcc
python -m platformio run -e esp32p4-asset-benchmark
python scripts/collect_asset_baseline.py --port COM_NUMBER --robot nova --output work/asset-target-nova.json
```

Repeat with `--robot orbit` and rebuild before collecting. This environment is deliberately excluded
from release board/image selection. Flash only the identified P4 after stopping its host, verify the
production partition table and keep a local application backup. Restore its normal application
afterwards. Never flash these fixtures as a normal installer image or overwrite C6/NVS.

Remaining gates: physical S3, versioned animation manifests and authenticated pack activation.
MicroSD is deferred until measured pack sizes require it. Permissions retain their separate
fail-closed USB/local-IPC gates. No Bluetooth product transport is planned.

## Rebuild compressed built-ins

After regenerating SVG artwork, run `python scripts/generate_companion_lz4.py --cc gcc`.
The generator reads the committed raw pixels, uses the pinned LVGL LZ4 encoder, verifies a
byte-identical round trip and emits encoded/decoded SHA-256 digests. Production decoding verifies
both digests before binding a frame. The two-slot cache may reuse a verified resident frame.
A failed frame is not retried every UI tick.

Hardware diagnostics report allocation, decoded-frame count, failures and maximum measured
decode-plus-bind time. Startup checkpoints include the normal display/LVGL/companion path.

## Normal P4 firmware measurement - 2026-10-13

The identified P4 was backed up, app-only flashed, digest verified and watchdog restarted.
The existing USB/live metadata handshake and bounded hardware report passed.

| Metric | Measured result |
| --- | ---: |
| Previous app image | 4,611,328 bytes |
| New app image | 2,347,328 bytes |
| Actual app saving | 2,264,000 bytes (49.1%) |
| Free app partition | 4,206,272 bytes |
| Companion cache allocation | 630,528 bytes |
| PSRAM free after companion initialization | 29,079,616 bytes |
| Largest free PSRAM block | 28,835,828 bytes |
| Internal heap free after companion initialization | 172,612 bytes |
| First-frame verified decode and LVGL bind | 20,513 us |
| Companion initialization complete (boot uptime) | 1,411 ms |

The cache reported active with zero failures. This measures one startup frame in the normal UI,
not p95 latency, all-pose physical timings, touch responsiveness or a soak test. Both SHA-256 checks
are included in the frame timing. The raw reserve poses explain why firmware savings are smaller
than the standalone all-payload compression savings.

Evidence: [normal P4 measurement](../.ecc/benchmarks/p4-production-companion-2026-10-13.json).
