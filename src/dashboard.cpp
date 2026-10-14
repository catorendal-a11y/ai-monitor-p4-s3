// AI Monitor P4 - Dashboard (v2 design)
// Pixel-matched to the user's ui_dashboard_preview_v2.svg:
//   header 78 px with eyebrow title, live dot + halo, 26 px clock, gear SET
//   button; two cards with provider-colored spine, letter badge, vendor meta,
//   "REMAINING" column, window meta rows, 30 px percentages with LEFT unit,
//   pill bars with light end-knob; system bar footer.
// Always show two full-size provider cards; extra providers use pages rather than tiny grids.

#include "dashboard.h"

#include <Arduino.h>
#include <lvgl.h>

#include <cstdio>
#include <cstring>
#include <algorithm>
#include <initializer_list>

#include "ai_monitor/ai_monitor.h"
#include "ui/backlight.h"
#include "ui/theme.h"
#include "ui/usage_format.h"
#include "ui/token_status.h"
#include "ui/session_status.h"
#include "ui/interaction.h"
#include "ui/quota_alert.h"
#include "ui_usage_details.h"
#include "ui_nova.h"
#include "ui/nova_assets.h"
#include "ui_settings.h"
#include "ui_menu.h"

// ───────────────────────────────────────────────────────────────────────────────
// V2 PALETTE (from the SVG)
// ───────────────────────────────────────────────────────────────────────────────
static const uint32_t& C_BG = ui_theme::background;
static const uint32_t& C_HEADER = ui_theme::header;
static const uint32_t& C_LINE = ui_theme::border;
static const uint32_t& C_LINE_SOFT = ui_theme::border;
static const uint32_t& C_EYEBROW = ui_theme::muted;
static const uint32_t& C_TITLE = ui_theme::text;
static const uint32_t& C_META = ui_theme::muted;
static const uint32_t& C_META_BRIGHT = ui_theme::muted;
static const uint32_t& C_CARD = ui_theme::surface;
static const uint32_t& C_NAME = ui_theme::text;
static const uint32_t& C_ROWLABEL = ui_theme::text;
static const uint32_t& C_PCT = ui_theme::text;
static const uint32_t& C_UNIT = ui_theme::muted;
static const uint32_t& C_RESET = ui_theme::muted;
static const uint32_t& C_BAR_TRACK = ui_theme::border;
static const uint32_t& C_SET_BG = ui_theme::button;
static const uint32_t& C_SET_BORDER = ui_theme::border;
static const uint32_t& C_GEAR = ui_theme::muted;
static const uint32_t& C_SET_TXT = ui_theme::text;
static const uint32_t& C_FOOTER_BG = ui_theme::header;
static const uint32_t& C_FOOTER_STRONG = ui_theme::text;
static const uint32_t& C_FOOTER = ui_theme::muted;
static const uint32_t& C_GREEN = ui_theme::accent;
static const uint32_t C_RED = 0xFF5252;
static const uint32_t C_AMBER = 0xFFAA00;

#define F_EYEBROW &lv_font_montserrat_18
#define F_META &lv_font_montserrat_16
#define F_ROWLABEL &lv_font_montserrat_22
#define F_PROVIDER &lv_font_montserrat_26
#define F_TIME &lv_font_montserrat_26
#define F_PCT &lv_font_montserrat_30
#define F_BADGE &lv_font_montserrat_22

static constexpr size_t kBigCards = 2;       // side-by-side (<= 2 providers)
static constexpr uint32_t STALE_MS = 300000;

// Per-provider v2 styling: brand base, light knob tint, badge colors, vendor.
struct V2Style {
  const char* key;
  uint32_t base;
  uint32_t light;
  uint32_t badgeFill;
  uint32_t badgeStroke;
  uint32_t badgeLetter;
  const char* vendor;
};

static const V2Style* v2_style(const char* key) {
  static const V2Style kTable[] = {
      {"codex", 0x10A37F, 0x74E3C9, 0x102E29, 0x17443B, 0x50D4B5, "OPENAI"},
      {"zcode", 0x14B8A6, 0x75E5D9, 0x10302E, 0x164541, 0x61DDD0, "Z.AI"},
      {"claude", 0xD97757, 0xF2AE91, 0x2E1D14, 0x4A3220, 0xF2AE91, "ANTHROPIC"},
      {"gemini", 0x4285F4, 0x8AB4F8, 0x14202E, 0x1D3050, 0x8AB4F8, "GOOGLE"},
      {"antigravity", 0x4E8CFF, 0x8AB4F8, 0x14202E, 0x1D3050, 0x8AB4F8, "GOOGLE"},
      {"copilot", 0xA371F7, 0xC9ACFB, 0x201A2E, 0x32264A, 0xC9ACFB, "GITHUB"},
      {"cursor", 0x9AD1D4, 0xC4E8EA, 0x1A2628, 0x27393B, 0xC4E8EA, "CURSOR"},
      {"opencode", 0xB9B9C7, 0xDADAE5, 0x202028, 0x34343F, 0xDADAE5, "OPENCODE"},
  };
  for (const auto& s : kTable) {
    if (key && strcmp(s.key, key) == 0) return &s;
  }
  return nullptr;
}

static uint32_t style_base(const V2Style* s) { return s ? s->base : 0xFF6B38; }
static uint32_t style_light(const V2Style* s) { return s ? s->light : 0xFFB380; }
static uint32_t style_badge_fill(const V2Style* s) { return s ? s->badgeFill : 0x1A2429; }
static uint32_t style_badge_stroke(const V2Style* s) { return s ? s->badgeStroke : 0x2A373D; }
static uint32_t style_badge_letter(const V2Style* s) { return s ? s->badgeLetter : 0xC5CED2; }
static const char* style_vendor(const V2Style* s, const char* fallback) {
  return s ? s->vendor : fallback;
}

// ───────────────────────────────────────────────────────────────────────────────
// WIDGETS
// ───────────────────────────────────────────────────────────────────────────────
struct RowWidgets {
  lv_obj_t* divider = nullptr;
  lv_obj_t* winMeta = nullptr;   // "5H WINDOW"
  lv_obj_t* name = nullptr;      // "Session"
  lv_obj_t* pct = nullptr;       // "33%"
  lv_obj_t* unit = nullptr;      // "LEFT"
  lv_obj_t* bar = nullptr;
  lv_obj_t* knob = nullptr;      // light dot at the bar end
  lv_obj_t* reset = nullptr;     // "Resets 23:30"
};

