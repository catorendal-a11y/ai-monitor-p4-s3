#pragma once
#include <cstdint>
#include <cstring>
#include "live_agent/activity_types.h"

// An agent that has started waiting for the user. Pure policy for the UI task: no LVGL, bounded to
// the eight listed sessions, driven only by the read-only live metadata copy. Only a fresh feed
// and a fresh event count: an old event is not a request, and nothing is inferred from counters.
class AgentAlerts {
 public:
  struct Alert {
    char provider[13] = {}, id[65] = {}, label[16] = {};
    bool hasLabel = false;
    uint32_t sinceMs = 0;  // when this device first saw it waiting
  };
  void update(const live_agent::UsbLiveSnapshot& snapshot, uint32_t now) {
    for (auto& state : states_) state.seen = false;
    const bool feed = snapshot.fresh && snapshot.count <= 8 && now - snapshot.receivedAt < live_agent::activity_lease_ms;
    for (unsigned i = 0; feed && i < snapshot.count; ++i) {
      const auto& entry = snapshot.agents[i];
      if (entry.state != agent::State::WAITING && entry.state != agent::State::NEEDS_ATTENTION) continue;
      if (live_agent::observed_age_ms(snapshot, entry, now) >= live_agent::activity_lease_ms) continue;
      State* state = find(entry.provider, entry.id);
      if (!state) {
        for (auto& candidate : states_) if (!candidate.used) { state = &candidate; break; }
        if (!state) continue;
        *state = State{};
        state->used = true;
        state->serial = ++serial_;
        state->alert.sinceMs = now;
        memcpy(state->alert.provider, entry.provider, sizeof(state->alert.provider));
        memcpy(state->alert.id, entry.id, sizeof(state->alert.id));
        arrived_ = true;
      }
      state->seen = true;
      state->alert.hasLabel = entry.hasLabel;
      memcpy(state->alert.label, entry.label, sizeof(state->alert.label));
    }
    // An agent that stopped waiting (or left the feed) forgets its acknowledgement: the next request is new.
    for (auto& state : states_) if (state.used && !state.seen) state = State{};
  }
  // The request that has waited longest and has not been dismissed.
  const Alert* current() const {
    const State* best = nullptr;
    for (const auto& state : states_)
      if (state.used && !state.acknowledged && (!best || state.serial < best->serial)) best = &state;
    return best ? &best->alert : nullptr;
  }
  unsigned count() const {
    unsigned number = 0;
    for (const auto& state : states_) if (state.used && !state.acknowledged) ++number;
    return number;
  }
  void acknowledge(const Alert& shown) {
    if (auto* state = find(shown.provider, shown.id)) state->acknowledged = true;
  }
  // True once after a new request appeared, so the screen wakes once per request.
  bool take_new() {
    const bool value = arrived_;
    arrived_ = false;
    return value;
  }
 private:
  struct State {
    Alert alert;
    uint32_t serial = 0;
    bool used = false, seen = false, acknowledged = false;
  } states_[8];
  uint32_t serial_ = 0;
  bool arrived_ = false;
  State* find(const char* provider, const char* id) {
    for (auto& state : states_)
      if (state.used && !strcmp(state.alert.provider, provider) && !strcmp(state.alert.id, id)) return &state;
    return nullptr;
  }
};
