#include "ai_monitor/ai_monitor_proto.h"
#include "companions/pack_protocol.h"
#include <cstring>
#include <iostream>
static int failures=0;
#define CHECK(x) do{if(!(x)){std::cerr<<__LINE__<<": "<<#x<<"\n";++failures;}}while(0)
static bool hash(const uint8_t*,size_t,const char*){return true;}
static bool decode(companions::Codec,const uint8_t*,size_t,uint8_t*,size_t){return true;}
static void feed(aim::ProtoCore& core,const char* line){for(const char* p=line;*p;++p)core.feed_byte(*p);}
int main(){
 uint8_t a[4096],b[4096],scratch[16];companions::PackStore store;
 CHECK(store.initialize(a,b,4096,scratch,16,hash,decode));
 aim::ProtoCore core;core.boot_id=17;
 core.companion_command=[&](JsonObjectConst object,uint32_t now,std::string& reply){return companions::pack_command(store,17,object,now,reply);};
 feed(core,"{\"cmd\":\"hello\"}\n");
 CHECK(core.out().find("\"companionProtocol\":1")!=std::string::npos);core.clear_out();
 feed(core,"{\"cmd\":\"pack_status\",\"bootId\":17,\"nonce\":\"11111111111111111111111111111111\"}\n");
 CHECK(core.out().find("\"state\":\"builtin\"")!=std::string::npos);core.clear_out();
 feed(core,"{\"cmd\":\"pack_begin\",\"bootId\":18,\"nonce\":\"11111111111111111111111111111111\",\"id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"bytes\":100}\n");
 CHECK(core.out().find("\"ok\":false")!=std::string::npos);core.clear_out();
 feed(core,"{\"cmd\":\"pack_begin\",\"bootId\":17,\"nonce\":\"11111111111111111111111111111111\",\"id\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"bytes\":100}\n");
 CHECK(core.out().find("\"ok\":true")!=std::string::npos);core.clear_out();
 feed(core,"{\"cmd\":\"pack_chunk\",\"bootId\":17,\"nonce\":\"11111111111111111111111111111111\",\"offset\":0,\"data\":\"xyz\"}\n");
 CHECK(core.out().find("\"ok\":false")!=std::string::npos);CHECK(store.offset()==0);
 if(failures)return 1;
 std::cout<<"Companion wire capability, boot ownership and strict chunk validation passed\n";
}
