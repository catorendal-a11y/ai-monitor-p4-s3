// AI Monitor P4 - LVGL Hardware Abstraction Layer
// LVGL 9.x RGB565 with PSRAM buffers, MIPI-DSI DPI panel flush.
// Manual 90 deg CW rotation in the flush callback avoids failures observed
// with lv_display_set_rotation on this ESP32-P4 panel.

#pragma once
#include <lvgl.h>
#include "../config.h"
#include "esp_lcd_panel_ops.h"
#include "esp_lcd_touch.h"

// ───────────────────────────────────────────────────────────────────────────────
// FUNCTION DECLARATIONS
// ───────────────────────────────────────────────────────────────────────────────
void lvgl_hal_init();
void lvgl_alloc_buffers();
void lvgl_flush_cb(lv_display_t* disp, const lv_area_t* area, uint8_t* px_map);
void lvgl_touchpad_read_cb(lv_indev_t* indev, lv_indev_data_t* data);

// External handles from display.cpp
extern esp_lcd_panel_handle_t display_panel;
extern esp_lcd_touch_handle_t display_touch;
