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
  uint8_t recovered = 0;
  CHECK(!take_initial_brightness(recovered));
  set_dim_minutes(5); CHECK(save_status() == SaveStatus::failed && fake_nvs::writes == 0);
  set_brightness(DISPLAY_DEFAULT_BRIGHTNESS); CHECK(save_status() == SaveStatus::failed && fake_nvs::writes == 0);
  fake_nvs::fail_open = false; settingsTick = 1001;
  CHECK(dim_minutes() == 10 && s_loaded);
  CHECK(brightness() == 90);
  const auto writesBeforeRecovery = fake_nvs::writes;
  CHECK(take_initial_brightness(recovered) && recovered == 90);
  CHECK(!take_initial_brightness(recovered) && fake_nvs::writes == writesBeforeRecovery);
  s_initialBrightnessConsumed = false;
  note_brightness_override();
  CHECK(!take_initial_brightness(recovered));  // Preserve an explicit action before recovery.
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
  // CLAUDE is the third stored companion; the next unassigned value still falls back.
  fake_nvs::values["appear_v1"] = {2,1}; s_loaded = false;
  CHECK(appearance().companion == Companion::claude && std::string(companion_name(appearance().companion)) == "CLAUDE");
  fake_nvs::values["appear_v1"] = {3,1}; s_loaded = false;
  CHECK(appearance().companion == Companion::nova);
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
  s_loaded = false; s_initialBrightnessConsumed = false; s_brightnessOverridden = false;
  fake_nvs::fail_open = true; settingsTick += 1001;
  CHECK(!take_initial_brightness(recovered));
  note_brightness_override();  // A temporary user change while NVS is unavailable.
  fake_nvs::fail_open = false; settingsTick += 1001;
  CHECK(!take_initial_brightness(recovered) && s_loaded);
  // A failed read of a present blob cannot publish any part of a settings load.
  fake_nvs::fail_open=fake_nvs::fail_write=false;s_loaded=true;
  set_brightness(92);set_dim_minutes(10);set_warning_percent(35);
  set_appearance({Companion::orbit,Theme::ocean});set_night({true,1260,390,10});
  set_warning_for("codex","Session",300,15);
  set_nova_window("codex",manual_window(10080,"Week"));
  set_nova_window("zcode",manual_window(300,"Session"));
  const auto durable=fake_nvs::values;
  auto loaded_state=[] {
    std::vector<uint8_t> bytes;
    auto append=[&](const auto& value) {
      const auto* first=reinterpret_cast<const uint8_t*>(&value);
      bytes.insert(bytes.end(),first,first+sizeof(value));
    };
    append(s_brightness);append(s_dimMinutes);append(s_warningPercent);append(s_night);append(s_appearance);
    append(s_rules);append(s_novaWindows);append(s_savedBrightness);append(s_savedDim);append(s_savedWarning);
    append(s_savedNight);append(s_savedAppearance);append(s_savedRules);append(s_savedNovaWindows);
    return bytes;
  };
  for(const char* key:{"appear_v1","night_v2","warn_rules","nova_win_v1"})for(unsigned fault=0;fault<3;++fault) {
    fake_nvs::values=durable;fake_nvs::read_limits.clear();fake_nvs::fail_lengths.clear();
    if(fault==2)fake_nvs::fail_lengths.insert(key);
    else fake_nvs::read_limits[key]=fault?durable.at(key).size()-1:0;
    s_loaded=s_loadFailed=false;settingsTick+=1001;
    s_brightness=17;s_dimMinutes=0;s_warningPercent=12;s_night={false,60,120,25};
    s_appearance={Companion::nova,Theme::ember};
    const auto before=loaded_state();const auto writesBefore=fake_nvs::writes;
    CHECK(!ensure_loaded());CHECK(!s_loaded && s_loadFailed && save_status()==SaveStatus::failed);
    CHECK(loaded_state()==before);
    set_nova_window("claude",manual_window(300,"Session"));
    set_warning_for("claude","Session",300,10);
    CHECK(fake_nvs::writes==writesBefore && fake_nvs::values==durable);
    CHECK(loaded_state()==before);
    fake_nvs::read_limits.clear();fake_nvs::fail_lengths.clear();settingsTick+=1001;
    CHECK(ensure_loaded() && s_loaded && !s_loadFailed);
    CHECK(brightness()==92 && dim_minutes()==10 && warning_percent()==35);
    CHECK(appearance().companion==Companion::orbit && appearance().theme==Theme::ocean);
    CHECK(night().enabled && night().start==1260 && night().end==390 && night().percent==10);
    CHECK(warning_for("codex","Session",300)==15);
    CHECK(!nova_window("codex").automatic && !nova_window("zcode").automatic);
    set_nova_window("codex",manual_window(300,"Updated"));s_loaded=false;
    CHECK(!nova_window("zcode").automatic && nova_window("zcode").minutes==300);
  }
  // Missing keys are defaults/migrations, not failed reads of present data.
  fake_nvs::values.clear();s_loaded=s_loadFailed=false;
  CHECK(ensure_loaded() && nova_window("codex").automatic && warning_override_for("codex","Session",300)==0);
  CHECK(appearance().companion==Companion::nova && !night().enabled);
  // Scalar SDK reads return their fallback on error, even for a present key.
  for (const char* key : {"brightness","dim_min","warn_pct","night_on","night_start","night_end","night_pct"}) {
    fake_nvs::values.clear();fake_nvs::fail_scalar.clear();s_loaded=s_loadFailed=false;
    Preferences stored;
    stored.putUChar("brightness",90);stored.putUChar("dim_min",10);stored.putUChar("warn_pct",15);
    stored.putBool("night_on",true);stored.putUShort("night_start",1200);
    stored.putUShort("night_end",360);stored.putUChar("night_pct",15);
    fake_nvs::fail_scalar.insert(key);
    const auto before=fake_nvs::writes;
    CHECK(!ensure_loaded() && !s_loaded);
    set_brightness(DISPLAY_DEFAULT_BRIGHTNESS);
    CHECK(save_status()==SaveStatus::failed && fake_nvs::writes==before);
    fake_nvs::fail_scalar.clear();settingsTick+=1001;
    CHECK(ensure_loaded() && brightness()==90 && dim_minutes()==10 && warning_percent()==15);
    CHECK(night().enabled && night().start==1200 && night().end==360 && night().percent==15);
    set_brightness(DISPLAY_DEFAULT_BRIGHTNESS);
    CHECK(save_status()==SaveStatus::saved && fake_nvs::writes==before+1);
    CHECK(fake_nvs::values["brightness"][0]==DISPLAY_DEFAULT_BRIGHTNESS);
  }
  // Sentinels are real valid stored values, not reserved error values.
  for (uint8_t level : {uint8_t{0},uint8_t{255}}) {
    fake_nvs::values.clear();s_loaded=s_loadFailed=false;
    Preferences stored;stored.putUChar("brightness",level);stored.putUShort("night_start",0);
    CHECK(ensure_loaded() && brightness()==level && night().start==0);
    const auto before=fake_nvs::writes;set_brightness(level);CHECK(fake_nvs::writes==before);
  }
  fake_nvs::values.clear();s_loaded=s_loadFailed=false;
  fake_nvs::values["brightness"]={1,2}; // Invalid legacy scalar type still defaults.
  CHECK(ensure_loaded() && brightness()==DISPLAY_DEFAULT_BRIGHTNESS);
  if (failures) return EXIT_FAILURE;
  std::cout << "NVS persistence, failure/retry, window identity and migration checks passed\n";
}
