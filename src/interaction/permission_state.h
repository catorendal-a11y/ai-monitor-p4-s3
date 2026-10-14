#pragma once
#include "types.h"

namespace interaction {
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
  void sync(const InteractionSnapshot& snapshot,bool connected,bool optedIn,bool trustedChannel,uint32_t now) {
    if (!connected || !optedIn || !trustedChannel) { cancel(); return; }
    if (!snapshot.fresh || !snapshot.leaseMs || snapshot.leaseMs>lease_ms || now-snapshot.receivedAt>=snapshot.leaseMs) {
      if (state_!=PermissionState::NONE) state_=PermissionState::EXPIRED;
      return;
    }
    if (!snapshot.request.present) { cancel(); return; }
    if (!snapshot.request.displaySupported) { state_=PermissionState::ERROR; return; }
    if (snapshot.epoch!=epoch_ || snapshot.revision!=revision_ || !snapshot.request.equals(prompt_)) {
      epoch_=snapshot.epoch; revision_=snapshot.revision;
      prompt_=snapshot.request;
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
  void delivery_failed() {
    if (state_==PermissionState::SENT || state_==PermissionState::DENIED)state_=PermissionState::ERROR;
  }
  Decision approve(const InteractionSnapshot& snapshot,bool connected,bool optedIn,bool trustedChannel,uint32_t now) {
    const auto previous=state_;
    sync(snapshot,connected,optedIn,trustedChannel,now);
    if (previous!=PermissionState::HOLDING || state_!=PermissionState::HOLDING || now-holdStarted_<holdMs)
      return Decision::none;
    state_=PermissionState::SENT; return Decision::once;
  }
  Decision deny(const InteractionSnapshot& snapshot,bool connected,bool optedIn,bool trustedChannel,uint32_t now) {
    sync(snapshot,connected,optedIn,trustedChannel,now);
    if (state_!=PermissionState::DISPLAYED && state_!=PermissionState::HOLDING) return Decision::none;
    state_=PermissionState::DENIED; return Decision::deny;
  }
  // Only an adapter with a documented, correlated acknowledgement may call this.
  // Disappearance of a request is never an acknowledgement.
  bool acknowledge(uint32_t epoch,uint32_t revision,const char* id,bool accepted) {
    if (!id || epoch!=epoch_ || revision!=revision_ || strcmp(id,prompt_.id) ||
        (state_!=PermissionState::SENT && state_!=PermissionState::DENIED)) return false;
    state_=accepted ? PermissionState::ACKNOWLEDGED : PermissionState::ERROR; return true;
  }
 private:
  PermissionState state_=PermissionState::NONE;
  uint32_t epoch_=0,revision_=0,holdStarted_=0;
  PermissionRequest prompt_;
};
}  // namespace interaction
