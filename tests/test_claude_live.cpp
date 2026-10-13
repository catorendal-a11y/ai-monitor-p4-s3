#include "live_agent/claude_live_proto.h"
#include "live_agent/permission_state.h"
#include "live_agent/permission_controller.h"
#include <cstdlib>
#include <iostream>
#include <string>
#define CHECK(value) do { if (!(value)) { std::cerr<<"Failure at "<<__LINE__<<": "<<#value<<'\n'; std::exit(1); } } while(0)
using live_agent::ParseResult;
static ParseResult parse(live_agent::ClaudeLiveProto& core,const std::string& line,uint32_t now=100) {
  return core.parse(reinterpret_cast<const uint8_t*>(line.data()),line.size(),now);
}
static const char* pending="{\"total\":3,\"running\":1,\"waiting\":1,\"tokens\":123,\"tokens_today\":10,"
  "\"prompt\":{\"id\":\"req_123\",\"tool\":\"Bash\",\"hint\":\"run synthetic test\"}}";
static void permissions_require_a_fresh_displayed_exact_request_and_continuous_hold() {
  using live_agent::Decision; using live_agent::PermissionState;
  live_agent::ClaudeLiveProto core; core.connect(); CHECK(parse(core,pending)==ParseResult::snapshot);
  live_agent::PermissionMachine machine;
  machine.sync(core.snapshot(),true,true,true,100);
  CHECK(machine.state()==PermissionState::RECEIVED && !machine.begin_hold(100));
  CHECK(!machine.displayed(core.snapshot().epoch,core.snapshot().revision+1,true));
  CHECK(!machine.displayed(core.snapshot().epoch,core.snapshot().revision,false));
  CHECK(machine.displayed(core.snapshot().epoch,core.snapshot().revision,true));
  CHECK(machine.approve(core.snapshot(),true,true,true,2000)==Decision::none);
  CHECK(machine.begin_hold(100));
  CHECK(machine.approve(core.snapshot(),true,true,true,1899)==Decision::none);
  machine.cancel_gesture();
  CHECK(machine.approve(core.snapshot(),true,true,true,1900)==Decision::none);
  CHECK(machine.begin_hold(2000));
  CHECK(machine.approve(core.snapshot(),true,true,true,3800)==Decision::once);
  CHECK(machine.state()==PermissionState::SENT);
  CHECK(machine.approve(core.snapshot(),true,true,true,3801)==Decision::none);
  CHECK(!machine.acknowledge(core.snapshot().epoch+1,core.snapshot().revision,"req_123",true));
  CHECK(machine.acknowledge(core.snapshot().epoch,core.snapshot().revision,"req_123",true));
  CHECK(machine.state()==PermissionState::ACKNOWLEDGED);
  for (unsigned scenario=0;scenario<7;++scenario) {
    live_agent::PermissionMachine check;
    CHECK(parse(core,pending,100)==ParseResult::snapshot);
    check.sync(core.snapshot(),true,true,true,100);
    CHECK(check.displayed(core.snapshot().epoch,core.snapshot().revision,true) && check.begin_hold(100));
    auto changed=core.snapshot();
    if (scenario==3) ++changed.revision;
    if (scenario==4) ++changed.epoch;
    if (scenario==5) changed.receivedAt=0;
    if (scenario==6) changed.prompt.hint[0]='X';
    CHECK(check.approve(changed,scenario!=0,scenario!=1,scenario!=2,scenario==5?30000:1900)==Decision::none);
  }
  live_agent::PermissionMachine denial;
  CHECK(parse(core,pending)==ParseResult::snapshot);
  denial.sync(core.snapshot(),true,true,true,100);
  CHECK(denial.displayed(core.snapshot().epoch,core.snapshot().revision,true));
  CHECK(denial.deny(core.snapshot(),true,true,true,100)==Decision::deny);
  CHECK(denial.state()==PermissionState::DENIED && denial.deny(core.snapshot(),true,true,true,101)==Decision::none);
  live_agent::PermissionMachine rollover;
  CHECK(parse(core,pending,0xfffffff0u)==ParseResult::snapshot);
  rollover.sync(core.snapshot(),true,true,true,0xfffffff0u);
  CHECK(rollover.displayed(core.snapshot().epoch,core.snapshot().revision,true) && rollover.begin_hold(0xfffffff0u));
  CHECK(rollover.approve(core.snapshot(),true,true,true,1800)==Decision::once);
}
static void permission_ui_controller_rechecks_queue_delivery_and_gesture_cancellation() {
  using namespace live_agent;
  ClaudeLiveProto core;core.connect();CHECK(parse(core,pending)==ParseResult::snapshot);
  const PermissionContext trusted{true,true,true,true,true,false};
  for (unsigned reason=0;reason<10;++reason) {
    PermissionController controller;controller.update(core.snapshot(),trusted,100);
    CHECK(!controller.press(100));CHECK(controller.displayed(true));CHECK(controller.press(100));
    CHECK(controller.progress(1000)==50);
    controller.pressing(1899,true);CHECK(!controller.queued());
    if (reason==0) { controller.release();controller.pressing(1900,true);CHECK(!controller.queued());continue; }
    if (reason==1) { controller.pressing(1000,false);controller.pressing(1900,true);CHECK(!controller.queued());continue; }
    if (reason==2) { controller.pressing(1000,true,false);controller.pressing(1900,true);CHECK(!controller.queued());continue; }
    controller.pressing(1900,true);CHECK(controller.queued());
    auto changed=core.snapshot();auto context=trusted;
    if (reason==3)context.secure=false;
    if (reason==4)context.connected=false;
    if (reason==5)++changed.epoch;
    if (reason==6)changed.prompt.hint[0]='X';
    if (reason==7)context.demo=true;
    if (reason==8) { controller.displayed(false);CHECK(!controller.queued());continue; }
    const auto envelope=controller.take(changed,context,reason==9?30100:1900);
    CHECK(envelope.decision==Decision::none && !controller.queued());
  }
  PermissionController controller;controller.update(core.snapshot(),trusted,100);
  CHECK(controller.displayed(true) && controller.press(100));controller.pressing(1900,true);
  const auto issued=controller.take(core.snapshot(),trusted,1900);CHECK(issued.decision==Decision::once);
  CHECK(controller.take(core.snapshot(),trusted,1900).decision==Decision::none);
  CHECK(controller.commit(issued,core.snapshot(),trusted,1900));
  auto invalidDecision=issued;invalidDecision.decision=static_cast<Decision>(255);
  CHECK(!PermissionController::valid(invalidDecision,core.snapshot(),trusted,1900));
  CHECK(!controller.commit(issued,core.snapshot(),trusted,1900));
  controller.delivery_failed();CHECK(controller.state()==PermissionState::ERROR);
  PermissionController denial;denial.update(core.snapshot(),trusted,100);CHECK(denial.displayed(true));
  denial.deny(100);CHECK(denial.take(core.snapshot(),trusted,100).decision==Decision::deny);
  CHECK(denial.take(core.snapshot(),trusted,101).decision==Decision::none);
  PermissionController hide;hide.update(core.snapshot(),trusted,100);CHECK(hide.displayed(true)&&hide.press(100));
  hide.hide();hide.pressing(1900,true);CHECK(!hide.queued());
  PermissionController queued;queued.update(core.snapshot(),trusted,100);CHECK(queued.displayed(true)&&queued.press(100));
  queued.pressing(1900,true);const auto beforeHide=queued.take(core.snapshot(),trusted,1900);
  queued.hide();CHECK(!queued.commit(beforeHide,core.snapshot(),trusted,1900));
}

