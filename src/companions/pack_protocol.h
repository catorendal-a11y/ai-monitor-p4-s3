#pragma once
#include "pack_store.h"
#include <string>
namespace companions {
inline bool pack_command(PackStore& store,uint32_t boot,JsonObjectConst object,uint32_t now,std::string& reply) {
  if(!object["cmd"].is<const char*>())return false;
  const char* command=object["cmd"].as<const char*>();
  const bool begin=!strcmp(command,"pack_begin"),chunk=!strcmp(command,"pack_chunk"),finish=!strcmp(command,"pack_finish");
  const bool status=!strcmp(command,"pack_status"),builtin=!strcmp(command,"pack_builtin"),abort=!strcmp(command,"pack_abort");
  if(!begin && !chunk && !finish && !status && !builtin && !abort)return false;
  char nonce[33]{};
  const bool nonceValid=text(object["nonce"],nonce,sizeof(nonce),false) && strlen(nonce)==32 &&
      strspn(nonce,"0123456789abcdef")==32;
  bool ok=nonceValid && object["bootId"].is<uint32_t>() && object["bootId"].as<uint32_t>()==boot;
  if(begin) {
    char digest[65]{};
    ok=ok && animation_fields(object,{"cmd","nonce","bootId","id","bytes"}) &&
       text(object["id"],digest,sizeof(digest),false,true) && object["bytes"].is<uint32_t>();
    if(ok)ok=store.begin(nonce,object["bytes"].as<uint32_t>(),digest,now);
  } else if(chunk) {
    ok=ok && animation_fields(object,{"cmd","nonce","bootId","offset","data"}) &&
       object["offset"].is<uint32_t>() && object["data"].is<const char*>();
    uint8_t decoded[512]{};size_t length=0;
    if(ok) {
      const auto value=object["data"].as<JsonString>();const char* data=value.c_str();length=value.size();
      ok=length>0 && length<=1024 && length%2==0 && strlen(data)==length;
      auto digit=[](char c)->int{return c>='0' && c<='9'?c-'0':c>='a' && c<='f'?c-'a'+10:-1;};
      if(ok)for(size_t i=0;i<length;i+=2){const int a=digit(data[i]),b=digit(data[i+1]);if(a<0 || b<0){ok=false;break;}decoded[i/2]=uint8_t(a*16+b);}
      if(ok)ok=store.chunk(nonce,object["offset"].as<uint32_t>(),decoded,length/2,now);
    }
  } else {
    ok=ok && animation_fields(object,{"cmd","nonce","bootId"});
    if(ok && finish)ok=store.finish(nonce,now);
    if(ok && builtin)store.request_builtin();
    if(ok && abort)store.cancel();
  }
  JsonDocument result;
  result["type"]="pack_reply";result["schema"]=1;result["cmd"]=command;
  result["bootId"]=boot;result["nonce"]=nonce;result["ok"]=ok;
  result["state"]=store.phase();result["id"]=store.active_id();result["offset"]=store.offset();
  reply.clear();serializeJson(result,reply);return true;
}
}