struct CardWidgets {
  uint8_t viewIndex = 0;
  char providerKey[16] = {};
  bool compact = false;
  uint8_t layoutRows = 0;
  bool layoutNotice = false;
  lv_obj_t* card = nullptr;
  lv_obj_t* spine = nullptr;
  lv_obj_t* badge = nullptr;
  lv_obj_t* badgeLetter = nullptr;
  lv_obj_t* badgeLogo = nullptr;
  lv_obj_t* name = nullptr;
  lv_obj_t* vendor = nullptr;    // "OPENAI · CONNECTED"
  lv_obj_t* remaining = nullptr; // "REMAINING" / "USED"
  RowWidgets rows[aim::kMaxRows];
};

struct HeaderWidgets {
  lv_obj_t* eyebrow = nullptr;
  lv_obj_t* title = nullptr;
  lv_obj_t* dot = nullptr;
  lv_obj_t* halo = nullptr;
  lv_obj_t* live = nullptr;
  lv_obj_t* clock = nullptr;
};

static HeaderWidgets hdr;
static CardWidgets big[kBigCards];
static lv_obj_t* footDot = nullptr;
static lv_obj_t* footStrong = nullptr;
static lv_obj_t* footFrames = nullptr;
static lv_obj_t* footSync = nullptr;
static lv_obj_t* footServices = nullptr;
static lv_obj_t* hintLabel = nullptr;
static lv_obj_t* dashboardScreen = nullptr;

static void settings_open_cb(lv_event_t* e) {
  (void)e;
  ui_menu_show();
}

bool dashboard_is_active() { return dashboardScreen && lv_screen_active() == dashboardScreen; }

// ───────────────────────────────────────────────────────────────────────────────
// CHANGE-DETECTION CACHES
// ───────────────────────────────────────────────────────────────────────────────
struct RowCaches {
  uint32_t percentColor = 0;
  char winMeta[36];
  char name[48];
  char pct[8];
  char unit[12];
  char reset[48];
  float bar;
  bool knobColorKnown;
  uint32_t knobColor;
};

struct CardCaches {
  const V2Style* style = nullptr;
  bool styleKnown = false;
  char badgeLetter[2];
  uint32_t spine;
  bool spineKnown;
  char name[16];
  char vendor[32];
  char remaining[12];
  RowCaches rows[aim::kMaxRows];
};

static CardCaches bigCache[kBigCards];
static char liveCache[12] = {0};
static char clockCache[8] = {0};
static uint32_t liveDotColor = 0;
static char footStrongCache[20] = {0};
static char footFramesCache[24] = {0};
static char footSyncCache[24] = {0};
static char footServicesCache[24] = {0};
static char hintCache[96] = {0};
static uint32_t footDotColor = 0;
static lv_obj_t* pageButton = nullptr;
static lv_obj_t* pageLabel = nullptr;
static uint8_t currentPage = 0, pageCount = 1;
static uint32_t lastPageMs = 0, viewRevision = UINT32_MAX;
// bar value/color cache slots: stable index per (layout, card, row)
static float g_barValue[kBigCards][aim::kMaxRows];
static uint32_t g_barColor[kBigCards][aim::kMaxRows];

static void set_label_cached(lv_obj_t* lbl, char* cache, size_t cap, const char* text) {
  if (!lbl || (strncmp(cache, text, cap) == 0 && strcmp(lv_label_get_text(lbl), cache) == 0)) return;
  const size_t length = std::min(strlen(text), cap - 1);
  memcpy(cache, text, length);
  cache[length] = '\0';
  lv_label_set_text(lbl, cache);
}

static void set_bar_cached(lv_obj_t* bar, size_t slot, size_t row, float pct, uint32_t base) {
  if (!bar) return;
  if (g_barColor[slot][row] != base) {
    lv_obj_set_style_bg_color(bar, lv_color_hex(base), LV_PART_INDICATOR);
    g_barColor[slot][row] = base;
  }
  if (pct < 0.0f) pct = 0.0f;
  if (pct > 100.0f) pct = 100.0f;
  if (g_barValue[slot][row] != pct) {
    lv_bar_set_value(bar, pct, LV_ANIM_OFF);
    g_barValue[slot][row] = pct;
  }
}

static void set_knob(lv_obj_t* knob, RowCaches& rc, float pct, uint32_t light) {
  if (!knob) return;
  if (!rc.knobColorKnown || rc.knobColor != light) {
    lv_obj_set_style_bg_color(knob, lv_color_hex(light), 0);
    rc.knobColor = light;
    rc.knobColorKnown = true;
  }
  if (pct < 0.0f) pct = 0.0f;
  if (pct > 100.0f) pct = 100.0f;
  int32_t x = (int32_t)(327.0f * pct / 100.0f) - 4;
  if (x < 0) x = 0;
  if (x > 319) x = 319;
  lv_obj_set_pos(knob, x, 1);  // parented to the 10 px bar
}

// ───────────────────────────────────────────────────────────────────────────────
// SMALL BUILDERS
// ───────────────────────────────────────────────────────────────────────────────
static lv_obj_t* make_label(lv_obj_t* parent, lv_coord_t x, lv_coord_t y, lv_coord_t w, const lv_font_t* font,
                            uint32_t color, lv_text_align_t align, const char* text) {
  lv_obj_t* lbl = lv_label_create(parent);
  lv_label_set_text(lbl, text);
  lv_obj_set_pos(lbl, x, y);
  lv_obj_set_width(lbl, w);
  lv_label_set_long_mode(lbl, LV_LABEL_LONG_MODE_CLIP);
  lv_obj_set_style_text_font(lbl, font, 0);
  lv_obj_set_style_text_color(lbl, lv_color_hex(color), 0);
  lv_obj_set_style_text_align(lbl, align, 0);
  return lbl;
}

