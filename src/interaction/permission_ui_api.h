#pragma once
#include "permission_delivery.h"
namespace interaction {
struct PermissionPublication {
  bool available=false;
  InteractionSnapshot snapshot;
  PermissionContext context;
  bool consentRequested=false;
};
// UI-owner API. No parser, crypto key, file or serial handle crosses this boundary.
bool permission_local_opt_in(bool enabled);
PermissionPublication permission_read();
void permission_observe_ui(bool visible,bool awake,uint32_t now);
bool permission_offer_ui(const PermissionEnvelope&,bool visible,bool awake,uint32_t now,
                         PermissionDelivery::Commit,void* owner);
void permission_cancel_ui();
}
