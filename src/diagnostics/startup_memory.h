#pragma once
#include <cstdint>

namespace diagnostics {
enum class StartupStage : uint8_t { beforeDisplay, afterDisplay, afterLvgl, afterCompanion };
inline constexpr const char* startup_stage_names[] = {
  "before-display", "after-display", "after-lvgl", "after-companion"
};
struct MemoryReading {
  uint32_t total = 0, free = 0, minimum = 0, largest = 0;
  bool valid() const { return minimum<=free && free<=total && largest<=free; }
};
struct StartupCheckpoint {
  bool captured = false;
  uint32_t uptimeMs = 0;
  MemoryReading internal, psram;
};
// Caller synchronizes access. Record once and in stage order; readings cannot be overwritten.
struct StartupMemory {
  StartupCheckpoint checkpoints[4]{};
  bool capture(StartupStage stage,uint32_t now,const MemoryReading& internal,const MemoryReading& psram) {
    const unsigned index=static_cast<unsigned>(stage);
    if (index>=4 || checkpoints[index].captured || !internal.valid() || !psram.valid() ||
        (index && !checkpoints[index-1].captured)) return false;
    checkpoints[index]={true,now,internal,psram};
    return true;
  }
};
void capture_startup_memory(StartupStage stage);
}  // namespace diagnostics