static lv_obj_t* make_line(lv_obj_t* parent, lv_coord_t x, lv_coord_t y, lv_coord_t w, uint32_t color) {
  lv_obj_t* ln = lv_obj_create(parent);
  lv_obj_set_size(ln, w, 1);
  lv_obj_set_pos(ln, x, y);
  lv_obj_set_style_bg_color(ln, lv_color_hex(color), 0);
  lv_obj_set_style_bg_opa(ln, LV_OPA_COVER, 0);
  lv_obj_set_style_border_width(ln, 0, 0);
  lv_obj_set_style_radius(ln, 0, 0);
  lv_obj_set_style_pad_all(ln, 0, 0);
  lv_obj_set_scrollable(ln, false);
  lv_obj_set_clickable(ln, false);
  return ln;
}

static lv_obj_t* make_dot(lv_obj_t* parent, lv_coord_t x, lv_coord_t y, lv_coord_t d, uint32_t color) {
  lv_obj_t* dot = lv_obj_create(parent);
  lv_obj_set_size(dot, d, d);
  lv_obj_set_pos(dot, x, y);
  lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_color(dot, lv_color_hex(color), 0);
  lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
  lv_obj_set_style_border_width(dot, 0, 0);
  lv_obj_set_style_pad_all(dot, 0, 0);
  lv_obj_set_scrollable(dot, false);
  lv_obj_set_clickable(dot, false);
  return dot;
}

static void window_label(uint32_t windowMinutes, char* out, size_t cap) {
  if (windowMinutes == 300) snprintf(out, cap, "5H WINDOW");
  else if (windowMinutes == 10080) snprintf(out, cap, "7 DAY WINDOW");
  else if (windowMinutes == 43200) snprintf(out, cap, "MONTHLY WINDOW");
  else if (windowMinutes == 0) snprintf(out, cap, "WINDOW");
  else if (windowMinutes % 1440 == 0) snprintf(out, cap, "%lu DAY%s", (unsigned long)(windowMinutes / 1440), windowMinutes == 1440 ? "" : "S");
  else snprintf(out, cap, "%lu MIN", (unsigned long)windowMinutes);
}

// ───────────────────────────────────────────────────────────────────────────────
// CARD BUILD (v2 geometry from the SVG)
// ───────────────────────────────────────────────────────────────────────────────
static void build_row(CardWidgets& c, size_t r, lv_coord_t yTop, bool withDivider) {
  RowWidgets& w = c.rows[r];
  if (withDivider) w.divider = make_line(c.card, 18, yTop - 17, 338, C_LINE_SOFT);
  w.winMeta = make_label(c.card, 18, yTop, 220, &lv_font_montserrat_18, C_META, LV_TEXT_ALIGN_LEFT, "");
  lv_obj_set_style_text_letter_space(w.winMeta, 1, 0);
  w.name = make_label(c.card, 18, yTop + 20, 240, F_ROWLABEL, C_ROWLABEL, LV_TEXT_ALIGN_LEFT, "");
  w.pct = make_label(c.card, 236, yTop + 5, 110, F_PCT, C_PCT, LV_TEXT_ALIGN_RIGHT, "--");
  w.unit = make_label(c.card, 236, yTop + 41, 110, F_META, C_UNIT, LV_TEXT_ALIGN_RIGHT, "");
  lv_obj_set_style_text_letter_space(w.unit, 1, 0);
  w.bar = lv_bar_create(c.card);
  lv_obj_set_size(w.bar, 327, 10);
  lv_obj_set_pos(w.bar, 18, yTop + 62);
  lv_bar_set_range(w.bar, 0, 100);
  lv_obj_set_style_bg_color(w.bar, lv_color_hex(C_BAR_TRACK), LV_PART_MAIN);
  lv_obj_set_style_bg_opa(w.bar, LV_OPA_COVER, LV_PART_MAIN);
  lv_obj_set_style_border_width(w.bar, 0, LV_PART_MAIN);
  lv_obj_set_style_radius(w.bar, 5, LV_PART_MAIN);
  lv_obj_set_style_pad_all(w.bar, 0, LV_PART_MAIN);
  lv_obj_set_style_bg_color(w.bar, lv_color_hex(C_GREEN), LV_PART_INDICATOR);
  lv_obj_set_style_bg_opa(w.bar, LV_OPA_COVER, LV_PART_INDICATOR);
  lv_obj_set_style_radius(w.bar, 5, LV_PART_INDICATOR);
  w.knob = make_dot(w.bar, 314, 1, 8, C_GREEN);  // child of the bar; x set per value
  w.reset = make_label(c.card, 18, yTop + 82, 330, &lv_font_montserrat_18, C_RESET, LV_TEXT_ALIGN_LEFT, "");
}

static CardWidgets build_big_card(lv_obj_t* parent, lv_coord_t x, lv_coord_t y) {
  CardWidgets c;
  c.card = lv_obj_create(parent);
  lv_obj_set_size(c.card, 372, 318);
  lv_obj_set_pos(c.card, x, y);
  lv_obj_set_style_bg_color(c.card, lv_color_hex(C_CARD), 0);
  lv_obj_set_style_bg_opa(c.card, LV_OPA_COVER, 0);
  lv_obj_set_style_border_color(c.card, lv_color_hex(C_LINE), 0);
  lv_obj_set_style_border_width(c.card, 1, 0);
  lv_obj_set_style_radius(c.card, 18, 0);
  lv_obj_set_style_shadow_width(c.card, 0, 0);
  lv_obj_set_style_pad_all(c.card, 0, 0);
  lv_obj_set_scrollable(c.card, false);
  lv_obj_set_clickable(c.card, false);
  lv_obj_set_hidden(c.card, true);

  c.spine = make_dot(c.card, 0, 0, 4, C_GREEN);
  lv_obj_set_size(c.spine, 4, 318);
  lv_obj_set_style_radius(c.spine, 2, 0);

  // provider badge (18,18,42,42) rx11
  c.badge = lv_obj_create(c.card);
  lv_obj_set_size(c.badge, 42, 42);
  lv_obj_set_pos(c.badge, 18, 18);
  lv_obj_set_style_radius(c.badge, 11, 0);
  lv_obj_set_style_border_width(c.badge, 1, 0);
  lv_obj_set_style_pad_all(c.badge, 0, 0);
  lv_obj_set_scrollable(c.badge, false);
  lv_obj_set_clickable(c.badge, false);
  c.badgeLetter = make_label(c.badge, 0, 0, 42, F_BADGE, 0xFFFFFF, LV_TEXT_ALIGN_CENTER, "C");
  lv_obj_center(c.badgeLetter);
  c.badgeLogo = lv_image_create(c.badge); lv_obj_set_clickable(c.badgeLogo, false);

  c.name = make_label(c.card, 74, 20, 220, F_PROVIDER, C_NAME, LV_TEXT_ALIGN_LEFT, "-");
  c.vendor = make_label(c.card, 74, 49, 240, F_META, C_META, LV_TEXT_ALIGN_LEFT, "");
  lv_obj_set_style_text_letter_space(c.vendor, 1, 0);
  c.remaining = make_label(c.card, 240, 21, 106, F_META, C_META, LV_TEXT_ALIGN_RIGHT, "REMAINING");
  lv_obj_set_style_text_letter_space(c.remaining, 1, 0);
  make_line(c.card, 18, 77, 356, C_LINE);

  build_row(c, 0, 94, false);
  build_row(c, 1, 210, true);
  build_row(c, 2, 238, false);
  return c;
}

