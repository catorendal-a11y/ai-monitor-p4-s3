#pragma once
#include "animation.h"
#include "frame_cache.h"
#include <limits>

namespace companions {
inline constexpr size_t max_pack_bytes=2u*1024u*1024u;
// Caller owns both banks and one validation scratch buffer for the entire runtime.
// Serial staging never writes the active bank; only the UI owner may activate/disable.
class PackStore {
 public:
  bool initialize(uint8_t* first,uint8_t* second,size_t capacity,uint8_t* scratch,size_t scratchBytes,
                  FrameCache::Hash hash,FrameCache::Decode decode) {
    if(initialized_ || !first || !second || !scratch || !hash || !decode || capacity<128 ||
       capacity>max_pack_bytes || !scratchBytes || scratchBytes>max_frame_bytes)return false;
    auto separate=[](uint8_t* a,size_t n,uint8_t* b,size_t m){
      const auto x=reinterpret_cast<uintptr_t>(a),y=reinterpret_cast<uintptr_t>(b);
      return x<=std::numeric_limits<uintptr_t>::max()-n && y<=std::numeric_limits<uintptr_t>::max()-m &&
             (x+n<=y || y+m<=x);
    };
    if(!separate(first,capacity,second,capacity) || !separate(first,capacity,scratch,scratchBytes) ||
       !separate(second,capacity,scratch,scratchBytes))return false;
    banks_[0].bytes=first;banks_[1].bytes=second;capacity_=capacity;scratch_=scratch;
    scratchBytes_=scratchBytes;hash_=hash;decode_=decode;initialized_=true;return true;
  }
  bool begin(const char* nonce,size_t total,const char* digest,uint32_t now) {
    if(!initialized_ || ready_ || builtin_ || !hex(nonce,32) || !hex(digest,64) || total<5 || total>capacity_)return false;
    staging_=active_==0?1:0;total_=total;offset_=0;received_=now;receiving_=true;
    memcpy(nonce_,nonce,33);memcpy(banks_[staging_].digest,digest,65);return true;
  }
  bool chunk(const char* nonce,size_t offset,const uint8_t* bytes,size_t length,uint32_t now) {
    expire(now);
    if(!receiving_ || !hex(nonce,32) || strcmp(nonce,nonce_) || !bytes || !length || length>512 ||
        offset!=offset_ || length>total_-offset_)return false;
    memcpy(banks_[staging_].bytes+offset_,bytes,length);offset_+=length;received_=now;return true;
  }
  bool finish(const char* nonce,uint32_t now) {
    expire(now);
    if(!receiving_ || !hex(nonce,32) || strcmp(nonce,nonce_))return false;
    receiving_=false;
    if(offset_!=total_)return false;
    auto& bank=banks_[staging_];
    if(!hash_(bank.bytes,total_,bank.digest))return false;
    const uint32_t length=uint32_t(bank.bytes[0])|(uint32_t(bank.bytes[1])<<8)|
        (uint32_t(bank.bytes[2])<<16)|(uint32_t(bank.bytes[3])<<24);
    if(!length || length>max_manifest_bytes || length>total_-4 ||
       !parse_animation_manifest(bank.bytes+4,length,bank.manifest))return false;
    size_t offset=4+length;
    for(unsigned i=0;i<bank.manifest.frameCount;++i) {
      const auto& frame=bank.manifest.frames[i].frame;
      if(frame.encodedBytes>total_-offset || frame.decodedBytes>scratchBytes_ ||
         frame.encodedBytes>max_frame_bytes+64u)return false;
      bank.offsets[i]=offset;
      if(!hash_(bank.bytes+offset,frame.encodedBytes,frame.encodedSha256) ||
         !decode_(bank.manifest.codec,bank.bytes+offset,frame.encodedBytes,scratch_,frame.decodedBytes) ||
         !hash_(scratch_,frame.decodedBytes,frame.decodedSha256))return false;
      offset+=frame.encodedBytes;
    }
    if(offset!=total_)return false;
    ready_=true;received_=now;return true;
  }
  bool activate() {
    if(builtin_){disable();return true;}
    if(!ready_)return false;
    active_=staging_;ready_=false;++revision_;return true;
  }
  void disable() {active_=-1;receiving_=ready_=builtin_=false;offset_=total_=0;nonce_[0]=0;++revision_;}
  void request_builtin(){receiving_=ready_=false;builtin_=true;}
  void cancel(){receiving_=ready_=false;nonce_[0]=0;}
  void expire(uint32_t now){if((receiving_ || ready_) && uint32_t(now-received_)>30000u)cancel();}
  const AnimationManifest* active()const{return active_>=0?&banks_[active_].manifest:nullptr;}
  const uint8_t* frame(unsigned index)const {
    return active_>=0 && index<banks_[active_].manifest.frameCount?banks_[active_].bytes+banks_[active_].offsets[index]:nullptr;
  }
  const char* active_id()const{return active_>=0?banks_[active_].digest:"";}
  const char* phase()const{return builtin_?"clearing":ready_?"ready":receiving_?"receiving":active_>=0?"active":"builtin";}
  bool pending()const{return ready_ || builtin_;}
  size_t offset()const{return offset_;}
  uint32_t revision()const{return revision_;}
 private:
  static bool hex(const char* value,size_t length){
    if(!value || strnlen(value,length+1)!=length)return false;
    for(size_t i=0;i<length;++i)if(!((value[i]>='0' && value[i]<='9')||(value[i]>='a' && value[i]<='f')))return false;
    return true;
  }
  struct Bank {uint8_t* bytes=nullptr;AnimationManifest manifest;size_t offsets[16]{};char digest[65]{};} banks_[2];
  uint8_t* scratch_=nullptr;size_t capacity_=0,scratchBytes_=0,total_=0,offset_=0;
  FrameCache::Hash hash_=nullptr;FrameCache::Decode decode_=nullptr;
  int active_=-1,staging_=0;bool initialized_=false,receiving_=false,ready_=false,builtin_=false;
  uint32_t received_=0,revision_=0;char nonce_[33]{};
};
}
