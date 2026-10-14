#pragma once
#include "permission_controller.h"
namespace interaction {
// Bounded UI-to-serial handoff. Call under an adapter-owned lock when crossing tasks.
// UI commits are earned by PermissionView/Controller, never by a transport message.
class PermissionDelivery {
 public:
  using Commit=bool(*)(void*,const PermissionEnvelope&,const InteractionSnapshot&,
                      const PermissionContext&,uint32_t);
  static constexpr uint32_t uiFreshMs=100;
  void update_local(const InteractionSnapshot& value,const PermissionContext& context,uint32_t now) {
    if(!context.eligible() || !value.fresh || !value.request.present || !value.request.displaySupported ||
       !value.leaseMs || value.leaseMs>lease_ms || uint32_t(now-value.receivedAt)>=value.leaseMs) {
      cancel();return;
    }
    local_=value;context_=context;observedAt_=now;observed_=true;
    if(pending_.decision!=Decision::none && !PermissionController::valid(pending_,value,context,now))cancel();
  }
  bool offer(const PermissionEnvelope& value,const InteractionSnapshot& current,
             const PermissionContext& context,uint32_t now,Commit commit,void* owner) {
    if(pending_.decision!=Decision::none || !commit || !owner ||
       !eligible(value,current,context,now) || !commit(owner,value,current,context,now))return false;
    pending_=value;
    return true;
  }
  PermissionEnvelope take(const InteractionSnapshot& current,const PermissionContext& context,uint32_t now) {
    const auto value=pending_;pending_={}; // Consume even when final authority changed; never retry.
    return eligible(value,current,context,now)?value:PermissionEnvelope{};
  }
  void cancel() { pending_={};observed_=false;local_={};context_={};observedAt_=0; }
  bool queued()const{return pending_.decision!=Decision::none;}
 private:
  InteractionSnapshot local_;
  PermissionContext context_;
  PermissionEnvelope pending_;
  uint32_t observedAt_=0;
  bool observed_=false;
  bool eligible(const PermissionEnvelope& value,const InteractionSnapshot& current,
                const PermissionContext& context,uint32_t now)const {
    return observed_ && uint32_t(now-observedAt_)<uiFreshMs && context_.eligible() &&
      PermissionController::valid(value,local_,context_,now) &&
      PermissionController::valid(value,current,context,now);
  }
};
}
