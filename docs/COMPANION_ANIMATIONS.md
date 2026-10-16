# Companion animation format 2

NOVA and ORBIT now use the same allocation-free animation player above CompanionRenderer and
the verified P4 LZ4 cache. Working/attention/success/error sequences select multiple existing poses;
resting/warning/critical remain stable poses. Each mood has its own timing and loop policy. Success
is nonlooping and holds its final frame. Changing companion or mood restarts the appropriate clip.
Testing animation is selected only from a fresh explicit TESTING event for a selected provider.
Token increases never establish testing, task success or other detailed phases.

The schema separates named image assets from mood sequences. Strict limits are:

- Version exactly 2, RGB565A8, raw or LZ4; at most 8,192 manifest bytes.
- Up to 16 unique assets, 8 distinct moods and 16 steps per sequence.
- Each step references an existing asset ID and has a 40–60,000 ms duration.
- Explicit boolean loop; required fallback mood with a real sequence.
- One global union crop/origin across all frames, within the existing 430×284 canvas.
- Exact encoded/decoded SHA-256, encoded-byte limits and decoded width×height×3 bytes.
- Safe lowercase filenames, no traversal/reserved device names, unknown/duplicate fields rejected.

Example sequence inside `animations`:

```json
{"mood":"working","loop":true,"frames":[
  {"id":"work_1","durationMs":150},
  {"id":"work_2","durationMs":150},
  {"id":"work_3","durationMs":150}
]}
```

`frames` declares every referenced asset's `id`, `file`, width/height/origin, encoded/decoded byte
counts and both hashes. Top-level fields are version, name, format, codec, fallback, frames and
animations. Supported moods: resting, working, testing, attention, success, error, warning, critical.

Parsing publishes only a complete valid manifest. Playback handles clock rollover, skipped UI
ticks and one-shot completion without allocating, decoding or touching transport. Asset ownership,
cache pins/hash verification and raw fallback remain in the existing renderer/cache domains.

## External packs on P4

Open the desktop **Companions** tab and choose **Import and use pack**. The ZIP must contain
`manifest.json` and exactly its declared frame files, with optional `LICENSE` and `README.md`.
Archives are never extracted or executed. Duplicate members/fields, unsafe names, unknown files,
oversize data, invalid crops, timings, hashes or compressed blocks are rejected before selection.
The library holds at most 16 packs. **Use built-in NOVA / ORBIT** restores normal rendering;
**Remove unused pack** cannot remove the selected pack or the user's original import file.

The original archive/notices and a verified content-addressed payload stay under the PC app's
`tools/companions/` directory, excluded from Git and release source exports. The host restores the
selected pack after a display restart. Durable storage is on the PC; the display holds its current
pack in RAM. No display filesystem formatting, NVS image storage or microSD is required.

P4 reserves two 2 MiB encoded banks and one bounded frame-validation buffer at startup. Staging
cannot overwrite the active bank. Every asset's encoded/decoded hash and exact decoded size is
checked before publication. The UI owner detaches the old LVGL/cache binding before switching
banks. The existing two-slot cache retains image pins and its raw built-in fallback; rendering
does not allocate. The bank/scratch allocation adds about 4.35 MiB of reserved PSRAM, separately
from the existing decoded frame cache. Allocation failure leaves built-in rendering available.

Transfers use bounded `pack_*` commands through the existing serial owner, with boot ID, random
transaction nonce, exact offsets, receipts and timeout. A complete transfer is not reported active
until the UI owner adopts it. Failed or incomplete replacements retain the previous companion.
Pressing a built-in companion on the display overrides the pack; the host reports that override
rather than immediately reinstalling it. Use the desktop selection to restore the external pack.
S3 does not advertise external runtime support.

Original example packs can be exported reproducibly with:

```text
python scripts/build_companion_packages.py --output work/companion-packs
```

This uses the committed original NOVA/ORBIT pixels and animation timings, pinned LZ4 block
compression, exact hashes and the unchanged original MIT notice. It does not copy provider logos
or grant trademark rights. Source/native tests are distinct from physical rendering evidence.
