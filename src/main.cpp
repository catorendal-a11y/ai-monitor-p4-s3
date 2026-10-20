// AI Monitor P4 - Main Entry Point
// GUITION JC4880P433 ESP32-P4 4.3" Touch Display Dev Board
// A dedicated desk display for AI provider usage limits, fed by the
// AI Monitor companion app (tobymarks/esp32-ai-monitor) over USB serial.

#include <Arduino.h>

#include "ai_monitor/ai_monitor.h"
#include "config.h"
#include "dashboard.h"
#include "ui/display.h"
#include "ui/lvgl_hal.h"
#include "ui/idle_dim.h"
#include "ui_settings.h"
#include "ui_usage_details.h"
#include "ui_notifications.h"
#include "ui_nova.h"
#include "ui_agents.h"
#include "ui_event_center.h"
#include "ui_menu.h"
#include "ui_enrollment.h"
#include "ui_history.h"
#include "ui_permission.h"
#include "ui_connection.h"
#include "mirror/runtime.h"
#include "ui/theme.h"
#include "diagnostics/hardware_types.h"
#include "diagnostics/ppa_benchmark.h"
#include "companions/runtime.h"

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static TaskHandle_t uiHandle = nullptr;

[[noreturn]] void fatal_halt(const char* reason) {
  LOG_E("FATAL: %s", reason);
  delay(3000);
  ESP.restart();
  for (;;) {
  }
}

// UI task (core 1): owns every lv_* call. Renders the dashboard from the
// synchronized snapshot the aiMon task publishes.
static void uiTask(void*) {
  ui_theme::load(app_settings::appearance().theme);
  dashboard_init();
  ui_settings_init();
  ui_details_init();
  ui_notifications_init();
  ui_nova_init();
  ui_agents_init();
  ui_event_center_init();
  ui_menu_init();
  ui_enrollment_init();
  ui_history_init();
  ui_connection_init();
  ui_permission_init();
  ui_nova_show();
  diagnostics::capture_startup_memory(diagnostics::StartupStage::afterCompanion);

  uint32_t lastUpdate = 0;
  for (;;) {
    aim::apply_pending_controls();
    const uint32_t now = millis();
    if (now - lastUpdate >= board_profile::ui_update_ms) {
      lastUpdate = now;
      // A transient first NVS read can recover after the screens exist.
      // Bring their palette into sync with the recovered stored selection.
      const auto theme = app_settings::appearance().theme;
      if (ui_theme::selectedTheme != theme) ui_theme::apply(theme);
      idle_dim_update();  // every screen, independent of USB freshness
      ui_settings_update();
      dashboard_update();
      ui_details_update();
      ui_nova_update();
      ui_agents_update();
      ui_notifications_update();
      ui_event_center_update();
      ui_menu_update();
      ui_enrollment_update();
      ui_history_update();
      ui_connection_update();
      ui_permission_update();
    }
    mirror::ui_tick();
    lv_timer_handler();
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}

void setup() {
  // AIM1 frames arrive as a single USB burst; the small default HWCDC buffer
  // would silently truncate them. HWCDC only resizes while stopped.
  // Reserve space for the 4095-byte payload AND its AIM1 header/trailing newline.
  Serial.setRxBufferSize(8192);
#if defined(AIM_USB_PERMISSION_RUNTIME)
  Serial.setTxBufferSize(2048);
  Serial.setTxTimeoutMs(0); // A permission write must never wait behind unrelated output.
#endif
#if defined(AIM_BOARD_WAVESHARE_S3)
  // The USB TO UART connector is used for both flashing and normal host data.
  Serial.begin(115200, SERIAL_8N1, 44, 43);
#else
  Serial.begin(115200);
#endif
  delay(100);

  LOG_I("LimitBuddy %s", FW_VERSION);
  LOG_I("Hardware: %s", board_profile::name);

  diagnostics::capture_startup_memory(diagnostics::StartupStage::beforeDisplay);
  display_init();
  diagnostics::capture_startup_memory(diagnostics::StartupStage::afterDisplay);
  lvgl_hal_init();
  diagnostics::capture_startup_memory(diagnostics::StartupStage::afterLvgl);
  diagnostics::initialize_hardware();
  diagnostics::run_isolated_ppa_benchmark();
  companions::runtime::initialize();
  aim::begin();  // initializes the control queue before the UI task starts

  if (xTaskCreatePinnedToCore(uiTask, "ui", board_profile::ui_stack_bytes, nullptr, 2, &uiHandle, 1) != pdPASS) {
    fatal_halt("ui task allocation failed");
  }

  LOG_I("All tasks started");
}

void loop() {
  // Arduino runs setup() on this task, so retain its full startup stack.
  // UI, USB and timers now have their own tasks; release the unused loop
  // task/stack rather than guessing a smaller startup allocation.
  disableLoopWDT();
  vTaskDelete(nullptr);
}
