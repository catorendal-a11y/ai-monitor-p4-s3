// AI Monitor receiver - firmware wrapper around the pure protocol core.
//
// Protocol logic (handshake, AIM1 framing, frames, replies) lives in
// ai_monitor_proto.h (covered by tests/test_protocol.cpp).
// This file wires Arduino USB CDC, millis/heap,
// queued backlight control and snapshot publication; it NEVER touches LVGL: the UI
// task reads the snapshot in dashboard.cpp.

#include "ai_monitor.h"

#include <Arduino.h>

#include <cstring>
#include <algorithm>
#include <atomic>
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "esp_random.h"

#include "../config.h"
#include "../ui/backlight.h"
#include "ai_monitor_proto.h"
#include "../diagnostics/hardware_types.h"
#include "../diagnostics/graphics_types.h"
#include "../diagnostics/ppa_benchmark.h"

namespace live_agent {
static UsbLiveSnapshot published;
static portMUX_TYPE publicationMux=portMUX_INITIALIZER_UNLOCKED;
static void publish_usb(const UsbLiveSnapshot& value) {
  portENTER_CRITICAL(&publicationMux);published=value;portEXIT_CRITICAL(&publicationMux);
}
UsbLiveSnapshot read_usb() {
  UsbLiveSnapshot value;
  portENTER_CRITICAL(&publicationMux);value=published;portEXIT_CRITICAL(&publicationMux);
  return value;
}
}

namespace aim {

// ───────────────────────────────────────────────────────────────────────────────
// SHARED SNAPSHOT (both reader and writer use the same short critical section)
// ───────────────────────────────────────────────────────────────────────────────
static Snapshot g_pub;
static portMUX_TYPE g_snapshotMux = portMUX_INITIALIZER_UNLOCKED;

struct BrightnessControl {
  uint8_t percent;
  bool persist;
};
static QueueHandle_t g_controls = nullptr;
static std::atomic<bool> refreshRequested{false};
void request_refresh() { refreshRequested.store(true, std::memory_order_release); }

static void publish(const Snapshot& snapshot) {
  portENTER_CRITICAL(&g_snapshotMux);
  g_pub = snapshot;
  portEXIT_CRITICAL(&g_snapshotMux);
}

Snapshot read() {
  Snapshot out{};
  portENTER_CRITICAL(&g_snapshotMux);
  out = g_pub;
  portEXIT_CRITICAL(&g_snapshotMux);
  return out;
}

void apply_pending_controls() {
  BrightnessControl control{};
  while (xQueueReceive(g_controls, &control, 0) == pdTRUE) {
    const uint8_t raw = brightness_raw(control.percent);
    display_apply_brightness(raw, control.persist);
  }
}

// ───────────────────────────────────────────────────────────────────────────────
// RX TASK
// ───────────────────────────────────────────────────────────────────────────────
static void ai_monitor_task(void*) {
  static ProtoCore core;  // ~13 KB state in .bss, off the task stack
  core.tick = [] { return millis(); };
  core.heap = [] { return ESP.getFreeHeap(); };
  core.psram_free = [] { return ESP.getFreePsram(); };
  core.hardware = diagnostics::hardware_baseline;
  core.graphics = diagnostics::graphics_snapshot;
  core.ppa_benchmark = diagnostics::ppa_benchmark_result;
  core.firmware_version = FW_VERSION;
  core.boot_id = esp_random();
  core.brightness = [] { return brightness_percent(display_get_brightness()); };
  core.apply_brightness = [](uint8_t pct, bool persist) {
    const BrightnessControl control{pct, persist};
    return xQueueSend(g_controls, &control, 0) == pdTRUE;
  };
  char mac[18];
  const uint64_t efuse = ESP.getEfuseMac();
  // Arduino fills the uint64_t byte-by-byte with esp_efuse_mac_get_default().
  snprintf(mac, sizeof(mac), "%02x:%02x:%02x:%02x:%02x:%02x", (unsigned)(efuse & 0xFF),
           (unsigned)((efuse >> 8) & 0xFF), (unsigned)((efuse >> 16) & 0xFF), (unsigned)((efuse >> 24) & 0xFF),
           (unsigned)((efuse >> 32) & 0xFF), (unsigned)((efuse >> 40) & 0xFF));
  core.set_mac(mac);

  uint8_t chunk[128];
  uint32_t publishedRevision = 0;
  bool publishedOnce = false;
  uint32_t liveRevision=0;
  for (;;) {
    int n = 0;
    while (n < (int)sizeof(chunk) && Serial.available() > 0) {
      const int c = Serial.read();
      if (c < 0) break;
      chunk[n++] = (uint8_t)c;
    }
    for (int i = 0; i < n; ++i) core.feed_byte((char)chunk[i]);
    const bool refresh = refreshRequested.exchange(false, std::memory_order_acq_rel);
    if (refresh) core.request_refresh();
    const bool changed = core.poll();
    if (core.live_snapshot().revision!=liveRevision) {
      liveRevision=core.live_snapshot().revision;
      live_agent::publish_usb(core.live_snapshot());
    }
    // Publish per state change, not per received chunk: one 4 KB frame must
    // not trigger dozens of full-snapshot copies with interrupts disabled.
    const uint32_t revision = core.snapshot_revision();
    if (!publishedOnce || changed || refresh || revision != publishedRevision) {
      publishedOnce = true;
      publishedRevision = revision;
      publish(core.snapshot());
    }
    const std::string& outBuf = core.out();
    if (!outBuf.empty()) {
      const int available = Serial.availableForWrite();
      if (available > 0) {
        const size_t bytes = std::min(outBuf.size(), static_cast<size_t>(available));
        core.consume_out(Serial.write(outBuf.data(), bytes));
      }
    }
    if (n == 0) vTaskDelay(pdMS_TO_TICKS(2));
  }
}

void begin() {
  // Serial.setRxBufferSize(8192) happens in setup() BEFORE Serial.begin -
  // HWCDC only resizes while stopped.
  g_controls = xQueueCreate(4, sizeof(BrightnessControl));
  if (!g_controls) fatal_halt("AI Monitor control queue allocation failed");
  if (xTaskCreatePinnedToCore(ai_monitor_task, "aiMon", 12288, nullptr, 1, nullptr, 1) != pdPASS) {
    fatal_halt("AI Monitor task allocation failed");
  }
}

}  // namespace aim
