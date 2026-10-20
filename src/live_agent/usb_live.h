#pragma once
#include <ArduinoJson.h>
#include <cstdint>
#include <cstring>
#include <limits>
#include "activity_types.h"

namespace live_agent {
// Serial-owner only. Publish value copies to other tasks. This domain carries no permissions,
// credentials, transcript, filesystem paths, tool arguments or provider commands.
class UsbLive {
 public:
  static constexpr uint32_t leaseMs=activity_lease_ms;
  const UsbLiveSnapshot& snapshot() const { return snapshot_; }
  bool accept(JsonObjectConst object,uint32_t bootId,uint32_t now) {
    poll(now);
    const auto command=object["cmd"];
    if(!command.is<const char*>())return false;
    const char* cmd=command.as<const char*>();
    if(command.as<JsonString>().size()!=strlen(cmd))return reject();
    if(!object["schema"].is<uint32_t>() || object["schema"].as<uint32_t>()!=1)return reject();
    if(!strcmp(cmd,"live_open")) {
      if(object.size()!=3 || !object["requestId"].is<uint32_t>() ||
          generation_==std::numeric_limits<uint32_t>::max())return reject();
      clear(); snapshot_.epoch=++generation_;snapshot_.sequence=0;active_=true;openedAt_=now;
      return true;
    }
    if(!object["bootId"].is<uint32_t>() || object["bootId"].as<uint32_t>()!=bootId ||
       !object["epoch"].is<uint32_t>() || object["epoch"].as<uint32_t>()!=snapshot_.epoch || !active_)return false;
    if(!strcmp(cmd,"live_close")) {
      if(object.size()!=4)return reject();
      active_=false;clear();return true;
    }
    if(strcmp(cmd,"live_state"))return reject();
    // Six base fields, plus total/selectedMask/linkedMask together when the host sends the summary.
    const bool summary=object.size()==9;
    if((object.size()!=6 && !summary) || !object["sequence"].is<uint32_t>())return reject();
    const uint32_t sequence=object["sequence"].as<uint32_t>();
    if(!sequence || sequence<=snapshot_.sequence)return false; // Never renew/replay old state.
    const auto agents=object["agents"].as<JsonArrayConst>();
    if(agents.isNull() || agents.size()>8)return reject();
    UsbLiveSnapshot next{};
    for(const auto entry:agents) {
      const auto row=entry.as<JsonObjectConst>();
      if(row.isNull() || row.size()<3 || row.size()>7)return reject();
      for(const auto field:row)if(strcmp(field.key().c_str(),"provider") && strcmp(field.key().c_str(),"id") &&
          strcmp(field.key().c_str(),"state") && strcmp(field.key().c_str(),"elapsedSeconds") &&
          strcmp(field.key().c_str(),"observedAgeSeconds") && strcmp(field.key().c_str(),"label") &&
          strcmp(field.key().c_str(),"hue"))return reject();
      auto& value=next.agents[next.count];
      if(!identifier(row["provider"],value.provider,sizeof(value.provider)) ||
         !provider(value.provider) || !identifier(row["id"],value.id,sizeof(value.id)) ||
         !row["state"].is<const char*>())return reject();
      const JsonString state=row["state"].as<JsonString>();
      bool known=false;
      for(unsigned i=0;i<sizeof(activity_names)/sizeof(*activity_names);++i) {
        if(state.size()==strlen(activity_names[i]) && !memcmp(state.c_str(),activity_names[i],state.size())) {
          value.state=static_cast<ActivityState>(i);known=true;break;
        }
      }
      if(state=="FAILED") {value.state=ActivityState::ERROR;known=true;}
      if(state=="DONE") {value.state=ActivityState::COMPLETED;known=true;}
      if(!known)return reject();
      if(row["elapsedSeconds"].isUnbound()==false) {
        if(!row["elapsedSeconds"].is<uint32_t>() || row["elapsedSeconds"].as<uint32_t>()>604800)return reject();
        value.hasElapsed=true;value.elapsedSeconds=row["elapsedSeconds"].as<uint32_t>();
      }
      if(row["observedAgeSeconds"].isUnbound()==false) {
        if(!row["observedAgeSeconds"].is<uint16_t>() || row["observedAgeSeconds"].as<uint16_t>()>900)return reject();
        value.observedAgeSeconds=row["observedAgeSeconds"].as<uint16_t>();
      }
      if(row["label"].isUnbound()==false) {
        if(!label(row["label"],value.label,sizeof(value.label)))return reject();
        value.hasLabel=true;
      }
      if(row["hue"].isUnbound()==false) {
        if(!row["hue"].is<uint8_t>() || row["hue"].as<uint8_t>()>=hue_count)return reject();
        value.hue=row["hue"].as<uint8_t>();
      }
      for(unsigned i=0;i<next.count;++i)
        if(!strcmp(value.provider,next.agents[i].provider) && !strcmp(value.id,next.agents[i].id))return reject();
      ++next.count;
    }
    if(summary) {
      for(const char* key:{"total","selectedMask","linkedMask"})if(!object[key].is<uint8_t>())return reject();
      next.total=object["total"].as<uint8_t>();
      next.selectedMask=object["selectedMask"].as<uint8_t>();
      next.linkedMask=object["linkedMask"].as<uint8_t>();
      if(next.total<next.count)return reject();   // the total includes every listed session
      next.hasSummary=true;
    }
    next.epoch=snapshot_.epoch;next.sequence=sequence;next.receivedAt=now;
    next.revision=snapshot_.revision+1;next.fresh=true;snapshot_=next;
    return true;
  }
  void poll(uint32_t now) {
    if(active_ && now-(snapshot_.fresh?snapshot_.receivedAt:openedAt_)>=leaseMs) {
      active_=false;clear();
    }
  }
 private:
  UsbLiveSnapshot snapshot_;
  uint32_t generation_=0,openedAt_=0;
  bool active_=false;
  void clear() {
    const uint32_t epoch=snapshot_.epoch,sequence=snapshot_.sequence,revision=snapshot_.revision;
    snapshot_=UsbLiveSnapshot{};snapshot_.epoch=epoch;snapshot_.sequence=sequence;snapshot_.revision=revision+1;
  }
  bool reject() { clear();return false; }
  static bool identifier(JsonVariantConst item,char* destination,size_t capacity) {
    if(!item.is<const char*>())return false;
    const JsonString text=item.as<JsonString>();
    if(!text.size() || text.size()>=capacity)return false;
    for(size_t i=0;i<text.size();++i) {
      const char ch=text.c_str()[i];
      if(!((ch>='a' && ch<='z') || (ch>='A' && ch<='Z') || (ch>='0' && ch<='9') || ch=='_' || ch=='-'))return false;
    }
    memcpy(destination,text.c_str(),text.size());destination[text.size()]=0;return true;
  }
  // Letters in words separated by single spaces ("Eager Badger"); no leading, doubled or trailing space.
  static bool label(JsonVariantConst item,char* destination,size_t capacity) {
    if(!item.is<const char*>())return false;
    const JsonString text=item.as<JsonString>();
    if(!text.size() || text.size()>=capacity)return false;
    bool afterSpace=true;
    for(size_t i=0;i<text.size();++i) {
      const char ch=text.c_str()[i];
      const bool space=ch==' ',letter=(ch>='a' && ch<='z') || (ch>='A' && ch<='Z');
      if((!letter && !space) || (space && afterSpace))return false;
      afterSpace=space;
    }
    if(afterSpace)return false;
    memcpy(destination,text.c_str(),text.size());destination[text.size()]=0;return true;
  }
  static bool provider(const char* name) {
    for(const char* candidate:{"codex","zcode","claude","gemini","copilot","cursor","antigravity","opencode"})
      if(!strcmp(candidate,name))return true;
    return false;
  }
};
}
