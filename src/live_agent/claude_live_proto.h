#pragma once
#include <ArduinoJson.h>
#include <cstdint>
#include <cstring>
#include "../serialization/json_input.h"

namespace live_agent {
// Independent of quota/AIM1, hooks, LVGL and BLE. Output metrics are not billing tokens.
struct Prompt {
  char id[97]{}, tool[65]{}, hint[513]{};
  bool present=false, displaySupported=false;
  bool equals(const Prompt& other) const {
    return present==other.present && displaySupported==other.displaySupported &&
      !strcmp(id,other.id) && !strcmp(tool,other.tool) && !strcmp(hint,other.hint);
  }
};
struct ClaudeLiveSnapshot {
  uint16_t total=0,running=0,waiting=0;
  uint64_t outputTokens=0,outputTokensToday=0;
  bool outputTokensKnown=false,outputTokensTodayKnown=false,fresh=false;
  uint32_t receivedAt=0,epoch=0,revision=0;
  Prompt prompt;
};
enum class ParseResult : uint8_t { snapshot, ignored, invalid, disconnected };
class ClaudeLiveProto {
 public:
  static constexpr size_t maxLine=4095;
  static constexpr uint32_t leaseMs=30000,fragmentMs=5000;
  void connect() {
    clear_line(); connected_=true;
    const uint32_t next=data_.epoch+1;
    data_=ClaudeLiveSnapshot{}; data_.epoch=next;
  }
  void disconnect() { connected_=false; clear_line(); invalidate(); }
  const ClaudeLiveSnapshot& snapshot() const { return data_; }
  bool connected() const { return connected_; }
  uint32_t errors() const { return errors_; }
  void tick(uint32_t now) {
    if (data_.fresh && now-data_.receivedAt>=leaseMs) invalidate();
    if (length_ && now-lineBegan_>=fragmentMs) { clear_line(); dropping_=true; invalid(); }
  }
  ParseResult feed(uint8_t byte,uint32_t now) {
    tick(now);
    if (!connected_) return ParseResult::disconnected;
    if (dropping_) { if (byte=='\n') clear_line(); return ParseResult::ignored; }
    if (byte=='\n') {
      if (!length_) return ParseResult::ignored;
      const auto result=parse(reinterpret_cast<const uint8_t*>(line_),length_,now);
      clear_line(); return result;
    }
    if (length_==maxLine) { clear_line(); dropping_=true; return invalid(); }
    if (!length_) lineBegan_=now;
    line_[length_++]=static_cast<char>(byte);
    return ParseResult::ignored;
  }
  ParseResult parse(const uint8_t* bytes,size_t size,uint32_t now) {
    tick(now);
    if (!connected_) return ParseResult::disconnected;
    if (!serialization::strict_object(bytes,size,maxLine)) return invalid();
    // Do not retain transcript, summary, owner, turn content or folder data in the document.
    JsonDocument filter;
    for (const char* key:{"total","running","waiting","tokens","tokens_today","evt","cmd","time","ack"})
      filter[key]=true;
    filter["prompt"]=true;
    JsonDocument document;
    if (deserializeJson(document,bytes,size,DeserializationOption::Filter(filter))) return invalid();
    bool counts=false;
    for (JsonPairConst item:document.as<JsonObjectConst>())
      if (item.key()=="total" || item.key()=="running" || item.key()=="waiting") counts=true;
    if (!counts) {
      if (!document["prompt"].isNull()) return invalid();
      // Only recognized non-snapshot forms are ignored. They never extend snapshot freshness.
      if (document["evt"]=="turn" || document["cmd"].is<const char*>() ||
          document["time"].is<JsonArrayConst>() || document["ack"].is<const char*>()) return ParseResult::ignored;
      return invalid();
    }
    if (!document["evt"].isNull() || !document["cmd"].isNull() || !document["ack"].isNull() ||
        !document["time"].isNull()) return invalid();
    ClaudeLiveSnapshot next;
    next.epoch=data_.epoch; next.revision=data_.revision;
    if (!count(document["total"],next.total) || !count(document["running"],next.running) ||
        !count(document["waiting"],next.waiting) || next.running+next.waiting>next.total) return invalid();
    if (!tokens(document["tokens"],next.outputTokens,next.outputTokensKnown) ||
        !tokens(document["tokens_today"],next.outputTokensToday,next.outputTokensTodayKnown)) return invalid();
    const auto prompt=document["prompt"];
    if (!prompt.isNull()) {
      if (!prompt.is<JsonObjectConst>() || prompt.size()!=3 || !next.waiting ||
          !copy(prompt["id"],next.prompt.id,sizeof(next.prompt.id),true) ||
          !copy(prompt["tool"],next.prompt.tool,sizeof(next.prompt.tool)) ||
          !copy(prompt["hint"],next.prompt.hint,sizeof(next.prompt.hint),false,true,true)) return invalid();
      next.prompt.present=true;
      next.prompt.displaySupported=display_text(next.prompt.tool) && display_text(next.prompt.hint);
    }
    if (!next.prompt.equals(data_.prompt)) ++next.revision;
    next.fresh=true; next.receivedAt=now;
    data_=next; return ParseResult::snapshot;
  }
 private:
  ClaudeLiveSnapshot data_;
  char line_[maxLine]{};
  size_t length_=0;
  uint32_t lineBegan_=0,errors_=0;
  bool connected_=false,dropping_=false;
  void clear_line() { memset(line_,0,sizeof(line_)); length_=0; dropping_=false; }
  void invalidate() {
    if (data_.fresh || data_.prompt.present) ++data_.revision;
    data_.fresh=false; data_.prompt=Prompt{};
  }
  ParseResult invalid() { invalidate(); if (errors_!=UINT32_MAX) ++errors_; return ParseResult::invalid; }
  static bool count(JsonVariantConst value,uint16_t& result) {
    if (!value.is<uint16_t>() || value.as<uint16_t>()>1024) return false;
    result=value.as<uint16_t>(); return true;
  }
  static bool tokens(JsonVariantConst value,uint64_t& result,bool& known) {
    if (value.isNull()) return true;
    if (!value.is<uint64_t>()) return false;
    result=value.as<uint64_t>(); known=true; return true;
  }
  static bool copy(JsonVariantConst value,char* target,size_t capacity,bool id=false,bool empty=false,bool multiline=false) {
    if (!value.is<const char*>()) return false;
    const auto text=value.as<JsonString>(); const size_t size=text.size(); const char* source=text.c_str();
    if (!source || (!size && !empty) || size>=capacity || strlen(source)!=size) return false;
    for (size_t i=0;i<size;++i) {
      const auto ch=static_cast<uint8_t>(source[i]);
      if ((ch<32 && !(multiline && ch=='\n')) || ch==127 || (id && !((ch>='a'&&ch<='z')||(ch>='A'&&ch<='Z')||
                                      (ch>='0'&&ch<='9')||ch=='_'||ch=='-'||ch=='.'))) return false;
    }
    memcpy(target,source,size+1); return true;
  }
  static bool display_text(const char* value) {
    for (;*value;++value) if (static_cast<uint8_t>(*value)>126) return false;
    return true;
  }
};
}  // namespace live_agent
