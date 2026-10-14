// AI Monitor P4 - Display Driver
// ESP32-P4: ST7701S 480x800 via MIPI-DSI + GT911 touch
// GUITION JC4880P433 4.3" Touch Display Dev Board

#pragma once

#include <stdint.h>
#include "backlight.h"
#include "../config.h"
#include "esp_lcd_panel_ops.h"
#if !defined(AIM_BOARD_WAVESHARE_S3)
#include "esp_lcd_mipi_dsi.h"
#include "esp_lcd_st7701.h"
#endif
#include "esp_lcd_touch.h"
#include "esp_lcd_touch_gt911.h"
#include "driver/i2c_master.h"

// ───────────────────────────────────────────────────────────────────────────────
// DISPLAY HANDLES - accessible by LVGL HAL for flush/touch callbacks
// ───────────────────────────────────────────────────────────────────────────────
extern esp_lcd_panel_handle_t display_panel;
extern esp_lcd_touch_handle_t display_touch;

// ───────────────────────────────────────────────────────────────────────────────
// FUNCTION DECLARATIONS
// ───────────────────────────────────────────────────────────────────────────────
void display_init();

// Fill physical panel with black (used at boot). Do not call during LVGL
// runtime - raw draw_bitmap races MIPI flush.
void display_fill_black();
