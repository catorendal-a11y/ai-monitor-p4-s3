#include "ui_history.h"
#include "history/types.h"
#include "ai_monitor/ai_monitor.h"
#include "ui/theme.h"
#include "ui/interaction.h"
#include "ui/quota_window.h"
#include "ui_menu.h"
#include <Arduino.h>
#include <lvgl.h>
#include <cstdio>
#include <cstring>
#include <algorithm>
namespace history_ui {
static lv_obj_t *screen=nullptr,*returnScreen=nullptr,*provider=nullptr,*total=nullptr,*status=nullptr,*quota=nullptr,*period=nullptr,*graphLabel=nullptr;
static lv_obj_t* bars[24]{};static uint8_t mode=0,selected=0,count=0;static char keys[8][16]{};
static uint32_t drawnRevision=UINT32_MAX,drawnTheme=UINT32_MAX;static uint8_t drawnMode=255,drawnProvider=255;static bool drawnStale=false;
static lv_obj_t* label(int x,int y,int w,const char* text,const lv_font_t* font,uint32_t color=ui_theme::text) {
  auto* result=lv_label_create(screen);lv_obj_set_pos(result,x,y);lv_obj_set_width(result,w);lv_label_set_text(result,text);
  lv_label_set_long_mode(result,LV_LABEL_LONG_MODE_CLIP);lv_obj_set_style_text_font(result,font,0);
  lv_obj_set_style_text_color(result,lv_color_hex(color),0);lv_obj_set_clickable(result,false);return result;
}
static void text(lv_obj_t* target,const char* value){if(strcmp(lv_label_get_text(target),value))lv_label_set_text(target,value);}
static lv_obj_t* button(int x,int y,int w,const char* caption,lv_event_cb_t action) {
  auto* result=lv_button_create(screen);lv_obj_set_pos(result,x,y);lv_obj_set_size(result,w,48);
  lv_obj_set_style_bg_color(result,lv_color_hex(ui_theme::button),0);lv_obj_set_style_bg_color(result,lv_color_hex(ui_theme::pressed),LV_STATE_PRESSED);
  lv_obj_set_style_radius(result,12,0);lv_obj_set_style_pad_all(result,0,0);lv_obj_set_style_shadow_width(result,0,0);
  auto* title=lv_label_create(result);lv_label_set_text(title,caption);lv_obj_set_style_text_font(title,&lv_font_montserrat_22,0);lv_obj_center(title);
  lv_obj_add_event_cb(result,action,LV_EVENT_CLICKED,nullptr);ui_interaction::keep_target(result);return result;
}
static void back(lv_event_t*){if(returnScreen)lv_screen_load(returnScreen);}
static void menu(lv_event_t*){ui_menu_show();}
static void choice(lv_event_t*){selected=lv_dropdown_get_selected(provider);ui_history_update();}
static void change_period(lv_event_t*){mode=(mode+1)%2;ui_history_update();}
static void number(uint64_t value,char* output,size_t size) {
  if(value>=1000000000ULL)snprintf(output,size,"%.1fB",static_cast<double>(value)/1e9);
  else if(value>=1000000)snprintf(output,size,"%.1fM",static_cast<double>(value)/1e6);
  else if(value>=1000)snprintf(output,size,"%.1fK",static_cast<double>(value)/1e3);
  else snprintf(output,size,"%llu",static_cast<unsigned long long>(value));
}
}
void ui_history_init() {
  using namespace history_ui;
  screen=lv_obj_create(nullptr);ui_theme::watch(screen);lv_obj_set_style_bg_color(screen,lv_color_hex(ui_theme::background),0);
  lv_obj_set_style_pad_all(screen,0,0);lv_obj_set_style_border_width(screen,0,0);lv_obj_set_scrollable(screen,false);
  label(24,22,540,"TODAY / HISTORY",&lv_font_montserrat_32);button(656,14,120,"MENU",menu);
  provider=lv_dropdown_create(screen);lv_obj_set_pos(provider,24,90);lv_obj_set_size(provider,360,56);
  lv_dropdown_set_options(provider,"No providers");lv_obj_set_style_text_font(provider,&lv_font_montserrat_26,0);
  lv_obj_set_style_bg_color(provider,lv_color_hex(ui_theme::button),0);lv_obj_set_style_text_color(provider,lv_color_hex(ui_theme::text),0);
  auto* list=lv_dropdown_get_list(provider);lv_obj_set_style_text_font(list,&lv_font_montserrat_26,0);lv_obj_set_style_max_height(list,300,0);
  ui_interaction::keep_target(provider);lv_obj_add_event_cb(provider,choice,LV_EVENT_VALUE_CHANGED,nullptr);
  total=label(412,92,364,"--",&lv_font_montserrat_40);label(412,140,364,"RECORDED TOKENS TODAY",&lv_font_montserrat_18,ui_theme::muted);
  status=label(24,178,752,"Waiting for history from PC",&lv_font_montserrat_22,ui_theme::muted);
  quota=label(24,212,752,"Sessions / active time: not recorded",&lv_font_montserrat_22,ui_theme::muted);
  graphLabel=label(24,257,752,"24 HOURLY BUCKETS / GAPS UNKNOWN",&lv_font_montserrat_18,ui_theme::accent);
  for(unsigned i=0;i<24;++i) {
    bars[i]=lv_obj_create(screen);lv_obj_set_pos(bars[i],24+i*31,397);lv_obj_set_size(bars[i],23,3);
    lv_obj_set_style_border_width(bars[i],0,0);lv_obj_set_style_radius(bars[i],3,0);lv_obj_set_scrollable(bars[i],false);lv_obj_set_clickable(bars[i],false);
    lv_obj_set_style_bg_color(bars[i],lv_color_hex(ui_theme::muted),0);
  }
  button(24,432,224,"BACK",back);period=button(280,432,240,"SHOW 7 DAYS",change_period);
  label(552,442,224,"Numbers only / local",&lv_font_montserrat_18,ui_theme::muted);
}
void ui_history_show(){using namespace history_ui;if(!screen || lv_screen_active()==screen)return;returnScreen=lv_screen_active();lv_screen_load(screen);ui_history_update();}
bool ui_history_is_active(){return history_ui::screen && lv_screen_active()==history_ui::screen;}
void ui_history_update() {
  using namespace history_ui;if(!ui_history_is_active())return;
  const auto data=history::read();const uint32_t now=millis();
  const bool stale=!aim::read().hostPresent || now-data.receivedAt>=120000;
  if(drawnRevision==data.revision && drawnMode==mode && drawnProvider==selected && drawnTheme==ui_theme::revision && drawnStale==stale)return;
  bool changed=count!=data.count;
  for(unsigned i=0;i<data.count && i<8;++i)changed|=strcmp(keys[i],data.providers[i].key)!=0;
  if(changed && (lv_dropdown_is_open(provider) || lv_obj_has_state(provider,LV_STATE_PRESSED)))return;
  // Do not replace the dropdown's option identity while a finger/menu is selecting it.
  if(changed && !lv_dropdown_is_open(provider) && !lv_obj_has_state(provider,LV_STATE_PRESSED)) {
    char options[256]{};size_t used=0;
    char previous[16]{};if(selected<count)strcpy(previous,keys[selected]);selected=0;count=data.count;
    for(unsigned i=0;i<count;++i) {
      strcpy(keys[i],data.providers[i].key);if(!strcmp(previous,keys[i]))selected=i;
      const auto* style=aim::provider_style(keys[i]);
      used+=snprintf(options+used,sizeof(options)-used,"%s%s",i?"\n":"",style?style->label:keys[i]);
    }
    lv_dropdown_set_options(provider,count?options:"No providers");lv_dropdown_set_selected(provider,selected);
  }
  lv_obj_set_state(provider,LV_STATE_DISABLED,!data.enabled || !data.count);
  const history::Provider* row=nullptr;
  if(selected<count)for(unsigned i=0;i<data.count;++i)if(!strcmp(keys[selected],data.providers[i].key))row=&data.providers[i];
  const bool available=data.fresh && data.enabled && !data.error && row;
  char value[128];
  if(available && (row->dailyKnown&(1u<<6)))number(row->daily[6],value,sizeof(value));else snprintf(value,sizeof(value),"--");text(total,value);
  if(!data.fresh)snprintf(value,sizeof(value),"Waiting for the updated PC host");
  else if(!data.enabled)snprintf(value,sizeof(value),"Enable local history in PC Host settings");
  else if(data.error)snprintf(value,sizeof(value),"History unavailable / check PC storage");
  else snprintf(value,sizeof(value),"%s / Recorded locally%s",data.date,stale?" / STALE":"");
  text(status,value);
  if(available && row->quotaKnown) {
    char window[48];quota_window_label(row->windowMinutes,"Model",window,sizeof(window));
    if(row->changeKnown)snprintf(value,sizeof(value),"%s: %.0f%% used / +%.0f points / %um ago",window,row->usedPercent,row->changePercent,row->quotaAgeMinutes);
    else snprintf(value,sizeof(value),"%s: %.0f%% used / %um ago",window,row->usedPercent,row->quotaAgeMinutes);
  } else snprintf(value,sizeof(value),"Sessions / active time: not recorded");
  text(quota,value);
  text(graphLabel,mode?"7 LOCAL DAYS / GAPS UNKNOWN":"24 HOURLY BUCKETS / GAPS UNKNOWN");
  text(lv_obj_get_child(period,0),mode?"SHOW 24 HOURS":"SHOW 7 DAYS");
  const unsigned bins=mode?7:24;const uint64_t* values=available?(mode?row->daily:row->hourly):nullptr;
  const uint32_t known=available?(mode?row->dailyKnown:row->hourlyKnown):0;
  uint64_t maximum=1;for(unsigned i=0;i<bins;++i)if((known&(1u<<i)) && values[i]>maximum)maximum=values[i];
  for(unsigned i=0;i<24;++i) {
    lv_obj_set_hidden(bars[i],i>=bins);if(i>=bins)continue;
    const bool observed=known&(1u<<i);
    const int height=observed?std::max(3,static_cast<int>(static_cast<double>(values[i])/maximum*100)):3;
    lv_obj_set_pos(bars[i],24+i*(mode?107:31),400-height);lv_obj_set_size(bars[i],mode?86:23,height);
    lv_obj_set_style_bg_color(bars[i],lv_color_hex(observed?ui_theme::accent:ui_theme::muted),0);
  }
  drawnRevision=data.revision;drawnMode=mode;drawnProvider=selected;drawnTheme=ui_theme::revision;drawnStale=stale;
  lv_obj_update_layout(screen);
}
