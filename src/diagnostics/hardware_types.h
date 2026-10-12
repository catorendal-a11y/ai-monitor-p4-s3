#pragma once
#include <cstdint>
#include "startup_memory.h"

namespace diagnostics {
struct DisplayMemory {
  uint32_t drawBytes = 0, rotationBytes = 0, framebufferBytes = 0, bounceBytes = 0;
  uint8_t drawCount = 0, framebufferCount = 0;
};
struct HardwareBaseline {
  uint32_t chipRevision = 0, cpuMHz = 0, flashBytes = 0, flashHz = 0;
  uint32_t applicationBytes = 0, partitionBytes = 0, partitionOffset = 0;
  uint32_t heapTotal = 0, heapFree = 0, heapMinimum = 0, heapLargest = 0;
  uint32_t psramSize = 0, psramTotal = 0, psramFree = 0, psramMinimum = 0, psramLargest = 0;
  const char* sdkVersion = "unknown";
  const char* hostedVersion = "unavailable";
  bool hostedCompiled = false, ppaSupported = false;
  DisplayMemory display;
  StartupMemory startup;
};
DisplayMemory draw_memory();
DisplayMemory panel_memory();
void initialize_hardware();
HardwareBaseline hardware_baseline();
}  // namespace diagnostics
