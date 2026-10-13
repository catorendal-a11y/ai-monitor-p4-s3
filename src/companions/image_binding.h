#pragma once
#include "frame_cache.h"
#include <lvgl.h>
#include <src/misc/cache/instance/lv_image_cache.h>

namespace companions {
// UI-task only. Pin storage until the synchronous single-unit renderer drops its source.
// A future asynchronous renderer needs an explicit draw-completion fence instead.
class ImageBinding {
 public:
  explicit ImageBinding(const lv_image_dsc_t* fallback,int16_t originX=0,int16_t originY=0)
      : fallback_(fallback),fallbackX_(originX),fallbackY_(originY) {}
  ImageBinding(const ImageBinding&)=delete;
  ImageBinding& operator=(const ImageBinding&)=delete;
  ~ImageBinding() { detach(); }
  bool activate(lv_obj_t* target,FrameCache& cache,unsigned index,int x,int y) {
#if LV_USE_OS != LV_OS_NONE || LV_DRAW_SW_DRAW_UNIT_CNT != 1
    (void)target;(void)cache;(void)index;(void)x;(void)y;
    return false; // Unsupported lifetime model is closed, never guessed safe.
#else
    const auto* slot=cache.slot(index);
    if (!target || !fallback_ || !slot || (target_ && (target!=target_ || &cache!=cache_)))return false;
    if (target_ && index==active_) {
      baseX_=x;baseY_=y;
      if (lv_image_get_src(target)!=&descriptors_[index])lv_image_set_src(target,&descriptors_[index]);
      lv_obj_set_pos(target,x+slot->frame.originX,y+slot->frame.originY);return true;
    }
    if (slot->pinned)return false; // A boolean ownership pin cannot be shared by bindings.
    if (!cache.pin(index))return false;
    auto& descriptor=descriptors_[index];
    lv_image_cache_drop(&descriptor);
    descriptor={};descriptor.header.magic=LV_IMAGE_HEADER_MAGIC;
    descriptor.header.cf=LV_COLOR_FORMAT_RGB565A8;
    descriptor.header.w=slot->frame.width;descriptor.header.h=slot->frame.height;
    descriptor.header.stride=slot->frame.width*2;
    descriptor.data=slot->pixels;descriptor.data_size=slot->frame.decodedBytes;
    lv_image_set_src(target,&descriptor);
    lv_obj_set_pos(target,x+slot->frame.originX,y+slot->frame.originY);
    if (target_) {
      lv_image_cache_drop(&descriptors_[active_]);cache_->retire(active_);
    } else {
      lv_obj_add_event_cb(target,on_delete,LV_EVENT_DELETE,this);
    }
    target_=target;cache_=&cache;active_=index;baseX_=x;baseY_=y;
    return true;
#endif
  }
  void detach() {
    if (!target_)return;
    lv_obj_remove_event_cb_with_user_data(target_,on_delete,this);
    lv_image_set_src(target_,fallback_);
    lv_obj_set_pos(target_,baseX_+fallbackX_,baseY_+fallbackY_);
    release();
  }
 private:
  static void on_delete(lv_event_t* event) {
    auto* self=static_cast<ImageBinding*>(lv_event_get_user_data(event));
    self->release(); // Object deletion has removed this image from future draws.
  }
  void release() {
    lv_image_cache_drop(&descriptors_[active_]);cache_->retire(active_);
    target_=nullptr;cache_=nullptr;
  }
  const lv_image_dsc_t* fallback_;
  lv_image_dsc_t descriptors_[2]{};
  lv_obj_t* target_=nullptr;
  FrameCache* cache_=nullptr;
  unsigned active_=0;
  int baseX_=0,baseY_=0;
  int16_t fallbackX_=0,fallbackY_=0;
};
}
