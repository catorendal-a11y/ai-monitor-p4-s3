#pragma once
#include "trust_storage.h"
#include "crypto_esp.h"
#include <nvs.h>
namespace interaction {
// Dedicated NVS namespace. Never erase a partition or unrelated device settings.
// Serial-owner only; there is no global instance or boot-time write.
class NvsTrustBackend {
 public:
  bool read(uint8_t* output,size_t length) {
    nvs_handle_t handle;
    if(nvs_open("aimtrust",NVS_READONLY,&handle)!=ESP_OK)return false;
    size_t actual=0;
    bool ok=nvs_get_blob(handle,"record_v1",nullptr,&actual)==ESP_OK && actual==length;
    if(ok)ok=nvs_get_blob(handle,"record_v1",output,&actual)==ESP_OK && actual==length;
    nvs_close(handle);return ok;
  }
  bool write(const uint8_t* input,size_t length) {
    if(length!=104)return false;
    nvs_handle_t handle;
    if(nvs_open("aimtrust",NVS_READWRITE,&handle)!=ESP_OK)return false;
    const bool ok=nvs_set_blob(handle,"record_v1",input,length)==ESP_OK && nvs_commit(handle)==ESP_OK;
    nvs_close(handle);return ok;
  }
  bool erase() {
    nvs_handle_t handle;const auto opened=nvs_open("aimtrust",NVS_READWRITE,&handle);
    if(opened!=ESP_OK)return false;
    const auto erased=nvs_erase_key(handle,"record_v1");
    const bool ok=(erased==ESP_OK || erased==ESP_ERR_NVS_NOT_FOUND) && nvs_commit(handle)==ESP_OK;
    nvs_close(handle);return ok;
  }
  bool absent() {
    nvs_handle_t handle;const auto opened=nvs_open("aimtrust",NVS_READONLY,&handle);
    if(opened==ESP_ERR_NVS_NOT_FOUND)return true;
    if(opened!=ESP_OK)return false;
    size_t length=0;const auto status=nvs_get_blob(handle,"record_v1",nullptr,&length);
    nvs_close(handle);return status==ESP_ERR_NVS_NOT_FOUND;
  }
};
using NvsTrustStorage=TrustStorage<NvsTrustBackend>;
}
