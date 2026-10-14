#pragma once
#include "types.h"
#include <cstring>
#include <limits>

namespace companions {
// Caller supplies a preallocated pool and stable descriptors. No allocation in load/swap/render.
// The UI owns pin/retire; it retires the old slot only after replacing/dropping LVGL's old source.
class FrameCache {
 public:
  using Hash = bool (*)(const uint8_t*,size_t,const char*);
  using Decode = bool (*)(Codec,const uint8_t*,size_t,uint8_t*,size_t);
  struct Slot { uint8_t* pixels=nullptr; Frame frame; bool valid=false, pinned=false; };
  bool initialize(uint8_t* pool,size_t bytes,size_t slotBytes) {
    if (initialized_ || !pool || slotBytes<3 || slotBytes>max_frame_bytes+64u || bytes<2u*slotBytes) return false;
    capacity_=slotBytes; slots_[0].pixels=pool; slots_[1].pixels=pool+slotBytes;
    initialized_=true; return true;
  }
  const Slot* slot(unsigned index) const { return index<2 && slots_[index].valid ? &slots_[index] : nullptr; }
  int load(const Frame& frame,Codec codec,const uint8_t* encoded,size_t length,Hash hash,Decode decode) {
    if (!initialized_ || !encoded || !hash || !decode || length!=frame.encodedBytes || !frame.width || !frame.height ||
        frame.originX+frame.width>canvas_width || frame.originY+frame.height>canvas_height ||
        static_cast<unsigned>(frame.pose)>=8 || (codec!=Codec::raw && codec!=Codec::lz4) || !frame.encodedBytes || frame.encodedBytes>max_frame_bytes+64u || !frame.decodedBytes ||
        (codec==Codec::raw && frame.encodedBytes!=frame.decodedBytes) || frame.decodedBytes>capacity_ ||
        frame.decodedBytes!=static_cast<size_t>(frame.width)*frame.height*3u) return -1;
    int selected=-1;
    for (unsigned i=0;i<2;++i) if (!slots_[i].pinned) { selected=i; break; }
    if (selected<0 || !hash(encoded,length,frame.encodedSha256)) return -1;
    auto& target=slots_[selected]; target.valid=false;
    const auto source=reinterpret_cast<uintptr_t>(encoded),destination=reinterpret_cast<uintptr_t>(target.pixels);
    if (source>std::numeric_limits<uintptr_t>::max()-length ||
        destination>std::numeric_limits<uintptr_t>::max()-frame.decodedBytes ||
        (source<destination+frame.decodedBytes && destination<source+length))return -1;
    if (!decode(codec,encoded,length,target.pixels,frame.decodedBytes) ||
        !hash(target.pixels,frame.decodedBytes,frame.decodedSha256)) return -1;
    target.frame=frame; target.valid=true; return selected;
  }
  bool pin(unsigned index) {
    if (index>=2 || !slots_[index].valid) return false;
    slots_[index].pinned=true; return true;
  }
  void retire(unsigned index) { if (index<2) slots_[index].pinned=false; }
  void clear_unpinned() { for (auto& slot:slots_) if (!slot.pinned) slot.valid=false; }
 private:
  bool initialized_=false;
  size_t capacity_=0;
  Slot slots_[2];
};
}  // namespace companions
