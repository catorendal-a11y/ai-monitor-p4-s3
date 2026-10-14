#pragma once
// Serial-owner enrollment core. Only local UI calls may arm/confirm; never wire booleans.
#include "auth_session.h"
#include <optional>

namespace interaction {
enum class EnrollmentState : uint8_t { closed, armed, comparing, confirmed, complete };
using SaveTrust=bool(*)(const DeviceTrust&);
using EnrollmentGate=bool(*)(uint32_t revision,uint32_t now);

// Crypto provides Key::generate/shared, random, sha256, hkdf and hmac. Key owns its
// ephemeral private material and destroys it on reset. No UI, NVS or transport ownership here.
template<class Crypto> class EnrollmentDevice {
 public:
  static constexpr uint32_t lifetimeMs=60000;
  EnrollmentDevice(SaveTrust save,EnrollmentGate gate):save_(save),gate_(gate){}
  ~EnrollmentDevice(){cancel();}
  EnrollmentDevice(const EnrollmentDevice&)=delete;
  EnrollmentDevice& operator=(const EnrollmentDevice&)=delete;
  bool arm(const char* deviceId,uint32_t bootId,uint32_t now) {
    cancel();
    if(!hex_string(deviceId,32) || !bootId || !save_ || !gate_ || generation_==UINT32_MAX)return false;
    ++generation_;
    memcpy(deviceId_,deviceId,33);bootId_=bootId;started_=now;state_=EnrollmentState::armed;
    return true;
  }
  void cancel() {
    ephemeral_.reset();wipe(key_,sizeof(key_));wipe(code_,sizeof(code_));
    if(!transcript_.empty())wipe(transcript_.data(),transcript_.size());
    transcript_.clear();wipe(deviceId_,sizeof(deviceId_));bootId_=started_=0;
    state_=EnrollmentState::closed;
  }
  void poll(uint32_t now) {
    if(state_!=EnrollmentState::closed && state_!=EnrollmentState::complete && now-started_>=lifetimeMs)cancel();
  }
  EnrollmentState state() const{return state_;}
  uint32_t revision() const{return generation_;}
  const char* code() const{return code_;} // Safe comparison code only. No key/hint export.
  bool begin(JsonObjectConst object,uint32_t now,std::string& reply) {
    reply.clear();poll(now);
    if(state_!=EnrollmentState::armed || object.size()!=4 ||
       !text_field(object["cmd"],18) || strcmp(object["cmd"],"interaction_enroll") ||
       !object["schema"].is<uint32_t>() || object["schema"].as<uint32_t>()!=1 ||
       !text_field(object["publicKey"],130) || !hex_string(object["publicKey"],130) ||
       strncmp(object["publicKey"],"04",2) || !text_field(object["nonce"],64) || !hex_string(object["nonce"],64)) {
      cancel();return false;
    }
    uint8_t peer[65],publicKey[65]{},shared[32]{},nonce[32]{},salt[32]{},display[32]{};
    const char* encoded=object["publicKey"];
    for(size_t i=0;i<65;++i)peer[i]=static_cast<uint8_t>((digit(encoded[i*2])<<4)|digit(encoded[i*2+1]));
    ephemeral_.emplace();
    bool ok=ephemeral_->generate(publicKey) && publicKey[0]==4 && ephemeral_->shared(peer,shared) && Crypto::random(nonce,32);
    if(ok) {
      transcript_.assign("AIM-ENROLL-1\0",13);transcript_+=deviceId_;transcript_+=encoded;
      transcript_+=encode_hex(publicKey,65);transcript_+=object["nonce"].template as<const char*>();
      transcript_+=encode_hex(nonce,32);append_u32(transcript_,bootId_);
      static const uint8_t info[]="AI-Monitor USB enrollment v1";
      ok=Crypto::sha256(reinterpret_cast<const uint8_t*>(transcript_.data()),transcript_.size(),salt) &&
         Crypto::hkdf(shared,salt,info,sizeof(info)-1,key_) && has_key() && sign("display",display);
    }
    ephemeral_.reset();wipe(shared,sizeof(shared));wipe(salt,sizeof(salt));
    if(ok) {
      const auto hex=encode_hex(display,8);
      for(unsigned i=0,j=0;i<16;++i) {
        if(i && i%4==0)code_[j++]='-';
        code_[j++]=hex[i]>='a' && hex[i]<='f'?static_cast<char>(hex[i]-'a'+'A'):hex[i];
      }
      JsonDocument response;response["type"]="interaction_enrollment";response["schema"]=1;
      response["deviceId"]=deviceId_;response["publicKey"]=encode_hex(publicKey,65);
      response["nonce"]=encode_hex(nonce,32);response["hostNonce"]=object["nonce"].template as<const char*>();
      response["bootId"]=bootId_;serializeJson(response,reply);state_=EnrollmentState::comparing;
    }
    wipe(display,sizeof(display));wipe(nonce,sizeof(nonce));
    if(!ok)cancel();
    return ok;
  }
  // Called only after a local, fully visible physical comparison action. A wire command
  // cannot call this method. Losing visibility/awake/connection must call cancel().
  bool confirm_physical(uint32_t displayedRevision,bool visible,bool awake,uint32_t now) {
    poll(now);
    if(state_!=EnrollmentState::comparing || displayedRevision!=generation_ || !visible || !awake || !gate_(generation_,now)){cancel();return false;}
    state_=EnrollmentState::confirmed;return true;
  }
  bool commit(JsonObjectConst object,uint32_t now,std::string& reply) {
    reply.clear();poll(now);uint8_t expected[32]{};uint8_t finished[32]{};
    bool ok=state_==EnrollmentState::confirmed && gate_ && gate_(generation_,now) && object.size()==4 &&
      text_field(object["cmd"],25) && !strcmp(object["cmd"],"interaction_enroll_commit") &&
      object["schema"].is<uint32_t>() && object["schema"].as<uint32_t>()==1 &&
      text_field(object["deviceId"],32) && !strcmp(object["deviceId"],deviceId_) &&
      text_field(object["proof"],64) && hex_string(object["proof"],64) && sign("enroll-host",expected);
    if(ok) {
      const auto hex=encode_hex(expected,32);unsigned mismatch=0;
      const char* offered=object["proof"];for(unsigned i=0;i<64;++i)mismatch|=hex[i]^offered[i];
      ok=!mismatch && sign("enroll-device",finished);
    }
    if(ok) {
      DeviceTrust record;memcpy(record.deviceId,deviceId_,33);memcpy(record.key,key_,32);
      // Enrollment stores identity only. Permission opt-in is a separate local setting.
      record.optedIn=false;ok=gate_(generation_,now) && save_(record) && gate_(generation_,now);wipe(record.key,sizeof(record.key));
      if(ok) {
        JsonDocument response;response["type"]="interaction_enrolled";response["schema"]=1;
        response["deviceId"]=deviceId_;response["proof"]=encode_hex(finished,32);serializeJson(response,reply);
      }
    }
    wipe(expected,sizeof(expected));wipe(finished,sizeof(finished));cancel();
    if(ok)state_=EnrollmentState::complete;
    return ok;
  }
 private:
  static unsigned digit(char c){return c<='9'?c-'0':c-'a'+10;}
  bool has_key() const{unsigned value=0;for(auto byte:key_)value|=byte;return value!=0;}
  bool sign(const char* label,uint8_t* output) {
    std::string input(label);input+='\0';input+=transcript_;
    return Crypto::hmac(key_,reinterpret_cast<const uint8_t*>(input.data()),input.size(),output);
  }
  SaveTrust save_;EnrollmentGate gate_;EnrollmentState state_=EnrollmentState::closed;
  uint32_t bootId_=0,started_=0,generation_=0;char deviceId_[33]{},code_[20]{};uint8_t key_[32]{};
  std::string transcript_;std::optional<typename Crypto::Key> ephemeral_;
};
}
