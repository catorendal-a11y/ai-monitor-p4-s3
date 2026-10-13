#pragma once
#include "nova_assets.h"

// Cropped frames retain their original canvas origin in every pose.
// Only the UI task calls render; source lifetime belongs to its built-in/cache owner.
struct CompanionFrameView {
  const lv_image_dsc_t* descriptor = nullptr;
  int16_t originX = 0, originY = 0;
};
class CompanionRenderer {
 public:
  bool render(lv_obj_t* image,const CompanionFrameView& view,int x,int y) {
    if (!image || !view.descriptor)return false;
    if (image != target_ || view.descriptor != drawn_ || lv_image_get_src(image) != view.descriptor) {
      target_ = image;drawn_ = view.descriptor;lv_image_set_src(image,view.descriptor);
    }
    x += view.originX;y += view.originY;
    if (lv_obj_get_x(image) != x)lv_obj_set_x(image,x);
    if (lv_obj_get_y(image) != y)lv_obj_set_y(image,y);
    return true;
  }
  void render(lv_obj_t* image, bool orbit, const lv_image_dsc_t* pose, int x, int y) {
    const auto* frame = nova_assets::companion_pose(orbit, pose);
    render(image,{frame,orbit ? nova_assets::orbit_origin_x : nova_assets::nova_origin_x,
        orbit ? nova_assets::orbit_origin_y : nova_assets::nova_origin_y},x,y);
  }
 private:
  const lv_image_dsc_t* drawn_ = nullptr;
  lv_obj_t* target_ = nullptr;
};
