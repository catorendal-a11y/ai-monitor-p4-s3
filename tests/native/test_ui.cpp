#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <initializer_list>
#include <iostream>
#include <string>
#include <map>
#include <vector>
#include <lvgl.h>
#include "ai_monitor/ai_monitor.h"
#include "ui/backlight.h"
#include "ui/idle_dim.h"
#include "app_settings.h"
#include "ui/visual_dimmer.h"
#include "ui/touch_input.h"
#include "companions/image_binding.h"

static uint32_t fakeTick = 1000;
static aim::Snapshot sample{};
static uint8_t selectedBrightness = 160, actualBrightness = 160, dimMinutes = 1;
static bool lastPersisted = false;
static unsigned failures = 0;
static unsigned requestedRefreshes = 0;
static uint8_t warningPercent = 25;
static app_settings::NightSettings nightSettings;
static app_settings::Appearance testAppearance;
static app_settings::SaveStatus testSaveStatus = app_settings::SaveStatus::idle;
static uint32_t testSaveRevision = 0;
static std::map<std::string, uint8_t> testWarningRules;
static std::map<std::string, app_settings::NovaWindow> testNovaWindows;
static bool testNovaSaveSuccess = true;
static bool testInitialBrightnessPending = false, testBrightnessOverridden = false;
static uint8_t testInitialBrightness = 160;
#define CHECK(condition) do { if (!(condition)) { \
  std::cerr << __func__ << ":" << __LINE__ << ": " #condition "\n"; ++failures; \
} } while (false)

uint32_t millis() { return fakeTick; }
namespace aim { Snapshot read() { return sample; } void request_refresh() { ++requestedRefreshes; } }
namespace app_settings {
void report_save(bool success) { testSaveStatus = success ? SaveStatus::saved : SaveStatus::failed; ++testSaveRevision; }
SaveStatus save_status() { return testSaveStatus; }
uint32_t save_revision() { return testSaveRevision; }
uint8_t dim_minutes() { return dimMinutes; }
void set_dim_minutes(uint8_t value) { dimMinutes = value; report_save(true); }
uint8_t warning_percent() { return warningPercent; }
void set_warning_percent(uint8_t value) { warningPercent = value; report_save(true); }
static std::string rule_key(const char* provider, const char* title, uint32_t window) {
  return std::string(provider) + "/" + title + "/" + std::to_string(window);
}
uint8_t warning_override_for(const char* provider, const char* title, uint32_t window) { return testWarningRules[rule_key(provider, title, window)]; }
uint8_t warning_for(const char* provider, const char* title, uint32_t window) {
  const uint8_t value = warning_override_for(provider, title, window); return value ? value : warningPercent;
}
void set_warning_for(const char* provider, const char* title, uint32_t window, uint8_t value) {
  testWarningRules[rule_key(provider, title, window)] = value; report_save(true);
}
NightSettings night() { return nightSettings; }
void set_night(NightSettings value) { nightSettings = value; report_save(true); }
Appearance appearance() { return testAppearance; }
NovaWindow nova_window(const char* provider) { return testNovaWindows[provider ? provider : ""]; }
void set_nova_window(const char* provider, NovaWindow value) {
  testNovaWindows[provider] = value; report_save(testNovaSaveSuccess);
}
void set_appearance(Appearance value) { testAppearance = normalize_appearance(value); report_save(true); }
bool take_initial_brightness(uint8_t& value) {
  if (!testInitialBrightnessPending) return false;
  testInitialBrightnessPending = false;
  if (testBrightnessOverridden) return false;
  value = testInitialBrightness; return true;
}
void note_brightness_override() { testBrightnessOverridden = true; }
}
void display_set_brightness(uint8_t value) { actualBrightness = value; }
uint8_t display_get_brightness() { return selectedBrightness; }
uint8_t display_get_applied_brightness() { return actualBrightness; }
void display_remember_brightness(uint8_t value) { selectedBrightness = value; }
void display_apply_brightness(uint8_t value, bool persist) {
  app_settings::note_brightness_override();
  selectedBrightness = actualBrightness = value;
  lastPersisted = persist;
  if (persist) app_settings::report_save(true);
}

// Compile the actual UI and send real LVGL events. Only hardware/data are faked.
#include "../../src/dashboard.cpp"
#include "../../src/ui_settings.cpp"
#include "../../src/ui_usage_details.cpp"
#include "../../src/ui_notifications.cpp"
#include "../../src/ui_nova.cpp"

alignas(64) static uint32_t drawBuffer[800 * 480];
static uint32_t framebuffer[800 * 480];

static void flush(lv_display_t* display, const lv_area_t* area, uint8_t* pixels) {
  const auto* source = reinterpret_cast<uint32_t*>(pixels);
  const int width = area->x2 - area->x1 + 1;
  for (int y = area->y1; y <= area->y2; ++y) {
    std::copy_n(source + (y - area->y1) * width, width, framebuffer + y * 800 + area->x1);
  }
  lv_display_flush_ready(display);
}

static lv_point_t touchPoint = {500, 250};
static bool touchPressed = false;
static bool touchFailed = false;
static TouchInputGuard testTouchGuard;
static void read_touch(lv_indev_t* input, lv_indev_data_t* data) {
  if (touchFailed) { testTouchGuard.failed(input, data); return; }
  data->point = touchPoint;
  data->state = touchPressed ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
  if (!testTouchGuard.accept(touchPressed)) data->state = LV_INDEV_STATE_RELEASED;
}

static void screenshot(const std::filesystem::path& directory, const char* name) {
  if (directory.empty()) return;
  std::filesystem::create_directories(directory);
  lv_refr_now(nullptr);
  std::ofstream image(directory / (std::string(name) + ".ppm"), std::ios::binary);
  image << "P6\n800 480\n255\n";
  for (uint32_t pixel : framebuffer) {
    const char rgb[] = {static_cast<char>(pixel >> 16), static_cast<char>(pixel >> 8), static_cast<char>(pixel)};
    image.write(rgb, sizeof(rgb));
  }
}

static void set_sample(size_t count, size_t rows) {
  sample = aim::Snapshot{};
  sample.hostPresent = sample.viewsConfigured = true;
  sample.viewCount = static_cast<uint8_t>(count);
  sample.frameCount = 1;
  sample.lastFrameMs = fakeTick;
  sample.displayTimeMs = fakeTick;
  std::strcpy(sample.displayTime, "21:30");
  const char* keys[] = {"codex", "zcode", "claude", "gemini", "copilot", "cursor", "antigravity", "codex"};
  const char* titles[] = {"Session", "Week", "Monthly"};
  for (size_t i = 0; i < count; ++i) {
    auto& view = sample.views[i];
    std::strcpy(sample.viewKeys[i], keys[i]);
    std::strcpy(view.providerKey, keys[i]);
    std::strcpy(view.providerLabel, aim::provider_style(keys[i])->label);
    view.valid = view.hasUsage = view.showsRemaining = true;
    view.receivedMs = view.quotaReceivedMs = fakeTick;
    view.rowCount = static_cast<uint8_t>(rows);
    for (size_t r = 0; r < rows; ++r) {
      view.rows[r].valid = true;
      view.rows[r].usedPercent = static_cast<float>(75 - i * 3 - r * 8);
      view.rows[r].windowMinutes = r == 0 ? 300 : (r == 1 ? 10080 : 43200);
      std::strcpy(view.rows[r].title, titles[r]);
      std::strcpy(view.rows[r].resetsShort, r == 0 ? "23:45" : "14 Oct 23:45");
    }
  }
}

static void check_inside(lv_obj_t* parent, lv_obj_t* child) {
  if (!child) { CHECK(false); return; }
  lv_area_t outer{}, inner{};
  lv_obj_get_coords(parent, &outer);
  lv_obj_get_coords(child, &inner);
  CHECK(inner.x1 >= outer.x1 && inner.y1 >= outer.y1);
  CHECK(inner.x2 <= outer.x2 && inner.y2 <= outer.y2);
}

static void settle_backlight() {
  idle_dim_update(); fakeTick += 600; idle_dim_update();
}

static void check_readable_text(lv_obj_t* object) {
  lv_point_t size{};
  lv_text_get_size(&size, lv_label_get_text(object), lv_obj_get_style_text_font(object, LV_PART_MAIN),
                  0, 0, LV_COORD_MAX, LV_TEXT_FLAG_NONE);
  CHECK(size.x <= lv_obj_get_content_width(object));
  CHECK(size.y <= lv_obj_get_height(object));
}

static void test_nova_readability(const std::filesystem::path& screenshots) {
  set_sample(8, 3); nova_ui::page = 0;
  std::strcpy(sample.views[7].providerKey, "opencode"); std::strcpy(sample.viewKeys[7], "opencode");
  for (size_t v = 0; v < 8; ++v)
    for (auto& row : sample.views[v].rows) row.usedPercent = v % 2 ? 100 : 0.01f;
  ui_nova_show();
  for (size_t p = 0; p < 4; ++p) {
    nova_ui::page = static_cast<uint8_t>(p); ui_nova_update(); lv_obj_update_layout(nova_ui::screen);
    for (const auto& item : nova_ui::providers) {
      for (auto* object : {item.name, item.percent, item.status}) {
        check_inside(item.card, object); check_readable_text(object);
      }
      lv_area_t name{}, percent{}, bar{};
      lv_obj_get_coords(item.name, &name); lv_obj_get_coords(item.percent, &percent); lv_obj_get_coords(item.bar, &bar);
      CHECK(name.x2 < percent.x1 && percent.y2 < bar.y1);
    }
  }
  sample.views[6].informational = true; sample.views[6].hasUsage = false;
  ui_nova_update(); lv_obj_update_layout(nova_ui::screen);
  check_readable_text(nova_ui::providers[0].percent); check_readable_text(nova_ui::providers[0].status);
  lv_area_t guidance{}, action{}; lv_obj_get_coords(nova_ui::pageLabel, &guidance);
  lv_obj_get_coords(nova_ui::updateButton, &action); CHECK(guidance.y2 < action.y1);
  screenshot(screenshots, "nova-readable-external-providers");
  nova_ui::page = 0; set_sample(2, 2); ui_nova_update();
}

