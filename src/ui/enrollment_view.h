#pragma once
#include <lvgl.h>
#include <cstdint>
namespace interaction {
struct EnrollmentDisplay {
  uint32_t revision=0,receivedAt=0,remainingMs=0;
  char code[20]{};
  bool connected=false,awake=false,comparing=false,confirmed=false;
};
// UI-task only. Callback queues a revision-bound local action; it does not store a key.
class EnrollmentView {
 public:
  using Clock=uint32_t(*)();
  using Action=bool(*)(uint32_t revision,bool confirm);
  EnrollmentView(Clock clock,Action action):clock_(clock),action_(action){}
  ~EnrollmentView();
  EnrollmentView(const EnrollmentView&)=delete;EnrollmentView& operator=(const EnrollmentView&)=delete;
  bool initialize();
  void show();void hide(bool cancel=true);
  void update(const EnrollmentDisplay&);
  lv_obj_t* root() const{return root_;}
  lv_obj_t* confirm_button() const{return confirm_;}
  lv_obj_t* cancel_button() const{return cancel_;}
  lv_obj_t* code_label() const{return code_;}
  bool visible() const{return reviewable();}
 private:
  Clock clock_;Action action_;EnrollmentDisplay display_;
  lv_obj_t *root_=nullptr,*code_=nullptr,*status_=nullptr,*confirm_=nullptr,*cancel_=nullptr,*progress_=nullptr,*screen_=nullptr;
  lv_indev_t* pointer_=nullptr;uint32_t started_=0;bool sent_=false;
  bool eligible() const;bool reviewable() const;bool inside() const;
  void release();void refresh();
  static void confirm_event(lv_event_t*);static void cancel_event(lv_event_t*);
  static void screen_event(lv_event_t*);static void deleted(lv_event_t*);
};
}
