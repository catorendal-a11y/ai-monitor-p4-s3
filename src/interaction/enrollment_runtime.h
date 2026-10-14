#pragma once
#include <ArduinoJson.h>
#include <string>
#include "enrollment.h"
namespace interaction {
struct EnrollmentPublication {
  EnrollmentState state=EnrollmentState::closed;
  uint32_t revision=0,receivedAt=0,remainingMs=0;
  char code[20]{};
};
// Serial-owner API. Keys never cross publication/queue boundaries.
bool enrollment_runtime_initialize(uint32_t bootId);
void enrollment_runtime_poll(uint32_t now,bool connected);
bool enrollment_runtime_command(JsonObjectConst,uint32_t,std::string&);
// UI-owner API. Wire commands cannot call these local action entry points.
bool enrollment_local_arm();
bool enrollment_local_action(uint32_t revision,bool confirm);
void enrollment_local_visibility(uint32_t revision,bool visible,bool awake,uint32_t now);
EnrollmentPublication enrollment_read();
}