static void test_quota_windows(const std::filesystem::path& screenshots) {
  testNovaWindows.clear(); testWarningRules.clear(); warningPercent = 25;
  testAppearance = app_settings::Appearance{}; ui_theme::apply(testAppearance.theme);
  set_sample(3, 2);
  nova_ui::page = 0;
  sample.views[1].rowCount = 3;
  sample.views[1].rows[2] = sample.views[1].rows[1];
  std::strcpy(sample.views[1].rows[2].title, "Monthly MCP"); sample.views[1].rows[2].windowMinutes = 43200;
  ui_nova_show();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "67%");
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].status)) == "7 DAYS / AUTO");
  ui_settings_show(); lv_obj_send_event(quotaButton, LV_EVENT_CLICKED, nullptr);
  CHECK(!lv_obj_is_hidden(quotaOverlay) && quotaProviderCount == 3 && quotaChoiceCount == 2);
  CHECK(std::string(lv_label_get_text(quotaProviderLabel)) == "CODEX");
  CHECK(std::string(lv_label_get_text(quotaCaptions[1])) == "5 HOURS");
  CHECK(std::string(lv_label_get_text(quotaCaptions[2])) == "7 DAYS");
  CHECK(std::string(lv_label_get_text(quotaProviderHelp)).find("weekly limit") != std::string::npos);
  CHECK(std::string(lv_label_get_text(quotaDetails[1])) == "75% left / REPORTED");
  lv_obj_send_event(quotaButtons[1], LV_EVENT_CLICKED, nullptr); ui_settings_update();
  CHECK(app_settings::nova_window("codex").minutes == 300);
  CHECK(std::string(lv_label_get_text(saveFeedback)) == "SAVED");
  lv_obj_update_layout(lv_layer_top());
  auto* card = lv_obj_get_child(quotaOverlay, 0);
  for (size_t i = 0; i < 4; ++i) if (!lv_obj_is_hidden(quotaButtons[i])) {
    check_inside(card, quotaButtons[i]); check_inside(quotaButtons[i], quotaCaptions[i]);
    check_inside(quotaButtons[i], quotaDetails[i]); check_readable_text(quotaCaptions[i]); check_readable_text(quotaDetails[i]);
    lv_area_t caption{}, detail{}; lv_obj_get_coords(quotaCaptions[i], &caption); lv_obj_get_coords(quotaDetails[i], &detail);
    CHECK(caption.y2 < detail.y1);
  }
  for (auto* label : {quotaSelectionLabel, quotaProviderLabel, quotaProviderHelp, quotaSetupHelp}) {
    check_inside(card, label); check_readable_text(label);
  }
  screenshot(screenshots, "settings-quota-codex");
  close_quota(nullptr); ui_settings_hide(); ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "75%");
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].status)) == "5 HOURS");
  screenshot(screenshots, "nova-quota-5-hours");
  ui_settings_show(); lv_obj_send_event(quotaButton, LV_EVENT_CLICKED, nullptr);
  lv_obj_send_event(quotaNext, LV_EVENT_CLICKED, nullptr);
  CHECK(std::string(lv_label_get_text(quotaProviderLabel)) == "Z CODE");
  CHECK(std::string(lv_label_get_text(quotaCaptions[2])) == "7 DAYS");
  CHECK(std::string(lv_label_get_text(quotaCaptions[3])) == "MONTHLY MCP");
  CHECK(std::string(lv_label_get_text(quotaProviderHelp)).find("not a monthly token budget") != std::string::npos);
  CHECK(std::string(lv_label_get_text(quotaSetupHelp)).find("Coding Plan API key") != std::string::npos);
  lv_obj_send_event(quotaButtons[3], LV_EVENT_CLICKED, nullptr);
  CHECK(app_settings::nova_window("zcode").minutes == 43200);
  CHECK(app_settings::nova_window("codex").minutes == 300);
  ui_settings_update(); screenshot(screenshots, "settings-quota-zcode");
  lv_obj_update_layout(lv_layer_top());
  for (auto* label : {quotaSelectionLabel, quotaProviderLabel, quotaProviderHelp, quotaSetupHelp}) {
    check_inside(card, label); check_readable_text(label);
  }
  lv_obj_send_event(quotaNext, LV_EVENT_CLICKED, nullptr);
  CHECK(std::string(lv_label_get_text(quotaProviderLabel)) == "CLAUDE");
  lv_obj_send_event(quotaButtons[2], LV_EVENT_CLICKED, nullptr);
  CHECK(app_settings::nova_window("claude").minutes == 10080);
  lv_obj_send_event(quotaNext, LV_EVENT_CLICKED, nullptr);  // wraps by stable provider key
  CHECK(std::string(lv_label_get_text(quotaProviderLabel)) == "CODEX");
  // Incoming row reordering cannot change a button's identity while touching it.
  std::swap(sample.views[0].rows[0], sample.views[0].rows[1]);
  lv_obj_send_event(quotaButtons[2], LV_EVENT_CLICKED, nullptr);
  CHECK(app_settings::nova_window("codex").minutes == 10080);
  close_quota(nullptr); ui_settings_hide(); ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "67%");
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].status)) == "7 DAYS");
  CHECK(std::string(lv_label_get_text(nova_ui::providers[1].status)) == "MONTHLY MCP");
  screenshot(screenshots, "nova-quota-week-month");
  // A harmless API title change retains the unique matching duration.
  std::strcpy(sample.views[0].rows[0].title, "Secondary"); ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "67%");
  ui_settings_show(); lv_obj_send_event(quotaButton, LV_EVENT_CLICKED, nullptr);
  CHECK(std::string(lv_label_get_text(quotaSelectionLabel)) == "Selected: 7 DAYS");
  CHECK(lv_color_eq(lv_obj_get_style_bg_color(quotaButtons[2], LV_PART_MAIN), lv_color_hex(ui_theme::accent)));
  close_quota(nullptr); ui_settings_hide();
  // Ambiguous same-duration quotas must not be silently substituted.
  sample.views[0].rows[1].windowMinutes = 10080;
  ui_nova_update(); CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "--");
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].status)) == "Selected window unavailable");
  std::strcpy(sample.views[0].rows[1].title, "Week"); ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "75%");
  sample.views[0].rows[0].valid = sample.views[0].rows[1].valid = false;
  ui_nova_update(); CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "--");
  // Missing windows remain visibly unavailable; AUTO recovers when data returns.
  set_sample(2, 1); ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "--");
  ui_settings_show(); lv_obj_send_event(quotaButton, LV_EVENT_CLICKED, nullptr);
  CHECK(std::string(lv_label_get_text(quotaSelectionLabel)).find("not currently reported") != std::string::npos);
  lv_obj_send_event(quotaButtons[0], LV_EVENT_CLICKED, nullptr);
  close_quota(nullptr); ui_settings_hide(); ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "75%");
  // A safe selected window never masks another window's critical alert/mood.
  set_sample(2, 2); sample.views[0].rows[1].usedPercent = 5;
  ui_settings_show(); lv_obj_send_event(quotaButton, LV_EVENT_CLICKED, nullptr);
  testNovaSaveSuccess = false;
  lv_obj_send_event(quotaButtons[1], LV_EVENT_CLICKED, nullptr); ui_settings_update();
  CHECK(std::string(lv_label_get_text(saveFeedback)) == "SAVE FAILED");
  CHECK(std::string(lv_label_get_text(quotaSelectionLabel)).find("saved") == std::string::npos);
  testNovaSaveSuccess = true;
  lv_obj_send_event(quotaButtons[1], LV_EVENT_CLICKED, nullptr); ui_settings_update();
  CHECK(std::string(lv_label_get_text(saveFeedback)) == "SAVED");
  close_quota(nullptr); ui_settings_hide(); ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "75%");
  CHECK(nova_ui::mood == NovaMood::critical);
  sample.hostPresent = false; ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].status)) == "OFFLINE / last good");
  CHECK(app_settings::nova_window("codex").minutes == 300);
  // Known windows remain selectable without fabricating missing percentages.
  set_sample(1, 0); sample.views[0].hasUsage = false; sample.views[0].informational = true;
  ui_settings_show(); lv_obj_send_event(quotaButton, LV_EVENT_CLICKED, nullptr);
  CHECK(quotaChoiceCount == 2 && !lv_obj_is_hidden(quotaButtons[1]) && !lv_obj_is_hidden(quotaButtons[2]));
  CHECK(std::string(lv_label_get_text(quotaDetails[2])).find("NOT REPORTED") == 0);
  lv_obj_send_event(quotaButtons[2], LV_EVENT_CLICKED, nullptr);
  CHECK(app_settings::nova_window("codex").minutes == 10080);
  CHECK(std::string(lv_label_get_text(quotaSelectionLabel)).find("not currently reported") != std::string::npos);
  screenshot(screenshots, "settings-quota-missing");
  const auto savedRevision = app_settings::save_revision();
  // New data is shown without closing Settings or rebinding a held target.
  set_sample(1, 2); fakeTick += 501; ui_settings_update();
  CHECK(std::string(lv_label_get_text(quotaDetails[2])) == "67% left / REPORTED");
  CHECK(app_settings::save_revision() == savedRevision);
  CHECK(app_settings::nova_window("codex").minutes == 10080);
  sample.views[0].fetching = true; fakeTick += 501; ui_settings_update();
  CHECK(std::string(lv_label_get_text(quotaDetails[2])).find("UPDATING") != std::string::npos);
  sample.views[0].fetching = false; sample.views[0].notice = true; fakeTick += 501; ui_settings_update();
  CHECK(std::string(lv_label_get_text(quotaDetails[2])).find("ERROR") != std::string::npos);
  sample.hostPresent = false; fakeTick += 501; ui_settings_update();
  CHECK(std::string(lv_label_get_text(quotaDetails[2])).find("OFFLINE") != std::string::npos);
  CHECK(std::string(lv_label_get_text(quotaSetupHelp)).find("Host offline") == 0);
  CHECK(app_settings::save_revision() == savedRevision);
  sample.hostPresent = true; sample.views[0].notice = false;
  std::strcpy(sample.views[0].providerKey, "gemini"); std::strcpy(sample.viewKeys[0], "gemini");
  sample.views[0].rowCount = 0; sample.views[0].hasUsage = false; sample.views[0].informational = true;
  refresh_quota(nullptr);
  CHECK(quotaChoiceCount == 0 && lv_obj_is_hidden(quotaButtons[1]));
  CHECK(std::string(lv_label_get_text(quotaProviderHelp)).find("Local token activity only") == 0);
  CHECK(std::string(lv_label_get_text(quotaSelectionLabel)).find("No quota windows reported") == 0);
  screenshot(screenshots, "settings-quota-local-only");
  std::strcpy(sample.views[0].providerKey, "opencode"); std::strcpy(sample.viewKeys[0], "opencode");
  refresh_quota(nullptr);
  CHECK(quotaChoiceCount == 0);
  CHECK(std::string(lv_label_get_text(quotaSetupHelp)).find("local tokens are read automatically") != std::string::npos);
  for (auto* label : {quotaProviderHelp, quotaSetupHelp}) check_readable_text(label);
  screenshot(screenshots, "settings-opencode-local");
  close_quota(nullptr); ui_settings_hide(); ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "LOCAL");
  sample = aim::Snapshot{}; ui_settings_show(); lv_obj_send_event(quotaButton, LV_EVENT_CLICKED, nullptr);
  CHECK(!quotaProviderCount && lv_obj_has_state(quotaNext, LV_STATE_DISABLED));
  CHECK(std::string(lv_label_get_text(quotaProviderLabel)) == "No providers configured");
  ui_settings_hide(); CHECK(lv_obj_is_hidden(quotaOverlay));
  // Unknown real windows are retained instead of being crowded out by defaults.
  set_sample(1, 1); std::strcpy(sample.views[0].providerKey, "zcode"); std::strcpy(sample.viewKeys[0], "zcode");
  sample.views[0].rows[0].windowMinutes = 1440; std::strcpy(sample.views[0].rows[0].title, "Daily");
  ui_settings_show(); open_quota(nullptr);
  CHECK(quotaChoices[0].minutes == 1440);
  CHECK(std::string(lv_label_get_text(quotaCaptions[1])) == "1 DAY");
  close_quota(nullptr); ui_settings_hide();
  set_sample(8, 0); std::strcpy(sample.views[7].providerKey, "opencode"); std::strcpy(sample.viewKeys[7], "opencode");
  ui_settings_show(); open_quota(nullptr); CHECK(quotaProviderCount == 8);
  for (size_t i = 0; i < 8; ++i) {
    lv_obj_update_layout(lv_layer_top());
    for (auto* label : {quotaSelectionLabel, quotaProviderLabel, quotaProviderHelp, quotaSetupHelp}) {
      check_inside(card, label); check_readable_text(label);
    }
    lv_obj_send_event(quotaNext, LV_EVENT_CLICKED, nullptr);
  }
  close_quota(nullptr); ui_settings_hide();
  testNovaWindows.clear(); set_sample(2, 2);
}

