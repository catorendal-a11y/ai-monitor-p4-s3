#include "graphics_types.h"
#if AIM_GRAPHICS_TELEMETRY
#include <freertos/FreeRTOS.h>
namespace {
diagnostics::GraphicsCounters counters;
portMUX_TYPE counterMux = portMUX_INITIALIZER_UNLOCKED;
}
#endif

namespace diagnostics {
void record_flush(uint32_t pixels, uint32_t rotation, uint32_t submission) {
#if AIM_GRAPHICS_TELEMETRY
  // UI-task caller only; do not invoke this normal critical section from an ISR.
  portENTER_CRITICAL(&counterMux); counters.add(pixels, rotation, submission); portEXIT_CRITICAL(&counterMux);
#else
  (void)pixels; (void)rotation; (void)submission;
#endif
}
GraphicsSnapshot graphics_snapshot() {
  GraphicsSnapshot result{};
#if AIM_GRAPHICS_TELEMETRY
  result.enabled = true;
  portENTER_CRITICAL(&counterMux); result.counters = counters; portEXIT_CRITICAL(&counterMux);
#endif
  return result;
}
}  // namespace diagnostics
