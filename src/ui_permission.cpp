#include "ui_permission.h"
#if defined(AIM_USB_PERMISSION_RUNTIME)
#include "ui/permission_view.h"
#include "interaction/permission_ui_api.h"
#include "ui/idle_dim.h"
#include "ui/backlight.h"
#include <Arduino.h>
#include <cstring>
namespace {
static interaction::PermissionController controller;
static bool shown=false,initialized=false,suppressCancellation=false;
static void cancel(){if(!suppressCancellation)interaction::permission_cancel_ui();}
static interaction::PermissionView view(controller,[]{return millis();},cancel);
static bool commit(void* owner,const interaction::PermissionEnvelope& value,
    const interaction::InteractionSnapshot& current,const interaction::PermissionContext& context,uint32_t now) {
  return static_cast<interaction::PermissionView*>(owner)->commit(value,current,context,now);
}
}
void ui_permission_init(){initialized=view.initialize();}
void ui_permission_update() {
  if(!initialized)return;
  const auto current=interaction::permission_read();const uint32_t now=millis();
  if(!current.available) {
    // A failed publication read is not a harmless "no request". Revoke before hiding.
    interaction::permission_cancel_ui();
    if(shown){view.hide();shown=false;}
    return;
  }
  const bool awake=!strcmp(idle_dim_mode(),"NORMAL") && display_get_applied_brightness()>=brightness_raw(5);
  const bool pending=current.snapshot.fresh && current.snapshot.request.present && current.context.trustedChannel;
  if(pending && !shown){view.show();shown=true;}
  if(!pending && shown) {
    suppressCancellation=true;view.hide();suppressCancellation=false;shown=false;
  }
  if(shown) {
    auto context=current.context;context.visible=true;context.awake=awake;
    view.update(current.snapshot,context);
    const bool visible=view.root() && !lv_obj_is_hidden(view.root());
    if(!visible || !awake)interaction::permission_cancel_ui();
    interaction::permission_observe_ui(visible,awake,now);
    const auto envelope=view.take(current.snapshot,context,now);
    if(envelope.decision!=interaction::Decision::none &&
       !interaction::permission_offer_ui(envelope,visible,awake,now,commit,&view))view.delivery_failed();
  }
}
bool ui_permission_is_active(){return shown;}
#else
void ui_permission_init(){}
void ui_permission_update(){}
bool ui_permission_is_active(){return false;}
#endif
