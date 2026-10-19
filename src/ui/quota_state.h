#pragma once
#include "ai_monitor/ai_monitor.h"

// One classification of a provider card's quota health. Callers choose the long or
// short label so the dashboard cannot describe the same state with different words.
namespace quota_state {

enum class State { Waiting, Offline, Activity, Error, Fetching, Stale, Critical, Low, Connected };

// `critical`/`low` only matter for a fresh, connected, error-free view.
inline State classify(const aim::ViewData* view, bool hostConnected, bool fresh, bool critical, bool low) {
  if (!view || !view->valid) return State::Waiting;
  if (!hostConnected) return State::Offline;
  if (view->informational) return State::Activity;
  if (view->notice) return State::Error;
  if (view->fetching) return State::Fetching;
  if (!fresh) return State::Stale;
  return critical ? State::Critical : (low ? State::Low : State::Connected);
}

// Short labels are used beside the session status, where width is limited.
inline const char* label(State state, bool shortForm) {
  switch (state) {
    case State::Waiting: return "WAITING";
    case State::Offline: return "OFFLINE";
    case State::Activity: return shortForm ? "ACTIVITY" : "ACTIVITY / SETUP";
    case State::Error: return shortForm ? "ERROR" : "ERROR - TAP";
    case State::Fetching: return shortForm ? "UPDATING" : "FETCHING";
    case State::Stale: return "STALE";
    case State::Critical: return "CRITICAL";
    case State::Low: return "LOW QUOTA";
    case State::Connected: return "CONNECTED";
  }
  return "WAITING";
}

}  // namespace quota_state
