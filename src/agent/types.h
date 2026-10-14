#pragma once
#include <cstdint>
namespace agent {
inline constexpr unsigned max_sources=8;
enum class State : uint8_t { UNKNOWN, IDLE, WORKING, THINKING, READING, SEARCHING, EDITING, WRITING,
                             RUNNING, BUILDING, TESTING, WAITING, NEEDS_ATTENTION, ERROR, COMPLETED,
                             FAILED=ERROR, DONE=COMPLETED };
inline constexpr const char* state_names[]={"UNKNOWN","IDLE","WORKING","THINKING","READING",
  "SEARCHING","EDITING","WRITING","RUNNING","BUILDING","TESTING","WAITING","NEEDS_ATTENTION","ERROR","COMPLETED"};
inline constexpr unsigned state_count=sizeof(state_names)/sizeof(*state_names);
enum class EventType : uint8_t { SESSION_STARTED, SESSION_ENDED, ACTIVITY, ATTENTION,
                                TASK_CREATED, TASK_STARTED, TASK_PROGRESS, TASK_COMPLETED,
                                TASK_FAILED, TASK_CANCELLED };
// Compatibility counts from session_activity. No quota, tokens, prompt or permission authority.
struct SessionCounts {
  uint16_t running=0,waiting=0,completed=0,error=0;
  uint8_t source=0;
};
struct Snapshot {
  SessionCounts sessions[max_sources]{};
  uint8_t sessionCount=0;
  uint32_t sessionActivityMs=0,revision=0;
  bool fresh=false;
};
Snapshot read();
}
