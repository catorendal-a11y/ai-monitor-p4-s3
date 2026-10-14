#pragma once
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "ai_monitor/ai_monitor.h"

// Bounded RAM history. One sample per five-minute bucket, at most 24 hours.
class UsageHistory {
 public:
  static constexpr size_t capacity = 288;
  struct Sample {
    uint32_t time = 0, bucketStart = 0;
    float remaining[aim::kMaxRows] = {};
    uint8_t valid = 0, breakBefore = 0;
  };
  struct Series {
    Sample points[capacity]{};
    size_t first = 0, count = 0;
    uint32_t lastReceived = 0;
    bool initialized = false;
    bool gap = false;
    char key[16] = {};
    char titles[aim::kMaxRows][36] = {};
    uint32_t windows[aim::kMaxRows] = {};
  };
  void capture(const aim::Snapshot& snapshot, uint32_t now) {
    for (size_t v = 0; v < aim::kMaxViews; ++v) {
      auto& series = views_[v];
      const auto& view = snapshot.views[v];
      while (series.count && now - sample(series, 0).time >= 86400000u) {
        series.first = (series.first + 1) % capacity; --series.count; ++revision_;
      }
      if (snapshot.viewsConfigured && (v >= snapshot.viewCount || std::strcmp(series.key, snapshot.viewKeys[v]) != 0)) {
        if (series.initialized) { series = Series{}; ++revision_; }
      }
      if (!snapshot.hostPresent || !view.valid || view.notice || view.fetching || !view.hasUsage || !view.rowCount) {
        if (!snapshot.hostPresent || view.notice || !view.valid || !view.hasUsage) series.gap = true;
        continue;
      }
      bool changed = std::strcmp(series.key, view.providerKey) != 0;
      for (size_t r = 0; r < aim::kMaxRows; ++r)
        changed |= std::strcmp(series.titles[r], view.rows[r].title) != 0 || series.windows[r] != view.rows[r].windowMinutes;
      if (!changed && series.initialized && series.lastReceived == view.quotaReceivedMs) continue;
      if (changed) {
        series.first = series.count = 0;
        std::snprintf(series.key, sizeof(series.key), "%s", view.providerKey);
        for (size_t r = 0; r < aim::kMaxRows; ++r) {
          std::snprintf(series.titles[r], sizeof(series.titles[r]), "%s", view.rows[r].title);
          series.windows[r] = view.rows[r].windowMinutes;
        }
      }
      series.initialized = true;
      const bool gap = series.gap || (series.count && view.quotaReceivedMs - series.lastReceived > 300000u);
      series.lastReceived = view.quotaReceivedMs;
      series.gap = false;
      if (now - view.quotaReceivedMs >= 86400000u) continue;
      Sample point;
      point.time = point.bucketStart = view.quotaReceivedMs;
      for (size_t r = 0; r < view.rowCount; ++r) {
        if (!view.rows[r].valid) continue;
        point.valid |= 1u << r;
        point.remaining[r] = std::clamp(view.showsRemaining ? view.rows[r].usedPercent : 100.0f - view.rows[r].usedPercent, 0.0f, 100.0f);
      }
      // Unsigned subtraction also handles the millisecond counter wrapping.
      point.breakBefore = gap ? point.valid : 0;
      if (!gap && series.count && point.time - sample(series, series.count - 1).bucketStart < 300000u) {
        auto& last = series.points[(series.first + series.count - 1) % capacity];
        point.bucketStart = last.bucketStart;
        point.breakBefore = last.breakBefore;
        last = point;
      } else {
        if (series.count == capacity) { series.first = (series.first + 1) % capacity; --series.count; }
        series.points[(series.first + series.count++) % capacity] = point;
      }
      ++revision_;
    }
  }
  const Series& series(size_t view) const { return views_[view]; }
  static const Sample& sample(const Series& series, size_t index) { return series.points[(series.first + index) % capacity]; }
  uint32_t revision() const { return revision_; }
 private:
  Series views_[aim::kMaxViews]{};
  uint32_t revision_ = 0;
};
