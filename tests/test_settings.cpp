#include "../src/app_settings.cpp"
#include <cstdlib>
#include <iostream>

static unsigned failures = 0;
static uint32_t settingsTick = 0;
uint32_t millis() { return settingsTick; }
#define CHECK(value) do { if (!(value)) { ++failures; std::cerr << __LINE__ << ": " #value "\n"; } } while (false)

static app_settings::NovaWindow manual_window(uint32_t minutes, const char* title) {
  app_settings::NovaWindow value; value.automatic = false; value.minutes = minutes;
  snprintf(value.title, sizeof(value.title), "%s", title); return value;
}

int main() {
  using namespace app_settings;
  fake_nvs::values["dim_min"] = {10}; fake_nvs::values["brightness"] = {90}; fake_nvs::fail_open = true;
  CHECK(dim_minutes() == 5 && !s_loaded && save_status() == SaveStatus::failed);
  set_dim_minutes(5); CHECK(save_status() == SaveStatus::failed && fake_nvs::writes == 0);
  set_brightness(DISPLAY_DEFAULT_BRIGHTNESS); CHECK(save_status() == SaveStatus::failed && fake_nvs::writes == 0);
  fake_nvs::fail_open = false; settingsTick = 1001;
  CHECK(dim_minutes() == 10 && s_loaded);
  CHECK(brightness() == 90);
  set_brightness(DISPLAY_DEFAULT_BRIGHTNESS);
  CHECK(save_status() == SaveStatus::saved && fake_nvs::values["brightness"][0] == DISPLAY_DEFAULT_BRIGHTNESS);
  const auto brightnessWrites = fake_nvs::writes;
  set_brightness(DISPLAY_DEFAULT_BRIGHTNESS); CHECK(fake_nvs::writes == brightnessWrites);
  set_dim_minutes(5);
  CHECK(save_status() == SaveStatus::saved && fake_nvs::values["dim_min"][0] == 5);
  s_loaded = false;
  Preferences legacy;
  legacy.putBool("night_on", true); legacy.putUShort("night_start", 1200);
  legacy.putUShort("night_end", 360); legacy.putUChar("night_pct", 15);
  CHECK(dim_minutes() == 5 && warning_percent() == 25);
  CHECK(night().enabled && night().start == 1200 && night().end == 360 && night().percent == 15);
  CHECK(appearance().companion == Companion::nova && appearance().theme == Theme::forest);
  fake_nvs::fail_write = true;
  set_appearance({Companion::orbit, Theme::ocean}); CHECK(save_status() == SaveStatus::failed);
  fake_nvs::fail_write = false;
  set_appearance({Companion::orbit, Theme::ocean}); CHECK(save_status() == SaveStatus::saved);
  const auto appearanceWrites = fake_nvs::writes;
  set_appearance({Companion::orbit, Theme::ocean}); CHECK(fake_nvs::writes == appearanceWrites);
  s_loaded = false; s_appearance = Appearance{};
  CHECK(appearance().companion == Companion::orbit && appearance().theme == Theme::ocean);
  fake_nvs::values["appear_v1"] = {255,255}; s_loaded = false;
  CHECK(appearance().companion == Companion::nova && appearance().theme == Theme::forest);
  CHECK(nova_window("codex").automatic && nova_window("zcode").automatic);
  set_nova_window("codex", manual_window(300, "Session"));
  set_nova_window("zcode", manual_window(43200, "Monthly"));
  CHECK(nova_window("codex").minutes == 300 && nova_window("zcode").minutes == 43200);
  CHECK(nova_window("claude").automatic);
  CHECK(fake_nvs::values["nova_win_v1"].size() == kNovaWindowBytes);
  const auto windowWrites = fake_nvs::writes;
  set_nova_window("zcode", manual_window(43200, "Monthly"));
  CHECK(fake_nvs::writes == windowWrites);
  fake_nvs::fail_write = true;
  set_nova_window("codex", manual_window(10080, "Week"));
  CHECK(save_status() == SaveStatus::failed && nova_window("codex").minutes == 10080);
  s_loaded = false; CHECK(nova_window("codex").minutes == 300);  // failed write did not persist
  fake_nvs::fail_write = false;
  set_nova_window("codex", manual_window(10080, "Week"));
  CHECK(save_status() == SaveStatus::saved);
  s_loaded = false;
  CHECK(nova_window("codex").minutes == 10080 && nova_window("zcode").minutes == 43200);
  CHECK(std::strcmp(nova_window("codex").title, "Week") == 0);
  fake_nvs::fail_open = true;
  set_nova_window("claude", manual_window(300, "Session")); CHECK(save_status() == SaveStatus::failed);
  fake_nvs::fail_open = false;
  set_nova_window("claude", manual_window(300, "Session")); CHECK(save_status() == SaveStatus::saved);
  const auto validWindows = fake_nvs::values["nova_win_v1"];
  fake_nvs::values["nova_win_v1"][0] = 255; s_loaded = false;
  CHECK(nova_window("codex").automatic && nova_window("zcode").minutes == 43200);
  fake_nvs::values["nova_win_v1"] = validWindows;
  fake_nvs::values["nova_win_v1"][5] = 1; s_loaded = false;
  CHECK(nova_window("codex").automatic);
  fake_nvs::values["nova_win_v1"] = validWindows;
  fake_nvs::values["nova_win_v1"][40] = 'x'; s_loaded = false;
  CHECK(nova_window("codex").automatic);  // unterminated stored title rejected
  fake_nvs::values["nova_win_v1"] = {1, 2}; s_loaded = false;
  CHECK(nova_window("codex").automatic && nova_window("zcode").automatic);
  fake_nvs::values["nova_win_v1"] = validWindows; s_loaded = false;
  set_nova_window("codex", NovaWindow{}); s_loaded = false;
  CHECK(nova_window("codex").automatic && nova_window("zcode").minutes == 43200);
  const auto validWriteCount = fake_nvs::writes;
  set_nova_window("unknown", manual_window(300, "Session")); CHECK(save_status() == SaveStatus::failed);
  set_nova_window(nullptr, manual_window(300, "Session")); CHECK(save_status() == SaveStatus::failed);
  set_nova_window("codex", manual_window(300, "")); CHECK(save_status() == SaveStatus::failed);
  auto invalidWindow = manual_window(300, "Session"); invalidWindow.title[35] = 'x';
  set_nova_window("codex", invalidWindow); CHECK(save_status() == SaveStatus::failed);
  CHECK(fake_nvs::writes == validWriteCount && nova_window("unknown").automatic);
  fake_nvs::fail_open = true;
  set_dim_minutes(1); CHECK(save_status() == SaveStatus::failed);
  CHECK(dim_minutes() == 1);  // temporary setting remains usable
  fake_nvs::fail_open = false;
  set_dim_minutes(1); CHECK(save_status() == SaveStatus::saved);
  CHECK(fake_nvs::values["dim_min"][0] == 1);
  const auto writes = fake_nvs::writes;
  set_dim_minutes(1); CHECK(fake_nvs::writes == writes);
  fake_nvs::fail_write = true;
  set_warning_percent(30); CHECK(save_status() == SaveStatus::failed);
  fake_nvs::fail_write = false;
  set_warning_percent(30); CHECK(save_status() == SaveStatus::saved);
  set_warning_for("codex", "Session", 300, 10);
  CHECK(warning_for("codex", "Session", 300) == 10);
  CHECK(warning_for("zcode", "Session", 300) == 30);
  CHECK(warning_for("codex", "Session", 10080) == 30);
  CHECK(warning_for("codex", "Week", 10080) == 30);
  const auto ruleWrites = fake_nvs::writes;
  set_warning_for("codex", "Session", 300, 10);
  CHECK(fake_nvs::writes == ruleWrites);
  fake_nvs::fail_write = true;
  set_warning_for("codex", "Week", 10080, 40); CHECK(save_status() == SaveStatus::failed);
  fake_nvs::fail_write = false;
  set_warning_for("codex", "Week", 10080, 40); CHECK(save_status() == SaveStatus::saved);
  fake_nvs::fail_write = true;
  set_night({true, 1260, 390, 10}); CHECK(save_status() == SaveStatus::failed);
  CHECK(fake_nvs::values["night_v2"].empty());
  fake_nvs::fail_write = false;
  set_night({true, 1260, 390, 10}); CHECK(save_status() == SaveStatus::saved);
  CHECK(fake_nvs::values["night_v2"].size() == 6);
  // Reload persisted bytes as a reboot would, independently of the active values.
  s_loaded = false; s_rules[0] = WarningRule{}; s_dimMinutes = 5; s_warningPercent = 25; s_night = NightSettings{};
  CHECK(dim_minutes() == 1 && warning_percent() == 30);
  CHECK(warning_for("codex", "Session", 300) == 10);
  CHECK(warning_for("codex", "Week", 10080) == 40);
  CHECK(night().enabled && night().start == 1260 && night().end == 390 && night().percent == 10);
  set_warning_for("codex", "Session", 300, 0);
  CHECK(warning_for("codex", "Session", 300) == 30);
  set_warning_for("unknown", "Session", 300, 10); CHECK(save_status() == SaveStatus::failed);
  set_warning_for("codex", "Session", 300, 51); CHECK(save_status() == SaveStatus::failed);
  if (failures) return EXIT_FAILURE;
  std::cout << "NVS persistence, failure/retry, window identity and migration checks passed\n";
}
