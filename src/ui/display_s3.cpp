#include "../config.h"
#if defined(AIM_BOARD_WAVESHARE_S3)
// Original Waveshare 4.3-inch board. Pin reference: ESP32_Display_Panel v1.0.4;
// CH422G register addresses: WCH CH422 datasheet (8-bit address >> 1).
#include "display.h"
#include "../app_settings.h"
#include <Arduino.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <cstring>
#include "driver/gpio.h"
#include "esp_lcd_panel_rgb.h"
#include "esp_heap_caps.h"
#include "esp_psram.h"

#if !CONFIG_SPIRAM_XIP_FROM_PSRAM
#error "S3 RGB target requires the matching official Espressif XIP SDK"
#endif

esp_lcd_panel_handle_t display_panel = nullptr;
esp_lcd_touch_handle_t display_touch = nullptr;

namespace {
constexpr unsigned i2c_frequency = 400000;
constexpr uint8_t ch422_system_address = 0x24;
constexpr uint8_t ch422_output_address = 0x38;
constexpr uint8_t backlight_mask = 1u << 2;
constexpr uint8_t lcd_reset_mask = 1u << 3;
constexpr uint8_t touch_reset_mask = 1u << 1;
constexpr std::array<int, 16> rgb_pins{14, 38, 18, 17, 10, 39, 0, 45, 48, 47, 21, 1, 2, 42, 41, 40};
i2c_master_bus_handle_t bus = nullptr;
i2c_master_dev_handle_t system_device = nullptr, output_device = nullptr;
esp_lcd_panel_io_handle_t touch_io = nullptr;
uint8_t outputs = 0xdb;  // Backlight off; USB selector EXIO5 low; SD select high.
std::atomic<uint8_t> selected_brightness{DISPLAY_DEFAULT_BRIGHTNESS};
uint16_t applied_brightness = 256;

void add_device(uint8_t address, i2c_master_dev_handle_t* handle) {
  i2c_device_config_t config{};
  config.dev_addr_length = I2C_ADDR_BIT_LEN_7;
  config.device_address = address;
  config.scl_speed_hz = i2c_frequency;
  ESP_ERROR_CHECK(i2c_master_bus_add_device(bus, &config, handle));
}

bool write_outputs(uint8_t value) {
  if (value == outputs) return true;
  if (i2c_master_transmit(output_device, &value, sizeof(value), 100) != ESP_OK) return false;
  outputs = value;
  return true;
}

void reset_expander_pin(uint8_t mask, unsigned low_ms, unsigned high_ms) {
  if (!write_outputs(static_cast<uint8_t>(outputs & ~mask))) fatal_halt("S3 expander reset failed");
  delay(low_ms);
  if (!write_outputs(static_cast<uint8_t>(outputs | mask))) fatal_halt("S3 expander reset failed");
  delay(high_ms);
}
}  // namespace

// Implemented in the S3 LVGL HAL; no LVGL calls before its overlay exists.
void s3_visual_brightness(uint8_t brightness);

void display_set_brightness(uint8_t brightness) {
  if (brightness == applied_brightness) return;
  const auto next = static_cast<uint8_t>(brightness ? outputs | backlight_mask : outputs & ~backlight_mask);
  if (!write_outputs(next)) {
    LOG_E("S3 backlight I2C write failed");
    app_settings::report_save(false);
    return;
  }
  s3_visual_brightness(brightness);
  applied_brightness = brightness;
}

uint8_t display_get_brightness() { return selected_brightness.load(std::memory_order_relaxed); }
uint8_t display_get_applied_brightness() { return applied_brightness <= 255 ? static_cast<uint8_t>(applied_brightness) : 0; }
void display_remember_brightness(uint8_t brightness) {
  selected_brightness = brightness;
  app_settings::set_brightness(brightness);
}
void display_apply_brightness(uint8_t brightness, bool persist) {
  selected_brightness = brightness;
  display_set_brightness(brightness);
  if (persist) display_remember_brightness(brightness);
}

void display_fill_black() {
  if (!display_panel) return;
  void* frame = nullptr;
  ESP_ERROR_CHECK(esp_lcd_rgb_panel_get_frame_buffer(display_panel, 1, &frame));
  memset(frame, 0, DISPLAY_H_RES * DISPLAY_V_RES * sizeof(uint16_t));
}

