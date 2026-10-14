#pragma once
#include <ArduinoJson.h>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <initializer_list>
#include "../serialization/json_input.h"
#include "types.h"

namespace companions {
inline bool text(JsonVariantConst value, char* output, size_t capacity, bool filename=false, bool hash=false) {
  if (!value.is<const char*>()) return false;
  const auto string=value.as<JsonString>(); const char* source=string.c_str();
  const size_t length=string.size();
  if (!source || !length || length>=capacity || strlen(source)!=length || (hash && length!=64)) return false;
  for (size_t i=0;i<length;++i) {
    const char ch=source[i];
    if (hash) { if (!((ch>='0'&&ch<='9')||(ch>='a'&&ch<='f'))) return false; }
    else if (!((ch>='a'&&ch<='z')||(!filename && ch>='A'&&ch<='Z')||(ch>='0'&&ch<='9')||ch=='_'||ch=='-'||
               (filename ? ch=='.' : ch==' '))) return false;
  }
  if (filename && (source[0]=='.' || strstr(source,".."))) return false;
  if (filename) {
    const size_t stem = strcspn(source,".");
    // Lowercase-only names prevent aliases on FAT; reserve Windows device stems too.
    for (const char* reserved:{"con","prn","aux","nul"})
      if (stem==strlen(reserved) && !strncmp(source,reserved,stem)) return false;
    if (stem==4 && (!strncmp(source,"com",3) || !strncmp(source,"lpt",3)) &&
        source[3]>='1' && source[3]<='9') return false;
  }
  memcpy(output,source,length+1); return true;
}
inline bool read_pose(JsonVariantConst value, Pose& result) {
  char name[16]; if (!text(value,name,sizeof(name))) return false;
  for (unsigned i=0;i<8;++i) if (!strcmp(name,pose_names[i])) { result=static_cast<Pose>(i); return true; }
  return false;
}
inline bool parse_manifest(const uint8_t* bytes, size_t length, Manifest& output) {
  if (!serialization::strict_object(bytes,length,max_manifest_bytes)) return false;
  JsonDocument document;
  if (deserializeJson(document,bytes,length) || !document.is<JsonObject>()) return false;
  if (!document["version"].is<uint16_t>() || document["version"].as<uint16_t>()!=1 || document["format"]!="RGB565A8") return false;
  Manifest value;
  if (!text(document["name"],value.name,sizeof(value.name)) || !read_pose(document["fallback"],value.fallback)) return false;
  if (document["codec"]=="raw") value.codec=Codec::raw;
  else if (document["codec"]=="lz4") value.codec=Codec::lz4;
  else return false;
  const auto frames=document["frames"].as<JsonArrayConst>();
  if (frames.isNull() || frames.size()==0 || frames.size()>max_frames) return false;
  for (JsonVariantConst item:frames) {
    if (!item.is<JsonObjectConst>()) return false;
    Frame frame;
    if (!read_pose(item["pose"],frame.pose) || !text(item["file"],frame.file,sizeof(frame.file),true) ||
        !text(item["encodedSha256"],frame.encodedSha256,sizeof(frame.encodedSha256),false,true) ||
        !text(item["decodedSha256"],frame.decodedSha256,sizeof(frame.decodedSha256),false,true)) return false;
    for (const char* key:{"width","height","originX","originY"}) if (!item[key].is<uint16_t>()) return false;
    for (const char* key:{"encodedBytes","decodedBytes"}) if (!item[key].is<uint32_t>()) return false;
    frame.width=item["width"].as<uint16_t>(); frame.height=item["height"].as<uint16_t>();
    frame.originX=item["originX"].as<uint16_t>(); frame.originY=item["originY"].as<uint16_t>();
    frame.encodedBytes=item["encodedBytes"].as<uint32_t>(); frame.decodedBytes=item["decodedBytes"].as<uint32_t>();
    if (!frame.width || !frame.height || frame.originX+frame.width>canvas_width || frame.originY+frame.height>canvas_height ||
        frame.decodedBytes!=static_cast<uint32_t>(frame.width)*frame.height*3u ||
        !frame.encodedBytes || frame.encodedBytes>max_frame_bytes+2048u ||
        (value.codec==Codec::raw && frame.encodedBytes!=frame.decodedBytes)) return false;
    const char* extension=strrchr(frame.file,'.');
    if (!extension || strcmp(extension,value.codec==Codec::raw?".raw":".lz4")) return false;
    for (unsigned i=0;i<value.count;++i) {
      const auto& previous=value.frames[i];
      if (previous.pose==frame.pose || !strcmp(previous.file,frame.file) || previous.originX!=frame.originX ||
          previous.originY!=frame.originY || previous.width!=frame.width || previous.height!=frame.height) return false;
    }
    value.frames[value.count++]=frame;
  }
  if (!value.find(value.fallback)) return false;
  output=value; return true;
}
}  // namespace companions
