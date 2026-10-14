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

External pack installation/activation is still disabled. This schema/player does not pretend to
provide storage staging, atomic pack activation or microSD. Public runtime loading requires those
independent gates; built-in animations already run through the production rendering path.
