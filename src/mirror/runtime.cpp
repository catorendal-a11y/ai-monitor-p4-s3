#include "runtime.h"
#include "protocol.h"
#include <Arduino.h>
#include <atomic>
#include <esp_heap_caps.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "../ui/lvgl_hal.h"
#include "../ui_enrollment.h"
#include "../ui_permission.h"

namespace mirror {
namespace {
Capture capture;
std::atomic<SemaphoreHandle_t> mutex{nullptr};
uint16_t* image=nullptr;uint8_t* coverage=nullptr;
std::atomic<bool> protectedScreen{true}; // Fail closed until the actual UI reports visibility.
bool blocked(){return ui_enrollment_is_active() || ui_permission_is_active();}
bool lock(){auto value=mutex.load(std::memory_order_acquire);return value && xSemaphoreTake(value,pdMS_TO_TICKS(5))==pdTRUE;}
void unlock(){xSemaphoreGive(mutex.load(std::memory_order_acquire));}
bool allocate() {
  if(image && coverage)return true;
  image=static_cast<uint16_t*>(heap_caps_malloc(imageBytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  coverage=static_cast<uint8_t*>(heap_caps_malloc(coverageBytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  if(image && coverage)return true;
  if(image)heap_caps_free(image);
  if(coverage)heap_caps_free(coverage);
  image=nullptr;coverage=nullptr;return false;
}
void release_inactive() {
  if(capture.state==State::pending || capture.state==State::capturing || capture.state==State::ready)return;
  capture.detach();
  if(image)heap_caps_free(image);
  if(coverage)heap_caps_free(coverage);
  image=nullptr;coverage=nullptr;
}
}
bool initialize(){if(!mutex.load(std::memory_order_acquire))mutex.store(xSemaphoreCreateMutex(),std::memory_order_release);return mutex.load(std::memory_order_acquire)!=nullptr;}
bool command(JsonObjectConst object,uint32_t now,std::string& response) {
  if(!lock())return false;
  const bool accepted=handle(capture,object,now,protectedScreen.load(std::memory_order_acquire),image,coverage,allocate,response);
  release_inactive();unlock();return accepted;
}

void poll(uint32_t now,bool connected) {
  if(!lock())return;
  capture.poll(now,!connected || protectedScreen.load(std::memory_order_acquire));release_inactive();unlock();
}
void ui_tick() {
  const bool denied=blocked();protectedScreen.store(denied,std::memory_order_release);
  if(!lock())return;
  const bool repaint=capture.start(millis(),denied);release_inactive();unlock();
  if(repaint) {
    // Invalidate all layers so the capture includes the actual overlay composition.
    lv_obj_invalidate(lv_screen_active());lv_obj_invalidate(lv_layer_top());lv_obj_invalidate(lv_layer_sys());
  }
}
void flushed(int x1,int y1,int x2,int y2,const uint16_t* source,bool last) {
  const bool denied=blocked();protectedScreen.store(denied,std::memory_order_release);
  if(!lock())return;
  capture.flush(x1,y1,x2,y2,source,size_t(x2-x1+1)*size_t(y2-y1+1),last,denied,millis());release_inactive();unlock();
}
} // namespace mirror
