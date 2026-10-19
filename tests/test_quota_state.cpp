#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "ui/quota_state.h"

using quota_state::State;
static void expect(bool ok, const char* what) {
  if (!ok) { std::fprintf(stderr, "FAILED: %s\n", what); std::exit(1); }
}

int main() {
  aim::ViewData view{};
  view.valid = true;
  expect(quota_state::classify(nullptr, true, true, false, false) == State::Waiting, "null view waits");
  aim::ViewData invalid{};
  expect(quota_state::classify(&invalid, true, true, false, false) == State::Waiting, "invalid view waits");
  expect(quota_state::classify(&view, false, true, true, true) == State::Offline, "offline outranks quota");
  view.informational = true; view.notice = true; view.fetching = true;
  expect(quota_state::classify(&view, true, true, true, true) == State::Activity, "activity-only outranks error");
  view.informational = false;
  expect(quota_state::classify(&view, true, true, true, true) == State::Error, "notice outranks fetching");
  view.notice = false;
  expect(quota_state::classify(&view, true, true, true, true) == State::Fetching, "fetching outranks stale/quota");
  view.fetching = false;
  expect(quota_state::classify(&view, true, false, true, true) == State::Stale, "stale outranks critical");
  expect(quota_state::classify(&view, true, true, true, true) == State::Critical, "critical outranks low");
  expect(quota_state::classify(&view, true, true, false, true) == State::Low, "low");
  expect(quota_state::classify(&view, true, true, false, false) == State::Connected, "connected");
  expect(!std::strcmp(quota_state::label(State::Activity, false), "ACTIVITY / SETUP"), "long activity");
  expect(!std::strcmp(quota_state::label(State::Activity, true), "ACTIVITY"), "short activity");
  expect(!std::strcmp(quota_state::label(State::Error, false), "ERROR - TAP"), "long error");
  expect(!std::strcmp(quota_state::label(State::Error, true), "ERROR"), "short error");
  expect(!std::strcmp(quota_state::label(State::Fetching, false), "FETCHING"), "long fetching");
  expect(!std::strcmp(quota_state::label(State::Fetching, true), "UPDATING"), "short fetching");
  std::puts("Quota state priority and label tests passed");
}