// ───────────────────────────────────────────────────────────────────────────────
// BUILD
// ───────────────────────────────────────────────────────────────────────────────
static void next_page_cb(lv_event_t*) {
  currentPage = (currentPage + 1u) % pageCount;
  lastPageMs = millis();
}

static void open_card_cb(lv_event_t* event) {
  const auto* card = static_cast<CardWidgets*>(lv_event_get_user_data(event));
  if (!card || !card->providerKey[0]) return;
  // A configuration frame may arrive between the last draw and release.
  // Follow the identity the user saw, never a newly rebound numeric slot.
  const auto snapshot = aim::read();
  for (size_t i = 0; i < aim::kMaxViews; ++i) {
    if (snapshot.viewsConfigured && i >= snapshot.viewCount) break;
    const auto* key = snapshot.viewsConfigured ? snapshot.viewKeys[i] : snapshot.views[i].providerKey;
    if (strcmp(key, card->providerKey) == 0) { ui_details_show(static_cast<uint8_t>(i)); return; }
  }
}
void dashboard_init() {
  lv_obj_t* scr = lv_screen_active();
  ui_theme::watch(scr);
  dashboardScreen = scr;
  lv_obj_set_style_bg_color(scr, lv_color_hex(C_BG), 0);
  lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
  lv_obj_set_style_border_width(scr, 0, 0);
  lv_obj_set_style_pad_all(scr, 0, 0);

  // ── header (78 px) ──
  lv_obj_t* header = lv_obj_create(scr);
  lv_obj_set_size(header, 800, 78);
  lv_obj_set_pos(header, 0, 0);
  lv_obj_set_style_bg_color(header, lv_color_hex(C_HEADER), 0);
  lv_obj_set_style_bg_opa(header, LV_OPA_COVER, 0);
  lv_obj_set_style_border_width(header, 0, 0);
  lv_obj_set_style_radius(header, 0, 0);
  lv_obj_set_style_pad_all(header, 0, 0);
  lv_obj_set_scrollable(header, false);
  make_line(header, 0, 77, 800, C_LINE);

#if defined(AIM_BOARD_WAVESHARE_S3)
  const char* boardCaption = "AI MONITOR / S3";
#else
  const char* boardCaption = "AI MONITOR / P4";
#endif
  hdr.eyebrow = make_label(header, 24, 13, 300, F_EYEBROW, C_EYEBROW, LV_TEXT_ALIGN_LEFT, boardCaption);
  lv_obj_set_style_text_letter_space(hdr.eyebrow, 2, 0);
  hdr.title = make_label(header, 24, 31, 306, F_PROVIDER, C_TITLE, LV_TEXT_ALIGN_LEFT, "Usage Dashboard");
  // live dot + halo + label (SVG: dot center (475,30) r4, halo r8)
  hdr.halo = make_dot(header, 467, 22, 16, C_GREEN);
  lv_obj_set_style_bg_opa(hdr.halo, LV_OPA_20, 0);
  hdr.dot = make_dot(header, 471, 26, 8, C_GREEN);
  hdr.live = make_label(header, 488, 22, 76, F_META, C_META_BRIGHT, LV_TEXT_ALIGN_LEFT, "LIVE");
  lv_obj_set_style_text_letter_space(hdr.live, 1, 0);

  hdr.clock = make_label(header, 574, 26, 78, F_TIME, C_TITLE, LV_TEXT_ALIGN_RIGHT, "--:--");

  // SET button with gear icon (684,18,92,42)
  lv_obj_t* setBtn = lv_btn_create(header);
  lv_obj_set_size(setBtn, 120, 48);
  lv_obj_set_pos(setBtn, 656, 14);
  lv_obj_set_style_bg_color(setBtn, lv_color_hex(C_SET_BG), 0);
  lv_obj_set_style_bg_opa(setBtn, LV_OPA_COVER, 0);
  lv_obj_set_style_border_color(setBtn, lv_color_hex(C_SET_BORDER), 0);
  lv_obj_set_style_border_width(setBtn, 1, 0);
  lv_obj_set_style_radius(setBtn, 11, 0);
  lv_obj_set_style_shadow_width(setBtn, 0, 0);
  lv_obj_set_style_pad_all(setBtn, 0, 0);
  lv_obj_set_style_bg_color(setBtn, lv_color_hex(ui_theme::pressed), LV_STATE_PRESSED);
  lv_obj_add_event_cb(setBtn, settings_open_cb, LV_EVENT_CLICKED, nullptr);
  ui_interaction::keep_target(setBtn);

  auto* setLbl = make_label(setBtn, 0, 0, 96, &lv_font_montserrat_22, C_SET_TXT, LV_TEXT_ALIGN_CENTER, "MENU");
  lv_obj_center(setLbl);

  // ── cards ──
  for (size_t i = 0; i < kBigCards; ++i) big[i] = build_big_card(scr, (lv_coord_t)(20 + i * 388), 96);
  for (auto& card : big) {
    lv_obj_set_clickable(card.card, true);
    lv_obj_add_event_cb(card.card, open_card_cb, LV_EVENT_CLICKED, &card);
    ui_interaction::keep_target(card.card);
    for (auto& row : card.rows) lv_obj_set_clickable(row.bar, false);
  }
  hintLabel = make_label(scr, 0, 230, 800, F_ROWLABEL, C_META, LV_TEXT_ALIGN_CENTER, "");

  // ── system bar footer (0,432,800,48) ──
  lv_obj_t* footer = lv_obj_create(scr);
  lv_obj_set_size(footer, 800, 48);
  lv_obj_set_pos(footer, 0, 432);
  lv_obj_set_style_bg_color(footer, lv_color_hex(C_FOOTER_BG), 0);
  lv_obj_set_style_bg_opa(footer, LV_OPA_COVER, 0);
  lv_obj_set_style_border_width(footer, 0, 0);
  lv_obj_set_style_radius(footer, 0, 0);
  lv_obj_set_style_pad_all(footer, 0, 0);
  lv_obj_set_scrollable(footer, false);
  make_line(footer, 0, 0, 800, C_LINE);
  footDot = make_dot(footer, 21, 20, 8, C_GREEN);
  footStrong = make_label(footer, 37, 16, 168, &lv_font_montserrat_14, C_FOOTER_STRONG, LV_TEXT_ALIGN_LEFT, "NO HOST");
  footFrames = nullptr;  // frame counts remain in the protocol, outside the daily-use footer
  footSync = make_label(footer, 196, 12, 220, &lv_font_montserrat_18, C_META, LV_TEXT_ALIGN_LEFT, "Updated -");
  footServices = make_label(footer, 552, 12, 224, &lv_font_montserrat_18, C_FOOTER, LV_TEXT_ALIGN_RIGHT, "0 / 0 services online");
  pageButton = lv_btn_create(footer);
  lv_obj_set_pos(pageButton, 448, 2);
  lv_obj_set_size(pageButton, 96, 44);
  lv_obj_set_style_bg_color(pageButton, lv_color_hex(C_SET_BG), 0);
  lv_obj_set_style_radius(pageButton, 8, 0);
  lv_obj_set_style_shadow_width(pageButton, 0, 0);
  lv_obj_set_style_border_width(pageButton, 1, 0);
  lv_obj_set_style_border_color(pageButton, lv_color_hex(C_SET_BORDER), 0);
  lv_obj_set_style_bg_color(pageButton, lv_color_hex(ui_theme::pressed), LV_STATE_PRESSED);
  lv_obj_set_style_bg_color(pageButton, lv_color_hex(ui_theme::button), LV_STATE_DISABLED);
  lv_obj_set_style_opa(pageButton, LV_OPA_50, LV_STATE_DISABLED);
  lv_obj_set_style_recolor_opa(pageButton, LV_OPA_TRANSP, LV_STATE_DISABLED);
  lv_obj_add_event_cb(pageButton, next_page_cb, LV_EVENT_CLICKED, nullptr);
  ui_interaction::keep_target(pageButton);
  pageLabel = make_label(pageButton, 0, 0, 70, F_META, C_TITLE, LV_TEXT_ALIGN_CENTER, "1 / 2 >");
  lv_obj_center(pageLabel);
  lv_obj_set_state(pageButton, LV_STATE_DISABLED, true);

  for (auto& cache : bigCache) cache = CardCaches{};
  memset(g_barValue, 0, sizeof(g_barValue));
  memset(g_barColor, 0, sizeof(g_barColor));
  liveCache[0] = clockCache[0] = '\0';
  footStrongCache[0] = footFramesCache[0] = footSyncCache[0] = footServicesCache[0] = hintCache[0] = '\0';
  liveDotColor = footDotColor = 0;
}

