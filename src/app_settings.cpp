// AI Monitor P4 - device settings implementation (NVS, UI-task only).

#include "app_settings.h"

#include <Arduino.h>
#include <Preferences.h>
#include <cstring>
#include <cstdio>
#include "ai_monitor/ai_monitor.h"
#include "config.h"

namespace app_settings {

static const char* NVS_NAMESPACE = "aimon";
static const char* KEY_DIM_MIN = "dim_min";
static uint8_t s_dimMinutes = 5;  // default: dim after 5 idle minutes
static uint8_t s_brightness = DISPLAY_DEFAULT_BRIGHTNESS, s_savedBrightness = DISPLAY_DEFAULT_BRIGHTNESS;
static bool s_loaded = false;
static bool s_initialBrightnessConsumed = false, s_brightnessOverridden = false;
static bool s_loadFailed = false;
static uint32_t s_loadAttemptMs = 0;
static uint8_t s_warningPercent = 25;
static NightSettings s_night;
static uint8_t s_savedDim = 5, s_savedWarning = 25;
static NightSettings s_savedNight;
static Appearance s_appearance, s_savedAppearance;
static constexpr size_t kNovaWindowBytes = 8 * 41;
static NovaWindow s_novaWindows[8], s_savedNovaWindows[8];
static int nova_provider_index(const char* key) {
  if (!key) return -1;
  for (size_t i = 0; i < 8; ++i) if (strcmp(key, nova_window_keys[i]) == 0) return static_cast<int>(i);
  return -1;
}
static bool valid_nova_window(const NovaWindow& value) {
  if (value.automatic) return true;
  if (!value.title[0] || value.title[35]) return false;
  for (const char* p = value.title; *p; ++p) if (*p < 32 || *p > 126) return false;
  return true;
}
static void encode_nova_windows(const NovaWindow (&values)[8], uint8_t (&bytes)[kNovaWindowBytes]) {
  memset(bytes, 0, sizeof(bytes));
  for (size_t i = 0; i < 8; ++i) {
    const auto& value = values[i]; auto* cell = bytes + i * 41;
    if (value.automatic) continue;
    cell[0] = 1;
    for (unsigned b = 0; b < 4; ++b) cell[b + 1] = static_cast<uint8_t>(value.minutes >> (b * 8));
    memcpy(cell + 5, value.title, 36);
  }
}
struct WarningRule {
  char provider[16] = {}, title[36] = {};
  uint32_t window = 0;
  uint8_t percent = 0;
};
static WarningRule s_rules[24], s_savedRules[24];
static SaveStatus s_saveStatus = SaveStatus::idle;
static uint32_t s_saveRevision = 0;
void report_save(bool success) { s_saveStatus = success ? SaveStatus::saved : SaveStatus::failed; ++s_saveRevision; }
SaveStatus save_status() { return s_saveStatus; }
uint32_t save_revision() { return s_saveRevision; }
static void night_bytes(const NightSettings& value, uint8_t (&bytes)[6]) {
  bytes[0] = value.enabled; bytes[1] = value.start & 255; bytes[2] = value.start >> 8;
  bytes[3] = value.end & 255; bytes[4] = value.end >> 8; bytes[5] = value.percent;
}

static bool ensure_loaded(bool retry = false) {
  if (s_loaded) return true;
  const uint32_t now = millis();
  if (s_loadFailed && !retry && now - s_loadAttemptMs < 1000u) return false;
  s_loadAttemptMs = now;
  Preferences prefs;
  auto failed = [&]() {
    prefs.end();
    if (!s_loadFailed) report_save(false);
    s_loadFailed = true;
    return false;
  };
  // A fresh device may have no namespace yet. Opening it writable creates
  // that namespace without publishing defaults over an unread existing value.
  if (!prefs.begin(NVS_NAMESPACE, true) && !prefs.begin(NVS_NAMESPACE, false)) return failed();

  // Stage the complete load. A short read may have filled only a prefix of its
  // destination; neither runtime values nor confirmed save baselines may see it.
  const uint8_t brightness = prefs.getUChar("brightness", DISPLAY_DEFAULT_BRIGHTNESS);
  const uint8_t dim = normalize_dim_minutes(prefs.getUChar(KEY_DIM_MIN, 5));
  const uint8_t warning = normalize_warning_percent(prefs.getUChar("warn_pct", 25));
  Appearance appearance;
  NightSettings night = normalize_night({prefs.getBool("night_on", false), prefs.getUShort("night_start", 1320),
                                        prefs.getUShort("night_end", 420), prefs.getUChar("night_pct", 20)});
  WarningRule rules[24]{};
  NovaWindow novaWindows[8]{};
  auto read_blob = [&](const char* key, void* destination, size_t expected, bool& present) {
    present = false;
    const size_t length = prefs.getBytesLength(key);
    // Missing and malformed legacy data retain their default/migration policy.
    // A present key whose length lookup fails is not a missing setting.
    if (!length) return !prefs.isKey(key);
    if (length != expected) return true;
    if (prefs.getBytes(key, destination, expected) != expected) return false;
    present = true;
    return true;
  };
  bool present = false;
  uint8_t look[2]{};
  if (!read_blob("appear_v1", look, sizeof(look), present)) return failed();
  if (present) appearance = normalize_appearance({static_cast<Companion>(look[0]), static_cast<Theme>(look[1])});
  uint8_t bytes[6]{};
  if (!read_blob("night_v2", bytes, sizeof(bytes), present)) return failed();
  if (present) night = normalize_night({bytes[0] != 0, static_cast<uint16_t>(bytes[1] | bytes[2] << 8),
                                      static_cast<uint16_t>(bytes[3] | bytes[4] << 8), bytes[5]});
  if (!read_blob("warn_rules", rules, sizeof(rules), present)) return failed();
  if (present) for (auto& rule : rules) {
    rule.provider[15] = rule.title[35] = '\0';
    if (!aim::provider_style(rule.provider) || rule.percent < 5 || rule.percent > 50) rule = WarningRule{};
  }
  uint8_t windows[kNovaWindowBytes]{};
  if (!read_blob("nova_win_v1", windows, sizeof(windows), present)) return failed();
  if (present) for (size_t i = 0; i < 8; ++i) {
    const auto* cell = windows + i * 41;
    if (cell[0] != 1) continue;
    NovaWindow value; value.automatic = false;
    for (unsigned b = 0; b < 4; ++b) value.minutes |= static_cast<uint32_t>(cell[b + 1]) << (b * 8);
    memcpy(value.title, cell + 5, 36);
    if (valid_nova_window(value)) novaWindows[i] = value;
  }
  prefs.end();

  s_brightness = brightness; s_dimMinutes = dim; s_warningPercent = warning;
  s_appearance = appearance; s_night = night;
  memcpy(s_rules, rules, sizeof(s_rules));
  memcpy(s_novaWindows, novaWindows, sizeof(s_novaWindows));
  s_savedBrightness = s_brightness;
  s_savedDim = s_dimMinutes; s_savedWarning = s_warningPercent; s_savedNight = s_night;
  s_savedAppearance = s_appearance;
  memcpy(s_savedNovaWindows, s_novaWindows, sizeof(s_novaWindows));
  memcpy(s_savedRules, s_rules, sizeof(s_rules));
  s_loadFailed = false;
  s_loaded = true;
  return true;
}

uint8_t dim_minutes() {
  ensure_loaded();
  return s_dimMinutes;
}

uint8_t brightness() { ensure_loaded(); return s_brightness; }
bool take_initial_brightness(uint8_t& value) {
  if (s_initialBrightnessConsumed || !ensure_loaded()) return false;
  s_initialBrightnessConsumed = true;
  if (s_brightnessOverridden) return false;
  value = s_brightness;
  return true;
}
void note_brightness_override() { s_brightnessOverridden = true; }
void set_brightness(uint8_t value) {
  if (!ensure_loaded(true)) { report_save(false); return; }
  s_brightness = value;
  if (value == s_savedBrightness) { report_save(true); return; }
  Preferences prefs;
  bool saved = false;
  if (prefs.begin(NVS_NAMESPACE, false)) {
    saved = prefs.putUChar("brightness", value) == sizeof(value); prefs.end();
  }
  if (saved) s_savedBrightness = value;
  report_save(saved);
}

Appearance appearance() { ensure_loaded(); return s_appearance; }
NovaWindow nova_window(const char* provider) {
  ensure_loaded(); const int index = nova_provider_index(provider);
  return index >= 0 ? s_novaWindows[index] : NovaWindow{};
}
void set_nova_window(const char* provider, NovaWindow value) {
  if (!ensure_loaded(true)) { report_save(false); return; }
  const int index = nova_provider_index(provider);
  if (index < 0 || !valid_nova_window(value)) { report_save(false); return; }
  if (value.automatic) value = NovaWindow{};
  s_novaWindows[index] = value;
  uint8_t bytes[kNovaWindowBytes], previous[kNovaWindowBytes];
  encode_nova_windows(s_novaWindows, bytes); encode_nova_windows(s_savedNovaWindows, previous);
  if (memcmp(bytes, previous, sizeof(bytes)) == 0) { report_save(true); return; }
  Preferences prefs; bool saved = false;
  if (prefs.begin(NVS_NAMESPACE, false)) {
    saved = prefs.putBytes("nova_win_v1", bytes, sizeof(bytes)) == sizeof(bytes); prefs.end();
  }
  if (saved) memcpy(s_savedNovaWindows, s_novaWindows, sizeof(s_novaWindows));
  report_save(saved);
}
void set_appearance(Appearance value) {
  if (!ensure_loaded(true)) { report_save(false); return; }
  value = normalize_appearance(value); s_appearance = value;
  if (value.companion == s_savedAppearance.companion && value.theme == s_savedAppearance.theme) { report_save(true); return; }
  const uint8_t bytes[] = {static_cast<uint8_t>(value.companion), static_cast<uint8_t>(value.theme)};
  Preferences prefs; bool saved = false;
  if (prefs.begin(NVS_NAMESPACE, false)) { saved = prefs.putBytes("appear_v1", bytes, sizeof(bytes)) == sizeof(bytes); prefs.end(); }
  if (saved) s_savedAppearance = value;
  report_save(saved);
}

void set_dim_minutes(uint8_t minutes) {
  if (!ensure_loaded(true)) { report_save(false); return; }
  minutes = normalize_dim_minutes(minutes);
  s_dimMinutes = minutes;
  if (minutes == s_savedDim) { report_save(true); return; }
  Preferences prefs;
  bool saved = false;
  if (prefs.begin(NVS_NAMESPACE, false)) { saved = prefs.putUChar(KEY_DIM_MIN, minutes) == sizeof(minutes); prefs.end(); }
  if (saved) s_savedDim = minutes;
  report_save(saved);
}

uint8_t warning_percent() {
  ensure_loaded();
  return s_warningPercent;
}

void set_warning_percent(uint8_t value) {
  if (!ensure_loaded(true)) { report_save(false); return; }
  value = normalize_warning_percent(value);
  s_warningPercent = value;
  if (value == s_savedWarning) { report_save(true); return; }
  Preferences prefs;
  bool saved = false;
  if (prefs.begin(NVS_NAMESPACE, false)) { saved = prefs.putUChar("warn_pct", value) == sizeof(value); prefs.end(); }
  if (saved) s_savedWarning = value;
  report_save(saved);
}

NightSettings night() { ensure_loaded(); return s_night; }
void set_night(NightSettings value) {
  if (!ensure_loaded(true)) { report_save(false); return; }
  value = normalize_night(value);
  s_night = value;
  uint8_t bytes[6], previous[6]; night_bytes(value, bytes); night_bytes(s_savedNight, previous);
  if (memcmp(bytes, previous, sizeof(bytes)) == 0) { report_save(true); return; }
  Preferences prefs;
  bool saved = false;
  if (prefs.begin(NVS_NAMESPACE, false)) {
    saved = prefs.putBytes("night_v2", bytes, sizeof(bytes)) == sizeof(bytes); prefs.end();
  }
  if (saved) s_savedNight = value;
  report_save(saved);
}

uint8_t warning_override_for(const char* provider, const char* title, uint32_t windowMinutes) {
  ensure_loaded();
  for (const auto& rule : s_rules)
    if (rule.percent && rule.window == windowMinutes && strcmp(rule.provider, provider) == 0 && strcmp(rule.title, title) == 0) return rule.percent;
  return 0;
}
uint8_t warning_for(const char* provider, const char* title, uint32_t windowMinutes) {
  const uint8_t value = warning_override_for(provider, title, windowMinutes);
  return value ? value : warning_percent();
}
void set_warning_for(const char* provider, const char* title, uint32_t windowMinutes, uint8_t percent) {
  if (!ensure_loaded(true)) { report_save(false); return; }
  if (!provider || !title || !aim::provider_style(provider) || strlen(title) >= 36 || (percent && (percent < 5 || percent > 50))) {
    report_save(false); return;
  }
  WarningRule* target = nullptr;
  for (auto& rule : s_rules)
    if (rule.percent && rule.window == windowMinutes && strcmp(rule.provider, provider) == 0 && strcmp(rule.title, title) == 0) { target = &rule; break; }
  if (!target && percent) for (auto& rule : s_rules) if (!rule.percent) { target = &rule; break; }
  if (!target && percent) { report_save(false); return; }
  if (target) {
    *target = WarningRule{};
    if (percent) {
      snprintf(target->provider, sizeof(target->provider), "%s", provider);
      snprintf(target->title, sizeof(target->title), "%s", title);
      target->window = windowMinutes; target->percent = percent;
    }
  }
  if (memcmp(s_rules, s_savedRules, sizeof(s_rules)) == 0) { report_save(true); return; }
  Preferences prefs;
  bool saved = false;
  if (prefs.begin(NVS_NAMESPACE, false)) { saved = prefs.putBytes("warn_rules", s_rules, sizeof(s_rules)) == sizeof(s_rules); prefs.end(); }
  if (saved) memcpy(s_savedRules, s_rules, sizeof(s_rules));
  report_save(saved);
}

}  // namespace app_settings
