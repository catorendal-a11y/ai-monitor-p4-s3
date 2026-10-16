#pragma once
#include <ArduinoJson.h>
#include <string>
#include "runtime.h"
namespace companions::runtime {
#if defined(CONFIG_IDF_TARGET_ESP32P4)
bool command(JsonObjectConst object,uint32_t now,std::string& response);
void poll(uint32_t now,bool connected);
void set_boot(uint32_t boot);
#else
inline bool command(JsonObjectConst,uint32_t,std::string&){return false;}
inline void poll(uint32_t,bool){}
inline void set_boot(uint32_t){}
#endif
}
