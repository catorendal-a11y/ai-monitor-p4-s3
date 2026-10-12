#include "ui_nova.h"
#include <Arduino.h>
#include <lvgl.h>
#include <cstdio>
#include <cstring>
#include "ai_monitor/ai_monitor.h"
#include "app_settings.h"
#include "ui/idle_dim.h"
#include "ui/nova_state.h"
#include "ui/nova_assets.h"
#include "ui/quota_alert.h"
#include "ui/quota_window.h"
#include "ui/theme.h"
#include "ui/interaction.h"
#include "ui_settings.h"
#include "ui_usage_details.h"

namespace nova_ui {
static lv_obj_t *screen = nullptr, *dashboard = nullptr, *stage = nullptr, *figure = nullptr;
static lv_obj_t *title = nullptr, *subtitle = nullptr, *hint = nullptr, *clock = nullptr, *link = nullptr;
static lv_obj_t* tracking = nullptr;
static lv_obj_t* companionLabel = nullptr;
static lv_obj_t *updateButton = nullptr, *updateLabel = nullptr, *nextButton = nullptr, *pageLabel = nullptr;
struct ProviderCard {
  lv_obj_t *card = nullptr, *icon = nullptr, *logoBox = nullptr, *name = nullptr, *percent = nullptr, *bar = nullptr, *status = nullptr;
  uint8_t view = 0;
  char providerKey[16] = {};
  uint32_t color = UINT32_MAX;
  const lv_image_dsc_t* logo = nullptr;
};
static ProviderCard providers[2];
static NovaState state;
static NovaMood mood = NovaMood::waiting;
static uint8_t page = 0, pageCount = 1;
static uint32_t lastRevision = UINT32_MAX;
static const lv_image_dsc_t* drawnPose = nullptr;
static uint32_t previousMotion = 0;

static void text(lv_obj_t* label, const char* value) {
  if (strcmp(lv_label_get_text(label), value) != 0) lv_label_set_text(label, value);
}
static lv_obj_t* label(lv_obj_t* parent, int x, int y, int width, const char* value, const lv_font_t* font, uint32_t color = ui_theme::text) {
  auto* object = lv_label_create(parent); lv_label_set_text(object, value);
  lv_obj_set_pos(object, x, y); lv_obj_set_width(object, width);
  lv_label_set_long_mode(object, LV_LABEL_LONG_MODE_CLIP);
  lv_obj_set_style_text_font(object, font, 0); lv_obj_set_style_text_color(object, lv_color_hex(color), 0);
  lv_obj_set_clickable(object, false);
  return object;
}
static lv_obj_t* button(lv_obj_t* parent, int x, int y, int width, const char* value, lv_event_cb_t callback, lv_obj_t** caption = nullptr) {
  auto* object = lv_btn_create(parent); lv_obj_set_pos(object, x, y); lv_obj_set_size(object, width, 48);
  lv_obj_set_style_bg_color(object, lv_color_hex(ui_theme::button), 0);
  lv_obj_set_style_bg_color(object, lv_color_hex(ui_theme::pressed), LV_STATE_PRESSED);
  lv_obj_set_style_bg_color(object, lv_color_hex(ui_theme::button), LV_STATE_DISABLED);
  lv_obj_set_style_opa(object, LV_OPA_50, LV_STATE_DISABLED);
  lv_obj_set_style_recolor_opa(object, LV_OPA_TRANSP, LV_STATE_DISABLED);
  lv_obj_set_style_radius(object, 12, 0); lv_obj_set_style_shadow_width(object, 0, 0);
  lv_obj_set_style_pad_all(object, 0, 0);
  auto* textLabel = label(object, 0, 0, width - 12, value, &lv_font_montserrat_16);
  lv_obj_set_style_text_align(textLabel, LV_TEXT_ALIGN_CENTER, 0); lv_obj_center(textLabel);
  lv_obj_add_event_cb(object, callback, LV_EVENT_CLICKED, nullptr);
  ui_interaction::keep_target(object);
  if (caption) *caption = textLabel;
  return object;
}
static void show_dashboard(lv_event_t*) { lv_screen_load(dashboard); }
static void show_settings(lv_event_t*) { ui_settings_show(); }
static void say_hi(lv_event_t*) { state.greet(millis()); ui_nova_update(); }
static void request_update(lv_event_t*) {
  const auto snapshot = aim::read();
  if (snapshot.hostPresent && snapshot.manualRefreshSupported && !refresh_busy(snapshot.refreshState)) aim::request_refresh();
}
static void next_page(lv_event_t*) { page = (page + 1) % pageCount; ui_nova_update(); }
static void details(lv_event_t* event) {
  auto* card = static_cast<ProviderCard*>(lv_event_get_user_data(event));
  if (!card) return;
  const auto snapshot = aim::read();
  for (size_t i = 0; i < aim::kMaxViews; ++i) {
    if (snapshot.viewsConfigured && i >= snapshot.viewCount) break;
    const char* key = snapshot.viewsConfigured ? snapshot.viewKeys[i] : snapshot.views[i].providerKey;
    if (card->providerKey[0] && strcmp(key, card->providerKey) == 0) { ui_details_show(static_cast<uint8_t>(i)); return; }
  }
}
}

