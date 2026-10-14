// Display settings: direct dim choices, brightness presets and touch feedback.
#include "ui_settings.h"
#include <Arduino.h>
#include <lvgl.h>
#include <cstdio>
#include <cstring>
#include "app_settings.h"
#include "config.h"
#include "ui/backlight.h"
#include "ui/idle_dim.h"
#include "ui/theme.h"
#include "ai_monitor/ai_monitor.h"
#include "ui/nova_assets.h"
#include "ui/quota_window.h"
#include "ui/usage_format.h"
#include "ui/interaction.h"
#include "ui_enrollment.h"
#include "ui_connection.h"

static lv_obj_t* settingsScreen = nullptr;
static lv_obj_t* dashScreen = nullptr;
static lv_obj_t* settingsReturnScreen = nullptr;
static lv_obj_t* brightnessValue = nullptr;
static lv_obj_t* brightnessSlider = nullptr;
static lv_obj_t *actualBrightnessLabel = nullptr, *saveFeedback = nullptr, *warningTargetLabel = nullptr;
struct AlertTarget { char provider[16] = {}, title[36] = {}; uint32_t window = 0; };
static AlertTarget alertTargets[25];
static uint8_t alertTargetCount = 1, alertTargetIndex = 0;
static uint32_t shownSaveRevision = 0, savedAtMs = 0;
static lv_obj_t *dimChoice=nullptr,*brightnessChoice=nullptr;
static lv_obj_t* previewButton = nullptr;
static lv_obj_t* connectPcButton = nullptr;
static lv_obj_t *alertsButton = nullptr, *alertsOverlay = nullptr, *warningSlider = nullptr, *warningValue = nullptr;
static lv_obj_t *warningPrev = nullptr, *warningNext = nullptr, *warningInherit = nullptr;
static lv_obj_t *nightButton = nullptr, *nightOverlay = nullptr, *nightToggleLabel = nullptr, *nightValue = nullptr;
static lv_obj_t *nightTimeValues[4] = {}, *nightTimeButtons[8] = {}, *nightSlider = nullptr;
static app_settings::NightSettings nightDraft;
static lv_obj_t *appearanceOverlay = nullptr, *companionPreview = nullptr;
static lv_obj_t *companionButtons[2] = {}, *companionCaptions[2] = {}, *themeButtons[4] = {}, *themeCaptions[4] = {};
static lv_obj_t *quotaButton = nullptr, *quotaOverlay = nullptr, *quotaProviderLabel = nullptr, *quotaSelectionLabel = nullptr;
static lv_obj_t *quotaProviderHelp = nullptr, *quotaSetupHelp = nullptr;
static lv_obj_t* quotaDetails[4] = {};
static uint32_t quotaUpdatedAt = 0;
static lv_obj_t *quotaButtons[4] = {}, *quotaCaptions[4] = {}, *quotaPrev = nullptr, *quotaNext = nullptr;
static char quotaProviders[8][16] = {};
static uint8_t quotaProviderCount = 0, quotaProviderIndex = 0, quotaChoiceCount = 0;
static app_settings::NovaWindow quotaChoices[3];
static const uint8_t kDimChoices[] = {0, 1, 5, 10};
static const uint8_t kBrightnessPresets[] = {25, 50, 75, 100};
static uint8_t lastDimChoice = 255, lastPresetValue = 255;
static uint8_t brightnessBeforeDrag = 0;
static bool brightnessDragging = false;

static void close_overlays() {
  for (auto* overlay : {alertsOverlay, nightOverlay, appearanceOverlay, quotaOverlay})
    if (overlay) lv_obj_set_hidden(overlay, true);
}

static void style_button(lv_obj_t* button, bool selected) {
  lv_obj_set_style_bg_color(button, lv_color_hex(selected ? ui_theme::accent : ui_theme::button), 0);
  lv_obj_set_style_bg_opa(button, LV_OPA_COVER, 0);
  lv_obj_set_style_border_color(button, lv_color_hex(selected ? ui_theme::accent : ui_theme::border), 0);
  lv_obj_set_style_border_width(button, selected ? 2 : 1, 0);
  lv_obj_set_style_radius(button, 12, 0);
  lv_obj_set_style_shadow_width(button, 0, 0);
  lv_obj_set_style_pad_all(button, 0, 0);
  lv_obj_set_style_bg_color(button, lv_color_hex(ui_theme::pressed), LV_STATE_PRESSED);
  lv_obj_set_style_bg_color(button, lv_color_hex(ui_theme::button), LV_STATE_DISABLED);
  lv_obj_set_style_opa(button, LV_OPA_50, LV_STATE_DISABLED);
  lv_obj_set_style_recolor_opa(button, LV_OPA_TRANSP, LV_STATE_DISABLED);
  lv_obj_set_style_border_color(button, lv_color_hex(ui_theme::accent), LV_STATE_PRESSED);
}

static lv_obj_t* make_label(lv_obj_t* parent, lv_coord_t x, lv_coord_t y, lv_coord_t width,
                            const char* text, const lv_font_t* font, uint32_t color, lv_text_align_t align) {
  auto* label = lv_label_create(parent);
  lv_label_set_text(label, text);
  lv_obj_set_pos(label, x, y);
  lv_obj_set_width(label, width);
  lv_label_set_long_mode(label, LV_LABEL_LONG_MODE_CLIP);
  lv_obj_set_style_text_font(label, font, 0);
  lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
  lv_obj_set_style_text_align(label, align, 0);
  return label;
}

// Help texts carry a second line after \n; CLIP would keep them one line tall.
static lv_obj_t* make_wrap_label(lv_obj_t* parent, lv_coord_t x, lv_coord_t y, lv_coord_t width,
                                 const char* text, const lv_font_t* font, uint32_t color, lv_text_align_t align) {
  auto* label = make_label(parent, x, y, width, text, font, color, align);
  lv_label_set_long_mode(label, LV_LABEL_LONG_MODE_WRAP);
  return label;
}

static void refresh_brightness();

static void refresh_choices() {
  const uint8_t minutes = app_settings::dim_minutes();
  if (minutes != lastDimChoice) {
    lastDimChoice = minutes;
    for (size_t i = 0; i < 4; ++i)if(minutes==kDimChoices[i])lv_dropdown_set_selected(dimChoice,i);
  }
  const uint8_t percent = brightness_percent(display_get_brightness());
  if (percent != lastPresetValue) {
    lastPresetValue = percent;
    unsigned selected=0;
    for(size_t i=0;i<4;++i)if(percent==kBrightnessPresets[i])selected=i+1;
    lv_dropdown_set_selected(brightnessChoice,selected);
  }
}

