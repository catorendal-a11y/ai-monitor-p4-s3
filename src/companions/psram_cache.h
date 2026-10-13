#pragma once
#include "frame_cache.h"
#include <esp_heap_caps.h>
#include <mbedtls/sha256.h>
#include <src/libs/lz4/lz4.h>

namespace companions {
// Boot-time ownership. The object must outlive every binding; no lazy render allocation.
class PsramCache {
 public:
  PsramCache()=default;
  PsramCache(const PsramCache&)=delete;
  PsramCache& operator=(const PsramCache&)=delete;
  ~PsramCache() {
    // Retain storage rather than freeing memory that a live LVGL source can read.
    for (unsigned i=0;i<2;++i)if (cache_.slot(i) && cache_.slot(i)->pinned)return;
    heap_caps_free(pool_);
  }
  bool initialize(size_t largestFrameBytes) {
    if (pool_ || !largestFrameBytes || largestFrameBytes>max_frame_bytes)return false;
    slotBytes_=(largestFrameBytes+63u)&~size_t(63u);
    pool_=static_cast<uint8_t*>(heap_caps_aligned_alloc(64,2u*slotBytes_,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    if (!pool_)return false;
    uint8_t digest[32],probe=0;
    if (mbedtls_sha256(&probe,1,digest,0)!=0) { heap_caps_free(pool_);pool_=nullptr;return false; }
    if (!cache_.initialize(pool_,2u*slotBytes_,slotBytes_)) {
      heap_caps_free(pool_);pool_=nullptr;return false;
    }
    return true;
  }
  FrameCache& frames() { return cache_; }
  size_t allocated_bytes() const { return pool_?2u*slotBytes_:0; }
  static bool hash(const uint8_t* data,size_t bytes,const char* expected) {
    if (!data || !expected || !bytes || bytes>max_frame_bytes+64u || strnlen(expected,65)!=64)return false;
    uint8_t digest[32];char hex[65];
    if (mbedtls_sha256(data,bytes,digest,0)!=0)return false;
    static constexpr char digits[]="0123456789abcdef";
    for (size_t i=0;i<32;++i) { hex[2*i]=digits[digest[i]>>4];hex[2*i+1]=digits[digest[i]&15]; }
    hex[64]=0;return !memcmp(hex,expected,65);
  }
  static bool decode(Codec codec,const uint8_t* encoded,size_t length,uint8_t* output,size_t bytes) {
    if (!encoded || !output || !length || !bytes || length>max_frame_bytes+64u || bytes>max_frame_bytes)return false;
    if (codec==Codec::raw) { if (length!=bytes)return false;memcpy(output,encoded,bytes);return true; }
    if (codec!=Codec::lz4)return false;
    return LZ4_decompress_safe(reinterpret_cast<const char*>(encoded),reinterpret_cast<char*>(output),length,bytes)==static_cast<int>(bytes);
  }
 private:
  uint8_t* pool_=nullptr;
  size_t slotBytes_=0;
  FrameCache cache_;
};
}
