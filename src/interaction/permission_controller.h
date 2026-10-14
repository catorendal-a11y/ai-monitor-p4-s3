#pragma once
#include "permission_state.h"

namespace interaction {
// Trusted local properties. No wire JSON may create or update this context.
struct PermissionContext {
  bool connected=false,optedIn=false,trustedChannel=false,visible=false,awake=false,demo=false;
  bool eligible() const { return connected && optedIn && trustedChannel && visible && awake && !demo; }
};
struct PermissionEnvelope {
  Decision decision=Decision::none;
  uint32_t epoch=0,revision=0;
  PermissionRequest prompt;
};
class PermissionController {
 public:
  void update(const InteractionSnapshot& snapshot,const PermissionContext& context,uint32_t now) {
    snapshot_=snapshot;context_=context;
    const auto previous=machine_.state();
    machine_.sync(snapshot,context.connected && context.visible && context.awake && !context.demo,
                  context.optedIn,context.trustedChannel,now);
    if (machine_.state()!=PermissionState::HOLDING)down_=false;
    if (pending_.decision!=Decision::none && !valid(pending_,snapshot,context,now))pending_={};
    if (handed_.decision!=Decision::none && !valid(handed_,snapshot,context,now))handed_={};
    if (machine_.state()==PermissionState::RECEIVED && previous!=PermissionState::RECEIVED)detailsVisible_=false;
    if (!context.eligible()) { detailsVisible_=false;down_=false;pending_={};handed_={}; }
  }
  bool displayed(bool complete) {
    detailsVisible_=complete;
    if (!complete) {
      release();
      if (queued() || handed_.decision!=Decision::none) { pending_={};handed_={};machine_.cancel(); }
      return false;
    }
    return machine_.displayed(snapshot_.epoch,snapshot_.revision,true);
  }
  bool press(uint32_t now) {
    machine_.sync(snapshot_,context_.connected && context_.visible && context_.awake && !context_.demo,
        context_.optedIn,context_.trustedChannel,now);
    if (!detailsVisible_ || !context_.eligible() || !machine_.begin_hold(now))return false;
    down_=true;pressedAt_=now;return true;
  }
  // Call only for a fresh, successful pointer sample inside the same held button.
  void pressing(uint32_t now,bool inside,bool validPointer=true) {
    if (!inside || !validPointer) { release();return; }
    if (!down_ || !detailsVisible_)return;
    const auto result=machine_.approve(snapshot_,context_.connected && context_.visible && context_.awake && !context_.demo,
        context_.optedIn,context_.trustedChannel,now);
    if (result==Decision::once) { queue(result);down_=false; }
    if (machine_.state()!=PermissionState::HOLDING)down_=false;
  }
  void release() { down_=false;machine_.cancel_gesture(); }
  void deny(uint32_t now) {
    if (!context_.eligible() || !detailsVisible_)return;
    const auto result=machine_.deny(snapshot_,true,true,true,now);
    if (result==Decision::deny) { queue(result);down_=false; }
  }
  void hide() { context_.visible=false;detailsVisible_=false;down_=false;pending_={};handed_={};machine_.cancel(); }
  PermissionEnvelope take(const InteractionSnapshot& current,const PermissionContext& context,uint32_t now) {
    const auto candidate=pending_;pending_={}; // Consume once, including failed/ambiguous delivery.
    if (!valid(candidate,current,context,now)) { if(candidate.decision!=Decision::none)machine_.cancel();return {}; }
    handed_=candidate;
    return candidate;
  }
  // UI-owner final gate, immediately before TX. A prepared queue envelope is not authorization to send.
  bool commit(const PermissionEnvelope& candidate,const InteractionSnapshot& current,
              const PermissionContext& context,uint32_t now) {
    const auto issued=handed_;handed_={}; // Consume on success AND failure; no retry of ambiguous delivery.
    const bool same=issued.decision!=Decision::none && candidate.decision==issued.decision &&
        candidate.epoch==issued.epoch && candidate.revision==issued.revision && candidate.prompt.equals(issued.prompt);
    const bool expectedState=(candidate.decision==Decision::once && state()==PermissionState::SENT) ||
        (candidate.decision==Decision::deny && state()==PermissionState::DENIED);
    if(!same || !expectedState || !detailsVisible_ || !context_.eligible() || !valid(candidate,current,context,now)) {
      if(issued.decision!=Decision::none)machine_.cancel();
      return false;
    }
    return true;
  }
  void delivery_failed() { pending_={};handed_={};machine_.delivery_failed(); }
  PermissionState state() const { return machine_.state(); }
  const InteractionSnapshot& snapshot() const { return snapshot_; }
  bool queued() const { return pending_.decision!=Decision::none; }
  uint32_t progress(uint32_t now) const {
    if (!down_)return 0;
    const uint32_t elapsed=now-pressedAt_;
    return elapsed>=PermissionMachine::holdMs?100:elapsed*100/PermissionMachine::holdMs;
  }
  static bool valid(const PermissionEnvelope& value,const InteractionSnapshot& current,
                    const PermissionContext& context,uint32_t now) {
    return (value.decision==Decision::once || value.decision==Decision::deny) && context.eligible() && current.fresh &&
        current.leaseMs>0 && current.leaseMs<=lease_ms && now-current.receivedAt<current.leaseMs && current.request.present && current.request.displaySupported &&
        current.epoch==value.epoch && current.revision==value.revision && current.request.equals(value.prompt);
  }
 private:
  PermissionMachine machine_;
  InteractionSnapshot snapshot_;
  PermissionContext context_;
  PermissionEnvelope pending_,handed_;
  bool down_=false,detailsVisible_=false;
  uint32_t pressedAt_=0;
  void queue(Decision decision) { pending_={decision,snapshot_.epoch,snapshot_.revision,snapshot_.request}; }
};
}