static void brightness_slider_cb(lv_event_t* event) {
  if (lv_event_get_code(event) == LV_EVENT_PRESSED) {
    brightnessBeforeDrag = display_get_brightness(); brightnessDragging = true; return;
  }
  if (lv_event_get_code(event) == LV_EVENT_PRESS_LOST) {
    if (brightnessDragging) display_apply_brightness(brightnessBeforeDrag, false);
    brightnessDragging = false;
    lv_slider_set_value(brightnessSlider, brightness_percent(display_get_brightness()), LV_ANIM_OFF);
    refresh_brightness(); return;
  }
  const uint8_t percent = static_cast<uint8_t>(lv_slider_get_value(brightnessSlider));
  display_apply_brightness(brightness_raw(percent), lv_event_get_code(event) == LV_EVENT_RELEASED);
  if (lv_event_get_code(event) == LV_EVENT_RELEASED) brightnessDragging = false;
  refresh_brightness();
}

static void brightness_preset_cb(lv_event_t*) {
  const auto index = lv_dropdown_get_selected(brightnessChoice);
  if (index == 0 || index > 4) return;
  display_apply_brightness(brightness_raw(kBrightnessPresets[index-1]), true);
  refresh_brightness();
}

static void dim_select_cb(lv_event_t*) {
  const auto index = lv_dropdown_get_selected(dimChoice);
  if (index >= 4) return;
  app_settings::set_dim_minutes(kDimChoices[index]);
  refresh_choices();
}

static void back_cb(lv_event_t*) { ui_settings_hide(); }
static void dim_preview_cb(lv_event_t*) { idle_dim_preview(); }

static lv_obj_t* make_button(lv_obj_t* parent, int x, int y, int width, const char* text,
                            lv_event_cb_t callback, void* data, lv_obj_t** labelOut = nullptr) {
  auto* button = lv_btn_create(parent);
  lv_obj_set_pos(button, x, y);
  lv_obj_set_size(button, width, 48);
  style_button(button, false);
  lv_obj_add_event_cb(button, callback, LV_EVENT_CLICKED, data);
  ui_interaction::keep_target(button);
  auto* label = make_label(button, 0, 0, width - 8, text, &lv_font_montserrat_20, ui_theme::text, LV_TEXT_ALIGN_CENTER);
  lv_obj_center(label);
  if (labelOut) *labelOut = label;
  return button;
}

static lv_obj_t* make_choice(lv_obj_t* parent,int x,int y,const char* options,lv_event_cb_t callback) {
  auto* choice=lv_dropdown_create(parent);lv_obj_set_pos(choice,x,y);lv_obj_set_size(choice,340,56);
  lv_dropdown_set_options(choice,options);
  lv_obj_set_style_text_font(choice,&lv_font_montserrat_26,0);
  lv_obj_set_style_text_color(choice,lv_color_hex(ui_theme::text),0);
  lv_obj_set_style_bg_color(choice,lv_color_hex(ui_theme::button),0);
  auto* list=lv_dropdown_get_list(choice);
  lv_obj_set_style_text_font(list,&lv_font_montserrat_26,0);
  lv_obj_set_style_text_line_space(list,20,0);
  lv_obj_set_style_text_color(list,lv_color_hex(ui_theme::text),0);
  lv_obj_set_style_bg_color(list,lv_color_hex(ui_theme::surface),0);
  lv_obj_set_style_bg_color(list,lv_color_hex(ui_theme::pressed),LV_PART_SELECTED);
  lv_obj_set_style_max_height(list,270,0);
  lv_obj_add_event_cb(choice,callback,LV_EVENT_VALUE_CHANGED,nullptr);ui_interaction::keep_target(choice);
  return choice;
}

static void refresh_appearance() {
  const auto look = app_settings::appearance();
  for (size_t i = 0; i < 2; ++i) {
    const bool selected = static_cast<uint8_t>(look.companion) == i;
    style_button(companionButtons[i], selected);
    lv_obj_set_style_text_color(companionCaptions[i], lv_color_hex(selected ? ui_theme::background : ui_theme::text), 0);
  }
  for (size_t i = 0; i < 4; ++i) {
    style_button(themeButtons[i], static_cast<uint8_t>(look.theme) == i);
    lv_obj_set_style_bg_color(themeButtons[i], lv_color_hex(ui_theme::palettes[i].button), 0);
    lv_obj_set_style_border_color(themeButtons[i], lv_color_hex(ui_theme::palettes[i].accent), 0);
    lv_obj_set_style_text_color(themeCaptions[i], lv_color_hex(ui_theme::palettes[i].text), 0);
  }
  lv_image_set_src(companionPreview, look.companion == app_settings::Companion::orbit ? &nova_assets::orbit_thumb : &nova_assets::nova_thumb);
}
static void companion_select(lv_event_t* event) {
  auto look = app_settings::appearance();
  look.companion = static_cast<app_settings::Companion>(reinterpret_cast<uintptr_t>(lv_event_get_user_data(event)));
  app_settings::set_appearance(look); refresh_appearance();
}
static void theme_select(lv_event_t* event) {
  auto look = app_settings::appearance();
  look.theme = static_cast<app_settings::Theme>(reinterpret_cast<uintptr_t>(lv_event_get_user_data(event)));
  app_settings::set_appearance(look); ui_theme::apply(look.theme); refresh_appearance();
  lastDimChoice = lastPresetValue = 255; refresh_choices();
}
static void open_appearance(lv_event_t*) { close_overlays(); refresh_appearance(); lv_obj_move_foreground(appearanceOverlay); lv_obj_set_hidden(appearanceOverlay, false); }
static void close_appearance(lv_event_t*) { lv_obj_set_hidden(appearanceOverlay, true); }

