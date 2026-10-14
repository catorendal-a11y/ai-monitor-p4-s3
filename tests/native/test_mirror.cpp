#include <cstdlib>
#include <vector>
#include <algorithm>
#include <iostream>
#include "lvgl.h"
#include "../../src/mirror/protocol.h"

#define CHECK(value) do { if(!(value)) { std::cerr << "CHECK failed: " #value " at " << __FILE__ << ":" << __LINE__ << "\n"; std::abort(); } } while(false)

static mirror::Capture capture;
static std::vector<uint16_t> image(mirror::pixels), source(mirror::pixels);
alignas(64) static uint16_t draw[mirror::width*20];
static std::vector<uint8_t> coverage(mirror::coverageBytes);
static uint16_t* imagePtr=image.data();static uint8_t* coveragePtr=coverage.data();
static constexpr char id[]="0123456789abcdef0123456789abcdef";
static uint32_t now=10;
static bool blocked=false;
static void flush(lv_display_t* display,const lv_area_t* area,uint8_t* data) {
  CHECK(capture.flush(area->x1,area->y1,area->x2,area->y2,reinterpret_cast<const uint16_t*>(data),
    size_t(area->x2-area->x1+1)*size_t(area->y2-area->y1+1),lv_display_flush_is_last(display),blocked,now));
  lv_display_flush_ready(display);
}
static bool command(const std::string& input,std::string& output) {
  JsonDocument object;CHECK(deserializeJson(object,input)==DeserializationError::Ok);
  return mirror::handle(capture,object.as<JsonObjectConst>(),now,blocked,imagePtr,coveragePtr,[]{return true;},output);
}
static std::string call(const char* cmd,unsigned frame=0,int index=-1) {
  JsonDocument object;object["cmd"]=cmd;object["requestId"]=id;
  if(frame)object["frameId"]=frame;
  if(index>=0)object["index"]=index;
  std::string request,result;serializeJson(object,request);CHECK(command(request,result));return result;
}
int main(int argc,char** argv) {
  if(argc==2 && std::strcmp(argv[1],"--check-failure")==0)CHECK(false);
  // Capture the actual pinned LVGL RGB565 compositor, including its top overlay.
  CHECK(capture.begin(id,now,imagePtr,coveragePtr));CHECK(capture.start(now,false));
  lv_init();auto* display=lv_display_create(mirror::width,mirror::height);
  lv_display_set_color_format(display,LV_COLOR_FORMAT_RGB565);
  lv_display_set_buffers(display,draw,nullptr,sizeof(draw),LV_DISPLAY_RENDER_MODE_PARTIAL);
  lv_display_set_flush_cb(display,flush);
  lv_obj_set_style_bg_color(lv_screen_active(),lv_color_hex(0xff0000),0);
  auto* overlay=lv_obj_create(lv_layer_top());lv_obj_remove_style_all(overlay);
  lv_obj_set_pos(overlay,100,100);lv_obj_set_size(overlay,100,100);
  lv_obj_set_style_bg_color(overlay,lv_color_hex(0x00ff00),0);lv_obj_set_style_bg_opa(overlay,LV_OPA_COVER,0);
  lv_obj_invalidate(lv_screen_active());lv_obj_invalidate(lv_layer_top());lv_tick_inc(40);
  lv_refr_now(display);CHECK(capture.state==mirror::State::ready);
  CHECK(image[0]==0xf800);CHECK(image[150*mirror::width+150]==0x07e0);
  const auto frame=capture.frame;
  auto reply=call("mirror_chunk",frame,0);JsonDocument part;CHECK(deserializeJson(part,reply)==DeserializationError::Ok);
  CHECK(std::strcmp(part["data"].as<const char*>(),"gAIA+A==")==0); // 640 red pixels, LE count/color.
  CHECK(reply.size()<4095);
  // Frozen frame must not change as the live display changes.
  std::fill(source.begin(),source.end(),0xffff);
  CHECK(!capture.flush(0,0,799,479,source.data(),source.size(),true,false,now));CHECK(image[0]==0xf800);
  call("mirror_end",frame);CHECK(capture.state==mirror::State::closed);
  CHECK(std::all_of(image.begin(),image.end(),[](uint16_t pixel){return pixel==0;}));
  std::string output;
  CHECK(!command("{\"cmd\":\"mirror_begin\",\"requestId\":1}",output));
  CHECK(!command("{\"cmd\":\"mirror_begin\",\"requestId\":\"0123456789abcdef0123456789abcdef\",\"extra\":true}",output));
  call("mirror_begin");CHECK(capture.frame!=frame);
  CHECK(!command("{\"cmd\":\"mirror_chunk\",\"requestId\":\"0123456789abcdef0123456789abcdef\",\"frameId\":1,\"index\":600}",output));
  CHECK(!command("{\"cmd\":\"mirror_status\",\"requestId\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"frameId\":2}",output));
  CHECK(!command("{\"cmd\":\"mirror_status\",\"requestId\":\"0123456789abcdef0123456789abcdef\",\"frameId\":1}",output));
  CHECK(!command("{\"cmd\":\"mirror_status\",\"requestId\":\"0123456789abcdef0123456789abcdef\",\"frameId\":true}",output));
  CHECK(!command("{\"cmd\":\"mirror_chunk\",\"requestId\":\"0123456789abcdef0123456789abcdef\",\"frameId\":2,\"index\":-1}",output));
  CHECK(!command("{\"cmd\":\"mirror_chunk\",\"requestId\":\"0123456789abcdef0123456789abcdef\",\"frameId\":2,\"index\":0.5}",output));
  CHECK(!command("{\"cmd\":\"mirror_touch\",\"requestId\":\"0123456789abcdef0123456789abcdef\",\"frameId\":2}",output));
  CHECK(!command("{\"cmd\":\"mirror_begin\",\"requestId\":\"0123456789ABCDEF0123456789abcdef\"}",output));
  CHECK(capture.start(now,false));
  // Incomplete refresh, overlap, invalid bounds and short data fail closed.
  CHECK(capture.flush(0,0,799,0,source.data(),800,true,false,now));CHECK(capture.state==mirror::State::unavailable);
  CHECK(capture.begin(id,now,imagePtr,coveragePtr));capture.start(now,false);
  CHECK(capture.flush(0,0,799,239,source.data(),800*240,false,false,now));
  CHECK(capture.flush(0,0,799,239,source.data(),800*240,true,false,now));
  CHECK(capture.state==mirror::State::unavailable); // Repeated pixels do not complete coverage.
  CHECK(capture.begin(id,now,imagePtr,coveragePtr));capture.start(now,false);
  CHECK(!capture.flush(-1,0,799,479,source.data(),source.size(),true,false,now));
  CHECK(capture.begin(id,now,imagePtr,coveragePtr));capture.start(now,false);
  CHECK(!capture.flush(0,0,799,479,source.data(),1,true,false,now));
  // Worst-case alternating color RLE remains bounded and all chunks are exact.
  CHECK(capture.begin(id,now,imagePtr,coveragePtr));capture.start(now,false);
  for(unsigned i=0;i<mirror::pixels;++i)source[i]=uint16_t(i);
  CHECK(capture.flush(0,0,799,479,source.data(),source.size(),true,false,now));
  CHECK(capture.chunk(0).size()==3416);CHECK(capture.chunk(599).size()==3416);CHECK(capture.chunk(600).empty());
  reply=call("mirror_chunk",capture.frame,599);CHECK(reply.size()<4095);
  blocked=true;call("mirror_status",capture.frame);CHECK(capture.state==mirror::State::unavailable);
  CHECK(std::all_of(image.begin(),image.end(),[](uint16_t pixel){return pixel==0;}));
  reply=call("mirror_begin");JsonDocument denied;CHECK(deserializeJson(denied,reply)==DeserializationError::Ok);
  CHECK(denied["frameId"].as<unsigned>()==0);CHECK(std::strcmp(denied["state"].as<const char*>(),"unavailable")==0);
  blocked=false;call("mirror_begin");now+=30000;call("mirror_status",capture.frame);CHECK(capture.state==mirror::State::expired);
  // Rollover-safe lease and absolute deadline even when valid requests keep arriving.
  now=0xfffffff0;call("mirror_begin");capture.start(now,false);capture.flush(0,0,799,479,source.data(),source.size(),true,false,now);
  for(unsigned i=0;i<5;++i){now+=25000;call("mirror_status",capture.frame);}
  CHECK(capture.state==mirror::State::expired);
  JsonDocument request;request["cmd"]="mirror_begin";request["requestId"]=id;
  CHECK(mirror::handle(capture,request.as<JsonObjectConst>(),now,false,imagePtr,coveragePtr,[]{return false;},output));
  CHECK(deserializeJson(denied,output)==DeserializationError::Ok);CHECK(denied["frameId"].as<unsigned>()==0);
  lv_display_delete(display);lv_deinit();std::cout<<"Real LVGL RGB565 flush capture and bounded mirror protocol passed\n";
}
