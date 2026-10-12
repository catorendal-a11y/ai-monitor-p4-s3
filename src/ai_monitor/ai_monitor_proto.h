#pragma once
// AI Monitor serial protocol core — pure C++, no Arduino / FreeRTOS / Serial.
//
// Everything protocol-level lives here so it can be unit-tested on the host
// (test/test_aimonitor): the info handshake, AIM1 length-prefixed framing,
// set_views/view_state, notice frames, ack/error replies and the byte-level
// line assembly. The firmware wrapper (ai_monitor.cpp) only wires Serial,
// millis/heap and synchronized snapshot publication around this class.
//
// Reference: tobymarks/esp32-ai-monitor docs/serial-protocol.md,
// protocol level 2.23.0 (plain line mode + AIM1 framing, schemaVersion 1).

#include <ArduinoJson.h>

#include <cstdarg>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <climits>
#include <cstdio>
#include <cstring>
#include <functional>
#include <string>

#include "ai_monitor.h"
#include "../board_profile.h"
#include "../diagnostics/hardware_types.h"
#include "../diagnostics/graphics_types.h"
#include "../diagnostics/ppa_benchmark.h"

namespace aim {

class ProtoCore {
 public:
  // Injected by the owner (firmware: millis()/ESP.getFreeHeap(); tests: fakes).
  std::function<uint32_t()> tick = [] { return 0u; };
  std::function<uint32_t()> heap = [] { return 0u; };
  std::function<uint32_t()> psram_free = [] { return 0u; };
  std::function<diagnostics::HardwareBaseline()> hardware;
  std::function<diagnostics::GraphicsSnapshot()> graphics;
  std::function<diagnostics::PpaBenchmark()> ppa_benchmark;
  const char* firmware_version = "unknown";
  uint32_t boot_id = 0;
  // Reported in the info handshake (percent 0-100).
  std::function<uint8_t()> brightness = [] { return 100u; };
  // Applied when the companion sends set_brightness (percent 0-100).
  std::function<bool(uint8_t, bool)> apply_brightness;

  void set_mac(const char* mac) { strlcpy_local(mac_, mac, sizeof(mac_)); }

  static constexpr uint32_t kAim1MaxPayload = 4095;  // protocol Spec 1
  static constexpr uint32_t kAim1ResyncMs = 2000;
  static constexpr uint32_t kHeartbeatTimeoutMs = 60000;
  static constexpr size_t kMaxReplyBytes = 8192;
  // Compatibility version for the companion's view/notice/ack feature set.
  static constexpr const char* kReportedVersion = "2.23.0";

  const Snapshot& snapshot() const { return snap_; }
  // Bumped on every snapshot state change; the owner publishes only on change.
  uint32_t snapshot_revision() const { return revision_; }
  // Bytes to transmit to the host (cleared by the owner after sending).
  const std::string& out() const { return out_; }
  void clear_out() { out_.clear(); }
  void consume_out(size_t bytes) { out_.erase(0, bytes); }
  void request_refresh() {
    if (refresh_pending()) return;
    if (!snap_.hostPresent || !snap_.manualRefreshSupported) {
      snap_.refreshState = RefreshState::failed;
      snap_.refreshCompletedMs = tick();
      copy_capped(snap_.refreshMessage, sizeof(snap_.refreshMessage), "Start the updated PC host to refresh");
      touch();
      return;
    }
    if (++snap_.refreshId == 0) ++snap_.refreshId;
    snap_.refreshState = RefreshState::requested;
    snap_.refreshRequestedMs = tick();
    copy_capped(snap_.refreshMessage, sizeof(snap_.refreshMessage), "Refresh requested");
    touch();
    emitf("{\"type\":\"refresh_request\",\"requestId\":%u}\n", (unsigned)snap_.refreshId);
  }

  // Periodic housekeeping (framed-transfer stall resync). Call from the owner
  // loop; cheap enough to run every iteration.
  bool poll() {
    const uint32_t now = tick();
    bool changed = false;
    if (framed_ && now - framedLastByteMs_ > kAim1ResyncMs) {
      framed_ = false;
      lineLen_ = 0;
      lineOverflow_ = false;
    }
    const uint32_t timeout = heartbeatEnabled_ ? kHeartbeatTimeoutMs : 300000u;
    if (snap_.hostPresent && now - snap_.hostSeenMs >= timeout) {
      snap_.hostPresent = false;
      changed = true;
      touch();
    }
    if (refresh_pending() && (!snap_.hostPresent || now - snap_.refreshRequestedMs >= 70000u)) {
      snap_.refreshState = RefreshState::failed;
      snap_.refreshCompletedMs = now;
      copy_capped(snap_.refreshMessage, sizeof(snap_.refreshMessage), "Host did not complete the update");
      changed = true;
      touch();
    }
    return changed;
  }

