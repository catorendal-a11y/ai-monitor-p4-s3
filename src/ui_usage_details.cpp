#include "ui_usage_details.h"
#include <Arduino.h>
#include <lvgl.h>
#include <cstdio>
#include <cstring>
#include "ai_monitor/ai_monitor.h"
#include "ui/theme.h"
#include "ui/usage_format.h"
#include "ui/usage_history.h"
#include "ui/quota_alert.h"
#include "ui/interaction.h"

namespace {
lv_obj_t *screen = nullptr, *dashboard = nullptr, *title = nullptr, *status = nullptr;
lv_obj_t *notice = nullptr, *updateButton = nullptr, *updateLabel = nullptr, *feedback = nullptr;
lv_obj_t* errorBanner = nullptr;
struct DetailRow { lv_obj_t *card, *name, *percent, *bar, *reset; } rows[aim::kMaxRows];
uint32_t detailBarColors[aim::kMaxRows] = {UINT32_MAX, UINT32_MAX, UINT32_MAX};
uint32_t detailStyleWrites = 0;
uint8_t selected = 0;
char expectedKey[16] = {};
lv_obj_t* detailReturnScreen = nullptr;
UsageHistory history;
bool historyMode = false;
lv_obj_t *historyPanel = nullptr, *historyToggleLabel = nullptr, *historyHint = nullptr;
lv_obj_t *historyPlot = nullptr, *historyLegends[aim::kMaxRows] = {}, *historyTimeLabels[3] = {};
lv_obj_t* historyRangeButtons[3] = {};
const uint8_t historyHours[] = {1, 6, 24};
const uint32_t historyColors[] = {0x35D07F, 0xFFAA00, 0xA371F7};
uint8_t historyRange = 0;
uint32_t graphNow = 0;
unsigned historyEdges = 0;
uint32_t drawnHistoryRevision = UINT32_MAX;
uint8_t drawnHistoryView = 255;
uint32_t historyThemeRevision = UINT32_MAX;

lv_obj_t* detail_label(lv_obj_t* parent, int x, int y, int width, const char* text, const lv_font_t* font, uint32_t color) {
  auto* label = lv_label_create(parent);
  lv_label_set_text(label, text);
  lv_obj_set_pos(label, x, y);
  lv_obj_set_width(label, width);
  lv_obj_set_style_text_font(label, font, 0);
  lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
  lv_label_set_long_mode(label, LV_LABEL_LONG_MODE_CLIP);
  return label;
}
void detail_text(lv_obj_t* label, const char* text) {
  if (strcmp(lv_label_get_text(label), text) != 0) lv_label_set_text(label, text);
}
void back(lv_event_t*) { lv_screen_load(detailReturnScreen ? detailReturnScreen : dashboard); }
void toggle_history(lv_event_t*) { historyMode = !historyMode; ui_details_update(); }
void select_history_range(lv_event_t* event) {
  historyRange = static_cast<uint8_t>(reinterpret_cast<uintptr_t>(lv_event_get_user_data(event)));
  drawnHistoryRevision = UINT32_MAX;
  ui_details_update();
}
void draw_history(lv_event_t* event) {
  historyEdges = 0;
  const auto& series = history.series(selected);
  if (strcmp(series.key, expectedKey) != 0) return;
  lv_area_t area; lv_obj_get_coords(historyPlot, &area);
  auto* layer = lv_event_get_layer(event);
  const uint32_t window = historyHours[historyRange] * 3600000u;
  for (size_t r = 0; r < aim::kMaxRows; ++r) {
    lv_draw_line_dsc_t line; lv_draw_line_dsc_init(&line);
    line.color = lv_color_hex(historyColors[r]); line.width = 3;
    line.round_start = line.round_end = 1;
    bool previousValid = false;
    lv_point_precise_t previousPoint{};
    for (size_t i = 0; i < series.count; ++i) {
      const auto& point = UsageHistory::sample(series, i);
      const uint32_t age = graphNow - point.time;
      if (!(point.valid & (1u << r)) || age > window) { previousValid = false; continue; }
      const lv_point_precise_t position = {
        static_cast<lv_value_precise_t>(area.x1 + (window - age) * 687.0 / window),
        static_cast<lv_value_precise_t>(area.y1 + 176.0f * (100.0f - point.remaining[r]) / 100.0f)};
      if (previousValid && !(point.breakBefore & (1u << r))) {
        line.p1 = previousPoint; line.p2 = position; lv_draw_line(layer, &line); ++historyEdges;
      } else {
        lv_draw_rect_dsc_t dot; lv_draw_rect_dsc_init(&dot);
        dot.bg_color = line.color; dot.radius = 2;
        lv_area_t dotArea = {static_cast<int32_t>(position.x) - 2, static_cast<int32_t>(position.y) - 2,
                             static_cast<int32_t>(position.x) + 2, static_cast<int32_t>(position.y) + 2};
        lv_draw_rect(layer, &dot, &dotArea);
      }
      previousPoint = position; previousValid = true;
    }
  }
}
void update(lv_event_t*) {
  const auto snapshot = aim::read();
  if (snapshot.hostPresent && snapshot.manualRefreshSupported && !refresh_busy(snapshot.refreshState)) aim::request_refresh();
}
void move(int direction) {
  const auto snapshot = aim::read();
  const size_t count = snapshot.viewsConfigured ? snapshot.viewCount : aim::kMaxViews;
  for (size_t step = 1; step <= count; ++step) {
    const size_t candidate = (selected + count + direction * static_cast<int>(step)) % count;
    if (snapshot.views[candidate].valid || (snapshot.viewsConfigured && snapshot.viewKeys[candidate][0])) {
      ui_details_show(static_cast<uint8_t>(candidate)); return;
    }
  }
}
void previous(lv_event_t*) { move(-1); }
void next(lv_event_t*) { move(1); }
void gesture(lv_event_t*) {
  auto* input = lv_indev_active();
  if (!input) return;
  const auto direction = lv_indev_get_gesture_dir(input);
  if (direction == LV_DIR_LEFT) move(1);
  else if (direction == LV_DIR_RIGHT) move(-1);
}
lv_obj_t* detail_button(lv_obj_t* parent, int x, int y, int width, const char* text, lv_event_cb_t callback, lv_obj_t** labelOut = nullptr, void* eventData = nullptr) {
  auto* button = lv_btn_create(parent);
  lv_obj_set_pos(button, x, y); lv_obj_set_size(button, width, 48);
  lv_obj_set_style_bg_color(button, lv_color_hex(ui_theme::button), 0);
  lv_obj_set_style_bg_color(button, lv_color_hex(ui_theme::pressed), LV_STATE_PRESSED);
  lv_obj_set_style_bg_color(button, lv_color_hex(ui_theme::button), LV_STATE_DISABLED);
  lv_obj_set_style_opa(button, LV_OPA_50, LV_STATE_DISABLED);
  lv_obj_set_style_recolor_opa(button, LV_OPA_TRANSP, LV_STATE_DISABLED);
  lv_obj_set_style_radius(button, 12, 0); lv_obj_set_style_shadow_width(button, 0, 0);
  lv_obj_set_style_pad_all(button, 0, 0);
  auto* label = detail_label(button, 0, 0, width - 12, text, &lv_font_montserrat_16, ui_theme::text);
  lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0); lv_obj_center(label);
  lv_obj_add_event_cb(button, callback, LV_EVENT_CLICKED, eventData);
  ui_interaction::keep_target(button);
  if (labelOut) *labelOut = label;
  return button;
}
}

