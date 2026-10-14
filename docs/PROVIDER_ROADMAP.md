# Provider expansion plan

Status: implementation plan, not a claim that bridge-only providers work automatically. Baseline: v1.12.0, eight selectable tools, no first-run provider defaults, automatic local activity for Codex/ZCode/Claude Code/Gemini CLI, optional Claude quota bridge, and external numeric bridges for the remaining choices.

Start a new coding task with `AGENTS.md`, `docs/PROVIDERS.md`, this plan and the relevant step. Run the Python suite for host changes; build firmware and run `scripts/run_tests.py --ui` for firmware/UI work. Every step should fit one reviewable PR. Do not implement every provider in one change.

## Shared constraints

- Follow the existing registry/config/polling/frame patterns in `tools/provider_catalog.py`, `tools/aim_host.py`, `tools/token_activity.py`, `tools/local_activity.py` and `tools/telemetry_bridge.py`.
- Preserve explicit selections. An unselected provider must not be polled or scanned. Missing credentials must not silently enable another tool.
- Report capability and actual availability separately. Context occupancy, billing estimates, request counts and plan quota percentages are distinct metrics.
- Use documented interfaces or reviewed local formats. Never scrape browser cookies, decrypt app credentials or infer a personal quota from an organization report.
- Fixtures must be synthetic and record sizes bounded. Keep prompts, authentication files, session transcripts, logs and raw identifiers out of commits/releases. Persist only whitelisted numeric bridge data or explicitly opted-in fixed lifecycle states/timestamps with hashed IDs.
- Test first-sample baselines, repeated IDs, streaming updates, counter decreases, corrupt/partial records, staleness, reconnects, permission failure and a source that is missing entirely.
- Firmware currently has eight source bits, eight views and three quota rows per view. A ninth provider is blocked on a versioned protocol-capacity change; do not reuse another source bit.
- Preserve provider branding, quota warning meanings, theme/companion settings and the current RGB565+A8 asset strategy. v1.12.0 uses about 85% of the application partition; measure added firmware assets before accepting them.

## Step 1 - Harden automatic onboarding (current Codex baseline)

Implemented in this task: selected-Codex setup locates or installs the official CLI, offers user-mediated login, respects CODEX_HOME and reads plan quota via account/rateLimits/read. It reuses the CLI credential store and keeps the legacy file adapter only when no CLI is available. It never starts a model turn or copies credentials into monitor configuration.

Remaining work for one follow-up PR: test installed-client version/OS coverage with consenting testers, make update/retry/cancellation statuses uniform, exercise keyring/file auth and API-key-only quota failure, and show capability/readiness without revealing account details. Keep installer/sign-in as explicit user actions. Rollback: disable the onboarding action while preserving source selections, the CLI account path and legacy fallback.

Validation: synthetic subprocess tests first, then opt-in Windows/macOS/Linux account checks. Do not install/login during CI. Exit: a beginner can finish or cancel every supported path with selections and account storage preserved. Dependency: none.

## Step 2 - A consistent capability/readiness contract

Context: the registry currently contains a label, source bit and human-readable support text. Multiple readiness/error conditions otherwise live in individual adapters. Avoid a second provider architecture.

Files: the existing provider catalog, host/control/bridge modules, selection tests and provider guide.

Tasks: extend registry entries with explicit activity/quota capabilities and setup requirements; return a typed readiness result from the existing adapters; distinguish unsupported, missing source, setup required, stale and temporarily failed. Keep the wire's activity-only informational behavior; no percentage for an unsupported quota.

Validation: all host tests; one selected source working while another is missing; change selection while connected; zero implicit provider defaults. Firmware/UI changes, if necessary, require a release firmware build, `python scripts/run_tests.py --ui`, and actual UI screenshots.

Exit: Status, setup and the panel agree about readiness for every provider. Rollback: retain existing adapter results and support text until each consumer is migrated.

Dependency: none. Priority: before adding more automatic bridges.

## Step 3 - Claude and Gemini onboarding robustness

Context: local activity already works from bounded CLI log parsing. Claude quota comes from documented statusline rate-limit fields; an existing custom statusline is preserved. Gemini has local usage/telemetry, but this release has no automatic account-quota adapter.

Files: `tools/local_activity.py`, `tools/telemetry_bridge.py`, `tools/aim_control.py`, corresponding tests and documentation.

Tasks: add selected-provider source discovery checks and version-specific fixture coverage; make optional Claude bridge install/remove idempotent, with rollback to its backup and no replacement of custom hooks; evaluate Gemini's documented hooks/OpenTelemetry as an opt-in numeric bridge. Do not modify the user's CLI settings except through a reviewed, explicit setup action.

Validation: incomplete JSONL, log rewrite/truncation, repeated IDs, excluded subagent duplication, Unicode paths, permission errors, install/remove round trip, and bridge output containing no prompt/credential text. Treat reported usage as observed activity rather than exact billing.

Exit: a beginner can see why a selected source is unavailable and enable the optional bridge safely. Rollback: restore backed-up app settings and retain current local activity parsing.

