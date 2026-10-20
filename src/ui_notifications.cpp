#include "ui_notifications.h"
#include <Arduino.h>
#include <lvgl.h>
#include <cstdio>
#include <cstring>
#include "live_agent/activity_types.h"
#include "ui/agent_alerts.h"
#include "ui/idle_dim.h"
#include "ui_agents.h"
#include "ui/quota_notifications.h"
#include "ui/usage_format.h"
#include "ui/theme.h"
#include "ui/interaction.h"
#include "app_settings.h"
#include "ui_settings.h"
#include "ui_event_center.h"
#include "ui_menu.h"
#include "ui_enrollment.h"
#include "ui_history.h"
#include "ui_permission.h"
#include "ui_connection.h"

namespace quota_banner {
static QuotaNotifications policy;
static QuotaNotifications::Alert displayed;
// Agents that started waiting for the user share the banner with quota alerts.
static AgentAlerts agentPolicy;
static AgentAlerts::Alert displayedAgent;
static bool displayedIsAgent = false;
static uint32_t bannerColor = 0;
static lv_obj_t *banner = nullptr, *heading = nullptr, *body = nullptr, *pending = nullptr, *dismissButton = nullptr;
static void text(lv_obj_t* label, const char* value) {
  if (strcmp(lv_label_get_text(label), value) != 0) lv_label_set_text(label, value);
}
static void dismiss(lv_event_t*) {
  // Dismiss exactly the alert whose text was visible when the tap began, quota or agent.
  if (displayedIsAgent) agentPolicy.acknowledge(displayedAgent);
  else policy.acknowledge(displayed);
  ui_notifications_update();
}
static lv_obj_t* label(lv_obj_t* parent, int x, int y, int width, const lv_font_t* font) {
  auto* object = lv_label_create(parent);
  lv_obj_set_pos(object, x, y); lv_obj_set_width(object, width);
  lv_obj_set_style_text_font(object, font, 0);
  lv_obj_set_style_text_color(object, lv_color_hex(ui_theme::text), 0);
  lv_label_set_long_mode(object, LV_LABEL_LONG_MODE_CLIP);
  return object;
}
static void paint(uint32_t color) {
  if (bannerColor == color) return;
  bannerColor = color;
  lv_obj_set_style_border_color(banner, lv_color_hex(color), 0);
  lv_obj_set_style_text_color(heading, lv_color_hex(color), 0);
}
}

void ui_notifications_init() {
  using namespace quota_banner;
  banner = lv_obj_create(lv_layer_top());
  lv_obj_set_pos(banner, 24, 82); lv_obj_set_size(banner, 752, 136);
  lv_obj_set_style_bg_color(banner, lv_color_hex(ui_theme::surface), 0);
  lv_obj_set_style_bg_opa(banner, LV_OPA_COVER, 0);
  lv_obj_set_style_border_width(banner, 2, 0); lv_obj_set_style_radius(banner, 14, 0);
  lv_obj_set_style_pad_all(banner, 0, 0); lv_obj_set_scrollable(banner, false);
  heading = label(banner, 20, 14, 530, &lv_font_montserrat_24);
  body = label(banner, 20, 53, 530, &lv_font_montserrat_20);
  lv_label_set_long_mode(body, LV_LABEL_LONG_MODE_WRAP);
  lv_obj_set_height(body, 48);
  pending = label(banner, 20, 108, 530, &lv_font_montserrat_16);
  lv_obj_set_style_text_color(pending, lv_color_hex(ui_theme::muted), 0);
  dismissButton = lv_btn_create(banner);
  lv_obj_set_pos(dismissButton, 578, 38); lv_obj_set_size(dismissButton, 152, 60);
  lv_obj_set_style_bg_color(dismissButton, lv_color_hex(ui_theme::button), 0);
  lv_obj_set_style_bg_color(dismissButton, lv_color_hex(ui_theme::pressed), LV_STATE_PRESSED);
  lv_obj_set_style_shadow_width(dismissButton, 0, 0);
  auto* caption = label(dismissButton, 0, 0, 132, &lv_font_montserrat_18);
  lv_label_set_text(caption, "DISMISS");
  lv_obj_set_style_text_align(caption, LV_TEXT_ALIGN_CENTER, 0); lv_obj_center(caption);
  lv_obj_add_event_cb(dismissButton, dismiss, LV_EVENT_CLICKED, nullptr);
  ui_interaction::keep_target(dismissButton);
  lv_obj_set_hidden(banner, true);
}

