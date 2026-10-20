#include "ui_nova.h"
#include <Arduino.h>
#include <lvgl.h>
#include <cstdio>
#include <cstring>
#include <algorithm>
#include "ai_monitor/ai_monitor.h"
#include "app_settings.h"
#include "ui/idle_dim.h"
#include "ui/nova_state.h"
#include "ui/nova_assets.h"
#include "ui/companion_renderer.h"
#include "companions/builtin_animation.h"
#include "companions/runtime.h"
#if defined(CONFIG_IDF_TARGET_ESP32P4)
#include "companions/psram_cache.h"
#include "diagnostics/hardware_types.h"
#endif
#include "ui/quota_alert.h"
#include "ui/quota_window.h"
#include "ui/quota_headline.h"
#include "ui/session_hue.h"
#include "ui/theme.h"
#include "ui/interaction.h"
#include "ui/navigation.h"
#include "ui_settings.h"
#include "ui_usage_details.h"
#include "ui_agents.h"
#include "ui_menu.h"

namespace nova_ui {
static lv_obj_t *screen = nullptr, *dashboard = nullptr, *stage = nullptr, *figure = nullptr;
static lv_obj_t *title = nullptr, *subtitle = nullptr, *hint = nullptr, *clock = nullptr, *link = nullptr;
static lv_obj_t* tracking = nullptr;
static lv_obj_t* companionLabel = nullptr;
// The most urgent quota window as a ring, readable from across the desk.
static lv_obj_t *dial = nullptr, *dialValue = nullptr, *dialName = nullptr, *dialWindow = nullptr;
static uint32_t dialColor = UINT32_MAX;
// Avatar extras, all bounded runtime objects (no new artwork, so no flash cost). The look is a HUD,
// not a mascot: radar rings in the mood colour, one chip per live session, a status tag, corner
// brackets, a shockwave ring on completion or tap, and a STANDBY tag at rest.
static lv_obj_t *aura[3]{}, *satellites[8]{}, *standby = nullptr, *shock = nullptr, *brackets[6]{};
static uint32_t auraColor = UINT32_MAX, tapMs = 0, pingMs = 0, pingColor = 0, pingDuration = 0, bracketColor = UINT32_MAX;
static bool tapped = false, pinging = false;
static uint8_t tapCount = 0;
static NovaMood previousMood = NovaMood::waiting;
static constexpr uint32_t kHopMs = 480, kGreetMs = 1500;
// The aura fades and breathes, the stage floor tints toward the mood, a tag says what the sessions
// are doing and a chip carries the status line.
static lv_obj_t *bubble = nullptr, *bubbleDots[3]{}, *bubbleGlyph = nullptr, *pill = nullptr;
static uint32_t auraRgb = 0, auraShownRgb = UINT32_MAX, auraMs = 0, stageTint = UINT32_MAX, pillColor = UINT32_MAX;
static int auraLevel = 0;            // 0..255: how much of the aura is showing right now
static uint8_t bubbleKind = 255;     // 0 none, 1 working dots, 2 waiting "!", 3 error "!", 4 done "OK"
static char pillText[48] = {};

static uint32_t mix_color(uint32_t from, uint32_t to, unsigned percent) {
  uint32_t out = 0;
  for (int shift = 16; shift >= 0; shift -= 8) {
    const int a = (from >> shift) & 0xFF, b = (to >> shift) & 0xFF;
    out |= static_cast<uint32_t>(a + (b - a) * static_cast<int>(percent) / 100) << shift;
  }
  return out;
}
// One step of a cross-fade: every channel moves about a third of the way, and always at least one unit.
static uint32_t approach_color(uint32_t from, uint32_t to) {
  uint32_t out = 0;
  for (int shift = 16; shift >= 0; shift -= 8) {
    const int a = (from >> shift) & 0xFF, b = (to >> shift) & 0xFF;
    int step = (b - a) * 35 / 100;
    if (!step && b != a) step = b > a ? 1 : -1;
    out |= static_cast<uint32_t>(a + step) << shift;
  }
  return out;
}
static int triangle255(uint32_t t, uint32_t period) {
  const uint32_t p = t % period, half = period / 2;
  return static_cast<int>((p < half ? p : period - p) * 255u / half);
}
static const char* const kGreetings[] = {"ONLINE", "ACK", "LISTENING", "STANDING BY", "READY"};
static lv_obj_t *menuButton = nullptr, *nextButton = nullptr, *pageLabel = nullptr;
static lv_obj_t *refreshButton = nullptr, *refreshLabel = nullptr;
struct ProviderCard {
  lv_obj_t *card = nullptr, *icon = nullptr, *logoBox = nullptr, *name = nullptr, *percent = nullptr, *bar = nullptr, *status = nullptr, *session = nullptr;
  uint8_t view = 0;
  char providerKey[16] = {};
  uint32_t color = UINT32_MAX;
  const lv_image_dsc_t* logo = nullptr;
};
static ProviderCard providers[2];
static companions::AnimationPlayer animation;
static uint8_t animatedCompanion=255;
static NovaState state;
static NovaMood mood = NovaMood::waiting;
static uint8_t page = 0, pageCount = 1;
static uint32_t lastRevision = UINT32_MAX;
#if defined(CONFIG_IDF_TARGET_ESP32P4)
static companions::PsramCache companionCache;
static diagnostics::CompanionCache cacheTelemetry;
#endif
static CompanionRenderer renderer;
static void detach_external(){renderer.reset();animation=companions::AnimationPlayer{};animatedCompanion=255;}
static int motionY = 0;
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
  auto* textLabel = label(object, 0, 0, width - 12, value, &lv_font_montserrat_22);
  lv_obj_set_style_text_align(textLabel, LV_TEXT_ALIGN_CENTER, 0); lv_obj_center(textLabel);
  lv_obj_add_event_cb(object, callback, LV_EVENT_CLICKED, nullptr);
  ui_interaction::keep_target(object);
  if (caption) *caption = textLabel;
  return object;
}
static void show_menu(lv_event_t*) {ui_menu_show();}
static void request_refresh(lv_event_t*) {
  const auto snapshot = aim::read();
  if (snapshot.hostPresent && snapshot.manualRefreshSupported && !refresh_busy(snapshot.refreshState))
    aim::request_refresh();
}
static void say_hi(lv_event_t*) { state.greet(millis()); tapMs = millis(); tapped = true; ++tapCount;
  pingMs = tapMs; pingColor = ui_theme::muted; pingDuration = 450; pinging = true;   // a quiet ping ring
  ui_nova_update(); }
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
#if defined(CONFIG_IDF_TARGET_ESP32P4)
    if (companionCache.initialize(companions::max_frame_bytes)) {
      renderer.initialize(companionCache.frames(),companions::PsramCache::hash,companions::PsramCache::decode);
      cacheTelemetry.enabled=true;
      cacheTelemetry.allocatedBytes=companionCache.allocated_bytes();
    } else companions::runtime::rendering_ready(false);
