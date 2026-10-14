#pragma once
#include <cstdint>
#include <cstdio>
#include "../ai_monitor/ai_monitor.h"

inline bool token_signal_fresh(const aim::Snapshot& snapshot, uint32_t now) {
  // The host allows a 15-second poll interval. Budget another full interval
  // for scheduling and local I/O; USB loss still invalidates immediately.
  return snapshot.hostPresent && snapshot.tokenUsageKnown && now - snapshot.tokenActivityMs < 35000u;
}

inline const char* token_tracking_label(const aim::Snapshot& snapshot, uint32_t now) {
  if (!snapshot.hostPresent) return "TRACKING / PC host offline";
  if (!snapshot.tokenUsageKnown) return "TRACKING / no counters";
  if (!token_signal_fresh(snapshot, now)) return "TRACKING / signal lost";
  switch (snapshot.tokenSourceMask) {
    case 1: return "TRACKING / Codex";
    case 2: return "TRACKING / ZCode";
    case 3: return "TRACKING / Codex + ZCode";
    case 4: return "TRACKING / Claude";
    case 8: return "TRACKING / Gemini";
    case 16: return "TRACKING / Copilot";
    case 32: return "TRACKING / Cursor";
    case 64: return "TRACKING / Antigravity";
    case 128: return "TRACKING / OpenCode";
    case 0: return "TRACKING / sources unknown";
    default: return "TRACKING / multiple sources";
  }
}

inline void format_token_count(uint64_t count, char* out, size_t capacity) {
  // Integer arithmetic avoids rounding away small increases and uint64 overflow.
  static constexpr uint64_t units[] = {1000ULL, 1000000ULL, 1000000000ULL,
      1000000000000ULL, 1000000000000000ULL, 1000000000000000000ULL};
  static constexpr char suffixes[] = "KMBTQE";
  for (int i = 5; i >= 0; --i) {
    if (count < units[i]) continue;
    snprintf(out, capacity, "%llu.%u%c", static_cast<unsigned long long>(count / units[i]),
             static_cast<unsigned>((count % units[i]) / (units[i] / 10)), suffixes[i]);
    return;
  }
  snprintf(out, capacity, "%llu", static_cast<unsigned long long>(count));
}

inline void token_activity_hint(const aim::Snapshot& snapshot, uint32_t now, char* out, size_t capacity) {
  if (!token_signal_fresh(snapshot, now)) {
    snprintf(out, capacity, "Token signal unavailable / tap to say hi");
  } else if (!snapshot.tokenUsageSeen) {
    snprintf(out, capacity, "Waiting for a token increase / tap to say hi");
  } else {
    const uint64_t seconds = static_cast<uint64_t>(snapshot.tokenIdleSeconds) + (now - snapshot.tokenActivityMs) / 1000u;
    if (seconds < 60) snprintf(out, capacity, "Last increase: %llu s ago / tap to say hi", static_cast<unsigned long long>(seconds));
    else if (seconds < 3600) snprintf(out, capacity, "Last increase: %llu min ago / tap to say hi", static_cast<unsigned long long>(seconds / 60));
    else snprintf(out, capacity, "Last increase: %llu h ago / tap to say hi", static_cast<unsigned long long>(seconds / 3600));
  }
}
