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
// Built-in companion index: 0 NOVA, 1 ORBIT, 2 CLAUDE, 3 WRAITH, 4 GLITCH (app_settings::Companion order);
// the last two exist only where AIM_EXTRA_COMPANIONS is set.
inline CompanionFrameView builtin_companion_view(uint8_t companion, const lv_image_dsc_t* pose) {
  if (companion == 1) return {nova_assets::companion_pose(1, pose), nova_assets::orbit_origin_x, nova_assets::orbit_origin_y};
  if (companion == 2) return {nova_assets::companion_pose(2, pose), nova_assets::claude_origin_x, nova_assets::claude_origin_y};
#if defined(AIM_EXTRA_COMPANIONS)
  if (companion == 3) return {nova_assets::companion_pose(3, pose), nova_assets::wraith_origin_x, nova_assets::wraith_origin_y};
  if (companion == 4) return {nova_assets::companion_pose(4, pose), nova_assets::glitch_origin_x, nova_assets::glitch_origin_y};
#endif
  return {pose, nova_assets::nova_origin_x, nova_assets::nova_origin_y};
}
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
  void reset() {
    binding_.detach();requested_=nullptr;externalRequested_=false;cached_=false;
    drawn_=nullptr;target_=nullptr;
  }
  bool render_external(lv_obj_t* image,const companions::Frame& frame,companions::Codec codec,
                       const uint8_t* encoded,int x,int y) {
    if(!cache_ || !image || !encoded)return false;
    if(!externalRequested_ || !same_frame(externalFrame_,frame) || externalCodec_!=codec) {
      externalRequested_=true;externalFrame_=frame;externalCodec_=codec;requested_=nullptr;cached_=false;
      int slot=-1;
      for(unsigned i=0;i<2;++i) {
        const auto* candidate=cache_->slot(i);
        if(candidate && same_frame(candidate->frame,frame))slot=i;
      }
      if(slot<0){slot=cache_->load(frame,codec,encoded,frame.encodedBytes,hash_,decode_);if(slot>=0)++decoded_;}
      if(slot>=0 && binding_.activate(image,*cache_,slot,x,y)){cached_=true;active_=slot;}
      else{++failures_;binding_.detach();}
    }
    return cached_ && binding_.activate(image,*cache_,active_,x,y);
  }
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
  void render(lv_obj_t* image, uint8_t companion, const lv_image_dsc_t* pose, int x, int y) {
    if (companion >= AIM_BUILTIN_COMPANIONS) companion = 0;   // an unavailable choice shows NOVA
#if !defined(AIM_BOARD_WAVESHARE_S3) || defined(AIM_COMPANION_CACHE_TEST)
    if (cache_) {
      unsigned index=0;
      const lv_image_dsc_t* poses[]={&nova_assets::work,&nova_assets::done,&nova_assets::low,
        &nova_assets::critical,&nova_assets::sleep,&nova_assets::blink};
      for (unsigned i=0;i<6;++i)if (pose==poses[i])index=i;
      const auto* wanted=&companions::builtin_frames[index+companion*companions::builtin_poses];
      if (wanted!=requested_) {
        externalRequested_=false;
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
      render(image,builtin_companion_view(companion,&nova_assets::work),x,y);
      return;
    }
#endif
    render(image,builtin_companion_view(companion,pose),x,y);
  }
 private:
  static bool same_frame(const companions::Frame& a,const companions::Frame& b) {
    return a.width==b.width && a.height==b.height && a.originX==b.originX && a.originY==b.originY &&
      a.encodedBytes==b.encodedBytes && a.decodedBytes==b.decodedBytes &&
      !memcmp(a.encodedSha256,b.encodedSha256,65) && !memcmp(a.decodedSha256,b.decodedSha256,65);
  }
  companions::Frame externalFrame_;
  companions::Codec externalCodec_=companions::Codec::raw;
  bool externalRequested_=false;
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
