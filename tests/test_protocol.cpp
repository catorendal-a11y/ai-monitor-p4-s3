#include "ai_monitor/ai_monitor_proto.h"
#include "ui/idle_dim.h"
#include "ui/backlight.h"
#include "app_settings.h"
#include "ui/usage_format.h"
#include "ui/usage_history.h"
#include "ui/night_mode.h"
#include "ui/brightness_fade.h"
#include "ui/quota_notifications.h"
#include "ui/nova_state.h"

#include <cmath>
#include <cstdlib>
#include <iostream>
#include <string>

static unsigned failures = 0;
#define CHECK(condition) do { if (!(condition)) { \
  std::cerr << __func__ << ":" << __LINE__ << ": " #condition "\n"; ++failures; \
} } while (false)

static void feed(aim::ProtoCore& core, const std::string& text) {
  for (char byte : text) core.feed_byte(byte);
}

static std::string frame(const std::string& rows, const char* provider = "codex", int index = 0) {
  return "{\"schemaVersion\":1,\"frameId\":7,\"displayTime\":\"14:30\",\"data\":[{\"provider\":\"" +
      std::string(provider) + "\",\"viewIndex\":" + std::to_string(index) +
      ",\"usage\":{\"rows\":" + rows + "}}]}\n";
}

static void timestamp_and_ack() {
  aim::ProtoCore core;
  core.tick = [] { return 1234u; };
  const uint32_t revisionBefore = core.snapshot_revision();
  const std::string payload = frame("[{\"title\":\"Session\",\"usedPercent\":25}]");
  feed(core, "AIM1 " + std::to_string(payload.size()) + " 7\n" + payload);
  CHECK(core.snapshot().views[0].receivedMs == 1234);
  CHECK(core.snapshot().lastFrameMs == 1234);
  CHECK(core.snapshot().frameCount == 1);
  CHECK(core.snapshot().views[0].rows[0].usedPercent == 25);
  CHECK(core.out().find("\"type\":\"ack\"") != std::string::npos);
  // A completed frame is a snapshot state change; stray text is not.
  CHECK(core.snapshot_revision() > revisionBefore);
  const uint32_t revisionAfterFrame = core.snapshot_revision();
  feed(core, "not json at all\n");
  CHECK(core.snapshot_revision() == revisionAfterFrame);
}

static void invalid_frame_keeps_snapshot() {
  aim::ProtoCore core;
  feed(core, frame("[{\"usedPercent\":20}]"));
  const auto before = core.snapshot();
  const std::string invalid[] = {
      frame("[{\"usedPercent\":20}]", "unknown"),
      frame("[{\"usedPercent\":20}]", "codex", 8),
      frame("[{\"usedPercent\":\"bad\"}]"),
      frame("[{\"usedPercent\":101}]"),
      frame("[]"),
      "{\"schemaVersion\":2,\"frameId\":8,\"displayTime\":\"01:00\",\"data\":[]}\n",
      // windowMinutes identifies a quota window; wrong types must be rejected.
      frame("[{\"title\":\"S\",\"usedPercent\":20,\"windowMinutes\":\"300\"}]"),
      frame("[{\"title\":\"S\",\"usedPercent\":20,\"windowMinutes\":300.5}]"),
      frame("[{\"title\":\"S\",\"usedPercent\":20,\"windowMinutes\":true}]"),
      "{\"schemaVersion\":1,\"frameId\":9,\"data\":[{\"provider\":\"codex\",\"viewIndex\":0,"
      "\"usage\":{\"primary\":{\"usedPercent\":20,\"windowMinutes\":\"300\"}}}]}\n",
  };
  for (const auto& text : invalid) {
    core.clear_out();
    feed(core, text);
    CHECK(core.snapshot().frameCount == before.frameCount);
    CHECK(core.snapshot().views[0].rows[0].usedPercent == 20);
    CHECK(std::string(core.snapshot().displayTime) == "14:30");
    CHECK(core.out().find("\"type\":\"error\"") != std::string::npos);
  }
}

static void set_views_clears_old_data_and_rejects_bad_keys() {
  aim::ProtoCore core;
  feed(core, frame("[{\"usedPercent\":20}]"));
  feed(core, "{\"cmd\":\"set_views\",\"views\":[\"zcode\"]}\n");
  CHECK(!core.snapshot().views[0].valid);
  CHECK(core.snapshot().viewCount == 1);
  core.clear_out();
  feed(core, "{\"cmd\":\"set_views\",\"views\":[\"co\\\"dex\"]}\n");
  CHECK(core.out().find("\"type\":\"error\"") != std::string::npos);
  CHECK(std::string(core.snapshot().viewKeys[0]) == "zcode");
  // interval/active must be integers when present, not silent defaults.
  const char* typed[] = {
      "{\"cmd\":\"set_views\",\"views\":[\"codex\"],\"interval\":\"20\"}",
      "{\"cmd\":\"set_views\",\"views\":[\"codex\"],\"interval\":3.5}",
      "{\"cmd\":\"set_views\",\"views\":[\"codex\"],\"active\":true}",
  };
  for (const auto* text : typed) {
    core.clear_out();
    feed(core, std::string(text) + "\n");
    CHECK(core.out().find("\"type\":\"error\"") != std::string::npos);
    CHECK(core.snapshot().viewCount == 1);
    CHECK(std::string(core.snapshot().viewKeys[0]) == "zcode");
  }
  core.clear_out();
  feed(core, "{\"cmd\":\"set_views\",\"views\":[\"codex\",\"zcode\"],\"interval\":20,\"active\":1}\n");
  CHECK(core.out().find("\"type\":\"ok\"") != std::string::npos);
  CHECK(core.snapshot().viewCount == 2);
  CHECK(core.snapshot().viewIntervalSeconds == 20);
  CHECK(core.snapshot().activeView == 1);
}

static void brightness_rejects_invalid_values() {
  aim::ProtoCore core;
  feed(core, "{\"cmd\":\"set_brightness\",\"value\":101}\n");
  CHECK(core.out().find("\"type\":\"error\"") != std::string::npos);
}

static void framing_timeout_and_overflow_recover() {
  aim::ProtoCore core;
  uint32_t tick = 0xfffffff0u;
  core.tick = [&tick] { return tick; };
  feed(core, "AIM1 100 1\n{}");
  tick += 2100;
  core.poll();
  feed(core, "{\"cmd\":\"get_info\"}\n");
  CHECK(core.out().find("\"type\":\"info\"") != std::string::npos);
  core.clear_out();
  feed(core, std::string(5000, 'x') + "\n{\"cmd\":\"get_info\"}\n");
  CHECK(core.out().find("\"type\":\"info\"") != std::string::npos);
}

