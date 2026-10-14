#include "live_agent/usb_live.h"
#include "ai_monitor/ai_monitor_proto.h"
#include "events/center.h"
#include <cstdlib>
#include <iostream>
#include <string>
#define CHECK(x) do { if (!(x)) { std::cerr << "Failed line " << __LINE__ << '\n'; std::exit(1); } } while (0)
using live_agent::UsbLive;
static bool accept(UsbLive& core, const std::string& message, uint32_t now=100) {
  JsonDocument doc;
  CHECK(deserializeJson(doc,message)==DeserializationError::Ok);
  return core.accept(doc.as<JsonObjectConst>(),17,now);
}
static std::string batch(uint32_t epoch, uint32_t sequence=1) {
  return "{\"cmd\":\"live_state\",\"schema\":1,\"bootId\":17,\"epoch\":"+std::to_string(epoch)+
    ",\"sequence\":"+std::to_string(sequence)+",\"agents\":[{\"provider\":\"claude\",\"id\":\"opaque_1\",\"state\":\"TESTING\"}]}";
}
int main() {
  {
    events::Center center;live_agent::UsbLiveSnapshot live{};
    live.fresh=true;live.receivedAt=1000;live.epoch=1;live.revision=1;live.count=1;
    strcpy(live.agents[0].provider,"codex");strcpy(live.agents[0].id,"opaque");live.agents[0].state=agent::State::EDITING;
    center.observe(1000,true,live);CHECK(center.count()==2 && center.at(0)->type==events::Type::STARTED);
    ++live.revision;center.observe(1001,true,live);CHECK(center.count()==2);
    live.agents[0].state=agent::State::WAITING;++live.revision;center.observe(1002,true,live);
    CHECK(center.at(0)->type==events::Type::ATTENTION);
    live.agents[0].state=agent::State::ERROR;++live.revision;center.observe(1003,true,live);
    live.agents[0].state=agent::State::COMPLETED;++live.revision;center.observe(1004,true,live);
    CHECK(center.at(0)->type==events::Type::COMPLETED && center.count()==5);
    center.observe(1005,false,{});CHECK(center.at(0)->type==events::Type::DISCONNECTED && center.count()==6);
    center.mark_read();CHECK(center.unread()==0);
    for(unsigned i=0;i<50;++i)center.quota("claude",true,2000+i);
    CHECK(center.count()==32 && center.unread()==32 && center.at(32)==nullptr);
    center.expire(2050+events::Center::expiryMs);CHECK(center.count()==0);
    center.quota("claude",false,0xfffffff0u);center.expire(32);CHECK(center.count()==1);
    center.expire(events::Center::expiryMs+32);CHECK(center.count()==0);
    events::Center stale;live.agents[0].observedAgeSeconds=31;++live.revision;
    stale.observe(1000,true,live);CHECK(stale.count()==1); // Old completion is not new attention.
  }
  {
    UsbLive timing;
    CHECK(accept(timing,"{\"cmd\":\"live_open\",\"schema\":1,\"requestId\":1}"));
    auto raw=batch(timing.snapshot().epoch);
    raw.replace(raw.find("TESTING"),7,"NEEDS_ATTENTION");
    raw.insert(raw.size()-3,",\"elapsedSeconds\":123,\"observedAgeSeconds\":45");
    CHECK(accept(timing,raw));
    const auto& row=timing.snapshot().agents[0];
    CHECK(row.state==agent::State::NEEDS_ATTENTION && row.hasElapsed && row.elapsedSeconds==123 && row.observedAgeSeconds==45);
    for(const auto key:{"elapsedSeconds","observedAgeSeconds"}) {
      auto broken=raw;auto pos=broken.find(std::string("\"")+key+"\":");
      auto start=pos+strlen(key)+3;auto end=broken.find_first_of(",}",start);
      broken.replace(start,end-start,"true");
      CHECK(!accept(timing,broken));
    }
  }
  aim::ProtoCore mux;mux.boot_id=17;mux.tick=[] {return 100u;};
  const auto quotaRevision=mux.snapshot_revision();
  const auto feed=[&](const std::string& line) {for(char ch:line+"\n")mux.feed_byte(ch);};
  feed("{\"cmd\":\"live_open\",\"schema\":1,\"requestId\":7}");
  CHECK(mux.out().find("\"permissions\":false")!=std::string::npos);
  mux.clear_out();feed(batch(mux.live_snapshot().epoch));
  CHECK(mux.live_snapshot().fresh && mux.snapshot_revision()==quotaRevision);
  feed("{\"cmd\":\"get_info\"}");
  CHECK(mux.out().find("\"liveProtocol\":1")!=std::string::npos);
  CHECK(mux.out().find("\"type\":\"info\"")!=std::string::npos && mux.live_snapshot().fresh);
  const std::string quota="{\"schemaVersion\":1,\"frameId\":7,\"displayTime\":\"14:30\","
      "\"data\":[{\"provider\":\"codex\",\"viewIndex\":0,\"usage\":{\"rows\":[{\"title\":\"Session\",\"usedPercent\":25}]}}]}\n";
  feed("AIM1 "+std::to_string(quota.size())+" 7");
  for(char ch:quota)mux.feed_byte(ch);
  CHECK(mux.snapshot().frameCount==1 && mux.snapshot().views[0].rows[0].usedPercent==25);
  CHECK(mux.live_snapshot().fresh && mux.live_snapshot().count==1);
  const auto afterQuota=mux.snapshot_revision();
  feed(batch(mux.live_snapshot().epoch,2));
  CHECK(mux.snapshot_revision()==afterQuota && mux.live_snapshot().sequence==2);
  UsbLive core;
  CHECK(!accept(core,batch(1)));
  CHECK(accept(core,"{\"cmd\":\"live_open\",\"schema\":1,\"requestId\":7}"));
  const auto epoch=core.snapshot().epoch;
  CHECK(epoch && !core.snapshot().fresh);
  CHECK(accept(core,batch(epoch)) && core.snapshot().fresh && core.snapshot().count==1);
  CHECK(!accept(core,batch(epoch)) && core.snapshot().receivedAt==100);
  CHECK(!accept(core,batch(epoch),29999) && core.snapshot().receivedAt==100);
  core.poll(30100); CHECK(!core.snapshot().fresh && core.snapshot().count==0);
  CHECK(!accept(core,batch(epoch,2),30101)); // Expiry closes the session.
  CHECK(accept(core,"{\"cmd\":\"live_open\",\"schema\":1,\"requestId\":8}",30102));
  const auto next=core.snapshot().epoch; CHECK(next!=epoch);
  CHECK(!accept(core,batch(epoch,2),30103));
  CHECK(accept(core,batch(next),30104));
  auto wrong=batch(next,2); wrong.replace(wrong.find("\"bootId\":17"),11,"\"bootId\":18");
  CHECK(!accept(core,wrong,30105) && core.snapshot().fresh);
  for (const auto& bad : {"THINKIN", "thinking", "APPROVE", "UNKNOWN\\u0000x"}) {
    UsbLive states; CHECK(accept(states,"{\"cmd\":\"live_open\",\"schema\":1,\"requestId\":9}"));
    auto invalid=batch(states.snapshot().epoch); invalid.replace(invalid.find("TESTING"),7,bad);
    CHECK(!accept(states,invalid) && !states.snapshot().fresh);
    CHECK(accept(states,batch(states.snapshot().epoch)));
  }
  UsbLive strict; CHECK(accept(strict,"{\"cmd\":\"live_open\",\"schema\":1,\"requestId\":1}"));
  for (const auto& mutation : {"extra", "duplicate", "provider", "nul", "boolean", "oversized"}) {
    auto raw=batch(strict.snapshot().epoch);
    const std::string kind=mutation;
    if(kind=="extra")raw.insert(raw.size()-1,",\"permission\":true");
    if(kind=="duplicate")raw.insert(raw.size()-2,",{\"provider\":\"claude\",\"id\":\"opaque_1\",\"state\":\"DONE\"}");
    if(kind=="provider")raw.replace(raw.find("claude"),6,"unsupported");
    if(kind=="nul")raw.replace(raw.find("opaque_1"),8,"opaque\\u0000_1");
    if(kind=="boolean")raw.replace(raw.find("\"sequence\":1"),12,"\"sequence\":true");
    if(kind=="oversized")raw.replace(raw.find("opaque_1"),8,std::string(65,'x'));
    CHECK(!accept(strict,raw) && !strict.snapshot().fresh);
  }
  CHECK(accept(strict,"{\"cmd\":\"live_open\",\"schema\":1,\"requestId\":10}",0xfffffff0u));
  CHECK(accept(strict,batch(strict.snapshot().epoch),0xfffffff0u));
  strict.poll(16); CHECK(strict.snapshot().fresh);
  strict.poll(30000); CHECK(!strict.snapshot().fresh);
  UsbLive capacity;CHECK(accept(capacity,"{\"cmd\":\"live_open\",\"schema\":1,\"requestId\":1}"));
  auto all=batch(capacity.snapshot().epoch);
  const auto begin=all.find('[');
  all.erase(begin);all+='[';
  for(unsigned i=0;i<8;++i) {
    if(i)all+=',';
    all+="{\"provider\":\"codex\",\"id\":\"agent_"+std::to_string(i)+"\",\"state\":\""+live_agent::activity_names[i]+"\"}";
  }
  all+="]}";CHECK(accept(capacity,all) && capacity.snapshot().count==8);
  auto empty=batch(capacity.snapshot().epoch,2);empty.erase(empty.find('['));empty+="[]}";
  CHECK(accept(capacity,empty) && capacity.snapshot().fresh && capacity.snapshot().count==0);
  all.insert(all.size()-2,",{\"provider\":\"codex\",\"id\":\"agent_8\",\"state\":\"DONE\"}");
  all.replace(all.find("\"sequence\":1"),12,"\"sequence\":3");
  CHECK(!accept(capacity,all) && !capacity.snapshot().fresh);
  std::cout << "USB live session, strict metadata, sequence and lease tests passed\n";
}
