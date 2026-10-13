#pragma once
#include <lvgl.h>
#include "../live_agent/permission_controller.h"

namespace live_agent {
// Dormant until a trusted adapter explicitly creates/shows it. Never reads quota/AIM1 data.
class PermissionView {
 public:
  using Clock=uint32_t(*)();
  explicit PermissionView(PermissionController& controller,Clock clock) : clock_(clock),controller_(controller) {}
  PermissionView(const PermissionView&)=delete;
  PermissionView& operator=(const PermissionView&)=delete;
  ~PermissionView();
  bool initialize();
  void show();
  void hide();
  void update(const ClaudeLiveSnapshot&,const PermissionContext&);
  PermissionEnvelope take(const ClaudeLiveSnapshot&,const PermissionContext&,uint32_t now);
  bool commit(const PermissionEnvelope&,const ClaudeLiveSnapshot&,const PermissionContext&,uint32_t now);
  void delivery_failed();
  PermissionState state() const { return controller_.state(); }
  lv_obj_t* root() const { return root_; }
  lv_obj_t* approve_button() const { return approve_; }
  lv_obj_t* deny_button() const { return deny_; }
  lv_obj_t* close_button() const { return close_; }
  lv_obj_t* hint_label() const { return hint_; }
  lv_obj_t* status_label() const { return status_; }
 private:
  Clock clock_;
  PermissionController& controller_; // Interaction authority outlives the view and its widgets.
  PermissionContext context_;
  lv_obj_t *root_=nullptr,*card_=nullptr,*request_=nullptr,*tool_=nullptr,*hint_=nullptr,
      *status_=nullptr,*progress_=nullptr,*approve_=nullptr,*deny_=nullptr,*close_=nullptr;
  lv_indev_t* pointer_=nullptr;
  lv_obj_t* screen_=nullptr;
  bool complete_=false;
  uint32_t renderedEpoch_=0,renderedRevision_=0;
  static void approve_event(lv_event_t*);
  static void deny_event(lv_event_t*);
  static void close_event(lv_event_t*);
  static void deleted(lv_event_t*);
  static void screen_event(lv_event_t*);
  bool pointer_inside(lv_obj_t*) const;
  void cancel_pointer();
  void refresh();
  bool fits(lv_obj_t*) const;
  bool reviewable() const;
  bool details_match(const ClaudeLiveSnapshot&) const;
};
}
