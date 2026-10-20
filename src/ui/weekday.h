#pragma once
#include <cstdint>

// Day of week for chart labels, 0 = Sunday. Pure date arithmetic (Sakamoto); no clock or locale.
inline uint8_t weekday_of(int year, int month, int day) {
  static const int offset[] = {0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4};
  if (year < 1970 || year > 9999 || month < 1 || month > 12 || day < 1 || day > 31) return 0xFF;
  if (month < 3) --year;
  return static_cast<uint8_t>((year + year / 4 - year / 100 + year / 400 + offset[month - 1] + day) % 7);
}

// "YYYY-MM-DD" as the host sends the local date; 0xFF when it is not exactly that shape.
inline uint8_t weekday_from_iso(const char* iso) {
  if (!iso) return 0xFF;
  int part[3] = {0, 0, 0};
  const int digits[3] = {4, 2, 2};
  const char* cursor = iso;
  for (int field = 0; field < 3; ++field) {
    for (int i = 0; i < digits[field]; ++i, ++cursor) {
      if (*cursor < '0' || *cursor > '9') return 0xFF;
      part[field] = part[field] * 10 + (*cursor - '0');
    }
    if (field < 2) {
      if (*cursor != '-') return 0xFF;
      ++cursor;
    }
  }
  return *cursor == '\0' ? weekday_of(part[0], part[1], part[2]) : 0xFF;
}

inline const char* weekday_name(uint8_t weekday) {
  static const char* const names[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
  return weekday < 7 ? names[weekday] : "";
}
