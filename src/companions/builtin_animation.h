#pragma once
#include "animation_types.h"
namespace companions {
// Frame indexes match the verified built-in cache: work/done/low/critical/sleep/blink.
// Sequences use existing verified artwork; they never imply unreported agent phases.
inline const Animation builtin_animations[]={
  {Mood::resting,true,1,{{4,60000}}},
  {Mood::working,true,3,{{0,3950},{5,180},{0,470}}},
  {Mood::testing,true,3,{{0,1600},{5,180},{0,820}}},
  {Mood::attention,true,3,{{2,3000},{5,180},{2,420}}},
  {Mood::success,false,3,{{1,1000},{5,180},{1,1200}}},
  {Mood::error,true,3,{{2,4000},{5,180},{2,420}}},
  {Mood::warning,true,1,{{2,60000}}},
  {Mood::critical,true,1,{{3,60000}}}
};
inline const Animation* builtin_animation(Mood mood) {
  const unsigned index=static_cast<unsigned>(mood);
  return &builtin_animations[index<max_animations?index:0];
}
}
