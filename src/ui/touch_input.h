#pragma once
#include <lvgl.h>

// A failed I2C read is not proof that a finger was released. Cancel the
// gesture and wait for a successful release before accepting another press.
class TouchInputGuard {
 public:
  void failed(lv_indev_t* input, lv_indev_data_t* data) {
    waitingForRelease_ = true;
    // In a read callback get_active_obj() is empty. wait_release() makes LVGL
    // send PRESS_LOST to its retained target while processing this sample;
    // reset() would silently discard that target and leave editable drafts.
    lv_indev_wait_release(input);
    data->state = LV_INDEV_STATE_RELEASED;
  }
  bool accept(bool pressed) {
    if (!waitingForRelease_) return true;
    if (!pressed) waitingForRelease_ = false;
    return false;
  }
 private:
  bool waitingForRelease_ = false;
};
