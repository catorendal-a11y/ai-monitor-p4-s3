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

The current numeric backend does not store reliable session counts, active time or completed-task
results. Those values remain unavailable; token changes cannot establish them. The live-agent
screen's current session timers remain a separate source/domain.

One coalesced background reader queries the existing database with its hard SQLite deadline.
The serial owner sends one begin packet and at most eight provider packets, each under AIM1's
4095-byte bound. The receiver publishes only the complete transaction, preserves previous data
on a failed/expired transfer and clears the view when history is disabled. History has its own
snapshot and cannot change quota, token activity, live agents or permission authority.

Synthetic tests cover local-day boundaries, gaps, overflow, invalid schema, future timestamps,
source selection changes, receipt correlation, atomic transfer/replay/expiry and actual LVGL layout.
