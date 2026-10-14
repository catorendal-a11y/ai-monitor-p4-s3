#include "permission_runtime_esp.h"
#if defined(AIM_USB_PERMISSION_RUNTIME)
#include "permission_serial.h"
#include "crypto_esp.h"
#include "trust_storage_esp.h"
#include <Arduino.h>
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
namespace interaction {
namespace {
static std::atomic<SemaphoreHandle_t> mutex{nullptr};
// Latest local consent replaces older requests atomically; a full action queue must
// never let an older enable override a newer disable. Low bit is the desired value.
static std::atomic<uint32_t> consent{0};
static uint32_t appliedConsent=0;
static uint32_t boot=0;
static bool host=false;
static std::atomic<bool> revoked{false};
static PermissionSerial owner(esp_crypto::hmac_sha256,esp_crypto::random,[]{return millis();});
static NvsTrustBackend backend;
static NvsTrustStorage storage(backend,esp_crypto::sha256);
class Lock {
 public:
  Lock():value_(mutex.load(std::memory_order_acquire)) {
    if(value_ && xSemaphoreTakeRecursive(value_,pdMS_TO_TICKS(5))!=pdTRUE)value_=nullptr;
  }
  ~Lock(){if(value_)xSemaphoreGiveRecursive(value_);}
  explicit operator bool()const{return value_!=nullptr;}
 private:SemaphoreHandle_t value_;
};
static bool connected(){return !revoked.load(std::memory_order_acquire) && (consent.load(std::memory_order_acquire)&1u) && host && static_cast<bool>(Serial);}
static size_t capacity(){const int bytes=Serial.availableForWrite();return bytes>0?static_cast<size_t>(bytes):0;}
static size_t write(const uint8_t* data,size_t bytes){return connected()?Serial.write(data,bytes):0;}
}
bool permission_runtime_initialize(uint32_t bootId) {
  if(!bootId || mutex.load())return false;
  auto value=xSemaphoreCreateRecursiveMutex();
  if(!value)return false;
  boot=bootId;DeviceTrust empty;owner.configure(empty,boot);
  mutex.store(value,std::memory_order_release);return true;
}
void permission_runtime_poll(uint32_t now,bool hostPresent) {
  Lock lock;if(!lock)return;
  host=hostPresent;
  if(revoked.exchange(false,std::memory_order_acq_rel)){owner.cancel_ui();owner.poll(now,false);}
  const uint32_t desired=consent.load(std::memory_order_acquire);
  if(desired!=appliedConsent) {
    DeviceTrust trust;
    if((desired&1u) && connected() && esp_crypto::initialize() && storage.load(trust) &&
       consent.load(std::memory_order_acquire)==desired && connected())trust.optedIn=true;
    owner.configure(trust,boot);wipe(trust.key,sizeof(trust.key));
    appliedConsent=desired;
  }
  owner.poll(now,connected());
}
bool permission_runtime_command(JsonObjectConst object,uint32_t now,std::string& reply) {
  Lock lock;if(!lock){reply.clear();return false;}
  owner.poll(now,connected());return owner.handle(object,now,reply);
}
bool permission_runtime_transmit() {
  Lock lock;if(!lock)return false;
  // The mutex also fences immediate UI cancellation; no LVGL runs on this task.
  return owner.transmit(connected,capacity,write);
}
bool permission_local_opt_in(bool enabled) {
  if(!enabled)revoked.store(true,std::memory_order_release);
  if(!mutex.load(std::memory_order_acquire))return false;
  uint32_t previous=consent.load(std::memory_order_acquire);
  for(unsigned attempt=0;attempt<3;++attempt) {
    if(previous>=0xfffffffcu)break; // Never wrap a consent generation.
    const uint32_t next=((previous&~1u)+2u)|(enabled?1u:0u);
    if(consent.compare_exchange_weak(previous,next,std::memory_order_acq_rel))return true;
  }
  consent.store(0xfffffffeu,std::memory_order_release); // Permanently disabled until reboot.
  revoked.store(true,std::memory_order_release);return false;
}
PermissionPublication permission_read() {
  Lock lock;if(!lock)return {};
  auto value=PermissionPublication{true,owner.snapshot(),owner.context(true,true)};
  value.consentRequested=(consent.load(std::memory_order_acquire)&1u)!=0;
  value.context.connected &= !revoked.load(std::memory_order_acquire);return value;
}
void permission_observe_ui(bool visible,bool awake,uint32_t now) {
  Lock lock;if(lock)owner.observe_ui(visible,awake,now);
}
bool permission_offer_ui(const PermissionEnvelope& value,bool visible,bool awake,uint32_t now,
                         PermissionDelivery::Commit commit,void* view) {
  Lock lock;return lock && owner.offer_ui(value,visible,awake,now,commit,view);
}
void permission_cancel_ui(){revoked.store(true,std::memory_order_release);Lock lock;if(lock)owner.cancel_ui();}
}
#else
namespace interaction {
bool permission_runtime_initialize(uint32_t){return false;}
void permission_runtime_poll(uint32_t,bool){}
bool permission_runtime_command(JsonObjectConst,uint32_t,std::string& reply){reply.clear();return false;}
bool permission_runtime_transmit(){return false;}
bool permission_local_opt_in(bool){return false;}
PermissionPublication permission_read(){return {};}
void permission_observe_ui(bool,bool,uint32_t){}
bool permission_offer_ui(const PermissionEnvelope&,bool,bool,uint32_t,PermissionDelivery::Commit,void*){return false;}
void permission_cancel_ui(){}
}
#endif
