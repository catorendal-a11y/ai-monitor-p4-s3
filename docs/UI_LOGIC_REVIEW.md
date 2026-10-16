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
| Diagnostic export | Dialog cancel, worker execution, whitelist, protected atomic write | Excludes keys, raw errors, account identifiers, arguments and conversations |
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

Changed Python modules have 89% combined executable-line coverage. Actual LVGL UI
translation units have 97-100% executable-line coverage and 54-74% branch execution.
Coverage is a measure of exercised code, not a guarantee that no defect remains.

Full suite and version-specific package/device/endurance results are recorded with
the local rc10 delivery. Real hold/release/enrollment, physical unplug/suspend,
S3 panel/touch, clean Windows profile installation, genuine publisher signing and
the full eight-hour endurance result remain distinct validation gates.