static void quota_text(lv_obj_t* label, const char* value) {
  if (strcmp(lv_label_get_text(label), value) != 0) lv_label_set_text(label, value);
}
static const aim::ViewData* quota_view(const aim::Snapshot& snapshot, const char* provider) {
  for (size_t v = 0; v < aim::kMaxViews; ++v) {
    if (snapshot.viewsConfigured && v >= snapshot.viewCount) continue;
    const auto& view = snapshot.views[v];
    const char* key = view.valid ? view.providerKey : snapshot.viewKeys[v];
    if (strcmp(key, provider) == 0) return &view;
  }
  return nullptr;
}
static void refresh_quota_choices() {
  const auto snapshot = aim::read();
  if (!quotaProviderCount) {
    quota_text(quotaProviderLabel, "No providers configured");
    quota_text(quotaProviderHelp, "Codex: 5 HOURS / 7 DAYS.\nZCode: 5 HOURS / 7 DAYS / MONTHLY MCP when reported.");
    quota_text(quotaSelectionLabel, "Choose your AIs in the PC app first.");
    quota_text(quotaSetupHelp, "Connect USB, select providers in Setup, then Start host.\nTap REFRESH here after connecting.");
    for (auto* button : quotaButtons) lv_obj_set_hidden(button, true);
    lv_obj_set_state(quotaPrev, LV_STATE_DISABLED, true); lv_obj_set_state(quotaNext, LV_STATE_DISABLED, true);
    return;
  }
  const auto* provider = quotaProviders[quotaProviderIndex];
  const auto* style = aim::provider_style(provider);
  const auto saved = app_settings::nova_window(provider);
  const auto* view = quota_view(snapshot, provider);
  quota_text(quotaProviderLabel, style ? style->label : provider);
  const bool codex = strcmp(provider, "codex") == 0, zcode = strcmp(provider, "zcode") == 0;
  const bool claude = strcmp(provider, "claude") == 0, gemini = strcmp(provider, "gemini") == 0;
  const bool opencode = strcmp(provider, "opencode") == 0;
  quota_text(quotaProviderHelp, codex ? "5 HOURS = short-term limit. 7 DAYS = weekly limit." :
      zcode ? "5 HOURS / 7 DAYS = model quota.\nMONTHLY MCP = tool calls, not a monthly token budget." :
      claude ? "5 HOURS / 7 DAYS come from the optional statusline bridge." :
      (gemini || opencode) ? "Local token activity only. No account quota is available." :
      "Shows quota rows supplied by your numeric bridge.\nNo automatic editor account quota is available.");
  quota_text(quotaSetupHelp, !snapshot.hostPresent ? "Host offline. Open the PC app and Start host." :
      codex ? "For quota: sign in to Codex with ChatGPT in the PC app.\nTap a window; its percentage is shown on NOVA / ORBIT." :
      zcode ? "For quota: add your ZAI Coding Plan API key in the PC app.\nOnly windows returned by your plan have a percentage." :
      claude ? "For quota: tap Link Claude quota in the PC app AI setup.\nAn API key alone does not provide subscription quota." :
      gemini ? "Use Gemini CLI with session recording for local activity.\nQuota options stay unavailable until real data is supplied." :
      opencode ? "Use OpenCode on this PC; local tokens are read automatically.\nTap Check AI setup in the PC app to check the source." :
      "Set up the external numeric bridge in the PC app.\nLocal token counts are activity, not account quota.");
  lv_obj_set_state(quotaPrev, LV_STATE_DISABLED, quotaProviderCount < 2);
  lv_obj_set_state(quotaNext, LV_STATE_DISABLED, quotaProviderCount < 2);
  int selectedChoice = saved.automatic ? 0 : -1;
  int durationChoice = -1;
  unsigned durationMatches = 0;
  for (size_t i = 0; i < quotaChoiceCount && !saved.automatic; ++i) {
    const auto& option = quotaChoices[i];
    if (saved.minutes != option.minutes) continue;
    if (strcmp(saved.title, option.title) == 0) selectedChoice = static_cast<int>(i + 1);
    if (saved.minutes) { durationChoice = static_cast<int>(i + 1); ++durationMatches; }
  }
  if (selectedChoice < 0 && durationMatches == 1) selectedChoice = durationChoice;
  for (size_t i = 0; i < 4; ++i) {
    lv_obj_set_hidden(quotaButtons[i], i > quotaChoiceCount);
    if (i > quotaChoiceCount) continue;
    lv_obj_set_state(quotaButtons[i], LV_STATE_DISABLED, quotaChoiceCount == 0);
    const bool selected = quotaChoiceCount && selectedChoice == static_cast<int>(i);
    style_button(quotaButtons[i], selected);
    lv_obj_set_style_text_color(quotaCaptions[i], lv_color_hex(selected ? ui_theme::background : ui_theme::text), 0);
    char text[96]; snprintf(text, sizeof(text), "%s", quotaChoiceCount ? "AUTO / MOST URGENT" : "ACTIVITY ONLY");
    const auto* row = view && !view->informational ? nova_quota_row(*view, provider, i ? quotaChoices[i - 1] : app_settings::NovaWindow{}) : nullptr;
    if (i) {
      const auto& option = quotaChoices[i - 1];
      char period[36]; quota_window_label(option.minutes, option.title, period, sizeof(period));
      bool duplicateDuration = false;
      for (size_t other = 0; other < quotaChoiceCount; ++other)
        duplicateDuration |= other != i - 1 && quotaChoices[other].minutes == option.minutes;
      if (duplicateDuration) snprintf(text, sizeof(text), "%s / %s", period, option.title);
      else snprintf(text, sizeof(text), "%s", period);
    }
    quota_text(quotaCaptions[i], text);
    if (row) {
      const float remaining = view->showsRemaining ? row->usedPercent : 100.0f - row->usedPercent;
      const char* state = !snapshot.hostPresent ? "OFFLINE" : view->notice ? "ERROR" : view->fetching ? "UPDATING" :
          millis() - view->quotaReceivedMs >= 300000u ? "STALE" : "REPORTED";
      char percent[16]; format_percent(remaining, true, percent, sizeof(percent));
      snprintf(text, sizeof(text), "%s left / %s", percent, state);
    } else snprintf(text, sizeof(text), "%s", i ? "NOT REPORTED / can select" :
                    quotaChoiceCount ? "Lowest remaining quota" : "No account quota available");
    quota_text(quotaDetails[i], text);
    lv_obj_set_style_text_color(quotaDetails[i], lv_color_hex(selected ? ui_theme::background : ui_theme::muted), 0);
  }
  char current[36], text[160]; quota_window_label(saved.minutes, saved.title, current, sizeof(current));
  if (!quotaChoiceCount) snprintf(text, sizeof(text), "No quota windows reported. Local activity only.");
  else snprintf(text, sizeof(text), "Selected: %s%s", saved.automatic ? "AUTO / MOST URGENT" : current,
                !saved.automatic && (!view || view->informational || !nova_quota_row(*view, provider, saved)) ? " / not currently reported" : "");
  quota_text(quotaSelectionLabel, text);
}
static void add_quota_choice(uint32_t minutes, const char* title) {
  if (quotaChoiceCount >= 3) return;
  for (size_t i = 0; i < quotaChoiceCount; ++i)
    if (quotaChoices[i].minutes == minutes && strcmp(quotaChoices[i].title, title) == 0) return;
  auto& choice = quotaChoices[quotaChoiceCount++]; choice = app_settings::NovaWindow{};
  choice.automatic = false; choice.minutes = minutes;
  snprintf(choice.title, sizeof(choice.title), "%s", title);
}
static void load_quota_choices() {
  quotaChoiceCount = 0;
  if (quotaProviderCount) {
    const auto snapshot = aim::read();
    const auto* provider = quotaProviders[quotaProviderIndex];
    const auto* view = quota_view(snapshot, provider);
    const bool modelWindows = strcmp(provider, "codex") == 0 || strcmp(provider, "claude") == 0 || strcmp(provider, "zcode") == 0;
    if (modelWindows) {
      const uint32_t periods[] = {300, 10080, 43200};
      const char* titles[] = {"Session", "Week", "Monthly MCP"};
      const size_t count = strcmp(provider, "zcode") == 0 ? 3 : 2;
      for (size_t p = 0; p < count; ++p) {
        if (view && view->hasUsage) for (size_t r = 0; r < view->rowCount && r < aim::kMaxRows; ++r) {
          const auto& row = view->rows[r];
          if (row.valid && row.title[0] && row.windowMinutes == periods[p]) add_quota_choice(row.windowMinutes, row.title);
        }
      }
      // Retain nonstandard reported rows before filling unused slots with
      // expected windows. Never replace real quotas with explanatory options.
      if (view && view->hasUsage) for (size_t r = 0; r < view->rowCount && r < aim::kMaxRows; ++r) {
        const auto& row = view->rows[r];
        if (row.valid && row.title[0]) add_quota_choice(row.windowMinutes, row.title);
      }
      for (size_t p = 0; p < count; ++p) {
        bool present = false;
        for (size_t i = 0; i < quotaChoiceCount; ++i) present |= quotaChoices[i].minutes == periods[p];
        if (!present) add_quota_choice(periods[p], titles[p]);
      }
    }
    if (view && view->hasUsage) for (size_t r = 0; r < view->rowCount && r < aim::kMaxRows; ++r) {
      const auto& row = view->rows[r];
      if (row.valid && row.title[0]) add_quota_choice(row.windowMinutes, row.title);
    }
  }
  refresh_quota_choices();
}
static void quota_select_cb(lv_event_t* event) {
  const auto choice = reinterpret_cast<uintptr_t>(lv_event_get_user_data(event));
  if (!quotaProviderCount || choice > quotaChoiceCount) return;
  app_settings::set_nova_window(quotaProviders[quotaProviderIndex], choice ? quotaChoices[choice - 1] : app_settings::NovaWindow{});
  refresh_quota_choices();
}
static void quota_provider_cb(lv_event_t* event) {
  if (!quotaProviderCount) return;
  const int direction = reinterpret_cast<intptr_t>(lv_event_get_user_data(event));
  quotaProviderIndex = (quotaProviderIndex + quotaProviderCount + direction) % quotaProviderCount;
  load_quota_choices();
}
static void close_quota(lv_event_t*) { lv_obj_set_hidden(quotaOverlay, true); }
static void open_quota(lv_event_t*) {
  close_overlays();
  quotaProviderCount = 0; quotaProviderIndex = 0;
  const auto snapshot = aim::read();
  for (size_t v = 0; v < aim::kMaxViews; ++v) {
    if (snapshot.viewsConfigured && v >= snapshot.viewCount) continue;
    const auto* key = snapshot.views[v].valid ? snapshot.views[v].providerKey : snapshot.viewKeys[v];
    if (!aim::provider_style(key)) continue;
    bool duplicate = false;
    for (size_t i = 0; i < quotaProviderCount; ++i) duplicate |= strcmp(quotaProviders[i], key) == 0;
    if (!duplicate && quotaProviderCount < 8) snprintf(quotaProviders[quotaProviderCount++], 16, "%s", key);
  }
  // Freeze option identities while the overlay is open. Incoming API row
  // reordering must not change the meaning of a button during a touch.
  load_quota_choices(); lv_obj_move_foreground(quotaOverlay); lv_obj_set_hidden(quotaOverlay, false);
}
static void refresh_quota(lv_event_t*) {
  char previous[16] = {};
  if (quotaProviderCount) snprintf(previous, sizeof(previous), "%s", quotaProviders[quotaProviderIndex]);
  open_quota(nullptr);
  for (size_t i = 0; i < quotaProviderCount; ++i) if (strcmp(quotaProviders[i], previous) == 0) {
    quotaProviderIndex = static_cast<uint8_t>(i); load_quota_choices(); break;
  }
  const auto snapshot = aim::read();
  if (snapshot.hostPresent && snapshot.manualRefreshSupported && !refresh_busy(snapshot.refreshState)) aim::request_refresh();
}

