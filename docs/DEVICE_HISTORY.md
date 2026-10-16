# Today and device history

Open MENU > HISTORY. Choose a provider to see recorded tokens today, its latest observed model
quota window and a graph of 24 hourly buckets or seven local days. BACK and the graph-period
button stay fixed. Provider option identities cannot change while the dropdown is open.

![Native synthetic Today preview](images/device-history-24h.png)

Enable **local usage history** in the PC app's Host settings to collect observations. History is
off by default. The existing PC SQLite database remains the only persistent history store;
the display receives bounded numeric summaries, never a database, prompt or transcript.

Grey gaps mean no observation. They are not fabricated zero activity. Today uses the PC's local
midnight; daylight-saving days may last 23 or 25 hours. Future buckets are excluded. Samples
older than two minutes are not sent, and sample age contributes to the display's stale marker.

![Native synthetic seven-day preview](images/device-history-7d.png)

The quota line identifies its exact model window. Percentage-point change is shown only across
observations of the same window, reset and recorder epoch. Tool/MCP quotas are not mixed with
model quotas. This is observation history, not billing, forecasting or task progress.

The opt-in event journal stores fixed Codex/Claude/ZCode lifecycle events and hashed session identities
in the same local SQLite backend. Schema-1 numeric databases migrate transactionally to schema 2
without changing token/quota records. Hooks retain no prompt, tool arguments, output or permission hint.
The journal is capped at 50,000 events and 30 days; hook writes use a 20 ms lock timeout.

Today also shows observed sessions, active time, completed turns and failed turns when their real
events are available. Session counts require SessionStart. Turn counts require a prompt-start event
and its matching Stop/StopFailure. Waiting is excluded; intervals longer than 15 minutes are unknown.
Concurrent agent activity is unioned, rather than counted twice. Time means observed intervals,
not guaranteed total work time. Missing events/unsupported providers stay `--`.
These are turns, not completed tasks. TaskCreated/TaskCompleted hooks can precede a veto and do not
prove task success. Task totals remain unavailable until an integration supplies confirmed results.
The live-agent screen's current session timers remain a separate source/domain.

The PC History tab also displays a daily agent summary for the selected provider over seven or
30 local calendar days: observed sessions, active seconds, completed turns and failed turns.
Unknown values stay `--`. Days use local midnights, including 23/25-hour daylight-saving days.
An event exactly at midnight belongs to the next day, while a known activity interval ending
there can close the preceding day's active time. Provider changes clear the previous summary
and disable export until the new selection has finished loading.

CSV export includes these observed metrics even when no token or quota sample exists. Local
lifecycle dates use the explicit `local_date` column; numeric quota timestamps retain UTC.
Unknown metrics are omitted rather than exported as zero. A zero failed-turn count means real
completed/failed turn evidence was observed without failures; it is not a count of task success.

History protocol 2 adds a strictly bounded `agents` summary to each provider packet. Schema 1 is
still accepted; the host sends schema 1 to old historyProtocol-1 devices. No event log/database is
transferred to the display. Collection stops when local history is disabled or the recorder shuts down.

One coalesced background reader queries the existing database with its hard SQLite deadline.
The serial owner sends one begin packet and at most eight provider packets, each under AIM1's
4095-byte bound. The receiver publishes only the complete transaction, preserves previous data
on a failed/expired transfer and clears the view when history is disabled. History has its own
snapshot and cannot change quota, token activity, live agents or permission authority.

Synthetic tests cover local-day boundaries, gaps, overflow, invalid schema, future timestamps,
source selection changes, receipt correlation, atomic transfer/replay/expiry and actual LVGL layout.