namespace nova_ui {
void init() {
  dashboard = lv_screen_active();
  screen = lv_obj_create(nullptr);
  ui_theme::watch(screen);
  lv_obj_set_style_bg_color(screen, lv_color_hex(ui_theme::background), 0);
  lv_obj_set_style_pad_all(screen, 0, 0); lv_obj_set_style_border_width(screen, 0, 0);
  lv_obj_set_scrollable(screen, false);
  auto* header = lv_obj_create(screen); lv_obj_set_pos(header, 0, 0); lv_obj_set_size(header, 800, 78);
  lv_obj_set_style_bg_color(header, lv_color_hex(ui_theme::header), 0);
  lv_obj_set_style_border_width(header, 0, 0); lv_obj_set_style_pad_all(header, 0, 0);
  lv_obj_set_style_radius(header, 0, 0); lv_obj_set_scrollable(header, false);
  label(header, 24, 12, 400, "AI MONITOR / COMPANION", &lv_font_montserrat_12, ui_theme::muted);
  companionLabel = label(header, 24, 34, 360, "NOVA", &lv_font_montserrat_26);
  clock = label(header, 574, 28, 92, "--:--", &lv_font_montserrat_26);
  button(header, 672, 14, 104, "SET", show_settings);
  stage = lv_obj_create(screen); lv_obj_set_pos(stage, 20, 90); lv_obj_set_size(stage, 350, 315);
  lv_obj_set_style_bg_color(stage, lv_color_hex(ui_theme::surface), 0);
  lv_obj_set_style_border_color(stage, lv_color_hex(ui_theme::border), 0);
  lv_obj_set_style_border_width(stage, 1, 0); lv_obj_set_style_pad_all(stage, 0, 0);
  lv_obj_set_style_radius(stage, 22, 0); lv_obj_set_scrollable(stage, false);
  lv_obj_set_style_clip_corner(stage, true, 0);
  lv_obj_add_event_cb(stage, say_hi, LV_EVENT_CLICKED, nullptr);
  ui_interaction::keep_target(stage);
  figure = lv_image_create(stage); lv_obj_set_clickable(figure, false);
  // Keep the robot at its original size; trim only transparent canvas margins.
  lv_obj_set_x(figure, -40);
  lv_image_set_src(figure, &nova_assets::sleep);
  hint = label(stage, 12, 287, 326, "Tap NOVA to say hi", &lv_font_montserrat_12, ui_theme::muted);
  lv_obj_set_style_text_align(hint, LV_TEXT_ALIGN_CENTER, 0);
  label(screen, 394, 98, 382, "RIGHT NOW", &lv_font_montserrat_14, ui_theme::accent);
  title = label(screen, 394, 125, 382, "Waiting", &lv_font_montserrat_32);
  subtitle = label(screen, 394, 171, 382, "Waiting for provider data", &lv_font_montserrat_20, ui_theme::muted);
  tracking = label(screen, 394, 201, 382, "TRACKING / no counters", &lv_font_montserrat_14, ui_theme::muted);
  for (size_t i = 0; i < 2; ++i) {
    auto& item = providers[i];
    item.card = lv_obj_create(screen); lv_obj_set_pos(item.card, 390, 228 + i * 90); lv_obj_set_size(item.card, 390, 88);
    lv_obj_set_style_bg_color(item.card, lv_color_hex(ui_theme::background), 0);
    lv_obj_set_style_border_width(item.card, 0, 0); lv_obj_set_style_pad_all(item.card, 0, 0);
    lv_obj_set_scrollable(item.card, false);
    lv_obj_add_event_cb(item.card, details, LV_EVENT_CLICKED, &item);
    ui_interaction::keep_target(item.card);
    auto* logoBox = lv_obj_create(item.card); lv_obj_set_pos(logoBox, 4, 14); lv_obj_set_size(logoBox, 48, 48);
    item.logoBox = logoBox;
    lv_obj_set_style_bg_color(logoBox, lv_color_hex(0x0A1114), 0);
    lv_obj_set_style_border_color(logoBox, lv_color_hex(ui_theme::border), 0);
    lv_obj_set_style_border_width(logoBox, 1, 0); lv_obj_set_style_pad_all(logoBox, 0, 0);
    lv_obj_set_style_radius(logoBox, 12, 0); lv_obj_set_scrollable(logoBox, false); lv_obj_set_clickable(logoBox, false);
    item.icon = lv_image_create(logoBox); lv_obj_set_clickable(item.icon, false);
    item.name = label(item.card, 62, 4, 146, "", &lv_font_montserrat_20, ui_theme::muted);
    item.percent = label(item.card, 218, 0, 164, "--", &lv_font_montserrat_40);
    lv_obj_set_style_text_align(item.percent, LV_TEXT_ALIGN_RIGHT, 0);
    item.bar = lv_bar_create(item.card); lv_obj_set_pos(item.bar, 62, 50); lv_obj_set_size(item.bar, 320, 10);
    lv_bar_set_range(item.bar, 0, 100); lv_obj_set_clickable(item.bar, false);
    lv_obj_set_style_bg_color(item.bar, lv_color_hex(ui_theme::border), LV_PART_MAIN);
    item.status = label(item.card, 62, 66, 320, "", &lv_font_montserrat_16, ui_theme::muted);
  }
  pageLabel = label(screen, 394, 408, 382, "", &lv_font_montserrat_14, ui_theme::muted);
  link = label(screen, 24, 442, 260, "Waiting for PC host", &lv_font_montserrat_14, ui_theme::muted);
  button(screen, 288, 426, 160, "DASHBOARD", show_dashboard);
  nextButton = button(screen, 470, 426, 144, "NEXT PAIR", next_page);
  updateButton = button(screen, 628, 426, 148, "UPDATE ALL", request_update, &updateLabel);
}

bool is_active() { return screen && lv_screen_active() == screen; }
void show() { lv_screen_load(screen); ui_nova_update(); }

void update() {
  if (!is_active()) return;
  const auto snapshot = aim::read(); const uint32_t now = millis();
  const auto companion = app_settings::appearance().companion;
  text(companionLabel, app_settings::companion_name(companion));
  const bool resting = strcmp(idle_dim_mode(), "NIGHT") == 0 || strcmp(idle_dim_mode(), "IDLE") == 0;
  mood = state.evaluate(snapshot, now, resting, [](const char* provider, const aim::Row& row) {
    return app_settings::warning_for(provider, row.title, row.windowMinutes);
  });
  const char *heading = "Ready", *message = "Waiting for token activity";
  char tokenMessage[96];
  const auto sessions = session_status(snapshot, now);
  const lv_image_dsc_t* pose = &nova_assets::work;
  switch (mood) {
    case NovaMood::session_working:
      heading = "Working";
      snprintf(tokenMessage, sizeof(tokenMessage), "%u reported running %s", sessions.running, sessions.running == 1 ? "session" : "sessions");
      message = tokenMessage; break;
    case NovaMood::attention:
      heading = "Needs you";
      snprintf(tokenMessage, sizeof(tokenMessage), "%u %s waiting for input", sessions.waiting, sessions.waiting == 1 ? "session" : "sessions");
      message = tokenMessage; break;
    case NovaMood::completed: heading = "Turn complete"; message = "Reported by the AI client"; pose = &nova_assets::done; break;
    case NovaMood::session_error: heading = "Session error"; message = "Check the AI client on your PC"; break;
    case NovaMood::working: {
      heading = "Working";
      char count[24]; format_token_count(snapshot.lastTokenDelta, count, sizeof(count));
      snprintf(tokenMessage, sizeof(tokenMessage), "+%s registered tokens", count);
      message = tokenMessage; break;
    }
    case NovaMood::updated: heading = "Nice work"; message = "Token activity has paused"; pose = &nova_assets::done; break;
    case NovaMood::low: heading = "Low energy"; message = "A quota window is low"; pose = &nova_assets::low; break;
    case NovaMood::critical: heading = "Low energy"; message = "A quota window is critical"; pose = &nova_assets::critical; break;
    case NovaMood::resting: heading = "Resting"; message = "No recent token use"; pose = &nova_assets::sleep; break;
    case NovaMood::offline: heading = "Waiting"; message = "Start the PC host"; pose = &nova_assets::sleep; break;
    case NovaMood::waiting: heading = "Waiting"; message = "No fresh provider data"; pose = &nova_assets::sleep; break;
    case NovaMood::issue: heading = "Needs attention"; message = "Tap a provider for details"; pose = &nova_assets::low; break;
    case NovaMood::greeting: heading = "Hi there!"; message = "Ready when you are"; pose = &nova_assets::done; break;
    case NovaMood::ready: if (!token_signal_fresh(snapshot, now)) message = "Token signal unavailable"; break;
  }
  if ((mood == NovaMood::ready || mood == NovaMood::working || mood == NovaMood::session_working) && now % 4600u >= 3950u && now % 4600u < 4130u) pose = &nova_assets::blink;
  pose = nova_assets::companion_pose(companion == app_settings::Companion::orbit, pose);
  if (pose != drawnPose) { drawnPose = pose; lv_image_set_src(figure, pose); }
  // Small bounded motion: triangle-wave breathing, no image allocation per tick.
  if (now - previousMotion >= 160u) {
    previousMotion = now;
    const unsigned phase = now % 3200u;
    const int y = -static_cast<int>((phase < 1600u ? phase : 3200u - phase) * 3u / 1600u);
    if (lv_obj_get_y(figure) != y) lv_obj_set_y(figure, y);
  }
  text(title, heading); text(subtitle, message);
  const uint32_t stageColor = mood == NovaMood::attention ? 0xFFC857 :
      (mood == NovaMood::session_error ? 0xFF5252 : ui_theme::border);
  if (lv_color_to_u32(lv_obj_get_style_border_color(stage, LV_PART_MAIN)) != lv_color_to_u32(lv_color_hex(stageColor)))
    lv_obj_set_style_border_color(stage, lv_color_hex(stageColor), 0);
  uint16_t minutes = 0; char value[128];
  text(tracking, sessions.known ? "SESSION EVENTS / selected AIs" : token_tracking_label(snapshot, now));
  token_activity_hint(snapshot, now, value, sizeof(value));
  text(hint, mood == NovaMood::attention ? "Input needed in your AI client" :
      (mood == NovaMood::session_error ? "Check the AI client on your PC" : value));
  if (local_minutes(snapshot, now, minutes)) snprintf(value, sizeof(value), "%02u:%02u", minutes / 60, minutes % 60);
  else snprintf(value, sizeof(value), "--:--");
  text(clock, value);
  const char* refresh = refresh_hint(snapshot, now);
  text(link, !snapshot.hostPresent ? "Waiting for PC host" : (refresh[0] ? refresh : "USB CONNECTED"));
  const bool busy = refresh_busy(snapshot.refreshState);
  lv_obj_set_state(updateButton, LV_STATE_DISABLED, busy || !snapshot.hostPresent || !snapshot.manualRefreshSupported);
  text(updateLabel, busy ? "UPDATING..." : "UPDATE ALL");
  // Keep pair selection and visible provider targets stable until release.
  for (const auto& item : providers) if (lv_obj_has_state(item.card, LV_STATE_PRESSED)) return;
  if (lv_obj_has_state(nextButton, LV_STATE_PRESSED)) return;
  uint8_t indices[aim::kMaxViews]; size_t count = 0;
  for (size_t v = 0; v < aim::kMaxViews; ++v) {
    if (snapshot.viewsConfigured && v >= snapshot.viewCount) continue;
    if (snapshot.views[v].valid || (snapshot.viewsConfigured && snapshot.viewKeys[v][0])) indices[count++] = v;
  }
  pageCount = static_cast<uint8_t>(count ? (count + 1) / 2 : 1);
  if (lastRevision != snapshot.viewRevision) { lastRevision = snapshot.viewRevision; page = snapshot.activeView / 2 % pageCount; }
  page %= pageCount;
  lv_obj_set_state(nextButton, LV_STATE_DISABLED, pageCount < 2);
  if (pageCount > 1) snprintf(value, sizeof(value), "Providers / %u of %u", page + 1, pageCount);
  else snprintf(value, sizeof(value), "Tap a provider for all windows");
  text(pageLabel, value);
  for (size_t i = 0; i < 2; ++i) {
    auto& item = providers[i]; const size_t index = page * 2 + i;
    lv_obj_set_hidden(item.card, index >= count);
    if (index >= count) continue;
    item.view = indices[index]; const auto& view = snapshot.views[item.view];
    const char* key = view.valid ? view.providerKey : snapshot.viewKeys[item.view];
    snprintf(item.providerKey, sizeof(item.providerKey), "%s", key);
    const auto* style = aim::provider_style(key);
    const auto* brand = nova_assets::logo_for(key, 48);
    if (brand != item.logo) { item.logo = brand; if (brand) lv_image_set_src(item.icon, brand); }
    lv_obj_set_hidden(item.icon, !brand);
    lv_obj_set_hidden(item.logoBox, !brand);
    text(item.name, style ? style->label : key);
    const auto choice = app_settings::nova_window(key);
    const auto* selectedRow = nova_quota_row(view, key, choice);
    const bool hasRow = selectedRow != nullptr;
    const float remaining = hasRow ? (view.showsRemaining ? selectedRow->usedPercent : 100.0f - selectedRow->usedPercent) : 0;
    const bool fresh = hasRow && !view.notice && !view.fetching && snapshot.hostPresent && now - view.quotaReceivedMs < 300000u;
    const auto& row = selectedRow ? *selectedRow : view.rows[0];
    const uint32_t color = !fresh ? ui_theme::muted : (quota_critical(remaining, key, row) ? 0xFF5252 :
                            (quota_low(remaining, key, row) ? 0xFFAA00 : (style ? style->color : ui_theme::accent)));
    if (item.color != color) { item.color = color; lv_obj_set_style_bg_color(item.bar, lv_color_hex(color), LV_PART_INDICATOR); }
    if (view.informational) snprintf(value, sizeof(value), "LOCAL");
    else if (hasRow) format_percent(remaining, true, value, sizeof(value)); else snprintf(value, sizeof(value), "--");
    text(item.percent, value);
    lv_obj_set_hidden(item.bar, view.informational);
    if (lv_bar_get_value(item.bar) != static_cast<int32_t>(remaining)) lv_bar_set_value(item.bar, remaining, LV_ANIM_OFF);
    char period[48], selectedStatus[64];
    quota_window_label(row.windowMinutes, row.title, period, sizeof(period));
    snprintf(selectedStatus, sizeof(selectedStatus), "%s%s", period, choice.automatic ? " / AUTO" : "");
    const char* status = !snapshot.hostPresent ? "OFFLINE / last good" : (view.informational ? "Activity only / tap for setup" : (view.notice ? "ERROR / last good" :
                          (view.fetching ? "UPDATING / last good" : (!hasRow ? (choice.automatic ? "Waiting for data" : "Selected window unavailable") : (!fresh ? "STALE / last good" : selectedStatus)))));
    const auto provider_sessions = style ? session_status(snapshot, now, style->activityMask) : SessionStatus{};
    if (snapshot.hostPresent && provider_sessions.known) {
      if (provider_sessions.waiting) status = "SESSION / needs you";
      else if (provider_sessions.running) status = "SESSION / running";
      else if (provider_sessions.error) status = "SESSION / error";
      else if (provider_sessions.completed) status = "SESSION / turn complete";
    }
    text(item.status, status);
  }
}
}  // namespace nova_ui
void ui_nova_init() { nova_ui::init(); }
void ui_nova_show() { nova_ui::show(); }
void ui_nova_update() { nova_ui::update(); }
bool ui_nova_is_active() { return nova_ui::is_active(); }