// ───────────────────────────────────────────────────────────────────────────────
// RENDER ONE CARD
// ───────────────────────────────────────────────────────────────────────────────
static void visible(lv_obj_t* object, bool show) {
  if (!object) return;
  lv_obj_set_hidden(object, !show);
}

static void layout_rows(CardWidgets& card, const aim::ViewData* view) {
  const uint8_t count = view && view->valid && view->rowCount ? view->rowCount : 1;
  const bool notice = view && view->notice && !view->hasUsage;
  if (card.layoutRows == count && card.layoutNotice == notice) return;
  card.layoutRows = count;
  card.layoutNotice = notice;
  for (size_t r = 0; r < aim::kMaxRows; ++r) {
    auto& row = card.rows[r];
    const bool show = r < count;
    for (auto* object : {row.winMeta, row.name, row.pct, row.unit, row.bar, row.knob, row.reset}) visible(object, show);
    visible(row.divider, show && count <= 2);
    if (!show) continue;
    const int top = card.compact ? (count == 3 ? 58 + static_cast<int>(r) * 30 : 64 + static_cast<int>(r) * 38) :
                    (count == 3 ? 94 + static_cast<int>(r) * 72 : 94 + static_cast<int>(r) * 116);
    if (card.compact) {
      lv_obj_set_pos(row.name, 16, top);
      lv_obj_set_pos(row.pct, 260, top - 1);
      lv_obj_set_pos(row.bar, 16, top + 20);
      lv_obj_set_pos(row.reset, 116, top);
    } else {
      lv_obj_set_pos(row.winMeta, 18, top);
      lv_obj_set_pos(row.name, 18, top + (count == 3 ? 17 : 20));
      lv_obj_set_pos(row.pct, 236, top + (count == 3 ? 2 : 0));
      lv_obj_set_style_text_font(row.pct, count == 3 ? &lv_font_montserrat_26 : &lv_font_montserrat_40, 0);
      lv_obj_set_pos(row.unit, 236, top + 45);
      visible(row.unit, count <= 2);
      lv_obj_set_pos(row.bar, 18, top + (count == 3 ? 42 : 62));
      lv_obj_set_height(row.bar, count == 3 ? 8 : 10);
      lv_obj_set_pos(row.reset, 18, top + (count == 3 ? 54 : 82));
      if (row.divider) lv_obj_set_y(row.divider, top - 17);
    }
    lv_obj_set_width(row.name, notice ? 330 : (card.compact ? 96 : 210));
    lv_obj_set_style_text_font(row.name, notice ? &lv_font_montserrat_14 : (card.compact ? F_META : F_ROWLABEL), 0);
    lv_label_set_long_mode(row.name, notice ? LV_LABEL_LONG_MODE_WRAP : LV_LABEL_LONG_MODE_CLIP);
    if (notice) {
      for (auto* object : {row.pct, row.unit, row.bar, row.knob, row.reset}) visible(object, false);
    }
  }
}

