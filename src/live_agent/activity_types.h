#pragma once
#include <cstdint>
#include "../agent/types.h"
namespace live_agent {
using ActivityState=agent::State;
inline constexpr auto& activity_names=agent::state_names;
inline constexpr uint32_t activity_lease_ms=30000;
inline constexpr uint8_t hue_count=12;  // colors the agents screen can draw
struct AgentMetadata {
  char provider[13]{},id[65]{};
  ActivityState state=ActivityState::UNKNOWN;
  uint32_t elapsedSeconds=0;
  uint16_t observedAgeSeconds=0;
  bool hasElapsed=false;
  // A readable name and color derived by the host from the opaque id (liveSummary capability).
  char label[16]{};
  uint8_t hue=0;
  bool hasLabel=false;
};
struct UsbLiveSnapshot {
  AgentMetadata agents[8]{};
  uint32_t epoch=0,sequence=0,receivedAt=0,revision=0;
  uint8_t count=0;
  bool fresh=false;
  // Sessions the host observes beyond the eight listed, and which AIs (provider bits as in
  // aim::ProviderStyle::activityMask) are selected and have verified observers installed.
  uint8_t total=0,selectedMask=0,linkedMask=0;
  bool hasSummary=false;
};
// The host age is measured at receipt; unsigned subtraction preserves clock rollover.
inline uint64_t observed_age_ms(const UsbLiveSnapshot& snapshot,const AgentMetadata& item,uint32_t now) {
  return static_cast<uint64_t>(item.observedAgeSeconds)*1000u+static_cast<uint32_t>(now-snapshot.receivedAt);
}
UsbLiveSnapshot read_usb();
}
