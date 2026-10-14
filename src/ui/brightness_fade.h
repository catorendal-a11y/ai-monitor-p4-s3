#pragma once
#include <algorithm>
#include <cstdint>

class BrightnessFade {
 public:
  static constexpr uint32_t duration = 600;
  void reset(uint32_t now, uint8_t value) { initialized_ = true; start_ = target_ = output_ = value; startedMs_ = now; }
  uint8_t update(uint32_t now, uint8_t target, uint8_t actual) {
    if (!initialized_ || actual != output_) reset(now, actual);
    if (target_ != target) { start_ = actual; target_ = target; startedMs_ = now; }
    const uint32_t elapsed = std::min(now - startedMs_, duration);
    output_ = static_cast<uint8_t>(static_cast<int32_t>(start_) + (static_cast<int32_t>(target_) - start_) * static_cast<int32_t>(elapsed) / static_cast<int32_t>(duration));
    return output_;
  }
 private:
  uint8_t start_ = 0, target_ = 0, output_ = 0;
  uint32_t startedMs_ = 0;
  bool initialized_ = false;
};
