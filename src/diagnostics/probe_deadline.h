#pragma once
#include <cstdint>
namespace diagnostics {
inline bool probe_deadline_exceeded(uint32_t began,uint32_t now,bool finished) {
  return !finished && now-began>=10000u;
}
}
