#pragma once
#include <algorithm>
#include <cstdio>
#include <cstring>
#include "ai_monitor/ai_monitor.h"

// Bounded, per-window acknowledgements. Only fresh successful measurements alert.
class QuotaNotifications {
 public:
  struct Alert {
    char provider[16] = {}, title[36] = {};
    uint32_t window = 0;
    float remaining = 0;
    uint8_t severity = 0;  // 1 = low, 2 = critical
  };
  template<typename Threshold>
  void update(const aim::Snapshot& snapshot, uint32_t now, Threshold threshold) {
    for (auto& state : states_) {
      state.fresh = false;
      if (state.used && !present(snapshot, state.alert)) state = State{};
    }
    if (!snapshot.hostPresent) return;
    for (size_t v = 0; v < aim::kMaxViews; ++v) {
      if (snapshot.viewsConfigured && v >= snapshot.viewCount) continue;
      const auto& view = snapshot.views[v];
      if (!view.valid || !view.hasUsage || view.notice || view.fetching || now - view.quotaReceivedMs >= 300000u) continue;
      for (size_t r = 0; r < view.rowCount; ++r) {
        const auto& row = view.rows[r];
        if (!row.valid) continue;
        State* state = find(view.providerKey, row.title, row.windowMinutes);
        if (!state) for (auto& candidate : states_) if (!candidate.used) { state = &candidate; break; }
        if (!state) continue;
        if (!state->used) {
          state->used = true;
          snprintf(state->alert.provider, sizeof(state->alert.provider), "%s", view.providerKey);
          snprintf(state->alert.title, sizeof(state->alert.title), "%s", row.title);
          state->alert.window = row.windowMinutes;
        }
        const uint8_t warning = threshold(view.providerKey, row);
        if (state->warning != warning) { state->warning = warning; state->acknowledged = 0; }
        const uint8_t critical = std::min<uint8_t>(10, warning);
        const float remaining = view.showsRemaining ? row.usedPercent : 100.0f - row.usedPercent;
        // Two percentage points of recovery prevent repeated alerts near a boundary.
        if (remaining > warning + 2) state->acknowledged &= ~3u;
        else if (remaining > critical + 2) state->acknowledged &= ~2u;
        state->alert.remaining = remaining;
        state->alert.severity = remaining <= critical && !(state->acknowledged & 2) ? 2 :
                                (remaining <= warning && !(state->acknowledged & 1) ? 1 : 0);
        state->fresh = true;
      }
    }
  }
  const Alert* current() const {
    const Alert* selected = nullptr;
    for (const auto& state : states_) {
      if (!state.used || !state.fresh || !state.alert.severity) continue;
      if (!selected || state.alert.severity > selected->severity ||
          (state.alert.severity == selected->severity && state.alert.remaining < selected->remaining)) selected = &state.alert;
    }
    return selected;
  }
  unsigned count() const {
    unsigned count = 0;
    for (const auto& state : states_) if (state.used && state.fresh && state.alert.severity) ++count;
    return count;
  }
  void acknowledge(const Alert& shown) {
    auto* state = find(shown.provider, shown.title, shown.window);
    if (!state) return;
    state->acknowledged |= shown.severity == 2 ? 3u : 1u;
    state->alert.severity = 0;
  }
 private:
  struct State {
    Alert alert;
    uint8_t acknowledged = 0, warning = 0;
    bool used = false, fresh = false;
  } states_[aim::kMaxViews * aim::kMaxRows];
  State* find(const char* provider, const char* title, uint32_t window) {
    for (auto& state : states_) if (state.used && state.alert.window == window &&
        strcmp(state.alert.provider, provider) == 0 && strcmp(state.alert.title, title) == 0) return &state;
    return nullptr;
  }
  static bool present(const aim::Snapshot& snapshot, const Alert& alert) {
    for (size_t v = 0; v < aim::kMaxViews; ++v) {
      if (snapshot.viewsConfigured && v >= snapshot.viewCount) continue;
      const auto& view = snapshot.views[v];
      const char* provider = snapshot.viewsConfigured ? snapshot.viewKeys[v] : view.providerKey;
      if (strcmp(provider, alert.provider) != 0) continue;
      if (!view.hasUsage) return true;  // preserve acknowledgement during reconnect
      for (size_t r = 0; r < view.rowCount; ++r) if (view.rows[r].valid && view.rows[r].windowMinutes == alert.window &&
          strcmp(view.rows[r].title, alert.title) == 0) return true;
    }
    return false;
  }
};
