#pragma once
#include <algorithm>
#include "app_settings.h"
#include "ai_monitor/ai_monitor.h"
inline bool quota_low(float remaining) { return remaining <= app_settings::warning_percent(); }
inline bool quota_critical(float remaining) { return remaining <= std::min<uint8_t>(10, app_settings::warning_percent()); }
inline bool quota_low(float remaining, const char* provider, const aim::Row& row) {
  return remaining <= app_settings::warning_for(provider, row.title, row.windowMinutes);
}
inline bool quota_critical(float remaining, const char* provider, const aim::Row& row) {
  return remaining <= std::min<uint8_t>(10, app_settings::warning_for(provider, row.title, row.windowMinutes));
}
