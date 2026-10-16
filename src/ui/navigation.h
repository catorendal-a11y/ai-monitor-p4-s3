#pragma once
#include <lvgl.h>
#include "theme.h"
#include "interaction.h"
#include "../dashboard.h"
#include "../ui_nova.h"
#include "../ui_agents.h"

namespace ui_navigation {
enum class Page { home, usage, agents };
inline void home(lv_event_t*) { if(!ui_nova_is_active())ui_nova_show(); }
inline void usage(lv_event_t*) { dashboard_show(); }
inline void agents(lv_event_t*) { ui_agents_show(); }
// Primary destinations never move when provider/session counts change.
inline void create(lv_obj_t* screen,Page current) {
  const char* captions[]={"HOME","USAGE","AGENTS"};
  const lv_event_cb_t callbacks[]={home,usage,agents};
  for(unsigned i=0;i<3;++i) {
    auto* button=lv_button_create(screen);
    lv_obj_set_pos(button,24+120*i,432);lv_obj_set_size(button,112,48);
    lv_obj_set_style_pad_all(button,0,0);lv_obj_set_style_radius(button,10,0);
    lv_obj_set_style_shadow_width(button,0,0);
    lv_obj_set_style_bg_color(button,lv_color_hex(ui_theme::button),0);
    lv_obj_set_style_bg_color(button,lv_color_hex(ui_theme::pressed),LV_STATE_PRESSED);
    lv_obj_set_style_border_width(button,static_cast<unsigned>(current)==i?2:0,0);
    lv_obj_set_style_border_color(button,lv_color_hex(ui_theme::accent),0);
    auto* label=lv_label_create(button);lv_label_set_text(label,captions[i]);
    lv_obj_set_style_text_font(label,&lv_font_montserrat_20,0);
    lv_obj_set_style_text_color(label,lv_color_hex(ui_theme::text),0);
    lv_obj_center(label);lv_obj_set_clickable(label,false);
    if(static_cast<unsigned>(current)!=i)lv_obj_add_event_cb(button,callbacks[i],LV_EVENT_CLICKED,nullptr);
    ui_interaction::keep_target(button);
  }
}
}
