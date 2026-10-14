#pragma once
#include "types.h"
namespace companions {
struct BuiltinFrame { Frame frame; const uint8_t* encoded; };
extern const BuiltinFrame builtin_frames[12];
}
