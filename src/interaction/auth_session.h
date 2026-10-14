#pragma once
// Transport authentication only. No enrollment, permissions, quota state or LVGL authority.
#include <ArduinoJson.h>
#include <cstdint>
#include <cstring>
#include <limits>
#include <string>

namespace interaction {
using HashMac=bool(*)(const uint8_t* key,const uint8_t* input,size_t length,uint8_t* output);
using RandomBytes=bool(*)(uint8_t* output,size_t length);
inline void wipe(void* value,size_t length) {
  auto* bytes=static_cast<volatile uint8_t*>(value);while(length--)*bytes++=0;
}
inline bool hex_string(const char* value,size_t length) {
  if(!value)return false;
  for(size_t i=0;i<length;++i)if(!((value[i]>='0' && value[i]<='9') || (value[i]>='a' && value[i]<='f')))return false;
  return value[length]=='\0';
}
inline std::string encode_hex(const uint8_t* input,size_t length) {
  static const char digits[]="0123456789abcdef";std::string output;output.reserve(length*2);
  for(size_t i=0;i<length;++i){output+=digits[input[i]>>4];output+=digits[input[i]&15];}return output;
}
inline void append_u32(std::string& value,uint32_t number) {
  for(int i=3;i>=0;--i)value+=static_cast<char>(number>>(8*i));
}
inline bool text_field(JsonVariantConst field,size_t exact=0,size_t maximum=1024) {
  if(!field.is<const char*>())return false;
  const JsonString value=field.as<JsonString>();
  const size_t length=value.size();
  if(!length || length>maximum || (exact && length!=exact))return false;
  for(size_t i=0;i<length;++i)if(!value.c_str()[i])return false;
  return true;
}
struct DeviceTrust {
  char deviceId[33]{};
  uint8_t key[32]{};
  bool optedIn=false; // Local enrollment/settings only. Never parse from a JSON field.
};
class AuthSession {
 public:
  static constexpr uint32_t handshakeMs=3000,leaseMs=5000;
  static constexpr size_t maxBody=1024;
  AuthSession(HashMac hash,RandomBytes random):hash_(hash),random_(random){}
  ~AuthSession(){close();wipe(trust_.key,sizeof(trust_.key));}
  AuthSession(const AuthSession&)=delete;
  AuthSession& operator=(const AuthSession&)=delete;
  void configure(const DeviceTrust& trust,uint32_t bootId) {
    close();wipe(trust_.key,sizeof(trust_.key));trust_=trust;bootId_=bootId;
    unsigned hasKey=0;for(const auto byte:trust_.key)hasKey|=byte;
    if(!hex_string(trust_.deviceId,32) || !bootId_ || !hasKey)trust_.optedIn=false;
  }
  bool open(JsonObjectConst object,uint32_t now,std::string& reply) {
    close();reply.clear();
    if(!trust_.optedIn || !hash_ || !random_ || generation_==std::numeric_limits<uint32_t>::max() ||
       object.size()!=5 || !text_field(object["cmd"],16) || strcmp(object["cmd"],"interaction_open") ||
       !object["schema"].is<uint32_t>() || object["schema"].as<uint32_t>()!=1 ||
       !text_field(object["deviceId"],32) || strcmp(object["deviceId"],trust_.deviceId) ||
       !text_field(object["instance"],32) || !hex_string(object["instance"],32) ||
       !text_field(object["hostNonce"],64) || !hex_string(object["hostNonce"],64))return false;
    uint8_t random[32];
    if(!random_(random,sizeof(random))){wipe(random,sizeof(random));return false;}
    const auto deviceNonce=encode_hex(random,sizeof(random));wipe(random,sizeof(random));
    const uint32_t epoch=++generation_;
    transcript_.assign("AIM-AUTH-1\0",11);transcript_+=trust_.deviceId;
    transcript_+=object["instance"].as<const char*>();transcript_+=object["hostNonce"].as<const char*>();
    transcript_+=deviceNonce;append_u32(transcript_,bootId_);append_u32(transcript_,epoch);
    uint8_t identity[32];
    if(!digest(trust_.key,"session",transcript_,identity) || !digest(trust_.key,"key",transcript_,key_)) {
      wipe(identity,sizeof(identity));close();return false;
    }
    session_=encode_hex(identity,sizeof(identity));wipe(identity,sizeof(identity));
    std::string signature;if(!sign_hex(trust_.key,"device",transcript_,signature)){close();return false;}
    JsonDocument document;document["type"]="interaction_challenge";document["schema"]=1;
    document["deviceId"]=trust_.deviceId;document["instance"]=object["instance"].as<const char*>();
    document["hostNonce"]=object["hostNonce"].as<const char*>();document["deviceNonce"]=deviceNonce;
    document["bootId"]=bootId_;document["epoch"]=epoch;document["proof"]=signature;
    serializeJson(document,reply);seenAt_=now;pending_=true;return true;
  }
  bool prove(JsonObjectConst object,uint32_t now,std::string& reply) {
    reply.clear();
    if(!pending_ || now-seenAt_>=handshakeMs || object.size()!=4 ||
       !text_field(object["cmd"],17) || strcmp(object["cmd"],"interaction_prove") ||
       !object["schema"].is<uint32_t>() || object["schema"].as<uint32_t>()!=1 ||
       !text_field(object["session"],64) || session_!=object["session"].as<const char*>() ||
       !text_field(object["proof"],64) || !verify(trust_.key,"host",transcript_,object["proof"])) {
      close();return false;
    }
    std::string signature;if(!sign_hex(key_,"ready",session_,signature)){close();return false;}
    JsonDocument document;document["type"]="interaction_ready";document["schema"]=1;
    document["session"]=session_;document["proof"]=signature;serializeJson(document,reply);
    pending_=false;authenticated_=true;seenAt_=now;return true;
  }
  bool receive(JsonObjectConst object,uint32_t now,std::string& body) {
    body.clear();poll(now);
    if(!authenticated_ || object.size()!=6 || !text_field(object["cmd"],11) || strcmp(object["cmd"],"interaction") ||
       !object["schema"].is<uint32_t>() || object["schema"].as<uint32_t>()!=1 ||
       !text_field(object["session"],64) || session_!=object["session"].as<const char*>() ||
       !object["sequence"].is<uint32_t>() || rx_==std::numeric_limits<uint32_t>::max() ||
       object["sequence"].as<uint32_t>()!=rx_+1 || !text_field(object["body"],0,maxBody) ||
       !text_field(object["mac"],64)) {close();return false;}
    const std::string raw=object["body"].as<const char*>();
    for(const auto character:raw)if(character<32 || character>126){close();return false;}
    const uint32_t sequence=object["sequence"];
    const auto input=packet_input("host",sequence,raw);
    if(!verify_raw(key_,input,object["mac"])) {close();return false;}
    JsonDocument parsed;
    if(deserializeJson(parsed,raw)!=DeserializationError::Ok || !parsed.is<JsonObject>()) {close();return false;}
    std::string canonical;serializeJson(parsed,canonical);
    if(canonical!=raw){close();return false;} // Reject duplicates/ambiguous encodings.
    rx_=sequence;seenAt_=now;body=raw;return true;
  }
  bool send(const std::string& body,uint32_t now,std::string& reply) {
    reply.clear();poll(now);
    if(!authenticated_ || body.empty() || body.size()>maxBody || tx_==std::numeric_limits<uint32_t>::max()) {close();return false;}
    for(const auto character:body)if(character<32 || character>126){close();return false;}
    const uint32_t sequence=++tx_;uint8_t signature[32];
    const auto input=packet_input("device",sequence,body);
    if(!hash_(key_,reinterpret_cast<const uint8_t*>(input.data()),input.size(),signature)) {
      wipe(signature,sizeof(signature));close();return false;
    }
    JsonDocument document;document["type"]="interaction_packet";document["schema"]=1;
    document["session"]=session_;document["sequence"]=sequence;document["body"]=body;
    document["mac"]=encode_hex(signature,sizeof(signature));wipe(signature,sizeof(signature));serializeJson(document,reply);return true;
  }
  void poll(uint32_t now) {
    if((pending_ && now-seenAt_>=handshakeMs) || (authenticated_ && now-seenAt_>=leaseMs))close();
  }
  bool authenticated()const{return authenticated_;}
  uint32_t epoch()const{return generation_;}
  const std::string& session()const{return session_;}
  void close() {
    pending_=authenticated_=false;rx_=tx_=0;wipe(key_,sizeof(key_));
    if(!transcript_.empty())wipe(&transcript_[0],transcript_.size());
    transcript_.clear();session_.clear();
  }
 private:
  HashMac hash_;RandomBytes random_;DeviceTrust trust_;
  uint8_t key_[32]{};uint32_t generation_=0,bootId_=0,seenAt_=0,rx_=0,tx_=0;
  bool pending_=false,authenticated_=false;
  std::string transcript_,session_;
  bool digest(const uint8_t* key,const char* label,const std::string& text,uint8_t* output)const {
    std::string input=label;input+='\0';input+=text;
    return hash_ && hash_(key,reinterpret_cast<const uint8_t*>(input.data()),input.size(),output);
  }
  bool sign_hex(const uint8_t* key,const char* label,const std::string& text,std::string& output)const {
    uint8_t signature[32];const bool ok=digest(key,label,text,signature);
    if(ok)output=encode_hex(signature,sizeof(signature));
    wipe(signature,sizeof(signature));return ok;
  }
  bool verify(const uint8_t* key,const char* label,const std::string& text,const char* signature)const {
    std::string input=label;input+='\0';input+=text;return verify_raw(key,input,signature);
  }
  bool verify_raw(const uint8_t* key,const std::string& input,const char* signature)const {
    if(!hex_string(signature,64))return false;
    uint8_t computed[32];
    if(!hash_(key,reinterpret_cast<const uint8_t*>(input.data()),input.size(),computed)){wipe(computed,sizeof(computed));return false;}
    const auto expected=encode_hex(computed,sizeof(computed));wipe(computed,sizeof(computed));
    unsigned difference=0;for(size_t i=0;i<64;++i)difference|=static_cast<unsigned char>(expected[i]^signature[i]);
    return difference==0;
  }
  std::string packet_input(const char* direction,uint32_t sequence,const std::string& body)const {
    std::string input("AIM-PACKET-1\0",13);input+=direction;input+='\0';input+=session_;
    append_u32(input,sequence);input+=static_cast<char>(body.size()>>8);input+=static_cast<char>(body.size());input+=body;return input;
  }
};
}
