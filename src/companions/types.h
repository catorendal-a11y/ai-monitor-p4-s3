#pragma once
#include <cstddef>
#include <cstdint>

namespace companions {
inline constexpr size_t max_manifest_bytes = 8192, max_frames = 8;
inline constexpr unsigned canvas_width = 430, canvas_height = 284;
inline constexpr size_t max_frame_bytes = canvas_width * canvas_height * 3u;
enum class Codec : uint8_t { raw, lz4 };
enum class Pose : uint8_t { work, done, low, critical, sleep, blink, attention, error };
inline constexpr const char* pose_names[] = {"work","done","low","critical","sleep","blink","attention","error"};
struct Frame {
  Pose pose = Pose::work;
  uint16_t width = 0, height = 0, originX = 0, originY = 0;
  uint32_t encodedBytes = 0, decodedBytes = 0;
  char file[49] = {}, encodedSha256[65] = {}, decodedSha256[65] = {};
};
struct Manifest {
  uint16_t version = 1;
  Codec codec = Codec::raw;
  Pose fallback = Pose::work;
  char name[33] = {};
  uint8_t count = 0;
  Frame frames[max_frames]{};
  const Frame* find(Pose pose) const {
    for (unsigned i=0;i<count;++i) if (frames[i].pose==pose) return &frames[i];
    return nullptr;
  }
  const Frame* resolve(Pose pose) const {
    const auto* exact=find(pose); return exact ? exact : find(fallback);
  }
};
}
