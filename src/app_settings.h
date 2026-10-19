#pragma once
// AI Monitor P4 - device settings (NVS-backed, owned by the UI task).
// Display backends apply brightness; this module owns confirmed persistence
// for brightness and the remaining on-device settings.

#include <cstdint>

namespace app_settings {
uint8_t brightness();
void set_brightness(uint8_t value);
// Apply a recovered first NVS load once, unless the user already changed it.
bool take_initial_brightness(uint8_t& value);
void note_brightness_override();

constexpr uint8_t normalize_dim_minutes(uint8_t minutes) {
  return minutes == 0 || minutes == 1 || minutes == 5 || minutes == 10 ? minutes : 5;
}

// Idle dim timeout in minutes (0 = never dim). Persisted.
uint8_t dim_minutes();
void set_dim_minutes(uint8_t minutes);

constexpr uint8_t normalize_warning_percent(uint8_t value) {
  return value >= 5 && value <= 50 ? value : 25;
}
uint8_t warning_percent();
void set_warning_percent(uint8_t value);
enum class SaveStatus : uint8_t { idle, saved, failed };
void report_save(bool success);
SaveStatus save_status();
uint32_t save_revision();
enum class Companion : uint8_t { nova, orbit, claude };
inline constexpr uint8_t companion_count = 3;
enum class Theme : uint8_t { forest, ocean, amethyst, ember };
struct Appearance { Companion companion = Companion::nova; Theme theme = Theme::forest; };
inline Appearance normalize_appearance(Appearance value) {
  if (static_cast<uint8_t>(value.companion) >= companion_count) value.companion = Companion::nova;
  if (static_cast<uint8_t>(value.theme) > 3) value.theme = Theme::forest;
  return value;
}
Appearance appearance();
void set_appearance(Appearance value);
// One independent NOVA/ORBIT quota-window preference per provider.
struct NovaWindow { bool automatic = true; uint32_t minutes = 0; char title[36] = {}; };
inline constexpr const char* nova_window_keys[] = {
  "codex", "zcode", "claude", "gemini", "copilot", "cursor", "antigravity", "opencode"
};
NovaWindow nova_window(const char* provider);
void set_nova_window(const char* provider, NovaWindow value);
inline const char* companion_name(Companion value) {
  return value == Companion::orbit ? "ORBIT" : value == Companion::claude ? "CLAUDE" : "NOVA";
}
inline const char* theme_name(Theme value) {
  static const char* names[] = {"Forest", "Ocean", "Amethyst", "Ember"};
  return names[static_cast<uint8_t>(normalize_appearance({Companion::nova, value}).theme)];
}
uint8_t warning_override_for(const char* provider, const char* title, uint32_t windowMinutes);
uint8_t warning_for(const char* provider, const char* title, uint32_t windowMinutes);
// Zero removes the override and restores the global default.
void set_warning_for(const char* provider, const char* title, uint32_t windowMinutes, uint8_t percent);

struct NightSettings {
  bool enabled = false;
  uint16_t start = 22 * 60, end = 7 * 60;
  uint8_t percent = 20;
};
inline NightSettings normalize_night(NightSettings value) {
  if (value.start >= 1440) value.start = 22 * 60;
  if (value.end >= 1440) value.end = 7 * 60;
  if (value.percent < 5 || value.percent > 50) value.percent = 20;
  return value;
}
NightSettings night();
void set_night(NightSettings value);
constexpr uint16_t adjust_night_time(uint16_t value, bool hours, int direction) {
  return static_cast<uint16_t>((static_cast<int>(value) + 1440 + direction * (hours ? 60 : 1)) % 1440);
}

}  // namespace app_settings
