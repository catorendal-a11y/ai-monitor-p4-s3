# Real device screen over USB

In NOVA, open **Device > Device screen**. The running host remains the only USB serial owner.
The read-only result shows
the actual 800×480 RGB565 pixels rendered by the device, including normal overlays. It does not
show a desktop simulation or generated preview. The capture time and STALE marker distinguish
a captured image from live video. Return and choose **Device screen** again for a fresh capture;
opening the result does not start polling.

P4 pixels are captured before its manual portrait rotation; S3 pixels before its panel write.
One complete LVGL refresh is frozen, then sent in 600 correlated chunks of 640 pixels. Each chunk
uses bounded RGB565 little-endian RLE and Base64, with worst-case payload below AIM1's 4,095 bytes.
Request nonce, device frame ID, dimensions, chunk index, decoded lengths and deadlines must match.
Partial/inconsistent images are discarded. Normal quota, token and live metadata remain separate.

Capture allocates 768,000 image bytes plus 48,000 coverage bytes in PSRAM. This memory is scrubbed
and released after completion, expiry, disconnect or a protected screen. No buffer is allocated
until capture is requested. Allocation failure reports unavailable and leaves the normal UI running.
The image lease has a 30-second idle deadline and a 120-second absolute limit.

The Windows capture mailbox is restricted to the current user. It accepts only the fixed capture
operation; no caller path, network endpoint, shell command or virtual touch. Responses are bounded,
nonce-matched, removed after display/cancellation and expire after 60 seconds. No images enter
usage history or Git. Enrollment/code-comparison and permission screens are excluded and scrubbed;
the viewer cannot substitute for physical security confirmation.

Native tests exercise the actual pinned LVGL partial RGB565 compositor and top layer, incomplete
refreshes, overlap coverage, worst-case chunks, strict inputs, replay, expiry and protected screens.
PC tests validate decoding/correlation, storage isolation, cancellation and host scheduling without
provider/model requests. Hardware transfer timing is recorded separately in V2_VALIDATION.md.
