#include "history/usb_history.h"
#include <iostream>
static unsigned failures=0;
#define CHECK(x) do{if(!(x)){std::cerr<<__LINE__<<": " #x "\n";++failures;}}while(false)
static bool known(const char* key){return !strcmp(key,"codex") || !strcmp(key,"zcode");}
static JsonDocument start(uint32_t revision=1) {
  JsonDocument d;d["cmd"]="history_begin";d["schema"]=1;d["bootId"]=17;d["epoch"]=11;d["revision"]=revision;
  d["enabled"]=true;d["error"]=false;d["date"]="2026-10-14";
  d["sampleAgeSeconds"]=0;
  auto a=d["providers"].to<JsonArray>();a.add("codex");a.add("zcode");return d;
}
static JsonDocument row(unsigned index,uint32_t revision=1) {
  JsonDocument d;d["cmd"]="history_provider";d["schema"]=1;d["epoch"]=11;d["revision"]=revision;d["index"]=index;
  d["today"]=123;auto daily=d["daily"].to<JsonArray>();for(unsigned i=0;i<6;++i)daily.add(nullptr);daily.add(123);
  auto hourly=d["hourly"].to<JsonArray>();for(unsigned i=0;i<23;++i)hourly.add(nullptr);hourly.add(123);d["quota"]=nullptr;return d;
}
int main() {
  history::UsbHistory core(known);auto begin=start();auto first=row(0),second=row(1);
  CHECK(core.handle(begin.as<JsonObjectConst>(),17,100));CHECK(core.handle(first.as<JsonObjectConst>(),17,101));
  CHECK(core.snapshot().revision==0);CHECK(core.handle(second.as<JsonObjectConst>(),17,102));
  CHECK(core.snapshot().count==2 && core.snapshot().fresh && core.snapshot().enabled);
  CHECK(core.snapshot().providers[0].dailyKnown==64 && core.snapshot().providers[0].daily[6]==123);
  CHECK(core.snapshot().providers[0].hourlyKnown==(1u<<23));CHECK(!core.handle(first.as<JsonObjectConst>(),17,103));
  const auto revision=core.snapshot().revision;
  for(unsigned fault=0;fault<15;++fault) {
    auto opening=start(fault+2);CHECK(core.handle(opening.as<JsonObjectConst>(),17,200));auto value=row(0,fault+2);
    if(fault==0)value["daily"][0]=true;
    if(fault==1)value["hourly"][0]=UINT64_MAX;
    if(fault==2)value["daily"].as<JsonArray>().add(nullptr);
    if(fault==3)value["today"]=124;
    if(fault==4)value["index"]=true;
    if(fault==5)value["epoch"]=12;
    if(fault==6)value["schema"]=true;
    if(fault==7){value.remove("quota");value["transcript"]="forbidden";}
    if(fault>=8){auto q=value["quota"].to<JsonObject>();q["windowMinutes"]=300;q["usedPercent"]=20;q["changePercent"]=10;q["ageMinutes"]=1;
      if(fault==8)q["usedPercent"]=101;
      if(fault==9)q["windowMinutes"]=true;
      if(fault==10)q["changePercent"]=-1;
      if(fault==11)q["ageMinutes"]=10081;
      if(fault==12)q["usedPercent"]="20";
      if(fault==13)q["hint"]="forbidden";
      if(fault==14){q.remove("changePercent");q["unknown"]=nullptr;}}
    CHECK(!core.handle(value.as<JsonObjectConst>(),17,201));CHECK(core.snapshot().revision==revision);
  }
  for(const char* date:{"2026-02-30","2025-02-29","2026-00-01","2026-13-01","2026-10-14x"}) {
    auto bad=start(30);bad["date"]=date;CHECK(!core.handle(bad.as<JsonObjectConst>(),17,300));
  }
  auto bad=start(31);bad["providers"][1]="codex";CHECK(!core.handle(bad.as<JsonObjectConst>(),17,300));
  bad=start(32);bad["bootId"]=18;CHECK(!core.handle(bad.as<JsonObjectConst>(),17,300));
  auto reset=start(40);CHECK(core.handle(reset.as<JsonObjectConst>(),17,0xfffffff0));
  auto late=row(0,40);core.poll(3010);CHECK(!core.handle(late.as<JsonObjectConst>(),17,3011));
  auto disabled=start(41);disabled["enabled"]=false;disabled["providers"].to<JsonArray>();
  CHECK(core.handle(disabled.as<JsonObjectConst>(),17,400));CHECK(!core.snapshot().enabled && !core.snapshot().count);
  CHECK(core.snapshot().revision==revision+1);
  for(unsigned fault=0;fault<7;++fault) {
    auto begin=start(50+fault);begin["schema"]=2;CHECK(core.handle(begin.as<JsonObjectConst>(),17,500));
    auto first=row(0,50+fault);first["schema"]=2;
    auto stats=first["agents"].to<JsonObject>();stats["sessions"]=2;stats["activeSeconds"]=180;
    stats["completedTurns"]=nullptr;stats["failedTurns"]=0;
    if(fault==1)stats["sessions"]=true;
    if(fault==2)stats["activeSeconds"]=100801;
    if(fault==3)stats["failedTurns"]=-1;
    if(fault==4)stats["prompt"]="forbidden";
    if(fault==5)first["schema"]=1;
    if(fault==6)stats["completedTurns"]=50001;
    if(fault){CHECK(!core.handle(first.as<JsonObjectConst>(),17,501));continue;}
    CHECK(core.handle(first.as<JsonObjectConst>(),17,501));
    auto second=row(1,50);second["schema"]=2;auto unknown=second["agents"].to<JsonObject>();
    for(const char* key:{"sessions","activeSeconds","completedTurns","failedTurns"})unknown[key]=nullptr;
    CHECK(core.handle(second.as<JsonObjectConst>(),17,502));
    CHECK(core.snapshot().providers[0].agentKnown==11 && core.snapshot().providers[0].activeSeconds==180);
    CHECK(core.snapshot().providers[1].agentKnown==0);
  }
  if(failures)return 1;
  std::cout<<"Atomic bounded history, unknown gaps, strict fields, replay and rollback tests passed\n";
}
