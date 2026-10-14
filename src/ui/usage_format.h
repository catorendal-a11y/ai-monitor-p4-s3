#pragma once
#include <cstdint>
#include <cstdio>
#include "../ai_monitor/ai_monitor.h"

inline void format_percent(float value, bool showsRemaining, char* text, size_t capacity) {
  const float remaining = showsRemaining ? value : 100.0f - value;
  if (value > 0 && value < 0.1f) snprintf(text, capacity, "<0.1%%");
  else if (value < 100 && value >= 99.95f) snprintf(text, capacity, ">99.9%%");
  else if (value != 0 && value != 100 && (value < 10 || value >= 99 || remaining < 10)) snprintf(text, capacity, "%.1f%%", static_cast<double>(value));
  else snprintf(text, capacity, "%.0f%%", static_cast<double>(value));
}

inline uint32_t reset_remaining(const aim::Row& row, uint32_t receivedMs, uint32_t now) {
  const uint32_t elapsed = (now - receivedMs) / 1000u;
  return elapsed < row.resetSeconds ? row.resetSeconds - elapsed : 0;
}

inline void format_countdown(uint32_t seconds, char* out, size_t capacity) {
  const uint32_t minutes = seconds / 60u + (seconds % 60u != 0);
  if (seconds == 0) snprintf(out, capacity, "Reset due");
  else if (minutes >= 1440) snprintf(out, capacity, "%lu d %lu h", (unsigned long)(minutes / 1440), (unsigned long)(minutes % 1440 / 60));
  else if (minutes >= 60) snprintf(out, capacity, "%lu h %lu m", (unsigned long)(minutes / 60), (unsigned long)(minutes % 60));
  else snprintf(out, capacity, "%lu m", (unsigned long)minutes);
}

inline bool refresh_busy(aim::RefreshState state) {
  return state == aim::RefreshState::requested || state == aim::RefreshState::waiting || state == aim::RefreshState::updating;
}

inline const char* refresh_hint(const aim::Snapshot& snapshot, uint32_t now) {
  if (!snapshot.hostPresent) return "PC host needed";
  if (!snapshot.manualRefreshSupported) return "Update PC host";
  if (snapshot.refreshState == aim::RefreshState::waiting) return "Queued";
  if (refresh_busy(snapshot.refreshState)) return "Updating...";
  if (now - snapshot.refreshCompletedMs < 10000u) {
    if (snapshot.refreshState == aim::RefreshState::complete) return "Data updated";
    if (snapshot.refreshState == aim::RefreshState::failed) return "Failed; see card";
  }
  return "";
}

inline bool local_minutes(const aim::Snapshot& snapshot, uint32_t now, uint16_t& result) {
  unsigned hour = 0, minute = 0;
  if (snapshot.displayTime[0] == '\0' || now - snapshot.displayTimeMs >= 43200000u ||
      sscanf(snapshot.displayTime, "%2u:%2u", &hour, &minute) != 2 || hour >= 24 || minute >= 60) return false;
  result = (hour * 60u + minute + (snapshot.displaySeconds + (now - snapshot.displayTimeMs) / 1000u) / 60u) % 1440u;
  return true;
}
