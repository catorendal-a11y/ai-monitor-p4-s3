#include "enrollment_view.h"
#include "theme.h"
#include <cstring>
#include <algorithm>
namespace interaction {
namespace enrollment_widgets {
static lv_obj_t* label(lv_obj_t* parent,int x,int y,int w,int h,const char* value,const lv_font_t* font) {
  auto* object=lv_label_create(parent);lv_obj_set_pos(object,x,y);lv_obj_set_size(object,w,h);
  lv_label_set_text(object,value);lv_label_set_long_mode(object,LV_LABEL_LONG_MODE_WRAP);
  lv_obj_set_style_text_font(object,font,0);lv_obj_set_style_text_color(object,lv_color_hex(ui_theme::text),0);
  lv_obj_set_clickable(object,false);return object;
}
static lv_obj_t* button(lv_obj_t* parent,int x,int width,const char* value) {
  auto* object=lv_button_create(parent);lv_obj_set_pos(object,x,380);lv_obj_set_size(object,width,72);
  lv_obj_set_style_pad_all(object,0,0);lv_obj_set_style_radius(object,14,0);lv_obj_set_style_shadow_width(object,0,0);
  lv_obj_set_style_bg_color(object,lv_color_hex(ui_theme::button),0);
  lv_obj_set_style_bg_color(object,lv_color_hex(ui_theme::pressed),LV_STATE_PRESSED);lv_obj_set_press_lock(object,true);
  auto* caption=label(object,0,0,width-16,36,value,&lv_font_montserrat_26);
  lv_obj_set_style_text_align(caption,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(caption);return object;
}
}
EnrollmentView::~EnrollmentView(){hide();if(root_)lv_obj_delete(root_);}
bool EnrollmentView::initialize() {
  if(root_ || !clock_ || !action_ || !lv_display_get_default())return false;
  root_=lv_obj_create(lv_layer_top());lv_obj_set_pos(root_,0,0);lv_obj_set_size(root_,800,480);
  lv_obj_set_style_pad_all(root_,0,0);lv_obj_set_style_border_width(root_,0,0);lv_obj_set_scrollable(root_,false);
  lv_obj_set_style_bg_color(root_,lv_color_hex(ui_theme::background),0);lv_obj_set_style_bg_opa(root_,LV_OPA_COVER,0);
  lv_obj_add_event_cb(root_,deleted,LV_EVENT_DELETE,this);
  using namespace enrollment_widgets;
  label(root_,24,24,752,44,"CONNECT YOUR PC",&lv_font_montserrat_32);
  label(root_,24,86,752,74,"Compare this code with LimitBuddy on your PC.\nOnly confirm if every group matches.",&lv_font_montserrat_24);
  code_=label(root_,24,180,752,64,"Waiting for PC...",&lv_font_montserrat_40);
  lv_obj_set_style_text_align(code_,LV_TEXT_ALIGN_CENTER,0);
  status_=label(root_,24,262,752,80,"",&lv_font_montserrat_22);
  progress_=lv_bar_create(root_);lv_obj_set_pos(progress_,280,358);lv_obj_set_size(progress_,496,8);
  lv_bar_set_range(progress_,0,100);lv_obj_set_style_bg_color(progress_,lv_color_hex(ui_theme::accent),LV_PART_INDICATOR);
  cancel_=button(root_,24,232,"CANCEL");confirm_=button(root_,280,496,"HOLD TO CONFIRM");
  lv_obj_add_event_cb(confirm_,confirm_event,LV_EVENT_ALL,this);
  lv_obj_add_event_cb(cancel_,cancel_event,LV_EVENT_CLICKED,this);
  lv_obj_set_hidden(root_,true);return true;
}
void EnrollmentView::show() {
  if(!root_)return;
  if(screen_)lv_obj_remove_event_cb_with_user_data(screen_,screen_event,this);
  screen_=lv_screen_active();lv_obj_add_event_cb(screen_,screen_event,LV_EVENT_SCREEN_UNLOAD_START,this);
  lv_obj_add_event_cb(screen_,screen_event,LV_EVENT_DELETE,this);sent_=false;release();lv_obj_set_hidden(root_,false);refresh();
}
void EnrollmentView::release(){if(pointer_)lv_indev_wait_release(pointer_);pointer_=nullptr;started_=0;}
void EnrollmentView::hide(bool cancel) {
  if(cancel && root_ && !lv_obj_is_hidden(root_) && display_.revision)action_(display_.revision,false);
  release();display_=EnrollmentDisplay{};sent_=false;
  if(screen_)lv_obj_remove_event_cb_with_user_data(screen_,screen_event,this);
  screen_=nullptr;
  if(root_){lv_label_set_text(code_,"");lv_obj_set_hidden(root_,true);}
}
bool EnrollmentView::reviewable() const {
  if(!root_ || lv_obj_is_hidden(root_) || screen_!=lv_screen_active())return false;
  lv_obj_update_layout(root_);lv_area_t bounds{};lv_obj_get_coords(root_,&bounds);
  auto* display=lv_obj_get_display(root_);
  if(bounds.x1!=0 || bounds.y1!=0 || bounds.x2!=799 || bounds.y2!=479 ||
     lv_display_get_horizontal_resolution(display)!=800 || lv_display_get_vertical_resolution(display)!=480)return false;
  for(auto* object=root_;object;object=lv_obj_get_parent(object))
    if(lv_obj_is_hidden(object) || lv_obj_get_style_opa(object,LV_PART_MAIN)!=LV_OPA_COVER)return false;
  auto* parent=lv_obj_get_parent(root_);
  for(uint32_t i=static_cast<uint32_t>(lv_obj_get_index(root_)+1);i<lv_obj_get_child_count(parent);++i)
    if(!lv_obj_is_hidden(lv_obj_get_child(parent,i)))return false;
  for(uint32_t i=0;i<lv_obj_get_child_count(lv_layer_sys());++i)
    if(!lv_obj_is_hidden(lv_obj_get_child(lv_layer_sys(),i)))return false;
  lv_point_t size{};
  lv_text_get_size(&size,lv_label_get_text(code_),lv_obj_get_style_text_font(code_,LV_PART_MAIN),
    lv_obj_get_style_text_letter_space(code_,LV_PART_MAIN),lv_obj_get_style_text_line_space(code_,LV_PART_MAIN),
    lv_obj_get_width(code_),LV_TEXT_FLAG_NONE);
  return !strcmp(lv_label_get_text(code_),display_.code[0]?display_.code:"Waiting for PC...") && size.x<=lv_obj_get_width(code_) && size.y<=lv_obj_get_height(code_) &&
    lv_obj_get_style_text_opa(code_,LV_PART_MAIN)==LV_OPA_COVER;
}
bool EnrollmentView::eligible() const {
  if(!display_.revision || !display_.connected || !display_.awake || !display_.comparing || display_.confirmed || sent_ ||
     !display_.remainingMs || display_.remainingMs>60000 || clock_()-display_.receivedAt>=display_.remainingMs)return false;
  if(display_.code[19])return false;
  for(unsigned i=0;i<19;++i) {
    const char c=display_.code[i];
    if(i==4 || i==9 || i==14){if(c!='-')return false;}
    else if(!((c>='0' && c<='9') || (c>='A' && c<='F')))return false;
  }
  return reviewable();
}
bool EnrollmentView::inside() const {
  auto* input=lv_indev_active();
  if(!input || lv_indev_get_type(input)!=LV_INDEV_TYPE_POINTER)return false;
  lv_point_t point{};lv_area_t bounds{};lv_indev_get_point(input,&point);lv_obj_get_coords(confirm_,&bounds);
  return point.x>=bounds.x1 && point.x<=bounds.x2 && point.y>=bounds.y1 && point.y<=bounds.y2;
}
void EnrollmentView::update(const EnrollmentDisplay& value) {
  if(!root_)return;
  if(value.revision!=display_.revision || memcmp(value.code,display_.code,20)) {release();sent_=false;}
  display_=value;
  char safe[20];memcpy(safe,value.code,20);safe[19]=0;
  const char* rendered=safe[0]?safe:"Waiting for PC...";
  if(strcmp(lv_label_get_text(code_),rendered))lv_label_set_text(code_,rendered);
  if(!value.connected || !value.awake || !value.remainingMs || clock_()-value.receivedAt>=value.remainingMs) {
    hide();return;
  }
  if(!lv_obj_is_hidden(root_) && !reviewable()){hide();return;}
  if(!eligible())release();
  refresh();
}
void EnrollmentView::refresh() {
  if(!root_)return;
  const bool available=eligible();lv_obj_set_state(confirm_,LV_STATE_DISABLED,!available);
  const uint32_t elapsed=pointer_?clock_()-started_:0;
  lv_bar_set_value(progress_,sent_?100:static_cast<int32_t>(std::min<uint32_t>(100,elapsed*100/1800)),LV_ANIM_OFF);
  const char* message=display_.confirmed || sent_?"Code confirmed here. Finish confirmation on your PC.":
    (available?(pointer_?"Keep holding inside the button.":"Hold for 1.8 seconds. A tap does not confirm."):"Waiting for a current, visible comparison code.");
  lv_label_set_text(status_,message);
}
void EnrollmentView::confirm_event(lv_event_t* event) {
  auto* self=static_cast<EnrollmentView*>(lv_event_get_user_data(event));const auto code=lv_event_get_code(event);
  if(code==LV_EVENT_PRESSED) {
    if(self->eligible() && self->inside()){self->pointer_=lv_indev_active();self->started_=self->clock_();}
  } else if(code==LV_EVENT_PRESSING) {
    if(!self->eligible() || !self->inside() || !self->pointer_ || lv_indev_active()!=self->pointer_)self->release();
    else if(self->clock_()-self->started_>=1800) {
      self->sent_=true;const bool accepted=self->action_(self->display_.revision,true);self->release();
      if(!accepted)self->hide();
    }
  } else if(code==LV_EVENT_RELEASED || code==LV_EVENT_PRESS_LOST)self->release();
  else return; // CLICKED, key events and long-press notifications never confirm.
  self->refresh();
}
void EnrollmentView::cancel_event(lv_event_t* event){static_cast<EnrollmentView*>(lv_event_get_user_data(event))->hide();}
void EnrollmentView::screen_event(lv_event_t* event) {
  auto* self=static_cast<EnrollmentView*>(lv_event_get_user_data(event));
  if(lv_event_get_code(event)==LV_EVENT_DELETE)self->screen_=nullptr;
  self->hide();
}
void EnrollmentView::deleted(lv_event_t* event) {
  auto* self=static_cast<EnrollmentView*>(lv_event_get_user_data(event));
  if(lv_event_get_target_obj(event)==self->root_){self->hide();self->root_=nullptr;}
}
}