Dependency: Step 2. Can be reviewed separately from Step 4.

## Step 4 - GitHub Copilot SDK bridge package

Context: Copilot is selectable but needs an external bridge. The official SDK exposes live `assistant.usage`, accumulated session metrics and account quota; live events are not equivalent to all VS Code/editor activity.

Files: a focused `integrations/copilot/` example/helper, the existing numeric bridge, provider tests, capability entry and provider guide.

Tasks: supply a runnable SDK bridge that accumulates per-session tokens and forwards the existing numeric stdin schema; use official account-quota fields only when accessible in the same authenticated context; label coverage as SDK sessions. Avoid requiring the repository's GitHub token or performing model requests during installation/tests.

Validation: fixture event replay, resume/deduplication, restarted cumulative counters, temporary host outage, rejected credentials, unlimited entitlements and quota reset dates. Full packaged executable smoke test; no live paid/model request in CI.

Exit: SDK users can install/configure the bridge through a documented flow; personal editor-wide monitoring is not advertised. Rollback: disable the helper; existing external ingestion remains usable.

Dependency: Step 2.

## Step 5 - OpenCode local adapter (implemented in v1.17.0)

Scope update, 2026-10-10: the user requested setup from the app. Official OpenCode V1/V2 SQLite projections and normalized cache/reasoning semantics were verified. A bounded read-only numeric adapter now covers those schemas, with hashed IDs, imported-session baselines and synthetic tests. Unsupported schemas stay unavailable; remaining account quota is not supported. The SDK bridge remains a possible extension. See PROVIDERS.md for primary references.

Files: `integrations/opencode/`, existing bridge/capability modules, fixtures and provider documentation.

Tasks: research the official SDK's usage events/metrics; create a small numeric-only bridge with supported-version detection; preserve session identity and deduplicate updates. Avoid parsing arbitrary chat databases until the local schema and access scope are verified.

Validation: versioned numeric fixtures, tool/streaming repeats, cache accounting, session resume, missing server/auth and bounded queue behavior. Never equate API cost with subscription quota.

Exit: a documented automatic bridge covers the declared SDK/client versions. If no verified data surface exists, retain bridge-only status and record the blocker. Rollback: remove the automatic connector without reusing its source bit.

Dependency: Step 2. Can proceed after Copilot independently.

## Step 6 - Cursor and Antigravity feasibility gates

Context: Cursor's documented Admin API concerns team administration. Antigravity has an interactive usage/quota command. Neither fact alone establishes a supported personal real-time quota or token stream.

Files: `docs/PROVIDERS.md`, this roadmap, and only then a focused integration module with fixtures.

Tasks: check current primary documentation for each product, supported permissions, account scope and numeric data semantics. Write a short go/no-go note for each. Implement one provider per PR only after a stable permitted data source is verified. Retain explicit external-bridge support where automatic access is unavailable.

Validation: prove personal/team scope is labeled correctly, unknown permissions fail without fabricated numbers, and source selection causes no unrelated login/cookie access. Verify staleness/rate limits before presenting values as live.

Exit: either a reviewed automatic adapter with tests, or a documented limitation and supported manual bridge. Rollback: keep the existing choice and external ingestion; remove only the unproven automatic path.

Dependency: Step 2. Research can run independently; implementations require review of the feasibility notes.

## Acceptance for every PR

1. Source and setup guide identify what is automatic and what remains user-mediated.
2. Run `python -m unittest discover -s tests -p "test_*.py"`; build firmware and run `python scripts/run_tests.py --ui` for firmware/UI changes.
3. Confirm other selected providers continue working, no implicit default was introduced, and no personal data entered Git or the release ZIP.
4. A maintainer with the relevant application performs the opt-in integration check. Synthetic fixtures are not described as physical/account validation.
5. Update the capability table, roadmap status and release notes together. Roll back by disabling the new adapter; preserve local configuration and companion/theme settings.

## Ordering and changes to the plan

Recommended order: Step 1, Step 2, then separate Claude/Gemini and Copilot PRs, followed by OpenCode and the Cursor/Antigravity decisions. Steps 3-6 share registry/bridge files; do not merge conflicting edits without a rebase and regression run. This task writes the plan; it does not implement those future provider expansions.

To change scope, record the reason and evidence, update dependencies and acceptance criteria, and keep unfinished work explicitly planned/blocked rather than calling it supported. Any future provider beyond the current eight needs a separate protocol-capacity PR before registration.

Primary references: [Codex authentication](https://learn.chatgpt.com/docs/auth), [Codex state environment](https://learn.chatgpt.com/docs/config-file/environment-variables), [Claude statusline](https://code.claude.com/docs/en/statusline), [Gemini hooks](https://geminicli.com/docs/hooks/reference/), [Copilot SDK usage](https://github.com/github/copilot-sdk/blob/main/docs/features/usage-and-billing.md), [OpenCode SDK](https://docs.opencode.ai/docs/sdk/), [Cursor Admin API](https://docs.cursor.com/en/account/teams/admin-api), [Antigravity usage](https://www.antigravity.google/docs/cli/commands/usage/).