static lv_obj_t* find_caption_button(lv_obj_t* parent, const char* text) {
  for (uint32_t i = 0; i < lv_obj_get_child_count(parent); ++i) {
    auto* child = lv_obj_get_child(parent, i);
    if (lv_obj_check_type(child, &lv_label_class) && strcmp(lv_label_get_text(child), text) == 0)
      return parent;
    if (auto* found = find_caption_button(child, text)) return found;
  }
  return nullptr;
}

struct ButtonGeometry { lv_obj_t* button; lv_area_t area; };
static void capture_button_geometry(lv_obj_t* parent, std::vector<ButtonGeometry>& geometry) {
  for (uint32_t i = 0; i < lv_obj_get_child_count(parent); ++i) {
    auto* child = lv_obj_get_child(parent, i);
    if (lv_obj_check_type(child, &lv_button_class)) {
      lv_area_t area{}; lv_obj_get_coords(child, &area); geometry.push_back({child, area});
    }
    capture_button_geometry(child, geometry);
  }
}

static void test_stable_touch_targets(const std::filesystem::path& screenshots) {
  ui_settings_hide(); nova_ui::show_dashboard(nullptr);
  lv_obj_update_layout(dashboardScreen); lv_obj_update_layout(nova_ui::screen);
  auto* dashboardSet = find_caption_button(dashboardScreen, "SET");
  auto* novaSet = find_caption_button(nova_ui::screen, "SET");
  CHECK(dashboardSet && novaSet);
  if (dashboardSet && novaSet) {
    lv_area_t a{}, b{}; lv_obj_get_coords(dashboardSet, &a); lv_obj_get_coords(novaSet, &b);
    CHECK(a.x1 == b.x1 && a.y1 == b.y1 && a.x2 == b.x2 && a.y2 == b.y2);
  }
  auto* pointer = lv_indev_create(); lv_indev_set_type(pointer, LV_INDEV_TYPE_POINTER);
  lv_indev_set_read_cb(pointer, read_touch);
  touchFailed = touchPressed = false; testTouchGuard = TouchInputGuard{};
  lv_indev_read(pointer);
  set_sample(8, 2); sample.automaticViews = true; sample.viewIntervalSeconds = 2;
  ++sample.viewRevision; dashboard_update();
  currentPage = 0; dashboard_update(); lv_obj_update_layout(dashboardScreen);
  touchPoint = {200, 120}; touchPressed = true; lv_indev_read(pointer);
  CHECK(lv_obj_has_state(compact[0].card, LV_STATE_PRESSED));
  fakeTick += 2100; dashboard_update();
  CHECK(currentPage == 0 && compact[0].viewIndex == 0);
  touchPressed = false; lv_indev_read(pointer);
  CHECK(lv_screen_active() == screen && selected == 0 && strcmp(expectedKey, "codex") == 0);
  back(nullptr);

  // A provider moves to another protocol slot during a real touch. Release
  // follows the displayed identity; removal cannot open the replacement AI.
  set_sample(2, 2); ++sample.viewRevision; dashboard_update(); lv_obj_update_layout(dashboardScreen);
  touchPoint = {200, 120}; touchPressed = true; lv_indev_read(pointer);
  CHECK(lv_obj_has_state(big[0].card, LV_STATE_PRESSED));
  std::swap(sample.views[0], sample.views[1]);
  std::swap(sample.viewKeys[0], sample.viewKeys[1]); ++sample.viewRevision;
  dashboard_update(); CHECK(strcmp(big[0].providerKey, "codex") == 0);
  touchPressed = false; lv_indev_read(pointer);
  CHECK(lv_screen_active() == screen && selected == 1 && strcmp(expectedKey, "codex") == 0);
  back(nullptr); set_sample(2, 2); ++sample.viewRevision; dashboard_update(); lv_obj_update_layout(dashboardScreen);
  touchPressed = true; lv_indev_read(pointer);
  sample.viewCount = 1; std::strcpy(sample.viewKeys[0], "zcode"); sample.views[0] = sample.views[1]; ++sample.viewRevision;
  dashboard_update(); touchPressed = false; lv_indev_read(pointer);
  CHECK(dashboard_is_active()); dashboard_update();
  CHECK(lv_obj_get_x(big[0].card) == 20);
  CHECK(!lv_obj_is_hidden(pageButton) && lv_obj_has_state(pageButton, LV_STATE_DISABLED));
  screenshot(screenshots, "dashboard-stable-single-slot");

  set_sample(2, 2); ++sample.viewRevision; ui_nova_show(); lv_obj_update_layout(nova_ui::screen);
  touchPoint = {700, 265}; touchPressed = true; lv_indev_read(pointer);
  CHECK(lv_obj_has_state(nova_ui::providers[0].card, LV_STATE_PRESSED));
  std::swap(sample.views[0], sample.views[1]); std::swap(sample.viewKeys[0], sample.viewKeys[1]); ++sample.viewRevision;
  ui_nova_update(); CHECK(strcmp(nova_ui::providers[0].providerKey, "codex") == 0);
  touchPressed = false; lv_indev_read(pointer);
  CHECK(selected == 1 && strcmp(expectedKey, "codex") == 0); back(nullptr);
  set_sample(1, 2); ++sample.viewRevision; ui_nova_update();
  CHECK(!lv_obj_is_hidden(nova_ui::nextButton) && lv_obj_has_state(nova_ui::nextButton, LV_STATE_DISABLED));
  sample.hostPresent = false; ui_nova_update();
  CHECK(strcmp(lv_label_get_text(nova_ui::link), "Waiting for PC host") == 0);
  screenshot(screenshots, "nova-stable-offline-controls");

  set_sample(1, 3); ui_details_show(0); historyMode = false; ui_details_update();
  const auto rowY = lv_obj_get_y(rows[0].card), rowHeight = lv_obj_get_height(rows[0].card);
  snprintf(sample.views[0].message, sizeof(sample.views[0].message), "%s", "A very long retained provider error should stay in its reserved strip and never move a card, hide navigation, overlap percentages or shift UPDATE ALL.");
  sample.views[0].notice = true; ui_details_update(); lv_obj_update_layout(screen);
  CHECK(lv_obj_get_y(rows[0].card) == rowY && lv_obj_get_height(rows[0].card) == rowHeight);
  lv_area_t error{}, card{}; lv_obj_get_coords(errorBanner, &error); lv_obj_get_coords(rows[0].card, &card);
  CHECK(error.y2 < card.y1);
  screenshot(screenshots, "details-stable-long-error");

  ui_settings_show();
  // A modal shields covered BACK/actions. Interrupted time adjustment must
  // restore its draft and must not leak into the next persisted action.
  lv_obj_update_layout(settingsScreen);
  const auto brightnessBeforeCancel = display_get_brightness();
  const auto brightnessSaveBeforeCancel = app_settings::save_revision();
  lv_area_t sliderArea{}; lv_obj_get_coords(brightnessSlider, &sliderArea);
  touchPoint = {sliderArea.x1 + (sliderArea.x2 - sliderArea.x1) * brightness_percent(brightnessBeforeCancel) / 100,
                (sliderArea.y1 + sliderArea.y2) / 2};
  touchPressed = true; lv_indev_read(pointer);
  touchPoint.x = sliderArea.x1 + 60; lv_indev_read(pointer);
  CHECK(display_get_brightness() != brightnessBeforeCancel);
  touchFailed = true; lv_indev_read(pointer);
  CHECK(display_get_brightness() == brightnessBeforeCancel);
  CHECK(lv_slider_get_value(brightnessSlider) == brightness_percent(brightnessBeforeCancel));
  touchFailed = false; lv_indev_read(pointer);
  touchPressed = false; lv_indev_read(pointer);
  CHECK(app_settings::save_revision() == brightnessSaveBeforeCancel);
  open_night(nullptr); lv_obj_update_layout(lv_layer_top());
  touchPoint = {100, 450}; touchPressed = true; lv_indev_read(pointer);
  touchPressed = false; lv_indev_read(pointer);
  CHECK(ui_settings_is_active() && !lv_obj_is_hidden(nightOverlay));
  const auto persistedNight = app_settings::night();
  const auto beforeCancelledSave = app_settings::save_revision();
  lv_area_t timeArea{}; lv_obj_get_coords(nightTimeButtons[0], &timeArea);
  touchPoint = {(timeArea.x1 + timeArea.x2) / 2, (timeArea.y1 + timeArea.y2) / 2};
  touchPressed = true; lv_indev_read(pointer); fakeTick += 650; lv_indev_read(pointer);
  CHECK(nightDraft.start != persistedNight.start);
  touchPoint = {600, 300}; lv_indev_read(pointer);
  CHECK(nightDraft.start == persistedNight.start);  // restore before release
  lv_obj_get_coords(nightTimeButtons[1], &timeArea);
  touchPoint = {(timeArea.x1 + timeArea.x2) / 2, (timeArea.y1 + timeArea.y2) / 2};
  lv_indev_read(pointer);  // a different +/- cannot acquire this held finger
  touchPressed = false; lv_indev_read(pointer);
  CHECK(nightDraft.start == persistedNight.start);
  CHECK(app_settings::save_revision() == beforeCancelledSave);
  lv_obj_get_coords(nightTimeButtons[0], &timeArea);
  touchPoint = {(timeArea.x1 + timeArea.x2) / 2, (timeArea.y1 + timeArea.y2) / 2};
  touchPressed = true; lv_indev_read(pointer); fakeTick += 650; lv_indev_read(pointer);
  CHECK(nightDraft.start != persistedNight.start);
  touchFailed = true; lv_indev_read(pointer);
  CHECK(nightDraft.start == persistedNight.start);
  touchFailed = false; lv_indev_read(pointer);
  touchPressed = false; lv_indev_read(pointer);
  CHECK(app_settings::save_revision() == beforeCancelledSave);
  close_night(nullptr);
  for (auto opener : {open_alerts, open_night, open_appearance, open_quota}) {
    opener(nullptr); lv_obj_update_layout(lv_layer_top());
    auto* overlay = opener == open_alerts ? alertsOverlay : opener == open_night ? nightOverlay :
                    opener == open_appearance ? appearanceOverlay : quotaOverlay;
    for (auto* other : {alertsOverlay, nightOverlay, appearanceOverlay, quotaOverlay})
      CHECK(lv_obj_is_hidden(other) == (other != overlay));
    auto* done = find_caption_button(overlay, "DONE");
    CHECK(done != nullptr);
    if (done) {
      lv_area_t area{}; lv_obj_get_coords(done, &area);
      CHECK(area.x1 == 616 && area.y1 == 406 && lv_obj_get_width(done) == 136 && lv_obj_get_height(done) == 48);
      lv_obj_send_event(done, LV_EVENT_CLICKED, nullptr); CHECK(lv_obj_is_hidden(overlay));
    }
  }
  sample = aim::Snapshot{}; open_alerts(nullptr);
  CHECK(lv_obj_has_state(warningPrev, LV_STATE_DISABLED) && lv_obj_has_state(warningNext, LV_STATE_DISABLED));
  CHECK(lv_obj_has_state(warningInherit, LV_STATE_DISABLED));
  const auto warningBeforeCancel = warningPercent;
  lv_slider_set_value(warningSlider, 12, LV_ANIM_OFF);
  lv_obj_send_event(warningSlider, LV_EVENT_VALUE_CHANGED, nullptr);
  lv_obj_send_event(warningSlider, LV_EVENT_PRESS_LOST, nullptr);
  CHECK(lv_slider_get_value(warningSlider) == warningBeforeCancel);
  CHECK(warningPercent == warningBeforeCancel);
  close_alerts(nullptr);
  ui_settings_hide(); nova_ui::show_dashboard(nullptr);
  quota_banner::policy = QuotaNotifications{}; quota_banner::displayed = QuotaNotifications::Alert{};
  set_sample(1, 1); sample.views[0].rows[0].usedPercent = 5; ui_notifications_update();
  std::memset(sample.views[0].rows[0].title, 'W', sizeof(sample.views[0].rows[0].title) - 1);
  sample.views[0].rows[0].title[sizeof(sample.views[0].rows[0].title) - 1] = '\0';
  ui_notifications_update();
  lv_obj_update_layout(lv_layer_top());
  lv_point_t wrappedSize{};
  lv_text_get_size(&wrappedSize, lv_label_get_text(quota_banner::body),
                   lv_obj_get_style_text_font(quota_banner::body, LV_PART_MAIN), 0, 0,
                   lv_obj_get_content_width(quota_banner::body), LV_TEXT_FLAG_NONE);
  CHECK(wrappedSize.y <= lv_obj_get_height(quota_banner::body));
  lv_area_t alertBody{}, alertPending{}; lv_obj_get_coords(quota_banner::body, &alertBody);
  lv_obj_get_coords(quota_banner::pending, &alertPending); CHECK(alertBody.y2 < alertPending.y1);
  screenshot(screenshots, "quota-long-window-name");
  touchPoint = {650, 150}; touchPressed = true; lv_indev_read(pointer);
  CHECK(lv_obj_has_state(quota_banner::dismissButton, LV_STATE_PRESSED));
  sample.views[0].rows[0].usedPercent = 80; ui_notifications_update();
  CHECK(!lv_obj_is_hidden(quota_banner::banner));
  touchPressed = false; lv_indev_read(pointer); ui_notifications_update();
  CHECK(lv_obj_is_hidden(quota_banner::banner));
  lv_indev_delete(pointer);
  // Every navigation/action rectangle survives busy, offline, new data and
  // palette changes. Captions and disabled styling may change in place.
  std::vector<ButtonGeometry> geometry;
  for (auto* root : {dashboardScreen, nova_ui::screen, settingsScreen, screen, lv_layer_top()}) {
    lv_obj_update_layout(root); capture_button_geometry(root, geometry);
  }
  for (int transition = 0; transition < 4; ++transition) {
    set_sample(transition % 2 ? 1 : 8, 3);
    sample.hostPresent = transition != 1; sample.manualRefreshSupported = true;
    sample.refreshState = transition == 2 ? aim::RefreshState::updating : aim::RefreshState::idle;
    ui_theme::apply(static_cast<app_settings::Theme>(transition));
    nova_ui::show_dashboard(nullptr); dashboard_update(); ui_nova_show();
    ui_details_show(0); ui_settings_show(); ui_settings_update(); ui_settings_hide();
    for (auto* root : {dashboardScreen, nova_ui::screen, settingsScreen, screen, lv_layer_top()}) lv_obj_update_layout(root);
    for (const auto& saved : geometry) {
      lv_area_t current{}; lv_obj_get_coords(saved.button, &current);
      CHECK(current.x1 == saved.area.x1 && current.y1 == saved.area.y1 &&
            current.x2 == saved.area.x2 && current.y2 == saved.area.y2);
    }
  }
  ui_theme::apply(app_settings::Theme::forest);
  char window[24]; quota_window_label(60, "Hourly", window, sizeof(window)); CHECK(strcmp(window, "1 HOUR") == 0);
  quota_window_label(120, "Hourly", window, sizeof(window)); CHECK(strcmp(window, "2 HOURS") == 0);
  set_sample(2, 2); dashboard_update();
}

