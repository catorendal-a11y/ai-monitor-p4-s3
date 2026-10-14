#pragma once
#include <cstdint>
#include "../agent/types.h"
namespace live_agent {
using ActivityState=agent::State;
inline constexpr auto& activity_names=agent::state_names;
inline constexpr uint32_t activity_lease_ms=30000;
struct AgentMetadata {
  char provider[13]{},id[65]{};
  ActivityState state=ActivityState::UNKNOWN;
  uint32_t elapsedSeconds=0;
  uint16_t observedAgeSeconds=0;
  bool hasElapsed=false;
};
struct UsbLiveSnapshot {
  AgentMetadata agents[8]{};
  uint32_t epoch=0,sequence=0,receivedAt=0,revision=0;
  uint8_t count=0;
  bool fresh=false;
};
UsbLiveSnapshot read_usb();
}