void ui_notifications_update() {
  using namespace quota_banner;
  const auto snapshot = aim::read();
  policy.update(snapshot, millis(), [](const char* provider, const aim::Row& row) {
    return app_settings::warning_for(provider, row.title, row.windowMinutes);
  });
  agentPolicy.update(live_agent::read_usb(), millis());
  // A request that just appeared wakes a dimmed screen, once; what is shown is decided below.
  if (agentPolicy.take_new()) idle_dim_alert();
  if (!banner) return;
  // Preserve both the identity and visibility of a held dismiss target,
  // including when its quota recovers while the finger is down.
  if (lv_obj_has_state(dismissButton, LV_STATE_PRESSED)) return;
  const auto* alert = policy.current();
  static QuotaNotifications::Alert recorded;
  if(!alert)recorded={};
  if(alert && (recorded.severity!=alert->severity || strcmp(recorded.provider,alert->provider) || strcmp(recorded.title,alert->title))) {
    ui_event_center_quota(alert->provider,alert->severity==2);recorded=*alert;
    // A critical alert must be readable on a dimmed screen; a low one waits for the next touch.
    if(alert->severity==2)idle_dim_alert();
  }
  const auto* attention = agentPolicy.current();
  // Order of urgency: a critical quota, then an agent waiting for the user, then a low quota.
  const bool showAgent = attention && !(alert && alert->severity == 2);
  const bool overlay = ui_settings_is_active() || ui_event_center_is_active() || ui_menu_is_active() || ui_enrollment_is_active() ||
                       ui_history_is_active() || ui_permission_is_active() || ui_connection_is_active();
  if ((!alert && !attention) || overlay || (showAgent && ui_agents_is_active())) { lv_obj_set_hidden(banner, true); return; }
  if (showAgent) {
    displayedIsAgent = true;
    displayedAgent = *attention;
    paint(0xFFCF66);
    const auto* agentStyle = aim::provider_style(attention->provider);
    char line[160], waited[24];
    snprintf(line, sizeof(line), "AGENT NEEDS YOU / %s", agentStyle ? agentStyle->label : attention->provider);
    text(heading, line);
    if (attention->hasLabel) snprintf(line, sizeof(line), "%s is waiting for you", attention->label);
    else {
      const size_t length = strlen(attention->id);
      snprintf(line, sizeof(line), "Session %s is waiting for you", attention->id + (length > 8 ? length - 8 : 0));
    }
    text(body, line);
    const unsigned long seconds = (millis() - attention->sinceMs) / 1000u;
    if (seconds >= 3600) snprintf(waited, sizeof(waited), "%lu:%02lu:%02lu", seconds / 3600, seconds / 60 % 60, seconds % 60);
    else snprintf(waited, sizeof(waited), "%lu:%02lu", seconds / 60, seconds % 60);
    snprintf(line, sizeof(line), "Waiting %s / %u request%s", waited, agentPolicy.count(), agentPolicy.count() == 1 ? "" : "s");
    text(pending, line);
    lv_obj_set_hidden(banner, false);
    return;
  }
  displayedIsAgent = false;
  const bool critical = alert->severity == 2;
  paint(critical ? 0xFF5252 : 0xFFAA00);
  displayed = *alert;
  const auto* provider = aim::provider_style(alert->provider);
  char value[160], percent[16];
  snprintf(value, sizeof(value), "%s / %s", critical ? "CRITICAL QUOTA" : "LOW QUOTA",
           provider ? provider->label : alert->provider);
  text(heading, value);
  format_percent(alert->remaining, true, percent, sizeof(percent));
  snprintf(value, sizeof(value), "%s: %s remaining", alert->title[0] ? alert->title : "Quota", percent);
  text(body, value);
  if (alert->hasReset) {
    // Whether to wait or switch tools depends on when the window comes back.
    char countdown[32];
    const uint32_t left = seconds_until(alert->resetSeconds, alert->receivedMs, millis());
    format_countdown(left, countdown, sizeof(countdown));
    if (left) snprintf(value, sizeof(value), "Resets in %s / %u pending alert%s", countdown, policy.count(), policy.count() == 1 ? "" : "s");
    else snprintf(value, sizeof(value), "%s / %u pending alert%s", countdown, policy.count(), policy.count() == 1 ? "" : "s");
  } else {
    snprintf(value, sizeof(value), "%u pending alert%s / all quota windows monitored", policy.count(), policy.count() == 1 ? "" : "s");
  }
  text(pending, value);
  lv_obj_set_hidden(banner, false);
}