static void render_card(CardWidgets& c, CardCaches& cache, const aim::ViewData* view, const char* key, size_t slot,
                        uint32_t now, bool hostConnected, const SessionStatus& sessions) {
  layout_rows(c, view);
  const V2Style* vs = v2_style(view && view->valid ? view->providerKey : key);
  const char* keyStr = view && view->valid ? view->providerKey : key;
  const uint32_t base = style_base(vs);
  const uint32_t light = style_light(vs);
  const char* vendor = style_vendor(vs, view && view->valid ? view->providerLabel : keyStr);

  // spine + badge colors
  if (c.spine && (!cache.spineKnown || cache.spine != base)) {
    lv_obj_set_style_bg_color(c.spine, lv_color_hex(base), 0);
    cache.spine = base;
    cache.spineKnown = true;
  }
  if (!cache.styleKnown || cache.style != vs) {
    cache.style = vs;
    cache.styleKnown = true;
    if (c.badge) {
      lv_obj_set_style_bg_color(c.badge, lv_color_hex(style_badge_fill(vs)), 0);
      lv_obj_set_style_border_color(c.badge, lv_color_hex(style_badge_stroke(vs)), 0);
    }
    if (c.badgeLetter) lv_obj_set_style_text_color(c.badgeLetter, lv_color_hex(style_badge_letter(vs)), 0);
  }
  char letter[2] = "?";
  if (keyStr && keyStr[0]) {
    letter[0] = (char)((keyStr[0] >= 'a' && keyStr[0] <= 'z') ? keyStr[0] - 32 : keyStr[0]);
  }
  set_label_cached(c.badgeLetter, cache.badgeLetter, sizeof(cache.badgeLetter), letter);
  const auto* logo = nova_assets::logo_for(keyStr, c.compact ? 24 : 42);
  if (logo && lv_image_get_src(c.badgeLogo) != logo) lv_image_set_src(c.badgeLogo, logo);
  lv_obj_set_hidden(c.badgeLogo, !logo);
  lv_obj_set_hidden(c.badgeLetter, logo != nullptr);

  // name + vendor meta
  char nameBuf[16];
  if (view && view->valid) snprintf(nameBuf, sizeof(nameBuf), "%s", view->providerLabel);
  else {
    const aim::ProviderStyle* ps = aim::provider_style(key);
    snprintf(nameBuf, sizeof(nameBuf), "%s", ps ? ps->label : (key ? key : "-"));
  }
  set_label_cached(c.name, cache.name, sizeof(cache.name), nameBuf);

  const bool fresh = view && view->hasUsage && now - view->quotaReceivedMs < STALE_MS;
  const char* quotaStatus = "CONNECTED";
  if (fresh && hostConnected && view && !view->notice && !view->fetching) {
    bool critical = false, low = false;
    for (size_t r = 0; r < view->rowCount; ++r) {
      const auto& row = view->rows[r];
      if (!row.valid) continue;
      const float remaining = view->showsRemaining ? row.usedPercent : 100.0f - row.usedPercent;
      critical |= quota_critical(remaining, view->providerKey, row);
      low |= quota_low(remaining, view->providerKey, row);
    }
    quotaStatus = critical ? "CRITICAL" : (low ? "LOW QUOTA" : "CONNECTED");
  }
  char vendorBuf[32];
  snprintf(vendorBuf, sizeof(vendorBuf), "%s - %s", vendor,
           !view || !view->valid ? "WAITING" :
           (!hostConnected ? "OFFLINE" : (view->informational ? "ACTIVITY / SETUP" : (view->notice ? "ERROR - TAP" : (view->fetching ? "FETCHING" : (!fresh ? "STALE" : quotaStatus))))));
  if (hostConnected && sessions.known && (sessions.waiting || sessions.running || sessions.error || sessions.completed)) {
    snprintf(vendorBuf, sizeof(vendorBuf), "%s - %s", vendor,
             sessions.waiting ? "NEEDS YOU" : sessions.error ? "SESSION ERROR" : sessions.running ? "WORKING" : "TURN DONE");
  }
  set_label_cached(c.vendor, cache.vendor, sizeof(cache.vendor), vendorBuf);

  char remBuf[12];
  const bool hasQuota = view && view->hasUsage && view->rowCount > 0;
  snprintf(remBuf, sizeof(remBuf), "%s", view && view->informational ? "LOCAL" :
           hasQuota ? (view->showsRemaining ? "REMAINING" : "USED") : "");
  set_label_cached(c.remaining, cache.remaining, sizeof(cache.remaining), remBuf);

  for (size_t r = 0; r < aim::kMaxRows; ++r) {
    RowWidgets& w = c.rows[r];
    RowCaches& rc = cache.rows[r];
    if (!w.bar) continue;  // row not present in this layout

    char winBuf[36];
    char nameBuf2[48];
    char pctBuf[8];
    char unitBuf[12];
    char resetBuf[48];
    if (view && view->notice && !view->hasUsage && r == 0) {
      snprintf(winBuf, sizeof(winBuf), "NOTICE");
      snprintf(nameBuf2, sizeof(nameBuf2), "%.47s", view->message);
      snprintf(pctBuf, sizeof(pctBuf), "--");
      unitBuf[0] = '\0';
      resetBuf[0] = '\0';
      set_bar_cached(w.bar, slot, r, 0.0f, base);
      if (w.knob) set_knob(w.knob, rc, 0.0f, light);
    } else if (!view || !view->valid || r >= view->rowCount || !view->rows[r].valid) {
      snprintf(winBuf, sizeof(winBuf), "WINDOW");
      snprintf(nameBuf2, sizeof(nameBuf2), "waiting ...");
      snprintf(pctBuf, sizeof(pctBuf), "--");
      unitBuf[0] = '\0';
      resetBuf[0] = '\0';
      set_bar_cached(w.bar, slot, r, 0.0f, base);
      if (w.knob) set_knob(w.knob, rc, 0.0f, light);
    } else {
      const aim::Row& row = view->rows[r];
      window_label(row.windowMinutes, winBuf, sizeof(winBuf));
      snprintf(nameBuf2, sizeof(nameBuf2), "%s", row.title[0] ? row.title : "-");
      format_percent(row.usedPercent, view->showsRemaining, pctBuf, sizeof(pctBuf));
      if (!c.compact) {
        const bool widePercent = strlen(pctBuf) >= 5;
        const int width = widePercent ? 142 : 110, x = widePercent ? 204 : 236;
        if (lv_obj_get_width(w.pct) != width) lv_obj_set_width(w.pct, width);
        if (lv_obj_get_x(w.pct) != x) lv_obj_set_x(w.pct, x);
        const auto* font = c.layoutRows == 3 ? &lv_font_montserrat_26 : (strlen(pctBuf) >= 6 ? &lv_font_montserrat_30 : &lv_font_montserrat_40);
        if (lv_obj_get_style_text_font(w.pct, LV_PART_MAIN) != font) lv_obj_set_style_text_font(w.pct, font, 0);
        const int nameWidth = widePercent ? 174 : 210;
        if (lv_obj_get_width(w.name) != nameWidth) lv_obj_set_width(w.name, nameWidth);
      }
      snprintf(unitBuf, sizeof(unitBuf), "%s", view->showsRemaining ? "LEFT" : "USED");
      if (row.resetsShort[0]) snprintf(resetBuf, sizeof(resetBuf), c.compact ? "%s" : "Resets %s", row.resetsShort);
      else resetBuf[0] = '\0';
      if (row.hasResetCountdown) {
        char countdown[32];
        format_countdown(reset_remaining(row, view->quotaReceivedMs, now), countdown, sizeof(countdown));
        snprintf(resetBuf, sizeof(resetBuf), c.compact ? "%s" : "%.24s / %.19s", countdown, row.resetsShort);
      }
      const float remaining = view->showsRemaining ? row.usedPercent : 100.0f - row.usedPercent;
      const uint32_t quotaColor = !fresh || !hostConnected || view->notice || view->fetching ? C_META :
                                  (quota_critical(remaining, view->providerKey, row) ? C_RED : (quota_low(remaining, view->providerKey, row) ? C_AMBER : base));
      if (fresh && hostConnected && !view->notice && !view->fetching && quota_low(remaining, view->providerKey, row) && !c.compact) {
        char period[16];
        window_label(row.windowMinutes, period, sizeof(period));
        snprintf(winBuf, sizeof(winBuf), "%s / %s", period, quota_critical(remaining, view->providerKey, row) ? "CRITICAL" : "LOW");
      }
      if (view->notice && view->hasUsage) {
        const unsigned long ageMinutes = (now - view->quotaReceivedMs) / 60000u;
        snprintf(winBuf, sizeof(winBuf), "LAST GOOD / %lu m ago", ageMinutes);
        if (c.compact) snprintf(resetBuf, sizeof(resetBuf), "Old / %lu m", ageMinutes);
        else if (r == 0) snprintf(resetBuf, sizeof(resetBuf), "%.47s", view->message);
      }
      const uint32_t percentColor = quotaColor == base ? C_PCT : quotaColor;
      if (rc.percentColor != percentColor) {
        rc.percentColor = percentColor;
        lv_obj_set_style_text_color(w.pct, lv_color_hex(percentColor), 0);
      }
      set_bar_cached(w.bar, slot, r, row.usedPercent, quotaColor);
      if (w.knob) set_knob(w.knob, rc, row.usedPercent, quotaColor == base ? light : quotaColor);
    }
    set_label_cached(w.winMeta, rc.winMeta, sizeof(rc.winMeta), winBuf);
    set_label_cached(w.name, rc.name, sizeof(rc.name), nameBuf2);
    set_label_cached(w.pct, rc.pct, sizeof(rc.pct), pctBuf);
    if (w.unit) set_label_cached(w.unit, rc.unit, sizeof(rc.unit), unitBuf);
    set_label_cached(w.reset, rc.reset, sizeof(rc.reset), resetBuf);
  }
}

