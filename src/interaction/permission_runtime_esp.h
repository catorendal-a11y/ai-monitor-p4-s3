#pragma once
#include <ArduinoJson.h>
#include <string>
#include "permission_ui_api.h"
namespace interaction {
// Serial owner only. Production builds leave this subsystem disabled.
bool permission_runtime_initialize(uint32_t boot);
void permission_runtime_poll(uint32_t now,bool hostPresent);
bool permission_runtime_command(JsonObjectConst,uint32_t,std::string&);
bool permission_runtime_transmit();
}
