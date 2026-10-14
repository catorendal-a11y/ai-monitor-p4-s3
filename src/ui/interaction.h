#pragma once
#include <lvgl.h>

namespace ui_interaction {
// A finger owns one target until release. Sliding off cancels that target and
// suppresses new activations even if the same finger enters another button.
// Sliders deliberately retain their own continuous-drag interaction.
inline void cancel_dragged_press(lv_event_t* event) {
  auto* input = lv_indev_active();
  if (!input || lv_indev_get_type(input) != LV_INDEV_TYPE_POINTER) return;
  auto* object = lv_event_get_target_obj(event);
  lv_point_t point{}; lv_indev_get_point(input, &point);
  lv_area_t area{}; lv_obj_get_coords(object, &area);
  if (point.x >= area.x1 && point.x <= area.x2 && point.y >= area.y1 && point.y <= area.y2) return;
  lv_indev_wait_release(input);
  // Restore a cancelled editable draft immediately, rather than displaying
  // an unsaved value until the user eventually lifts the finger.
  lv_obj_send_event(object, LV_EVENT_PRESS_LOST, input);
}
inline void keep_target(lv_obj_t* object) {
  lv_obj_set_press_lock(object, true);
  lv_obj_add_event_cb(object, cancel_dragged_press, LV_EVENT_PRESSING, nullptr);
}
}
