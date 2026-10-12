#pragma once
#include "nova_assets.h"

// Cropped frames retain their original canvas origin in every pose.
// Only the UI task calls render; no image allocation or decoding at runtime.
class CompanionRenderer {
 public:
  void render(lv_obj_t* image, bool orbit, const lv_image_dsc_t* pose, int x, int y) {
    const auto* frame = nova_assets::companion_pose(orbit, pose);
    if (image != target_ || frame != drawn_) { target_ = image; drawn_ = frame; lv_image_set_src(image, frame); }
    x += orbit ? nova_assets::orbit_origin_x : nova_assets::nova_origin_x;
    y += orbit ? nova_assets::orbit_origin_y : nova_assets::nova_origin_y;
    if (lv_obj_get_x(image) != x) lv_obj_set_x(image, x);
    if (lv_obj_get_y(image) != y) lv_obj_set_y(image, y);
  }
 private:
  const lv_image_dsc_t* drawn_ = nullptr;
  lv_obj_t* target_ = nullptr;
};
