#pragma once
#include "animation_types.h"
namespace companions::runtime {
#if defined(CONFIG_IDF_TARGET_ESP32P4)
bool initialize();
bool available();
void rendering_ready(bool ready);
void ui_tick(void (*detach)());
void use_builtin(); // UI-only request; never a permission/control input.
const AnimationManifest* current();
const uint8_t* frame(unsigned index);
uint32_t revision();
#else
inline bool initialize(){return false;}
inline bool available(){return false;}
inline void rendering_ready(bool){}
inline void ui_tick(void (*)()){}
inline void use_builtin(){}
inline const AnimationManifest* current(){return nullptr;}
inline const uint8_t* frame(unsigned){return nullptr;}
inline uint32_t revision(){return 0;}
#endif
}
