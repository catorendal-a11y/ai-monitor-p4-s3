#pragma once
#include <cstdint>
namespace live_agent {
enum class ActivityState : uint8_t { UNKNOWN, IDLE, THINKING, EDITING, SEARCHING, BUILDING,
                                    TESTING, WAITING, FAILED, DONE };
inline constexpr const char* activity_names[]={"UNKNOWN","IDLE","THINKING","EDITING","SEARCHING",
                                              "BUILDING","TESTING","WAITING","FAILED","DONE"};
inline constexpr uint32_t activity_lease_ms=30000;
struct AgentMetadata {
  char provider[13]{},id[65]{};
  ActivityState state=ActivityState::UNKNOWN;
};
struct UsbLiveSnapshot {
  AgentMetadata agents[8]{};
  uint32_t epoch=0,sequence=0,receivedAt=0,revision=0;
  uint8_t count=0;
  bool fresh=false;
};
UsbLiveSnapshot read_usb();
}