static void brightness_honors_persistence_and_queue_failure() {
  aim::ProtoCore core;
  unsigned calls = 0;
  bool persisted = true;
  core.apply_brightness = [&](uint8_t value, bool persist) {
    CHECK(value == 50);
    persisted = persist;
    ++calls;
    return true;
  };
  feed(core, "{\"cmd\":\"set_brightness\",\"value\":50,\"persist\":false}\n");
  CHECK(calls == 1 && !persisted);
  CHECK(core.out().find("\"type\":\"ok\"") != std::string::npos);
  feed(core, "{\"cmd\":\"set_brightness\",\"value\":50,\"persist\":true}\n");
  CHECK(calls == 2 && persisted);
  for (const char* invalid : {"1", "0", "0.5", "\"true\"", "\"false\"", "null", "[]", "{}"}) {
    core.clear_out();
    feed(core, std::string("{\"cmd\":\"set_brightness\",\"value\":50,\"persist\":") + invalid + "}\n");
    CHECK(calls == 2 && persisted);
    CHECK(core.out().find("set_brightness: invalid persist") != std::string::npos);
    CHECK(core.out().find("\"type\":\"ok\"") == std::string::npos);
  }
  core.clear_out();
  feed(core, "{\"cmd\":\"set_brightness\",\"value\":50}\n");
  CHECK(calls == 3 && !persisted);  // omission remains non-persistent
  core.clear_out();
  feed(core, "{\"cmd\":\"set_brightness\",\"value\":\"50\"}\n");
  CHECK(calls == 3);
  CHECK(core.out().find("\"type\":\"error\"") != std::string::npos);
  core.apply_brightness = [](uint8_t, bool) { return false; };
  core.clear_out();
  feed(core, "{\"cmd\":\"set_brightness\",\"value\":50}\n");
  CHECK(core.out().find("\"type\":\"error\"") != std::string::npos);
}

static void text_sanitization_collapses_utf8_and_bounds_malformed_input() {
  struct Case { std::string input, expected; };
  const Case cases[] = {
      {"ASCII 50%", "ASCII 50%"},
      {"caf\xC3\xA9", "caf?"},             // two-byte scalar
      {"A\xE2\x82\xAC" "B", "A?B"},    // three-byte scalar
      {"A\xF0\x9F\xA4\x96" "B", "A?B"}, // four-byte scalar
      {"\xC2\x80\xDF\xBF\xE0\xA0\x80\xED\x9F\xBF\xEE\x80\x80\xF0\x90\x80\x80\xF4\x8F\xBF\xBF", "???????"},
      {std::string("A\tB\x7F", 4), "A?B?"},
      {"\xC0\xAF", "??"},              // overlong two-byte encoding
      {"\xE0\x80\x80", "???"},        // overlong three-byte encoding
      {"\xED\xA0\x80", "???"},        // UTF-16 surrogate, not a scalar
      {"\xF0\x80\x80\x80", "????"},  // overlong four-byte encoding
      {"\xF4\x90\x80\x80", "????"},  // beyond U+10FFFF
      {"\xF5\x80\x80\x80", "????"},  // invalid leading byte
      {"\xC3", "?"}, {"\xE2\x82", "??"}, {"\xF0\x9F\xA4", "???"},
      {"\xE2" "AB", "?AB"}, {"\x80\xBF" "Z", "??Z"},
      {std::string(34, 'a') + "\xF0\x9F\xA4\x96" + "tail", std::string(34, 'a') + "?"},
      {std::string(35, 'a') + "\xC3\xA9", std::string(35, 'a')},
  };
  for (const auto& test : cases) {
    aim::ProtoCore core;
    JsonDocument document;
    document["provider"] = "codex";
    auto row = document["usage"]["rows"].to<JsonArray>().add<JsonObject>();
    row["title"] = test.input; row["usedPercent"] = 45;
    JsonDocument wrapper;
    wrapper["data"].to<JsonArray>().add(document.as<JsonObject>());
    std::string payload; serializeJson(wrapper, payload); payload += '\n';
    feed(core, payload);
    CHECK(core.snapshot().frameCount == 1);
    CHECK(std::string(core.snapshot().views[0].rows[0].title) == test.expected);
    CHECK(core.snapshot().views[0].rows[0].usedPercent == 45);
    CHECK(core.snapshot().views[0].rows[0].title[35] == '\0');
  }
  // Sanitizing while copying keeps bounded ASCII output after many Unicode
  // characters, rather than byte-truncating the source before conversion.
  std::string message;
  for (size_t i = 0; i < 158; ++i) message += "\xF0\x9F\xA4\x96";
  message += "AB";
  aim::ProtoCore core;
  JsonDocument notice;
  notice["data"][0]["provider"] = "codex"; notice["data"][0]["notice"] = message;
  std::string payload; serializeJson(notice, payload); payload += '\n'; feed(core, payload);
  CHECK(std::string(core.snapshot().views[0].message) == std::string(158, '?') + "A");
  CHECK(core.snapshot().views[0].message[159] == '\0');
  aim::ProtoCore resetCore;
  feed(resetCore, frame("[{\"usedPercent\":40,\"resetsAt\":\"2026-04-10T\xE2\x82\xAC" "AB\"}]"));
  CHECK(std::string(resetCore.snapshot().views[0].rows[0].resetsShort) == "?AB");
}

static void notices_and_clock_sync() {
  aim::ProtoCore core;
  core.tick = [] { return 3000u; };
  feed(core, frame("[{\"usedPercent\":20}]"));
  CHECK(core.snapshot().displayTimeMs == 3000);
  core.tick = [] { return 5000u; };
  feed(core, "{\"frameId\":8,\"data\":[{\"provider\":\"codex\",\"notice\":\"Unavailable\"}]}\n");
  CHECK(core.snapshot().views[0].notice);
  CHECK(core.snapshot().views[0].rowCount == 1);
  CHECK(core.snapshot().views[0].hasUsage);
  CHECK(core.snapshot().views[0].quotaReceivedMs == 3000);
  CHECK(core.snapshot().views[0].rows[0].usedPercent == 20);
  CHECK(core.snapshot().views[0].receivedMs == 5000);
  CHECK(core.snapshot().displayTimeMs == 3000);
  CHECK(std::string(core.snapshot().displayTime) == "14:30");
}

