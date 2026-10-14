#pragma once
#include "live_agent/activity_types.h"
#include <cstring>
namespace events {
enum class Type:uint8_t { STARTED, COMPLETED, ATTENTION, ERROR, CONNECTED, DISCONNECTED, QUOTA_LOW, QUOTA_CRITICAL };
inline const char* text(Type type) {
  switch(type) {
    case Type::STARTED:return "Agent activity started";
    case Type::COMPLETED:return "Agent response completed";
    case Type::ATTENTION:return "Agent needs your attention";
    case Type::ERROR:return "Agent reported an error";
    case Type::CONNECTED:return "USB host connected";
    case Type::DISCONNECTED:return "USB host disconnected";
    case Type::QUOTA_LOW:return "Quota below warning threshold";
    case Type::QUOTA_CRITICAL:return "Quota at critical threshold";
  }
  return "Unknown event";
}
struct Entry {Type type=Type::STARTED;char source[13]{};uint32_t timestampMs=0;bool read=false;};
class Center {
 public:
  static constexpr unsigned capacity=32;
  static constexpr uint32_t expiryMs=86400000u;
  unsigned count()const{return count_;}
  unsigned unread()const {unsigned result=0;for(unsigned i=0;i<count_;++i)result+=!entries_[i].read;return result;}
  const Entry* at(unsigned newestFirst)const{return newestFirst<count_?&entries_[count_-1-newestFirst]:nullptr;}
  void mark_read(){for(unsigned i=0;i<count_;++i)entries_[i].read=true;}
  void clear(){count_=0;}
  void expire(uint32_t now) {
    unsigned kept=0;for(unsigned i=0;i<count_;++i)if(now-entries_[i].timestampMs<expiryMs)entries_[kept++]=entries_[i];count_=kept;
  }
  void quota(const char* provider,bool critical,uint32_t now) {
    push(critical?Type::QUOTA_CRITICAL:Type::QUOTA_LOW,provider,now);
  }
  void observe(uint32_t now,bool hostPresent,const live_agent::UsbLiveSnapshot& live) {
    expire(now);
    if(hostPresent!=host_) {if(hostPresent || everConnected_)push(hostPresent?Type::CONNECTED:Type::DISCONNECTED,"host",now);host_=hostPresent;everConnected_|=hostPresent;}
    if(!hostPresent || !live.fresh || now-live.receivedAt>=live_agent::activity_lease_ms || live.count>8)return;
    if(observed_ && live.epoch==epoch_ && live.revision==revision_)return;
    observed_=true;epoch_=live.epoch;revision_=live.revision;
    for(unsigned i=0;i<live.count;++i) {
      const auto& item=live.agents[i];
      if(item.observedAgeSeconds>30)continue;
      const live_agent::AgentMetadata* old=nullptr;
      for(unsigned j=0;j<previous_.count;++j)if(!strcmp(item.provider,previous_.agents[j].provider) && !strcmp(item.id,previous_.agents[j].id))old=&previous_.agents[j];
      if(old && old->state==item.state)continue;
      const uint32_t when=now-static_cast<uint32_t>(item.observedAgeSeconds)*1000u;
      switch(item.state) {
        case agent::State::WAITING:case agent::State::NEEDS_ATTENTION:push(Type::ATTENTION,item.provider,when);break;
        case agent::State::ERROR:push(Type::ERROR,item.provider,when);break;
        case agent::State::COMPLETED:push(Type::COMPLETED,item.provider,when);break;
        case agent::State::WORKING:case agent::State::THINKING:case agent::State::READING:
        case agent::State::EDITING:case agent::State::WRITING:case agent::State::SEARCHING:
        case agent::State::RUNNING:case agent::State::BUILDING:case agent::State::TESTING:
          if(!old || old->state==agent::State::IDLE || old->state==agent::State::COMPLETED || old->state==agent::State::ERROR)push(Type::STARTED,item.provider,when);
          break;
        default:break;
      }
    }
    previous_=live;
  }
 private:
  Entry entries_[capacity]{};
  unsigned count_=0;bool host_=false,everConnected_=false,observed_=false;
  uint32_t epoch_=0,revision_=0;
  live_agent::UsbLiveSnapshot previous_{};
  void push(Type type,const char* source,uint32_t now) {
    if(!source || strnlen(source,13)>12)return;
    if(count_==capacity) {for(unsigned i=1;i<capacity;++i)entries_[i-1]=entries_[i];--count_;}
    unsigned position=count_++;
    while(position && now!=entries_[position-1].timestampMs &&
          now-entries_[position-1].timestampMs>=0x80000000u) {
      entries_[position]=entries_[position-1];--position;
    }
    auto& entry=entries_[position];entry={};entry.type=type;entry.timestampMs=now;
    memcpy(entry.source,source,strlen(source)+1);
  }
};
}
