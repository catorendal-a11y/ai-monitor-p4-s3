# Standalone P4/C6 bring-up

## USB-only product decision (2026-10-13)

Bluetooth is permanently excluded from AI Monitor. The current standalone probe is identity/version
only (schema 2), with no Bluetooth controller initialization/enabling. Schema 1 measurements below
are historical evidence from before this decision; the collector keeps them readable. The remaining
controller-related procedure descriptions below apply only to that historical experiment.
The normal firmware does not initialize the radio. See [USB-only v2 transport](USB_LIVE_TRANSPORT.md).

The reported board is JC4880P443C_I_W_Y. The vendor specifies 32 MB PSRAM, 16 MB flash and an
ST7701S panel. `_Y` identifies the enclosed variant. These specifications are not runtime detection.

## Isolated test firmware

```text
python -m platformio run -e esp32p4-c6-probe
```

This developer-only environment replaces the normal monitor entry point. Its source filter includes
only `src/diagnostics/c6_probe_main.cpp`; it has no display/UI, AIM1 host, Claude integration, GATT
server, Wi-Fi association or scanning. It is excluded from release board/image selection.
Production images do not initialize the coprocessor.

The test checks the SDK's SDIO profile at compile time: clock 18, command 19, data 14/15/16/17,
reset 54 and configured ESP32-C6 target. These match the board-specific BSP's measured profile.
A different SDK pin configuration fails the build instead of silently using its defaults.
Do not apply this profile to another board revision without its wiring evidence.

One worker initializes NVS without erasing it, creates the SDK event loop, starts ESP-Hosted,
connects to its coprocessor, checks its announced target through `esp_hosted_get_cp_info`, reads
the actual slave firmware version, then requests controller initialization/enabling through Hosted RPC.
There is no coprocessor firmware update, credential input, bonding,
automatic retry or connection to an access point.

Send the ASCII line `probe` followed by newline over this standalone firmware's USB serial port to
read the result. The response includes host/slave version, RPC response state, controller state,
numeric error and deadline state. `configuredSlaveTarget` is separate from `detectedChip`, which is
populated only after the runtime Hosted identity check. `controllerEnableConfirmed` reports the
controller RPC acknowledgement, not an independently measured HCI/GATT connection.

The supervisor marks unfinished work as timed out after 10 seconds and does not retry. A blocking
SDK operation may remain active: the test does not forcibly delete its task or free driver resources.
Late completion remains timed out. This is an isolated SDK test, not a production bounded-driver
guarantee; a driver panic or incompatible slave firmware must be recorded on actual hardware.
Successful completion remains successful when the result is read later.

## Validation status and physical gate

Native tests cover deadline boundaries, completed results and clock rollover. Compilation validates
the pinned SDK APIs/pins. Neither proves actual C6 presence, compatible slave firmware, controller
operation, pairing or secure Claude transport. Flash only the explicitly
identified P4 port after stopping its host, and restore its production image afterwards. Never flash
an unrelated serial device or update the C6 merely to probe it.

Physical execution on JC4880P443C_I_W_Y completed on 2026-10-13. Runtime target detection reported
ESP32-C6, host version 2.12.13 and coprocessor version 2.12.22. Controller initialization/enabling
was acknowledged through RPC within the deadline. No C6 firmware was updated. The original P4
application was restored and its USB startup verified. HCI, GATT, secure pairing and Claude Desktop
remain untested; production does not initialize this test transport.
See [the measured results and limits](P4_HARDWARE_BENCHMARKS.md).

Read an already installed standalone test using the bounded collector:

```text
python scripts/collect_c6_baseline.py --port COM_NUMBER --output work/c6.json
```

The collector waits at most 15 seconds, discards oversized boot-noise lines, rejects malformed or
duplicate result fields and saves a whitelisted terminal result. A saved failure is not a successful
radio test. It sends only read-only `probe` queries; it cannot start initialization or flash firmware.

References: [vendor specification](https://www.guition.com/icms/upload/fb081940d6fc11f09850077a33e1404f/FTPData/UEditor/file/2026121/1768961095795/JC4880P443C_I_W%20Specifications-EN-V1.0.pdf),
[board-specific tested pin profile](https://github.com/ultramcu/guition-jc4880p4-bsp/blob/main/src/board_p4_pins.h),
[Espressif coprocessor version example](https://github.com/espressif/esp-hosted-mcu/tree/main/examples/system/get_cp_fw_version).
The BSP is supporting hardware evidence, not a dependency or a replacement for the working display driver.
