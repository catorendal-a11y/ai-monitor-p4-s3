#pragma once
#include <cstdint>
#include <limits>

#ifndef AIM_GRAPHICS_TELEMETRY
#define AIM_GRAPHICS_TELEMETRY 0
#endif

namespace diagnostics {
struct GraphicsCounters {
  uint64_t flushCalls = 0, pixels = 0, rotateUs = 0, submitUs = 0;
  uint32_t maxRotateUs = 0, maxSubmitUs = 0;
  bool saturated = false;
  void add(uint32_t count, uint32_t rotation, uint32_t submission) {
    const auto increase = [&](uint64_t& value, uint64_t extra) {
      if (extra > std::numeric_limits<uint64_t>::max() - value) {
        value = std::numeric_limits<uint64_t>::max(); saturated = true;
      } else value += extra;
    };
    increase(flushCalls, 1); increase(pixels, count);
    increase(rotateUs, rotation); increase(submitUs, submission);
    if (rotation > maxRotateUs) maxRotateUs = rotation;
    if (submission > maxSubmitUs) maxSubmitUs = submission;
  }
};
struct GraphicsSnapshot {
  bool enabled = false;
  GraphicsCounters counters;
};
void record_flush(uint32_t pixels, uint32_t rotateUs, uint32_t submitUs);
GraphicsSnapshot graphics_snapshot();
}  // namespace diagnostics
