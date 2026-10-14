#pragma once
#include "nova_assets.h"
#include "../companions/builtin_lz4.h"
#include "../companions/image_binding.h"

// Cropped frames retain their original canvas origin in every pose.
// Only the UI task calls render; source lifetime belongs to its built-in/cache owner.
struct CompanionFrameView {
  const lv_image_dsc_t* descriptor = nullptr;
  int16_t originX = 0, originY = 0;
};
class CompanionRenderer {
 public:
  // Storage is allocated once at startup and must outlive this UI-owned renderer.
  void initialize(companions::FrameCache& cache, companions::FrameCache::Hash hash,
                  companions::FrameCache::Decode decode) {
    cache_=&cache;hash_=hash;decode_=decode;
  }
  bool cache_active() const { return cached_; }
  uint32_t decoded_frames() const { return decoded_; }
  uint32_t decode_failures() const { return failures_; }
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
#if !defined(AIM_BOARD_WAVESHARE_S3) || defined(AIM_COMPANION_CACHE_TEST)
    if (cache_) {
      unsigned index=0;
      const lv_image_dsc_t* poses[]={&nova_assets::work,&nova_assets::done,&nova_assets::low,
        &nova_assets::critical,&nova_assets::sleep,&nova_assets::blink};
      for (unsigned i=0;i<6;++i)if (pose==poses[i])index=i;
      const auto* wanted=&companions::builtin_frames[index+(orbit?6:0)];
      if (wanted!=requested_) {
        requested_=wanted;cached_=false;
        int slot=-1;
        for (unsigned i=0;i<2;++i) {
          const auto* existing=cache_->slot(i);
          if (existing && !memcmp(existing->frame.encodedSha256,wanted->frame.encodedSha256,65))slot=i;
        }
        if (slot<0) {
          slot=cache_->load(wanted->frame,companions::Codec::lz4,wanted->encoded,
              wanted->frame.encodedBytes,hash_,decode_);
          if (slot>=0)++decoded_;
        }
        if (slot>=0 && binding_.activate(image,*cache_,slot,x,y)) {
          cached_=true;active_=slot;
        } else { ++failures_;binding_.detach(); }
      }
      if (cached_ && binding_.activate(image,*cache_,active_,x,y))return;
      render(image,{orbit?&nova_assets::orbit_work:&nova_assets::work,
          orbit?nova_assets::orbit_origin_x:nova_assets::nova_origin_x,
          orbit?nova_assets::orbit_origin_y:nova_assets::nova_origin_y},x,y);
      return;
    }
#endif
    const auto* frame = nova_assets::companion_pose(orbit, pose);
    render(image,{frame,orbit ? nova_assets::orbit_origin_x : nova_assets::nova_origin_x,
        orbit ? nova_assets::orbit_origin_y : nova_assets::nova_origin_y},x,y);
  }
 private:
  const lv_image_dsc_t* drawn_ = nullptr;
  lv_obj_t* target_ = nullptr;
  companions::FrameCache* cache_=nullptr;
  companions::FrameCache::Hash hash_=nullptr;
  companions::FrameCache::Decode decode_=nullptr;
  companions::ImageBinding binding_{&nova_assets::work,nova_assets::nova_origin_x,nova_assets::nova_origin_y};
  const companions::BuiltinFrame* requested_=nullptr;
  unsigned active_=0;
  uint32_t decoded_=0,failures_=0;
  bool cached_=false;
};
