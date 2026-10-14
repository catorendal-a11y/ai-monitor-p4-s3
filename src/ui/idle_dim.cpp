#include "idle_dim.h"
#include "backlight.h"
#include "../app_settings.h"
#include <Arduino.h>
#include "night_mode.h"
#include "brightness_fade.h"

static IdleDimPolicy policy;
static uint32_t nightLastTouch = 0;
static bool nightTouched = false;
static BrightnessFade fade;
static const char* mode = "NORMAL";
const char* idle_dim_mode() { return mode; }
void idle_dim_update() {
  uint8_t recovered = 0;
  if (app_settings::take_initial_brightness(recovered)) display_apply_brightness(recovered, false);
  const uint32_t now = millis();
  const uint8_t selected = display_get_brightness();
  const uint8_t base = nightTouched && now - nightLastTouch < 60000u ? selected :
                       night_brightness(aim::read(), now, selected, app_settings::night());
  const uint8_t target = policy.update(now, base, app_settings::dim_minutes());
  mode = policy.dimmed() ? "IDLE" : (base < selected ? "NIGHT" : "NORMAL");
  display_set_brightness(fade.update(now, target, display_get_applied_brightness()));
}
bool idle_dim_touch(bool pressed) {
  if (pressed && display_get_brightness() < brightness_raw(5)) policy.preview();
  const bool accepted = policy.touch(millis(), pressed);
  if (pressed) {
    nightLastTouch = millis(); nightTouched = true;
    if (display_get_brightness() < brightness_raw(5)) display_apply_brightness(brightness_raw(5), false);
    else display_set_brightness(display_get_brightness());
    fade.reset(millis(), display_get_brightness());
    mode = "NORMAL";
  }
  return accepted;
}
void idle_dim_preview() { policy.preview(); idle_dim_update(); }
