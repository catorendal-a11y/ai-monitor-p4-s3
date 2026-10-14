// Standalone developer benchmark. No UI, filesystem, provider or transport integration.
#if defined(AIM_ASSET_BENCHMARK) && AIM_ASSET_BENCHMARK
#include <Arduino.h>
#include <algorithm>
#include <cstring>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <mbedtls/sha256.h>
#include <miniz.h>
#include <lvgl.h>
#include <src/libs/lz4/lz4.h>
#include <src/libs/rle/lv_rle_private.h>
#include "../companions/rle_bounds.h"
#include "../companions/psram_cache.h"

enum class AssetCodec : uint8_t { raw,rle,lz4,deflate };
struct AssetFixture {
  const char *robot,*pose;
  AssetCodec codec;
  const uint8_t* input;
  size_t encodedBytes,decodedBytes;
  const char *sha256,*encodedSha256;
  uint16_t width,height,originX,originY;
};
#if !__has_include("asset_fixtures.h")
#error "Generate trusted asset fixtures with scripts/export_asset_benchmark.py first"
#endif
#include "asset_fixtures.h"
static_assert(sizeof(fixtures)/sizeof(fixtures[0])==24,"Expected six poses and four codecs");
namespace {
uint8_t* output=nullptr;
tinfl_decompressor* inflater=nullptr;
size_t capacity=0;
bool ran=false;
companions::PsramCache cache;
bool cacheReady=false;
bool decode(const AssetFixture& frame) {
  if (!frame.input || !frame.encodedBytes || !frame.decodedBytes || frame.decodedBytes>capacity) return false;
  switch (frame.codec) {
    case AssetCodec::raw:
      if (frame.encodedBytes!=frame.decodedBytes) return false;
      memcpy(output,frame.input,frame.decodedBytes);return true;
    case AssetCodec::rle:
      if (!companions::exact_rle(frame.input,frame.encodedBytes,frame.decodedBytes))return false;
      return lv_rle_decompress(frame.input,frame.encodedBytes,output,frame.decodedBytes,1)==frame.decodedBytes;
    case AssetCodec::lz4:
      return LZ4_decompress_safe(reinterpret_cast<const char*>(frame.input),reinterpret_cast<char*>(output),
          frame.encodedBytes,frame.decodedBytes)==static_cast<int>(frame.decodedBytes);
    case AssetCodec::deflate: {
      tinfl_init(inflater);
      size_t in=frame.encodedBytes,out=frame.decodedBytes;
      const auto status=tinfl_decompress(inflater,frame.input,&in,output,output,&out,
          TINFL_FLAG_PARSE_ZLIB_HEADER|TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF|TINFL_FLAG_COMPUTE_ADLER32);
      return status==TINFL_STATUS_DONE && in==frame.encodedBytes && out==frame.decodedBytes;
    }
  }
  return false;
}
bool equal_hash(const AssetFixture& frame) {
  uint8_t digest[32];char hex[65];
  if (mbedtls_sha256(output,frame.decodedBytes,digest,0)!=0)return false;
  for (size_t i=0;i<32;++i)snprintf(hex+2*i,3,"%02x",digest[i]);
  return !strcmp(hex,frame.sha256);
}
void benchmark() {
  // Once per boot. Hashing is outside the decode timer, but checked for every sample.
  if (ran)return;ran=true;
  if (!output || !inflater) { Serial.println("{\"type\":\"asset_benchmark_error\",\"reason\":\"allocation-failed\"}");return; }
  const char* names[]={"raw","rle","lz4","deflate"};
  unsigned cached=0;uint64_t loadUs=0;int active=-1;
  bool hashRejected=true,decodeRejected=true,pinPreserved=true;
  for (const auto& frame:fixtures) {
    uint32_t times[5]{};unsigned samples=0;bool exact=true;
    for (unsigned i=0;i<5;++i) {
      const int64_t start=esp_timer_get_time();
      const bool decoded=decode(frame);
      times[i]=static_cast<uint32_t>(esp_timer_get_time()-start);
      if (!decoded || !equal_hash(frame)) { exact=false;break; }
      ++samples;
    }
    std::sort(times,times+5);
    Serial.printf("{\"type\":\"asset_benchmark\",\"schema\":1,\"robot\":\"%s\",\"pose\":\"%s\","
      "\"codec\":\"%s\",\"encodedBytes\":%u,\"decodedBytes\":%u,\"samples\":%u,\"medianDecodeUs\":%u,"
      "\"bitExact\":%s,\"outputBufferBytes\":%u,\"decoderStateBytes\":%u,\"cpuMHz\":%u,\"decodedSha256\":\"%s\"}\n",
      frame.robot,frame.pose,names[static_cast<unsigned>(frame.codec)],static_cast<unsigned>(frame.encodedBytes),
      static_cast<unsigned>(frame.decodedBytes),samples,exact?times[2]:0,exact?"true":"false",
      static_cast<unsigned>(capacity),frame.codec==AssetCodec::deflate?static_cast<unsigned>(sizeof(tinfl_decompressor)):0,
      ESP.getCpuFreqMHz(),frame.sha256);
    delay(1);
    if (frame.codec==AssetCodec::lz4 && cacheReady) {
      companions::Frame record;
      record.width=frame.width;record.height=frame.height;record.originX=frame.originX;record.originY=frame.originY;
      record.encodedBytes=frame.encodedBytes;record.decodedBytes=frame.decodedBytes;
      memcpy(record.encodedSha256,frame.encodedSha256,65);memcpy(record.decodedSha256,frame.sha256,65);
      const auto started=esp_timer_get_time();
      const int loaded=cache.frames().load(record,companions::Codec::lz4,frame.input,frame.encodedBytes,
          companions::PsramCache::hash,companions::PsramCache::decode);
      loadUs+=esp_timer_get_time()-started;
      if (loaded>=0 && cache.frames().pin(loaded)) {
        if (active>=0)cache.frames().retire(active);
        active=loaded;++cached;
        auto invalid=record;invalid.encodedSha256[0]=invalid.encodedSha256[0]=='a'?'b':'a';
        hashRejected &= cache.frames().load(invalid,companions::Codec::lz4,frame.input,frame.encodedBytes,
            companions::PsramCache::hash,companions::PsramCache::decode)==-1;
        invalid=record;--invalid.encodedBytes;
        uint8_t digest[32];
        if (mbedtls_sha256(frame.input,invalid.encodedBytes,digest,0)!=0)decodeRejected=false;
        else {
          for (size_t i=0;i<32;++i)snprintf(invalid.encodedSha256+2*i,3,"%02x",digest[i]);
          decodeRejected &= cache.frames().load(invalid,companions::Codec::lz4,frame.input,invalid.encodedBytes,
              companions::PsramCache::hash,companions::PsramCache::decode)==-1;
        }
        const auto* held=cache.frames().slot(active);
        pinPreserved &= held && held->pinned && companions::PsramCache::hash(held->pixels,held->frame.decodedBytes,held->frame.decodedSha256);
      }
    }
  }
  if (active>=0)cache.frames().retire(active);
  Serial.printf("{\"type\":\"asset_cache\",\"schema\":1,\"loads\":%u,\"allocatedBytes\":%u,\"totalLoadUs\":%llu,"
    "\"hashRejected\":%s,\"decodeRejected\":%s,\"pinPreserved\":%s}\n",cached,
    static_cast<unsigned>(cache.allocated_bytes()),static_cast<unsigned long long>(loadUs),
    hashRejected?"true":"false",decodeRejected?"true":"false",pinPreserved?"true":"false");
  Serial.println("{\"type\":\"asset_benchmark_end\",\"schema\":1,\"count\":24}");
}
}
void setup() {
  Serial.setRxBufferSize(1024);Serial.begin(115200);delay(100);
  for (const auto& frame:fixtures)if (frame.decodedBytes>capacity)capacity=frame.decodedBytes;
  if (capacity>366360)return;
  output=static_cast<uint8_t*>(heap_caps_aligned_alloc(64,capacity,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
  inflater=static_cast<tinfl_decompressor*>(heap_caps_malloc(sizeof(tinfl_decompressor),MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
  cacheReady=cache.initialize(capacity);
}
void loop() {
  static char command[16];static unsigned used=0;static bool dropping=false;
  while(Serial.available()) {
    const char ch=static_cast<char>(Serial.read());
    if (ch=='\n') {
      if (!dropping && used==6 && !memcmp(command,"assets",6))benchmark();
      used=0;dropping=false;
    } else if (used<sizeof(command))command[used++]=ch;
    else dropping=true;
  }
  delay(5);
}
#endif
