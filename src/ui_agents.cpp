#include "ui_agents.h"
#include <Arduino.h>
#include <lvgl.h>
#include <cstdio>
#include <cstring>
#include "live_agent/activity_types.h"
#include "ai_monitor/ai_monitor.h"
#include "ui_nova.h"
#include "ui_settings.h"
#include "ui_event_center.h"
#include "ui_menu.h"
#include "ui/theme.h"
#include "ui/interaction.h"

namespace agents_ui {
static lv_obj_t *screen=nullptr,*empty=nullptr,*help=nullptr,*summary=nullptr,*next=nullptr;
struct Row {lv_obj_t *card=nullptr,*provider=nullptr,*identity=nullptr,*state=nullptr;};
static Row rows[4];
static uint8_t page=0;
static uint8_t pages=1;
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
  auto* captionLabel=label(object,0,0,width-16,caption,&lv_font_montserrat_22,ui_theme::text);
  lv_obj_set_style_text_align(captionLabel,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(captionLabel);
  ui_interaction::keep_target(object);lv_obj_add_event_cb(object,callback,LV_EVENT_CLICKED,nullptr);return object;
}
static void back(lv_event_t*) {ui_nova_show();}
static void show_menu(lv_event_t*) {ui_menu_show();}
static void next_page(lv_event_t*) {page=static_cast<uint8_t>((page+1)%pages);ui_agents_update();}
void init() {
  screen=lv_obj_create(nullptr);ui_theme::watch(screen);
  lv_obj_set_style_bg_color(screen,lv_color_hex(ui_theme::background),0);
  lv_obj_set_style_pad_all(screen,0,0);lv_obj_set_style_border_width(screen,0,0);lv_obj_set_scrollable(screen,false);
  label(screen,24,14,600,"LIVE AGENTS",&lv_font_montserrat_32,ui_theme::text);
  auto* events=button(656,120,"MENU",show_menu);lv_obj_set_y(events,14);
  for(unsigned i=0;i<4;++i) {
    auto& row=rows[i];row.card=lv_obj_create(screen);
    lv_obj_set_pos(row.card,24,94+i*80);lv_obj_set_size(row.card,752,76);
    lv_obj_set_style_pad_all(row.card,0,0);lv_obj_set_style_bg_color(row.card,lv_color_hex(ui_theme::surface),0);
    lv_obj_set_style_border_color(row.card,lv_color_hex(ui_theme::border),0);
    lv_obj_set_scrollable(row.card,false);lv_obj_set_clickable(row.card,false);
    row.provider=label(row.card,16,4,350,"",&lv_font_montserrat_26,ui_theme::text);
    row.identity=label(row.card,16,43,380,"",&lv_font_montserrat_20,ui_theme::muted);
    row.state=label(row.card,410,20,320,"",&lv_font_montserrat_24,ui_theme::accent);
  }
  empty=label(screen,24,112,752,"No recent agent events",&lv_font_montserrat_26,ui_theme::text);
  help=label(screen,24,162,752,"Enable agent events in the PC app.",&lv_font_montserrat_24,ui_theme::muted);
  summary=label(screen,24,56,600,"Waiting for USB live data",&lv_font_montserrat_20,ui_theme::muted);
  button(24,224,"HOME",back);next=button(552,224,"NEXT PAGE",next_page);
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
  const unsigned agents=fresh?(snapshot.count<=8?snapshot.count:0):0;
  // Presentation-only fallback: selected providers are not fabricated live agents.
  // Keep their quota/token snapshot separate from the live domain and permission authority.
  const auto quota=aim::read();
  const aim::ProviderStyle* available[8]{};unsigned providerCount=0;
  if(quota.hostPresent && quota.viewsConfigured)for(unsigned i=0;i<quota.viewCount && i<8;++i) {
    const auto* style=aim::provider_style(quota.viewKeys[i]);if(!style)continue;
    bool represented=false;
    for(unsigned j=0;j<agents;++j)if(!strcmp(snapshot.agents[j].provider,style->key))represented=true;
    for(unsigned j=0;j<providerCount;++j)if(available[j]==style)represented=true;
    if(!represented)available[providerCount++]=style;
  }
  const unsigned count=agents+providerCount;
  pages=static_cast<uint8_t>(count?((count+3)/4):1);
  if(epoch!=snapshot.epoch) {epoch=snapshot.epoch;page=0;}
  if(page>=pages)page=0;
  lv_obj_set_hidden(empty,count!=0);lv_obj_set_hidden(help,count!=0);
  for(unsigned i=0;i<4;++i) {
    auto& row=rows[i];const unsigned index=page*4+i;
    lv_obj_set_hidden(row.card,index>=count);
    if(index>=count) {text(row.provider,"");text(row.identity,"");text(row.state,"");continue;}
    if(index>=agents) {
      const auto* style=available[index-agents];text(row.provider,style->label);
      const bool counter=quota.tokenUsageKnown && millis()-quota.tokenActivityMs<35000 &&
          (quota.tokenSourceMask&style->activityMask)!=0;
      text(row.identity,counter?"Token activity available":"No recent token activity");
      text(row.state,!strcmp(style->key,"codex") || !strcmp(style->key,"claude")?"NO RECENT EVENTS":"ACTIVITY ONLY");
      lv_obj_set_style_text_color(row.state,lv_color_hex(ui_theme::muted),0);
      continue;
    }
    const auto& entry=snapshot.agents[index];
    const auto* style=aim::provider_style(entry.provider);
    text(row.provider,style?style->label:"UNKNOWN PROVIDER");
    char identifier[64];
    if(entry.hasElapsed)snprintf(identifier,sizeof(identifier),"%lu:%02lu:%02lu / event %us ago",
        static_cast<unsigned long>(entry.elapsedSeconds/3600),
        static_cast<unsigned long>((entry.elapsedSeconds/60)%60),static_cast<unsigned long>(entry.elapsedSeconds%60),entry.observedAgeSeconds);
    else snprintf(identifier,sizeof(identifier),"Start unknown / event %us ago",entry.observedAgeSeconds);
    text(row.identity,identifier);
    const unsigned state=static_cast<unsigned>(entry.state);
    char phase[32];snprintf(phase,sizeof(phase),"%s",state<agent::state_count?live_agent::activity_names[state]:"UNKNOWN");
    for(auto* c=phase;*c;++c)if(*c=='_')*c=' ';
    text(row.state,phase);
    const uint32_t color=entry.state==live_agent::ActivityState::FAILED?0xFF6B6B:
        (entry.state==live_agent::ActivityState::WAITING || entry.state==agent::State::NEEDS_ATTENTION)?0xFFCF66:
        state<2 || state>=agent::state_count?ui_theme::muted:ui_theme::accent;
    if(!lv_color_eq(lv_obj_get_style_text_color(row.state,LV_PART_MAIN),lv_color_hex(color)))
      lv_obj_set_style_text_color(row.state,lv_color_hex(color),0);
  }
  if(count>4)lv_obj_remove_state(next,LV_STATE_DISABLED);else lv_obj_add_state(next,LV_STATE_DISABLED);
  lv_obj_set_hidden(next,count<=4);
  char status[100];
  if(providerCount)snprintf(status,sizeof(status),"Page %u/%u / %u agents / %u providers",
      page+1,pages,agents,providerCount);
  else if(!fresh)snprintf(status,sizeof(status),"Waiting for host / check the PC app");
  else if(!count)snprintf(status,sizeof(status),"No recent events / enable events on PC");
  else snprintf(status,sizeof(status),"Page %u/%u / %u agents / updated %lus ago",
      page+1,pages,count,static_cast<unsigned long>(age/1000));
  text(summary,status);
}
}
void ui_agents_init() {agents_ui::init();}
void ui_agents_show() {agents_ui::show();}
void ui_agents_update() {agents_ui::update();}
