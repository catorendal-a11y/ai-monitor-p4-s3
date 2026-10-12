# Companion improvements and measured priorities

The related-project review informs this project; another project's feature list is not a claim
that its hardware, security or software has been validated here. USB remains the display transport.

## Included in the local v1.19.0 candidate

- Provider-specific connection checklist and an observation test without model requests.
- Optional local numeric history, quota charts and reset-aware consumption estimates.
- Explicit observational Claude session hooks. Other AIs retain recorded token activity.
- Family-wide transparent cropping for all six NOVA poses and all six ORBIT poses.
  Original canvas origins are retained by `CompanionRenderer`; thumbnails and desktop artwork
  are unchanged. RGB565+A8 frame payload falls from 4,396,320 to 3,349,656 bytes,
  saving 1,046,664 bytes (23.8%) without dropping nontransparent source pixels.
- Apply a recovered first brightness load once, while preserving any explicit user change.
- Report a local reader taking more than 15 seconds. USB and quota polling continue; the app
  recommends restarting the host if activity does not resume. It does not create replacement
  threads or claim to recover an indefinitely blocked reader automatically.
- Include free PSRAM in the bounded device information reply, alongside existing free heap.

Cropping reduces flash data; it does not reduce the display framebuffer, prove a runtime RAM
improvement, or compress/decode frames into PSRAM. Native tests cover both board interfaces and
pose origins. Real P4 operation and physical S3 validation are separate checks.

## Next reliability work

1. Physical gesture tests: drag out/back in, failed touch read, reordered providers while held.
2. Long P4 soak: resets, reconnects, free heap/PSRAM trends, touch and backlight behavior.
3. Windows Job Objects with kill-on-close for explicitly owned quota workers and descendants.
   Existing cleanup uses scoped process enumeration; it cannot guarantee containment after every
   unexpected parent exit. Never terminate unrelated processes by name.
4. Enforceable process deadlines for local readers if bounded I/O still proves insufficient.

## Optional extensions requiring separate evaluation

- Additional companion packs with validated sizes, origins and bounded allocation. Compression
  and PSRAM caching need measurements before committing to a decoder or a storage format.
- A compact tray quota glance and reset notifications using existing cached observations.
- Provider incident/status indicators that distinguish account quota from service outages.
- A safe update checker, then verified downloads. Firmware updates remain a separate user action.

BLE/C6 transport and approval of AI tool commands from the screen change the security and hardware
scope substantially. They are not enabled by observational session reporting and are not part of
this candidate. Graphics acceleration should follow measured rendering bottlenecks, rather than
the mere availability of P4 hardware features.

Related examples: [Desktop Buddy](https://github.com/tech-nickk2/claude-desktop-buddy),
[CodexBar](https://github.com/steipete/CodexBar) and
[ESP32 AI Monitor](https://github.com/tobymarks/esp32-ai-monitor).
