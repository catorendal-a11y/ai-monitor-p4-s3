#include "runtime_esp.h"
#if defined(CONFIG_IDF_TARGET_ESP32P4)
#include "pack_protocol.h"
#include "psram_cache.h"
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
namespace companions::runtime {
namespace {
PackStore store;
SemaphoreHandle_t mutex=nullptr;
std::atomic<bool> enabled{false},builtinRequested{false};
uint32_t bootId=0;
// All buffers are allocated at startup, before any frame can refer to them.
uint8_t *first=nullptr,*second=nullptr,*scratch=nullptr;
bool hash(const uint8_t* data,size_t bytes,const char* expected) {
  if(!data || !bytes || bytes>max_pack_bytes || !expected || strnlen(expected,65)!=64)return false;
  uint8_t digest[32];char hex[65];
  if(mbedtls_sha256(data,bytes,digest,0)!=0)return false;
  constexpr char digits[]="0123456789abcdef";
  for(unsigned i=0;i<32;++i){hex[i*2]=digits[digest[i]>>4];hex[i*2+1]=digits[digest[i]&15];}
  hex[64]=0;return !memcmp(hex,expected,65);
}
}
bool initialize() {
  if(enabled.load())return true;
  if(mutex)return false;
  mutex=xSemaphoreCreateMutex();if(!mutex)return false;
  first=static_cast<uint8_t*>(heap_caps_malloc(max_pack_bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  second=static_cast<uint8_t*>(heap_caps_malloc(max_pack_bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  scratch=static_cast<uint8_t*>(heap_caps_malloc(max_frame_bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  if(!store.initialize(first,second,max_pack_bytes,scratch,max_frame_bytes,hash,PsramCache::decode)) {
    heap_caps_free(first);heap_caps_free(second);heap_caps_free(scratch);first=second=scratch=nullptr;
    return false;
  }
  enabled.store(true,std::memory_order_release);return true;
}
bool available(){return enabled.load(std::memory_order_acquire);}
void rendering_ready(bool ready){if(!ready)enabled.store(false,std::memory_order_release);}
void set_boot(uint32_t boot){bootId=boot;}
bool command(JsonObjectConst object,uint32_t now,std::string& response) {
  if(!available() || !mutex || xSemaphoreTake(mutex,pdMS_TO_TICKS(50))!=pdTRUE)return false;
  const bool result=pack_command(store,bootId,object,now,response);
  xSemaphoreGive(mutex);return result;
}
void poll(uint32_t now,bool connected) {
  if(!available() || xSemaphoreTake(mutex,0)!=pdTRUE)return;
  if(!connected)store.cancel();else store.expire(now);
  xSemaphoreGive(mutex);
}
void ui_tick(void (*detach)()) {
  if(!available() || !detach || xSemaphoreTake(mutex,0)!=pdTRUE)return;
  if(builtinRequested.exchange(false)) {detach();store.disable();}
  else if(store.pending()){detach();store.activate();}
  xSemaphoreGive(mutex);
}
void use_builtin(){builtinRequested.store(true);}
const AnimationManifest* current(){return available()?store.active():nullptr;}
const uint8_t* frame(unsigned index){return available()?store.frame(index):nullptr;}
uint32_t revision(){return available()?store.revision():0;}
}
#endif
