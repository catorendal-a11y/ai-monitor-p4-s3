#include "ui_agents.h"
#include <Arduino.h>
#include <lvgl.h>
#include <cstdio>
#include <cstring>
#include "live_agent/activity_types.h"
#include "ai_monitor/ai_monitor.h"
#include "ui_nova.h"
#include "ui_settings.h"
#include "ui/theme.h"
#include "ui/interaction.h"

namespace agents_ui {
static lv_obj_t *screen=nullptr,*empty=nullptr,*help=nullptr,*summary=nullptr,*next=nullptr;
struct Row {lv_obj_t *card=nullptr,*provider=nullptr,*identity=nullptr,*state=nullptr;};
static Row rows[4];
static uint8_t page=0;
static uint32_t epoch=0;
static void text(lv_obj_t* label,const char* value) {
  if(strcmp(lv_label_get_text(label),value))lv_label_set_text(label,value);
}
static lv_obj_t* label(lv_obj_t* parent,int x,int y,int width,const char* value,
                       const lv_font_t* font,uint32_t color) {
  auto* object=lv_label_create(parent);lv_label_set_text(object,value);
  lv_obj_set_pos(object,x,y);lv_obj_set_width(object,width);
  lv_label_set_long_mode(object,LV_LABEL_LONG_CLIP);
  lv_obj_set_style_text_font(object,font,0);lv_obj_set_style_text_color(object,lv_color_hex(color),0);
  lv_obj_set_clickable(object,false);return object;
}
static lv_obj_t* button(int x,int width,const char* caption,lv_event_cb_t callback) {
  auto* object=lv_btn_create(screen);lv_obj_set_pos(object,x,426);lv_obj_set_size(object,width,48);
  lv_obj_set_style_bg_color(object,lv_color_hex(ui_theme::button),0);
  lv_obj_set_style_bg_color(object,lv_color_hex(ui_theme::pressed),LV_STATE_PRESSED);
  lv_obj_set_style_bg_color(object,lv_color_hex(ui_theme::button),LV_STATE_DISABLED);
  lv_obj_set_style_opa(object,LV_OPA_50,LV_STATE_DISABLED);
  lv_obj_set_style_border_width(object,0,0);lv_obj_set_style_shadow_width(object,0,0);
  auto* captionLabel=label(object,0,0,width-16,caption,&lv_font_montserrat_16,ui_theme::text);
  lv_obj_set_style_text_align(captionLabel,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(captionLabel);
  ui_interaction::keep_target(object);lv_obj_add_event_cb(object,callback,LV_EVENT_CLICKED,nullptr);return object;
}
static void back(lv_event_t*) {ui_nova_show();}
static void settings(lv_event_t*) {ui_settings_show();}
static void next_page(lv_event_t*) {page=page?0:1;ui_agents_update();}
void init() {
  screen=lv_obj_create(nullptr);ui_theme::watch(screen);
  lv_obj_set_style_bg_color(screen,lv_color_hex(ui_theme::background),0);
  lv_obj_set_style_pad_all(screen,0,0);lv_obj_set_style_border_width(screen,0,0);lv_obj_set_scrollable(screen,false);
  label(screen,24,14,740,"AI MONITOR / LIVE AGENTS",&lv_font_montserrat_26,ui_theme::text);
  label(screen,24,54,752,"Last reported events / read-only / up to 8 entries",&lv_font_montserrat_16,ui_theme::muted);
  for(unsigned i=0;i<4;++i) {
    auto& row=rows[i];row.card=lv_obj_create(screen);
    lv_obj_set_pos(row.card,24,96+i*72);lv_obj_set_size(row.card,752,68);
    lv_obj_set_style_pad_all(row.card,0,0);lv_obj_set_style_bg_color(row.card,lv_color_hex(ui_theme::surface),0);
    lv_obj_set_style_border_color(row.card,lv_color_hex(ui_theme::border),0);
    lv_obj_set_scrollable(row.card,false);lv_obj_set_clickable(row.card,false);
    row.provider=label(row.card,16,7,350,"",&lv_font_montserrat_20,ui_theme::text);
    row.identity=label(row.card,16,36,360,"",&lv_font_montserrat_16,ui_theme::muted);
    row.state=label(row.card,414,20,310,"",&lv_font_montserrat_20,ui_theme::accent);
  }
  empty=label(screen,24,112,752,"No recent agent events",&lv_font_montserrat_26,ui_theme::text);
  help=label(screen,24,162,752,"Link session events in the PC app. Missing phases stay unknown.",&lv_font_montserrat_16,ui_theme::muted);
  summary=label(screen,24,392,752,"Waiting for USB live data",&lv_font_montserrat_16,ui_theme::muted);
  button(24,224,"COMPANION",back);next=button(288,224,"NEXT PAGE",next_page);button(552,224,"SETTINGS",settings);
}
void show() {
  if(!screen)return;
  page=0;lv_screen_load(screen);ui_agents_update();
}
void update() {
  if(!screen || lv_screen_active()!=screen)return;
  const auto snapshot=live_agent::read_usb();
  const uint32_t age=millis()-snapshot.receivedAt;
  const bool fresh=snapshot.fresh && age<live_agent::activity_lease_ms;
  const unsigned count=fresh?(snapshot.count<=8?snapshot.count:0):0;
  if(epoch!=snapshot.epoch) {epoch=snapshot.epoch;page=0;}
  if(count<=4)page=0;
  lv_obj_set_hidden(empty,count!=0);lv_obj_set_hidden(help,count!=0);
  for(unsigned i=0;i<4;++i) {
    auto& row=rows[i];const unsigned index=page*4+i;
    lv_obj_set_hidden(row.card,index>=count);
    if(index>=count) {text(row.provider,"");text(row.identity,"");text(row.state,"");continue;}
    const auto& agent=snapshot.agents[index];
    const auto* style=aim::provider_style(agent.provider);
    text(row.provider,style?style->label:"UNKNOWN PROVIDER");
    char identifier[48];snprintf(identifier,sizeof(identifier),"Session %.12s",agent.id);text(row.identity,identifier);
    const unsigned state=static_cast<unsigned>(agent.state);
    text(row.state,state<10?live_agent::activity_names[state]:"UNKNOWN");
    const uint32_t color=agent.state==live_agent::ActivityState::FAILED?0xFF6B6B:
        agent.state==live_agent::ActivityState::WAITING?0xFFCF66:
        state<2 || state>=10?ui_theme::muted:ui_theme::accent;
    if(!lv_color_eq(lv_obj_get_style_text_color(row.state,LV_PART_MAIN),lv_color_hex(color)))
      lv_obj_set_style_text_color(row.state,lv_color_hex(color),0);
  }
  if(count>4)lv_obj_remove_state(next,LV_STATE_DISABLED);else lv_obj_add_state(next,LV_STATE_DISABLED);
  char status[100];
  if(!fresh)snprintf(status,sizeof(status),"USB live data unavailable / reconnect or link events in the PC app");
  else if(!count)snprintf(status,sizeof(status),"No recent events / source status expires after 30 seconds");
  else snprintf(status,sizeof(status),"Page %u/%u / %u reported entries / USB update %lu seconds ago",
      page+1,count>4?2:1,count,static_cast<unsigned long>(age/1000));
  text(summary,status);
}
}
void ui_agents_init() {agents_ui::init();}
void ui_agents_show() {agents_ui::show();}
void ui_agents_update() {agents_ui::update();}
