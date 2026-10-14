#pragma once
#include <cstdint>
#include <lvgl.h>
#include "../app_settings.h"

namespace ui_theme {
struct Palette { uint32_t background, header, surface, border, text, muted, accent, button, pressed; };
inline constexpr Palette palettes[] = {
  {0x0C1215,0x11191D,0x141D21,0x263239,0xEFF5F3,0xA3B2BC,0x35D07F,0x242F35,0x32434C},
  {0x0A1622,0x0F1D2C,0x142536,0x304758,0xE7F3FE,0xABC1D5,0x54C4F2,0x21384C,0x34546D},
  {0x151023,0x1B1529,0x231B35,0x403252,0xF4EDFF,0xBDB0D0,0xC49AFF,0x352846,0x514066},
  {0x1D1311,0x231815,0x2A1D19,0x4B3730,0xFFF0E5,0xCCB7A8,0xFFB96A,0x402B23,0x614638}
};
inline Palette current = palettes[0];
inline app_settings::Theme selectedTheme = app_settings::Theme::forest;
inline uint32_t& background = current.background;
inline uint32_t& header = current.header;
inline uint32_t& surface = current.surface;
inline uint32_t& border = current.border;
inline uint32_t& text = current.text;
inline uint32_t& muted = current.muted;
inline uint32_t& accent = current.accent;
inline uint32_t& button = current.button;
inline uint32_t& pressed = current.pressed;
inline lv_obj_t* roots[8] = {};
inline uint32_t revision = 0;
inline void watch(lv_obj_t* screen) {
  for (auto*& root : roots) { if (root == screen) return; if (!root) { root = screen; return; } }
}
inline void load(app_settings::Theme theme) {
  selectedTheme = app_settings::normalize_appearance({app_settings::Companion::nova, theme}).theme;
  current = palettes[static_cast<uint8_t>(selectedTheme)];
}
inline void recolor(lv_obj_t* object, const Palette& before, const Palette& after) {
  const uint32_t oldColors[] = {before.background,before.header,before.surface,before.border,before.text,before.muted,before.accent,before.button,before.pressed};
  const uint32_t newColors[] = {after.background,after.header,after.surface,after.border,after.text,after.muted,after.accent,after.button,after.pressed};
  const lv_part_t parts[] = {LV_PART_MAIN,LV_PART_INDICATOR,LV_PART_KNOB,LV_PART_ITEMS,LV_PART_SCROLLBAR};
  const lv_state_t states[] = {LV_STATE_DEFAULT,LV_STATE_PRESSED,LV_STATE_DISABLED,LV_STATE_CHECKED,LV_STATE_FOCUSED};
  const lv_style_prop_t properties[] = {LV_STYLE_BG_COLOR,LV_STYLE_TEXT_COLOR,LV_STYLE_BORDER_COLOR,LV_STYLE_OUTLINE_COLOR,LV_STYLE_SHADOW_COLOR,LV_STYLE_BG_GRAD_COLOR};
  for (const auto part : parts) for (const auto state : states) for (const auto property : properties) {
    lv_style_value_t value;
    const auto selector = static_cast<lv_style_selector_t>(part) | state;
    if (lv_obj_get_local_style_prop(object,property,&value,selector) != LV_STYLE_RES_FOUND) continue;
    const uint32_t color = (uint32_t(value.color.red) << 16) | (uint32_t(value.color.green) << 8) | value.color.blue;
    for (size_t i = 0; i < 9; ++i) if (color == oldColors[i]) {
      value.color = lv_color_hex(newColors[i]); lv_obj_set_local_style_prop(object,property,value,selector); break;
    }
  }
  for (uint32_t i = 0; i < lv_obj_get_child_count(object); ++i) recolor(lv_obj_get_child(object,i),before,after);
}
inline void apply(app_settings::Theme theme) {
  const auto previous = current; load(theme);
  ++revision;
  for (auto* root : roots) if (root) recolor(root,previous,current);
  recolor(lv_layer_top(),previous,current);
  lv_obj_invalidate(lv_screen_active());
}
}
