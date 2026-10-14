#pragma once
#include <lvgl.h>
namespace nova_assets {
inline constexpr int16_t nova_origin_x = 28;
inline constexpr int16_t nova_origin_y = 0;
inline constexpr int16_t orbit_origin_x = 58;
inline constexpr int16_t orbit_origin_y = 17;
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
extern const lv_image_dsc_t openai24;
extern const lv_image_dsc_t openai42;
extern const lv_image_dsc_t openai48;
extern const lv_image_dsc_t zcode24;
extern const lv_image_dsc_t zcode42;
extern const lv_image_dsc_t zcode48;
const lv_image_dsc_t* logo_for(const char* provider, unsigned size);
const lv_image_dsc_t* companion_pose(bool orbit, const lv_image_dsc_t* novaPose);
}
