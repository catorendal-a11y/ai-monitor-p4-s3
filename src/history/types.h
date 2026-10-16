#pragma once
#include <cstdint>
namespace history {
struct Provider {
  char key[16]{};
  uint64_t daily[7]{},hourly[24]{};
  uint32_t dailyKnown=0,hourlyKnown=0;
  bool quotaKnown=false,changeKnown=false;
  uint32_t windowMinutes=0,quotaAgeMinutes=0;
  float usedPercent=0,changePercent=0;
  uint8_t agentKnown=0;
  uint32_t sessions=0,activeSeconds=0,completedTurns=0,failedTurns=0;
  uint32_t createdTasks=0,startedTasks=0,completedTasks=0,failedTasks=0;
};
struct Snapshot {
  bool fresh=false,enabled=false,error=false;
  char date[11]{};
  uint32_t receivedAt=0,revision=0;
  uint8_t count=0;
  Provider providers[8];
};
Snapshot read();
}