int main() {
  permission_ui_controller_rechecks_queue_delivery_and_gesture_cancellation();
  permissions_require_a_fresh_displayed_exact_request_and_continuous_hold();
  live_agent::ClaudeLiveProto core;
  CHECK(parse(core,pending)==ParseResult::disconnected);
  core.connect(); CHECK(parse(core,pending)==ParseResult::snapshot);
  CHECK(core.snapshot().total==3 && core.snapshot().outputTokens==123 && core.snapshot().prompt.displaySupported);
  const auto revision=core.snapshot().revision;
  CHECK(parse(core,pending,101)==ParseResult::snapshot && core.snapshot().revision==revision);
  CHECK(parse(core,"{\"evt\":\"turn\",\"role\":\"assistant\",\"content\":[{\"text\":\"private fixture\"}]}",200)==ParseResult::ignored);
  CHECK(core.snapshot().receivedAt==101);
  std::string changed=pending; changed.replace(changed.find("run synthetic test"),18,"changed details");
  CHECK(parse(core,changed)==ParseResult::snapshot && core.snapshot().revision!=revision);
  core.tick(30100); CHECK(!core.snapshot().fresh && !core.snapshot().prompt.present);
  CHECK(parse(core,pending)==ParseResult::snapshot);
  CHECK(parse(core,"{\"total\":3,\"running\":1,\"waiting\":0}")==ParseResult::snapshot);
  CHECK(!core.snapshot().prompt.present && !core.snapshot().outputTokensKnown);
  for (const char* bad:{"{\"total\":true,\"running\":0,\"waiting\":0}","{\"total\":1,\"running\":1,\"waiting\":1}",
                       "{\"total\":1,\"running\":0}","{\"total\":1025,\"running\":0,\"waiting\":0}"}) {
    CHECK(parse(core,pending)==ParseResult::snapshot);
    CHECK(parse(core,bad)==ParseResult::invalid && !core.snapshot().fresh && !core.snapshot().prompt.present);
  }
  changed=pending; changed.replace(changed.find("run synthetic test"),18,std::string(513,'x'));
  CHECK(parse(core,changed)==ParseResult::invalid);
  changed=pending; changed.replace(changed.find("run synthetic test"),18,"\\u00d8");
  CHECK(parse(core,changed)==ParseResult::snapshot && !core.snapshot().prompt.displaySupported);
  changed=pending; changed.replace(changed.find("run synthetic test"),18,"first\\nsecond");
  CHECK(parse(core,changed)==ParseResult::snapshot && core.snapshot().prompt.displaySupported);
  CHECK(std::string(core.snapshot().prompt.hint)=="first\nsecond");
  changed=pending; changed.replace(changed.find("run synthetic test"),18,"\\u0000hidden");
  CHECK(parse(core,changed)==ParseResult::invalid);
  core.disconnect(); const auto epoch=core.snapshot().epoch;
  core.connect(); CHECK(core.snapshot().epoch!=epoch && !core.snapshot().fresh && !core.snapshot().prompt.present);
  for (unsigned char ch:std::string(pending)+"\n") core.feed(ch,100);
  CHECK(core.snapshot().fresh);
  for (unsigned i=0;i<=core.maxLine;++i) core.feed('x',200);
  CHECK(!core.snapshot().fresh && !core.snapshot().prompt.present);
  core.feed('\n',200);
  for (unsigned char ch:std::string(pending)+"\n") core.feed(ch,300);
  CHECK(core.snapshot().fresh);
  core.feed('{',301); core.tick(5301);
  CHECK(!core.snapshot().fresh);
  core.feed('\n',5301);
  CHECK(parse(core,pending,0xfffffff0u)==ParseResult::snapshot);
  core.tick(16); CHECK(core.snapshot().fresh);
  core.tick(30000); CHECK(!core.snapshot().fresh);
  std::cout<<"Claude live bounded parsing, fragmentation, prompt identity and lease tests passed\n";
}
