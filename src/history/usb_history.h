#pragma once
#include "types.h"
#include <ArduinoJson.h>
#include <cstring>
#include <cmath>
#include <limits>
#include <initializer_list>
namespace history {
// Read-only history domain. Atomic bounded transaction; no permissions/provider snapshots.
class UsbHistory {
 public:
  using ProviderKnown=bool(*)(const char*);
  explicit UsbHistory(ProviderKnown known):known_(known){}
  const Snapshot& snapshot() const{return published_;}
  void poll(uint32_t now){if(pending_ && now-started_>=3000)cancel();}
  bool handle(JsonObjectConst message,uint32_t boot,uint32_t now) {
    poll(now);
    if(!text_field(message["cmd"],0,32) || !message["schema"].is<uint32_t>() ||
       (message["schema"].as<uint32_t>()!=1 && message["schema"].as<uint32_t>()!=2))return fail();
    const char* cmd=message["cmd"];
    if(!strcmp(cmd,"history_begin")) {
      if(!fields(message,{"cmd","schema","bootId","epoch","revision","enabled","error","providers","date","sampleAgeSeconds"}) || !boot || !message["bootId"].is<uint32_t>() || message["bootId"].as<uint32_t>()!=boot ||
         !message["sampleAgeSeconds"].is<uint32_t>() || message["sampleAgeSeconds"].as<uint32_t>()>120 ||
         !number(message["epoch"]) || !number(message["revision"]) || !message["enabled"].is<bool>() || !message["error"].is<bool>() ||
         !message["providers"].is<JsonArrayConst>() || message["providers"].size()>8 || !date(message["date"]))return fail();
      const uint32_t epoch=message["epoch"],revision=message["revision"];
      if(epoch==epoch_ && revision<=sequence_)return fail();
      cancel();epoch_=epoch;sequence_=revision;schema_=message["schema"];staging_={};staging_.fresh=true;
      ageMs_=message["sampleAgeSeconds"].as<uint32_t>()*1000;
      staging_.enabled=message["enabled"];staging_.error=message["error"];strcpy(staging_.date,message["date"]);
      staging_.count=message["providers"].size();
      for(unsigned i=0;i<staging_.count;++i) {
        auto value=message["providers"][i];
        if(!text_field(value,0,15) || !known_ || !known_(value))return fail();
        for(unsigned j=0;j<i;++j)if(!strcmp(staging_.providers[j].key,value))return fail();
        strcpy(staging_.providers[i].key,value);
      }
      if(!staging_.enabled && staging_.count)return fail();
      if(!staging_.count){publish(now);return true;}
      started_=now;pending_=true;return true;
    }
    const bool shape=message["schema"].as<uint32_t>()==2?
      fields(message,{"cmd","schema","epoch","revision","index","today","daily","hourly","quota","agents"}):
      fields(message,{"cmd","schema","epoch","revision","index","today","daily","hourly","quota"});
    if(strcmp(cmd,"history_provider") || !shape || !pending_ || message["schema"].as<uint32_t>()!=schema_ || !number(message["epoch"]) || !number(message["revision"]) ||
       message["epoch"].as<uint32_t>()!=epoch_ || message["revision"].as<uint32_t>()!=sequence_ || !message["index"].is<uint32_t>())return fail();
    const uint32_t index=message["index"];
    if(index>=staging_.count || (received_&(1u<<index)))return fail();
    auto& provider=staging_.providers[index];
    if(schema_==2) {
      const auto agents=message["agents"];
      if(!agents.is<JsonObjectConst>() || !fields(agents.as<JsonObjectConst>(),{"sessions","activeSeconds","completedTurns","failedTurns"}))return fail();
      unsigned i=0;uint32_t* values[]={&provider.sessions,&provider.activeSeconds,&provider.completedTurns,&provider.failedTurns};
      for(const char* key:{"sessions","activeSeconds","completedTurns","failedTurns"}) {
        const auto value=agents[key];
        if(!value.isNull()) {
          if(!value.is<uint32_t>() || value.as<uint32_t>()>(i==1?100800u:50000u))return fail();
          *values[i]=value;provider.agentKnown|=1u<<i;
        }
        ++i;
      }
    }
    if(!series(message["daily"],provider.daily,provider.dailyKnown) || !series(message["hourly"],provider.hourly,provider.hourlyKnown))return fail();
    const auto today=message["today"];
    if(today.isNull()!=!(provider.dailyKnown&(1u<<6)) || (!today.isNull() && (!count(today) || today.as<uint64_t>()!=provider.daily[6])))return fail();
    const auto quota=message["quota"];
    if(!quota.isNull()) {
      if(!quota.is<JsonObjectConst>() || !fields(quota.as<JsonObjectConst>(),{"windowMinutes","ageMinutes","usedPercent","changePercent"}) || !quota["windowMinutes"].is<uint32_t>() || quota["windowMinutes"].as<uint32_t>()>525600 ||
         !quota["ageMinutes"].is<uint32_t>() || quota["ageMinutes"].as<uint32_t>()>10080 || !percent(quota["usedPercent"],0,100) ||
         (!quota["changePercent"].isNull() && !percent(quota["changePercent"],0,100)))return fail();
      provider.quotaKnown=true;provider.windowMinutes=quota["windowMinutes"];provider.quotaAgeMinutes=quota["ageMinutes"];
      provider.usedPercent=quota["usedPercent"];provider.changeKnown=!quota["changePercent"].isNull();
      if(provider.changeKnown)provider.changePercent=quota["changePercent"];
    }
    if(staging_.error && (provider.dailyKnown || provider.hourlyKnown || provider.quotaKnown || provider.agentKnown))return fail();
    received_|=1u<<index;
    if(received_==((1u<<staging_.count)-1))publish(now);
    return true;
  }
 private:
  static bool fields(JsonObjectConst object,std::initializer_list<const char*> allowed) {
    if(object.size()!=allowed.size())return false;
    for(JsonPairConst pair:object) {
      bool found=false;for(const char* key:allowed)if(!strcmp(pair.key().c_str(),key)){found=true;break;}
      if(!found)return false;
    }
    return true;
  }
  static bool text_field(JsonVariantConst value,size_t exact=0,size_t maximum=32) {
    if(!value.is<const char*>())return false;
    const auto text=value.as<JsonString>();const size_t length=text.size();
    if(!length || length>maximum || (exact && length!=exact))return false;
    for(size_t i=0;i<length;++i)if(!text.c_str()[i])return false;
    return true;
  }
  static bool number(JsonVariantConst value){return value.is<uint32_t>() && value.as<uint32_t>()>0;}
  static bool count(JsonVariantConst value){return value.is<uint64_t>() && value.as<uint64_t>()<=INT64_MAX;}
  static bool percent(JsonVariantConst value,float low,float high) {
    return !value.is<bool>() && (value.is<double>() || value.is<int64_t>()) && std::isfinite(value.as<double>()) && value.as<double>()>=low && value.as<double>()<=high;
  }
  template<size_t N> static bool series(JsonVariantConst value,uint64_t (&output)[N],uint32_t& mask) {
    if(!value.is<JsonArrayConst>() || value.size()!=N)return false;
    for(unsigned i=0;i<N;++i)if(!value[i].isNull()) {
      if(!count(value[i]))return false;
      output[i]=value[i];mask|=1u<<i;
    }
    return true;
  }
  static bool date(JsonVariantConst value) {
    if(!text_field(value,10))return false;
    const char* text=value;
    for(unsigned i=0;i<10;++i)if(i==4 || i==7){if(text[i]!='-')return false;}else if(text[i]<'0' || text[i]>'9')return false;
    const unsigned year=(text[0]-'0')*1000+(text[1]-'0')*100+(text[2]-'0')*10+text[3]-'0';
    const unsigned month=(text[5]-'0')*10+text[6]-'0',day=(text[8]-'0')*10+text[9]-'0';
    static constexpr unsigned lengths[]={31,28,31,30,31,30,31,31,30,31,30,31};
    return year>=1970 && month>=1 && month<=12 && day>=1 && day<=lengths[month-1]+(month==2 && year%4==0 && (year%100!=0 || year%400==0));
  }
  bool fail(){cancel();return false;}
  void cancel(){pending_=false;received_=0;staging_={};}
  void publish(uint32_t now){staging_.receivedAt=now-ageMs_;staging_.revision=published_.revision+1;published_=staging_;cancel();}
  ProviderKnown known_;Snapshot published_,staging_;
  bool pending_=false;uint32_t started_=0,received_=0,epoch_=0,sequence_=0,ageMs_=0,schema_=1;
};
}
