#pragma once
#include "capture.h"
#include <ArduinoJson.h>
#include <functional>
namespace mirror {
inline bool handle(Capture& capture,JsonObjectConst object,uint32_t now,bool protectedScreen,
                   uint16_t*& image,uint8_t*& coverage,const std::function<bool()>& prepare,std::string& response) {
  const char* cmd=object["cmd"]|"";
  if(!object["cmd"].is<const char*>() || object["cmd"].as<JsonString>().size()!=std::strlen(cmd))return false;
  const char* id=object["requestId"]|"";
  if(!object["requestId"].is<const char*>() || !valid_id(id,object["requestId"].as<JsonString>().size()))return false;
  const bool begin=std::strcmp(cmd,"mirror_begin")==0;
  const bool part=std::strcmp(cmd,"mirror_chunk")==0;
  if(!begin && !part && std::strcmp(cmd,"mirror_status") && std::strcmp(cmd,"mirror_end"))return false;
  if(object.size()!=(begin?2u:part?4u:3u) || (!begin && (!object["frameId"].is<uint32_t>() || object["frameId"].as<uint32_t>()==0)) ||
      (part && (!object["index"].is<unsigned>() || object["index"].as<unsigned>()>=chunks)))return false;
  capture.poll(now,protectedScreen);
  const char* error=nullptr;
  if(begin) {
    if(protectedScreen)error="protected screen";
    else if(!prepare())error="PSRAM unavailable";
    else if(!capture.begin(id,now,image,coverage))error="capture busy";
  } else if(!capture.matches(id,object["frameId"].as<uint32_t>())){return false;}
  JsonDocument reply;
  reply["type"]="mirror";reply["cmd"]=cmd;reply["requestId"]=id;
  reply["frameId"]=begin && error?0u:capture.frame;
  reply["width"]=width;reply["height"]=height;reply["pixelsPerChunk"]=perChunk;
  reply["chunks"]=chunks;reply["encoding"]="rle565le-base64";
  if(!error && !begin) {
    if(!std::strcmp(cmd,"mirror_end"))capture.clear();
    else capture.touch(now);
    if(part && capture.state==State::ready) {
      reply["index"]=object["index"].as<unsigned>();
      reply["data"]=capture.chunk(object["index"].as<unsigned>());
    }
  }
  reply["state"]=error?"unavailable":state_name(capture.state);
  if(error)reply["error"]=error;
  serializeJson(reply,response);return response.size()<=4095;
}
} // namespace mirror