static void fallback_rows_and_three_row_cap() {
  aim::ProtoCore core;
  feed(core, "{\"data\":[{\"provider\":\"codex\",\"usage\":{\"primary\":{\"usedPercent\":25},"
      "\"secondary\":{\"usedPercent\":50}}}]}\n");
  CHECK(core.snapshot().views[0].rowCount == 2);
  feed(core, frame("[{\"usedPercent\":10},{\"usedPercent\":20},{\"usedPercent\":30},{\"usedPercent\":40}]"));
  CHECK(core.snapshot().views[0].rowCount == 3);
  CHECK(core.snapshot().views[0].rows[2].usedPercent == 30);
}

static void dim_timeout_wake_and_wraparound() {
  IdleDimPolicy dim;
  const uint32_t start = 0xfffffff0u;
  CHECK(dim.update(start, 160, 1) == 160);
  CHECK(dim.update(start + 59999u, 160, 1) == 160);
  CHECK(dim.update(start + 60000u, 160, 1) == 48);
  CHECK(!dim.touch(start + 60001u, true));
  CHECK(!dim.touch(start + 60002u, true));
  CHECK(dim.update(start + 160000u, 160, 1) == 160);  // held touch never dims
  CHECK(!dim.touch(start + 160001u, false));
  CHECK(dim.touch(start + 160002u, true));
  dim.touch(start + 160003u, false);
  CHECK(dim.update(start + 220003u, 160, 0) == 160);
  dim.preview();
  CHECK(dim.update(start + 220003u, 160, 0) == 48);
  CHECK(dim.update(start + 220003u, 1, 0) == 1);
  for (unsigned percent = 0; percent <= 100; ++percent) {
    CHECK(brightness_percent(brightness_raw(static_cast<uint8_t>(percent))) == percent);
  }
  CHECK(app_settings::normalize_dim_minutes(255) == 5);
}

static void view_mode_and_firmware_identity() {
  aim::ProtoCore core;
  core.firmware_version = "v1.2.0";
  feed(core, "{\"cmd\":\"get_info\"}\n");
  CHECK(core.out().find("\"firmwareVersion\":\"v1.2.0\"") != std::string::npos);
  CHECK(core.out().find(std::string("\"boardId\":\"") + board_profile::id + "\"") != std::string::npos);
  CHECK(core.out().find(std::string("\"chip\":\"") + board_profile::chip + "\"") != std::string::npos);
  CHECK(core.out().find(std::string("\"brightnessControl\":\"") + board_profile::brightness_control + "\"") != std::string::npos);
  core.tick = [] { return uint32_t{0xffffffffu}; };
  core.heap = [] { return uint32_t{0xffffffffu}; };
  core.boot_id = 0xffffffffu;
  feed(core, "{\"cmd\":\"token_activity\",\"known\":true,\"seen\":true,\"sources\":255,\"idleSeconds\":4294967295,\"delta\":18446744073709551615}\n");
  core.clear_out();
  feed(core, "{\"cmd\":\"get_info\"}\n");
  JsonDocument identity;
  CHECK(!deserializeJson(identity, core.out()));
  CHECK(identity["boardId"] == board_profile::id);
  feed(core, "{\"cmd\":\"set_views\",\"views\":[\"codex\",\"zcode\"],\"mode\":\"automatic\",\"active\":1,\"interval\":2}\n");
  CHECK(core.snapshot().activeView == 1);
  CHECK(core.snapshot().automaticViews);
  CHECK(core.snapshot().viewIntervalSeconds == 2);
  CHECK(core.snapshot().viewRevision == 1);
}

static void framed_identity_and_types_are_checked() {
  aim::ProtoCore core;
  const std::string payload = frame("[{\"usedPercent\":20}]");
  feed(core, "AIM1 " + std::to_string(payload.size()) + " 99\n" + payload);
  CHECK(core.snapshot().frameCount == 0);
  CHECK(core.out().find("\"frameId\":99") != std::string::npos);
  CHECK(core.out().find("\"type\":\"error\"") != std::string::npos);
  const std::string invalid[] = {
    "{\"frameId\":7,\"schemaVersion\":\"bad\",\"data\":[{\"provider\":\"codex\",\"usage\":{\"rows\":[{\"usedPercent\":20}]}}]}\n",
    "{\"frameId\":7,\"data\":[{\"provider\":\"codex\",\"viewIndex\":\"bad\",\"usage\":{\"rows\":[{\"usedPercent\":20}]}}]}\n",
    "{\"frameId\":7,\"data\":[{\"provider\":\"codex\",\"fetching\":\"yes\",\"usage\":{\"rows\":[{\"usedPercent\":20}]}}]}\n",
    "{\"frameId\":7,\"data\":[{\"provider\":\"codex\",\"usage\":{\"percentMode\":false,\"rows\":[{\"usedPercent\":20}]}}]}\n",
  };
  for (const auto& text : invalid) {
    core.clear_out(); feed(core, text);
    CHECK(core.snapshot().frameCount == 0);
    CHECK(core.out().find("\"type\":\"error\"") != std::string::npos);
  }
}

static void active_slow_transfer_is_not_a_stall() {
  aim::ProtoCore core;
  uint32_t now = 100;
  core.tick = [&now] { return now; };
  const std::string payload = frame("[{\"usedPercent\":20}]");
  feed(core, "AIM1 " + std::to_string(payload.size()) + " 7\n");
  for (size_t offset = 0; offset < payload.size(); offset += 25) {
    now += 500;
    feed(core, payload.substr(offset, 25));
    core.poll();
  }
  CHECK(now > 2100);
  CHECK(core.snapshot().frameCount == 1);
}

