#pragma once
#include "types.h"
namespace companions {
struct BuiltinFrame { Frame frame; const uint8_t* encoded; };
// Six poses per companion, in app_settings::Companion order.
inline constexpr unsigned builtin_poses = 6;
extern const BuiltinFrame builtin_frames[18];
}
