#include "../config.h"
#if defined(AIM_BOARD_WAVESHARE_S3)
#include "lvgl_hal.h"
#include "display.h"
#include "idle_dim.h"
#include "touch_input.h"
#include "visual_dimmer.h"
#include "../diagnostics/hardware_types.h"
#include "../diagnostics/graphics_types.h"
#include "../mirror/runtime.h"
#include <Arduino.h>
#include "esp_heap_caps.h"
#include "esp_timer.h"

namespace {
constexpr size_t draw_bytes = DISPLAY_H_RES * 20u * sizeof(uint16_t);
uint8_t* draw_buffer = nullptr;
lv_obj_t* dimmer = nullptr;
esp_timer_handle_t tick_timer = nullptr;
TouchInputGuard touchInputGuard;
void tick_callback(void*) { lv_tick_inc(1); }
}  // namespace

void s3_visual_brightness(uint8_t brightness) {
  apply_visual_dimmer(dimmer, brightness);
}

void lvgl_alloc_buffers() {
  draw_buffer = static_cast<uint8_t*>(heap_caps_aligned_calloc(64, 1, draw_bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA));
  if (!draw_buffer) fatal_halt("S3 draw buffer allocation failed");
}

diagnostics::DisplayMemory diagnostics::draw_memory() {
  DisplayMemory result{}; result.drawCount = draw_buffer ? 1 : 0;
  result.drawBytes = draw_buffer ? draw_bytes : 0; return result;
}

void lvgl_flush_cb(lv_display_t* display, const lv_area_t* area, uint8_t* pixels) {
  // PARTIAL mode supplies contiguous rows. The RGB driver copies them into
  // its persistent PSRAM framebuffer before returning; no rotation needed.
  if (display_panel && area && pixels) {
    mirror::flushed(area->x1,area->y1,area->x2,area->y2,reinterpret_cast<const uint16_t*>(pixels),lv_display_flush_is_last(display));
#if AIM_GRAPHICS_TELEMETRY
    const int64_t began = esp_timer_get_time();
#endif
    ESP_ERROR_CHECK(esp_lcd_panel_draw_bitmap(display_panel, area->x1, area->y1, area->x2 + 1, area->y2 + 1, pixels));
#if AIM_GRAPHICS_TELEMETRY
    diagnostics::record_flush((area->x2 - area->x1 + 1) * (area->y2 - area->y1 + 1), 0,
                             static_cast<uint32_t>(esp_timer_get_time() - began));
#endif
  }
  lv_display_flush_ready(display);
}

void lvgl_touchpad_read_cb(lv_indev_t* input, lv_indev_data_t* data) {
  data->state = LV_INDEV_STATE_RELEASED;
  if (!display_touch || esp_lcd_touch_read_data(display_touch) != ESP_OK) {
    touchInputGuard.failed(input, data); return;
  }
  esp_lcd_touch_point_data_t point{};
  uint8_t count = 0;
  if (esp_lcd_touch_get_data(display_touch, &point, &count, 1) != ESP_OK) {
    touchInputGuard.failed(input, data); return;
  }
  if (count == 1) {
    data->point.x = static_cast<lv_coord_t>(point.x < DISPLAY_H_RES ? point.x : DISPLAY_H_RES - 1);
    data->point.y = static_cast<lv_coord_t>(point.y < DISPLAY_V_RES ? point.y : DISPLAY_V_RES - 1);
    data->state = LV_INDEV_STATE_PRESSED;
  }
  const bool pressed = data->state == LV_INDEV_STATE_PRESSED;
  const bool awake = idle_dim_touch(pressed);
  if (!touchInputGuard.accept(pressed) || !awake) data->state = LV_INDEV_STATE_RELEASED;
}

void lvgl_hal_init() {
  lv_init();
  lvgl_alloc_buffers();
  auto* display = lv_display_create(DISPLAY_H_RES, DISPLAY_V_RES);
  lv_display_set_color_format(display, LV_COLOR_FORMAT_RGB565);
  lv_display_set_buffers(display, draw_buffer, nullptr, draw_bytes, LV_DISPLAY_RENDER_MODE_PARTIAL);
  lv_display_set_flush_cb(display, lvgl_flush_cb);
  auto* input = lv_indev_create();
  lv_indev_set_type(input, LV_INDEV_TYPE_POINTER);
  lv_indev_set_read_cb(input, lvgl_touchpad_read_cb);
  dimmer = create_visual_dimmer();
  s3_visual_brightness(display_get_applied_brightness());
  esp_timer_create_args_t timer{};
  timer.callback = tick_callback; timer.dispatch_method = ESP_TIMER_TASK; timer.name = "lvgl_tick";
  ESP_ERROR_CHECK(esp_timer_create(&timer, &tick_timer));
  ESP_ERROR_CHECK(esp_timer_start_periodic(tick_timer, 1000));
}
#endif