static void heartbeat_tracks_link_without_refreshing_quota() {
  aim::ProtoCore core;
  uint32_t now = 100;
  core.tick = [&now] { return now; };
  core.boot_id = 42;
  feed(core, frame("[{\"usedPercent\":20}]"));
  now = 10000;
  feed(core, "{\"cmd\":\"get_info\",\"heartbeat\":true,\"displayTime\":\"23:59\",\"displaySeconds\":59}\n");
  CHECK(core.snapshot().displaySeconds == 59);
  CHECK(core.snapshot().lastFrameMs == 100);
  CHECK(core.snapshot().views[0].receivedMs == 100);
  CHECK(core.snapshot().frameCount == 1);
  CHECK(core.out().find("\"bootId\":42") != std::string::npos);
  now += aim::ProtoCore::kHeartbeatTimeoutMs;
  CHECK(core.poll());
  CHECK(!core.snapshot().hostPresent);
  feed(core, "{\"cmd\":\"get_info\",\"heartbeat\":true}\n");
  CHECK(core.snapshot().hostPresent);
  feed(core, "{\"cmd\":\"get_info\"}\n");  // switching to a legacy companion restores its tolerance
  now += aim::ProtoCore::kHeartbeatTimeoutMs;
  CHECK(!core.poll());
  CHECK(core.snapshot().hostPresent);
}

static void reply_queue_and_header_limits() {
  aim::ProtoCore core;
  feed(core, "{\"cmd\":\"get_info\"}\n");
  const std::string reply = core.out();
  core.consume_out(7);
  CHECK(core.out() == reply.substr(7));
  core.consume_out(100000);
  CHECK(core.out().empty());
  for (unsigned i = 0; i < 100; ++i) feed(core, "{\"cmd\":\"get_info\"}\n");
  CHECK(core.out().size() <= aim::ProtoCore::kMaxReplyBytes);
  CHECK(core.out().back() == '\n');
  core.clear_out();
  feed(core, "AIM1 100 1 trailing\n");
  CHECK(core.out().find("\"type\":\"error\"") != std::string::npos);
  core.clear_out();
  feed(core, "{\"cmd\":\"get_info\"}\n");
  CHECK(core.out().find("\"type\":\"info\"") != std::string::npos);
}

static void oversized_plain_frame_is_rejected() {
  aim::ProtoCore core;
  std::string payload = frame("[{\"usedPercent\":20}]");
  payload.pop_back();
  const std::string emptyPadding = ",\"padding\":\"\"";
  const size_t padding = aim::ProtoCore::kAim1MaxPayload + 1 - payload.size() - emptyPadding.size();
  payload.insert(payload.size() - 1, ",\"padding\":\"" + std::string(padding, 'x') + "\"");
  CHECK(payload.size() == aim::ProtoCore::kAim1MaxPayload + 1);
  feed(core, payload + "\n");
  CHECK(core.snapshot().frameCount == 0);
  CHECK(core.out().find("line exceeds maxFrameBytes") != std::string::npos);
  // A line beyond the assembly buffer is also answered, not silently dropped.
  core.clear_out();
  feed(core, std::string(aim::ProtoCore::kAim1MaxPayload + 40, 'y') + "\n");
  CHECK(core.snapshot().frameCount == 0);
  CHECK(core.out().find("line exceeds maxFrameBytes") != std::string::npos);
  // Recovery: the very next well-formed command still works.
  core.clear_out();
  feed(core, "{\"cmd\":\"get_info\"}\n");
  CHECK(core.out().find("\"type\":\"info\"") != std::string::npos);
}

static void rows_beyond_protocol_cap_do_not_invalidate_supported_rows() {
  aim::ProtoCore core;
  feed(core, frame("[{\"usedPercent\":10},{\"usedPercent\":20},{\"usedPercent\":30},null]"));
  CHECK(core.snapshot().frameCount == 1);
  CHECK(core.snapshot().views[0].rowCount == 3);
}

static void reset_countdown_types_and_wraparound() {
  aim::ProtoCore core;
  feed(core, frame("[{\"usedPercent\":20,\"resetSeconds\":2400}]"));
  const auto& row = core.snapshot().views[0].rows[0];
  CHECK(row.hasResetCountdown && row.resetSeconds == 2400);
  CHECK(reset_remaining(row, 0xfffffff0u, 0x3d8u) == 2399);
  CHECK(reset_remaining(row, 0, 2400000) == 0);
  char text[40];
  format_countdown(1, text, sizeof(text)); CHECK(std::string(text) == "1 m");
  format_countdown(0, text, sizeof(text)); CHECK(std::string(text) == "Reset due");
  format_countdown(86400, text, sizeof(text)); CHECK(std::string(text) == "1 d 0 h");
  format_countdown(UINT32_MAX, text, sizeof(text)); CHECK(std::string(text).find("49710 d") == 0);
  for (const char* invalid : {"-1", "true", "\"20\"", "1.5", "4294967296"}) {
    feed(core, frame(std::string("[{\"usedPercent\":20,\"resetSeconds\":") + invalid + "}]"));
    CHECK(core.snapshot().frameCount == 1);
  }
}

static void manual_refresh_lifecycle_and_timeout() {
  aim::ProtoCore core;
  uint32_t now = 100;
  core.tick = [&now] { return now; };
  core.request_refresh();
  CHECK(core.snapshot().refreshState == aim::RefreshState::failed);
  CHECK(core.out().empty());
  feed(core, "{\"cmd\":\"get_info\",\"manualRefresh\":true,\"heartbeat\":true}\n");
  core.clear_out(); core.request_refresh();
  CHECK(core.snapshot().refreshId == 1);
  CHECK(core.out().find("\"type\":\"refresh_request\"") != std::string::npos);
  const auto event = core.out(); core.request_refresh(); CHECK(core.out() == event);
  feed(core, "{\"cmd\":\"refresh_status\",\"requestId\":2,\"state\":\"complete\"}\n");
  CHECK(core.snapshot().refreshState == aim::RefreshState::requested);
  feed(core, "{\"cmd\":\"refresh_status\",\"requestId\":1,\"state\":\"waiting\"}\n");
  CHECK(core.snapshot().refreshState == aim::RefreshState::waiting);
  feed(core, "{\"cmd\":\"refresh_status\",\"requestId\":1,\"state\":\"updating\"}\n");
  feed(core, "{\"cmd\":\"refresh_status\",\"requestId\":1,\"state\":\"complete\"}\n");
  CHECK(core.snapshot().refreshState == aim::RefreshState::complete);
  feed(core, "{\"cmd\":\"refresh_status\",\"requestId\":1,\"state\":\"waiting\"}\n");
  CHECK(core.snapshot().refreshState == aim::RefreshState::complete);
  core.request_refresh(); CHECK(core.snapshot().refreshId == 2);
  now += 50000;
  feed(core, "{\"cmd\":\"get_info\",\"manualRefresh\":true,\"heartbeat\":true}\n");
  now += 20000;
  CHECK(core.poll());
  CHECK(core.snapshot().hostPresent);
  CHECK(core.snapshot().refreshState == aim::RefreshState::failed);
  core.request_refresh();
  now += 60000;
  CHECK(core.poll());
  CHECK(!core.snapshot().hostPresent && core.snapshot().refreshState == aim::RefreshState::failed);
  feed(core, "{\"cmd\":\"get_info\"}\n");
  core.clear_out(); core.request_refresh();
  CHECK(core.out().empty());  // older companion cannot refresh
}

