// Standalone developer firmware only. No display, Wi-Fi connection, GATT server or Claude logic.
#if defined(AIM_C6_PROBE) && AIM_C6_PROBE
#include <Arduino.h>
#include <esp_event.h>
#include <nvs_flash.h>
#include "probe_deadline.h"
extern "C" {
#include <esp_hosted.h>
#include <esp_hosted_host_fw_ver.h>
}

// This build is exclusively for JC4880P443C_I_W/Y. Do not silently use another SDK pin profile.
#if !defined(CONFIG_ESP_SDIO_HOST_INTERFACE) || CONFIG_ESP_SDIO_GPIO_RESET_SLAVE != 54 || \
    CONFIG_ESP_SDIO_PIN_CLK != 18 || CONFIG_ESP_SDIO_PIN_CMD != 19 || \
    CONFIG_ESP_SDIO_PIN_D0 != 14 || CONFIG_ESP_SDIO_PIN_D1 != 15 || \
    CONFIG_ESP_SDIO_PIN_D2 != 16 || CONFIG_ESP_SDIO_PIN_D3 != 17 || \
    !defined(CONFIG_SLAVE_IDF_TARGET_ESP32C6)
#error "Standalone C6 test requires the verified JC4880P443C_I_W SDIO/reset profile"
#endif

namespace {
struct Result {
  const char* stage="pending";
  int error=0;
  bool finished=false,responded=false,detectedC6=false,controllerEnableConfirmed=false,deadlineExceeded=false;
  uint32_t major=0,minor=0,patch=0;
} result;
portMUX_TYPE resultMux=portMUX_INITIALIZER_UNLOCKED;
uint32_t began=0;
void finish(const char* stage,int error) {
  portENTER_CRITICAL(&resultMux);
  result.stage=stage; result.error=error; result.finished=true;
  portEXIT_CRITICAL(&resultMux);
}
bool deadline() {
  const uint32_t now=millis();
  portENTER_CRITICAL(&resultMux);
  const bool elapsed=diagnostics::probe_deadline_exceeded(began,now,result.finished);
  if (elapsed) result.deadlineExceeded=true;
  portEXIT_CRITICAL(&resultMux);
  return elapsed;
}
void probe(void*) {
  // Never erase NVS to recover from an initialization error.
  auto error=nvs_flash_init();
  if (error!=ESP_OK) { finish("nvs-init-failed",error); vTaskDelete(nullptr); return; }
  error=esp_event_loop_create_default();
  if (error!=ESP_OK && error!=ESP_ERR_INVALID_STATE) { finish("event-loop-failed",error); vTaskDelete(nullptr); return; }
  error=esp_hosted_init();
  if (error!=ESP_OK) { finish("host-init-failed",error); vTaskDelete(nullptr); return; }
  if (deadline()) { finish("deadline-exceeded",ESP_ERR_TIMEOUT); vTaskDelete(nullptr); return; }
  error=esp_hosted_connect_to_slave();
  if (error!=ESP_OK) { finish("transport-failed",error); vTaskDelete(nullptr); return; }
  if (deadline()) { finish("deadline-exceeded",ESP_ERR_TIMEOUT); vTaskDelete(nullptr); return; }
  uint32_t chipId=0; char target[32]{};
  error=esp_hosted_get_cp_info(&chipId,target,sizeof(target));
  if (error!=ESP_OK || !memchr(target,0,sizeof(target)) || strcmp(target,"esp32c6")) {
    finish("coprocessor-identity-unverified",error!=ESP_OK ? error : ESP_ERR_INVALID_RESPONSE);
    vTaskDelete(nullptr); return;
  }
  portENTER_CRITICAL(&resultMux); result.detectedC6=true; portEXIT_CRITICAL(&resultMux);
  if (deadline()) { finish("deadline-exceeded",ESP_ERR_TIMEOUT); vTaskDelete(nullptr); return; }
  esp_hosted_coprocessor_fwver_t version{};
  error=esp_hosted_get_coprocessor_fwversion(&version);
  if (error!=ESP_OK) { finish("version-query-failed",error); vTaskDelete(nullptr); return; }
  portENTER_CRITICAL(&resultMux);
  result.responded=true; result.major=version.major1; result.minor=version.minor1; result.patch=version.patch1;
  portEXIT_CRITICAL(&resultMux);
  if (deadline()) { finish("deadline-exceeded",ESP_ERR_TIMEOUT); vTaskDelete(nullptr); return; }
  error=esp_hosted_bt_controller_init();
  if (error!=ESP_OK) { finish("controller-init-failed",error); vTaskDelete(nullptr); return; }
  if (deadline()) { finish("deadline-exceeded",ESP_ERR_TIMEOUT); vTaskDelete(nullptr); return; }
  error=esp_hosted_bt_controller_enable();
  if (error!=ESP_OK) { finish("controller-enable-failed",error); vTaskDelete(nullptr); return; }
  portENTER_CRITICAL(&resultMux);
  result.controllerEnableConfirmed=true;
  portEXIT_CRITICAL(&resultMux);
  const bool late=deadline();
  finish(late ? "deadline-exceeded" : "completed",late ? ESP_ERR_TIMEOUT : ESP_OK);
  // Driver tasks/resources stay alive; no forced task deletion or unconfirmed cleanup of the SDK.
  vTaskDelete(nullptr);
}
void report() {
  Result copy;
  portENTER_CRITICAL(&resultMux); copy=result; portEXIT_CRITICAL(&resultMux);
  Serial.printf("{\"type\":\"c6_probe\",\"schema\":1,\"stage\":\"%s\",\"error\":%d,"
    "\"hostVersion\":\"%u.%u.%u\",\"coprocessorResponded\":%s,\"coprocessorVersion\":",
    copy.deadlineExceeded ? "deadline-exceeded" : copy.stage,copy.deadlineExceeded ? ESP_ERR_TIMEOUT : copy.error,
    ESP_HOSTED_VERSION_MAJOR_1,ESP_HOSTED_VERSION_MINOR_1,ESP_HOSTED_VERSION_PATCH_1,
    copy.responded ? "true" : "false");
  if (copy.responded) Serial.printf("\"%u.%u.%u\"",copy.major,copy.minor,copy.patch);
  else Serial.print("null");
  Serial.printf(",\"configuredSlaveTarget\":\"esp32c6\",\"detectedChip\":%s,"
    "\"controllerEnableConfirmed\":%s,\"deadlineExceeded\":%s,\"retryAllowed\":false}\n",
    copy.detectedC6 ? "\"esp32c6\"" : "null",copy.controllerEnableConfirmed ? "true" : "false",
    copy.deadlineExceeded ? "true" : "false");
}
}
void setup() {
  Serial.begin(115200); delay(100);
  began=millis();
  if (xTaskCreate(probe,"c6Probe",8192,nullptr,1,nullptr)!=pdPASS) finish("task-allocation-failed",ESP_ERR_NO_MEM);
}
void loop() {
  // Poll only this test result. No installation, credentials or firmware-update commands.
  static char command[24]{}; static unsigned used=0; static bool dropping=false;
  deadline();
  while (Serial.available()) {
    const char ch=static_cast<char>(Serial.read());
    if (ch=='\n') {
      if (!dropping && used==5 && !memcmp(command,"probe",5)) report();
      used=0; dropping=false;
    } else if (used<sizeof(command)) command[used++]=ch;
    else dropping=true;
  }
  delay(5);
}
#endif
