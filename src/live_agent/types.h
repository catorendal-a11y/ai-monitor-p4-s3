#pragma once
#include <cstdint>
#include <cstring>
#include "../interaction/types.h"

namespace live_agent {
inline constexpr uint32_t lease_ms=30000;
using Prompt=interaction::PermissionRequest;
struct ClaudeLiveSnapshot {
  uint16_t total=0,running=0,waiting=0;
  uint64_t outputTokens=0,outputTokensToday=0;
  bool outputTokensKnown=false,outputTokensTodayKnown=false,fresh=false;
  uint32_t receivedAt=0,epoch=0,revision=0;
  Prompt prompt;
  // Archived-reference adapter only; new production interaction code never depends on this type.
  operator interaction::InteractionSnapshot()const {
    interaction::InteractionSnapshot result;
    result.fresh=fresh;result.receivedAt=receivedAt;result.epoch=epoch;result.revision=revision;result.request=prompt;
    return result;
  }
};
}