static void history_is_bounded_normalized_and_provider_specific() {
  static UsageHistory history;
  aim::Snapshot snapshot;
  snapshot.hostPresent = true;
  auto& view = snapshot.views[0];
  view.valid = view.hasUsage = true; view.rowCount = 1; view.rows[0].valid = true;
  std::strcpy(view.providerKey, "codex"); std::strcpy(view.rows[0].title, "Session");
  view.rows[0].usedPercent = 75; view.receivedMs = view.quotaReceivedMs = 100;
  history.capture(snapshot, view.quotaReceivedMs); history.capture(snapshot, view.quotaReceivedMs);
  CHECK(history.series(0).count == 1);
  CHECK(UsageHistory::sample(history.series(0), 0).remaining[0] == 25);
  view.quotaReceivedMs += 200000; view.rows[0].usedPercent = 80; history.capture(snapshot, view.quotaReceivedMs);
  CHECK(history.series(0).count == 1);
  CHECK(UsageHistory::sample(history.series(0), 0).remaining[0] == 20);
  CHECK(UsageHistory::sample(history.series(0), 0).time == 200100);
  for (int i = 0; i < 300; ++i) { view.quotaReceivedMs += 300000; history.capture(snapshot, view.quotaReceivedMs); }
  CHECK(history.series(0).count == UsageHistory::capacity);
  view.notice = true; view.quotaReceivedMs += 300000; history.capture(snapshot, view.quotaReceivedMs);
  CHECK(history.series(0).count == UsageHistory::capacity - 1);  // time keeps expiring during errors
  view.notice = false; view.showsRemaining = true;
  std::strcpy(view.providerKey, "zcode"); history.capture(snapshot, view.quotaReceivedMs);
  CHECK(history.series(0).count == 1);
  CHECK(UsageHistory::sample(history.series(0), 0).remaining[0] == 80);
  CHECK(app_settings::normalize_warning_percent(0) == 25);
  CHECK(app_settings::normalize_warning_percent(50) == 50);
}

static void history_expires_offline_and_does_not_join_outages() {
  static UsageHistory history;
  aim::Snapshot snapshot;
  snapshot.hostPresent = true;
  auto& view = snapshot.views[0]; view.valid = view.hasUsage = true;
  view.rowCount = 1; view.rows[0].valid = true; view.showsRemaining = true;
  std::strcpy(view.providerKey, "codex");
  view.quotaReceivedMs = 100; history.capture(snapshot, 100);
  view.quotaReceivedMs = 300100; history.capture(snapshot, 300100);
  CHECK(!UsageHistory::sample(history.series(0), 1).breakBefore);
  view.notice = true; history.capture(snapshot, 350100);
  view.notice = false; view.quotaReceivedMs = 400100; history.capture(snapshot, 400100);
  CHECK(history.series(0).count == 3);  // a recovery starts a separate bucket
  CHECK(UsageHistory::sample(history.series(0), 2).breakBefore & 1);
  snapshot.hostPresent = false;
  history.capture(snapshot, 400100 + 86400000u);
  CHECK(history.series(0).count == 0);
  snapshot.hostPresent = true; history.capture(snapshot, 400100 + 86400000u);
  CHECK(history.series(0).count == 0);  // old snapshot is never reinserted
  view.quotaReceivedMs = 0xffff0000u; history.capture(snapshot, view.quotaReceivedMs);
  view.quotaReceivedMs += 300000; history.capture(snapshot, view.quotaReceivedMs);
  CHECK(history.series(0).count == 2);
}

static void retained_quota_and_refresh_feedback() {
  aim::ProtoCore core;
  uint32_t now = 100; core.tick = [&now] { return now; };
  feed(core, frame("[{\"usedPercent\":20,\"resetSeconds\":2400}]"));
  now = 300100;
  feed(core, "{\"data\":[{\"provider\":\"codex\",\"notice\":\"Unavailable\"}]}\n");
  const auto& retained = core.snapshot().views[0];
  CHECK(retained.notice && retained.hasUsage && retained.rowCount == 1);
  CHECK(retained.quotaReceivedMs == 100);
  CHECK(reset_remaining(retained.rows[0], retained.quotaReceivedMs, now) == 2100);
  feed(core, "{\"data\":[{\"provider\":\"codex\",\"fetching\":true}]}\n");
  CHECK(core.snapshot().views[0].hasUsage && core.snapshot().views[0].quotaReceivedMs == 100);
  now += 500; feed(core, frame("[{\"usedPercent\":30}]"));
  CHECK(!core.snapshot().views[0].notice && core.snapshot().views[0].quotaReceivedMs == now);
  feed(core, "{\"data\":[{\"provider\":\"gemini\",\"notice\":\"Unavailable\"}]}\n");
  CHECK(!core.snapshot().views[0].hasUsage);  // never show another provider's quota
  aim::Snapshot snapshot; snapshot.hostPresent = snapshot.manualRefreshSupported = true;
  snapshot.refreshState = aim::RefreshState::complete; snapshot.refreshCompletedMs = 100;
  CHECK(std::string(refresh_hint(snapshot, 110)) == "Data updated");
  CHECK(std::string(refresh_hint(snapshot, 10100)).empty());
  snapshot.hostPresent = false; CHECK(std::string(refresh_hint(snapshot, 110)) == "PC host needed");
}

