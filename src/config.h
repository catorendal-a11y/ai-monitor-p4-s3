#pragma once
// Shared AI Monitor configuration; hardware backend selected at build time.

#define FW_VERSION "v1.19.1-rc8"
#include "board_profile.h"
// Reported to the AI Monitor companion in the info handshake (protocol level).
#define AIM_REPORTED_VERSION "2.23.0"

// ───────────────────────────────────────────────────────────────────────────────
// DISPLAY & TOUCH - MIPI-DSI (handled by ESP-IDF native drivers)
// ───────────────────────────────────────────────────────────────────────────────
#if defined(AIM_BOARD_WAVESHARE_S3)
#define PIN_TOUCH_SDA 8
#define PIN_TOUCH_SCL 9
#else
#define PIN_TOUCH_SDA 7
#define PIN_TOUCH_SCL 8
#endif
#define TOUCH_ADDR_GT911 0x5D  // GT911 default I2C address

// MIPI-DSI lane configuration - actual settings live in display.cpp
#if !defined(AIM_BOARD_WAVESHARE_S3)
#define MIPI_DSI_LANE_NUM 2
#define MIPI_DSI_LANE_BITRATE_MBPS 500u
#endif

// Display resolution
// Physical panel: 480x800 portrait
// Logical (LVGL): 800x480 landscape (manual rotation in flush callback)
#define DISPLAY_H_RES 800
#define DISPLAY_V_RES 480
#if defined(AIM_BOARD_WAVESHARE_S3)
#define DISPLAY_H_RES_NATIVE 800
#define DISPLAY_V_RES_NATIVE 480
#else
#define DISPLAY_H_RES_NATIVE 480
#define DISPLAY_V_RES_NATIVE 800
#endif

// Default backlight (0-255). The AI Monitor companion can override it with
// set_brightness (0-100), which is persisted to NVS.
#if defined(AIM_BOARD_WAVESHARE_S3)
#define DISPLAY_DEFAULT_BRIGHTNESS 255
#else
#define DISPLAY_DEFAULT_BRIGHTNESS 160
#endif

// ───────────────────────────────────────────────────────────────────────────────
// DEBUG LOGGING
// ───────────────────────────────────────────────────────────────────────────────
// LOG_E is always compiled in - errors must be diagnosable in the field.
// Release builds stay silent on the serial line so the AI Monitor protocol
// replies remain clean.
#define LOG_E(f, ...) Serial.printf("[E] " f "\n", ##__VA_ARGS__)
#ifndef DEBUG_BUILD
#define DEBUG_BUILD 0
#endif
#if DEBUG_BUILD
#define LOG_D(f, ...) Serial.printf("[D] " f "\n", ##__VA_ARGS__)
#define LOG_I(f, ...) Serial.printf("[I] " f "\n", ##__VA_ARGS__)
#define LOG_W(f, ...) Serial.printf("[W] " f "\n", ##__VA_ARGS__)
#else
#define LOG_D(...) \
  do {             \
  } while (0)
#define LOG_I(...) \
  do {             \
  } while (0)
#define LOG_W(...) \
  do {             \
  } while (0)
#endif

// ───────────────────────────────────────────────────────────────────────────────
// ASCII SANITIZATION - LVGL Montserrat fonts only cover 0x20-0x7E
// ───────────────────────────────────────────────────────────────────────────────
#include <cstddef>
inline void sanitize_ascii(char* buf, unsigned int len) {
  for (unsigned int i = 0; i < len && buf[i]; i++) {
    if (buf[i] < 0x20 || buf[i] > 0x7E) buf[i] = '?';
  }
}

[[noreturn]] void fatal_halt(const char* reason);
