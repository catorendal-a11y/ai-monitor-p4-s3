#pragma once
#include "../ai_monitor/ai_monitor.h"
#include "../app_settings.h"
#include "quota_alert.h"
#include <cstdio>
#include <cstring>

inline void quota_window_label(uint32_t minutes, const char* title, char* text, size_t size) {
  if (minutes == 300) snprintf(text, size, "5 HOURS");
  else if (minutes == 10080) snprintf(text, size, "7 DAYS");
  else if (minutes >= 40320 && minutes <= 44640) snprintf(text, size, "%s", title && strstr(title, "MCP") ? "MONTHLY MCP" : "MONTHLY");
  else if (minutes && minutes % 1440 == 0) snprintf(text, size, "%lu DAY%s", static_cast<unsigned long>(minutes / 1440), minutes == 1440 ? "" : "S");
  else if (minutes && minutes % 60 == 0) snprintf(text, size, "%lu HOUR%s", static_cast<unsigned long>(minutes / 60), minutes == 60 ? "" : "S");
  else snprintf(text, size, "%s", title && title[0] ? title : "Quota");
}

inline const aim::Row* nova_quota_row(const aim::ViewData& view, const char* provider,
                                     const app_settings::NovaWindow& choice) {
  if (!view.hasUsage) return nullptr;
  const aim::Row* selected = nullptr;
  const aim::Row* durationMatch = nullptr;
  unsigned durationMatches = 0, severity = 0;
  float remaining = 0;
  for (size_t i = 0; i < view.rowCount && i < aim::kMaxRows; ++i) {
    const auto& row = view.rows[i]; if (!row.valid) continue;
    if (!choice.automatic) {
      if (row.windowMinutes == choice.minutes && strcmp(row.title, choice.title) == 0) return &row;
      if (choice.minutes && row.windowMinutes == choice.minutes) { durationMatch = &row; ++durationMatches; }
      continue;
    }
    const float candidate = view.showsRemaining ? row.usedPercent : 100.0f - row.usedPercent;
    const unsigned level = quota_critical(candidate, provider, row) ? 2 : (quota_low(candidate, provider, row) ? 1 : 0);
    if (!selected || level > severity || (level == severity && candidate < remaining)) {
      selected = &row; severity = level; remaining = candidate;
    }
  }
  // A unique duration survives harmless API title changes. Ambiguous or absent
  // windows remain unavailable; never silently substitute a different quota.
  return choice.automatic ? selected : (durationMatches == 1 ? durationMatch : nullptr);
}
