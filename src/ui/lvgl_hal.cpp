#include "../config.h"
#if !defined(AIM_BOARD_WAVESHARE_S3)
// AI Monitor P4 - LVGL Hardware Abstraction Layer Implementation
// LVGL 9.x with PSRAM buffers, MIPI-DSI DPI panel flush
// Color format: RGB565 (matching ST7701S and JC4880P433C BSP)
// Manual 90 deg CW rotation in flush callback (LVGL rotation crashes on P4)

#include "lvgl_hal.h"
#include <Arduino.h>
#include "../config.h"
#include "display.h"
#include "idle_dim.h"
#include "touch_input.h"
#include "../diagnostics/hardware_types.h"
#include "../diagnostics/graphics_types.h"
#include "../diagnostics/rotation.h"
static TouchInputGuard touchInputGuard;

#include "freertos/FreeRTOS.h"
#include <esp_timer.h>
#include <esp_heap_caps.h>
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_touch.h"

// ───────────────────────────────────────────────────────────────────────────────
// TICK TIMER - 1ms tick for LVGL animations and timers
// ───────────────────────────────────────────────────────────────────────────────
static esp_timer_handle_t lvgl_tick_timer;

static void IRAM_ATTR lvgl_tick_cb(void* arg) { lv_tick_inc(1); }

// ───────────────────────────────────────────────────────────────────────────────
// LVGL BUFFERS - PSRAM (full frame, double buffered) + rotation scratch
// LVGL renders at 800x480 landscape, flush rotates to 480x800 portrait
// ───────────────────────────────────────────────────────────────────────────────
static uint8_t* buf1 = nullptr;
static uint8_t* buf2 = nullptr;
static size_t buf_bytes = 0;
static uint16_t* rot_buf = nullptr;
static size_t rot_buf_pixels = 0;

diagnostics::DisplayMemory diagnostics::draw_memory() {
  DisplayMemory result{};
  result.drawCount = static_cast<uint8_t>((buf1 ? 1 : 0) + (buf2 ? 1 : 0));
  result.drawBytes = result.drawCount * buf_bytes;
  result.rotationBytes = rot_buf ? rot_buf_pixels * sizeof(uint16_t) : 0;
  return result;
}

void lvgl_alloc_buffers() {
  buf_bytes = DISPLAY_H_RES * DISPLAY_V_RES * 2;   // 800 x 480 x 2 = 768000
  rot_buf_pixels = DISPLAY_H_RES * DISPLAY_V_RES;  // 384000 pixels

  buf1 = (uint8_t*)heap_caps_aligned_calloc(64, 1, buf_bytes, MALLOC_CAP_SPIRAM);
  buf2 = (uint8_t*)heap_caps_aligned_calloc(64, 1, buf_bytes, MALLOC_CAP_SPIRAM);
  rot_buf = (uint16_t*)heap_caps_aligned_calloc(64, 1, rot_buf_pixels * 2, MALLOC_CAP_SPIRAM);

  if (!buf1 || !buf2 || !rot_buf) {
    LOG_E("FATAL: LVGL buffer alloc failed!");
    if (buf1) heap_caps_free(buf1);
    if (buf2) heap_caps_free(buf2);
    if (rot_buf) heap_caps_free(rot_buf);
    buf1 = nullptr;
    buf2 = nullptr;
    rot_buf = nullptr;
    return;
  }
  LOG_I("LVGL buffers OK: 2x%u bytes draw + %u bytes rotation (PSRAM)", (unsigned)buf_bytes,
        (unsigned)(rot_buf_pixels * 2));
}

// ───────────────────────────────────────────────────────────────────────────────
// DISPLAY FLUSH CALLBACK - Manual 90 deg CW rotation from 800x480 to 480x800
// Rotation mapping: landscape (x, y) -> portrait (y, 799-x)
// ───────────────────────────────────────────────────────────────────────────────
void lvgl_flush_cb(lv_display_t* disp, const lv_area_t* area, uint8_t* px_map) {
  if (!display_panel || !px_map || !area || !rot_buf) {
    lv_display_flush_ready(disp);
    return;
  }

  int x1 = area->x1, y1 = area->y1;
  int x2 = area->x2, y2 = area->y2;

  if (x1 < 0) x1 = 0;
  if (y1 < 0) y1 = 0;
  if (x2 >= DISPLAY_H_RES) x2 = DISPLAY_H_RES - 1;
  if (y2 >= DISPLAY_V_RES) y2 = DISPLAY_V_RES - 1;

  const int W = x2 - x1 + 1;
  const int H = y2 - y1 + 1;

  if (W <= 0 || H <= 0) {
    lv_display_flush_ready(disp);
    return;
  }

  if ((size_t)(W * H) > rot_buf_pixels) {
    LOG_E("Rotation buffer too small: need %d, have %u", W * H, (unsigned)rot_buf_pixels);
    lv_display_flush_ready(disp);
    return;
  }

  const uint16_t* src = (const uint16_t*)px_map;

#if AIM_GRAPHICS_TELEMETRY
  const int64_t began = esp_timer_get_time();
#endif
  if (!diagnostics::rotate_to_panel(src, W * H, rot_buf, rot_buf_pixels, W, H)) {
    lv_display_flush_ready(disp); return;
  }
#if AIM_GRAPHICS_TELEMETRY
  const int64_t rotated = esp_timer_get_time();
#endif

  const int px1 = y1;        // portrait x start
  const int py1 = 799 - x2;  // portrait y start
  const int px2 = y2;        // portrait x end
  const int py2 = 799 - x1;  // portrait y end

  esp_lcd_panel_draw_bitmap(display_panel, px1, py1, px2 + 1, py2 + 1, rot_buf);
#if AIM_GRAPHICS_TELEMETRY
  diagnostics::record_flush(W * H, static_cast<uint32_t>(rotated - began),
                           static_cast<uint32_t>(esp_timer_get_time() - rotated));
#endif
  lv_display_flush_ready(disp);
}

