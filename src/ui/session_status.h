#pragma once
#include "ai_monitor/ai_monitor.h"
#include "agent/types.h"
#include "live_agent/activity_types.h"

struct SessionStatus {
  bool known = false;
  uint8_t sources = 0;
  uint16_t running = 0, waiting = 0, completed = 0, error = 0;
};

inline SessionStatus session_status(const aim::Snapshot& snapshot, uint32_t now,
                                    uint8_t requested_sources = 255u,const agent::Snapshot& events=agent::read(),
                                    const live_agent::UsbLiveSnapshot& live=live_agent::UsbLiveSnapshot{}) {
  SessionStatus result{};
  if (!snapshot.hostPresent) return result;
  uint8_t selected = requested_sources;
  if (snapshot.viewsConfigured) {
    uint8_t configured = 0;
    for (size_t i = 0; i < snapshot.viewCount && i < aim::kMaxViews; ++i) {
      const auto* style = aim::provider_style(snapshot.viewKeys[i]);
      if (style) configured |= style->activityMask;
    }
    selected &= configured;
  }
  uint8_t represented=0;
  if(live.fresh && now-live.receivedAt<live_agent::activity_lease_ms)
    for(unsigned i=0;i<live.count && i<8;++i) {
      const auto& item=live.agents[i];const auto* style=aim::provider_style(item.provider);
      if(!style || !(style->activityMask&selected))continue;
      represented|=style->activityMask;
      if(item.observedAgeSeconds>30)continue; // Historical phase is not fresh companion activity.
      result.known=true;result.sources|=style->activityMask;
      switch(item.state) {
        case agent::State::WAITING:case agent::State::NEEDS_ATTENTION:++result.waiting;break;
        case agent::State::ERROR:++result.error;break;
        case agent::State::COMPLETED:++result.completed;break;
        case agent::State::WORKING:case agent::State::THINKING:case agent::State::READING:
        case agent::State::SEARCHING:case agent::State::EDITING:case agent::State::WRITING:
        case agent::State::RUNNING:case agent::State::BUILDING:case agent::State::TESTING:++result.running;break;
        default:break;
      }
    }
  if (!events.fresh || now-events.sessionActivityMs>=35000u)return result;
  for (size_t i = 0; i < events.sessionCount && i < agent::max_sources; ++i) {
    const auto& item = events.sessions[i];
    if (!(item.source & selected) || (item.source&represented)) continue;
    result.known = true; result.sources |= item.source;
    result.running += item.running; result.waiting += item.waiting;
    result.completed += item.completed; result.error += item.error;
  }
  return result;
}

inline SessionStatus session_status(const aim::Snapshot& snapshot, uint32_t now, const char* provider) {
  const auto* style = aim::provider_style(provider);
  return session_status(snapshot, now, static_cast<uint8_t>(style ? style->activityMask : 0u));
}
