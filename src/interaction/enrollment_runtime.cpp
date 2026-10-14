#include "enrollment_runtime.h"
#include "enrollment_esp.h"
#include "trust_storage_esp.h"
#include "enrollment_lease.h"
#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
namespace interaction {
namespace {
struct LocalAction{uint32_t revision;uint8_t kind;}; // 0 cancel, 1 confirm, 2 arm
struct Visibility{uint32_t revision=0,at=0;bool visible=false,awake=false;};
static QueueHandle_t actions=nullptr;
static portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
static EnrollmentPublication publication;
static Visibility visibility;
static NvsTrustBackend backend;
static NvsTrustStorage storage(backend,esp_crypto::sha256);
static uint32_t boot=0,armedAt=0,offeredAt=0;
static bool hostConnected=false;
static EnrollmentLease channelLease;
static bool channel_connected() {
#if ARDUINO_USB_CDC_ON_BOOT
  return hostConnected && static_cast<bool>(Serial);
#else
  // UART boards have no cable-status signal; the enrollment lease is required.
  return hostConnected;
#endif
}
static bool save(const DeviceTrust& value){return storage.save(value);}
static bool gate(uint32_t revision,uint32_t) {
  Visibility value;portENTER_CRITICAL(&mux);value=visibility;portEXIT_CRITICAL(&mux);
  const uint32_t now=millis();
  return channelLease.valid(now,channel_connected()) && value.revision==revision && value.visible && value.awake && now-value.at<250;
}
static EspEnrollmentDevice device(save,gate);
static void publish(uint32_t now) {
  EnrollmentPublication value;value.state=device.state();value.revision=device.revision();value.receivedAt=now;
  const uint32_t age=now-armedAt;
  if(value.state!=EnrollmentState::closed && value.state!=EnrollmentState::complete && age<60000)value.remainingMs=60000-age;
  memcpy(value.code,device.code(),20);
  portENTER_CRITICAL(&mux);publication=value;portEXIT_CRITICAL(&mux);
}
static bool enqueue(LocalAction action){return actions && xQueueSend(actions,&action,0)==pdTRUE;}
}
bool enrollment_runtime_initialize(uint32_t bootId) {
  if(actions || !bootId)return false;
  boot=bootId;actions=xQueueCreate(8,sizeof(LocalAction));return actions!=nullptr;
}
bool enrollment_local_arm(){return enqueue({0,2});}
bool enrollment_local_action(uint32_t revision,bool confirm) {
  // Invalidate immediately on the UI task, before queue delivery or screen teardown.
  // A PC commit can arrive before the serial owner gets to drain local actions.
  if(!confirm){portENTER_CRITICAL(&mux);visibility.visible=false;portEXIT_CRITICAL(&mux);}
  return enqueue({revision,static_cast<uint8_t>(confirm?1:0)});
}
void enrollment_local_visibility(uint32_t revision,bool visible,bool awake,uint32_t now) {
  const Visibility value{revision,now,visible,awake};
  portENTER_CRITICAL(&mux);visibility=value;portEXIT_CRITICAL(&mux);
}
EnrollmentPublication enrollment_read() {
  EnrollmentPublication value;portENTER_CRITICAL(&mux);value=publication;portEXIT_CRITICAL(&mux);return value;
}
void enrollment_runtime_poll(uint32_t now,bool connected) {
  hostConnected=connected;LocalAction action{};
  while(actions && xQueueReceive(actions,&action,0)==pdTRUE) {
    if(action.kind==2) {
      device.cancel();channelLease.cancel();
      if(connected && esp_crypto::initialize()) {
        DeviceTrust previous;char id[33]{};
        if(storage.load(previous))memcpy(id,previous.deviceId,33);
        else {
          uint8_t random[16]{};
          if(esp_crypto::random(random,16)){const auto encoded=encode_hex(random,16);memcpy(id,encoded.c_str(),33);}
          wipe(random,sizeof(random));
        }
        wipe(previous.key,sizeof(previous.key));
        if(device.arm(id,boot,now))armedAt=now;
      }
    } else if(action.revision==device.revision() || (!action.revision && !action.kind)) {
      if(action.kind==1)device.confirm_physical(action.revision,gate(action.revision,now),true,now);
      else device.cancel();
    }
  }
  device.poll(now);
  const auto state=device.state();
  if(!connected || ((state==EnrollmentState::comparing || state==EnrollmentState::confirmed) &&
      (!channelLease.valid(now,channel_connected()) || (now-offeredAt>=500 && !gate(device.revision(),now))))) {
    device.cancel();channelLease.cancel();
  }
  publish(now);
}
bool enrollment_runtime_command(JsonObjectConst object,uint32_t now,std::string& reply) {
  reply.clear();const char* cmd=object["cmd"]|"";bool ok=false;
  const auto state=device.state();
  if((state==EnrollmentState::comparing || state==EnrollmentState::confirmed) &&
      !channelLease.valid(now,channel_connected())){device.cancel();channelLease.cancel();}
  if(!strcmp(cmd,"interaction_enroll")) {
    if(channel_connected())ok=device.begin(object,now,reply);
    if(ok){offeredAt=now;channelLease.start(now);}
  } else if(!strcmp(cmd,"interaction_enroll_commit"))ok=device.commit(object,now,reply);
  else if(!strcmp(cmd,"interaction_enroll_status") && object.size()==2 && object["schema"].is<uint32_t>() && object["schema"].as<uint32_t>()==1) {
    channelLease.renew(now,channel_connected());
    device.poll(now);JsonDocument result;result["type"]="interaction_enrollment_status";result["schema"]=1;
    result["comparing"]=device.state()==EnrollmentState::comparing;result["confirmed"]=device.state()==EnrollmentState::confirmed;
    result["armed"]=device.state()==EnrollmentState::armed;serializeJson(result,reply);ok=true;
  } else if(!strcmp(cmd,"interaction_enroll_cancel") && object.size()==2 && object["schema"].is<uint32_t>() && object["schema"].as<uint32_t>()==1) {
    device.cancel();reply="{\"type\":\"interaction_enrollment_cancelled\",\"schema\":1}";ok=true;
  } else device.cancel();
  publish(now);return ok;
}
}
