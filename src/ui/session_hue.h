#pragma once
#include <cstdint>

// The twelve session colours, shared by the Agents list and the NOVA screen. The PC terminal uses
// the same values (tools/terminal_presentation.py HUE_COLORS), so a session looks the same everywhere.
inline constexpr uint32_t session_hue_colors[12] = {0xF26B6B, 0xF2A25C, 0xE8D55B, 0xA5D96B, 0x5CD68A, 0x5CD6C0,
                                                    0x5CC4F2, 0x6B8CF2, 0x8F6BF2, 0xC06BF2, 0xF26BC8, 0xF26B94};