void display_init() {
  selected_brightness = app_settings::brightness();
  // Arduino's getPsramSize reports heap capacity after XIP reservations, not
  // physical size. Inspect the chip capacity so valid XIP builds can boot.
  if (!psramFound() || esp_psram_get_size() < 8u * 1024u * 1024u) fatal_halt("S3 needs 8MB OPI PSRAM");

  i2c_master_bus_config_t i2c{};
  i2c.i2c_port = I2C_NUM_0;
  i2c.sda_io_num = static_cast<gpio_num_t>(PIN_TOUCH_SDA);
  i2c.scl_io_num = static_cast<gpio_num_t>(PIN_TOUCH_SCL);
  i2c.clk_source = I2C_CLK_SRC_DEFAULT;
  i2c.glitch_ignore_cnt = 7;
  i2c.flags.enable_internal_pullup = true;
  ESP_ERROR_CHECK(i2c_new_master_bus(&i2c, &bus));
  add_device(ch422_system_address, &system_device);
  add_device(ch422_output_address, &output_device);
  // Load safe data before changing the whole bank to outputs.
  ESP_ERROR_CHECK(i2c_master_transmit(output_device, &outputs, sizeof(outputs), 100));
  const uint8_t output_enable = 0x01;
  ESP_ERROR_CHECK(i2c_master_transmit(system_device, &output_enable, sizeof(output_enable), 100));
  reset_expander_pin(lcd_reset_mask, 10, 100);

  esp_lcd_rgb_panel_config_t rgb{};
  rgb.clk_src = LCD_CLK_SRC_DEFAULT;
  rgb.data_width = 16;
  rgb.bits_per_pixel = 16;
  rgb.num_fbs = 1;
  rgb.bounce_buffer_size_px = DISPLAY_H_RES * 10;
  rgb.sram_trans_align = 4; rgb.psram_trans_align = 64;
  rgb.hsync_gpio_num = 46; rgb.vsync_gpio_num = 3;
  rgb.de_gpio_num = 5; rgb.pclk_gpio_num = 7; rgb.disp_gpio_num = -1;
  std::copy(rgb_pins.begin(), rgb_pins.end(), rgb.data_gpio_nums);
  rgb.timings.pclk_hz = 16000000;
  rgb.timings.h_res = DISPLAY_H_RES; rgb.timings.v_res = DISPLAY_V_RES;
  rgb.timings.hsync_pulse_width = 4; rgb.timings.hsync_back_porch = 8; rgb.timings.hsync_front_porch = 8;
  rgb.timings.vsync_pulse_width = 4; rgb.timings.vsync_back_porch = 8; rgb.timings.vsync_front_porch = 8;
  rgb.timings.flags.pclk_active_neg = true;
  rgb.flags.fb_in_psram = true;
  ESP_ERROR_CHECK(esp_lcd_new_rgb_panel(&rgb, &display_panel));
  ESP_ERROR_CHECK(esp_lcd_panel_reset(display_panel));
  ESP_ERROR_CHECK(esp_lcd_panel_init(display_panel));
  display_fill_black();

  // INT low while releasing reset selects GT911's default 0x5D address.
  gpio_set_direction(GPIO_NUM_4, GPIO_MODE_OUTPUT);
  gpio_set_level(GPIO_NUM_4, 0);
  reset_expander_pin(touch_reset_mask, 100, 200);
  gpio_reset_pin(GPIO_NUM_4);
  esp_lcd_panel_io_i2c_config_t touch_config{};
  touch_config.dev_addr = ESP_LCD_TOUCH_IO_I2C_GT911_ADDRESS;
  touch_config.control_phase_bytes = 1;
  touch_config.lcd_cmd_bits = 16;
  touch_config.flags.disable_control_phase = true;
  touch_config.scl_speed_hz = i2c_frequency;
  ESP_ERROR_CHECK(esp_lcd_new_panel_io_i2c(bus, &touch_config, &touch_io));
  esp_lcd_touch_config_t touch{};
  touch.x_max = DISPLAY_H_RES; touch.y_max = DISPLAY_V_RES;
  touch.rst_gpio_num = GPIO_NUM_NC; touch.int_gpio_num = GPIO_NUM_4;
  ESP_ERROR_CHECK(esp_lcd_touch_new_i2c_gt911(touch_io, &touch, &display_touch));
  display_set_brightness(display_get_brightness());
}
#endif
