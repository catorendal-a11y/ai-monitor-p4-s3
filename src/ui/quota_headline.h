#pragma once
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include "ai_monitor/ai_monitor.h"
#include "quota_alert.h"

// The most urgent quota window over every selected AI, for the dashboard header. With more than
// two AIs the cards page, so the window that matters most must not hide on another page.
// Only fresh, error-free measurements count, like the cards and the quota alerts.
struct QuotaHeadline {
  bool valid = false;
  char provider[16] = {}, window[36] = {};
  float remaining = 100.0f;
  uint8_t level = 0;  // 0 comfortable, 1 low, 2 critical
};

inline QuotaHeadline quota_headline(const aim::Snapshot& snapshot, uint32_t now) {
  QuotaHeadline best;
  if (!snapshot.hostPresent) return best;
  for (size_t v = 0; v < aim::kMaxViews; ++v) {
    if (snapshot.viewsConfigured && v >= snapshot.viewCount) continue;
    const auto& view = snapshot.views[v];
    if (!view.valid || !view.hasUsage || view.notice || view.fetching || view.informational ||
        now - view.quotaReceivedMs >= aim::kQuotaStaleMs) continue;
    for (size_t r = 0; r < view.rowCount; ++r) {
      const auto& row = view.rows[r];
      if (!row.valid) continue;
      const float remaining = view.showsRemaining ? row.usedPercent : 100.0f - row.usedPercent;
      if (best.valid && remaining >= best.remaining) continue;
      best.valid = true;
      best.remaining = remaining;
      snprintf(best.provider, sizeof(best.provider), "%s", view.providerLabel[0] ? view.providerLabel : view.providerKey);
      snprintf(best.window, sizeof(best.window), "%s", row.title);
      best.level = quota_critical(remaining, view.providerKey, row) ? 2 : (quota_low(remaining, view.providerKey, row) ? 1 : 0);
    }
  }
  return best;
}