void ui_details_init() {
  dashboard = lv_screen_active();
  screen = lv_obj_create(nullptr);
  ui_theme::watch(screen);
  lv_obj_set_style_bg_color(screen, lv_color_hex(ui_theme::background), 0);
  lv_obj_set_style_pad_all(screen, 0, 0); lv_obj_set_style_border_width(screen, 0, 0);
  lv_obj_set_scrollable(screen, false);
  lv_obj_add_event_cb(screen, gesture, LV_EVENT_GESTURE, nullptr);
  title = detail_label(screen, 24, 14, 430, "Provider details", &lv_font_montserrat_26, ui_theme::text);
  status = detail_label(screen, 24, 50, 576, "", &lv_font_montserrat_14, ui_theme::muted);
  detail_button(screen, 640, 16, 136, "<  BACK", back);
  detail_button(screen, 474, 16, 150, "HISTORY", toggle_history, &historyToggleLabel);
  for (size_t i = 0; i < aim::kMaxRows; ++i) {
    auto& row = rows[i];
    // Reserve an error-summary strip permanently; rows never jump on failure.
    row.card = lv_obj_create(screen); lv_obj_set_pos(row.card, 24, 118 + i * 96); lv_obj_set_size(row.card, 752, 90);
    lv_obj_set_style_bg_color(row.card, lv_color_hex(ui_theme::surface), 0);
    lv_obj_set_style_border_color(row.card, lv_color_hex(ui_theme::border), 0);
    lv_obj_set_style_border_width(row.card, 1, 0); lv_obj_set_style_radius(row.card, 14, 0);
    lv_obj_set_style_pad_all(row.card, 0, 0); lv_obj_set_scrollable(row.card, false);
    lv_obj_set_gesture_bubble(row.card, true);
    row.name = detail_label(row.card, 16, 9, 560, "", &lv_font_montserrat_20, ui_theme::text);
    row.percent = detail_label(row.card, 608, 1, 124, "", &lv_font_montserrat_32, ui_theme::text);
    lv_obj_set_style_text_align(row.percent, LV_TEXT_ALIGN_RIGHT, 0);
    row.bar = lv_bar_create(row.card); lv_obj_set_pos(row.bar, 16, 45); lv_obj_set_size(row.bar, 716, 8);
    lv_bar_set_range(row.bar, 0, 100); lv_obj_set_style_bg_color(row.bar, lv_color_hex(ui_theme::border), LV_PART_MAIN);
    lv_obj_set_style_pad_all(row.bar, 0, 0); lv_obj_set_style_radius(row.bar, 4, LV_PART_MAIN);
    row.reset = detail_label(row.card, 16, 66, 716, "", &lv_font_montserrat_16, ui_theme::muted);
  }
  notice = detail_label(screen, 40, 142, 720, "", &lv_font_montserrat_20, ui_theme::text);
  lv_label_set_long_mode(notice, LV_LABEL_LONG_MODE_WRAP);
  errorBanner = detail_label(screen, 24, 78, 752, "", &lv_font_montserrat_14, 0xFFAA00);
  lv_label_set_long_mode(errorBanner, LV_LABEL_LONG_MODE_DOTS);
  lv_obj_set_height(errorBanner, 34);
  lv_obj_set_hidden(errorBanner, true);
  historyPanel = lv_obj_create(screen);
  lv_obj_set_pos(historyPanel, 24, 94); lv_obj_set_size(historyPanel, 752, 310);
  lv_obj_set_style_bg_color(historyPanel, lv_color_hex(ui_theme::surface), 0);
  lv_obj_set_style_border_color(historyPanel, lv_color_hex(ui_theme::border), 0);
  lv_obj_set_style_border_width(historyPanel, 1, 0); lv_obj_set_style_radius(historyPanel, 14, 0);
  lv_obj_set_style_pad_all(historyPanel, 0, 0); lv_obj_set_scrollable(historyPanel, false);
  lv_obj_set_gesture_bubble(historyPanel, true);
  for (size_t i = 0; i < aim::kMaxRows; ++i) {
    historyLegends[i] = detail_label(historyPanel, 32 + i * 236, 12, 220, "", &lv_font_montserrat_14, historyColors[i]);
    auto* grid = lv_obj_create(historyPanel);
    lv_obj_set_pos(grid, 32, 48 + i * 88); lv_obj_set_size(grid, 688, 1);
    lv_obj_set_style_bg_color(grid, lv_color_hex(ui_theme::border), 0);
    lv_obj_set_style_border_width(grid, 0, 0); lv_obj_set_style_pad_all(grid, 0, 0);
    lv_obj_set_clickable(grid, false);
    historyTimeLabels[i] = detail_label(historyPanel, 32 + i * 306, 232, 76, "--:--", &lv_font_montserrat_12, ui_theme::muted);
    const char* names[] = {"1 H", "6 H", "24 H"};
    historyRangeButtons[i] = detail_button(historyPanel, 392 + i * 112, 256, 104, names[i], select_history_range, nullptr, reinterpret_cast<void*>(i));
    lv_obj_set_height(historyRangeButtons[i], 44);
  }
  historyPlot = lv_obj_create(historyPanel);
  lv_obj_set_pos(historyPlot, 32, 48); lv_obj_set_size(historyPlot, 688, 177);
  lv_obj_set_style_bg_opa(historyPlot, LV_OPA_TRANSP, 0); lv_obj_set_style_border_width(historyPlot, 0, 0);
  lv_obj_set_style_pad_all(historyPlot, 0, 0); lv_obj_set_clickable(historyPlot, false);
  lv_obj_set_scrollable(historyPlot, false);
  lv_obj_add_event_cb(historyPlot, draw_history, LV_EVENT_DRAW_MAIN, nullptr);
  detail_label(historyPanel, 4, 40, 28, "100", &lv_font_montserrat_12, ui_theme::muted);
  detail_label(historyPanel, 8, 128, 24, "50", &lv_font_montserrat_12, ui_theme::muted);
  detail_label(historyPanel, 16, 216, 16, "0", &lv_font_montserrat_12, ui_theme::muted);
  historyHint = detail_label(historyPanel, 32, 270, 350, "", &lv_font_montserrat_12, ui_theme::muted);
  lv_label_set_long_mode(historyHint, LV_LABEL_LONG_MODE_WRAP);
  lv_obj_set_hidden(historyPanel, true);
  detail_button(screen, 24, 426, 96, "< PREV", previous);
  detail_button(screen, 132, 426, 96, "NEXT >", next);
  feedback = detail_label(screen, 244, 441, 296, "", &lv_font_montserrat_14, ui_theme::muted);
  updateButton = detail_button(screen, 552, 426, 224, "UPDATE ALL", update, &updateLabel);
}

