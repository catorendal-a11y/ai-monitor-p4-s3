#pragma once
#include <lvgl.h>
#include <cstdint>

// Visual attenuation only. Physical LEDs are switched by the board backend.
inline lv_obj_t* create_visual_dimmer() {
  auto* overlay = lv_obj_create(lv_layer_sys());
  lv_obj_remove_style_all(overlay);
  lv_obj_set_size(overlay, 800, 480);
  lv_obj_set_pos(overlay, 0, 0);
  lv_obj_set_style_bg_color(overlay, lv_color_black(), 0);
  lv_obj_set_style_bg_opa(overlay, LV_OPA_TRANSP, 0);
  lv_obj_remove_flag(overlay, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(overlay, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(overlay, LV_OBJ_FLAG_HIDDEN);
  return overlay;
}

inline void apply_visual_dimmer(lv_obj_t* overlay, uint8_t brightness) {
  if (!overlay) return;
  lv_obj_set_style_bg_opa(overlay, static_cast<lv_opa_t>(255u - brightness), 0);
  if (brightness == 255) lv_obj_add_flag(overlay, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_remove_flag(overlay, LV_OBJ_FLAG_HIDDEN);
}
