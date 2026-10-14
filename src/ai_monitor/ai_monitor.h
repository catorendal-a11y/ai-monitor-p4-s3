#pragma once
// AI Monitor receiver - displays AI provider usage limits on this panel.
//
// Speaks the USB-serial protocol of tobymarks/esp32-ai-monitor (plain line
// mode plus AIM1 framing): the Windows/macOS companion app polls the local
// CodexBar CLI and streams newline-JSON usage frames; this module parses them
// and publishes a snapshot for the dashboard. Data only ever arrives over USB
// CDC - the device never needs Wi-Fi and never sees cloud credentials.

#include <cstdint>
#include <cstddef>
#include <cstring>

namespace aim {

static constexpr size_t kMaxRows = 3;   // protocol: usage.rows[] is capped at 3
static constexpr size_t kMaxViews = 8;  // protocol: set_views accepts up to 8 windows

// One usage row ("Current session (5h)", percent, when it resets).
struct Row {
  bool valid = false;
  float usedPercent = 0.0f;      // 0..100 as sent by the host
  char title[36] = {0};
  char resetsShort[20] = {0};    // "15:00" or "31 Oct 23:45" from resetsAt
  uint32_t windowMinutes = 0;    // 0 = unknown
  bool hasResetCountdown = false;
  uint32_t resetSeconds = 0;
};

// Last frame received for one view (window). viewIndex addresses these.
struct ViewData {
  bool valid = false;
  bool notice = false;           // host sent a notice instead of usage rows
  bool informational = false;    // activity-only/setup message, not an API error
  bool fetching = false;         // host is mid-poll for this provider
  bool showsRemaining = false;   // percentMode "remaining"
  char providerKey[16] = {0};    // wire key, e.g. "claude"
  char providerLabel[16] = {0};  // display label, e.g. "CLAUDE"
  char message[160] = {0};       // bounded full notice, available in details
  uint8_t rowCount = 0;
  Row rows[kMaxRows];
  uint32_t receivedMs = 0;       // millis() of the last frame for this view
  bool hasUsage = false;         // includes retained data during a failed fetch
  uint32_t quotaReceivedMs = 0;  // only a successful usage frame advances this
};

enum class RefreshState : uint8_t { idle, requested, waiting, updating, complete, failed };
enum class HostActivity : uint8_t { idle, fetching, updated, failed };

struct Snapshot {
  ViewData views[kMaxViews];
  char viewKeys[kMaxViews][16];  // keys from the last set_views, "" if unused
  char displayTime[6] = {0};     // "HH:mm" from the last frame envelope
  uint32_t displayTimeMs = 0;    // millis() when the clock was synchronized
  uint8_t displaySeconds = 0;
  uint8_t viewCount = 0;
  bool viewsConfigured = false;  // host sent set_views at least once
  uint8_t activeView = 0;
  bool automaticViews = false;
  uint16_t viewIntervalSeconds = 10;
  uint32_t viewRevision = 0;
  bool hostPresent = false;      // companion completed the info handshake
  uint32_t hostSeenMs = 0;
  uint32_t lastFrameMs = 0;
  uint32_t frameCount = 0;
  bool manualRefreshSupported = false;
  RefreshState refreshState = RefreshState::idle;
  uint32_t refreshId = 0;
  uint32_t refreshRequestedMs = 0;
  uint32_t refreshCompletedMs = 0;
  char refreshMessage[64] = {0};
  HostActivity activity = HostActivity::idle;
  uint32_t activityMs = 0;
  char activityMessage[96] = {0};
  bool tokenUsageKnown = false, tokenUsageSeen = false;
  uint8_t tokenSourceMask = 0;
  uint32_t tokenIdleSeconds = 0, tokenActivityMs = 0;
  uint64_t lastTokenDelta = 0;
};

// Wire key -> display label + brand color. Header-only so the dashboard can
// use it anywhere.
struct ProviderStyle {
  const char* key;
  const char* label;
  uint32_t color;
  uint8_t activityMask;
};

inline const ProviderStyle* provider_style(const char* key) {
  static const ProviderStyle kTable[] = {
      {"codex", "CODEX", 0x10A37Fu, 1},
      {"zcode", "Z CODE", 0x14B8A6u, 2},
      {"claude", "CLAUDE", 0xD97757u, 4},
      {"antigravity", "ANTIGRAVITY", 0x4E8CFFu, 64},
      {"gemini", "GEMINI", 0x4285F4u, 8},
      {"copilot", "COPILOT", 0xA371F7u, 16},
      {"cursor", "CURSOR", 0x9AD1D4u, 32},
      {"opencode", "OPENCODE", 0xB9B9C7u, 128},
  };
  for (const auto& entry : kTable) {
    if (key && std::strcmp(entry.key, key) == 0) return &entry;
  }
  return nullptr;
}

// Create the receiver task (call once from setup() after Serial.begin).
void begin();
// Apply queued host controls on the UI task, the owner of backlight writes.
void apply_pending_controls();
// Thread-safe snapshot copy, protected by a short FreeRTOS critical section.
Snapshot read();
// Queue an on-device refresh request for the USB owner task.
void request_refresh();

}  // namespace aim
