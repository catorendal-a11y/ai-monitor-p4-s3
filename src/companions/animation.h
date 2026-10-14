#pragma once
#include <ArduinoJson.h>
#include "manifest.h"
#include "animation_types.h"
namespace companions {
inline bool animation_fields(JsonObjectConst object,std::initializer_list<const char*> keys) {
  if(object.size()!=keys.size())return false;
  for(JsonPairConst pair:object) {
    bool found=false;for(const char* key:keys)found|=!strcmp(pair.key().c_str(),key);
    if(!found)return false;
  }
  return true;
}
inline bool animation_mood(JsonVariantConst value,Mood& mood) {
  char name[16];if(!text(value,name,sizeof(name)))return false;
  for(unsigned i=0;i<max_animations;++i)if(!strcmp(name,mood_names[i])){mood=static_cast<Mood>(i);return true;}
  return false;
}
inline bool animation_id(JsonVariantConst value,char* output,size_t size) {
  if(!text(value,output,size,true))return false;
  for(const char* p=output;*p;++p)if(*p=='.')return false;
  return true;
}
inline bool parse_animation_manifest(const uint8_t* bytes,size_t length,AnimationManifest& output) {
  if(!serialization::strict_object(bytes,length,max_manifest_bytes))return false;
  JsonDocument document;
  if(deserializeJson(document,bytes,length) || !document.is<JsonObject>() ||
     !animation_fields(document.as<JsonObjectConst>(),{"version","name","format","codec","fallback","frames","animations"}) ||
     !document["version"].is<uint16_t>() || document["version"].as<uint16_t>()!=2 || document["format"]!="RGB565A8")return false;
  AnimationManifest value;
  char format[16],codec[8];
  if(!text(document["format"],format,sizeof(format)) || strcmp(format,"RGB565A8") ||
     !text(document["codec"],codec,sizeof(codec)))return false;
  if(!text(document["name"],value.name,sizeof(value.name)) || !animation_mood(document["fallback"],value.fallback))return false;
  if(!strcmp(codec,"raw"))value.codec=Codec::raw;
  else if(strcmp(codec,"lz4"))return false;
  const auto frames=document["frames"].as<JsonArrayConst>();
  if(frames.isNull() || !frames.size() || frames.size()>max_animation_frames)return false;
  for(JsonVariantConst item:frames) {
    if(!item.is<JsonObjectConst>() || !animation_fields(item.as<JsonObjectConst>(),
       {"id","file","width","height","originX","originY","encodedBytes","decodedBytes","encodedSha256","decodedSha256"}))return false;
    AnimationAsset asset;auto& frame=asset.frame;
    if(!animation_id(item["id"],asset.id,sizeof(asset.id)) || !text(item["file"],frame.file,sizeof(frame.file),true) ||
       !text(item["encodedSha256"],frame.encodedSha256,sizeof(frame.encodedSha256),false,true) ||
       !text(item["decodedSha256"],frame.decodedSha256,sizeof(frame.decodedSha256),false,true))return false;
    for(const char* key:{"width","height","originX","originY"})if(!item[key].is<uint16_t>())return false;
    for(const char* key:{"encodedBytes","decodedBytes"})if(!item[key].is<uint32_t>())return false;
    frame.width=item["width"];frame.height=item["height"];frame.originX=item["originX"];frame.originY=item["originY"];
    frame.encodedBytes=item["encodedBytes"];frame.decodedBytes=item["decodedBytes"];
    if(!frame.width || !frame.height || frame.originX+frame.width>canvas_width || frame.originY+frame.height>canvas_height ||
       frame.decodedBytes!=static_cast<uint32_t>(frame.width)*frame.height*3u || !frame.encodedBytes ||
       frame.encodedBytes>max_frame_bytes+2048u || (value.codec==Codec::raw && frame.encodedBytes!=frame.decodedBytes))return false;
    const char* extension=strrchr(frame.file,'.');
    if(!extension || strcmp(extension,value.codec==Codec::raw?".raw":".lz4"))return false;
    for(unsigned i=0;i<value.frameCount;++i) {
      const auto& old=value.frames[i];
      if(!strcmp(old.id,asset.id) || !strcmp(old.frame.file,frame.file) || old.frame.width!=frame.width ||
         old.frame.height!=frame.height || old.frame.originX!=frame.originX || old.frame.originY!=frame.originY)return false;
    }
    value.frames[value.frameCount++]=asset;
  }
  const auto animations=document["animations"].as<JsonArrayConst>();
  if(animations.isNull() || !animations.size() || animations.size()>max_animations)return false;
  for(JsonVariantConst item:animations) {
    if(!item.is<JsonObjectConst>() || !animation_fields(item.as<JsonObjectConst>(),{"mood","loop","frames"}) || !item["loop"].is<bool>())return false;
    Animation clip;if(!animation_mood(item["mood"],clip.mood))return false;clip.loop=item["loop"];
    for(unsigned i=0;i<value.animationCount;++i)if(value.animations[i].mood==clip.mood)return false;
    const auto steps=item["frames"].as<JsonArrayConst>();
    if(steps.isNull() || !steps.size() || steps.size()>max_animation_steps)return false;
    for(JsonVariantConst step:steps) {
      char id[25];if(!step.is<JsonObjectConst>() || !animation_fields(step.as<JsonObjectConst>(),{"id","durationMs"}) ||
         !animation_id(step["id"],id,sizeof(id)) || !step["durationMs"].is<uint16_t>() ||
         step["durationMs"].as<uint16_t>()<40 || step["durationMs"].as<uint16_t>()>60000)return false;
      unsigned index=0;while(index<value.frameCount && strcmp(id,value.frames[index].id))++index;
      if(index==value.frameCount)return false;
      clip.steps[clip.count++]={static_cast<uint8_t>(index),step["durationMs"].as<uint16_t>()};
    }
    value.animations[value.animationCount++]=clip;
  }
  if(!value.find(value.fallback))return false;
  output=value;return true;
}
}
