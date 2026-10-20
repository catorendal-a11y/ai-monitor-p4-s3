#pragma once
#include "types.h"
#include "../companion_features.h"
namespace companions {
struct BuiltinFrame { Frame frame; const uint8_t* encoded; };
// Six poses per companion, in app_settings::Companion order.
inline constexpr unsigned builtin_poses = 6;
inline constexpr unsigned builtin_frame_count = builtin_poses * AIM_BUILTIN_COMPANIONS;
extern const BuiltinFrame builtin_frames[builtin_frame_count];
}
