#pragma once
#include "types.h"
namespace companions {
enum class Mood:uint8_t { resting,working,testing,attention,success,error,warning,critical };
inline constexpr const char* mood_names[]={"resting","working","testing","attention","success","error","warning","critical"};
inline constexpr unsigned max_animation_frames=16,max_animations=8,max_animation_steps=16;
struct AnimationStep { uint8_t frame=0;uint16_t durationMs=0; };
struct Animation {
  Mood mood=Mood::resting;bool loop=false;uint8_t count=0;
  AnimationStep steps[max_animation_steps]{};
  uint32_t duration()const {uint32_t sum=0;for(unsigned i=0;i<count;++i)sum+=steps[i].durationMs;return sum;}
};
struct AnimationAsset { char id[25]{};Frame frame; };
struct AnimationManifest {
  uint16_t version=2;Codec codec=Codec::lz4;Mood fallback=Mood::resting;
  char name[33]{};uint8_t frameCount=0,animationCount=0;
  AnimationAsset frames[max_animation_frames]{};Animation animations[max_animations]{};
  const Animation* find(Mood mood)const {
    for(unsigned i=0;i<animationCount;++i)if(animations[i].mood==mood)return &animations[i];
    return nullptr;
  }
  const Animation* resolve(Mood mood)const {const auto* value=find(mood);return value?value:find(fallback);}
};
// UI-owned, no allocation/decoder/transport. Manifest/assets must outlive playback.
class AnimationPlayer {
 public:
  bool select(const Animation* clip,uint32_t now,bool restart=false) {
    if(!clip || !clip->count || clip->count>max_animation_steps)return false;
    for(unsigned i=0;i<clip->count;++i)if(clip->steps[i].durationMs<40 ||
        clip->steps[i].durationMs>60000 || clip->steps[i].frame>=max_animation_frames)return false;
    if(clip!=clip_ || restart){clip_=clip;position_=0;last_=now;finished_=false;}
    return true;
  }
  uint8_t frame(uint32_t now) {
    if(!clip_)return 0;
    const uint32_t elapsed=now-last_;last_=now;
    const uint32_t duration=clip_->duration();
    if(clip_->loop)position_=(position_+elapsed%duration)%duration;
    else if(!finished_) {
      if(elapsed>=duration-position_){finished_=true;position_=duration-1;}
      else position_+=elapsed;
    }
    uint32_t edge=0;
    for(unsigned i=0;i<clip_->count;++i){edge+=clip_->steps[i].durationMs;if(position_<edge)return clip_->steps[i].frame;}
    return clip_->steps[clip_->count-1].frame;
  }
  bool finished()const{return finished_;}
 private:
  const Animation* clip_=nullptr;uint32_t position_=0,last_=0;bool finished_=false;
};
}