static void refresh_warning_target();
static void warning_slider_cb(lv_event_t* event) {
  if (lv_event_get_code(event) == LV_EVENT_PRESS_LOST) { refresh_warning_target(); return; }
  const uint8_t value = static_cast<uint8_t>(lv_slider_get_value(warningSlider));
  char text[96];
  snprintf(text, sizeof(text), "Low quota <= %u %% remaining / Critical <= %u %%", value, value < 10 ? value : 10);
  lv_label_set_text(warningValue, text);
  if (lv_event_get_code(event) == LV_EVENT_RELEASED) {
    const auto& target = alertTargets[alertTargetIndex];
    if (alertTargetIndex == 0) app_settings::set_warning_percent(value);
    else app_settings::set_warning_for(target.provider, target.title, target.window, value);
    refresh_warning_target();
  }
}
static void close_alerts(lv_event_t*) { lv_obj_set_hidden(alertsOverlay, true); }
static void refresh_warning_target() {
  lv_obj_set_state(warningPrev, LV_STATE_DISABLED, alertTargetCount < 2);
  lv_obj_set_state(warningNext, LV_STATE_DISABLED, alertTargetCount < 2);
  lv_obj_set_state(warningInherit, LV_STATE_DISABLED, alertTargetIndex == 0);
  const auto& target = alertTargets[alertTargetIndex];
  const uint8_t percent = alertTargetIndex ? app_settings::warning_for(target.provider, target.title, target.window) : app_settings::warning_percent();
  lv_slider_set_value(warningSlider, percent, LV_ANIM_OFF);
  lv_obj_send_event(warningSlider, LV_EVENT_VALUE_CHANGED, nullptr);
  char text[128];
  if (!alertTargetIndex) snprintf(text, sizeof(text), "GLOBAL DEFAULT");
  else snprintf(text, sizeof(text), "%s / %s / %s", aim::provider_style(target.provider)->label, target.title,
                app_settings::warning_override_for(target.provider, target.title, target.window) ? "CUSTOM" : "INHERITED");
  lv_label_set_text(warningTargetLabel, text);
}
static void change_warning_target(lv_event_t* event) {
  const int direction = reinterpret_cast<intptr_t>(lv_event_get_user_data(event));
  alertTargetIndex = (alertTargetIndex + alertTargetCount + direction) % alertTargetCount;
  refresh_warning_target();
}
static void inherit_warning(lv_event_t*) {
  if (alertTargetIndex) {
    const auto& target = alertTargets[alertTargetIndex];
    app_settings::set_warning_for(target.provider, target.title, target.window, 0);
    refresh_warning_target();
  }
}
static void open_alerts(lv_event_t*) {
  close_overlays();
  alertTargetCount = 1; alertTargetIndex = 0;
  const auto snapshot = aim::read();
  for (size_t v = 0; v < aim::kMaxViews; ++v) {
    const auto& view = snapshot.views[v];
    if (snapshot.viewsConfigured && v >= snapshot.viewCount) continue;
    if (!view.hasUsage || !aim::provider_style(view.providerKey)) continue;
    for (size_t r = 0; r < view.rowCount && alertTargetCount < 25; ++r) {
      const auto& row = view.rows[r];
      if (!row.valid) continue;
      bool duplicate = false;
      for (size_t i = 1; i < alertTargetCount; ++i)
        duplicate |= alertTargets[i].window == row.windowMinutes && strcmp(alertTargets[i].provider, view.providerKey) == 0 && strcmp(alertTargets[i].title, row.title) == 0;
      if (duplicate) continue;
      auto& target = alertTargets[alertTargetCount++];
      snprintf(target.provider, sizeof(target.provider), "%s", view.providerKey);
      snprintf(target.title, sizeof(target.title), "%s", row.title); target.window = row.windowMinutes;
    }
  }
  refresh_warning_target();
  lv_obj_move_foreground(alertsOverlay); lv_obj_set_hidden(alertsOverlay, false);
}

