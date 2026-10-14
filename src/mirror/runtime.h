#pragma once
#include <ArduinoJson.h>
#include <cstdint>
#include <string>
namespace mirror {
bool initialize();
bool command(JsonObjectConst object,uint32_t now,std::string& response);
void poll(uint32_t now,bool connected);
// UI task only: requests full repaint, then consumes real HAL flush pixels.
void ui_tick();
void flushed(int x1,int y1,int x2,int y2,const uint16_t* source,bool last);
}
