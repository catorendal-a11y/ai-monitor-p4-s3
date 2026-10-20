#pragma once

// Built-in companions. NOVA, ORBIT and CLAUDE are always compiled in. WRAITH and GLITCH (indices 3
// and 4 of app_settings::Companion) are compiled in only where flash allows it: the P4 build, and the
// native UI tests that stand in for it. The Waveshare S3 image is nearly full, so it keeps the first
// three and treats a stored choice of 3 or 4 as NOVA.
// The target macro comes from sdkconfig.h. Pull it in here: a file that includes this header before
// Arduino.h would otherwise count three companions and silently turn a saved WRAITH/GLITCH into NOVA.
#if __has_include("sdkconfig.h")
#include "sdkconfig.h"
#endif
#if defined(CONFIG_IDF_TARGET_ESP32P4) || (defined(AIM_COMPANION_CACHE_TEST) && !defined(AIM_BOARD_WAVESHARE_S3))
#define AIM_EXTRA_COMPANIONS 1
#define AIM_BUILTIN_COMPANIONS 5
#else
#define AIM_BUILTIN_COMPANIONS 3
#endif