static void refresh_night_controls() {
  const auto value = nightDraft;
  lv_label_set_text(nightToggleLabel, value.enabled ? "ON" : "OFF");
  char text[100];
  const uint16_t components[] = {static_cast<uint16_t>(value.start / 60), static_cast<uint16_t>(value.start % 60),
                                 static_cast<uint16_t>(value.end / 60), static_cast<uint16_t>(value.end % 60)};
  for (size_t i = 0; i < 4; ++i) {
    snprintf(text, sizeof(text), "%02u", components[i]);
    if (strcmp(lv_label_get_text(nightTimeValues[i]), text) != 0) lv_label_set_text(nightTimeValues[i], text);
  }
  snprintf(text, sizeof(text), "Night brightness: %u %% / Equal start and end = all day", value.percent);
  lv_label_set_text(nightValue, text);
}
static void night_toggle_cb(lv_event_t*) {
  nightDraft.enabled = !nightDraft.enabled;
  app_settings::set_night(nightDraft); refresh_night_controls();
}
static void night_time_cb(lv_event_t* event) {
  if (lv_event_get_code(event) == LV_EVENT_PRESS_LOST) {
    nightDraft = app_settings::night(); refresh_night_controls(); return;
  }
  if (lv_event_get_code(event) == LV_EVENT_RELEASED) {
    app_settings::set_night(nightDraft); return;
  }
  const auto choice = reinterpret_cast<uintptr_t>(lv_event_get_user_data(event));
  if (choice >= 8) return;
  const size_t group = choice / 2;
  const int direction = choice % 2 ? 1 : -1;
  auto& value = group < 2 ? nightDraft.start : nightDraft.end;
  value = app_settings::adjust_night_time(value, group % 2 == 0, direction);
  if (lv_event_get_code(event) == LV_EVENT_SHORT_CLICKED) app_settings::set_night(nightDraft);
  refresh_night_controls();
}
static void night_slider_cb(lv_event_t* event) {
  if (lv_event_get_code(event) == LV_EVENT_PRESS_LOST) {
    nightDraft = app_settings::night(); lv_slider_set_value(nightSlider, nightDraft.percent, LV_ANIM_OFF);
    refresh_night_controls(); return;
  }
  char text[96];
  const uint8_t percent = lv_slider_get_value(nightSlider);
  snprintf(text, sizeof(text), "Night brightness: %u %% / Saved on release", percent);
  lv_label_set_text(nightValue, text);
  if (lv_event_get_code(event) == LV_EVENT_RELEASED) {
    nightDraft.percent = percent;
    app_settings::set_night(nightDraft);
  }
}
static void close_night(lv_event_t*) { lv_obj_set_hidden(nightOverlay, true); }
static void open_night(lv_event_t*) {
  close_overlays();
  nightDraft = app_settings::night();
  refresh_night_controls();
  lv_slider_set_value(nightSlider, app_settings::night().percent, LV_ANIM_OFF);
  lv_obj_move_foreground(nightOverlay); lv_obj_set_hidden(nightOverlay, false);
}