void dashboard_update() {
  if (!dashboard_is_active()) return;  // settings screen visible
  // Do not move, hide or rebind an active touch target. Release activation
  // resolves the saved provider identity against the newest snapshot.
  for (const auto& card : big) if (lv_obj_has_state(card.card, LV_STATE_PRESSED)) return;
  if (lv_obj_has_state(pageButton, LV_STATE_PRESSED)) return;
  const aim::Snapshot snap = aim::read();
  const uint32_t now = millis();
  const bool recent = snap.frameCount != 0 && (now - snap.lastFrameMs < STALE_MS);
  size_t onlineCount = 0, activeCount = 0, fetchingCount = 0;
  for (size_t i = 0; i < aim::kMaxViews; ++i) {
    if (snap.viewsConfigured && i >= snap.viewCount) continue;
    const auto& view = snap.views[i];
    if (!view.valid && !(snap.viewsConfigured && snap.viewKeys[i][0])) continue;
    ++activeCount;
    if (view.valid && view.fetching && !view.notice) ++fetchingCount;
    const auto* provider = aim::provider_style(view.providerKey);
    // Quota and local activity are independent capabilities. A fresh signal
    // from some other selected AI must not mark a missing bridge healthy.
    const bool local = view.valid && view.informational && provider &&
        ((token_signal_fresh(snap, now) && (snap.tokenSourceMask & provider->activityMask)) ||
         session_status(snap, now, provider->activityMask).known);
    if (snap.hostPresent && (local || (view.valid && !view.notice && !view.fetching && view.rowCount &&
        now - view.quotaReceivedMs < STALE_MS))) ++onlineCount;
  }

  // ── header: dot + LIVE/STALE/NO HOST + clock ──
  char liveBuf[12];
  uint32_t dotColor = C_GREEN;
  if (!snap.hostPresent) {
    snprintf(liveBuf, sizeof(liveBuf), "NO HOST");
    dotColor = C_AMBER;
  } else if (snap.frameCount == 0) {
    snprintf(liveBuf, sizeof(liveBuf), "WAITING");
    dotColor = C_AMBER;
  } else if (recent) {
    const bool fetching = activeCount > 0 && fetchingCount == activeCount;
    const bool issue = activeCount > 0 && onlineCount == 0 && !fetching;
    const bool partial = onlineCount < activeCount;
    snprintf(liveBuf, sizeof(liveBuf), "%s", fetching ? "FETCHING" : (issue ? "ISSUE" : (partial ? "PARTIAL" : "LIVE")));
    dotColor = issue ? C_RED : (partial ? C_AMBER : C_GREEN);
  } else {
    snprintf(liveBuf, sizeof(liveBuf), "STALE");
    dotColor = C_RED;
  }
  set_label_cached(hdr.live, liveCache, sizeof(liveCache), liveBuf);
  if (liveDotColor != dotColor) {
    liveDotColor = dotColor;
    lv_obj_set_style_bg_color(hdr.dot, lv_color_hex(dotColor), 0);
    lv_obj_set_style_bg_color(hdr.halo, lv_color_hex(dotColor), 0);
  }
  char clockBuf[8] = "--:--";
  uint16_t clockMinutes = 0;
  // Same freshness policy as every other clock consumer: stop extrapolating
  // from a host sync older than 12 h instead of presenting a derived clock.
  if (local_minutes(snap, now, clockMinutes)) {
    snprintf(clockBuf, sizeof(clockBuf), "%02u:%02u", clockMinutes / 60u, clockMinutes % 60u);
  }
  set_label_cached(hdr.clock, clockCache, sizeof(clockCache), clockBuf);

  // ── collect entries ──
  struct Entry {
    uint8_t index;
    const aim::ViewData* view;
    const char* key;
  };
  Entry entries[aim::kMaxViews];
  size_t used = 0;
  for (size_t v = 0; v < aim::kMaxViews; ++v) {
    if (snap.viewsConfigured && v >= snap.viewCount) continue;
    const bool configured = snap.viewsConfigured && v < snap.viewCount && snap.viewKeys[v][0] != '\0';
    if (!snap.views[v].valid && !configured) continue;
    entries[used].view = &snap.views[v];
    entries[used].index = static_cast<uint8_t>(v);
    entries[used].key = snap.viewKeys[v];
    used++;
  }

  pageCount = static_cast<uint8_t>(std::max<size_t>(1, (used + kBigCards - 1) / kBigCards));
  if (viewRevision != snap.viewRevision) {
    viewRevision = snap.viewRevision;
    currentPage = (snap.activeView / kBigCards) % pageCount;
    lastPageMs = now;
  }
  currentPage %= pageCount;
  const uint32_t period = static_cast<uint32_t>(snap.viewIntervalSeconds) * 1000u;
  if (pageCount > 1 && snap.automaticViews && period && now - lastPageMs >= period) {
    currentPage = (currentPage + (now - lastPageMs) / period) % pageCount;
    lastPageMs = now;
  }
  lv_obj_set_state(pageButton, LV_STATE_DISABLED, pageCount < 2);
  lv_obj_set_hidden(pageButton, pageCount < 2);
  {
    char text[16];
    snprintf(text, sizeof(text), "%u / %u >", currentPage + 1u, pageCount);
    if (strcmp(lv_label_get_text(pageLabel), text) != 0) lv_label_set_text(pageLabel, text);
  }
  const size_t start = currentPage * kBigCards;
  const size_t onPage = std::min(kBigCards, used - std::min(start, used));

  for(size_t i=0;i<kBigCards;++i) {
    auto& card=big[i];
    lv_obj_set_hidden(card.card,i>=onPage);
    if(i>=onPage)continue;
    const auto& entry=entries[start+i];
    card.viewIndex=entry.index;
    snprintf(card.providerKey,sizeof(card.providerKey),"%s",entry.key[0]?entry.key:entry.view->providerKey);
    render_card(card,bigCache[i],entry.view,entry.key,i,now,snap.hostPresent,
        session_status(snap,now,entry.key));
  }

  char hintBuf[96];
  if (used > 0 || snap.viewsConfigured) hintBuf[0] = '\0';
  else if (!snap.hostPresent) snprintf(hintBuf, sizeof(hintBuf), "Waiting for the AI Monitor host on USB ...");
  else snprintf(hintBuf, sizeof(hintBuf), "Connected - waiting for the first usage frame ...");
  set_label_cached(hintLabel, hintCache, sizeof(hintCache), hintBuf);

  // ── system bar footer ──
  char strongBuf[20];
  uint32_t fdot = C_GREEN;
  if (!snap.hostPresent) {
    snprintf(strongBuf, sizeof(strongBuf), "NO HOST");
    fdot = C_AMBER;
  } else {
    snprintf(strongBuf, sizeof(strongBuf), "HOST CONNECTED");
  }
  set_label_cached(footStrong, footStrongCache, sizeof(footStrongCache), strongBuf);
  if (footDotColor != fdot) {
    footDotColor = fdot;
    lv_obj_set_style_bg_color(footDot, lv_color_hex(fdot), 0);
  }
  char framesBuf[24];
  snprintf(framesBuf, sizeof(framesBuf), "%lu frames", (unsigned long)snap.frameCount);
  set_label_cached(footFrames, footFramesCache, sizeof(footFramesCache), framesBuf);
  char syncBuf[24];
  const uint32_t age = snap.frameCount ? (now - snap.lastFrameMs) / 1000u : 0;
  const char* refreshHint = refresh_hint(snap, now);
  if (refreshHint[0]) snprintf(syncBuf, sizeof(syncBuf), "%s", refreshHint);
  else if (!snap.frameCount) snprintf(syncBuf, sizeof(syncBuf), "Updated -");
  else if (age < 60) snprintf(syncBuf, sizeof(syncBuf), "Updated %lu s ago", (unsigned long)age);
  else if (age < 3600) snprintf(syncBuf, sizeof(syncBuf), "Updated %lu m ago", (unsigned long)(age / 60));
  else snprintf(syncBuf, sizeof(syncBuf), "Updated %lu h ago", (unsigned long)(age / 3600));
  set_label_cached(footSync, footSyncCache, sizeof(footSyncCache), syncBuf);
  char servicesBuf[24];
  snprintf(servicesBuf, sizeof(servicesBuf), "%lu / %lu services online", (unsigned long)onlineCount, (unsigned long)used);
  set_label_cached(footServices, footServicesCache, sizeof(footServicesCache), servicesBuf);

}

void dashboard_show() {if(dashboardScreen){lv_screen_load(dashboardScreen);dashboard_update();}}
