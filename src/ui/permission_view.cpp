#include "permission_view.h"
#include "theme.h"
#include <cstdio>
#include <cstring>

namespace live_agent {
namespace {
void text(lv_obj_t* label,const char* value) {
  if (strcmp(lv_label_get_text(label),value))lv_label_set_text(label,value);
}
lv_obj_t* label(lv_obj_t* parent,int x,int y,int w,int h,const lv_font_t* font) {
  auto* result=lv_label_create(parent);lv_obj_set_pos(result,x,y);lv_obj_set_size(result,w,h);
  lv_label_set_text(result,"");
  lv_obj_set_style_text_font(result,font,0);lv_obj_set_style_text_color(result,lv_color_hex(ui_theme::text),0);
  lv_label_set_long_mode(result,LV_LABEL_LONG_MODE_WRAP);lv_obj_set_clickable(result,false);return result;
}
lv_obj_t* button(lv_obj_t* parent,int x,int width,const char* caption) {
  auto* result=lv_button_create(parent);lv_obj_set_pos(result,x,354);lv_obj_set_size(result,width,60);
  lv_obj_set_style_radius(result,10,0);lv_obj_set_style_shadow_width(result,0,0);
  lv_obj_set_style_bg_color(result,lv_color_hex(ui_theme::button),0);
  lv_obj_set_style_bg_color(result,lv_color_hex(ui_theme::pressed),LV_STATE_PRESSED);
  lv_obj_set_press_lock(result,true);
  auto* title=label(result,0,0,width-16,26,&lv_font_montserrat_20);
  lv_label_set_text(title,caption);lv_obj_set_style_text_align(title,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(title);
  return result;
}
}
PermissionView::~PermissionView() {
  hide();
  if(root_)lv_obj_delete(root_);
}
bool PermissionView::initialize() {
  if (root_ || !clock_ || !lv_display_get_default())return false;
  root_=lv_obj_create(lv_layer_top());lv_obj_set_pos(root_,0,0);lv_obj_set_size(root_,800,480);
  lv_obj_set_style_pad_all(root_,0,0);lv_obj_set_scrollable(root_,false);
  lv_obj_set_style_bg_color(root_,lv_color_hex(ui_theme::background),0);lv_obj_set_style_bg_opa(root_,LV_OPA_COVER,0);
  lv_obj_add_event_cb(root_,deleted,LV_EVENT_DELETE,this);
  card_=lv_obj_create(root_);lv_obj_set_pos(card_,20,25);lv_obj_set_size(card_,760,430);
  lv_obj_set_style_pad_all(card_,0,0);lv_obj_set_scrollable(card_,false);
  lv_obj_set_style_bg_color(card_,lv_color_hex(ui_theme::surface),0);
  lv_obj_set_style_border_color(card_,lv_color_hex(ui_theme::border),0);lv_obj_set_style_radius(card_,14,0);
  auto* title=label(card_,24,14,568,32,&lv_font_montserrat_24);lv_label_set_text(title,"LIVE AGENT PERMISSION");
  close_=button(card_,620,116,"CLOSE");lv_obj_set_pos(close_,620,12);lv_obj_set_height(close_,36);
  lv_obj_set_style_pad_all(close_,0,0);
  lv_obj_add_event_cb(close_,close_event,LV_EVENT_CLICKED,this);
  request_=label(card_,24,58,700,44,&lv_font_montserrat_16);
  tool_=label(card_,24,106,700,48,&lv_font_montserrat_20);
  hint_=label(card_,24,160,700,138,&lv_font_montserrat_18);
  status_=label(card_,24,305,700,40,&lv_font_montserrat_16);
  lv_obj_set_style_text_color(status_,lv_color_hex(ui_theme::muted),0);
  progress_=lv_bar_create(card_);lv_obj_set_pos(progress_,246,344);lv_obj_set_size(progress_,490,5);
  lv_bar_set_range(progress_,0,100);lv_bar_set_value(progress_,0,LV_ANIM_OFF);
  lv_obj_set_style_bg_color(progress_,lv_color_hex(ui_theme::accent),LV_PART_INDICATOR);
  deny_=button(card_,24,200,"DENY");approve_=button(card_,246,490,"HOLD TO APPROVE");
  lv_obj_add_event_cb(approve_,approve_event,LV_EVENT_ALL,this);
  lv_obj_add_event_cb(deny_,deny_event,LV_EVENT_CLICKED,this);
  lv_obj_set_hidden(root_,true);refresh();return true;
}
void PermissionView::show() {
  if(!root_)return;
  if(screen_)lv_obj_remove_event_cb_with_user_data(screen_,screen_event,this);
  screen_=lv_screen_active();
  lv_obj_add_event_cb(screen_,screen_event,LV_EVENT_SCREEN_UNLOAD_START,this);
  lv_obj_add_event_cb(screen_,screen_event,LV_EVENT_DELETE,this);
  lv_obj_set_hidden(root_,false);
}
void PermissionView::hide() {
  cancel_pointer();controller_.hide();
  if(screen_)lv_obj_remove_event_cb_with_user_data(screen_,screen_event,this);
  screen_=nullptr;
  if(root_) { text(request_,"");text(tool_,"");text(hint_,"");lv_obj_set_hidden(root_,true); }
}
void PermissionView::screen_event(lv_event_t* event) {
  auto* self=static_cast<PermissionView*>(lv_event_get_user_data(event));
  self->cancel_pointer();self->controller_.hide();
  if(self->root_)lv_obj_set_hidden(self->root_,true);
  if(lv_event_get_code(event)==LV_EVENT_DELETE)self->screen_=nullptr;
}
void PermissionView::deleted(lv_event_t* event) {
  auto* self=static_cast<PermissionView*>(lv_event_get_user_data(event));
  if(lv_event_get_target_obj(event)==self->root_) { self->cancel_pointer();self->controller_.hide();self->root_=nullptr; }
}
void PermissionView::cancel_pointer() {
  if(pointer_)lv_indev_wait_release(pointer_);
  pointer_=nullptr;controller_.release();
}
bool PermissionView::fits(lv_obj_t* object) const {
  for(auto* current=object;current;current=lv_obj_get_parent(current))
    if(lv_obj_is_hidden(current) || lv_obj_get_style_opa(current,LV_PART_MAIN)!=LV_OPA_COVER)return false;
  if(lv_obj_get_style_text_opa(object,LV_PART_MAIN)!=LV_OPA_COVER)return false;
  lv_point_t size{};
  lv_text_get_size(&size,lv_label_get_text(object),lv_obj_get_style_text_font(object,LV_PART_MAIN),
      lv_obj_get_style_text_letter_space(object,LV_PART_MAIN),lv_obj_get_style_text_line_space(object,LV_PART_MAIN),
      lv_obj_get_width(object),LV_TEXT_FLAG_NONE);
  return size.x<=lv_obj_get_width(object) && size.y<=lv_obj_get_height(object);
}
bool PermissionView::reviewable() const {
  if (!root_ || lv_obj_is_hidden(root_) || screen_!=lv_screen_active())return false;
  lv_obj_update_layout(root_);
  for(auto* current=root_;current;current=lv_obj_get_parent(current))
    if(lv_obj_is_hidden(current) || lv_obj_get_style_opa(current,LV_PART_MAIN)!=LV_OPA_COVER)return false;
  auto* display=lv_obj_get_display(root_);lv_area_t bounds{};lv_obj_get_coords(root_,&bounds);
  if(lv_display_get_horizontal_resolution(display)!=800 || lv_display_get_vertical_resolution(display)!=480 ||
      bounds.x1<0 || bounds.y1<0 || bounds.x2>=800 || bounds.y2>=480)return false;
  auto* parent=lv_obj_get_parent(root_);
  const int32_t index=lv_obj_get_index(root_);
  for (uint32_t i=static_cast<uint32_t>(index+1);i<lv_obj_get_child_count(parent);++i)
    if (!lv_obj_is_hidden(lv_obj_get_child(parent,i)))return false;
  // A system overlay (e.g. the sleeping display's dimmer) also blocks review.
  for (uint32_t i=0;i<lv_obj_get_child_count(lv_layer_sys());++i)
    if (!lv_obj_is_hidden(lv_obj_get_child(lv_layer_sys(),i)))return false;
  return true;
}
bool PermissionView::details_match(const ClaudeLiveSnapshot& value) const {
  if(!root_ || !value.prompt.present)return false;
  char id[112],tool[80];snprintf(id,sizeof(id),"REQUEST: %s",value.prompt.id);
  snprintf(tool,sizeof(tool),"TOOL: %s",value.prompt.tool);
  return !strcmp(lv_label_get_text(request_),id) && !strcmp(lv_label_get_text(tool_),tool) &&
      !strcmp(lv_label_get_text(hint_),value.prompt.hint);
}
void PermissionView::update(const ClaudeLiveSnapshot& value,const PermissionContext& context) {
  if(!root_)return;
  const uint32_t now=clock_();context_=context;context_.visible &= reviewable();
  if (value.epoch!=renderedEpoch_ || value.revision!=renderedRevision_ ||
      !value.prompt.equals(controller_.snapshot().prompt) || !context_.eligible())cancel_pointer();
  controller_.update(value,context_,now);
  const bool present=value.fresh && now-value.receivedAt<lease_ms && value.prompt.present;
  if(present) {
    char id[112],tool[80];snprintf(id,sizeof(id),"REQUEST: %s",value.prompt.id);
    snprintf(tool,sizeof(tool),"TOOL: %s",value.prompt.tool);
    text(request_,id);text(tool_,tool);text(hint_,value.prompt.hint);
  } else { text(request_,"");text(tool_,"");text(hint_,""); }
  renderedEpoch_=value.epoch;renderedRevision_=value.revision;
  lv_obj_update_layout(root_);
  complete_=present && value.prompt.displaySupported && fits(request_) && fits(tool_) && fits(hint_);
  controller_.displayed(complete_);refresh();
}
bool PermissionView::pointer_inside(lv_obj_t* target) const {
  if(!reviewable())return false;
  auto* input=lv_indev_active();
  if(!input || lv_indev_get_type(input)!=LV_INDEV_TYPE_POINTER)return false;
  lv_point_t point{};lv_area_t area{};lv_indev_get_point(input,&point);lv_obj_get_coords(target,&area);
  return point.x>=area.x1 && point.x<=area.x2 && point.y>=area.y1 && point.y<=area.y2;
}
void PermissionView::approve_event(lv_event_t* event) {
  auto* self=static_cast<PermissionView*>(lv_event_get_user_data(event));
  const auto code=lv_event_get_code(event);
  if(code!=LV_EVENT_PRESSED && code!=LV_EVENT_PRESSING && code!=LV_EVENT_RELEASED && code!=LV_EVENT_PRESS_LOST)return;
  if(code==LV_EVENT_PRESSED) {
    if(self->pointer_inside(self->approve_) && self->details_match(self->controller_.snapshot()) &&
        self->controller_.press(self->clock_()))self->pointer_=lv_indev_active();
  } else if(code==LV_EVENT_PRESSING) {
    const bool inside=self->pointer_inside(self->approve_) && lv_indev_active()==self->pointer_ &&
        self->details_match(self->controller_.snapshot()) && self->fits(self->request_) && self->fits(self->tool_) && self->fits(self->hint_);
    self->controller_.pressing(self->clock_(),inside);
    if(!inside)self->cancel_pointer();
  } else if(code==LV_EVENT_RELEASED || code==LV_EVENT_PRESS_LOST)self->cancel_pointer();
  // CLICKED, keyboard activation and long-press notifications never approve.
  self->refresh();
}
void PermissionView::deny_event(lv_event_t* event) {
  auto* self=static_cast<PermissionView*>(lv_event_get_user_data(event));
  if(self->pointer_inside(self->deny_))self->controller_.deny(self->clock_());
  self->cancel_pointer();self->refresh();
}
void PermissionView::close_event(lv_event_t* event) {
  auto* self=static_cast<PermissionView*>(lv_event_get_user_data(event));
  if(self->pointer_inside(self->close_))self->hide();
}
void PermissionView::refresh() {
  if(!root_)return;
  const auto state=controller_.state();
  const bool actionable=context_.eligible() && complete_ && (state==PermissionState::DISPLAYED || state==PermissionState::HOLDING);
  if(actionable) { lv_obj_remove_state(approve_,LV_STATE_DISABLED);lv_obj_remove_state(deny_,LV_STATE_DISABLED); }
  else { lv_obj_add_state(approve_,LV_STATE_DISABLED);lv_obj_add_state(deny_,LV_STATE_DISABLED); }
  lv_bar_set_value(progress_,state==PermissionState::SENT?100:controller_.progress(clock_()),LV_ANIM_OFF);
  const char* message="Waiting for a current request.";
  if(context_.demo)message="DEMO - approvals are blocked.";
  else if(!context_.connected || !context_.secure)message="Secure paired connection required. Review on Desktop.";
  else if(!context_.optIn)message="Device permissions are disabled.";
  else if(state==PermissionState::EXPIRED)message="Request expired. Review on Desktop.";
  else if(state==PermissionState::CANCELLED)message="Request cancelled. A new request is required.";
  else if(state==PermissionState::ERROR)message="Request unavailable or delivery failed. Review on Desktop.";
  else if(state==PermissionState::SENT)message=controller_.queued()?"Approval queued; transport will recheck the request.":"Decision handed to transport. Verify on Desktop.";
  else if(state==PermissionState::DENIED)message="Denial selected. Verify on Desktop.";
  else if(state==PermissionState::ACKNOWLEDGED)message="Acknowledgement received.";
  else if(!complete_ && controller_.snapshot().prompt.present)message="Complete details do not fit. Review on Desktop.";
  else if(state==PermissionState::HOLDING)message="Keep holding inside the button. Release cancels.";
  else if(state==PermissionState::DISPLAYED)message="Hold for 1.8 seconds to approve. A tap never approves.";
  text(status_,message);
}
PermissionEnvelope PermissionView::take(const ClaudeLiveSnapshot& value,const PermissionContext& context,uint32_t now) {
  auto trusted=context;trusted.visible &= reviewable();
  if (!root_ || !complete_ || !details_match(value) || !fits(request_) || !fits(tool_) || !fits(hint_))trusted.visible=false;
  const auto result=controller_.take(value,trusted,now);refresh();return result;
}
void PermissionView::delivery_failed() { controller_.delivery_failed();refresh(); }
bool PermissionView::commit(const PermissionEnvelope& value,const ClaudeLiveSnapshot& current,
                            const PermissionContext& context,uint32_t now) {
  auto trusted=context;trusted.visible &= reviewable();
  if(!root_ || !complete_ || !details_match(current) || !fits(request_) || !fits(tool_) || !fits(hint_))trusted.visible=false;
  const bool accepted=controller_.commit(value,current,trusted,now);refresh();return accepted;
}
}