  void feed_byte(char c) {
    if (framed_) {
      framedLastByteMs_ = tick();
      payload_[payloadLen_++] = c;
      if (payloadLen_ >= framedRemaining_) {
        payload_[payloadLen_] = '\0';
        framed_ = false;
        JsonDocument doc;
        if (deserializeJson(doc, payload_, payloadLen_) == DeserializationError::Ok) {
          handle_frame(doc, payloadLen_, framedHeaderId_);
        } else {
          reply_error(framedHeaderId_, 1, "JSON parse error");
        }
      }
      return;
    }
    if (c == '\0') { lineOverflow_ = true; return; }
    if (c == '\n') {
      line_[lineLen_ < sizeof(line_) ? lineLen_ : sizeof(line_) - 1] = '\0';
      const bool overflow = lineOverflow_;
      lineLen_ = 0;
      lineOverflow_ = false;
      if (overflow) reply_error(-1, 0, "line exceeds maxFrameBytes");
      else handle_line(line_);
      return;
    }
    if (lineLen_ + 1 < sizeof(line_)) {
      line_[lineLen_++] = c;
    } else {
      lineOverflow_ = true;  // oversize line: discard on next newline
    }
  }

 private:
  bool refresh_pending() const {
    return snap_.refreshState == RefreshState::requested || snap_.refreshState == RefreshState::waiting || snap_.refreshState == RefreshState::updating;
  }
  void touch() { ++revision_; }
  Snapshot snap_{};
  uint32_t revision_ = 0;
  std::string out_;
  char mac_[18] = "00:00:00:00:00:00";

  // strlcpy/bsd helpers are absent on native platforms — local versions.
  static void strlcpy_local(char* dst, const char* src, size_t cap) {
    if (!dst || cap == 0) return;
    size_t i = 0;
    for (; i + 1 < cap && src[i]; ++i) dst[i] = src[i];
    dst[i] = '\0';
  }

  // Unsupported Unicode is one display character, not one replacement per
  // UTF-8 byte. Validate scalar encodings; malformed bytes consume one byte.
  // Short-circuiting at each NUL prevents reads beyond a truncated C string.
  static size_t utf8_span(const unsigned char* src) {
    const unsigned char first = src[0];
    if (first < 0xC2 || first > 0xF4) return 1;
    const unsigned char second = src[1];
    if (second < 0x80 || second > 0xBF) return 1;
    if (first <= 0xDF) return 2;
    if ((first == 0xE0 && second < 0xA0) || (first == 0xED && second > 0x9F) ||
        (first == 0xF0 && second < 0x90) || (first == 0xF4 && second > 0x8F)) return 1;
    const unsigned char third = src[2];
    if (third < 0x80 || third > 0xBF) return 1;
    if (first <= 0xEF) return 3;
    const unsigned char fourth = src[3];
    return fourth >= 0x80 && fourth <= 0xBF ? 4 : 1;
  }

  char line_[kAim1MaxPayload + 8] = {0};
  size_t lineLen_ = 0;
  bool lineOverflow_ = false;
  char payload_[kAim1MaxPayload + 1] = {0};
  size_t payloadLen_ = 0;
  bool framed_ = false;
  uint32_t framedRemaining_ = 0;
  int framedHeaderId_ = -1;
  uint32_t framedLastByteMs_ = 0;
  bool heartbeatEnabled_ = false;

  // view configuration echoed back in view_state (RAM only; the companion
  // restores its configuration after (re)connect, so persisting is not needed)
  char viewKeys_[kMaxViews][16] = {};
  uint8_t viewCount_ = 0;
  bool viewsAutomatic_ = false;
  uint16_t viewInterval_ = 10;
  uint8_t viewActive_ = 0;

  // ─────────────────────────────────────────────────────────────────────────────
  // OUTPUT HELPERS
  // ─────────────────────────────────────────────────────────────────────────────
  void emit(const char* text) {
    const size_t length = strlen(text);
    if (length <= kMaxReplyBytes - out_.size()) out_.append(text, length);
  }

  void emitf(const char* fmt, ...) {
    char buf[1024];
    va_list args;
    va_start(args, fmt);
    const int length = vsnprintf(buf, sizeof(buf), fmt, args);
    va_end(args);
    if (length >= 0 && static_cast<size_t>(length) < sizeof(buf)) emit(buf);
  }

  void note_host_seen() {
    snap_.hostPresent = true;
    snap_.hostSeenMs = tick();
    touch();
  }

  void reply_error(int frameId, int schemaVersion, const char* message) {
    if (frameId >= 0) {
      emitf("{\"type\":\"error\",\"frameId\":%d,\"schemaVersion\":%d,\"message\":\"%s\"}\n", frameId,
            schemaVersion, message ? message : "unknown");
    } else {
      emitf("{\"type\":\"error\",\"message\":\"%s\"}\n", message ? message : "unknown");
    }
  }

  void print_view_state() {
    JsonDocument doc;
    doc["type"] = "view_state";
    doc["mode"] = viewsAutomatic_ ? "automatic" : "manual";
    doc["interval"] = viewInterval_;
    doc["active"] = viewActive_;
    JsonArray views = doc["views"].to<JsonArray>();
    for (uint8_t i = 0; i < viewCount_; ++i) views.add(viewKeys_[i]);
    std::string reply;
    serializeJson(doc, reply);
    reply.push_back('\n');
    emit(reply.c_str());
  }