#endif
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
  label(header, 24, 10, 500, "LIMITBUDDY", &lv_font_montserrat_18, ui_theme::muted);
  companionLabel = label(header, 24, 34, 360, "NOVA", &lv_font_montserrat_26);
  clock = label(header, 548, 28, 92, "--:--", &lv_font_montserrat_26);
  menuButton = button(header, 656, 14, 120, "MENU", show_menu);
  stage = lv_obj_create(screen); lv_obj_set_pos(stage, 20, 90); lv_obj_set_size(stage, 320, 315);
  lv_obj_set_style_bg_color(stage, lv_color_hex(ui_theme::surface), 0);
  lv_obj_set_style_border_color(stage, lv_color_hex(ui_theme::border), 0);
  lv_obj_set_style_border_width(stage, 1, 0); lv_obj_set_style_pad_all(stage, 0, 0);
  lv_obj_set_style_radius(stage, 22, 0); lv_obj_set_scrollable(stage, false);
  lv_obj_set_style_clip_corner(stage, true, 0);
  lv_obj_add_event_cb(stage, say_hi, LV_EVENT_CLICKED, nullptr);
  ui_interaction::keep_target(stage);
  for (int i = 0; i < 3; ++i) {   // radar rings behind the figure, so they are created first
    const int size = 252 - i * 46;
    aura[i] = lv_obj_create(stage); lv_obj_set_size(aura[i], size, size); lv_obj_set_pos(aura[i], 160 - size / 2, 150 - size / 2);
    lv_obj_set_style_radius(aura[i], LV_RADIUS_CIRCLE, 0); lv_obj_set_style_bg_opa(aura[i], LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(aura[i], i == 0 ? 1 : 2, 0); lv_obj_set_style_border_opa(aura[i], LV_OPA_TRANSP, 0);
    lv_obj_set_scrollable(aura[i], false); lv_obj_set_clickable(aura[i], false);
  }
  lv_obj_set_style_bg_grad_dir(stage, LV_GRAD_DIR_VER, 0);   // the colour at the bottom is set per mood
  figure = lv_image_create(stage); lv_obj_set_clickable(figure, false);
  // Keep the robot at its original size; trim only transparent canvas margins.
  lv_obj_set_x(figure, -55);
#if defined(CONFIG_IDF_TARGET_ESP32P4)
  const uint32_t firstFrameStarted=micros();
#endif
  renderer.render(figure,false,&nova_assets::sleep,-55,0);
#if defined(CONFIG_IDF_TARGET_ESP32P4)
  cacheTelemetry.lastSwitchUs=micros()-firstFrameStarted;
  cacheTelemetry.maxSwitchUs=cacheTelemetry.lastSwitchUs;
#endif
  dial = lv_arc_create(stage); lv_obj_set_size(dial, 64, 64); lv_obj_set_pos(dial, 250, 6);
  lv_arc_set_rotation(dial, 135); lv_arc_set_bg_angles(dial, 0, 270); lv_arc_set_range(dial, 0, 100); lv_arc_set_value(dial, 0);
  lv_obj_remove_style(dial, nullptr, LV_PART_KNOB); lv_obj_set_clickable(dial, false);
  lv_obj_set_style_arc_width(dial, 7, LV_PART_MAIN); lv_obj_set_style_arc_width(dial, 7, LV_PART_INDICATOR);
  lv_obj_set_style_arc_color(dial, lv_color_hex(ui_theme::muted), LV_PART_MAIN); lv_obj_set_style_arc_opa(dial, LV_OPA_30, LV_PART_MAIN);
  lv_obj_set_style_arc_rounded(dial, true, LV_PART_MAIN); lv_obj_set_style_arc_rounded(dial, true, LV_PART_INDICATOR);
  dialValue = label(stage, 250, 26, 64, "--", &lv_font_montserrat_18);
  lv_obj_set_style_text_align(dialValue, LV_TEXT_ALIGN_CENTER, 0);
  // Which window the ring is about sits beside it, clear of the robot's antenna and head.
  dialName = label(stage, 172, 15, 72, "", &lv_font_montserrat_14);
  lv_obj_set_style_text_align(dialName, LV_TEXT_ALIGN_RIGHT, 0);
  dialWindow = label(stage, 172, 33, 72, "", &lv_font_montserrat_14, ui_theme::muted);
  lv_obj_set_style_text_align(dialWindow, LV_TEXT_ALIGN_RIGHT, 0);
  lv_obj_set_hidden(dial, true); lv_obj_set_hidden(dialValue, true); lv_obj_set_hidden(dialName, true); lv_obj_set_hidden(dialWindow, true);
  for (int i = 0; i < 8; ++i) {   // one chip per live session, top left, clear of the antenna and the ring
    satellites[i] = lv_obj_create(stage); lv_obj_set_size(satellites[i], 10, 10); lv_obj_set_pos(satellites[i], 24 + i * 15, 16);
    lv_obj_set_style_radius(satellites[i], 2, 0); lv_obj_set_style_border_width(satellites[i], 0, 0);
    lv_obj_set_style_bg_opa(satellites[i], LV_OPA_COVER, 0); lv_obj_set_scrollable(satellites[i], false);
    lv_obj_set_clickable(satellites[i], false); lv_obj_set_hidden(satellites[i], true);
  }
  standby = label(stage, 24, 36, 90, "STANDBY", &lv_font_montserrat_14, ui_theme::muted);
  lv_obj_set_style_text_letter_space(standby, 2, 0); lv_obj_set_hidden(standby, true);
  bubble = lv_obj_create(stage); lv_obj_set_size(bubble, 62, 24); lv_obj_set_pos(bubble, 76, 34);
  lv_obj_set_style_radius(bubble, 3, 0); lv_obj_set_style_bg_color(bubble, lv_color_hex(ui_theme::background), 0);
  lv_obj_set_style_bg_opa(bubble, LV_OPA_COVER, 0); lv_obj_set_style_border_width(bubble, 1, 0);
  lv_obj_set_style_pad_all(bubble, 0, 0); lv_obj_set_scrollable(bubble, false); lv_obj_set_clickable(bubble, false);
  for (int i = 0; i < 3; ++i) {   // three blocks light up in turn while a session works
    bubbleDots[i] = lv_obj_create(bubble); lv_obj_set_size(bubbleDots[i], 12, 6); lv_obj_set_pos(bubbleDots[i], 6 + i * 16, 8);
    lv_obj_set_style_radius(bubbleDots[i], 1, 0); lv_obj_set_style_border_width(bubbleDots[i], 0, 0);
    lv_obj_set_style_bg_color(bubbleDots[i], lv_color_hex(ui_theme::accent), 0); lv_obj_set_style_bg_opa(bubbleDots[i], LV_OPA_30, 0);
    lv_obj_set_scrollable(bubbleDots[i], false); lv_obj_set_clickable(bubbleDots[i], false);
  }
  bubbleGlyph = label(bubble, 0, 3, 62, "", &lv_font_montserrat_14);
  lv_obj_set_style_text_align(bubbleGlyph, LV_TEXT_ALIGN_CENTER, 0); lv_obj_set_style_text_letter_space(bubbleGlyph, 1, 0);
  lv_obj_set_hidden(bubble, true);
  // Corner brackets frame the stage like a viewfinder; the top right belongs to the quota ring.
  static const int bx[6] = {8, 8, 8, 8, 296, 310}, by[6] = {8, 8, 305, 291, 305, 291};
  static const int bw[6] = {16, 2, 16, 2, 16, 2}, bh[6] = {2, 16, 2, 16, 2, 16};
  for (int i = 0; i < 6; ++i) {
    brackets[i] = lv_obj_create(stage); lv_obj_set_size(brackets[i], bw[i], bh[i]); lv_obj_set_pos(brackets[i], bx[i], by[i]);
    lv_obj_set_style_radius(brackets[i], 0, 0); lv_obj_set_style_border_width(brackets[i], 0, 0);
    lv_obj_set_style_bg_color(brackets[i], lv_color_hex(ui_theme::accent), 0); lv_obj_set_style_bg_opa(brackets[i], LV_OPA_40, 0);
    lv_obj_set_scrollable(brackets[i], false); lv_obj_set_clickable(brackets[i], false);
  }
  pill = lv_obj_create(stage); lv_obj_set_height(pill, 26); lv_obj_set_y(pill, 285);
  lv_obj_set_style_radius(pill, 4, 0); lv_obj_set_style_border_width(pill, 1, 0); lv_obj_set_style_pad_all(pill, 0, 0);
  lv_obj_set_style_bg_opa(pill, LV_OPA_COVER, 0); lv_obj_set_scrollable(pill, false); lv_obj_set_clickable(pill, false);
  lv_obj_set_hidden(pill, true);
  shock = lv_obj_create(stage); lv_obj_set_size(shock, 90, 90);   // one expanding ring, reused for completion and taps
  lv_obj_set_style_radius(shock, LV_RADIUS_CIRCLE, 0); lv_obj_set_style_bg_opa(shock, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_width(shock, 2, 0); lv_obj_set_scrollable(shock, false); lv_obj_set_clickable(shock, false);
  lv_obj_set_hidden(shock, true);
  hint = label(stage, 12, 289, 296, "Tap to ping", &lv_font_montserrat_18, ui_theme::muted);
  lv_obj_set_style_text_align(hint, LV_TEXT_ALIGN_CENTER, 0);
  label(screen, 364, 94, 412, "RIGHT NOW", &lv_font_montserrat_18, ui_theme::accent);
  title = label(screen, 364, 122, 412, "Waiting", &lv_font_montserrat_32);
  subtitle = label(screen, 364, 165, 412, "Waiting for provider data", &lv_font_montserrat_24, ui_theme::muted);
  tracking = label(screen, 364, 200, 412, "TRACKING / no counters", &lv_font_montserrat_18, ui_theme::muted);
  for (size_t i = 0; i < 2; ++i) {
    auto& item = providers[i];
    item.card = lv_obj_create(screen); lv_obj_set_pos(item.card, 360, 228 + i * 90); lv_obj_set_size(item.card, 420, 88);
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
    item.name = label(item.card, 62, 4, 174, "", &lv_font_montserrat_22, ui_theme::text);
    item.session = label(item.card, 62, 29, 174, "", &lv_font_montserrat_16, ui_theme::accent);
    item.percent = label(item.card, 242, 0, 170, "--", &lv_font_montserrat_40);
    lv_obj_set_style_text_align(item.percent, LV_TEXT_ALIGN_RIGHT, 0);
    item.bar = lv_bar_create(item.card); lv_obj_set_pos(item.bar, 62, 50); lv_obj_set_size(item.bar, 350, 10);
    lv_bar_set_range(item.bar, 0, 100); lv_obj_set_clickable(item.bar, false);
    lv_obj_set_style_bg_color(item.bar, lv_color_hex(ui_theme::border), LV_PART_MAIN);
    item.status = label(item.card, 62, 64, 350, "", &lv_font_montserrat_20, ui_theme::muted);
  }
  pageLabel = label(screen, 364, 408, 412, "", &lv_font_montserrat_18, ui_theme::muted);
  link = label(screen, 24, 410, 316, "Waiting for PC host", &lv_font_montserrat_14, ui_theme::muted);
  ui_navigation::create(screen,ui_navigation::Page::home);
  refreshButton = button(screen, 448, 432, 164, "REFRESH", request_refresh, &refreshLabel);
  nextButton = button(screen, 628, 432, 148, "NEXT", next_page);
}

bool is_active() { return screen && lv_screen_active() == screen; }
void show() { lv_screen_load(screen); ui_nova_update(); }

void update() {
  companions::runtime::ui_tick(detach_external);
  if (!is_active()) return;
  const auto snapshot = aim::read(); const uint32_t now = millis();
  const auto companion = app_settings::appearance().companion;
  const auto* external=companions::runtime::current();
  text(companionLabel, external?external->name:app_settings::companion_name(companion));
  const auto urgent = quota_headline(snapshot, now);
  lv_obj_set_hidden(dial, !urgent.valid); lv_obj_set_hidden(dialValue, !urgent.valid);
  lv_obj_set_hidden(dialName, !urgent.valid); lv_obj_set_hidden(dialWindow, !urgent.valid);
  if (urgent.valid) {
    const int32_t level = urgent.remaining < 0.0f ? 0 : urgent.remaining > 100.0f ? 100 : static_cast<int32_t>(urgent.remaining + 0.5f);
    if (lv_arc_get_value(dial) != level) lv_arc_set_value(dial, level);
    const uint32_t color = urgent.level == 2 ? 0xFF5252 : urgent.level == 1 ? 0xFFAA00 : ui_theme::accent;
    if (dialColor != color) {
      dialColor = color;
      lv_obj_set_style_arc_color(dial, lv_color_hex(color), LV_PART_INDICATOR);
      lv_obj_set_style_text_color(dialValue, lv_color_hex(color), 0);
    }
    char percent[8]; snprintf(percent, sizeof(percent), "%d%%", static_cast<int>(level));
    text(dialValue, percent); text(dialName, urgent.provider); text(dialWindow, urgent.window);
  }
  const bool resting = strcmp(idle_dim_mode(), "NIGHT") == 0 || strcmp(idle_dim_mode(), "IDLE") == 0;
  const auto live=live_agent::read_usb();const auto agentCounts=agent::read();
  mood = state.evaluate(snapshot, now, resting, [](const char* provider, const aim::Row& row) {
    return app_settings::warning_for(provider, row.title, row.windowMinutes);
  },agentCounts,live);
  const char *heading = "Ready", *message = "Waiting for token activity";
  char tokenMessage[96];
  const auto sessions = session_status(snapshot, now,255u,agentCounts,live);
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
      heading = "Recent activity";
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
  auto animationMood=companions::Mood::working;
  if(pose==&nova_assets::sleep)animationMood=companions::Mood::resting;
  else if(pose==&nova_assets::done)animationMood=companions::Mood::success;
  else if(pose==&nova_assets::low)animationMood=companions::Mood::warning;
  else if(pose==&nova_assets::critical)animationMood=companions::Mood::critical;
  if(mood==NovaMood::attention)animationMood=companions::Mood::attention;
  if(mood==NovaMood::session_error)animationMood=companions::Mood::error;
  // Detailed testing is used only when a current trusted lifecycle source explicitly reports it.
  if(mood==NovaMood::session_working && live.fresh && now-live.receivedAt<live_agent::activity_lease_ms)
    for(unsigned i=0;i<live.count && i<8;++i) {
      const auto& item=live.agents[i];const auto* style=aim::provider_style(item.provider);
      if(item.state==agent::State::TESTING && live_agent::observed_age_ms(live,item,now)<=30000u && style &&
         session_status(snapshot,now,style->activityMask,agentCounts,live).running)animationMood=companions::Mood::testing;
    }
  animation.select(external?external->resolve(animationMood):companions::builtin_animation(animationMood),now,animatedCompanion!=static_cast<uint8_t>(companion));
  animatedCompanion=static_cast<uint8_t>(companion);
  const lv_image_dsc_t* animatedPoses[]={&nova_assets::work,&nova_assets::done,&nova_assets::low,
    &nova_assets::critical,&nova_assets::sleep,&nova_assets::blink};
  const auto animationFrame=animation.frame(now);
  if(!external)pose=animatedPoses[animationFrame];
  // Small bounded motion: triangle-wave breathing, no image allocation per tick.
  int hop = 0;   // a short jump after a tap, a triangle wave over kHopMs
  if (tapped) {
    const uint32_t t = now - tapMs;
    if (t < kHopMs) hop = -static_cast<int>((t < kHopMs / 2 ? t : kHopMs - t) * 16u / (kHopMs / 2));
    else tapped = false;
  }
  if (now - previousMotion >= 160u) {
    previousMotion = now;
    const unsigned phase = now % 3200u;
    motionY = -static_cast<int>((phase < 1600u ? phase : 3200u - phase) * 3u / 1600u);
  }
#if defined(CONFIG_IDF_TARGET_ESP32P4)
  const auto decodeCount=renderer.decoded_frames(), failureCount=renderer.decode_failures();
  const uint32_t switchStarted=micros();
#endif
  if(!external || !renderer.render_external(figure,external->frames[animationFrame].frame,external->codec,
      companions::runtime::frame(animationFrame),-55,motionY + hop))
    renderer.render(figure, static_cast<uint8_t>(companion), pose, -55, motionY + hop);
#if defined(CONFIG_IDF_TARGET_ESP32P4)
  if (decodeCount!=renderer.decoded_frames() || failureCount!=renderer.decode_failures()) {
    cacheTelemetry.lastSwitchUs=micros()-switchStarted;
    cacheTelemetry.maxSwitchUs=std::max(cacheTelemetry.maxSwitchUs,cacheTelemetry.lastSwitchUs);
  }
  cacheTelemetry.decodedFrames=renderer.decoded_frames();cacheTelemetry.failures=renderer.decode_failures();
  cacheTelemetry.active=renderer.cache_active();diagnostics::publish_companion_cache(cacheTelemetry);
#endif
  // Status tag: what the sessions are doing, readable without the text on the right.
  uint8_t kind = 0;
  if (mood != NovaMood::resting) switch (mood) {
    case NovaMood::working: case NovaMood::session_working: kind = 1; break;
    case NovaMood::attention: kind = 2; break;
    case NovaMood::session_error: case NovaMood::critical: kind = 3; break;
    case NovaMood::completed: kind = 4; break;
    default: break;
  }
  lv_obj_set_hidden(bubble, kind == 0);
  if (kind != bubbleKind) {
    bubbleKind = kind;
    const uint32_t edge = kind == 3 ? 0xFF5252 : kind == 2 ? 0xFFC857 : ui_theme::accent;
    lv_obj_set_style_border_color(bubble, lv_color_hex(edge), 0);
    lv_obj_set_style_text_color(bubbleGlyph, lv_color_hex(edge), 0);
    for (auto* block : bubbleDots) lv_obj_set_hidden(block, kind != 1);
    lv_obj_set_hidden(bubbleGlyph, kind == 1);
    text(bubbleGlyph, kind == 4 ? "DONE" : kind == 3 ? "FAULT" : "WAIT");
  }
  if (kind == 1)
    for (int i = 0; i < 3; ++i) {   // a chase across three blocks, like a loading bar
      const lv_opa_t opa = static_cast<lv_opa_t>(60 + triangle255(now + static_cast<uint32_t>(2 - i) * 150u, 900u) * 195 / 255 / 32 * 32);
      if (lv_obj_get_style_bg_opa(bubbleDots[i], LV_PART_MAIN) != opa) lv_obj_set_style_bg_opa(bubbleDots[i], opa, 0);
    }
  text(title, heading); text(subtitle, message);
  const uint32_t stageColor = mood == NovaMood::attention ? 0xFFC857 :
      (mood == NovaMood::session_error ? 0xFF5252 : ui_theme::border);
  if (lv_color_to_u32(lv_obj_get_style_border_color(stage, LV_PART_MAIN)) != lv_color_to_u32(lv_color_hex(stageColor)))
    lv_obj_set_style_border_color(stage, lv_color_hex(stageColor), 0);
  uint16_t minutes = 0; char value[128];
  text(tracking, sessions.known ? "SESSION EVENTS / selected AIs" : token_tracking_label(snapshot, now));
  if(token_signal_fresh(snapshot,now) && snapshot.lastTokenDelta)
    snprintf(value,sizeof(value),"Tokens %llus ago",static_cast<unsigned long long>(token_idle_seconds(snapshot,now)));
  else snprintf(value,sizeof(value),"Tap to ping");
  const bool greeting = tapCount && now - tapMs < kGreetMs;
  text(hint, greeting ? kGreetings[(tapCount - 1) % (sizeof(kGreetings) / sizeof(kGreetings[0]))] :
             (mood == NovaMood::attention || mood == NovaMood::session_error ? "Check AI on your PC" : value));
  {   // Pill: the status line sits on a capsule in the mood colour, sized to its text.
    const char* shown = lv_label_get_text(hint);
    const uint32_t accent = mood == NovaMood::attention || mood == NovaMood::low ? 0xFFC857 :
        (mood == NovaMood::session_error || mood == NovaMood::critical || mood == NovaMood::issue ? 0xFF5252 : ui_theme::accent);
    if (strcmp(pillText, shown) != 0 || pillColor != accent) {
      snprintf(pillText, sizeof(pillText), "%s", shown);
      pillColor = accent;
      lv_point_t size{};
      lv_text_get_size(&size, shown, &lv_font_montserrat_18, 0, 0, LV_COORD_MAX, LV_TEXT_FLAG_NONE);
      const int width = size.x + 28 > 304 ? 304 : size.x + 28;
      lv_obj_set_width(pill, width); lv_obj_set_x(pill, (320 - width) / 2);
      lv_obj_set_style_bg_color(pill, lv_color_hex(mix_color(ui_theme::surface, accent, 16)), 0);
      lv_obj_set_style_border_color(pill, lv_color_hex(mix_color(ui_theme::surface, accent, 45)), 0);
      lv_obj_set_hidden(pill, false);
    }
  }
  // Aura: radar rings in the mood colour. Moods that carry no message, and rest, show none.
  uint32_t glow = 0;
  switch (mood) {
    case NovaMood::working: case NovaMood::session_working: case NovaMood::completed: case NovaMood::updated: glow = ui_theme::accent; break;
    case NovaMood::attention: case NovaMood::low: glow = 0xFFC857; break;
    case NovaMood::critical: case NovaMood::session_error: case NovaMood::issue: glow = 0xFF5252; break;
    default: break;
  }
  auraColor = glow;   // the target; what is drawn fades toward it
  {
    const uint32_t elapsed = now - auraMs;
    auraMs = now;
    const int step = elapsed > 400u ? 255 : static_cast<int>(elapsed * 255u / 400u);
    if (glow) {
      if (auraLevel == 0) auraRgb = glow;
      else if (auraRgb != glow) auraRgb = approach_color(auraRgb, glow);
      auraLevel = auraLevel + step > 255 ? 255 : auraLevel + step;
    } else auraLevel = auraLevel - step < 0 ? 0 : auraLevel - step;
    const int breath = 217 + triangle255(now, 3200u) * 38 / 255;   // 85 .. 100 %
    static const int base[3] = {LV_OPA_30, LV_OPA_50, LV_OPA_70};   // outer ring faintest, inner ring strongest
    for (int ring = 0; ring < 3; ++ring) {
      if (auraShownRgb != auraRgb) lv_obj_set_style_border_color(aura[ring], lv_color_hex(auraRgb), 0);
      const lv_opa_t opa = static_cast<lv_opa_t>(base[ring] * auraLevel / 255 * breath / 255);
      if (lv_obj_get_style_border_opa(aura[ring], LV_PART_MAIN) != opa) lv_obj_set_style_border_opa(aura[ring], opa, 0);
    }
    auraShownRgb = auraRgb;
    // The stage floor takes a little of the aura's colour, so the whole card reflects the mood.
    const uint32_t tint = mix_color(ui_theme::surface, auraRgb, static_cast<unsigned>(auraLevel * 16 / 255));
    if (tint != stageTint) { stageTint = tint; lv_obj_set_style_bg_grad_color(stage, lv_color_hex(tint), 0); }
    const uint32_t frame = auraLevel ? auraRgb : ui_theme::accent;
    if (frame != bracketColor) { bracketColor = frame; for (auto* corner : brackets) lv_obj_set_style_bg_color(corner, lv_color_hex(frame), 0); }
  }
  // Satellites: the sessions the PC reports right now, in the colour the Agents list gives them.
  const unsigned liveCount = live.fresh && now - live.receivedAt < live_agent::activity_lease_ms ? (live.count < 8 ? live.count : 8) : 0;
  for (unsigned i = 0; i < 8; ++i) {
    lv_obj_set_hidden(satellites[i], i >= liveCount);
    if (i >= liveCount) continue;
    const auto& entry = live.agents[i];
    const bool needsYou = entry.state == agent::State::WAITING || entry.state == agent::State::NEEDS_ATTENTION;
    lv_obj_set_style_bg_color(satellites[i], lv_color_hex(session_hue_colors[entry.hue < 12 ? entry.hue : 0]), 0);
    lv_obj_set_style_border_width(satellites[i], needsYou ? 2 : 0, 0);
    lv_obj_set_style_border_color(satellites[i], lv_color_hex(0xFFC857), 0);
  }
  // Rest: dim the figure a little and show the standby tag.
  const bool sleepy = mood == NovaMood::resting;   // night brightness alone does not put an active robot to sleep
  lv_obj_set_hidden(standby, !sleepy);
  lv_obj_set_style_image_recolor(figure, lv_color_black(), 0);
  lv_obj_set_style_image_recolor_opa(figure, sleepy ? LV_OPA_30 : LV_OPA_TRANSP, 0);
  // Completion: one shockwave ring leaves the figure per finished turn; a tap sends a quieter one.
  if (mood == NovaMood::completed && previousMood != NovaMood::completed) { pingMs = now; pingColor = ui_theme::accent; pingDuration = 800; pinging = true; }
  previousMood = mood;
  const uint32_t pingAge = now - pingMs;
  if (pinging && pingAge >= pingDuration) pinging = false;
  lv_obj_set_hidden(shock, !pinging);
  if (pinging) {
    const int diameter = 90 + static_cast<int>(pingAge * 190u / pingDuration);
    lv_obj_set_size(shock, diameter, diameter); lv_obj_set_pos(shock, 160 - diameter / 2, 150 - diameter / 2);
    lv_obj_set_style_border_color(shock, lv_color_hex(pingColor), 0);
    lv_obj_set_style_border_opa(shock, static_cast<lv_opa_t>(200u - pingAge * 200u / pingDuration), 0);
  }
  if (local_minutes(snapshot, now, minutes)) snprintf(value, sizeof(value), "%02u:%02u", minutes / 60, minutes % 60);
  else snprintf(value, sizeof(value), "--:--");
  text(clock, value);
  const char* refresh = refresh_hint(snapshot, now);
  text(link, !snapshot.hostPresent ? "Waiting for PC host" : (refresh[0] ? refresh : "USB CONNECTED"));
  const bool busy = refresh_busy(snapshot.refreshState);
  text(refreshLabel, busy ? "UPDATING" : "REFRESH");
  lv_obj_set_state(refreshButton, LV_STATE_DISABLED,
                   !snapshot.hostPresent || !snapshot.manualRefreshSupported || busy);
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
  lv_obj_set_hidden(nextButton, pageCount < 2);
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
    const bool fresh = hasRow && !view.notice && !view.fetching && snapshot.hostPresent && now - view.quotaReceivedMs < aim::kQuotaStaleMs;
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
    const auto provider_sessions = style ? session_status(snapshot, now, style->activityMask,agentCounts,live) : SessionStatus{};
    // Session events and quota freshness are independent signals. Never let one
    // erase the other; keep the existing card and touch target geometry stable.
    const char* session = "";
    if (snapshot.hostPresent && provider_sessions.known) {
      if (provider_sessions.waiting) session = "Session: needs you";
      else if (provider_sessions.running) session = "Session: running";
      else if (provider_sessions.error) session = "Session: error";
      else if (provider_sessions.completed) session = "Session: complete";
    }
    text(item.session, session);
    text(item.status, status);
  }
}
}  // namespace nova_ui
void ui_nova_init() { nova_ui::init(); }
void ui_nova_show() { nova_ui::show(); }
void ui_nova_update() { nova_ui::update(); }
bool ui_nova_is_active() { return nova_ui::is_active(); }