static void test_reported_session_poses(const std::filesystem::path& screenshots) {
  ui_settings_hide(); ui_nova_show(); fakeTick += 5000;
  set_sample(1, 1); sample.hostPresent = true; sample.viewsConfigured = true;
  std::strcpy(sample.viewKeys[0], "claude"); std::strcpy(sample.views[0].providerKey, "claude");
  sample.views[0].informational = true; sample.views[0].hasUsage = false;
  sample.views[0].rowCount = 0; sample.sessionCount = 1; sample.sessionActivityMs = fakeTick;
  sample.sessions[0] = aim::SessionCounts{1,0,0,0,4};
  ui_nova_update(); CHECK(nova_ui::mood == NovaMood::session_working);
  CHECK(std::string(lv_label_get_text(nova_ui::title)) == "Working");
  const auto update_x = lv_obj_get_x(nova_ui::updateButton), update_y = lv_obj_get_y(nova_ui::updateButton);
  screenshot(screenshots, "nova-session-working");
  sample.sessions[0] = aim::SessionCounts{0,1,0,0,4}; ui_nova_update();
  CHECK(nova_ui::mood == NovaMood::attention);
  CHECK(std::string(lv_label_get_text(nova_ui::title)) == "Needs you");
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].status)) == "SESSION / needs you");
  screenshot(screenshots, "nova-session-waiting");
  sample.sessions[0] = aim::SessionCounts{0,0,1,0,4}; ui_nova_update();
  CHECK(nova_ui::mood == NovaMood::completed); screenshot(screenshots, "nova-session-complete");
  sample.sessions[0] = aim::SessionCounts{0,0,0,1,4}; ui_nova_update();
  CHECK(nova_ui::mood == NovaMood::session_error); screenshot(screenshots, "nova-session-error");
  CHECK(lv_obj_get_x(nova_ui::updateButton) == update_x && lv_obj_get_y(nova_ui::updateButton) == update_y);
  sample.sessionActivityMs = fakeTick - 35000u; ui_nova_update();
  CHECK(nova_ui::mood != NovaMood::session_error);
  sample.sessionCount = 0;
}

