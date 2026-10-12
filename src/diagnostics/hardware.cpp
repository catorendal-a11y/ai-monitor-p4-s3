#include "hardware_types.h"
#include <Arduino.h>
#include <esp_heap_caps.h>
#include <esp_ota_ops.h>
#include <esp_psram.h>
#include <esp_flash.h>
#include <soc/soc_caps.h>
#include <cstdio>

#if !defined(AIM_BOARD_WAVESHARE_S3) && __has_include("esp_hosted_host_fw_ver.h")
#include "esp_hosted_host_fw_ver.h"
#define AIM_HAS_HOSTED_METADATA 1
#endif

namespace diagnostics {
namespace {
uint32_t imageBytes = 0;
char hostedVersion[24] = "unavailable";
}
void initialize_hardware() {
  imageBytes = ESP.getSketchSize();  // Verify/measure the image once, never each heartbeat.
#if defined(AIM_HAS_HOSTED_METADATA)
  snprintf(hostedVersion, sizeof(hostedVersion), "%u.%u.%u", ESP_HOSTED_VERSION_MAJOR_1,
           ESP_HOSTED_VERSION_MINOR_1, ESP_HOSTED_VERSION_PATCH_1);
#endif
}
HardwareBaseline hardware_baseline() {
  HardwareBaseline result{};
  result.chipRevision = ESP.getChipRevision(); result.cpuMHz = ESP.getCpuFreqMHz();
  esp_flash_get_physical_size(nullptr, &result.flashBytes);
  result.flashHz = ESP.getFlashChipSpeed();  // Configured image-header frequency, not throughput.
  result.applicationBytes = imageBytes; result.sdkVersion = ESP.getSdkVersion();
  const auto* partition = esp_ota_get_running_partition();
  if (partition) { result.partitionBytes = partition->size; result.partitionOffset = partition->address; }
  constexpr uint32_t internal = MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT;
  constexpr uint32_t external = MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT;
  multi_heap_info_t internalInfo{}, externalInfo{};
  heap_caps_get_info(&internalInfo, internal); heap_caps_get_info(&externalInfo, external);
  result.heapTotal = heap_caps_get_total_size(internal); result.heapFree = internalInfo.total_free_bytes;
  result.heapMinimum = internalInfo.minimum_free_bytes; result.heapLargest = internalInfo.largest_free_block;
  result.psramSize = esp_psram_get_size(); result.psramTotal = heap_caps_get_total_size(external);
  result.psramFree = externalInfo.total_free_bytes; result.psramMinimum = externalInfo.minimum_free_bytes;
  result.psramLargest = externalInfo.largest_free_block;
#if defined(AIM_HAS_HOSTED_METADATA)
  result.hostedCompiled = true; result.hostedVersion = hostedVersion;
#endif
#if defined(SOC_PPA_SUPPORTED) && SOC_PPA_SUPPORTED
  result.ppaSupported = true;
#endif
  result.display = draw_memory();
  const auto panel = panel_memory();
  result.display.framebufferBytes = panel.framebufferBytes;
  result.display.framebufferCount = panel.framebufferCount;
  result.display.bounceBytes = panel.bounceBytes;
  return result;
}
}  // namespace diagnostics