void ui_details_show(uint8_t viewIndex) {
  if (viewIndex >= aim::kMaxViews) return;
  if (lv_screen_active() != screen) detailReturnScreen = lv_screen_active();
  selected = viewIndex;
  const auto snapshot = aim::read();
  const char* key = snapshot.viewsConfigured ? snapshot.viewKeys[selected] : snapshot.views[selected].providerKey;
  snprintf(expectedKey, sizeof(expectedKey), "%s", key);
  lv_screen_load(screen);
  ui_details_update();
}

void ui_details_update() {
  const auto snapshot = aim::read();
  history.capture(snapshot, millis());
  if (!screen || lv_screen_active() != screen) return;
  if (historyThemeRevision != ui_theme::revision) {
    historyThemeRevision = ui_theme::revision;
    // Fixed series colors may equal a palette color. Restore their semantic
    // identity after generic recoloring so legends still match the plot.
    for (size_t r = 0; r < aim::kMaxRows; ++r)
      lv_obj_set_style_text_color(historyLegends[r], lv_color_hex(historyColors[r]), 0);
    drawnHistoryRevision = UINT32_MAX;
  }
  const auto& view = snapshot.views[selected]; const uint32_t now = millis();
  const char* key = snapshot.viewsConfigured ? snapshot.viewKeys[selected] : view.providerKey;
  const bool changed = (snapshot.viewsConfigured && selected >= snapshot.viewCount) || strcmp(key, expectedKey) != 0;
  const auto* style = aim::provider_style(expectedKey);
  char text[256]; snprintf(text, sizeof(text), "%s / Details", style ? style->label : "Provider"); detail_text(title, text);
  const bool fresh = view.hasUsage && now - view.quotaReceivedMs < 300000u;
  snprintf(text, sizeof(text), "%s / %s / Last good %lu m ago", view.hasUsage ? (view.showsRemaining ? "REMAINING" : "USED") : "NO DATA",
           !snapshot.hostPresent ? "OFFLINE" : (view.notice ? "ERROR" : (view.fetching ? "FETCHING" : (!fresh ? "STALE" : "CONNECTED"))),
           static_cast<unsigned long>((now - view.quotaReceivedMs) / 60000));
  if (!view.hasUsage) snprintf(text, sizeof(text), "%s / No successful measurement yet", snapshot.hostPresent ? "CONNECTED" : "OFFLINE");
  if (view.informational) snprintf(text, sizeof(text), "%s / ACTIVITY ONLY / Quota not available", snapshot.hostPresent ? "CONNECTED" : "OFFLINE");
  if (changed) snprintf(text, sizeof(text), "Provider selection changed / return or choose PREV / NEXT");
  detail_text(status, text);
  const bool retained = !changed && view.notice && view.hasUsage;
  lv_obj_set_hidden(errorBanner, !retained || historyMode);
  if (retained) detail_text(errorBanner, view.message);
  const bool showNotice = changed || !view.valid || !view.hasUsage || !view.rowCount;
  detail_text(historyToggleLabel, historyMode ? "DATA" : "HISTORY");
  lv_obj_set_hidden(historyPanel, !historyMode || changed);
  lv_obj_set_hidden(notice, !showNotice || (historyMode && !changed));
  if (showNotice) detail_text(notice, changed ? "This view changed. Return to the dashboard." :
                                    (view.notice ? view.message : "Waiting for provider data."));
  for (size_t i = 0; i < aim::kMaxRows; ++i) {
    auto& widgets = rows[i]; lv_obj_set_hidden(widgets.card, historyMode || showNotice || i >= view.rowCount);
    if (showNotice || i >= view.rowCount) continue;
    const auto& row = view.rows[i]; detail_text(widgets.name, row.title);
    format_percent(row.usedPercent, view.showsRemaining, text, sizeof(text)); detail_text(widgets.percent, text);
    const bool widePercent = strlen(text) >= 5;
    const int pctWidth = widePercent ? 172 : 124, pctX = widePercent ? 560 : 608;
    if (lv_obj_get_width(widgets.percent) != pctWidth) lv_obj_set_width(widgets.percent, pctWidth);
    if (lv_obj_get_x(widgets.percent) != pctX) lv_obj_set_x(widgets.percent, pctX);
    if (lv_obj_get_width(widgets.name) != 536) lv_obj_set_width(widgets.name, 536);
    const float remaining = view.showsRemaining ? row.usedPercent : 100.0f - row.usedPercent;
    const uint32_t color = !fresh || !snapshot.hostPresent || view.notice || view.fetching ? ui_theme::muted :
                          (quota_critical(remaining, view.providerKey, row) ? 0xFF5252 : (quota_low(remaining, view.providerKey, row) ? 0xFFAA00 : (style ? style->color : ui_theme::accent)));
    if (detailBarColors[i] != color) {
      detailBarColors[i] = color; ++detailStyleWrites;
      lv_obj_set_style_bg_color(widgets.bar, lv_color_hex(color), LV_PART_INDICATOR);
      lv_obj_set_style_text_color(widgets.percent, lv_color_hex(color), 0);
    }
    if (lv_bar_get_value(widgets.bar) != static_cast<int32_t>(row.usedPercent))
      lv_bar_set_value(widgets.bar, static_cast<int32_t>(row.usedPercent), LV_ANIM_OFF);
    char countdown[40] = {};
    if (row.hasResetCountdown) {
      format_countdown(reset_remaining(row, view.quotaReceivedMs, now), countdown, sizeof(countdown));
      snprintf(text, sizeof(text), "Reset in %s   /   %s", countdown, row.resetsShort);
      if (reset_remaining(row, view.quotaReceivedMs, now) == 0) snprintf(text, sizeof(text), "Reset due - update to confirm   /   %s", row.resetsShort);
    } else snprintf(text, sizeof(text), "Reset time: %s", row.resetsShort[0] ? row.resetsShort : "Not provided");
    detail_text(widgets.reset, text);
  }
  if (historyMode && !changed && (drawnHistoryRevision != history.revision() || drawnHistoryView != selected || now - graphNow >= 60000u)) {
    drawnHistoryRevision = history.revision(); drawnHistoryView = selected;
    const auto& series = history.series(selected);
    const size_t samples = strcmp(series.key, expectedKey) == 0 ? series.count : 0;
    graphNow = now;
    const uint32_t window = historyHours[historyRange] * 3600000u;
    size_t visibleSamples = 0;
    for (size_t p = 0; p < samples; ++p) if (now - UsageHistory::sample(series, p).time <= window) ++visibleSamples;
    for (size_t r = 0; r < aim::kMaxRows; ++r) {
      detail_text(historyLegends[r], samples ? series.titles[r] : "");
      uint16_t minute = 0;
      if (local_minutes(snapshot, now, minute)) {
        const uint16_t axisMinute = (minute + 1440u - (historyHours[historyRange] * 60u * (2u - r) / 2u) % 1440u) % 1440u;
        snprintf(text, sizeof(text), "%02u:%02u", axisMinute / 60u, axisMinute % 60u);
      } else snprintf(text, sizeof(text), "%s", r == 2 ? "Now" : "--:--");
      detail_text(historyTimeLabels[r], text);
      lv_obj_set_style_bg_color(historyRangeButtons[r], lv_color_hex(historyRange == r ? ui_theme::accent : ui_theme::button), 0);
      lv_obj_set_style_text_color(lv_obj_get_child(historyRangeButtons[r], 0), lv_color_hex(historyRange == r ? ui_theme::background : ui_theme::text), 0);
    }
    snprintf(text, sizeof(text), "Remaining %% / %u h / %u points\nGaps = no data / RAM history", historyHours[historyRange], static_cast<unsigned>(visibleSamples));
    detail_text(historyHint, text);
    lv_obj_invalidate(historyPlot);
  }
  const bool busy = refresh_busy(snapshot.refreshState);
  lv_obj_set_state(updateButton, LV_STATE_DISABLED, busy || !snapshot.hostPresent || !snapshot.manualRefreshSupported);
  detail_text(updateLabel, busy ? "UPDATING..." : "UPDATE ALL");
  const char* state = refresh_hint(snapshot, now);
  if (!state[0]) state = "Swipe to change provider";
  detail_text(feedback, state);
}
