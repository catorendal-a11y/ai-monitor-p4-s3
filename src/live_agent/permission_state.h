#pragma once
#include "claude_live_proto.h"

namespace live_agent {
enum class PermissionState : uint8_t { NONE, RECEIVED, DISPLAYED, HOLDING, SENT, ACKNOWLEDGED,
                                       DENIED, EXPIRED, CANCELLED, ERROR };
enum class Decision : uint8_t { none, once, deny };
// UI task owns this state. Security/opt-in come from trusted local transport/settings, never JSON.
// The adapter must recheck those properties immediately before enqueueing a returned decision.
// A returned decision is consumed once; failure/ambiguous delivery must not trigger a retry.
class PermissionMachine {
 public:
  static constexpr uint32_t holdMs=1800;
  PermissionState state() const { return state_; }
  uint32_t epoch() const { return epoch_; }
  uint32_t revision() const { return revision_; }
  const char* request_id() const { return prompt_.id; }
  void sync(const ClaudeLiveSnapshot& snapshot,bool connected,bool optIn,bool secure,uint32_t now) {
    if (!connected || !optIn || !secure) { cancel(); return; }
    if (!snapshot.fresh || now-snapshot.receivedAt>=ClaudeLiveProto::leaseMs) {
      if (state_!=PermissionState::NONE) state_=PermissionState::EXPIRED;
      return;
    }
    if (!snapshot.prompt.present) { cancel(); return; }
    if (!snapshot.prompt.displaySupported) { state_=PermissionState::ERROR; return; }
    if (snapshot.epoch!=epoch_ || snapshot.revision!=revision_ || !snapshot.prompt.equals(prompt_)) {
      epoch_=snapshot.epoch; revision_=snapshot.revision;
      prompt_=snapshot.prompt;
      holdStarted_=0; state_=PermissionState::RECEIVED;
    }
  }
  bool displayed(uint32_t epoch,uint32_t revision,bool completeDetailsVisible) {
    if (!completeDetailsVisible || state_!=PermissionState::RECEIVED || epoch!=epoch_ || revision!=revision_) return false;
    state_=PermissionState::DISPLAYED; return true;
  }
  bool begin_hold(uint32_t now) {
    if (state_!=PermissionState::DISPLAYED) return false;
    holdStarted_=now; state_=PermissionState::HOLDING; return true;
  }
  void cancel_gesture() { if (state_==PermissionState::HOLDING) state_=PermissionState::DISPLAYED; }
  void cancel() { if (state_!=PermissionState::NONE) state_=PermissionState::CANCELLED; }
  Decision approve(const ClaudeLiveSnapshot& snapshot,bool connected,bool optIn,bool secure,uint32_t now) {
    const auto previous=state_;
    sync(snapshot,connected,optIn,secure,now);
    if (previous!=PermissionState::HOLDING || state_!=PermissionState::HOLDING || now-holdStarted_<holdMs)
      return Decision::none;
    state_=PermissionState::SENT; return Decision::once;
  }
  Decision deny(const ClaudeLiveSnapshot& snapshot,bool connected,bool optIn,bool secure,uint32_t now) {
    sync(snapshot,connected,optIn,secure,now);
    if (state_!=PermissionState::DISPLAYED && state_!=PermissionState::HOLDING) return Decision::none;
    state_=PermissionState::DENIED; return Decision::deny;
  }
  // Only a future adapter with a documented, correlated acknowledgement may call this.
  // The current Desktop reference does not define permission ACKs; absence of prompt is not an ACK.
  bool acknowledge(uint32_t epoch,uint32_t revision,const char* id,bool accepted) {
    if (!id || epoch!=epoch_ || revision!=revision_ || strcmp(id,prompt_.id) ||
        (state_!=PermissionState::SENT && state_!=PermissionState::DENIED)) return false;
    state_=accepted ? PermissionState::ACKNOWLEDGED : PermissionState::ERROR; return true;
  }
 private:
  PermissionState state_=PermissionState::NONE;
  uint32_t epoch_=0,revision_=0,holdStarted_=0;
  Prompt prompt_;
};
}  // namespace live_agent
