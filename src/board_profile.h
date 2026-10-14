#pragma once

// Compile-time identities; never derive a hardware target from incoming data.
namespace board_profile {
#if defined(AIM_BOARD_WAVESHARE_S3)
inline constexpr const char* id = "waveshare-s3-43";
inline constexpr const char* name = "Waveshare ESP32-S3-Touch-LCD-4.3";
inline constexpr const char* chip = "esp32s3";
inline constexpr const char* display = "waveshare-s3-touch-lcd-4.3";
inline constexpr const char* panel = "ST7262";
inline constexpr const char* panel_id = "esp32s3-rgb";
inline constexpr const char* brightness_control = "visual-dimming-switch";
inline constexpr bool visual_dimming = true;
inline constexpr bool experimental = true;
inline constexpr unsigned ui_stack_bytes = 32768;
inline constexpr unsigned ui_update_ms = 50;
#else
inline constexpr const char* id = "guition-p4";
inline constexpr const char* name = "GUITION JC4880P433";
inline constexpr const char* chip = "esp32p4";
inline constexpr const char* display = "jc4880p433";
inline constexpr const char* panel = "ST7701S";
inline constexpr const char* panel_id = "esp32p4-mipi-dsi";
inline constexpr const char* brightness_control = "pwm";
inline constexpr bool visual_dimming = false;
inline constexpr bool experimental = false;
inline constexpr unsigned ui_stack_bytes = 65536;
inline constexpr unsigned ui_update_ms = 40;
#endif
}  // namespace board_profile