void ui_settings_init() {
  dashScreen = lv_screen_active();
  settingsScreen = lv_obj_create(nullptr);
  lv_obj_set_style_bg_color(settingsScreen, lv_color_hex(ui_theme::background), 0);
  lv_obj_set_style_bg_opa(settingsScreen, LV_OPA_COVER, 0);
  lv_obj_set_style_border_width(settingsScreen, 0, 0);
  lv_obj_set_style_pad_all(settingsScreen, 0, 0);
  lv_obj_set_scrollable(settingsScreen, false);

  auto* header = lv_obj_create(settingsScreen);
  lv_obj_set_size(header, 800, 78);
  lv_obj_set_pos(header, 0, 0);
  lv_obj_set_style_bg_color(header, lv_color_hex(ui_theme::header), 0);
  lv_obj_set_style_border_width(header, 0, 0);
  lv_obj_set_style_radius(header, 0, 0);
  lv_obj_set_style_pad_all(header, 0, 0);
  lv_obj_set_scrollable(header, false);
  make_label(header, 24, 12, 420, "AI MONITOR / DISPLAY " FW_VERSION, &lv_font_montserrat_14, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  make_label(header, 24, 34, 500, "Settings", &lv_font_montserrat_26, ui_theme::text, LV_TEXT_ALIGN_LEFT);
  alertsButton = make_button(header, 608, 16, 168, "ALERTS", open_alerts, nullptr);

  auto* card = lv_obj_create(settingsScreen);
  lv_obj_set_pos(card, 24, 94);
  lv_obj_set_size(card, 752, 314);
  lv_obj_set_style_bg_color(card, lv_color_hex(ui_theme::surface), 0);
  lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
  lv_obj_set_style_border_color(card, lv_color_hex(ui_theme::border), 0);
  lv_obj_set_style_border_width(card, 1, 0);
  lv_obj_set_style_radius(card, 16, 0);
  lv_obj_set_style_pad_all(card, 0, 0);
  lv_obj_set_scrollable(card, false);
  lv_obj_set_clickable(card, false);

  make_label(card, 24, 20, 420, board_profile::visual_dimming ? "VISUAL BRIGHTNESS (LED ON/OFF)" : "DAY BRIGHTNESS", &lv_font_montserrat_16, ui_theme::accent, LV_TEXT_ALIGN_LEFT);
  brightnessValue = make_label(card, 600, 12, 128, "", &lv_font_montserrat_30, ui_theme::text, LV_TEXT_ALIGN_RIGHT);
  brightnessSlider = lv_slider_create(card);
  lv_obj_set_pos(brightnessSlider, 24, 64);
  lv_obj_set_size(brightnessSlider, 700, 20);
  lv_slider_set_range(brightnessSlider, 5, 100);
  lv_obj_set_ext_click_area(brightnessSlider, 16);
  lv_obj_set_style_bg_color(brightnessSlider, lv_color_hex(ui_theme::border), LV_PART_MAIN);
  lv_obj_set_style_bg_opa(brightnessSlider, LV_OPA_COVER, LV_PART_MAIN);
  lv_obj_set_style_radius(brightnessSlider, 5, LV_PART_MAIN);
  lv_obj_set_style_bg_color(brightnessSlider, lv_color_hex(ui_theme::accent), LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(brightnessSlider, lv_color_hex(ui_theme::accent), LV_PART_KNOB);
  lv_obj_set_style_radius(brightnessSlider, 12, LV_PART_KNOB);
  lv_obj_add_event_cb(brightnessSlider, brightness_slider_cb, LV_EVENT_VALUE_CHANGED, nullptr);
  lv_obj_add_event_cb(brightnessSlider, brightness_slider_cb, LV_EVENT_RELEASED, nullptr);
  lv_obj_add_event_cb(brightnessSlider, brightness_slider_cb, LV_EVENT_PRESSED, nullptr);
  lv_obj_add_event_cb(brightnessSlider, brightness_slider_cb, LV_EVENT_PRESS_LOST, nullptr);

  brightnessChoice=make_choice(card,24,104,"CUSTOM\n25 %\n50 %\n75 %\n100 %",brightness_preset_cb);
  actualBrightnessLabel = make_wrap_label(card, 400, 108, 328, "", &lv_font_montserrat_20, ui_theme::muted, LV_TEXT_ALIGN_CENTER);
  connectPcButton=make_button(card,400,148,328,"CONNECT PC",[](lv_event_t*){ui_connection_show();},nullptr);
  make_label(card, 24, 174, 400, "DIM AFTER", &lv_font_montserrat_20, ui_theme::accent, LV_TEXT_ALIGN_LEFT);
  dimChoice=make_choice(card,24,204,"OFF\n1 MINUTE\n5 MINUTES\n10 MINUTES",dim_select_cb);
  previewButton = make_button(card, 560, 204, 168, "TEST DIM", dim_preview_cb, nullptr);
  make_label(card, 24, 278, 704, board_profile::visual_dimming ?
             "Visual dimming; LEDs stay on above 0%. First touch wakes only." :
             "First touch wakes only. Release before the next tap.",
             &lv_font_montserrat_18, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  make_button(settingsScreen, 24, 424, 152, "<  BACK", back_cb, nullptr);
  nightButton = make_button(settingsScreen, 200, 424, 176, "NIGHT MODE", open_night, nullptr);
  make_button(settingsScreen, 392, 424, 176, "APPEARANCE", open_appearance, nullptr);
  quotaButton = make_button(settingsScreen, 592, 424, 184, "AI USAGE", open_quota, nullptr);
  lastDimChoice = lastPresetValue = 255;
  refresh_brightness();
  alertsOverlay = lv_obj_create(lv_layer_top());
  lv_obj_set_size(alertsOverlay, 800, 480); lv_obj_set_pos(alertsOverlay, 0, 0);
  lv_obj_set_style_bg_color(alertsOverlay, lv_color_hex(ui_theme::background), 0);
  lv_obj_set_style_bg_opa(alertsOverlay, LV_OPA_80, 0);
  lv_obj_set_style_pad_all(alertsOverlay, 0, 0); lv_obj_set_style_border_width(alertsOverlay, 0, 0);
  lv_obj_set_scrollable(alertsOverlay, false);
  auto* alertCard = lv_obj_create(alertsOverlay);
  lv_obj_set_pos(alertCard, 24, 64); lv_obj_set_size(alertCard, 752, 354);
  lv_obj_set_style_bg_color(alertCard, lv_color_hex(ui_theme::surface), 0);
  lv_obj_set_style_border_color(alertCard, lv_color_hex(ui_theme::border), 0);
  lv_obj_set_style_pad_all(alertCard, 0, 0); lv_obj_set_scrollable(alertCard, false);
  make_label(alertCard, 24, 20, 700, "Quota warning threshold", &lv_font_montserrat_26, ui_theme::text, LV_TEXT_ALIGN_LEFT);
  warningPrev = make_button(alertCard, 24, 72, 96, "< PREV", change_warning_target, reinterpret_cast<void*>(-1));
  warningNext = make_button(alertCard, 632, 72, 96, "NEXT >", change_warning_target, reinterpret_cast<void*>(1));
  warningTargetLabel = make_label(alertCard, 132, 84, 484, "", &lv_font_montserrat_14, ui_theme::text, LV_TEXT_ALIGN_CENTER);
  warningValue = make_label(alertCard, 24, 142, 700, "", &lv_font_montserrat_16, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  warningSlider = lv_slider_create(alertCard);
  lv_obj_set_pos(warningSlider, 36, 196); lv_obj_set_size(warningSlider, 680, 20);
  lv_slider_set_range(warningSlider, 5, 50); lv_obj_set_ext_click_area(warningSlider, 16);
  lv_obj_set_style_bg_color(warningSlider, lv_color_hex(ui_theme::accent), LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(warningSlider, lv_color_hex(ui_theme::accent), LV_PART_KNOB);
  lv_obj_add_event_cb(warningSlider, warning_slider_cb, LV_EVENT_VALUE_CHANGED, nullptr);
  lv_obj_add_event_cb(warningSlider, warning_slider_cb, LV_EVENT_RELEASED, nullptr);
  lv_obj_add_event_cb(warningSlider, warning_slider_cb, LV_EVENT_PRESS_LOST, nullptr);
  make_label(alertCard, 24, 244, 700, "5-50 %. Release to save. INHERIT restores the global default.", &lv_font_montserrat_14, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  warningInherit = make_button(alertCard, 24, 278, 176, "INHERIT", inherit_warning, nullptr);
  make_button(alertsOverlay, 616, 406, 136, "DONE", close_alerts, nullptr);
  lv_obj_set_hidden(alertsOverlay, true);
  nightOverlay = lv_obj_create(lv_layer_top());
  lv_obj_set_pos(nightOverlay, 0, 0); lv_obj_set_size(nightOverlay, 800, 480);
  lv_obj_set_style_bg_color(nightOverlay, lv_color_hex(ui_theme::background), 0);
  lv_obj_set_style_bg_opa(nightOverlay, LV_OPA_80, 0);
  lv_obj_set_style_pad_all(nightOverlay, 0, 0); lv_obj_set_style_border_width(nightOverlay, 0, 0);
  lv_obj_set_scrollable(nightOverlay, false);
  auto* nightCard = lv_obj_create(nightOverlay);
  lv_obj_set_pos(nightCard, 24, 64); lv_obj_set_size(nightCard, 752, 354);
  lv_obj_set_style_bg_color(nightCard, lv_color_hex(ui_theme::surface), 0);
  lv_obj_set_style_border_color(nightCard, lv_color_hex(ui_theme::border), 0);
  lv_obj_set_style_pad_all(nightCard, 0, 0); lv_obj_set_scrollable(nightCard, false);
  make_label(nightCard, 24, 20, 520, "Scheduled night brightness", &lv_font_montserrat_26, ui_theme::text, LV_TEXT_ALIGN_LEFT);
  make_button(nightCard, 600, 16, 128, "OFF", night_toggle_cb, nullptr, &nightToggleLabel);
  const char* timeNames[] = {"START / HH", "START / MM", "END / HH", "END / MM"};
  for (size_t i = 0; i < 4; ++i) {
    const int x = 24 + i * 182;
    make_label(nightCard, x, 74, 158, timeNames[i], &lv_font_montserrat_14, ui_theme::muted, LV_TEXT_ALIGN_CENTER);
    nightTimeValues[i] = make_label(nightCard, x, 96, 158, "", &lv_font_montserrat_26, ui_theme::text, LV_TEXT_ALIGN_CENTER);
    for (size_t control = 0; control < 2; ++control) {
      const size_t index = i * 2 + control;
      auto* timeButton = make_button(nightCard, x + control * 86, 134, 72, control ? "+" : "-", night_time_cb, reinterpret_cast<void*>(index));
      nightTimeButtons[index] = timeButton;
      lv_obj_set_height(timeButton, 48);
      lv_obj_remove_event_cb(timeButton, night_time_cb);
      for (auto code : {LV_EVENT_SHORT_CLICKED, LV_EVENT_LONG_PRESSED, LV_EVENT_LONG_PRESSED_REPEAT, LV_EVENT_RELEASED, LV_EVENT_PRESS_LOST})
        lv_obj_add_event_cb(timeButton, night_time_cb, code, reinterpret_cast<void*>(index));
    }
  }
  nightValue = make_label(nightCard, 24, 202, 700, "", &lv_font_montserrat_16, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  nightSlider = lv_slider_create(nightCard);
  lv_obj_set_pos(nightSlider, 36, 244); lv_obj_set_size(nightSlider, 680, 20);
  lv_slider_set_range(nightSlider, 5, 50); lv_obj_set_ext_click_area(nightSlider, 16);
  lv_obj_set_style_bg_color(nightSlider, lv_color_hex(ui_theme::accent), LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(nightSlider, lv_color_hex(ui_theme::accent), LV_PART_KNOB);
  lv_obj_add_event_cb(nightSlider, night_slider_cb, LV_EVENT_VALUE_CHANGED, nullptr);
  lv_obj_add_event_cb(nightSlider, night_slider_cb, LV_EVENT_RELEASED, nullptr);
  lv_obj_add_event_cb(nightSlider, night_slider_cb, LV_EVENT_PRESS_LOST, nullptr);
  make_wrap_label(nightCard, 24, 286, 480, "HH / MM: tap or hold +/- to adjust.\nTouch restores daytime level for 60 seconds.", &lv_font_montserrat_14, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  make_button(nightOverlay, 616, 406, 136, "DONE", close_night, nullptr);
  lv_obj_set_hidden(nightOverlay, true);
  appearanceOverlay = lv_obj_create(lv_layer_top());
  lv_obj_set_size(appearanceOverlay, 800, 480); lv_obj_set_pos(appearanceOverlay, 0, 0);
  lv_obj_set_style_bg_color(appearanceOverlay, lv_color_hex(ui_theme::background), 0);
  lv_obj_set_style_bg_opa(appearanceOverlay, LV_OPA_80, 0); lv_obj_set_style_pad_all(appearanceOverlay, 0, 0);
  lv_obj_set_style_border_width(appearanceOverlay, 0, 0); lv_obj_set_scrollable(appearanceOverlay, false);
  auto* appearanceCard = lv_obj_create(appearanceOverlay); lv_obj_set_pos(appearanceCard, 24, 54); lv_obj_set_size(appearanceCard, 752, 374);
  lv_obj_set_style_bg_color(appearanceCard, lv_color_hex(ui_theme::surface), 0);
  lv_obj_set_style_border_color(appearanceCard, lv_color_hex(ui_theme::border), 0); lv_obj_set_style_pad_all(appearanceCard, 0, 0);
  lv_obj_set_scrollable(appearanceCard, false);
  make_label(appearanceCard, 24, 18, 700, "Make it yours", &lv_font_montserrat_26, ui_theme::text, LV_TEXT_ALIGN_LEFT);
  make_label(appearanceCard, 24, 58, 400, "COMPANION", &lv_font_montserrat_14, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  for (size_t i = 0; i < 2; ++i) companionButtons[i] = make_button(appearanceCard, 24 + i * 180, 86, 166,
      app_settings::companion_name(static_cast<app_settings::Companion>(i)), companion_select, reinterpret_cast<void*>(i), &companionCaptions[i]);
  companionPreview = lv_image_create(appearanceCard); lv_obj_set_pos(companionPreview, 546, 54); lv_obj_set_clickable(companionPreview, false);
  make_label(appearanceCard, 24, 160, 700, "UI COLOR THEME", &lv_font_montserrat_14, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  for (size_t i = 0; i < 4; ++i) themeButtons[i] = make_button(appearanceCard, 24 + i * 178, 192, 166,
      app_settings::theme_name(static_cast<app_settings::Theme>(i)), theme_select, reinterpret_cast<void*>(i), &themeCaptions[i]);
  make_label(appearanceCard, 24, 260, 700, "Changes apply now and are saved on this display.", &lv_font_montserrat_14, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  make_label(appearanceCard, 24, 286, 500, "Provider logos and warning colors stay consistent.", &lv_font_montserrat_12, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  make_button(appearanceOverlay, 616, 406, 136, "DONE", close_appearance, nullptr);
  lv_obj_set_hidden(appearanceOverlay, true);
  quotaOverlay = lv_obj_create(lv_layer_top());
  lv_obj_set_size(quotaOverlay, 800, 480); lv_obj_set_pos(quotaOverlay, 0, 0);
  lv_obj_set_style_bg_color(quotaOverlay, lv_color_hex(ui_theme::background), 0);
  lv_obj_set_style_bg_opa(quotaOverlay, LV_OPA_80, 0); lv_obj_set_style_border_width(quotaOverlay, 0, 0);
  lv_obj_set_style_pad_all(quotaOverlay, 0, 0); lv_obj_set_scrollable(quotaOverlay, false);
  auto* quotaCard = lv_obj_create(quotaOverlay);
  lv_obj_set_pos(quotaCard, 24, 24); lv_obj_set_size(quotaCard, 752, 432);
  lv_obj_set_style_bg_color(quotaCard, lv_color_hex(ui_theme::surface), 0);
  lv_obj_set_style_border_color(quotaCard, lv_color_hex(ui_theme::border), 0);
  lv_obj_set_style_pad_all(quotaCard, 0, 0); lv_obj_set_scrollable(quotaCard, false);
  make_label(quotaCard, 24, 16, 700, "AI usage settings", &lv_font_montserrat_26, ui_theme::text, LV_TEXT_ALIGN_LEFT);
  quotaPrev = make_button(quotaCard, 24, 58, 96, "< PREV", quota_provider_cb, reinterpret_cast<void*>(-1));
  quotaNext = make_button(quotaCard, 632, 58, 96, "NEXT >", quota_provider_cb, reinterpret_cast<void*>(1));
  quotaProviderLabel = make_label(quotaCard, 132, 70, 484, "", &lv_font_montserrat_20, ui_theme::text, LV_TEXT_ALIGN_CENTER);
  quotaProviderHelp = make_wrap_label(quotaCard, 24, 116, 704, "", &lv_font_montserrat_16, ui_theme::text, LV_TEXT_ALIGN_LEFT);
  for (size_t i = 0; i < 4; ++i) {
    quotaButtons[i] = make_button(quotaCard, 24 + (i % 2) * 360, 164 + (i / 2) * 72, 344, "",
                                  quota_select_cb, reinterpret_cast<void*>(i), &quotaCaptions[i]);
    lv_obj_set_height(quotaButtons[i], 64);
    lv_obj_set_align(quotaCaptions[i], LV_ALIGN_TOP_LEFT);
    lv_obj_set_pos(quotaCaptions[i], 4, 9); lv_obj_set_width(quotaCaptions[i], 336);
    lv_obj_set_height(quotaCaptions[i], 24); lv_obj_set_style_text_font(quotaCaptions[i], &lv_font_montserrat_20, 0);
    lv_label_set_long_mode(quotaCaptions[i], LV_LABEL_LONG_MODE_DOTS);
    quotaDetails[i] = make_label(quotaButtons[i], 4, 36, 336, "", &lv_font_montserrat_14, ui_theme::muted, LV_TEXT_ALIGN_CENTER);
  }
  quotaSelectionLabel = make_label(quotaCard, 24, 314, 704, "", &lv_font_montserrat_18, ui_theme::accent, LV_TEXT_ALIGN_LEFT);
  lv_label_set_long_mode(quotaSelectionLabel, LV_LABEL_LONG_MODE_DOTS);
  lv_obj_set_height(quotaSelectionLabel, 24);
  quotaSetupHelp = make_wrap_label(quotaCard, 24, 340, 704, "", &lv_font_montserrat_14, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  make_wrap_label(quotaCard, 24, 386, 400, "NOVA + ORBIT show quota remaining.\nAlerts still check every window.",
                  &lv_font_montserrat_14, ui_theme::muted, LV_TEXT_ALIGN_LEFT);
  make_button(quotaOverlay, 464, 406, 136, "REFRESH", refresh_quota, nullptr);
  make_button(quotaOverlay, 616, 406, 136, "DONE", close_quota, nullptr);
  lv_obj_set_hidden(quotaOverlay, true);
  ui_theme::watch(settingsScreen); refresh_appearance();
  saveFeedback = make_label(lv_layer_top(), 590, 406, 186, "", &lv_font_montserrat_12, ui_theme::accent, LV_TEXT_ALIGN_LEFT);
  lv_obj_set_hidden(saveFeedback, true);
}

static void refresh_brightness() {
  const uint8_t percent = brightness_percent(display_get_brightness());
  const int32_t sliderValue = percent < 5 ? 5 : percent;
  if (!lv_obj_has_state(brightnessSlider, LV_STATE_PRESSED) && lv_slider_get_value(brightnessSlider) != sliderValue)
    lv_slider_set_value(brightnessSlider, sliderValue, LV_ANIM_OFF);
  char text[12];
  snprintf(text, sizeof(text), "%u %%", percent);
  if (strcmp(lv_label_get_text(brightnessValue), text) != 0) lv_label_set_text(brightnessValue, text);
  char actual[48];
  snprintf(actual, sizeof(actual), "Actual %u %% / %s", brightness_percent(display_get_applied_brightness()), idle_dim_mode());
  lv_obj_set_state(connectPcButton,LV_STATE_DISABLED,!aim::read().hostPresent);
  if (strcmp(lv_label_get_text(actualBrightnessLabel), actual) != 0) lv_label_set_text(actualBrightnessLabel, actual);
  refresh_choices();
}

void ui_settings_update() {
  // Refresh percentages/availability without moving or rebinding touch targets.
  // New option identities are loaded only on explicit REFRESH/provider change.
  if (!lv_obj_is_hidden(quotaOverlay) && millis() - quotaUpdatedAt >= 500u) {
    quotaUpdatedAt = millis(); refresh_quota_choices();
  }
  const bool choosing = !lv_obj_is_hidden(appearanceOverlay) || !lv_obj_is_hidden(quotaOverlay);
  if (choosing && lv_obj_get_index(saveFeedback) != static_cast<int32_t>(lv_obj_get_child_count(lv_layer_top())) - 1) lv_obj_move_foreground(saveFeedback);
  const int x = choosing ? 48 : 590, y = choosing ? 446 : 406;
  if (lv_obj_get_x(saveFeedback) != x || lv_obj_get_y(saveFeedback) != y) lv_obj_set_pos(saveFeedback, x, y);
  if (lv_screen_active() == settingsScreen && !lv_obj_has_state(brightnessSlider, LV_STATE_PRESSED)) refresh_brightness();
  if (shownSaveRevision != app_settings::save_revision()) {
    shownSaveRevision = app_settings::save_revision(); savedAtMs = millis();
    const bool success = app_settings::save_status() == app_settings::SaveStatus::saved;
    lv_label_set_text(saveFeedback, success ? "SAVED" : "SAVE FAILED");
    lv_obj_set_style_text_color(saveFeedback, lv_color_hex(success ? ui_theme::accent : 0xFF5252), 0);
  }
  lv_obj_set_hidden(saveFeedback, lv_screen_active() != settingsScreen || !shownSaveRevision || millis() - savedAtMs >= 5000u);
}
void ui_settings_show() {
  if (lv_screen_active() != settingsScreen) settingsReturnScreen = lv_screen_active();
  refresh_brightness();
  display_set_brightness(display_get_brightness());
  lv_screen_load(settingsScreen);
}
void ui_settings_hide() {
  lv_obj_set_hidden(saveFeedback, true);
  lv_obj_set_hidden(alertsOverlay, true); lv_obj_set_hidden(nightOverlay, true);
  lv_obj_set_hidden(appearanceOverlay, true);
  lv_obj_set_hidden(quotaOverlay, true);
  lv_screen_load(settingsReturnScreen ? settingsReturnScreen : dashScreen);
}
bool ui_settings_is_active() { return lv_screen_active() == settingsScreen; }