static void night_schedule_clock_and_boundaries() {
  app_settings::NightSettings settings{true, 1320, 420, 20};
  CHECK(night_scheduled(1320, settings)); CHECK(night_scheduled(419, settings));
  CHECK(!night_scheduled(420, settings)); CHECK(!night_scheduled(1319, settings));
  settings.start = 600; settings.end = 900;
  CHECK(night_scheduled(600, settings)); CHECK(!night_scheduled(900, settings));
  settings.start = settings.end = 0; CHECK(night_scheduled(100, settings));
  aim::Snapshot snapshot;
  CHECK(night_brightness(snapshot, 0, 200, settings) == 200);  // no synchronized clock
  std::strcpy(snapshot.displayTime, "23:59"); snapshot.displaySeconds = 59; snapshot.displayTimeMs = 10;
  uint16_t minute = 100;
  CHECK(local_minutes(snapshot, 1010, minute) && minute == 0);
  CHECK(night_brightness(snapshot, 1010, 200, settings) == brightness_raw(20));
  CHECK(night_brightness(snapshot, 1010, 10, settings) == 10);  // never raise selected brightness
  CHECK(!local_minutes(snapshot, 43200010, minute));
  const auto normalized = app_settings::normalize_night({true, 1500, 1500, 0});
  CHECK(normalized.start == 1320 && normalized.end == 420 && normalized.percent == 20);
}

static void quota_precision_and_bidirectional_fades() {
  char text[12];
  format_percent(0.4f, true, text, sizeof(text)); CHECK(std::string(text) == "0.4%");
  format_percent(0.04f, true, text, sizeof(text)); CHECK(std::string(text) == "<0.1%");
  format_percent(99.6f, false, text, sizeof(text)); CHECK(std::string(text) == "99.6%");
  format_percent(99.99f, true, text, sizeof(text)); CHECK(std::string(text) == ">99.9%");
  format_percent(0, true, text, sizeof(text)); CHECK(std::string(text) == "0%");
  format_percent(100, true, text, sizeof(text)); CHECK(std::string(text) == "100%");
  BrightnessFade fade;
  CHECK(fade.update(0, 40, 200) == 200);
  CHECK(fade.update(300, 40, 200) == 120);
  CHECK(fade.update(600, 40, 120) == 40);
  CHECK(fade.update(700, 200, 40) == 40);
  CHECK(fade.update(1000, 200, 40) == 120);
  CHECK(fade.update(1300, 200, 120) == 200);
  fade.reset(0xffffff00u, 200);
  CHECK(fade.update(0xffffff00u, 0, 200) == 200);
  CHECK(fade.update(0x158u, 0, 200) == 0);  // timer wrap, decreasing to zero
  fade.reset(100, 200);
  CHECK(fade.update(100, 40, 200) == 200);
  CHECK(fade.update(400, 40, 75) == 75);  // direct slider/USB change restarts the fade
}

static void notifications_acknowledge_escalate_and_rearm_after_recovery() {
  QuotaNotifications policy;
  aim::Snapshot snapshot;
  snapshot.hostPresent = true;
  auto& view = snapshot.views[0];
  view.valid = view.hasUsage = view.showsRemaining = true;
  view.rowCount = 1; view.quotaReceivedMs = 100;
  std::strcpy(view.providerKey, "codex");
  auto& row = view.rows[0]; row.valid = true; row.windowMinutes = 300;
  std::strcpy(row.title, "Session");
  const auto threshold = [](const char*, const aim::Row&) { return uint8_t{25}; };
  const auto update = [&](float remaining) { row.usedPercent = remaining; policy.update(snapshot, 100, threshold); };
  update(40); CHECK(!policy.current());
  update(25); CHECK(policy.current() && policy.current()->severity == 1);
  policy.acknowledge(*policy.current()); update(24); CHECK(!policy.current());
  update(10); CHECK(policy.current() && policy.current()->severity == 2);
  policy.acknowledge(*policy.current()); update(9); CHECK(!policy.current());
  update(10.5); update(9.8); CHECK(!policy.current());  // no repeated alert from threshold jitter
  update(13); CHECK(!policy.current());
  update(9); CHECK(policy.current() && policy.current()->severity == 2);
  policy.acknowledge(*policy.current());
  update(27.1); update(24); CHECK(policy.current() && policy.current()->severity == 1);
  policy.acknowledge(*policy.current());
  snapshot.hostPresent = false; update(90); CHECK(!policy.current());
  snapshot.hostPresent = true; update(24); CHECK(!policy.current());  // disconnect does not clear acknowledgement
  view.notice = true; update(5); CHECK(!policy.current());
  view.notice = false; policy.update(snapshot, 300100, threshold); CHECK(!policy.current());
  view.quotaReceivedMs = 0xfffffff0u;
  policy.update(snapshot, 16, threshold); CHECK(policy.current() && policy.current()->severity == 2);
}

static void notifications_prioritize_each_window_and_ignore_removed_views() {
  QuotaNotifications policy;
  aim::Snapshot snapshot;
  snapshot.hostPresent = snapshot.viewsConfigured = true; snapshot.viewCount = 2;
  const char* providers[] = {"codex", "zcode"};
  for (size_t i = 0; i < 2; ++i) {
    std::strcpy(snapshot.viewKeys[i], providers[i]);
    auto& view = snapshot.views[i];
    std::strcpy(view.providerKey, providers[i]);
    view.valid = view.hasUsage = view.showsRemaining = true; view.rowCount = 1;
    view.rows[0].valid = true; view.rows[0].usedPercent = i ? 12 : 24;
    std::strcpy(view.rows[0].title, "Session"); view.rows[0].windowMinutes = 300;
  }
  snapshot.views[0].rowCount = 2;
  snapshot.views[0].rows[1] = snapshot.views[0].rows[0];
  std::strcpy(snapshot.views[0].rows[1].title, "Week");
  snapshot.views[0].rows[1].windowMinutes = 10080; snapshot.views[0].rows[1].usedPercent = 5;
  const auto threshold = [](const char*, const aim::Row&) { return uint8_t{25}; };
  policy.update(snapshot, 0, threshold);
  CHECK(policy.count() == 3);
  CHECK(policy.current() && std::string(policy.current()->title) == "Week" && policy.current()->severity == 2);
  policy.acknowledge(*policy.current()); policy.update(snapshot, 0, threshold);
  CHECK(policy.current() && std::string(policy.current()->provider) == "zcode");
  snapshot.viewCount = 1; policy.update(snapshot, 0, threshold);
  CHECK(policy.count() == 1 && std::string(policy.current()->provider) == "codex");
  policy.acknowledge(*policy.current());
  snapshot.views[0].showsRemaining = false; snapshot.views[0].rows[0].usedPercent = 95;
  policy.update(snapshot, 0, threshold);
  CHECK(policy.current() && policy.current()->remaining == 5 && policy.current()->severity == 2);
}

