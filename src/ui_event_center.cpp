#include "ui_event_center.h"
#include <Arduino.h>
#include <lvgl.h>
#include <cstdio>
#include "events/center.h"
#include "ai_monitor/ai_monitor.h"
#include "ui_agents.h"
#include "ui_notifications.h"
#include "ui/theme.h"
#include "ui/interaction.h"
namespace event_center_ui {
static events::Center center;
static lv_obj_t *screen=nullptr,*summary=nullptr,*next=nullptr;
struct Row {lv_obj_t *card=nullptr,*heading=nullptr,*detail=nullptr;};
static Row rows[4];static unsigned page=0,pages=1;
static void text(lv_obj_t* label,const char* value){if(strcmp(lv_label_get_text(label),value))lv_label_set_text(label,value);}
static lv_obj_t* label(lv_obj_t* parent,int x,int y,int width,const char* value,const lv_font_t* font,uint32_t color) {
  auto* result=lv_label_create(parent);lv_obj_set_pos(result,x,y);lv_obj_set_width(result,width);
  lv_label_set_long_mode(result,LV_LABEL_LONG_CLIP);lv_obj_set_style_text_font(result,font,0);
  lv_obj_set_style_text_color(result,lv_color_hex(color),0);lv_label_set_text(result,value);lv_obj_set_clickable(result,false);return result;
}
static void back(lv_event_t*){ui_agents_show();}
static void mark_read(lv_event_t*){center.mark_read();ui_event_center_update();}
static void next_page(lv_event_t*){page=(page+1)%pages;ui_event_center_update();}
static lv_obj_t* button(int x,const char* name,lv_event_cb_t handler) {
  auto* result=lv_btn_create(screen);lv_obj_set_pos(result,x,426);lv_obj_set_size(result,224,48);
  lv_obj_set_style_bg_color(result,lv_color_hex(ui_theme::button),0);lv_obj_set_style_bg_color(result,lv_color_hex(ui_theme::pressed),LV_STATE_PRESSED);
  lv_obj_set_style_border_width(result,0,0);lv_obj_set_style_shadow_width(result,0,0);
  auto* caption=label(result,0,0,208,name,&lv_font_montserrat_22,ui_theme::text);lv_obj_center(caption);
  lv_obj_set_style_text_align(caption,LV_TEXT_ALIGN_CENTER,0);ui_interaction::keep_target(result);
  lv_obj_add_event_cb(result,handler,LV_EVENT_CLICKED,nullptr);return result;
}
}
namespace event_center_ui {
void initialize() {
  screen=lv_obj_create(nullptr);ui_theme::watch(screen);lv_obj_set_scrollable(screen,false);
  lv_obj_set_style_pad_all(screen,0,0);lv_obj_set_style_border_width(screen,0,0);lv_obj_set_style_bg_color(screen,lv_color_hex(ui_theme::background),0);
  label(screen,24,14,752,"NOTIFICATIONS",&lv_font_montserrat_32,ui_theme::text);
  for(unsigned i=0;i<4;++i) {
    auto& row=rows[i];row.card=lv_obj_create(screen);lv_obj_set_pos(row.card,24,94+80*i);lv_obj_set_size(row.card,752,76);
    lv_obj_set_style_pad_all(row.card,0,0);lv_obj_set_scrollable(row.card,false);lv_obj_set_clickable(row.card,false);
    lv_obj_set_style_bg_color(row.card,lv_color_hex(ui_theme::surface),0);lv_obj_set_style_border_color(row.card,lv_color_hex(ui_theme::border),0);
    row.heading=label(row.card,16,4,716,"",&lv_font_montserrat_24,ui_theme::text);
    row.detail=label(row.card,16,43,716,"",&lv_font_montserrat_20,ui_theme::muted);
  }
  summary=label(screen,24,56,752,"No events recorded this boot",&lv_font_montserrat_20,ui_theme::muted);
  button(24,"BACK",back);next=button(288,"NEXT PAGE",next_page);button(552,"READ ALL",mark_read);
}
} // namespace event_center_ui
void ui_event_center_init(){event_center_ui::initialize();}
bool ui_event_center_is_active(){return event_center_ui::screen && lv_screen_active()==event_center_ui::screen;}
unsigned ui_event_center_unread(){return event_center_ui::center.unread();}
void ui_event_center_show(){if(!event_center_ui::screen)return;event_center_ui::page=0;lv_screen_load(event_center_ui::screen);ui_event_center_update();ui_notifications_update();}
void ui_event_center_quota(const char* source,bool critical){event_center_ui::center.quota(source,critical,millis());}
namespace event_center_ui {
void update() {
  const uint32_t now=millis();center.observe(now,aim::read().hostPresent,live_agent::read_usb());
  if(!ui_event_center_is_active())return;
  pages=center.count()?(center.count()+3)/4:1;if(page>=pages)page=0;
  for(unsigned i=0;i<4;++i) {
    auto& row=rows[i];const auto* entry=center.at(page*4+i);lv_obj_set_hidden(row.card,!entry);if(!entry)continue;
    text(row.heading,events::text(entry->type));
    const auto* provider=aim::provider_style(entry->source);char value[100];
    snprintf(value,sizeof(value),"%s / %lus ago / %s",provider?provider->label:"SYSTEM",
      static_cast<unsigned long>((now-entry->timestampMs)/1000),entry->read?"read":"unread");text(row.detail,value);
  }
  char value[100];snprintf(value,sizeof(value),"Page %u/%u / %u events / %u unread",page+1,pages,center.count(),center.unread());text(summary,value);
  if(pages>1)lv_obj_remove_state(next,LV_STATE_DISABLED);else lv_obj_add_state(next,LV_STATE_DISABLED);
  lv_obj_set_hidden(next,pages<=1);
}

} // namespace event_center_ui
void ui_event_center_update(){event_center_ui::update();}