  void reply_info() {
    emitf("{\"type\":\"info\",\"version\":\"%s\",\"firmwareVersion\":\"%s\",\"bootId\":%u,\"mac\":\"%s\","
          "\"display\":\"%s\",\"panel\":\"%s\",\"panelId\":\"%s\",\"boardId\":\"%s\",\"chip\":\"%s\","
          "\"experimental\":%s,\"brightnessControl\":\"%s\","
          "\"orientation\":\"landscape\",\"theme\":\"dark\",\"language\":\"en\",\"brightness\":%u,"
          "\"serialTransport\":\"line\",\"maxFrameBytes\":%u,\"hostActivity\":true,\"tokenActivity\":true,\"providerSelection\":true,\"sessionActivity\":true,"
          "\"uptime\":%lu,\"heap\":%u,\"psramFree\":%u,\"tokenKnown\":%s,\"tokenSeen\":%s,\"tokenSources\":%u,\"tokenIdleSeconds\":%u,\"tokenDelta\":%llu,\"tokenAgeSeconds\":%lu}\n",
          kReportedVersion, firmware_version, (unsigned)boot_id, mac_, board_profile::display, board_profile::panel,
          board_profile::panel_id, board_profile::id, board_profile::chip, board_profile::experimental ? "true" : "false",
          board_profile::brightness_control, (unsigned)brightness(), (unsigned)kAim1MaxPayload,
          (unsigned long)(tick() / 1000u), (unsigned)heap(), (unsigned)psram_free(), snap_.tokenUsageKnown ? "true" : "false", snap_.tokenUsageSeen ? "true" : "false",
          (unsigned)snap_.tokenSourceMask, (unsigned)snap_.tokenIdleSeconds, static_cast<unsigned long long>(snap_.lastTokenDelta),
          static_cast<unsigned long>((tick()-snap_.tokenActivityMs)/1000u));
    note_host_seen();
  }

  void reply_hardware() {
    if (!hardware) { reply_error(-1, 0, "hardware diagnostics unavailable"); return; }
    const auto value = hardware();
    JsonDocument reply;
    reply["type"] = "hardware"; reply["schema"] = 1;
    reply["boardId"] = board_profile::id; reply["chip"] = board_profile::chip;
    reply["firmwareVersion"] = firmware_version; reply["chipRevision"] = value.chipRevision;
    reply["bootId"] = boot_id; reply["uptimeMs"] = tick();
    reply["cpuMHz"] = value.cpuMHz; reply["sdkVersion"] = value.sdkVersion;
    auto flash = reply["flash"].to<JsonObject>();
    flash["bytes"] = value.flashBytes; flash["frequencyHz"] = value.flashHz;
    flash["applicationBytes"] = value.applicationBytes; flash["partitionBytes"] = value.partitionBytes;
    flash["partitionOffset"] = value.partitionOffset;
    flash["freeApplicationBytes"] = value.applicationBytes<=value.partitionBytes ?
      value.partitionBytes-value.applicationBytes : 0;
    auto heap = reply["internalHeap"].to<JsonObject>();
    heap["total"] = value.heapTotal; heap["free"] = value.heapFree;
    heap["minimumFree"] = value.heapMinimum; heap["largestFreeBlock"] = value.heapLargest;
    auto psram = reply["psram"].to<JsonObject>();
    psram["sizeBytes"] = value.psramSize; psram["heapTotal"] = value.psramTotal; psram["free"] = value.psramFree;
    psram["minimumFree"] = value.psramMinimum; psram["largestFreeBlock"] = value.psramLargest;
    auto display = reply["display"].to<JsonObject>();
    display["width"] = 800; display["height"] = 480; display["color"] = "RGB565";
    display["drawBytes"] = value.display.drawBytes; display["drawCount"] = value.display.drawCount;
    display["rotationBytes"] = value.display.rotationBytes;
    display["framebufferBytes"] = value.display.framebufferBytes;
    display["framebufferCount"] = value.display.framebufferCount; display["bounceBytes"] = value.display.bounceBytes;
    auto hosted = reply["hosted"].to<JsonObject>();
    hosted["compiled"] = value.hostedCompiled; hosted["hostVersion"] = value.hostedVersion;
    hosted["probeState"] = "not-probed"; hosted["coprocessorVersion"] = nullptr;
    hosted["detectedChip"] = nullptr;
    auto ppa = reply["ppa"].to<JsonObject>();
    ppa["supported"] = value.ppaSupported; ppa["active"] = false;
    auto stages=reply["startupMemory"].to<JsonArray>();
    for (unsigned i=0;i<4;++i) {
      const auto& checkpoint=value.startup.checkpoints[i];
      auto stage=stages.add<JsonObject>();
      stage["stage"]=diagnostics::startup_stage_names[i]; stage["captured"]=checkpoint.captured;
      if (!checkpoint.captured) continue;
      stage["uptimeMs"]=checkpoint.uptimeMs;
      const auto addMemory=[&](const char* name,const diagnostics::MemoryReading& reading) {
        auto memory=stage[name].to<JsonObject>();
        memory["total"]=reading.total; memory["free"]=reading.free;
        memory["minimumFree"]=reading.minimum; memory["largestFreeBlock"]=reading.largest;
      };
      addMemory("internalHeap",checkpoint.internal); addMemory("psram",checkpoint.psram);
    }
    if (measureJson(reply) > kAim1MaxPayload) { reply_error(-1, 0, "hardware reply exceeds limit"); return; }
    std::string output; serializeJson(reply, output); output.push_back('\n'); emit(output.c_str());
  }