static void night_time_components_and_midnight_wrap() {
  CHECK(app_settings::adjust_night_time(0, false, -1) == 1439);
  CHECK(app_settings::adjust_night_time(1439, false, 1) == 0);
  CHECK(app_settings::adjust_night_time(15, true, -1) == 1395);
  CHECK(app_settings::adjust_night_time(22 * 60 + 15, true, 1) == 23 * 60 + 15);
  CHECK(app_settings::adjust_night_time(6 * 60 + 44, false, 1) == 6 * 60 + 45);
}

static void nova_activity_and_mood_are_based_on_real_data() {
  aim::ProtoCore core;
  uint32_t now = 100; core.tick = [&now] { return now; };
  feed(core, "{\"cmd\":\"get_info\"}\n");
  CHECK(core.out().find("\"hostActivity\":true") != std::string::npos);
  feed(core, frame("[{\"usedPercent\":20}]"));
  now = 500;
  feed(core, "{\"cmd\":\"host_activity\",\"state\":\"fetching\",\"message\":\"Fetching provider data\"}\n");
  CHECK(core.snapshot().activity == aim::HostActivity::fetching);
  CHECK(core.snapshot().lastFrameMs == 100 && core.snapshot().views[0].quotaReceivedMs == 100);
  CHECK(core.snapshot().frameCount == 1);
  feed(core, "{\"cmd\":\"host_activity\",\"state\":\"updated\"}\n");
  CHECK(core.snapshot().activity == aim::HostActivity::updated);
  feed(core, "{\"cmd\":\"host_activity\",\"state\":false}\n");
  feed(core, "{\"cmd\":\"host_activity\",\"state\":\"invented\"}\n");
  CHECK(core.snapshot().activity == aim::HostActivity::updated);
  NovaState state;
  const auto warning = [](const char*, const aim::Row&) { return uint8_t{25}; };
  CHECK(state.evaluate(core.snapshot(), now, false, warning) == NovaMood::ready);
  CHECK(state.evaluate(core.snapshot(), now + 5000, false, warning) == NovaMood::ready);
  CHECK(state.evaluate(core.snapshot(), now, true, warning) == NovaMood::ready);
  auto snapshot = core.snapshot(); snapshot.activity = aim::HostActivity::fetching;
  CHECK(state.evaluate(snapshot, now, false, warning) == NovaMood::ready);
  CHECK(state.evaluate(snapshot, now + 60000, false, warning) == NovaMood::ready);
  snapshot.activity = aim::HostActivity::idle; snapshot.views[0].showsRemaining = true;
  snapshot.views[0].rows[0].usedPercent = 24;
  CHECK(state.evaluate(snapshot, now, false, warning) == NovaMood::low);
  snapshot.views[0].rows[0].usedPercent = 5;
  CHECK(state.evaluate(snapshot, now, false, warning) == NovaMood::critical);
  snapshot.views[0].notice = true;
  CHECK(state.evaluate(snapshot, now, false, warning) == NovaMood::issue);
  snapshot.views[0].notice = false;
  CHECK(state.evaluate(snapshot, 300100, false, warning) == NovaMood::waiting);
  snapshot.hostPresent = false;
  CHECK(state.evaluate(snapshot, now, false, warning) == NovaMood::offline);
  state.greet(now);
  CHECK(state.evaluate(snapshot, now + 1, false, warning) == NovaMood::greeting);
  CHECK(state.evaluate(snapshot, now + 2200, false, warning) == NovaMood::offline);
}

static void nova_follows_tokens_not_screen_dimming_or_fetching() {
  aim::ProtoCore core;
  uint32_t now = 100; core.tick = [&now] { return now; };
  feed(core, frame("[{\"usedPercent\":20}]"));
  feed(core, "{\"cmd\":\"token_activity\",\"known\":true,\"seen\":true,\"sources\":3,\"idleSeconds\":0,\"delta\":500}\n");
  CHECK(core.snapshot().tokenUsageKnown && core.snapshot().lastTokenDelta == 500);
  CHECK(core.snapshot().views[0].quotaReceivedMs == 100 && core.snapshot().frameCount == 1);
  core.clear_out();
  feed(core, "{\"cmd\":\"get_info\"}\n");
  JsonDocument info;
  CHECK(!deserializeJson(info, core.out()));
  CHECK(info["tokenKnown"] == true && info["tokenSeen"] == true);
  CHECK(info["tokenSources"] == 3 && info["tokenDelta"] == 500);
  NovaState state;
  const auto warning = [](const char*, const aim::Row&) { return uint8_t{25}; };
  CHECK(state.evaluate(core.snapshot(), now, true, warning) == NovaMood::working);  // dimmed screen, active tokens
  auto lowQuota = core.snapshot(); lowQuota.views[0].showsRemaining = true; lowQuota.views[0].rows[0].usedPercent = 5;
  CHECK(state.evaluate(lowQuota, now, true, warning) == NovaMood::working);  // token use must be visible despite a critical quota
  auto snapshot = core.snapshot();
  snapshot.tokenIdleSeconds = 90; CHECK(state.evaluate(snapshot, now, true, warning) == NovaMood::updated);
  snapshot.tokenIdleSeconds = 100; CHECK(state.evaluate(snapshot, now, true, warning) == NovaMood::ready);
  snapshot.tokenIdleSeconds = 300; CHECK(state.evaluate(snapshot, now, false, warning) == NovaMood::resting);
  snapshot.tokenUsageKnown = false; CHECK(state.evaluate(snapshot, now, true, warning) == NovaMood::ready);
  snapshot.tokenUsageKnown = true; CHECK(state.evaluate(snapshot, 35100, true, warning) == NovaMood::ready);  // old activity is unknown
  snapshot.tokenActivityMs = 0xfffffff0u; snapshot.tokenIdleSeconds = 0;
  CHECK(state.evaluate(snapshot, 16, true, warning) == NovaMood::working);
  feed(core, "{\"cmd\":\"token_activity\",\"known\":true,\"seen\":true,\"sources\":3,\"idleSeconds\":-1,\"delta\":500}\n");
  CHECK(core.snapshot().tokenIdleSeconds == 0);
}

