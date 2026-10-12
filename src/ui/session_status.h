#pragma once
#include "ai_monitor/ai_monitor.h"

struct SessionStatus {
  bool known = false;
  uint8_t sources = 0;
  uint16_t running = 0, waiting = 0, completed = 0, error = 0;
};

inline SessionStatus session_status(const aim::Snapshot& snapshot, uint32_t now,
                                    uint8_t requested_sources = 255u) {
  SessionStatus result{};
  if (!snapshot.hostPresent || now - snapshot.sessionActivityMs >= 35000u) return result;
  uint8_t selected = requested_sources;
  if (snapshot.viewsConfigured) {
    uint8_t configured = 0;
    for (size_t i = 0; i < snapshot.viewCount && i < aim::kMaxViews; ++i) {
      const auto* style = aim::provider_style(snapshot.viewKeys[i]);
      if (style) configured |= style->activityMask;
    }
    selected &= configured;
  }
  for (size_t i = 0; i < snapshot.sessionCount && i < aim::kMaxViews; ++i) {
    const auto& item = snapshot.sessions[i];
    if (!(item.source & selected)) continue;
    result.known = true; result.sources |= item.source;
    result.running += item.running; result.waiting += item.waiting;
    result.completed += item.completed; result.error += item.error;
  }
  return result;
}

inline SessionStatus session_status(const aim::Snapshot& snapshot, uint32_t now, const char* provider) {
  const auto* style = aim::provider_style(provider);
  return session_status(snapshot, now, static_cast<uint8_t>(style ? style->activityMask : 0u));
}
