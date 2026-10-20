#pragma once
#include <cstdint>

class IdleDimPolicy {
 public:
  // A new critical alert keeps the screen out of idle dimming for a minute, so it is readable on a
  // screen nobody is touching. Night brightness is untouched: it is already chosen for a dark room.
  static constexpr uint32_t alert_hold_ms = 60000;
  void alert(uint32_t now) { initialize(now); alertUntil_ = now + alert_hold_ms; holding_ = true; }
  uint8_t update(uint32_t now, uint8_t selected, uint8_t timeoutMinutes) {
    initialize(now);
    // Signed difference keeps the hold correct across the 32-bit millisecond rollover.
    const bool held = holding_ && static_cast<int32_t>(alertUntil_ - now) > 0;
    if (!held) holding_ = false;
    dimmed_ = !held && (preview_ || (timeoutMinutes != 0 && !pressed_ &&
                                     now - lastActivity_ >= static_cast<uint32_t>(timeoutMinutes) * 60000u));
    if (!dimmed_ || selected == 0) return selected;
    const uint8_t reduced = static_cast<uint32_t>(selected) * 30u / 100u;
    return reduced ? reduced : 1;
  }
  // First press wakes only; suppress that finger until a confirmed release.
  bool touch(uint32_t now, bool pressed) {
    initialize(now);
    if (pressed) {
      if (dimmed_) suppress_ = true;
      lastActivity_ = now;
      dimmed_ = preview_ = false;
    } else {
      if (pressed_) lastActivity_ = now;
      suppress_ = false;
    }
    pressed_ = pressed;
    return pressed && !suppress_;
  }
  void preview() { preview_ = dimmed_ = true; }
  bool dimmed() const { return dimmed_; }
 private:
  void initialize(uint32_t now) {
    if (!initialized_) { lastActivity_ = now; initialized_ = true; }
  }
  uint32_t lastActivity_ = 0, alertUntil_ = 0;
  bool holding_ = false;
  bool initialized_ = false, pressed_ = false, suppress_ = false, preview_ = false, dimmed_ = false;
};

void idle_dim_update();
bool idle_dim_touch(bool pressed);
void idle_dim_preview();
// A new critical quota alert: hold full brightness for a minute (UI task only).
void idle_dim_alert();
const char* idle_dim_mode();