static void token_presentation_handles_stale_sources_large_counts_and_wraparound() {
  aim::Snapshot snapshot{}; snapshot.hostPresent = snapshot.tokenUsageKnown = snapshot.tokenUsageSeen = true;
  snapshot.tokenSourceMask = 3; snapshot.tokenActivityMs = 0xfffffff0u; snapshot.tokenIdleSeconds = 2;
  char value[128];
  CHECK(token_signal_fresh(snapshot, 16));
  CHECK(std::string(token_tracking_label(snapshot, 16)) == "TRACKING / Codex + ZCode");
  token_activity_hint(snapshot, 1016, value, sizeof(value));
  CHECK(std::string(value).find("Last increase: 3 s ago") == 0);
  CHECK(token_signal_fresh(snapshot, 16000));  // max poll interval plus jitter
  CHECK(std::string(token_tracking_label(snapshot, 35000)) == "TRACKING / signal lost");
  snapshot.tokenUsageKnown = false;
  CHECK(std::string(token_tracking_label(snapshot, 16)) == "TRACKING / no counters");
  snapshot.hostPresent = false;
  CHECK(std::string(token_tracking_label(snapshot, 16)) == "TRACKING / PC host offline");
  format_token_count(999, value, sizeof(value)); CHECK(std::string(value) == "999");
  format_token_count(1000, value, sizeof(value)); CHECK(std::string(value) == "1.0K");
  format_token_count(1999, value, sizeof(value)); CHECK(std::string(value) == "1.9K");
  format_token_count(UINT64_MAX, value, sizeof(value)); CHECK(std::string(value) == "18.4E");
  char small[4]; format_token_count(UINT64_MAX, small, sizeof(small)); CHECK(small[3] == '\0');
}

static void nova_uses_selected_provider_token_sources() {
  aim::Snapshot snapshot{};
  snapshot.hostPresent = snapshot.viewsConfigured = true;
  snapshot.viewCount = 1; snapshot.tokenUsageKnown = snapshot.tokenUsageSeen = true;
  snapshot.tokenActivityMs = 100; snapshot.tokenIdleSeconds = 0;
  std::strcpy(snapshot.viewKeys[0], "copilot");
  auto& view = snapshot.views[0]; view.valid = view.notice = view.informational = true;
  std::strcpy(view.providerKey, "copilot");
  NovaState state; const auto warning = [](const char*, const aim::Row&) { return uint8_t{25}; };
  snapshot.tokenSourceMask = 1;
  CHECK(state.evaluate(snapshot, 100, false, warning) == NovaMood::waiting);
  snapshot.tokenIdleSeconds = 100;
  CHECK(state.evaluate(snapshot, 100, false, warning) == NovaMood::waiting);
  snapshot.tokenSourceMask = 16;
  CHECK(state.evaluate(snapshot, 100, false, warning) == NovaMood::ready);
  snapshot.tokenIdleSeconds = 0;
  CHECK(state.evaluate(snapshot, 100, false, warning) == NovaMood::working);
  snapshot.viewCount = 0;
  CHECK(state.evaluate(snapshot, 100, false, warning) == NovaMood::waiting);
  snapshot.viewsConfigured = false;
  CHECK(state.evaluate(snapshot, 100, false, warning) == NovaMood::working);  // legacy aggregate signal
}

int main() {
  text_sanitization_collapses_utf8_and_bounds_malformed_input();
  nova_uses_selected_provider_token_sources();
  const char* activityKeys[] = {"codex", "zcode", "claude", "gemini", "copilot", "cursor", "antigravity", "opencode"};
  for (unsigned i = 0; i < 8; ++i) CHECK(aim::provider_style(activityKeys[i])->activityMask == (1u << i));
  {
    aim::ProtoCore core; core.tick = [] { return 100u; };
    feed(core, "{\"cmd\":\"token_activity\",\"known\":true,\"seen\":true,\"sources\":255,\"idleSeconds\":0,\"delta\":45}\n");
    CHECK(core.snapshot().tokenSourceMask == 255);
    feed(core, "{\"data\":[{\"provider\":\"claude\",\"notice\":\"Activity only\",\"informational\":true}]}\n");
    CHECK(core.snapshot().views[0].informational && !core.snapshot().views[0].hasUsage);
    NovaState state; auto warning = [](const char*, const aim::Row&) { return uint8_t{25}; };
    CHECK(state.evaluate(core.snapshot(), 100, false, warning) == NovaMood::working);
    auto snapshot = core.snapshot(); snapshot.tokenIdleSeconds = 100;
    CHECK(state.evaluate(snapshot, 100, false, warning) == NovaMood::ready);
    CHECK(std::string(token_tracking_label(snapshot, 100)) == "TRACKING / multiple sources");
    core.clear_out();
    feed(core, "{\"data\":[{\"provider\":\"opencode\",\"notice\":\"Setup\",\"informational\":\"bad\"}]}\n");
    CHECK(core.out().find("invalid informational flag") != std::string::npos);
  }
  timestamp_and_ack();
  invalid_frame_keeps_snapshot();
  set_views_clears_old_data_and_rejects_bad_keys();
  brightness_rejects_invalid_values();
  framing_timeout_and_overflow_recover();
  brightness_honors_persistence_and_queue_failure();
  notices_and_clock_sync();
  fallback_rows_and_three_row_cap();
  dim_timeout_wake_and_wraparound();
  view_mode_and_firmware_identity();
  framed_identity_and_types_are_checked();
  active_slow_transfer_is_not_a_stall();
  heartbeat_tracks_link_without_refreshing_quota();
  reply_queue_and_header_limits();
  oversized_plain_frame_is_rejected();
  rows_beyond_protocol_cap_do_not_invalidate_supported_rows();
  reset_countdown_types_and_wraparound();
  manual_refresh_lifecycle_and_timeout();
  history_is_bounded_normalized_and_provider_specific();
  history_expires_offline_and_does_not_join_outages();
  retained_quota_and_refresh_feedback();
  night_schedule_clock_and_boundaries();
  quota_precision_and_bidirectional_fades();
  notifications_acknowledge_escalate_and_rearm_after_recovery();
  notifications_prioritize_each_window_and_ignore_removed_views();
  night_time_components_and_midnight_wrap();
  nova_activity_and_mood_are_based_on_real_data();
  nova_follows_tokens_not_screen_dimming_or_fetching();
  token_presentation_handles_stale_sources_large_counts_and_wraparound();
  if (failures) { std::cerr << failures << " failed checks\n"; return EXIT_FAILURE; }
  std::cout << "Protocol, token-driven NOVA, quota notification, dimming, precision, night and history scenarios passed\n";
}
