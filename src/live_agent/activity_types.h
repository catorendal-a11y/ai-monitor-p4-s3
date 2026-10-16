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
// The host age is measured at receipt; unsigned subtraction preserves clock rollover.
inline uint64_t observed_age_ms(const UsbLiveSnapshot& snapshot,const AgentMetadata& item,uint32_t now) {
  return static_cast<uint64_t>(item.observedAgeSeconds)*1000u+static_cast<uint32_t>(now-snapshot.receivedAt);
}
UsbLiveSnapshot read_usb();
}
