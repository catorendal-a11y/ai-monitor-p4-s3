# P4 hardware measurements for v2

Measured on the owner's **JC4880P443C_I_W_Y** on 2026-10-13. The numerical artifact is
[p4-hardware-2026-10-13.json](../.ecc/benchmarks/p4-hardware-2026-10-13.json).
It contains no USB logs, MAC addresses, provider data or application backups.

The diagnostic applications used the current pinned P4 platform and SDK. Before changing
applications, the test verified firmware and ROM identity, checked the production partition table
and backed up the existing application locally. It wrote only the application partition and verified
its contents. The original application was restored and its normal USB startup verified afterwards.
The installed host was restarted on COM6. No C6 firmware or NVS was written.

## Isolated PPA rotation

The benchmark compares the existing CPU rotation with PPA on separate, 64-byte-aligned PSRAM
buffers. Both rotate an identical pseudorandom 800 x 480 RGB565 input into a 480 x 800 buffer.
The display driver is initialized, but the benchmark does not submit these buffers to the display.
PPA time includes waiting for its completion callback. Each output was compared byte-for-byte.

| Measurement | Result |
| --- | ---: |
| CPU rotation median, eight samples | 23,963 us |
| PPA rotation median, eight samples | 14,744 us |
| Pixel comparisons | 8 / 8 exact |
| Retained resources after cleanup | None |
| Speed ratio for this test | 1.625x |

**Decision:** retain CPU rotation in production. PPA is a promising candidate, but this isolated
result does not establish partial-region performance, display DMA/cache ownership, tearing behavior,
end-to-end frame rate or long-term reliability. These gates must pass before switching presentation.
No buffer-size or runtime asset-format decision follows from this one benchmark.

## Normal graphics counters in the diagnostic build

The boot screen was observed for 10,203 ms without a host or provider request. It submitted
13 flush chunks containing 1,294,650 pixels. Total CPU rotation time was 78,829 us; total driver
submission time was 61,490 us. Mean times per chunk were 6,063.77 us and 4,730 us respectively.
These are chunk counters, **not display FPS**, total LVGL render time or DMA completion timings.

Measured allocation: two LVGL draw buffers (1,536,000 bytes), rotation scratch (768,000 bytes)
and two display framebuffers (1,536,000 bytes). Physical PSRAM is 33,554,432 bytes and flash is
16,777,216 bytes. Startup/allocator readings remain separate from these physical capacities.
Internal/PSRAM bandwidth and alternative buffer sizes still need controlled target comparisons.

Read an already installed diagnostic build without enabling acceleration:

```text
python scripts/collect_graphics_baseline.py --board guition-p4 --port COM_NUMBER --seconds 10 --ppa --output work/graphics.json
```

## Standalone C6 result

The isolated C6 test reached `completed` within its deadline:

| Runtime result | Value |
| --- | --- |
| Detected coprocessor | ESP32-C6 |
| ESP-Hosted host version | 2.12.13 |
| Coprocessor firmware version | 2.12.22 |
| Controller init/enable RPC | Confirmed |

These different host/slave versions worked for the tested RPC calls. This is not HCI traffic,
encrypted GATT, pairing, reconnect or Claude Desktop validation. Production firmware still leaves
the coprocessor uninitialized and reports `not-probed` for its runtime radio state.
See [C6 bring-up](C6_BRINGUP.md) before further transport work.

## Collector fixes and validation

Opening USB can restart the board, and the isolated benchmark runs before the protocol task starts.
The hardware collector now waits on the same connection for up to three three-second identity
attempts. A wrong identity is never retried. A changed boot ID between identity and telemetry rejects
the measurement. The flashing harness also allows USB re-enumeration after watchdog reset.

The new C6 collector bounds the line buffer to 2,048 bytes, has a 15-second deadline, rejects
duplicate JSON fields, and exports only validated result fields. Querying `probe` does not retry
radio initialization. Failure/timeout results remain failures, never guessed capability support.
Synthetic tests cover these limits, fragmented replies, boot noise, partial writes, invalid types,
unverified identities, pixel mismatches and missing fields. All 324 Python regressions passed.

Next gates: target asset decode timing/peak memory, PSRAM cache/LVGL lifetime binding, production
transport isolation, authenticated BLE and the permission UI. SD and physical S3 remain untested.
