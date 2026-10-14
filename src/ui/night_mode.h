#pragma once
#include <algorithm>
#include "../app_settings.h"
#include "usage_format.h"
#include "backlight.h"

inline bool night_scheduled(uint16_t minute, const app_settings::NightSettings& settings) {
  if (!settings.enabled) return false;
  if (settings.start == settings.end) return true;  // equal endpoints mean all day
  return settings.start < settings.end ? minute >= settings.start && minute < settings.end :
                                        minute >= settings.start || minute < settings.end;
}
inline uint8_t night_brightness(const aim::Snapshot& snapshot, uint32_t now, uint8_t selected,
                               const app_settings::NightSettings& settings) {
  uint16_t minute = 0;
  return local_minutes(snapshot, now, minute) && night_scheduled(minute, settings) ?
         std::min(selected, brightness_raw(settings.percent)) : selected;
}
