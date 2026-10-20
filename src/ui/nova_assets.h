#pragma once
#include <lvgl.h>
#include "../companion_features.h"
namespace nova_assets {
inline constexpr int16_t nova_origin_x = 28;
inline constexpr int16_t nova_origin_y = 4;
inline constexpr int16_t orbit_origin_x = 58;
inline constexpr int16_t orbit_origin_y = 17;
inline constexpr int16_t claude_origin_x = 47;
inline constexpr int16_t claude_origin_y = 4;
inline constexpr int16_t wraith_origin_x = 58;
inline constexpr int16_t wraith_origin_y = 17;
inline constexpr int16_t glitch_origin_x = 58;
inline constexpr int16_t glitch_origin_y = 6;
extern const lv_image_dsc_t work;
extern const lv_image_dsc_t done;
extern const lv_image_dsc_t low;
extern const lv_image_dsc_t critical;
extern const lv_image_dsc_t sleep;
extern const lv_image_dsc_t blink;
extern const lv_image_dsc_t nova_thumb;
extern const lv_image_dsc_t orbit_work;
extern const lv_image_dsc_t orbit_done;
extern const lv_image_dsc_t orbit_low;
extern const lv_image_dsc_t orbit_critical;
extern const lv_image_dsc_t orbit_sleep;
extern const lv_image_dsc_t orbit_blink;
extern const lv_image_dsc_t orbit_thumb;
extern const lv_image_dsc_t claude_work;
extern const lv_image_dsc_t claude_done;
extern const lv_image_dsc_t claude_low;
extern const lv_image_dsc_t claude_critical;
extern const lv_image_dsc_t claude_sleep;
extern const lv_image_dsc_t claude_blink;
extern const lv_image_dsc_t claude_thumb;
#if defined(AIM_EXTRA_COMPANIONS)
extern const lv_image_dsc_t wraith_work;
extern const lv_image_dsc_t wraith_done;
extern const lv_image_dsc_t wraith_low;
extern const lv_image_dsc_t wraith_critical;
extern const lv_image_dsc_t wraith_sleep;
extern const lv_image_dsc_t wraith_blink;
extern const lv_image_dsc_t wraith_thumb;
#endif
#if defined(AIM_EXTRA_COMPANIONS)
extern const lv_image_dsc_t glitch_work;
extern const lv_image_dsc_t glitch_done;
extern const lv_image_dsc_t glitch_low;
extern const lv_image_dsc_t glitch_critical;
extern const lv_image_dsc_t glitch_sleep;
extern const lv_image_dsc_t glitch_blink;
extern const lv_image_dsc_t glitch_thumb;
#endif
extern const lv_image_dsc_t openai24;
extern const lv_image_dsc_t openai42;
extern const lv_image_dsc_t openai48;
extern const lv_image_dsc_t zcode24;
extern const lv_image_dsc_t zcode42;
extern const lv_image_dsc_t zcode48;
const lv_image_dsc_t* logo_for(const char* provider, unsigned size);
const lv_image_dsc_t* companion_pose(uint8_t companion, const lv_image_dsc_t* novaPose);
const lv_image_dsc_t* companion_thumb(uint8_t companion);
}
