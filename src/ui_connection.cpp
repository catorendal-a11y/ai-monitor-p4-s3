#include "ui_connection.h"
#include "ui_enrollment.h"
#include "ui_permission.h"
#include "interaction/permission_ui_api.h"
#include "ai_monitor/ai_monitor.h"
#include "ui/theme.h"
#include <lvgl.h>
#include <cstdio>
#include <cstring>
namespace connection_ui {
static lv_obj_t *root=nullptr,*status=nullptr,*help=nullptr,*consentButton=nullptr,*consentCaption=nullptr,*connectButton=nullptr;
static lv_obj_t* callingScreen=nullptr;
static void text(lv_obj_t* target,const char* value) {
  if(strcmp(lv_label_get_text(target),value))lv_label_set_text(target,value);
}
static lv_obj_t* label(lv_obj_t* parent,int x,int y,int width,const char* text,const lv_font_t* font) {
  auto* value=lv_label_create(parent);lv_obj_set_pos(value,x,y);lv_obj_set_width(value,width);
  lv_label_set_text(value,text);lv_obj_set_style_text_font(value,font,0);
  lv_obj_set_style_text_color(value,lv_color_hex(ui_theme::text),0);
  lv_label_set_long_mode(value,LV_LABEL_LONG_MODE_WRAP);return value;
}
static lv_obj_t* button(int x,int y,int width,const char* text,lv_event_cb_t callback,lv_obj_t** caption=nullptr) {
  auto* value=lv_button_create(root);lv_obj_set_pos(value,x,y);lv_obj_set_size(value,width,64);
  lv_obj_set_style_bg_color(value,lv_color_hex(ui_theme::button),0);lv_obj_set_style_border_color(value,lv_color_hex(ui_theme::border),0);
  lv_obj_set_style_border_width(value,1,0);lv_obj_set_style_radius(value,12,0);lv_obj_set_style_pad_all(value,0,0);
  auto* title=label(value,0,0,width,text,&lv_font_montserrat_24);lv_obj_set_style_text_align(title,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(title);
  lv_obj_add_event_cb(value,callback,LV_EVENT_CLICKED,nullptr);if(caption)*caption=title;return value;
}
static void back(lv_event_t*){ui_connection_hide();}
static void screen_changed(lv_event_t*){ui_connection_hide();}
static void connect(lv_event_t*) {
  interaction::permission_local_opt_in(false);
  ui_connection_hide();ui_enrollment_show();
}
static void consent(lv_event_t*) {
  const auto value=interaction::permission_read();
  if(!value.available || !aim::read().hostPresent || ui_permission_is_active())return;
  if(!interaction::permission_local_opt_in(!value.context.optedIn))lv_label_set_text(status,"Permission setting unavailable. Try again.");
  else lv_label_set_text(status,value.context.optedIn?"Disabling permissions...":"Checking the enrolled PC key...");
}
}
void ui_connection_init() {
  using namespace connection_ui;if(root)return;
  root=lv_obj_create(lv_layer_top());lv_obj_set_pos(root,0,0);lv_obj_set_size(root,800,480);
  lv_obj_set_style_bg_color(root,lv_color_hex(ui_theme::background),0);lv_obj_set_style_bg_opa(root,LV_OPA_COVER,0);
  lv_obj_set_style_pad_all(root,0,0);lv_obj_set_style_border_width(root,0,0);lv_obj_set_scrollable(root,false);
  label(root,24,20,520,"PC connection",&lv_font_montserrat_32);
  button(624,12,152,"BACK",connection_ui::back);
  status=label(root,24,94,752,"",&lv_font_montserrat_24);
  help=label(root,24,136,752,
    "Connect this PC in the app and compare both codes.\n"
    "Claude permissions need separate PC and display opt-in.\n"
    "Each approval needs a new 1.8-second hold.\n"
    "Display opt-in resets when the device restarts.",&lv_font_montserrat_22);
  connectButton=button(24,292,752,"CONNECT PC",connection_ui::connect);
  consentButton=button(24,376,752,"PERMISSIONS OFF",connection_ui::consent,&consentCaption);
  lv_obj_set_hidden(root,true);
}
void ui_connection_show() {
  using namespace connection_ui;if(!root)return;
  if(ui_connection_is_active()){ui_connection_update();return;}
  callingScreen=lv_screen_active();lv_obj_add_event_cb(callingScreen,screen_changed,LV_EVENT_SCREEN_UNLOAD_START,nullptr);
  lv_obj_add_event_cb(callingScreen,screen_changed,LV_EVENT_DELETE,nullptr);
  lv_obj_set_hidden(root,false);ui_connection_update();
}
void ui_connection_hide() {
  using namespace connection_ui;
  if(callingScreen)lv_obj_remove_event_cb(callingScreen,screen_changed);
  callingScreen=nullptr;
  if(root)lv_obj_set_hidden(root,true);
}
bool ui_connection_is_active(){return connection_ui::root && !lv_obj_is_hidden(connection_ui::root);}
void ui_connection_update() {
  using namespace connection_ui;if(!ui_connection_is_active())return;
  const auto value=interaction::permission_read();const bool host=aim::read().hostPresent;
  text(status,!host?"Start the PC host to connect.":value.context.optedIn?"Permissions ON - hold to approve each tool.":value.consentRequested?"Connect this PC before enabling permissions.":"Display permissions OFF");
  text(consentCaption,!value.available?"PERMISSIONS PREVIEW - VALIDATION REQUIRED":value.context.optedIn?"TURN PERMISSIONS OFF":"ENABLE DISPLAY PERMISSIONS");
  lv_obj_set_state(consentButton,LV_STATE_DISABLED,!host || !value.available || ui_permission_is_active());
  lv_obj_set_state(connectButton,LV_STATE_DISABLED,!host || ui_permission_is_active());
}
