#include "interaction/permission_delivery.h"
#include <cassert>
#include <initializer_list>
using namespace interaction;
static bool commit(void* owner,const PermissionEnvelope& e,const InteractionSnapshot& s,
                   const PermissionContext& c,uint32_t now) {
  return static_cast<PermissionController*>(owner)->commit(e,s,c,now);
}
static InteractionSnapshot snapshot(uint32_t now) {
  InteractionSnapshot s;s.fresh=true;s.receivedAt=now;s.epoch=1;s.revision=1;s.leaseMs=25000;
  s.request.present=s.request.displaySupported=true;
  strcpy(s.request.id,"fixture-request");strcpy(s.request.nonce,"fixture-nonce");
  strcpy(s.request.tool,"Read");strcpy(s.request.hint,"{\"file_path\":\"fixture.txt\"}");return s;
}
static PermissionContext trusted(){return {true,true,true,true,true,false};}
static PermissionEnvelope earn(PermissionController& ui,const InteractionSnapshot& s,
                               const PermissionContext& c,uint32_t now,bool deny=false) {
  ui.update(s,c,now);assert(ui.displayed(true));
  if(deny)ui.deny(now);
  else{assert(ui.press(now-1800));ui.pressing(now,true);}
  return ui.take(s,c,now);
}
int main() {
  const auto context=trusted();
  for(unsigned failure=0;failure<9;++failure) {
    auto s=snapshot(0);PermissionController ui;PermissionDelivery delivery;
    const auto e=earn(ui,s,context,2000);assert(e.decision==Decision::once);
    delivery.update_local(s,context,2000);
    assert(delivery.offer(e,s,context,2000,commit,&ui));
    assert(!delivery.offer(e,s,context,2000,commit,&ui));
    auto changed=context;uint32_t now=2001;
    if(failure==0)changed.connected=false;
    if(failure==1)changed.optedIn=false;
    if(failure==2)changed.trustedChannel=false;
    if(failure==3)changed.visible=false;
    if(failure==4)changed.awake=false;
    if(failure==5)changed.demo=true;
    if(failure==6)s.revision=2;
    if(failure==7)strcpy(s.request.id,"different-request");
    if(failure==8)now=2100;
    assert(delivery.take(s,changed,now).decision==Decision::none);
    assert(!delivery.queued());assert(delivery.take(snapshot(0),context,2001).decision==Decision::none);
  }
  for(bool deny:{false,true}) {
    auto s=snapshot(UINT32_MAX-1000);PermissionController ui;PermissionDelivery delivery;
    const auto e=earn(ui,s,context,1000,deny);
    delivery.update_local(s,context,1000);
    assert(delivery.offer(e,s,context,1000,commit,&ui));
    assert(delivery.take(s,context,1001).decision==(deny?Decision::deny:Decision::once));
    assert(delivery.take(s,context,1002).decision==Decision::none);
  }
  { // A transport-created envelope cannot replace the UI owner's earned/handed decision.
    auto s=snapshot(0);PermissionController ui;PermissionDelivery delivery;
    ui.update(s,context,100);ui.displayed(true);delivery.update_local(s,context,100);
    PermissionEnvelope forged{Decision::once,s.epoch,s.revision,s.request};
    assert(!delivery.offer(forged,s,context,100,commit,&ui));assert(!delivery.queued());
  }
  { // UI hides after committing, before the serial owner takes the envelope.
    auto s=snapshot(0);PermissionController ui;PermissionDelivery delivery;
    const auto e=earn(ui,s,context,2000);delivery.update_local(s,context,2000);
    assert(delivery.offer(e,s,context,2000,commit,&ui));
    auto hidden=context;hidden.visible=false;delivery.update_local(s,hidden,2001);
    assert(delivery.take(s,context,2002).decision==Decision::none);
  }
  { // Refreshing the visibility stamp cannot extend the underlying request deadline.
    auto s=snapshot(0);PermissionController ui;PermissionDelivery delivery;
    const auto e=earn(ui,s,context,24900);delivery.update_local(s,context,24900);
    assert(delivery.offer(e,s,context,24900,commit,&ui));
    delivery.update_local(s,context,24999);
    assert(delivery.take(s,context,25000).decision==Decision::none);
  }
}
