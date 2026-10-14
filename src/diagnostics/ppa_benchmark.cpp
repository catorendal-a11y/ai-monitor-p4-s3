#include "ppa_benchmark.h"
#include "rotation.h"
#include <soc/soc_caps.h>

#if defined(AIM_PPA_BENCHMARK) && AIM_PPA_BENCHMARK && defined(SOC_PPA_SUPPORTED) && SOC_PPA_SUPPORTED
#include <Arduino.h>
#include <algorithm>
#include <cstring>
#include <driver/ppa.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#endif

namespace diagnostics {
namespace {
PpaBenchmark result;
bool attempted = false;
#if defined(AIM_PPA_BENCHMARK) && AIM_PPA_BENCHMARK && defined(SOC_PPA_SUPPORTED) && SOC_PPA_SUPPORTED
SemaphoreHandle_t completed = nullptr;
ppa_client_handle_t client = nullptr;
uint16_t *input = nullptr, *cpu = nullptr, *output = nullptr;
bool IRAM_ATTR on_complete(ppa_client_handle_t, ppa_event_data_t*, void*) {
  BaseType_t woken = pdFALSE; xSemaphoreGiveFromISR(completed, &woken); return woken == pdTRUE;
}
void cleanup() {
  if (client && ppa_unregister_client(client) != ESP_OK) {
    result.status = "cleanup-unconfirmed"; result.resourcesRetained = true; return;
  }
  client = nullptr;
  if (completed) vSemaphoreDelete(completed);
  completed = nullptr;
  heap_caps_free(input); heap_caps_free(cpu); heap_caps_free(output);
  input = cpu = output = nullptr;
}
#endif
}
PpaBenchmark ppa_benchmark_result() { return result; }
void run_isolated_ppa_benchmark() {
  if (attempted) return;
  attempted = true;
#if defined(AIM_PPA_BENCHMARK) && AIM_PPA_BENCHMARK && defined(SOC_PPA_SUPPORTED) && SOC_PPA_SUPPORTED
  // Setup-task only, once before UI/RX tasks. Never write to display framebuffers.
  constexpr size_t pixels = 800u * 480u, bytes = pixels * sizeof(uint16_t);
  input = static_cast<uint16_t*>(heap_caps_aligned_alloc(64, bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  cpu = static_cast<uint16_t*>(heap_caps_aligned_alloc(64, bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  output = static_cast<uint16_t*>(heap_caps_aligned_alloc(64, bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT));
  completed = xSemaphoreCreateBinary();
  if (!input || !cpu || !output || !completed) { result.status = "allocation-failed"; cleanup(); return; }
  uint32_t seed = 12345;
  for (size_t index = 0; index < pixels; ++index) {
    seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
    input[index] = static_cast<uint16_t>(seed);
  }
  ppa_client_config_t configuration{};
  configuration.oper_type = PPA_OPERATION_SRM; configuration.max_pending_trans_num = 1;
  if (ppa_register_client(&configuration, &client) != ESP_OK) { result.status = "registration-failed"; cleanup(); return; }
  ppa_event_callbacks_t callbacks{}; callbacks.on_trans_done = on_complete;
  if (ppa_client_register_event_callbacks(client, &callbacks) != ESP_OK) { result.status = "callback-failed"; cleanup(); return; }
  ppa_srm_oper_config_t operation{};
  operation.in.buffer = input; operation.in.pic_w = operation.in.block_w = 800;
  operation.in.pic_h = operation.in.block_h = 480; operation.in.srm_cm = PPA_SRM_COLOR_MODE_RGB565;
  operation.out.buffer = output; operation.out.buffer_size = bytes;
  operation.out.pic_w = 480; operation.out.pic_h = 800; operation.out.srm_cm = PPA_SRM_COLOR_MODE_RGB565;
  operation.rotation_angle = PPA_SRM_ROTATION_ANGLE_90; operation.scale_x = operation.scale_y = 1.0f;
  operation.mode = PPA_TRANS_MODE_NON_BLOCKING;
  uint32_t cpuTimes[8]{}, ppaTimes[8]{};
  result.bitExact = true;
  for (unsigned sample = 0; sample < 8; ++sample) {
    auto began = esp_timer_get_time();
    rotate_to_panel(input, pixels, cpu, pixels, 800, 480);
    cpuTimes[sample] = static_cast<uint32_t>(esp_timer_get_time() - began);
    began = esp_timer_get_time();
    if (ppa_do_scale_rotate_mirror(client, &operation) != ESP_OK) { result.status = "submission-failed"; cleanup(); return; }
    if (xSemaphoreTake(completed, pdMS_TO_TICKS(300)) != pdTRUE) {
      // DMA may still be running. Retain its buffers/client/semaphore until reboot.
      result.status = "timeout-resources-retained"; result.resourcesRetained = true;
      result.bitExact = false; return;
    }
    ppaTimes[sample] = static_cast<uint32_t>(esp_timer_get_time() - began);
    ++result.samples;
    if (memcmp(cpu, output, bytes) != 0) result.bitExact = false;
  }
  std::sort(cpuTimes, cpuTimes + 8); std::sort(ppaTimes, ppaTimes + 8);
  result.cpuMedianUs = (static_cast<uint64_t>(cpuTimes[3]) + cpuTimes[4]) / 2u;
  result.ppaMedianUs = (static_cast<uint64_t>(ppaTimes[3]) + ppaTimes[4]) / 2u;
  result.status = result.bitExact ? "passed" : "pixel-mismatch";
  cleanup();
#elif !defined(SOC_PPA_SUPPORTED) || !SOC_PPA_SUPPORTED
  result.status = "unsupported";
#endif
}
}
