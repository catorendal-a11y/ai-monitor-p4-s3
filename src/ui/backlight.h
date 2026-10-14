#pragma once
#include <cstdint>

// The UI task owns backlight writes; the USB task may read the selected level.
void display_set_brightness(uint8_t brightness);
uint8_t display_get_brightness();
// UI-task only: actual PWM level, including night mode and idle dimming.
uint8_t display_get_applied_brightness();
void display_apply_brightness(uint8_t brightness, bool persist);
void display_remember_brightness(uint8_t brightness);

constexpr uint8_t brightness_percent(uint8_t raw) {
  return static_cast<uint8_t>((static_cast<uint32_t>(raw) * 100u + 127u) / 255u);
}

constexpr uint8_t brightness_raw(uint8_t percent) {
  return static_cast<uint8_t>((static_cast<uint32_t>(percent) * 255u + 50u) / 100u);
}
