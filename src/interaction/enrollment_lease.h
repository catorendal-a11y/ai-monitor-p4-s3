#pragma once
#include <cstdint>
namespace interaction {
// Only a fresh enrollment exchange extends this lease; quota heartbeats cannot.
class EnrollmentLease {
 public:
  void start(uint32_t now) { active_=true;last_=now; }
  void cancel() { active_=false; }
  bool valid(uint32_t now,bool connected) const {
    return active_ && connected && uint32_t(now-last_)<3000;
  }
  bool renew(uint32_t now,bool connected) {
    if(!valid(now,connected)){cancel();return false;}
    last_=now;return true;
  }
 private:
  bool active_=false;
  uint32_t last_=0;
};
}