int main(int argc, char** argv) {
  const std::filesystem::path screenshots = argc > 1 ? argv[1] : "";
  lv_init();
  lv_tick_set_cb(millis);
  auto* display = lv_display_create(800, 480);
  lv_display_set_color_format(display, LV_COLOR_FORMAT_XRGB8888);
  lv_display_set_buffers(display, drawBuffer, nullptr, sizeof(drawBuffer), LV_DISPLAY_RENDER_MODE_FULL);
  lv_display_set_flush_cb(display, flush);
  testInitialBrightnessPending = true; testInitialBrightness = 90;
  idle_dim_update();
  CHECK(selectedBrightness == 90 && actualBrightness == 90 && !lastPersisted);
  display_apply_brightness(110, false);
  testInitialBrightnessPending = true; testInitialBrightness = 30;
  idle_dim_update();
  CHECK(selectedBrightness == 110);  // A user override wins over recovered NVS.
  display_apply_brightness(160, false); idle_dim_touch(true); idle_dim_touch(false);
  dashboard_init();
#if defined(AIM_BOARD_WAVESHARE_S3)
  CHECK(strcmp(lv_label_get_text(hdr.eyebrow), "AI MONITOR / S3") == 0);
#else
  CHECK(strcmp(lv_label_get_text(hdr.eyebrow), "AI MONITOR / P4") == 0);
#endif
  ui_settings_init();
  ui_details_init();
  ui_notifications_init();
  ui_nova_init();
  settle_backlight();

  // First activity-only frame clears initialized quota headings and remains
  // healthy only when this provider's own counter source is readable.
  set_sample(1, 0);
  std::strcpy(sample.viewKeys[0], "gemini"); std::strcpy(sample.views[0].providerKey, "gemini");
  sample.views[0].hasUsage = false;
  sample.views[0].notice = sample.views[0].informational = true;
  sample.tokenUsageKnown = true; sample.tokenSourceMask = 8; sample.tokenActivityMs = fakeTick;
  dashboard_update();
  CHECK(std::strcmp(lv_label_get_text(hdr.live), "LIVE") == 0);
  CHECK(std::strcmp(lv_label_get_text(footServices), "1 / 1 services online") == 0);
  CHECK(std::strcmp(lv_label_get_text(big[0].remaining), "LOCAL") == 0);
  sample.tokenSourceMask = 1; dashboard_update();
  CHECK(std::strcmp(lv_label_get_text(hdr.live), "ISSUE") == 0);
  set_sample(2, 2);
  std::strcpy(sample.viewKeys[1], "gemini"); std::strcpy(sample.views[1].providerKey, "gemini");
  sample.views[1].hasUsage = false; sample.views[1].rowCount = 0;
  sample.views[1].notice = sample.views[1].informational = true;
  sample.tokenUsageKnown = true; sample.tokenSourceMask = 8; sample.tokenActivityMs = fakeTick;
  dashboard_update();
  CHECK(std::strcmp(lv_label_get_text(hdr.live), "LIVE") == 0);
  CHECK(std::strcmp(lv_label_get_text(footServices), "2 / 2 services online") == 0);

  set_sample(2, 2);
  dashboard_update();
  screenshot(screenshots, "dashboard-two-rows");
  set_sample(1, 2);
  dashboard_update();
  lv_obj_update_layout(lv_screen_active());
  CHECK(lv_obj_get_x(big[0].card) == 20);
  screenshot(screenshots, "dashboard-single-provider");
  set_sample(2, 2);
  dashboard_update();
  lv_obj_update_layout(lv_screen_active());
  CHECK(lv_obj_get_x(big[0].card) == 20);
  lv_obj_update_layout(lv_screen_active());
  lv_area_t percentage{}, unit{};
  lv_obj_get_coords(big[0].rows[0].pct, &percentage);
  lv_obj_get_coords(big[0].rows[0].unit, &unit);
  CHECK(percentage.y2 < unit.y1);

  sample.views[0].rows[0].usedPercent = 10;
  sample.views[1].rows[0].usedPercent = 25;
  dashboard_update();
  CHECK(g_barColor[0][0] == C_RED);
  CHECK(g_barColor[1][0] == C_AMBER);
  CHECK(std::string(lv_label_get_text(big[0].rows[0].winMeta)).find("CRITICAL") != std::string::npos);
  screenshot(screenshots, "dashboard-low-quota");
  sample.views[0].showsRemaining = false;
  sample.views[0].rows[0].usedPercent = 90;
  dashboard_update();
  CHECK(g_barColor[0][0] == C_RED);
  sample.hostPresent = false;
  dashboard_update();
  CHECK(g_barColor[0][0] == C_META);
  CHECK(std::string(lv_label_get_text(footServices)) == "0 / 2 services online");
  CHECK(std::string(lv_label_get_text(big[0].vendor)).find("OFFLINE") != std::string::npos);
  screenshot(screenshots, "dashboard-offline");

  sample.hostPresent = true;
  std::strcpy(sample.displayTime, "23:59");
  sample.displaySeconds = 59;
  sample.displayTimeMs = fakeTick;
  fakeTick += 1000;
  dashboard_update();
  CHECK(std::string(lv_label_get_text(hdr.clock)) == "00:00");

  set_sample(2, 3);
  dashboard_update();
  lv_obj_update_layout(lv_screen_active());
  CHECK(big[0].rows[2].bar != nullptr);
  if (big[0].rows[2].bar) {
    CHECK(!lv_obj_is_hidden(big[0].rows[2].bar));
    check_inside(big[0].card, big[0].rows[2].reset);
  }
  screenshot(screenshots, "dashboard-three-rows");

  set_sample(4, 3);
  dashboard_update();
  lv_obj_update_layout(lv_screen_active());
  for (auto& card : compact) {
    for (auto& row : card.rows) {
      check_inside(card.card, row.reset);
      lv_area_t name{}, reset{};
      lv_obj_get_coords(row.name, &name);
      lv_obj_get_coords(row.reset, &reset);
      CHECK(name.x2 < reset.x1);
    }
  }
  screenshot(screenshots, "dashboard-four-providers");

  set_sample(8, 3);
  dashboard_update();
  CHECK(!lv_obj_is_hidden(pageButton));
  CHECK(std::string(lv_label_get_text(footServices)) == "8 / 8 services online");
  lv_obj_send_event(pageButton, LV_EVENT_CLICKED, nullptr);
  dashboard_update();
  CHECK(currentPage == 1);
  CHECK(std::string(lv_label_get_text(compact[0].name)) == "COPILOT");
  screenshot(screenshots, "dashboard-page-two");
  sample.automaticViews = true;
  sample.viewIntervalSeconds = 2;
  sample.activeView = 4;
  ++sample.viewRevision;
  dashboard_update();
  CHECK(currentPage == 1);
  fakeTick += 2000;
  dashboard_update();
  CHECK(currentPage == 0);

  set_sample(2, 2);
  ++sample.viewRevision;
  dashboard_update();
  CHECK(!lv_obj_is_hidden(pageButton) && lv_obj_has_state(pageButton, LV_STATE_DISABLED));
  CHECK(lv_obj_is_hidden(big[0].rows[2].bar));
  sample.views[0].notice = true;
  sample.views[0].hasUsage = false; sample.views[0].rowCount = 0;  // first-ever failed measurement
  std::strcpy(sample.views[0].message, "Codex: check login or API key");
  dashboard_update();
  CHECK(std::string(lv_label_get_text(big[0].rows[0].name)) == sample.views[0].message);
  CHECK(std::string(lv_label_get_text(big[0].remaining)).empty());
  CHECK(lv_obj_is_hidden(big[0].rows[0].bar));
  CHECK(std::string(lv_label_get_text(footServices)) == "1 / 2 services online");
  CHECK(std::string(lv_label_get_text(hdr.live)) == "PARTIAL");
  sample.views[1].notice = true;
  dashboard_update();
  CHECK(std::string(lv_label_get_text(hdr.live)) == "ISSUE");
  sample.views[1].notice = false;
  dashboard_update();
  sample.views[0].notice = false;
  sample.views[0].fetching = sample.views[1].fetching = true;
  dashboard_update();
  CHECK(std::string(lv_label_get_text(hdr.live)) == "FETCHING");
  sample.views[0].fetching = sample.views[1].fetching = false;
  sample.views[0].notice = true;
  dashboard_update();
  screenshot(screenshots, "dashboard-error");
  lv_display_trigger_activity(display);
  fakeTick += 60000;
  sample.lastFrameMs = fakeTick;  // usage continues to arrive while nobody touches the screen
  settle_backlight();
  dashboard_update();
  CHECK(actualBrightness < selectedBrightness);

  CHECK(!idle_dim_touch(true));
  CHECK(actualBrightness == selectedBrightness);
  CHECK(!idle_dim_touch(false));
  CHECK(idle_dim_touch(true));
  idle_dim_touch(false);

  ui_settings_show();
  screenshot(screenshots, "settings");
  for (auto* button : dimButtons) {
    CHECK(lv_obj_get_height(button) >= 48);
    check_inside(settingsScreen, button);
  }
  lv_obj_send_event(dimButtons[3], LV_EVENT_CLICKED, nullptr);
  CHECK(dimMinutes == 10);
  CHECK(lastDimChoice == 10);
  lv_obj_send_event(presetButtons[2], LV_EVENT_CLICKED, nullptr);
  CHECK(brightness_percent(selectedBrightness) == 75);
  CHECK(lastPersisted);
  CHECK(lv_slider_get_value(brightnessSlider) == 75);
  screenshot(screenshots, "settings-selected");
  lv_obj_send_event(dimButtons[1], LV_EVENT_CLICKED, nullptr);
  CHECK(dimMinutes == 1);
  selectedBrightness = brightness_raw(50);
  ui_settings_update();
  CHECK(lv_slider_get_value(brightnessSlider) == 50);
  CHECK(std::string(lv_label_get_text(brightnessValue)) == "50 %");
  lv_obj_set_state(brightnessSlider, LV_STATE_PRESSED, true);
  selectedBrightness = brightness_raw(60);
  ui_settings_update();
  CHECK(lv_slider_get_value(brightnessSlider) == 50);
  lv_obj_set_state(brightnessSlider, LV_STATE_PRESSED, false);
  ui_settings_update();
  CHECK(lv_slider_get_value(brightnessSlider) == 60);
  fakeTick += 60000;
  settle_backlight();
  CHECK(actualBrightness < selectedBrightness);
  selectedBrightness = actualBrightness = 0;
  idle_dim_touch(true);
  CHECK(selectedBrightness == brightness_raw(5));
  CHECK(actualBrightness == brightness_raw(5));
  CHECK(!lastPersisted);
  idle_dim_touch(true);
  idle_dim_touch(false);
  dimMinutes = 0;
  fakeTick += 600000;
  settle_backlight();
  CHECK(actualBrightness == selectedBrightness);
  idle_dim_preview();
  settle_backlight();
  CHECK(actualBrightness < selectedBrightness);
  idle_dim_touch(true);
  idle_dim_touch(false);
  selectedBrightness = actualBrightness = 0;
  CHECK(!idle_dim_touch(true));  // an awake screen blacked out by the host also wakes only
  CHECK(selectedBrightness == brightness_raw(5));
  char period[16];
  window_label(86400, period, sizeof(period));
  CHECK(std::string(period) == "60 DAYS");
  window_label(1440, period, sizeof(period));
  CHECK(std::string(period) == "1 DAY");
  lv_obj_send_event(dimButtons[0], LV_EVENT_CLICKED, nullptr);
  CHECK(dimMinutes == 0);
  idle_dim_touch(false);
  selectedBrightness = brightness_raw(75);
  settle_backlight();
  lv_obj_send_event(previewButton, LV_EVENT_CLICKED, nullptr);
  settle_backlight();
  CHECK(actualBrightness < selectedBrightness);
  lv_obj_send_event(alertsButton, LV_EVENT_CLICKED, nullptr);
  CHECK(!lv_obj_is_hidden(alertsOverlay));
  lv_slider_set_value(warningSlider, 30, LV_ANIM_OFF);
  lv_obj_send_event(warningSlider, LV_EVENT_VALUE_CHANGED, nullptr);
  CHECK(warningPercent == 25);  // a drag does not write flash
  lv_obj_send_event(warningSlider, LV_EVENT_RELEASED, nullptr);
  CHECK(warningPercent == 30);
  screenshot(screenshots, "settings-alerts");
  close_alerts(nullptr);
  ui_settings_hide();
  set_sample(2, 3);
  sample.manualRefreshSupported = true;
  sample.views[0].rows[0].usedPercent = 28;
  sample.views[0].rows[0].hasResetCountdown = true;
  sample.views[0].rows[0].resetSeconds = 2400;
  dashboard_update();
  CHECK(g_barColor[0][0] == C_AMBER);
  lv_obj_send_event(big[0].card, LV_EVENT_CLICKED, nullptr);
  CHECK(lv_screen_active() == screen);
  CHECK(selected == 0);
  CHECK(std::string(lv_label_get_text(rows[0].reset)).find("40 m") != std::string::npos);
  auto* pointer = lv_indev_create();
  lv_indev_set_type(pointer, LV_INDEV_TYPE_POINTER);
  lv_indev_set_read_cb(pointer, read_touch);
  lv_obj_update_layout(screen);
  touchPressed = true; touchPoint = {500, 280}; lv_indev_read(pointer);
  fakeTick += 30; touchPoint = {200, 280}; lv_indev_read(pointer);
  touchPressed = false; lv_indev_read(pointer);
  CHECK(selected == 1);  // actual pointer gesture, rather than calling next()
  previous(nullptr);
  CHECK(selected == 0);
  screenshot(screenshots, "provider-details");
  lv_obj_send_event(updateButton, LV_EVENT_CLICKED, nullptr);
  CHECK(requestedRefreshes == 1);
  // An I2C failure while touching UPDATE must not become a click. The held
  // finger remains suppressed after recovery until a confirmed release.
  touchPoint = {620, 450}; touchPressed = true; lv_indev_read(pointer);
  touchFailed = true; lv_indev_read(pointer);
  touchFailed = false; lv_indev_read(pointer);
  touchPressed = false; lv_indev_read(pointer);
  CHECK(requestedRefreshes == 1);
  touchPressed = true; lv_indev_read(pointer);
  touchPressed = false; lv_indev_read(pointer);
  CHECK(requestedRefreshes == 2);
  requestedRefreshes = 1;  // later refresh lifecycle assertions use one request
  sample.refreshState = aim::RefreshState::waiting;
  ui_details_update();
  CHECK(lv_obj_has_state(updateButton, LV_STATE_DISABLED));
  update(nullptr);
  CHECK(requestedRefreshes == 1);
  sample.refreshState = aim::RefreshState::complete;
  sample.refreshCompletedMs = fakeTick;
  ui_details_update();
  CHECK(std::string(lv_label_get_text(feedback)) == "Data updated");
  next(nullptr);
  CHECK(selected == 1);
  previous(nullptr);
  CHECK(selected == 0);
  fakeTick += 299970;  // include the 30 ms used by the pointer swipe
  sample.views[0].receivedMs = sample.views[0].quotaReceivedMs = fakeTick;
  sample.views[0].rows[0].usedPercent = 45;
  ui_details_update();
  toggle_history(nullptr);
  CHECK(historyMode && !lv_obj_is_hidden(historyPanel));
  CHECK(history.series(0).count == 2);
  screenshot(screenshots, "provider-history");
  CHECK(historyEdges == 3);
  ui_theme::apply(app_settings::Theme::ocean);
  ui_details_update();
  CHECK(lv_color_eq(lv_obj_get_style_text_color(historyLegends[0], LV_PART_MAIN), lv_color_hex(historyColors[0])));
  ui_theme::apply(app_settings::Theme::forest); ui_details_update();
  lv_obj_send_event(historyRangeButtons[1], LV_EVENT_CLICKED, nullptr);
  CHECK(historyRange == 1);
  CHECK(std::string(lv_label_get_text(historyHint)).find("6 h") != std::string::npos);
  lv_obj_send_event(historyRangeButtons[2], LV_EVENT_CLICKED, nullptr);
  CHECK(historyRange == 2);
  const auto cachedStyleWrites = detailStyleWrites;
  ui_details_update(); ui_details_update();
  CHECK(detailStyleWrites == cachedStyleWrites);
  sample.views[0].notice = true;
  ui_details_update();
  fakeTick += 600000;
  sample.views[0].notice = false;
  sample.views[0].receivedMs = sample.views[0].quotaReceivedMs = fakeTick;
  sample.views[0].rows[0].usedPercent = 60;
  ui_details_update();
  fakeTick += 300000;
  sample.views[0].receivedMs = sample.views[0].quotaReceivedMs = fakeTick;
  sample.views[0].rows[0].usedPercent = 55;
  ui_details_update();
  lv_obj_send_event(historyRangeButtons[0], LV_EVENT_CLICKED, nullptr);
  screenshot(screenshots, "provider-history-gap");
  CHECK(history.series(0).count == 4);
  CHECK(historyEdges == 6);  // two segments per row, with no line over the outage
  toggle_history(nullptr);
  fakeTick += 2400000;
  ui_details_update();
  CHECK(std::string(lv_label_get_text(rows[0].reset)).find("Reset due") != std::string::npos);
  sample.views[0].notice = true;
  std::strcpy(sample.views[0].message, "Full provider error: check login and credentials. This detailed message is longer than the dashboard preview and remains readable here.");
  ui_details_update();
  CHECK(std::string(lv_label_get_text(errorBanner)) == sample.views[0].message);
  CHECK(!lv_obj_is_hidden(rows[0].card));
  CHECK(detailBarColors[0] == ui_theme::muted);
  screenshot(screenshots, "provider-notice");
  back(nullptr); dashboard_update();
  CHECK(!lv_obj_is_hidden(big[0].rows[0].bar));
  CHECK(g_barColor[0][0] == C_META);
  screenshot(screenshots, "dashboard-retained-error");
  ui_details_show(0);
  std::strcpy(sample.viewKeys[0], "gemini");
  ui_details_update();
  CHECK(std::string(lv_label_get_text(notice)).find("view changed") != std::string::npos);
  back(nullptr);
  set_sample(8, 3);
  sample.automaticViews = false;
  ++sample.viewRevision;
  dashboard_update();
  currentPage = 1;
  dashboard_update();
  lv_obj_send_event(compact[0].card, LV_EVENT_CLICKED, nullptr);
  CHECK(selected == 4);
  CHECK(std::string(lv_label_get_text(title)).find("COPILOT") != std::string::npos);
  back(nullptr); ui_settings_show();
  lv_obj_send_event(nightButton, LV_EVENT_CLICKED, nullptr);
  CHECK(!lv_obj_is_hidden(nightOverlay));
  night_toggle_cb(nullptr);
  CHECK(nightSettings.enabled);
  lv_slider_set_value(nightSlider, 15, LV_ANIM_OFF);
  lv_obj_send_event(nightSlider, LV_EVENT_VALUE_CHANGED, nullptr);
  CHECK(nightSettings.percent == 20);
  lv_obj_send_event(nightSlider, LV_EVENT_RELEASED, nullptr);
  CHECK(nightSettings.percent == 15);
  screenshot(screenshots, "settings-night");
  auto* startTimeButton = nightTimeButtons[1];
  lv_obj_send_event(startTimeButton, LV_EVENT_SHORT_CLICKED, nullptr);
  CHECK(nightSettings.start == 1380);
  lv_obj_send_event(nightTimeButtons[0], LV_EVENT_LONG_PRESSED, nullptr);
  CHECK(nightSettings.start == 1380);  // holding changes the draft; persist only on release
  CHECK(nightDraft.start == 1320);
  lv_obj_send_event(nightTimeButtons[0], LV_EVENT_RELEASED, nullptr);
  CHECK(nightSettings.start == 1320);
  CHECK(selectedBrightness == brightness_raw(75));
  close_night(nullptr);
  dimMinutes = 0; selectedBrightness = brightness_raw(75);
  std::strcpy(sample.displayTime, "23:00"); sample.displayTimeMs = fakeTick;
  idle_dim_touch(true); idle_dim_touch(false); fakeTick += 60000; settle_backlight();
  CHECK(actualBrightness == brightness_raw(15));
  idle_dim_touch(true); settle_backlight();
  CHECK(actualBrightness == selectedBrightness);
  idle_dim_touch(false); fakeTick += 60000; settle_backlight();
  CHECK(actualBrightness == brightness_raw(15));
  nightSettings.enabled = false;
  settle_backlight();
  CHECK(actualBrightness == selectedBrightness);
  back(nullptr);
  sample.hostPresent = false; dashboard_update();
  CHECK(std::string(lv_label_get_text(footSync)) == "PC host needed");
  sample.hostPresent = true; sample.manualRefreshSupported = false; dashboard_update();
  CHECK(std::string(lv_label_get_text(footSync)) == "Update PC host");
  set_sample(2, 3);
  sample.manualRefreshSupported = true;
  sample.views[0].rows[0].usedPercent = 0.4f;
  sample.views[0].rows[1].usedPercent = 99.99f;
  dashboard_update();
  CHECK(std::string(lv_label_get_text(big[0].rows[0].pct)) == "0.4%");
  CHECK(std::string(lv_label_get_text(big[0].rows[1].pct)) == ">99.9%");
  screenshot(screenshots, "dashboard-precision");
  ui_details_show(0);
  CHECK(std::string(lv_label_get_text(rows[0].percent)) == "0.4%");
  screenshot(screenshots, "provider-precision");
  back(nullptr); ui_settings_show();
  lv_obj_send_event(alertsButton, LV_EVENT_CLICKED, nullptr);
  CHECK(alertTargetCount == 7);
  alertTargetIndex = 1; refresh_warning_target();
  CHECK(std::string(lv_label_get_text(warningTargetLabel)).find("CODEX / Session") != std::string::npos);
  lv_slider_set_value(warningSlider, 15, LV_ANIM_OFF);
  lv_obj_send_event(warningSlider, LV_EVENT_RELEASED, nullptr);
  CHECK(app_settings::warning_for("codex", "Session", 300) == 15);
  CHECK(app_settings::warning_for("codex", "Week", 10080) == 30);
  CHECK(app_settings::warning_for("zcode", "Session", 300) == 30);
  ui_settings_update();
  CHECK(std::string(lv_label_get_text(saveFeedback)) == "SAVED");
  screenshot(screenshots, "settings-window-alert");
  inherit_warning(nullptr);
  CHECK(app_settings::warning_for("codex", "Session", 300) == 30);
  app_settings::report_save(false); ui_settings_update();
  CHECK(std::string(lv_label_get_text(saveFeedback)) == "SAVE FAILED");
  screenshot(screenshots, "settings-save-failed");
  fakeTick += 5000; ui_settings_update(); CHECK(lv_obj_is_hidden(saveFeedback));
  close_alerts(nullptr);
  nightSettings = {true, 1320, 420, 15}; dimMinutes = 0;
  std::strcpy(sample.displayTime, "23:00"); sample.displayTimeMs = fakeTick;
  idle_dim_touch(true); idle_dim_touch(false); fakeTick += 60000;
  idle_dim_update(); fakeTick += 300; idle_dim_update();
  CHECK(actualBrightness > brightness_raw(15) && actualBrightness < selectedBrightness);
  CHECK(std::string(idle_dim_mode()) == "NIGHT");
  fakeTick += 300; idle_dim_update(); ui_settings_update();
  CHECK(std::string(lv_label_get_text(actualBrightnessLabel)) == "Actual 15 %\nNIGHT");
  screenshot(screenshots, "settings-actual-night");
  idle_dim_touch(true);
  CHECK(actualBrightness == selectedBrightness && std::string(idle_dim_mode()) == "NORMAL");
  lv_obj_send_event(nightButton, LV_EVENT_CLICKED, nullptr);
  nightDraft.start = 22 * 60; nightDraft.end = 7 * 60; refresh_night_controls();
  for (int i = 0; i < 15; ++i) lv_obj_send_event(nightTimeButtons[3], LV_EVENT_SHORT_CLICKED, nullptr);
  lv_obj_send_event(nightTimeButtons[4], LV_EVENT_SHORT_CLICKED, nullptr);
  for (int i = 0; i < 45; ++i) lv_obj_send_event(nightTimeButtons[7], LV_EVENT_LONG_PRESSED_REPEAT, nullptr);
  CHECK(nightSettings.start == 22 * 60 + 15);
  CHECK(nightSettings.end == 6 * 60);  // hold changes only the draft until release
  lv_obj_send_event(nightTimeButtons[7], LV_EVENT_RELEASED, nullptr);
  CHECK(nightSettings.end == 6 * 60 + 45);
  CHECK(std::string(lv_label_get_text(nightTimeValues[0])) == "22");
  CHECK(std::string(lv_label_get_text(nightTimeValues[1])) == "15");
  CHECK(std::string(lv_label_get_text(nightTimeValues[2])) == "06");
  CHECK(std::string(lv_label_get_text(nightTimeValues[3])) == "45");
  for (auto* button : nightTimeButtons) CHECK(lv_obj_get_height(button) >= 44);
  ui_settings_update(); screenshot(screenshots, "settings-night-precise");
  close_night(nullptr); ui_settings_hide();
  set_sample(1, 2);
  sample.views[0].rows[0].usedPercent = 24;
  sample.views[0].rows[1].usedPercent = 40;
  dashboard_update(); ui_notifications_update();
  CHECK(!lv_obj_is_hidden(quota_banner::banner));
  CHECK(std::string(lv_label_get_text(quota_banner::heading)).find("LOW QUOTA / CODEX") == 0);
  screenshot(screenshots, "quota-low-notification");
  lv_obj_send_event(quota_banner::dismissButton, LV_EVENT_CLICKED, nullptr);
  ui_notifications_update(); CHECK(lv_obj_is_hidden(quota_banner::banner));
  sample.views[0].rows[0].usedPercent = sample.views[0].rows[1].usedPercent = 40;
  ui_notifications_update();
  sample.views[0].rows[0].usedPercent = 24; ui_notifications_update();
  CHECK(std::string(quota_banner::displayed.title) == "Session");
  lv_obj_set_state(quota_banner::dismissButton, LV_STATE_PRESSED, true);
  sample.views[0].rows[1].usedPercent = 5; ui_notifications_update();
  CHECK(std::string(quota_banner::displayed.title) == "Session");  // do not swap messages under the finger
  lv_obj_set_state(quota_banner::dismissButton, LV_STATE_PRESSED, false);
  lv_obj_send_event(quota_banner::dismissButton, LV_EVENT_CLICKED, nullptr);
  CHECK(std::string(quota_banner::displayed.title) == "Week");
  lv_obj_send_event(quota_banner::dismissButton, LV_EVENT_CLICKED, nullptr);
  CHECK(lv_obj_is_hidden(quota_banner::banner));
  sample.views[0].rows[0].usedPercent = 5;
  dashboard_update(); ui_notifications_update(); CHECK(!lv_obj_is_hidden(quota_banner::banner));
  CHECK(std::string(lv_label_get_text(quota_banner::heading)).find("CRITICAL QUOTA") == 0);
  screenshot(screenshots, "quota-critical-notification");
  lv_obj_send_event(quota_banner::dismissButton, LV_EVENT_CLICKED, nullptr);
  ui_notifications_update(); CHECK(lv_obj_is_hidden(quota_banner::banner));
  sample.views[0].rows[0].usedPercent = 40; ui_notifications_update();
  sample.views[0].rows[0].usedPercent = 24;
  ui_settings_show(); ui_notifications_update(); CHECK(lv_obj_is_hidden(quota_banner::banner));
  ui_settings_hide(); ui_notifications_update(); CHECK(!lv_obj_is_hidden(quota_banner::banner));
  sample.hostPresent = false; ui_notifications_update(); CHECK(lv_obj_is_hidden(quota_banner::banner));
  sample.hostPresent = true; sample.views[0].notice = true;
  ui_notifications_update(); CHECK(lv_obj_is_hidden(quota_banner::banner));
  sample.views[0].notice = false; ui_notifications_update(); CHECK(!lv_obj_is_hidden(quota_banner::banner));
  lv_obj_send_event(quota_banner::dismissButton, LV_EVENT_CLICKED, nullptr);
  ui_notifications_update(); CHECK(lv_obj_is_hidden(quota_banner::banner));
  set_sample(2, 2); sample.manualRefreshSupported = true;
  sample.activity = aim::HostActivity::fetching; sample.activityMs = fakeTick;
  sample.tokenUsageKnown = sample.tokenUsageSeen = true; sample.tokenActivityMs = fakeTick; sample.lastTokenDelta = 1200;
  sample.tokenSourceMask = 3;
  ui_nova_show();
  CHECK(ui_nova_is_active() && nova_ui::mood == NovaMood::working);
  CHECK(std::string(lv_label_get_text(nova_ui::title)) == "Working");
  CHECK(std::string(lv_label_get_text(nova_ui::subtitle)) == "+1.2K registered tokens");
  CHECK(std::string(lv_label_get_text(nova_ui::tracking)) == "TRACKING / Codex + ZCode");
  CHECK(std::string(lv_label_get_text(nova_ui::hint)).find("Last increase: 0 s ago") == 0);
  CHECK(lv_image_get_src(nova_ui::providers[0].icon) == &nova_assets::openai48);
  CHECK(lv_image_get_src(nova_ui::providers[1].icon) == &nova_assets::zcode48);
  screenshot(screenshots, "nova-working");
  sample.views[0].fetching = true; ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].status)) == "UPDATING / last good");
  sample.views[0].fetching = false; sample.tokenSourceMask = 2; ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::tracking)) == "TRACKING / ZCode");
  sample.tokenActivityMs = fakeTick - 35000u; ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::subtitle)) == "Token signal unavailable");
  CHECK(std::string(lv_label_get_text(nova_ui::tracking)) == "TRACKING / signal lost");
  screenshot(screenshots, "nova-signal-lost");
  sample.tokenActivityMs = fakeTick; sample.tokenSourceMask = 3;
  sample.activity = aim::HostActivity::updated; sample.tokenIdleSeconds = 90; ui_nova_update();
  CHECK(nova_ui::mood == NovaMood::updated);
  screenshot(screenshots, "nova-updated");
  fakeTick += 5000; sample.activity = aim::HostActivity::idle;
  sample.tokenIdleSeconds = 100; sample.tokenActivityMs = fakeTick;
  sample.views[0].rows[1].usedPercent = 12; ui_nova_update();
  CHECK(nova_ui::mood == NovaMood::low);
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "12%");
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].status)) == "7 DAYS / AUTO");
  screenshot(screenshots, "nova-low");
  sample.views[0].rows[1].usedPercent = 5; ui_nova_update();
  CHECK(nova_ui::mood == NovaMood::critical);
  CHECK(lv_image_get_src(nova_ui::figure) == &nova_assets::critical);
  const auto requestsBefore = requestedRefreshes;
  lv_obj_send_event(nova_ui::updateButton, LV_EVENT_CLICKED, nullptr);
  CHECK(requestedRefreshes == requestsBefore + 1);
  sample.refreshState = aim::RefreshState::updating; ui_nova_update();
  CHECK(lv_obj_has_state(nova_ui::updateButton, LV_STATE_DISABLED));
  sample.refreshState = aim::RefreshState::idle;
  nova_ui::show_settings(nullptr); CHECK(ui_settings_is_active());
  ui_settings_hide(); CHECK(ui_nova_is_active());
  lv_obj_send_event(nova_ui::providers[0].card, LV_EVENT_CLICKED, nullptr);
  CHECK(lv_screen_active() == screen && selected == 0);
  next(nullptr); back(nullptr); CHECK(ui_nova_is_active());
  sample.views[0].rows[1].usedPercent = 60;
  lv_obj_send_event(nova_ui::stage, LV_EVENT_CLICKED, nullptr);
  CHECK(nova_ui::mood == NovaMood::greeting);
  fakeTick += 2200; ui_nova_update(); CHECK(nova_ui::mood == NovaMood::ready);
  nova_ui::show_dashboard(nullptr); dashboard_update();
  CHECK(lv_image_get_src(big[0].badgeLogo) == &nova_assets::openai42);
  CHECK(lv_obj_is_hidden(big[0].badgeLetter));
  CHECK(lv_image_get_src(big[1].badgeLogo) == &nova_assets::zcode42);
  screenshot(screenshots, "dashboard-real-logos");
  lv_obj_send_event(novaButton, LV_EVENT_CLICKED, nullptr); CHECK(ui_nova_is_active());
  sample.hostPresent = false; ui_nova_update(); CHECK(nova_ui::mood == NovaMood::offline);
  sample.hostPresent = true;
  nightSettings = {true, 0, 0, 20}; dimMinutes = 0; fakeTick += 60000; settle_backlight();
  sample.tokenActivityMs = fakeTick; sample.tokenIdleSeconds = 0; ui_nova_update();
  CHECK(nova_ui::mood == NovaMood::working);  // night brightness must not put an active robot to sleep
  screenshot(screenshots, "nova-active-while-dimmed");
  sample.tokenIdleSeconds = 300; ui_nova_update(); CHECK(nova_ui::mood == NovaMood::resting);
  screenshot(screenshots, "nova-resting");
  set_sample(2, 1);
  for (size_t i = 0; i < 2; ++i) {
    const char* key = i == 0 ? "claude" : "gemini";
    std::strcpy(sample.viewKeys[i], key); std::strcpy(sample.views[i].providerKey, key);
    sample.views[i].hasUsage = false; sample.views[i].rowCount = 0;
    sample.views[i].notice = sample.views[i].informational = true;
    std::strcpy(sample.views[i].message, "Local token activity; quota unavailable");
  }
  sample.tokenUsageKnown = sample.tokenUsageSeen = true; sample.tokenSourceMask = 12;
  sample.tokenActivityMs = fakeTick; sample.lastTokenDelta = 6500; sample.tokenIdleSeconds = 0;
  ui_nova_show();
  CHECK(nova_ui::mood == NovaMood::working);
  CHECK(std::string(lv_label_get_text(nova_ui::providers[0].percent)) == "LOCAL");
  CHECK(lv_obj_is_hidden(nova_ui::providers[0].bar));
  screenshot(screenshots, "nova-claude-gemini");
  set_sample(2, 2); sample.manualRefreshSupported = true;
  sample.tokenUsageKnown = sample.tokenUsageSeen = true; sample.tokenSourceMask = 3;
  sample.tokenActivityMs = fakeTick; sample.lastTokenDelta = 14500; sample.tokenIdleSeconds = 0;
  ui_nova_show();
  const auto brandColor = lv_obj_get_style_bg_color(nova_ui::providers[0].bar, LV_PART_INDICATOR);
  ui_settings_show(); open_appearance(nullptr);
  lv_obj_send_event(companionButtons[1], LV_EVENT_CLICKED, nullptr);
  lv_obj_send_event(themeButtons[1], LV_EVENT_CLICKED, nullptr);
  CHECK(app_settings::appearance().companion == app_settings::Companion::orbit);
  CHECK(ui_theme::background == 0x0A1622 && ui_theme::accent == 0x54C4F2);
  CHECK(lv_color_eq(lv_obj_get_style_bg_color(settingsScreen, LV_PART_MAIN), lv_color_hex(ui_theme::background)));
  CHECK(lv_color_eq(lv_obj_get_style_border_color(themeButtons[0],LV_PART_MAIN),lv_color_hex(ui_theme::palettes[0].accent)));
  CHECK(lv_color_eq(lv_obj_get_style_bg_color(nova_ui::providers[0].bar, LV_PART_INDICATOR),brandColor));
  ui_settings_update();
  CHECK(std::string(lv_label_get_text(saveFeedback)) == "SAVED");
  screenshot(screenshots, "settings-appearance-ocean");
  close_appearance(nullptr); ui_settings_hide(); ui_nova_update();
  CHECK(std::string(lv_label_get_text(nova_ui::companionLabel)) == "ORBIT");
  CHECK(lv_image_get_src(nova_ui::figure) == &nova_assets::orbit_work || lv_image_get_src(nova_ui::figure) == &nova_assets::orbit_blink);
  screenshot(screenshots, "orbit-ocean");
  CHECK((framebuffer[120 * 800 + 50] & 0xffffffu) == ui_theme::surface);
  nova_ui::show_dashboard(nullptr); dashboard_update();
  CHECK(std::string(lv_label_get_text(lv_obj_get_child(novaButton,0))) == "ORBIT");
  screenshot(screenshots, "dashboard-ocean");
  ui_details_show(0); ui_details_update(); screenshot(screenshots, "details-ocean");
  ui_settings_show(); open_appearance(nullptr);
  for (size_t i = 0; i < 4; ++i) {
    lv_obj_send_event(themeButtons[i], LV_EVENT_CLICKED, nullptr);
    CHECK(lv_color_eq(lv_obj_get_style_bg_color(nova_ui::screen,LV_PART_MAIN),lv_color_hex(ui_theme::palettes[i].background)));
  }
  lv_obj_send_event(themeButtons[2], LV_EVENT_CLICKED, nullptr);
  close_appearance(nullptr); ui_settings_hide(); ui_nova_show();
  screenshot(screenshots, "orbit-amethyst");
  ui_settings_show(); open_appearance(nullptr);
  lv_obj_send_event(companionButtons[0], LV_EVENT_CLICKED, nullptr);
  lv_obj_send_event(themeButtons[3], LV_EVENT_CLICKED, nullptr);
  close_appearance(nullptr); ui_settings_hide(); ui_nova_show();
  CHECK(std::string(lv_label_get_text(nova_ui::companionLabel)) == "NOVA");
  screenshot(screenshots, "nova-ember");
  idle_dim_touch(true); idle_dim_touch(false); nightSettings.enabled = false;
  set_sample(8, 3); sample.manualRefreshSupported = true;
  ui_nova_update(); CHECK(nova_ui::pageCount == 4);
  lv_obj_send_event(nova_ui::nextButton, LV_EVENT_CLICKED, nullptr);
  CHECK(nova_ui::page == 1 && nova_ui::providers[0].view == 2);
  auto* dimmer = create_visual_dimmer();
  apply_visual_dimmer(dimmer, 255);
  CHECK(lv_obj_has_flag(dimmer, LV_OBJ_FLAG_HIDDEN));
  apply_visual_dimmer(dimmer, 80);
  CHECK(!lv_obj_has_flag(dimmer, LV_OBJ_FLAG_HIDDEN));
  CHECK(lv_obj_get_style_bg_opa(dimmer, LV_PART_MAIN) == 175);
  CHECK(!lv_obj_has_flag(dimmer, LV_OBJ_FLAG_CLICKABLE));
  CHECK(lv_obj_get_parent(dimmer) == lv_layer_sys());
  lv_obj_delete(dimmer);
  test_quota_windows(screenshots);
  test_nova_readability(screenshots);
  test_stable_touch_targets(screenshots);
  test_reported_session_poses(screenshots);
  auto* rendered = lv_image_create(lv_screen_active());
  CompanionRenderer cropRenderer;
  const lv_image_dsc_t* poses[] = {&nova_assets::work, &nova_assets::done, &nova_assets::low,
      &nova_assets::critical, &nova_assets::sleep, &nova_assets::blink};
  for (bool orbit : {false, true}) for (const auto* pose : poses) {
    cropRenderer.render(rendered, orbit, pose, -40, -2);
    lv_obj_update_layout(rendered);
    CHECK(lv_image_get_src(rendered) == nova_assets::companion_pose(orbit, pose));
    CHECK(lv_obj_get_x(rendered) == -40 + (orbit ? nova_assets::orbit_origin_x : nova_assets::nova_origin_x));
    CHECK(lv_obj_get_y(rendered) == -2 + (orbit ? nova_assets::orbit_origin_y : nova_assets::nova_origin_y));
  }
  CHECK(!cropRenderer.render(rendered,CompanionFrameView{},0,0));
  CHECK(cropRenderer.render(rendered,{&nova_assets::work,3,4},10,20));
  lv_obj_update_layout(rendered);
  CHECK(lv_obj_get_x(rendered)==13 && lv_obj_get_y(rendered)==24);
  lv_image_set_src(rendered,&nova_assets::done); // Another source owner replaced the image.
  CHECK(cropRenderer.render(rendered,{&nova_assets::work,3,4},10,20));
  CHECK(lv_image_get_src(rendered)==&nova_assets::work);
  lv_obj_delete(rendered);
  {
    uint8_t pixels[128]{},encoded[12];memset(encoded,255,sizeof(encoded));
    companions::FrameCache cache;CHECK(cache.initialize(pixels,sizeof(pixels),64));
    companions::Frame frame;frame.width=2;frame.height=2;frame.originX=3;frame.originY=4;
    frame.encodedBytes=frame.decodedBytes=12;
    auto hash=[](const uint8_t*,size_t,const char*) { return true; };
    auto decode=[](companions::Codec,const uint8_t* input,size_t length,uint8_t* out,size_t capacity) {
      if (length!=capacity)return false;
      memcpy(out,input,length);return true;
    };
    auto* target=lv_image_create(lv_screen_active());
    auto* other=lv_image_create(lv_screen_active());
    companions::ImageBinding binding(&nova_assets::work,nova_assets::nova_origin_x,nova_assets::nova_origin_y);
    CHECK(cache.load(frame,companions::Codec::raw,pixels,12,hash,decode)==-1);
    int first=cache.load(frame,companions::Codec::raw,encoded,12,hash,decode);CHECK(first==0);
    CHECK(binding.activate(target,cache,first,10,20));
    lv_obj_update_layout(target);CHECK(lv_obj_get_x(target)==13 && lv_obj_get_y(target)==24);
    const auto* descriptor=static_cast<const lv_image_dsc_t*>(lv_image_get_src(target));
    CHECK(descriptor->data==cache.slot(first)->pixels && descriptor->header.cf==LV_COLOR_FORMAT_RGB565A8);
    CHECK(cache.slot(first)->pinned);
    companions::ImageBinding competing(&nova_assets::work);
    CHECK(!competing.activate(other,cache,first,0,0));
    CHECK(!binding.activate(other,cache,first,0,0));
    CHECK(binding.activate(target,cache,first,20,30));lv_obj_update_layout(target);
    CHECK(lv_obj_get_x(target)==23 && lv_obj_get_y(target)==34);
    lv_image_set_src(target,&nova_assets::work);
    CHECK(binding.activate(target,cache,first,20,30));
    CHECK(lv_image_get_src(target)==descriptor);
    int second=cache.load(frame,companions::Codec::raw,encoded,12,hash,decode);CHECK(second==1);
    CHECK(binding.activate(target,cache,second,10,20));
    CHECK(!cache.slot(first)->pinned && cache.slot(second)->pinned);
    CHECK(!binding.activate(target,cache,2,0,0));
    binding.detach();CHECK(!cache.slot(second)->pinned);
    CHECK(lv_image_get_src(target)==&nova_assets::work);
    lv_obj_update_layout(target);
    CHECK(lv_obj_get_x(target)==10+nova_assets::nova_origin_x && lv_obj_get_y(target)==20+nova_assets::nova_origin_y);
    CHECK(binding.activate(target,cache,first,0,0));
    lv_obj_delete(target);CHECK(!cache.slot(first)->pinned);
    {
      companions::ImageBinding scoped(&nova_assets::work,nova_assets::nova_origin_x,nova_assets::nova_origin_y);
      CHECK(scoped.activate(other,cache,first,30,40));
    }
    CHECK(!cache.slot(first)->pinned && lv_image_get_src(other)==&nova_assets::work);
    lv_obj_delete(other);
  }
  if (failures) { std::cerr << failures << " UI checks failed\n"; return EXIT_FAILURE; }
  std::cout << "Real LVGL UI regressions passed\n";
}
