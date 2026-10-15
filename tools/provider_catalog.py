"""Explicit provider choices and their supported data sources."""
PROVIDERS = {
    'codex': ('Codex', 1, 'Automatic official CLI setup + local tokens and account quota'),
    'zcode': ('ZCode', 2, 'Local tokens + optional Z.AI coding-plan quota key'),
    'claude': ('Claude Code', 4, 'Local CLI token logs + optional official statusline quota bridge'),
    'gemini': ('Gemini CLI', 8, 'Local CLI tokens; automatic account quota not available'),
    'copilot': ('GitHub Copilot', 16, 'External numeric bridge required; SDK usage events are supported'),
    'cursor': ('Cursor', 32, 'External numeric bridge required; no automatic personal-quota adapter'),
    'antigravity': ('Antigravity', 64, 'External numeric bridge required; no automatic quota adapter'),
    'opencode': ('OpenCode', 128, 'Automatic local SQLite token usage; no remaining account quota'),
}

# Instructions are bundled and visible without a browser or a cloud request.
PROVIDER_SETUP = {
    'codex': ('1. Select Codex and save settings.\n2. Click Install / sign in Codex. If the CLI is missing, accept the '
              'official Windows installer; an existing client is reused. No manual terminal command is needed.\n'
              '3. Accept sign-in and complete the official browser flow with your own ChatGPT account. No OpenAI key '
              'is pasted into this app.\n4. Start host and check Live provider health. Local token records animate the robot; '
              'the CLI supplies available 5-hour and 7-day quotas. The Windows monitor includes its runtime; Python, '
              'Node.js and Git do not need to be installed separately. Internet and a browser are needed for first setup.\n'
              '5. Optional: Link Codex session events below. Review and trust the hooks using /hooks in a compatible '
              'Codex client, then restart the session. Events report waiting, editing and stopped turns; they never '
              'approve tools. Missing hook events remain unknown. Check Agent USB for confirmed display delivery.',
              'https://github.com/catorendal-a11y/ai-monitor-p4-s3/blob/main/docs/CODEX_SETUP.md'),
    'zcode': ('1. Install ZCode and sign in with your own account for local token activity.\n'
              '2. For quota percentages, create a Z.AI Coding Plan API key in your Z.AI account and paste it '
              'in the masked field below. Save settings.\n3. Without a key, local activity still works but quota '
              'is unavailable. The display lists only the windows your plan reports.\n'
              '4. Optional: Link ZCode session events for working, reading, editing, waiting and turn completion. '
              'Confirm Hooks is enabled in ZCode and start a new session. This observer never approves tools; '
              'subagent lifecycle is not reported by this adapter.',
              'https://docs.z.ai/devpack/quick-start'),
    'claude': ('1. Install Claude Code, sign in and use the CLI on this PC. Local token records are read automatically.\n'
               '2. For available subscription quotas, click Link Claude quota below. Existing custom '
               'statuslines are preserved.\n3. Restart Claude Code. '
               'A Claude API key alone does not supply subscription quotas.\n'
               '4. Optional: Link Claude session events for reported working, waiting and turn-complete states. '
               'This preserves other hooks and never approves commands. Restart Claude Code; display events require v1.19.0 firmware.',
               'https://code.claude.com/docs/en/statusline'),
    'gemini': ('1. Install Gemini CLI and sign in with your own account.\n2. Use recorded CLI sessions on this PC; '
               'the monitor reads their numeric token totals.\n3. This integration displays LOCAL activity. '
               'Automatic remaining account quota is unavailable; no key is entered in this app.',
               'https://geminicli.com/docs/cli/session-management/'),
    'opencode': ('1. Install OpenCode and connect your own provider in its official client.\n'
                 '2. Select OpenCode and save settings. The monitor reads numeric tokens from its local SQLite database automatically.\n'
                 '3. Use OpenCode normally, then click Check AI setup. This integration shows LOCAL activity; '
                 'remaining account quota is unavailable. No scripts or monitor API key are needed.',
                 'https://docs.opencode.ai/docs/'),
    **{key: (f'1. Select {name} and save settings.\n2. Connect your own integration to '
              f'AI-Monitor-Console.exe --ingest {key}, sending cumulative numeric token counters. '
              'See the bundled provider guide for the JSON format.\n3. This bridge shows LOCAL activity. '
              'Selecting the provider alone does not import editor activity or account quota.',
              'https://github.com/catorendal-a11y/ai-monitor-p4-s3/blob/main/docs/PROVIDERS.md#external-numeric-bridge')
       for key, name in [('copilot', 'GitHub Copilot'), ('cursor', 'Cursor'),
                         ('antigravity', 'Antigravity')]},
}


def selected_providers(config, legacy=False):
    values = config.get('providers')
    if 'providers' not in config:
        # Preserve the choices implied by old installed configs, never a new installation.
        values = ['codex'] + (['zcode'] if config.get('zai_key') else []) if legacy else []
    if not isinstance(values, list) or len(values) > len(PROVIDERS) or any(not isinstance(v, str) or v not in PROVIDERS for v in values):
        raise ValueError('providers must be a list of supported provider IDs')
    if len(set(values)) != len(values):
        raise ValueError('providers must not contain duplicates')
    return list(values)
