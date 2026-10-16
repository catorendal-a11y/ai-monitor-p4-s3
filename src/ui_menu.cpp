#include "ui_menu.h"
#include <lvgl.h>
#include "dashboard.h"
#include "ui_nova.h"
#include "ui_agents.h"
#include "ui_event_center.h"
#include "ui_settings.h"
#include "ui_history.h"
#include "ui_notifications.h"
#include "ai_monitor/ai_monitor.h"
#include "ui/theme.h"
#include "ui/interaction.h"
#include "ui/usage_format.h"

namespace menu_ui {
static lv_obj_t *screen=nullptr,*returnScreen=nullptr;
static void home(lv_event_t*) {ui_nova_show();}
static void usage(lv_event_t*) {dashboard_show();}
static void agents(lv_event_t*) {ui_agents_show();}
static void events(lv_event_t*) {if(returnScreen)lv_screen_load(returnScreen);ui_event_center_show();}
static void settings(lv_event_t*) {
  // Settings must return to the original screen, not to the navigation menu.
  if(returnScreen)lv_screen_load(returnScreen);
  ui_settings_show();
}
static void back(lv_event_t*) {if(returnScreen)lv_screen_load(returnScreen);}
static void history(lv_event_t*){if(returnScreen)lv_screen_load(returnScreen);ui_history_show();}
static lv_obj_t* button(int x,int y,int width,int height,const char* caption,lv_event_cb_t callback) {
  auto* result=lv_button_create(screen);lv_obj_set_pos(result,x,y);lv_obj_set_size(result,width,height);
  lv_obj_set_style_bg_color(result,lv_color_hex(ui_theme::button),0);
  lv_obj_set_style_bg_color(result,lv_color_hex(ui_theme::pressed),LV_STATE_PRESSED);
  lv_obj_set_style_bg_color(result,lv_color_hex(ui_theme::button),LV_STATE_DISABLED);
  lv_obj_set_style_opa(result,LV_OPA_50,LV_STATE_DISABLED);
  lv_obj_set_style_border_width(result,0,0);lv_obj_set_style_shadow_width(result,0,0);
  lv_obj_set_style_pad_all(result,0,0);lv_obj_set_style_radius(result,16,0);
  auto* label=lv_label_create(result);lv_label_set_text(label,caption);
  lv_obj_set_style_text_font(label,&lv_font_montserrat_26,0);
  lv_obj_set_style_text_color(label,lv_color_hex(ui_theme::text),0);lv_obj_center(label);
  lv_obj_set_clickable(label,false);ui_interaction::keep_target(result);
  lv_obj_add_event_cb(result,callback,LV_EVENT_CLICKED,nullptr);return result;
}
}
namespace menu_ui {
void initialize() {
  screen=lv_obj_create(nullptr);ui_theme::watch(screen);
  lv_obj_set_style_bg_color(screen,lv_color_hex(ui_theme::background),0);
  lv_obj_set_style_pad_all(screen,0,0);lv_obj_set_style_border_width(screen,0,0);lv_obj_set_scrollable(screen,false);
  auto* title=lv_label_create(screen);lv_label_set_text(title,"MENU");lv_obj_set_pos(title,24,26);
  lv_obj_set_style_text_font(title,&lv_font_montserrat_32,0);lv_obj_set_style_text_color(title,lv_color_hex(ui_theme::text),0);
  button(632,16,144,56,"BACK",back);
  button(24,104,360,92,"HOME",home);button(408,104,368,92,"USAGE",usage);
  button(24,216,360,92,"AGENTS",agents);button(408,216,368,92,"EVENTS",events);
  button(24,328,360,92,"SETTINGS",settings);button(408,328,368,92,"HISTORY",history);
}
}
void ui_menu_init() {menu_ui::initialize();}
void ui_menu_show() {
  if(!menu_ui::screen || lv_screen_active()==menu_ui::screen)return;
  menu_ui::returnScreen=lv_screen_active();lv_screen_load(menu_ui::screen);ui_menu_update();ui_notifications_update();
}
bool ui_menu_is_active() {return menu_ui::screen && lv_screen_active()==menu_ui::screen;}
void ui_menu_update() {
  if(!menu_ui::screen || lv_screen_active()!=menu_ui::screen)return;
}
