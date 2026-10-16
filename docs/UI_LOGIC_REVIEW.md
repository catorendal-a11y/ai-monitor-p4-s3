# rc11 device navigation follow-up

User feedback exposed a presentation defect missed by the rc10 review: selected
providers were rendered among real sessions on Agents. Rc11 removes those rows,
shows a short session ID and distinguishes no observed sessions from no live feed.
Home, Usage and Agents now share fixed primary destinations at the bottom; the
current destination is outlined. Usage retains two full-size cards. MENU remains
fixed and secondary screens retain their return-to-caller behavior.

Native regressions cover direct navigation, identical button geometry across all
three screens, empty/disconnected feeds, quota-provider independence, multiple
session identities, paging, expiry, rollover and session/event timing. Synthetic
screens do not establish physical touch validation. The rc10 review below is
historical evidence; its passing tests did not establish satisfactory usability.

# rc10 UI logic review

Scope: desktop action/state flows and the firmware UI. Evidence is scoped to source
review, synthetic Qt/LVGL execution and separately recorded installed-device checks.
It does not certify every hardware interaction or provider model.

| Surface | Logic checked | Result in rc10 |
| --- | --- | --- |
| Setup and saved selection | Board/provider/port validation, unsaved changes, automatic start, wrong-device health | Selection stays explicit; stale or mismatched status does not confirm a connection |
| Desktop actions | Busy controls, asynchronous completion, stale status epochs, error recovery, close/cancel/tray | Main-thread UI updates and one action worker retained; failure does not complete a pending close |
| Provider setup | Selected providers, exact-owned hook removal, alternate Claude configuration root, custom metadata | Uninstall preserves unrelated settings and hook metadata |
| Provider health | Quota versus activity, last check versus last success, expired health | Separate timestamps and bounded states; saving credentials never establishes working quota |
| Diagnostic export | Dialog cancel, worker execution, whitelist, protected atomic write | Excludes keys, raw errors, account identifiers, arguments and conversations; expires device receipts independently during reconnect |
| Desktop history | Selection generation, quota-window identity, unknown gaps, chart/table/CSV dates | Local calendar boundaries shared across views; UTC observations unchanged |
| History clearing | Explicit confirmation, stop failure, clear rollback, prior host restoration, pending read | Revoke before transactional deletion; no database unlink; no old results accepted during clear |
| Companion library | Import/selection, uncertain activation, saved board/port identity, asynchronous status | Activation requires matching fresh device status; custom packages remain data-only |
| Device screen mirror | Request/response identity, stale reply, cancellation and closure | Read-only pixels through existing serial owner; protected screens stay excluded |
| Home and Usage | Simultaneous quota/session states, token-only activity, stale values, fixed targets | Quota errors remain visible; Recent activity does not claim agent work |
| Agents | Event freshness, reported duration and state | Expired metadata says Last and uses muted presentation |
| Menu, details and history | Return navigation, drag cancellation, rebinding while pressed, dropdown identity, unknowns | Existing touch geometry retained; unknown values remain unknown |
| Settings and notifications | Draft/cancel/save, save feedback, quota warning acknowledgment, timing rollover | UI ownership and fail-closed persistence retained |
| Permission/enrollment | Opt-in, physical comparison, request identity, hold/release, visibility and delivery gates | Production approval remains disabled; synthetic tests do not establish physical validation |
| Upgrade/uninstall | Exact installation host/task/integrations, old-version compatibility, cleanup failure | New helper stops old host; uncertain cleanup blocks uninstall; private data retained |

Changed Python modules have 89% combined executable-line coverage. The nine main
firmware UI modules have 97-100% executable-line coverage; connection UI has 89%.
The main modules take 54-74% of branch outcomes at least once (gcov), including
compiler-generated paths. The permission wrapper has its own separate native target.
Coverage is a measure of exercised code, not a guarantee that no defect remains.

Full suite and version-specific package/device/endurance results are recorded with
the local rc10 delivery. Real hold/release/enrollment, physical unplug/suspend,
S3 panel/touch, clean Windows profile installation, genuine publisher signing and
the full eight-hour endurance result remain distinct validation gates.


## Visual follow-up

Reviewed all main screens and sub-screens using 75 native 800x480 states and 19
Qt views/dialogs with real Segoe fonts at minimum desktop size. This includes
provider paging and precision, remaining/used labels, offline/last-good values,
long errors, session versus token activity, old agent observations, history gaps,
warning/critical overlays, notification pages, brightness choices, night minutes,
quota-window selection, themes, enrollment comparison and blocked/held permissions.
Desktop views cover setup, provider instructions, host preferences, firmware
operation/confirmation, help, history, companions, the checklist and empty mirror.

The visual review exposed two additional defects after the initial source audit:

- History actions exceeded the minimum desktop width. Selection/refresh and
  export/clear now use two rows; real-font geometry asserts no horizontal overflow.
- SAVED / SAVE FAILED could be covered by alert and night overlays. Feedback now
  stays in front of every active settings overlay and outside its action buttons.
  Tests verify stacking, position and visibility; the final failure frame was
  inspected rather than relying on the stored label text alone.

Snapshot data and comparison codes used in this review are synthetic. Physical
screen capture verifies only the actual current P4 frame, not unperformed touch
flows. No virtual approval/touch path was added.
