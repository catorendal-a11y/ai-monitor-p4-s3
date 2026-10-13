#pragma once
#include <cstdint>
#include <cstring>

namespace live_agent {
inline constexpr uint32_t lease_ms=30000;
struct Prompt {
  char id[97]{}, tool[65]{}, hint[513]{};
  bool present=false, displaySupported=false;
  bool equals(const Prompt& other) const {
    return present==other.present && displaySupported==other.displaySupported &&
      !strcmp(id,other.id) && !strcmp(tool,other.tool) && !strcmp(hint,other.hint);
  }
};
struct ClaudeLiveSnapshot {
  uint16_t total=0,running=0,waiting=0;
  uint64_t outputTokens=0,outputTokensToday=0;
  bool outputTokensKnown=false,outputTokensTodayKnown=false,fresh=false;
  uint32_t receivedAt=0,epoch=0,revision=0;
  Prompt prompt;
};
}