  void reply_graphics() {
    if (!graphics) { reply_error(-1, 0, "graphics telemetry unavailable"); return; }
    const auto value = graphics(); const auto& data = value.counters;
    JsonDocument reply;
    reply["type"] = "graphics"; reply["schema"] = 1; reply["enabled"] = value.enabled;
    reply["bootId"] = boot_id; reply["uptimeMs"] = tick();
    reply["flushCalls"] = data.flushCalls; reply["pixelsSubmitted"] = data.pixels;
    reply["rotationUs"] = data.rotateUs; reply["submissionUs"] = data.submitUs;
    reply["maxRotationUs"] = data.maxRotateUs; reply["maxSubmissionUs"] = data.maxSubmitUs;
    reply["saturated"] = data.saturated;
    reply["displayRefreshHz"] = nullptr;  // Submission timing is not scanout/VSYNC timing.
    reply["ppaActive"] = false;
    std::string output; serializeJson(reply, output); output.push_back('\n'); emit(output.c_str());
  }

  void reply_ack(int frameId, int schemaVersion, size_t bytes, const char* label, unsigned rows) {
    if (frameId < 0) return;
    emitf("{\"type\":\"ack\",\"frameId\":%d,\"schemaVersion\":%d,\"message\":\"accepted\","
          "\"bytes\":%u,\"provider\":\"%s\",\"rows\":%u,\"heap\":%u}\n",
          frameId, schemaVersion, (unsigned)bytes, label, rows, (unsigned)heap());
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // FRAME PARSING
  // ─────────────────────────────────────────────────────────────────────────────
  static void copy_capped(char* dst, size_t cap, const char* src) {
    if (!dst || cap == 0) return;
    if (!src) {
      dst[0] = '\0';
      return;
    }
    const auto* input = reinterpret_cast<const unsigned char*>(src);
    size_t output = 0;
    while (*input && output + 1 < cap) {
      const unsigned char value = *input;
      const size_t consumed = value < 0x80 ? 1 : utf8_span(input);
      dst[output++] = value >= 0x20 && value <= 0x7E ? static_cast<char>(value) : '?';
      input += consumed;
    }
    dst[output] = '\0';
  }

  // "2026-04-10T15:00:00Z" -> "15:00"; other formats are kept as-is (capped).
  static void short_reset(const char* iso, char* outBuf, size_t cap) {
    if (!outBuf || cap == 0) return;
    outBuf[0] = '\0';
    if (!iso || !iso[0]) return;
    const char* t = strlen(iso) >= 16 && iso[4] == '-' && iso[7] == '-' && iso[10] == 'T' ? iso + 10 : nullptr;
    if (t) {
      size_t n = 0;
      for (const char* p = t + 1; *p && n < 5 && n < cap - 1; ++p, ++n) outBuf[n] = *p;
      outBuf[n] = '\0';
      copy_capped(outBuf, cap, outBuf);  // malformed ISO text still stays ASCII
      return;
    }
    copy_capped(outBuf, cap, iso);
  }

  static bool parse_usage_rows(JsonObject usage, ViewData& view) {
    view.rowCount = 0;
    JsonArray rows = usage["rows"];
    if (!rows.isNull()) {
      for (JsonObject row : rows) {
        if (view.rowCount >= kMaxRows) break;
        if (row.isNull()) return false;
        Row& r = view.rows[view.rowCount];
        if (!row["usedPercent"].is<float>()) return false;
        r.usedPercent = row["usedPercent"].as<float>();
        if (!std::isfinite(r.usedPercent) || r.usedPercent < 0 || r.usedPercent > 100) return false;
        copy_capped(r.title, sizeof(r.title), row["title"] | (const char*)"");
        short_reset(row["resetsAt"] | (const char*)"", r.resetsShort, sizeof(r.resetsShort));
        // windowMinutes identifies a quota window (matching, NVS rules); reject
        // wrong types instead of silently coercing them to 0.
        if (!row["windowMinutes"].isNull() && !row["windowMinutes"].is<uint32_t>()) return false;
        r.windowMinutes = row["windowMinutes"] | 0u;
        if (!row["resetSeconds"].isNull()) {
          if (!row["resetSeconds"].is<uint32_t>()) return false;
          r.hasResetCountdown = true;
          r.resetSeconds = row["resetSeconds"].as<uint32_t>();
        }
        r.valid = true;
        view.rowCount++;
      }
    }
    if (view.rowCount == 0) {
      // Fallback for hosts that only send primary/secondary/tertiary blocks.
      static const char* kBlocks[3] = {"primary", "secondary", "tertiary"};
      for (size_t i = 0; i < 3; ++i) {
        JsonObject block = usage[kBlocks[i]];
        if (block.isNull()) continue;
        Row& r = view.rows[view.rowCount];
        if (!block["usedPercent"].is<float>()) return false;
        r.usedPercent = block["usedPercent"].as<float>();
        if (!std::isfinite(r.usedPercent) || r.usedPercent < 0 || r.usedPercent > 100) return false;
        copy_capped(r.title, sizeof(r.title), kBlocks[i]);
        short_reset(block["resetsAt"] | (const char*)"", r.resetsShort, sizeof(r.resetsShort));
        if (!block["windowMinutes"].isNull() && !block["windowMinutes"].is<uint32_t>()) return false;
        r.windowMinutes = block["windowMinutes"] | 0u;
        if (!block["resetSeconds"].isNull()) {
          if (!block["resetSeconds"].is<uint32_t>()) return false;
          r.hasResetCountdown = true;
          r.resetSeconds = block["resetSeconds"].as<uint32_t>();
        }
        r.valid = true;
        view.rowCount++;
        if (view.rowCount >= kMaxRows) break;
      }
    }
    return view.rowCount > 0;
  }

  static void normalize_key(char* key) {
    for (char* p = key; *p; ++p) {
      if (*p >= 'A' && *p <= 'Z') *p = static_cast<char>(*p - 'A' + 'a');
    }
  }

  void handle_frame(JsonDocument& doc, size_t rawLen, int headerId = -1) {
    const int frameId = doc["frameId"] | headerId;
    if (!doc["frameId"].isNull() && (!doc["frameId"].is<int>() || frameId < 0)) {
      reply_error(headerId, 0, "invalid frameId");
      return;
    }
    if (headerId >= 0 && frameId != headerId) {
      reply_error(headerId, 0, "frameId does not match AIM1 header");
      return;
    }
    const int schemaVersion = doc["schemaVersion"] | 0;
    if ((!doc["schemaVersion"].isNull() && !doc["schemaVersion"].is<int>()) || schemaVersion < 0 || schemaVersion > 1) {
      reply_error(frameId, schemaVersion, "unsupported schemaVersion");
      return;
    }

    JsonObject data0 = doc["data"][0];
    if (data0.isNull()) {
      reply_error(frameId, schemaVersion, "Missing data[0]");
      return;
    }
    if (!data0["pluginId"].isNull()) {
      // Never advertised (sceneProtocol absent in info), so the companion
      // should not send these; reject cleanly if a future one does.
      reply_error(frameId, schemaVersion, "plugin scenes not supported");
      return;
    }

    char key[16];
    if (!data0["provider"].isNull() && !data0["provider"].is<const char*>()) {
      reply_error(frameId, schemaVersion, "invalid provider");
      return;
    }
    copy_capped(key, sizeof(key), data0["provider"] | (const char*)"claude");
    normalize_key(key);
    const ProviderStyle* style = provider_style(key);
    if (!style) {
      reply_error(frameId, schemaVersion, "unsupported provider");
      return;
    }

    int viewIndex = data0["viewIndex"] | 0;
    if ((!data0["viewIndex"].isNull() && !data0["viewIndex"].is<int>()) || viewIndex < 0 || viewIndex >= (int)kMaxViews) {
      reply_error(frameId, schemaVersion, "invalid viewIndex");
      return;
    }
    if (snap_.viewsConfigured && (viewIndex >= viewCount_ || strcmp(key, viewKeys_[viewIndex]) != 0)) {
      reply_error(frameId, schemaVersion, "provider does not match configured view");
      return;
    }

    ViewData view;
    if ((!data0["fetching"].isNull() && !data0["fetching"].is<bool>()) ||
        (!data0["notice"].isNull() && !data0["notice"].is<const char*>())) {
      reply_error(frameId, schemaVersion, "invalid fetching or notice");
      return;
    }
    view.valid = true;
    view.fetching = data0["fetching"] | false;
    copy_capped(view.providerKey, sizeof(view.providerKey), key);
    copy_capped(view.providerLabel, sizeof(view.providerLabel), style->label);

    const char* notice = data0["notice"] | (const char*)"";
    if (notice[0] != '\0') {
      if (!data0["informational"].isNull() && !data0["informational"].is<bool>()) {
        reply_error(frameId, schemaVersion, "invalid informational flag"); return;
      }
      view.notice = true;
      view.informational = data0["informational"] | false;
      copy_capped(view.message, sizeof(view.message), notice);
      store_clock(doc);
      store_view((uint8_t)viewIndex, view);
      reply_ack(frameId, schemaVersion, rawLen, style->label, 0);
      return;
    }

    JsonObject usage = data0["usage"];
    if (!usage.isNull()) {
      if (!usage["percentMode"].isNull() && !usage["percentMode"].is<const char*>()) {
        reply_error(frameId, schemaVersion, "invalid percentMode");
        return;
      }
      const char* percentMode = usage["percentMode"] | (const char*)"used";
      view.showsRemaining = (strcmp(percentMode, "remaining") == 0);
      if (strcmp(percentMode, "used") != 0 && !view.showsRemaining) {
        reply_error(frameId, schemaVersion, "invalid percentMode");
        return;
      }
      if (!parse_usage_rows(usage, view)) {
        reply_error(frameId, schemaVersion, "invalid usage rows");
        return;
      }
    } else if (!view.fetching) {
      reply_error(frameId, schemaVersion, "missing usage or notice");
      return;
    }

    store_clock(doc);
    store_view((uint8_t)viewIndex, view);
    reply_ack(frameId, schemaVersion, rawLen, style->label, view.rowCount);
  }

  void store_clock(JsonDocument& doc) {
    const char* value = doc["displayTime"] | (const char*)"";
    unsigned hour = 0, minute = 0;
    char extra = '\0';
    const int seconds = doc["displaySeconds"] | 0;
    if ((!doc["displaySeconds"].isNull() && !doc["displaySeconds"].is<int>()) || seconds < 0 || seconds > 59) return;
    if (strlen(value) == 5 && sscanf(value, "%2u:%2u%c", &hour, &minute, &extra) == 2 &&
        hour < 24 && minute < 60) {
      copy_capped(snap_.displayTime, sizeof(snap_.displayTime), value);
      snap_.displayTimeMs = tick();
      snap_.displaySeconds = static_cast<uint8_t>(seconds);
    }
  }

  void store_view(uint8_t viewIndex, const ViewData& view) {
    const uint32_t now = tick();
    const auto previous = snap_.views[viewIndex];
    snap_.views[viewIndex] = view;
    auto& stored = snap_.views[viewIndex];
    if (view.rowCount && !view.notice && !view.fetching) {
      stored.hasUsage = true;
      stored.quotaReceivedMs = now;
    } else if (previous.hasUsage && strcmp(previous.providerKey, view.providerKey) == 0) {
      stored.hasUsage = true;
      stored.quotaReceivedMs = previous.quotaReceivedMs;
      stored.showsRemaining = previous.showsRemaining;
      stored.rowCount = previous.rowCount;
      for (size_t r = 0; r < kMaxRows; ++r) stored.rows[r] = previous.rows[r];
    }
    snap_.views[viewIndex].receivedMs = now;
    snap_.lastFrameMs = now;
    note_host_seen();
    snap_.frameCount++;
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // COMMANDS
  // ─────────────────────────────────────────────────────────────────────────────
  void handle_command(JsonDocument& doc) {
    const char* cmd = doc["cmd"] | "";

    if (strcmp(cmd, "get_ppa_benchmark") == 0) {
      if (doc.size() != 1 || !ppa_benchmark) { reply_error(-1, 0, "PPA benchmark unavailable"); return; }
      const auto value = ppa_benchmark(); JsonDocument reply;
      reply["type"] = "ppa_benchmark"; reply["schema"] = 1; reply["status"] = value.status;
      reply["width"] = value.width; reply["height"] = value.height; reply["samples"] = value.samples;
      reply["cpuMedianUs"] = value.cpuMedianUs; reply["ppaMedianUs"] = value.ppaMedianUs;
      reply["bitExact"] = value.bitExact; reply["resourcesRetained"] = value.resourcesRetained;
      reply["isolated"] = true; reply["productionPpaActive"] = false;
      std::string output; serializeJson(reply, output); output.push_back('\n'); emit(output.c_str()); return;
    } else if (strcmp(cmd, "get_graphics") == 0) {
      if (doc.size() != 1) { reply_error(-1, 0, "invalid graphics telemetry options"); return; }
      reply_graphics(); return;
    } else if (strcmp(cmd, "get_hardware") == 0) {
      if (doc.size() != 1) { reply_error(-1, 0, "invalid hardware diagnostic options"); return; }
      reply_hardware();
      return;  // Diagnostics do not establish/renew a provider-host lease.
    } else if (strcmp(cmd, "get_info") == 0) {
      if (!doc["heartbeat"].isNull()) {
        if (!doc["heartbeat"].is<bool>()) { reply_error(-1, 0, "invalid heartbeat"); return; }
      }
      heartbeatEnabled_ = doc["heartbeat"] | false;
      if (!doc["manualRefresh"].isNull() && !doc["manualRefresh"].is<bool>()) {
        reply_error(-1, 0, "invalid manual refresh capability"); return;
      }
      snap_.manualRefreshSupported = doc["manualRefresh"] | false;
      store_clock(doc);
      reply_info();
    } else if (strcmp(cmd, "token_activity") == 0) {
      if (!doc["known"].is<bool>() || !doc["seen"].is<bool>() || !doc["sources"].is<uint8_t>() ||
          !doc["idleSeconds"].is<uint32_t>() || !doc["delta"].is<uint64_t>()) {
        reply_error(-1, 0, "invalid token activity"); return;
      }
      snap_.tokenUsageKnown = doc["known"].as<bool>(); snap_.tokenUsageSeen = doc["seen"].as<bool>();
      snap_.tokenSourceMask = doc["sources"].as<uint8_t>();
      snap_.tokenIdleSeconds = doc["idleSeconds"].as<uint32_t>(); snap_.tokenActivityMs = tick();
      if (doc["delta"].as<uint64_t>() > 0) snap_.lastTokenDelta = doc["delta"].as<uint64_t>();
      emit("{\"type\":\"ok\",\"cmd\":\"token_activity\"}\n");
    } else if (strcmp(cmd, "session_activity") == 0) {
      const JsonArrayConst providers = doc["providers"].as<JsonArrayConst>();
      if (providers.isNull() || providers.size() > kMaxViews) {
        reply_error(-1, 0, "invalid session activity"); return;
      }
      SessionCounts incoming[kMaxViews]{};
      uint8_t count = 0, sources = 0;
      for (const auto row : providers) {
        const auto* style = provider_style(row["provider"] | "");
        if (!row.is<JsonObjectConst>() || !row["provider"].is<const char*>() || !style ||
            (sources & style->activityMask) || !row["running"].is<uint16_t>() ||
            !row["waiting"].is<uint16_t>() || !row["completed"].is<uint16_t>() || !row["error"].is<uint16_t>()) {
          reply_error(-1, 0, "invalid session activity"); return;
        }
        const auto running = row["running"].as<uint16_t>(), waiting = row["waiting"].as<uint16_t>();
        const auto completed = row["completed"].as<uint16_t>(), error = row["error"].as<uint16_t>();
        if (static_cast<uint32_t>(running) + waiting + completed + error > 64u) {
          reply_error(-1, 0, "invalid session counts"); return;
        }
        incoming[count++] = SessionCounts{running, waiting, completed, error, style->activityMask};
        sources |= style->activityMask;
      }
      for (size_t i = 0; i < kMaxViews; ++i) snap_.sessions[i] = incoming[i];
      snap_.sessionCount = count; snap_.sessionActivityMs = tick();
      emit("{\"type\":\"ok\",\"cmd\":\"session_activity\"}\n");
    } else if (strcmp(cmd, "host_activity") == 0) {
      if (!doc["state"].is<const char*>() || (!doc["message"].isNull() && !doc["message"].is<const char*>())) {
        reply_error(-1, 0, "invalid host activity"); return;
      }
      const char* state = doc["state"];
      if (strcmp(state, "fetching") == 0) snap_.activity = HostActivity::fetching;
      else if (strcmp(state, "updated") == 0) snap_.activity = HostActivity::updated;
      else if (strcmp(state, "failed") == 0) snap_.activity = HostActivity::failed;
      else if (strcmp(state, "idle") == 0) snap_.activity = HostActivity::idle;
      else { reply_error(-1, 0, "invalid host activity state"); return; }
      snap_.activityMs = tick();
      copy_capped(snap_.activityMessage, sizeof(snap_.activityMessage), doc["message"] | "");
      emit("{\"type\":\"ok\",\"cmd\":\"host_activity\"}\n");
    } else if (strcmp(cmd, "refresh_status") == 0) {
      if (!doc["requestId"].is<uint32_t>() || doc["requestId"].as<uint32_t>() != snap_.refreshId || !snap_.refreshId || !refresh_pending()) {
        reply_error(-1, 0, "unknown refresh request"); return;
      }
      const char* state = doc["state"] | "";
      if (strcmp(state, "waiting") == 0) snap_.refreshState = RefreshState::waiting;
      else if (strcmp(state, "updating") == 0) snap_.refreshState = RefreshState::updating;
      else if (strcmp(state, "complete") == 0) snap_.refreshState = RefreshState::complete;
      else if (strcmp(state, "failed") == 0) snap_.refreshState = RefreshState::failed;
      else { reply_error(-1, 0, "invalid refresh state"); return; }
      if (!refresh_pending()) snap_.refreshCompletedMs = tick();
      copy_capped(snap_.refreshMessage, sizeof(snap_.refreshMessage), doc["message"] | "");
      emit("{\"type\":\"ok\",\"cmd\":\"refresh_status\"}\n");
    } else if (strcmp(cmd, "get_views") == 0) {
      print_view_state();
    } else if (strcmp(cmd, "set_views") == 0) {
      JsonArray views = doc["views"];
      if (views.isNull() || views.size() == 0 || views.size() > (int)kMaxViews) {
        reply_error(-1, 0, "set_views: invalid count");
        return;
      }
      char keys[kMaxViews][16] = {};
      for (size_t i = 0; i < views.size(); ++i) {
        copy_capped(keys[i], sizeof(keys[i]), views[i].as<const char*>());
        normalize_key(keys[i]);
        // Plugin windows would stream scene frames this device cannot render.
        if (strncmp(keys[i], "plugin:", 7) == 0) {
          reply_error(-1, 0, "set_views: plugin windows not supported");
          return;
        }
        if (!provider_style(keys[i])) {
          reply_error(-1, 0, "set_views: unsupported provider");
          return;
        }
      }
      const char* mode = doc["mode"] | "manual";
      if (strcmp(mode, "manual") != 0 && strcmp(mode, "automatic") != 0) {
        reply_error(-1, 0, "set_views: invalid mode");
        return;
      }
      int interval = doc["interval"] | 10;
      int active = doc["active"] | 0;
      if ((!doc["interval"].isNull() && !doc["interval"].is<int>()) ||
          (!doc["active"].isNull() && !doc["active"].is<int>()) ||
          interval < 2 || interval > 3600 || active < 0 || active >= (int)views.size()) {
        reply_error(-1, 0, "set_views: invalid interval or active");
        return;
      }
      viewCount_ = (uint8_t)views.size();
      memcpy(viewKeys_, keys, sizeof(keys));
      viewsAutomatic_ = (strcmp(mode, "automatic") == 0);
      viewInterval_ = (uint16_t)interval;
      viewActive_ = (uint8_t)active;
      memcpy(snap_.viewKeys, keys, sizeof(keys));
      snap_.viewCount = viewCount_;
      snap_.viewsConfigured = true;
      snap_.activeView = viewActive_;
      snap_.automaticViews = viewsAutomatic_;
      snap_.viewIntervalSeconds = viewInterval_;
      ++snap_.viewRevision;
      // Configuration may reorder or remove providers. Old data must not be
      // displayed under a new key, including views outside the new count.
      for (auto& view : snap_.views) view = ViewData{};
      emitf("{\"type\":\"ok\",\"cmd\":\"set_views\",\"count\":%u}\n", (unsigned)viewCount_);
      print_view_state();
    } else if (strcmp(cmd, "set_brightness") == 0) {
      // The companion's per-device profile sends this on every connect; this
      // panel is dedicated, so the backlight level is ours to take.
      const long value = doc["value"] | -1L;
      const bool persist = doc["persist"] | false;
      if (!doc["value"].is<long>() || value < 0 || value > 100) {
        reply_error(-1, 0, "set_brightness: invalid value");
        return;
      }
      if (!doc["persist"].isUnbound() && !doc["persist"].is<bool>()) {
        reply_error(-1, 0, "set_brightness: invalid persist");
        return;
      }
      if (!apply_brightness || !apply_brightness(static_cast<uint8_t>(value), persist)) {
        reply_error(-1, 0, "set_brightness: update unavailable");
        return;
      }
      emitf("{\"type\":\"ok\",\"cmd\":\"set_brightness\",\"value\":%ld,\"persist\":%s}\n", value,
            persist ? "true" : "false");
    } else if (strcmp(cmd, "set_orientation") == 0 || strcmp(cmd, "set_theme") == 0 ||
               strcmp(cmd, "set_language") == 0 || strcmp(cmd, "standby") == 0) {
      // Accepted but not acted on: the panel orientation is fixed by the LVGL
      // rotation, and the dark industrial theme is the design.
      emitf("{\"type\":\"ok\",\"cmd\":\"%s\"}\n", cmd);
    } else if (strcmp(cmd, "reboot") == 0) {
      // Deliberate deviation from the reference firmware: the companion app
      // never restarts this display.
      reply_error(-1, 0, "reboot disabled on this device");
    } else if (strncmp(cmd, "wifi_", 5) == 0) {
      reply_error(-1, 0, "wifi not supported on this device");
    } else {
      reply_error(-1, 0, "unknown command");
    }
    note_host_seen();
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // LINE ASSEMBLY
  // ─────────────────────────────────────────────────────────────────────────────
  void handle_line(char* line) {
    size_t len = strlen(line);
    while (len > 0 && (line[len - 1] == '\r' || line[len - 1] == ' ')) line[--len] = '\0';
    if (len == 0) return;
    if (len > kAim1MaxPayload) { reply_error(-1, 0, "line exceeds maxFrameBytes"); return; }

    if (strncmp(line, "AIM1 ", 5) == 0) {
      const char* start = line + 5;
      char* end = nullptr;
      const unsigned long remaining = strtoul(start, &end, 10);
      bool valid = *start >= '0' && *start <= '9' && remaining > 0 && remaining <= kAim1MaxPayload && *end == ' ';
      while (*end == ' ') ++end;
      start = end;
      const unsigned long id = strtoul(start, &end, 10);
      valid = valid && *start >= '0' && *start <= '9' && id <= INT_MAX && *end == '\0';
      if (valid) {
        framed_ = true;
        framedRemaining_ = remaining;
        framedHeaderId_ = id;
        payloadLen_ = 0;
        framedLastByteMs_ = tick();
      } else {
        reply_error(-1, 0, "invalid AIM1 header");
      }
      return;
    }

    JsonDocument doc;
    if (deserializeJson(doc, line, len) != DeserializationError::Ok) return;  // stray log text
    if (!doc["cmd"].isNull()) {
      handle_command(doc);
      return;
    }
    handle_frame(doc, len);
  }
};

}  // namespace aim
