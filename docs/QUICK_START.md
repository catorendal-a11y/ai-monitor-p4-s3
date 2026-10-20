# Quick start

Follow [LimitBuddy terminal installation](TERMINAL.md). The PC application is now the terminal
command `limitbuddy`; the graphical Windows app and EXE installer are retired.

Choose and save the board, USB port and providers in Settings, then Start host.
Use Overview/Device to check actual USB status and Agents to check observational links.
No board/provider is selected automatically and setup never flashes hardware.

See [provider setup](PROVIDERS.md) and [development](DEVELOPMENT.md).

## Reading the display

- **Header:** the tightest quota window over every selected AI, for example "29% left / CODEX Week".
- **Cards:** an amber or red edge means a window is low or critical. The faint ticks in each bar are a
  25 / 50 / 75 % scale, not warning thresholds.
- **White marker on a bar:** where an even burn would be by now, from the window length and its reset
  time. With "left" bars, a fill shorter than the marker means the quota is going faster than the
  window; longer means you are ahead. It is hidden when the reset time is unknown.
- **Ring on the NOVA screen:** the same tightest window as a ring with its percentage, provider and
  window name. It is hidden without a fresh host and quota reading.
- **History chart:** weekday names come from the host's local date; observed days show their token
  count above the bar and the newest bar is solid. Unobserved days stay a thin tick, never zero.
