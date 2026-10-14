#pragma once
// A read-only, bounded image of real LVGL RGB565 flushes. Caller owns storage and locking.
#include <cstdint>
#include <cstring>
#include <string>

namespace mirror {
constexpr unsigned width=800, height=480, pixels=width*height, perChunk=640, chunks=pixels/perChunk;
constexpr unsigned imageBytes=pixels*2, coverageBytes=pixels/8;
enum class State {closed,pending,capturing,ready,unavailable,expired};
inline const char* state_name(State value) {
  switch(value) {case State::pending: case State::capturing:return "capturing";
    case State::ready:return "ready";case State::unavailable:return "unavailable";
    case State::expired:return "expired";default:return "closed";}
}
inline bool valid_id(const char* value,size_t length) {
  if(!value || length!=32 || std::strlen(value)!=32)return false;
  for(size_t i=0;i<length;++i)if(!((value[i]>='0'&&value[i]<='9')||(value[i]>='a'&&value[i]<='f')))return false;
  return true;
}
class Capture {
 public:
  State state=State::closed;
  uint32_t frame=0;
  char request[33]{};
  bool begin(const char* id,uint32_t now,uint16_t* image,uint8_t* coverage) {
    if(!valid_id(id,32) || !image || !coverage || state==State::pending || state==State::capturing || state==State::ready)return false;
    storage_=image; coverage_=coverage; std::memset(coverage_,0,coverageBytes);
    std::memcpy(request,id,33); if(++frame==0)++frame;
    started_=last_=now; count_=0; state=State::pending;return true;
  }
  bool matches(const char* id,uint32_t number)const{return id && std::strcmp(request,id)==0 && number==frame;}
  bool start(uint32_t now,bool blocked) {
    poll(now,blocked);if(state!=State::pending)return false;state=State::capturing;return true;
  }
  void poll(uint32_t now,bool blocked) {
    if(state!=State::pending && state!=State::capturing && state!=State::ready)return;
    if(blocked)clear(State::unavailable);
    else if(now-started_>=120000u || now-last_>=30000u)clear(State::expired);
  }
  void touch(uint32_t now){last_=now;}
  void clear(State next=State::closed) {
    if(storage_)std::memset(storage_,0,imageBytes);
    if(coverage_)std::memset(coverage_,0,coverageBytes);
    count_=0;state=next;
  }
  void detach() {
    // Storage may be released only after the immutable frame is no longer available.
    if(state==State::pending || state==State::capturing || state==State::ready)return;
    storage_=nullptr;coverage_=nullptr;
  }
  bool flush(int x1,int y1,int x2,int y2,const uint16_t* source,size_t available,bool last,bool blocked,uint32_t now) {
    poll(now,blocked);if(state!=State::capturing)return false;
    if(!source || x1<0 || y1<0 || x2<x1 || y2<y1 || x2>=int(width) || y2>=int(height) ||
      available<size_t(x2-x1+1)*size_t(y2-y1+1)){clear(State::unavailable);return false;}
    size_t pos=0;
    for(int y=y1;y<=y2;++y)for(int x=x1;x<=x2;++x) {
      const unsigned at=unsigned(y)*width+unsigned(x);storage_[at]=source[pos++];
      const uint8_t mask=uint8_t(1u<<(at&7));if(!(coverage_[at>>3]&mask)){coverage_[at>>3]|=mask;++count_;}
    }
    if(last) {if(count_==pixels)state=State::ready;else clear(State::unavailable);}
    return true;
  }
  std::string chunk(unsigned index) const {
    if(state!=State::ready || index>=chunks)return {};
    uint8_t encoded[perChunk*4];unsigned used=0,start=index*perChunk;
    for(unsigned at=0;at<perChunk;) {
      unsigned run=1;const uint16_t color=storage_[start+at];
      while(at+run<perChunk && storage_[start+at+run]==color)++run;
      encoded[used++]=uint8_t(run);encoded[used++]=uint8_t(run>>8);
      encoded[used++]=uint8_t(color);encoded[used++]=uint8_t(color>>8);at+=run;
    }
    static constexpr char alphabet[]="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string output;output.reserve((used+2)/3*4);
    for(unsigned i=0;i<used;i+=3) {
      uint32_t value=uint32_t(encoded[i])<<16;
      if(i+1<used)value|=uint32_t(encoded[i+1])<<8;
      if(i+2<used)value|=encoded[i+2];
      output+=alphabet[(value>>18)&63];output+=alphabet[(value>>12)&63];
      output+=i+1<used?alphabet[(value>>6)&63]:'=';output+=i+2<used?alphabet[value&63]:'=';
    }
    return output;
  }
 private:
  uint16_t* storage_=nullptr;uint8_t* coverage_=nullptr;
  uint32_t started_=0,last_=0;unsigned count_=0;
};
} // namespace mirror
