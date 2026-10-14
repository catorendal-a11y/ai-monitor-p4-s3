#include "ui_enrollment.h"
#include "ui/enrollment_view.h"
#include "interaction/enrollment_runtime.h"
#include "ai_monitor/ai_monitor.h"
#include "ui/idle_dim.h"
#include "ui/backlight.h"
#include <Arduino.h>
#include <cstring>
namespace {
static interaction::EnrollmentView view([]{return millis();},interaction::enrollment_local_action);
static bool initialized=false,requested=false,shown=false;
static uint32_t requestedAt=0;
}
void ui_enrollment_init(){initialized=view.initialize();}
void ui_enrollment_show() {
  if(initialized && !requested && aim::read().hostPresent && interaction::enrollment_local_arm()){requested=true;requestedAt=millis();}
}
void ui_enrollment_update() {
  const auto current=interaction::enrollment_read();const uint32_t now=millis();
  const bool awake=!strcmp(idle_dim_mode(),"NORMAL") && display_get_applied_brightness()>=brightness_raw(5);
  if(requested && !shown && now-requestedAt>=3000){requested=false;interaction::enrollment_local_action(0,false);}
  if(requested && !shown && current.state==interaction::EnrollmentState::armed){view.show();shown=true;}
  if(shown) {
    if(current.state==interaction::EnrollmentState::closed || current.state==interaction::EnrollmentState::complete) {
      view.hide(false);shown=requested=false;
    } else {
      interaction::EnrollmentDisplay value;value.revision=current.revision;value.receivedAt=current.receivedAt;
      value.remainingMs=current.remainingMs;memcpy(value.code,current.code,20);
      value.connected=aim::read().hostPresent;value.awake=awake;
      value.comparing=current.state==interaction::EnrollmentState::comparing;
      value.confirmed=current.state==interaction::EnrollmentState::confirmed;view.update(value);
      if(!view.visible()){shown=requested=false;view.hide();}
    }
  }
  interaction::enrollment_local_visibility(current.revision,shown && view.visible(),awake,now);
}
bool ui_enrollment_is_active(){return shown;}