// ───────────────────────────────────────────────────────────────────────────────
// TOUCH READ CALLBACK - GT911 polled by LVGL
// Touch is 480x800 portrait; LVGL sees 800x480 landscape, so swap x/y.
// ───────────────────────────────────────────────────────────────────────────────
void lvgl_touchpad_read_cb(lv_indev_t* indev_drv, lv_indev_data_t* data) {
  (void)indev_drv;
  if (display_touch == nullptr) {
    touchInputGuard.failed(indev_drv, data);
    return;
  }

  if (esp_lcd_touch_read_data(display_touch) != ESP_OK) {
    touchInputGuard.failed(indev_drv, data);
    return;
  }

  esp_lcd_touch_point_data_t point{};
  uint8_t touch_cnt = 0;
  const esp_err_t result = esp_lcd_touch_get_data(display_touch, &point, &touch_cnt, 1);
  if (result != ESP_OK) {
    touchInputGuard.failed(indev_drv, data);
    return;
  }

  if (touch_cnt == 1) {
    const uint16_t px = point.x;
    const uint16_t py = point.y;

    int32_t lx = 799 - (int32_t)py;  // landscape x = 799 - portrait y
    int32_t ly = (int32_t)px;        // landscape y = portrait x
    if (lx < 0) lx = 0;
    if (lx > 799) lx = 799;
    if (ly < 0) ly = 0;
    if (ly > 479) ly = 479;
    data->point.x = (lv_coord_t)lx;
    data->point.y = (lv_coord_t)ly;
    data->state = LV_INDEV_STATE_PRESSED;
  } else {
    data->state = LV_INDEV_STATE_RELEASED;
  }
  // Only successful reads prove that the waking finger was lifted.
  const bool pressed = data->state == LV_INDEV_STATE_PRESSED;
  const bool awake = idle_dim_touch(pressed);
  if (!touchInputGuard.accept(pressed) || !awake) data->state = LV_INDEV_STATE_RELEASED;
}

// ───────────────────────────────────────────────────────────────────────────────
// LVGL INITIALIZATION
// ───────────────────────────────────────────────────────────────────────────────
void lvgl_hal_init() {
  LOG_I("LVGL HAL init starting...");

  lv_init();
  lvgl_alloc_buffers();

  if (buf1 == nullptr || buf2 == nullptr || rot_buf == nullptr) {
    LOG_E("LVGL buffer allocation failed - cannot continue");
    fatal_halt("lvgl buffer allocation failed");
  }

  // Logical resolution is 800x480 landscape. NO lv_display_set_rotation() -
  // it causes Load access faults on ESP32-P4; the flush callback rotates.
  lv_display_t* disp = lv_display_create(DISPLAY_H_RES, DISPLAY_V_RES);
  lv_display_set_color_format(disp, LV_COLOR_FORMAT_RGB565);
  lv_display_set_buffers(disp, buf1, buf2, buf_bytes, LV_DISPLAY_RENDER_MODE_PARTIAL);
  lv_display_set_flush_cb(disp, lvgl_flush_cb);

  LOG_I("LVGL display driver registered: %dx%d landscape, manual rotation to %dx%d physical, RGB565",
        DISPLAY_H_RES, DISPLAY_V_RES, DISPLAY_H_RES_NATIVE, DISPLAY_V_RES_NATIVE);

  lv_indev_t* indev = lv_indev_create();
  lv_indev_set_type(indev, LV_INDEV_TYPE_POINTER);
  lv_indev_set_read_cb(indev, lvgl_touchpad_read_cb);
  LOG_I("LVGL touch input registered (GT911, manual coordinate swap)");

  const esp_timer_create_args_t tick_timer_args = {.callback = &lvgl_tick_cb,
                                                   .arg = nullptr,
                                                   .dispatch_method = esp_timer_dispatch_t::ESP_TIMER_TASK,
                                                   .name = "lvgl_tick"};

  ESP_ERROR_CHECK(esp_timer_create(&tick_timer_args, &lvgl_tick_timer));
  ESP_ERROR_CHECK(esp_timer_start_periodic(lvgl_tick_timer, 1000));  // 1ms

  LOG_I("LVGL tick timer started (1ms)");
  LOG_I("LVGL HAL init complete");
}

#endif
