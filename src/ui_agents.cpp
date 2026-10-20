#include "ui_agents.h"
#include <Arduino.h>
#include <lvgl.h>
#include <cstdio>
#include <cstring>
#include "live_agent/activity_types.h"
#include "ui/session_hue.h"
#include "ai_monitor/ai_monitor.h"
#include "ui_nova.h"
#include "ui_settings.h"
#include "ui_event_center.h"
#include "ui_menu.h"
#include "ui/theme.h"
#include "ui/interaction.h"
#include "ui/navigation.h"

namespace agents_ui {
static lv_obj_t *screen=nullptr,*empty=nullptr,*help=nullptr,*summary=nullptr,*pageInfo=nullptr,*next=nullptr;
struct Row {lv_obj_t *card=nullptr,*chip=nullptr,*provider=nullptr,*identity=nullptr,*state=nullptr;};
// One color per host-derived hue, evenly spaced around the wheel at similar brightness so the same
// session is recognized at a glance; adjacent hues stay clearly different.
static const auto& hue_colors=session_hue_colors;
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
static void show_menu(lv_event_t*) {ui_menu_show();}
static void next_page(lv_event_t*) {page=static_cast<uint8_t>((page+1)%pages);ui_agents_update();}
void init() {
  screen=lv_obj_create(nullptr);ui_theme::watch(screen);
  lv_obj_set_style_bg_color(screen,lv_color_hex(ui_theme::background),0);
  lv_obj_set_style_pad_all(screen,0,0);lv_obj_set_style_border_width(screen,0,0);lv_obj_set_scrollable(screen,false);
  label(screen,24,14,600,"AGENT SESSIONS",&lv_font_montserrat_32,ui_theme::text);
  auto* events=button(656,120,"MENU",show_menu);lv_obj_set_y(events,14);
  for(unsigned i=0;i<4;++i) {
    auto& row=rows[i];row.card=lv_obj_create(screen);
    lv_obj_set_pos(row.card,24,94+i*80);lv_obj_set_size(row.card,752,76);
    lv_obj_set_style_pad_all(row.card,0,0);lv_obj_set_style_bg_color(row.card,lv_color_hex(ui_theme::surface),0);
    lv_obj_set_style_border_color(row.card,lv_color_hex(ui_theme::border),0);
    lv_obj_set_scrollable(row.card,false);lv_obj_set_clickable(row.card,false);
    row.chip=lv_obj_create(row.card);lv_obj_set_pos(row.chip,0,0);lv_obj_set_size(row.chip,8,76);
    lv_obj_set_style_radius(row.chip,0,0);lv_obj_set_style_border_width(row.chip,0,0);lv_obj_set_style_pad_all(row.chip,0,0);
    lv_obj_set_scrollable(row.chip,false);lv_obj_set_clickable(row.chip,false);lv_obj_set_hidden(row.chip,true);
    row.provider=label(row.card,16,4,380,"",&lv_font_montserrat_22,ui_theme::text);
    row.identity=label(row.card,16,43,380,"",&lv_font_montserrat_16,ui_theme::muted);
    row.state=label(row.card,410,20,320,"",&lv_font_montserrat_24,ui_theme::accent);
  }
  empty=label(screen,24,112,752,"No observed agent sessions",&lv_font_montserrat_26,ui_theme::text);
  help=label(screen,24,162,752,"Check event observers in the PC app.",&lv_font_montserrat_24,ui_theme::muted);
  // State counts on the left, session count and page on the right; MENU starts at x 656.
  summary=label(screen,24,56,440,"Waiting for USB live data",&lv_font_montserrat_18,ui_theme::muted);
  pageInfo=label(screen,450,56,200,"",&lv_font_montserrat_18,ui_theme::muted);
  lv_obj_set_style_text_align(pageInfo,LV_TEXT_ALIGN_RIGHT,0);
  ui_navigation::create(screen,ui_navigation::Page::agents);
  next=button(552,224,"NEXT PAGE",next_page);lv_obj_set_y(next,432);
}
void show() {
  if(!screen)return;
  page=0;lv_screen_load(screen);ui_agents_update();
}
// Why the list is empty. A host that reports the observer masks lets the screen name what to link.
static void empty_hint(const live_agent::UsbLiveSnapshot& snapshot,bool fresh,char* out,size_t capacity) {
  if(!fresh) {snprintf(out,capacity,"Connect the PC app to receive session events.");return;}
  if(!snapshot.hasSummary) {
    snprintf(out,capacity,"Check event observers in the PC app.\nProvider quotas and token activity are on Usage.");return;
  }
  if(!snapshot.selectedMask) {
    snprintf(out,capacity,"None of the selected AIs report sessions.\nSelect Codex, Claude Code or ZCode in the PC app.");return;
  }
  const uint8_t unlinked=snapshot.selectedMask&static_cast<uint8_t>(~snapshot.linkedMask);
  if(!unlinked) {
    snprintf(out,capacity,"Observers are linked. Start a session in a linked AI.\nProvider quotas and token activity are on Usage.");return;
  }
  char names[100]="";size_t length=0;
  for(const char* key:{"codex","zcode","claude","gemini","copilot","cursor","antigravity","opencode"}) {
    const auto* style=aim::provider_style(key);
    if(!style || !(style->activityMask&unlinked))continue;
    const int wrote=snprintf(names+length,sizeof(names)-length,"%s%s",length?", ":"",style->label);
    if(wrote>0)length=length+static_cast<size_t>(wrote)<sizeof(names)?length+static_cast<size_t>(wrote):sizeof(names)-1;
  }
  snprintf(out,capacity,"Not linked: %s\nLink them in the PC app: Agents > Provider events.",names);
}
void update() {
  if(!screen || lv_screen_active()!=screen)return;
  const auto snapshot=live_agent::read_usb();
  const uint32_t age=millis()-snapshot.receivedAt;
  const bool fresh=snapshot.fresh && age<live_agent::activity_lease_ms;
  const unsigned agents=fresh?(snapshot.count<=8?snapshot.count:0):0;
  const unsigned count=agents;
  pages=static_cast<uint8_t>(count?((count+3)/4):1);
  if(epoch!=snapshot.epoch) {epoch=snapshot.epoch;page=0;}
  if(page>=pages)page=0;
  lv_obj_set_hidden(empty,count!=0);lv_obj_set_hidden(help,count!=0);
  text(empty,fresh?"No observed agent sessions":"Agent feed unavailable");
  char hint[160];empty_hint(snapshot,fresh,hint,sizeof(hint));
  text(help,hint);
  for(unsigned i=0;i<4;++i) {
    auto& row=rows[i];const unsigned index=page*4+i;
    lv_obj_set_hidden(row.card,index>=count);
    if(index>=count) {text(row.provider,"");text(row.identity,"");text(row.state,"");continue;}
    const auto& entry=snapshot.agents[index];
    const auto* style=aim::provider_style(entry.provider);
    const size_t idLength=strlen(entry.id);
    const char* shortId=entry.id+(idLength>8?idLength-8:0);
    // A host-derived name and color are recognizable at a glance; without them the id's tail is shown.
    char heading[64];
    if(entry.hasLabel)snprintf(heading,sizeof(heading),"%.24s / %.15s",style?style->label:"UNKNOWN",entry.label);
    else snprintf(heading,sizeof(heading),"%.24s / %.8s",style?style->label:"UNKNOWN",shortId);
    text(row.provider,heading);
    lv_obj_set_hidden(row.chip,!entry.hasLabel);
    if(entry.hasLabel) {
      const uint32_t chip=hue_colors[entry.hue<live_agent::hue_count?entry.hue:0];
      if(!lv_color_eq(lv_obj_get_style_bg_color(row.chip,LV_PART_MAIN),lv_color_hex(chip)))
        lv_obj_set_style_bg_color(row.chip,lv_color_hex(chip),0);
    }
    char identifier[80];
    const auto observedAge=static_cast<unsigned long long>(live_agent::observed_age_ms(snapshot,entry,millis())/1000u);
    if(entry.hasElapsed)snprintf(identifier,sizeof(identifier),"Session %lu:%02lu:%02lu / event %llus ago",
        static_cast<unsigned long>(entry.elapsedSeconds/3600),
        static_cast<unsigned long>((entry.elapsedSeconds/60)%60),static_cast<unsigned long>(entry.elapsedSeconds%60),observedAge);
    else snprintf(identifier,sizeof(identifier),"Start unknown / event %llus ago",observedAge);
    text(row.identity,identifier);
    const unsigned state=static_cast<unsigned>(entry.state);
    const bool observedStale=live_agent::observed_age_ms(snapshot,entry,millis())>=live_agent::activity_lease_ms;
    char phase[40];snprintf(phase,sizeof(phase),"%s%s",observedStale?"Last: ":"",
        state<agent::state_count?live_agent::activity_names[state]:"UNKNOWN");
    for(auto* c=phase;*c;++c)if(*c=='_')*c=' ';
    text(row.state,phase);
    const uint32_t color=observedStale?ui_theme::muted:(entry.state==live_agent::ActivityState::FAILED || entry.state==agent::State::ERROR)?0xFF6B6B:
        (entry.state==live_agent::ActivityState::WAITING || entry.state==agent::State::NEEDS_ATTENTION)?0xFFCF66:
        state<2 || state>=agent::state_count?ui_theme::muted:ui_theme::accent;
    if(!lv_color_eq(lv_obj_get_style_text_color(row.state,LV_PART_MAIN),lv_color_hex(color)))
      lv_obj_set_style_text_color(row.state,lv_color_hex(color),0);
  }
  if(count>4)lv_obj_remove_state(next,LV_STATE_DISABLED);else lv_obj_add_state(next,LV_STATE_DISABLED);
  lv_obj_set_hidden(next,count<=4);
  // Counts by state, the most urgent first, in the color of the most urgent one present: the whole
  // screen is readable without reading a row. An old event no longer says what the agent is doing.
  unsigned errors=0,attention=0,working=0,idle=0;
  for(unsigned i=0;i<count;++i) {
    const auto& entry=snapshot.agents[i];
    if(live_agent::observed_age_ms(snapshot,entry,millis())>=live_agent::activity_lease_ms) {++idle;continue;}
    switch(entry.state) {
      case agent::State::ERROR:++errors;break;
      case agent::State::WAITING:case agent::State::NEEDS_ATTENTION:++attention;break;
      case agent::State::WORKING:case agent::State::THINKING:case agent::State::READING:case agent::State::SEARCHING:
      case agent::State::EDITING:case agent::State::WRITING:case agent::State::RUNNING:case agent::State::BUILDING:
      case agent::State::TESTING:++working;break;
      default:++idle;break;
    }
  }
  char status[100]="";size_t used=0;
  const auto add=[&](unsigned number,const char* one,const char* many) {
    if(!number)return;
    const int wrote=snprintf(status+used,sizeof(status)-used,"%s%u %s",used?" / ":"",number,number==1?one:many);
    if(wrote>0)used=used+static_cast<size_t>(wrote)<sizeof(status)?used+static_cast<size_t>(wrote):sizeof(status)-1;
  };
  add(errors,"error","errors");add(attention,"need you","need you");add(working,"working","working");add(idle,"idle","idle");
  if(!fresh)snprintf(status,sizeof(status),"Waiting for host / check the PC app");
  else if(!count)snprintf(status,sizeof(status),"0 sessions / USB live data received");
  text(summary,status);
  const uint32_t summaryColor=(!fresh||!count)?ui_theme::muted:errors?0xFF6B6B:attention?0xFFCF66:working?ui_theme::accent:ui_theme::muted;
  if(!lv_color_eq(lv_obj_get_style_text_color(summary,LV_PART_MAIN),lv_color_hex(summaryColor)))
    lv_obj_set_style_text_color(summary,lv_color_hex(summaryColor),0);
  // "8 of 11" when the host observes more sessions than it can list; a total below the list is ignored.
  char info[48]="";
  if(count) {
    const unsigned total=snapshot.hasSummary&&snapshot.total>count?snapshot.total:count;
    if(total>count)snprintf(info,sizeof(info),"%u of %u",count,total);
    else snprintf(info,sizeof(info),"%u session%s",count,count==1?"":"s");
    if(pages>1) {const size_t length=strlen(info);snprintf(info+length,sizeof(info)-length," / page %u/%u",page+1,pages);}
  }
  text(pageInfo,info);
}
}
void ui_agents_init() {agents_ui::init();}
void ui_agents_show() {agents_ui::show();}
void ui_agents_update() {agents_ui::update();}
bool ui_agents_is_active() {return agents_ui::screen && lv_screen_active()==agents_ui::screen;}
