// Synthetic native interoperability endpoint. Never connected to USB, hooks or real trust.
#include "interaction/auth_session.h"
#include "interaction/usb_interaction.h"
#include "interaction/permission_serial.h"
#include "interaction/enrollment.h"
#include "interaction/trust_storage.h"
#include <iostream>
#include <vector>
#if defined(_WIN32)
#include <windows.h>
#include <bcrypt.h>
#else
#include <openssl/hmac.h>
#endif
static bool cryptoFailure=false;
static uint32_t serialNow=0,signDelay=0;
static bool serialConnected=true,partialWrite=false;
static bool disconnectOnSign=false;
static size_t serialCapacity=2048,serialWrites=0;
static size_t capacityCalls=0;
static uint32_t capacityDelay=0;
static std::string serialOutput;
static uint32_t serial_clock(){return serialNow;}
static bool serial_connected(){return serialConnected;}
static size_t serial_capacity(){if(++capacityCalls==2)serialNow+=capacityDelay;return serialCapacity;}
static size_t serial_write(const uint8_t* bytes,size_t length) {
  ++serialWrites;const size_t written=partialWrite?length/2:length;
  serialOutput.assign(reinterpret_cast<const char*>(bytes),written);return written;
}
static bool ui_commit(void* owner,const interaction::PermissionEnvelope& value,
    const interaction::InteractionSnapshot& current,const interaction::PermissionContext& context,uint32_t now) {
  return static_cast<interaction::PermissionController*>(owner)->commit(value,current,context,now);
}
static bool hash(const uint8_t* key,const uint8_t* input,size_t length,uint8_t* output) {
  serialNow+=signDelay;
  if(disconnectOnSign)serialConnected=false;
  if(cryptoFailure)return false;
#if defined(_WIN32)
  BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE handle=nullptr;
  DWORD objectBytes=0,returned=0;
  if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,BCRYPT_ALG_HANDLE_HMAC_FLAG)<0)return false;
  bool ok=BCryptGetProperty(algorithm,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&objectBytes),sizeof(objectBytes),&returned,0)>=0;
  std::vector<uint8_t> object(objectBytes);
  if(ok)ok=BCryptCreateHash(algorithm,&handle,object.data(),objectBytes,const_cast<PUCHAR>(key),32,0)>=0;
  if(ok)ok=BCryptHashData(handle,const_cast<PUCHAR>(input),static_cast<ULONG>(length),0)>=0;
  if(ok)ok=BCryptFinishHash(handle,output,32,0)>=0;
  if(handle)BCryptDestroyHash(handle);
  interaction::wipe(object.data(),object.size());BCryptCloseAlgorithmProvider(algorithm,0);return ok;
#else
  unsigned int bytes=0;return HMAC(EVP_sha256(),key,32,input,length,output,&bytes)!=nullptr && bytes==32;
#endif
}
static bool random(uint8_t* output,size_t length) {
  // Deliberately fixed fixture nonce. This function is never built into production firmware.
  memset(output,0xaa,length);return true;
}
#include "enrollment_crypto.h"
struct FixtureStorage {
  std::vector<uint8_t> bytes;bool failRead=false,failWrite=false,failErase=false,corruptWrite=false;
  bool read(uint8_t* output,size_t length) {
    if(failRead || bytes.size()!=length)return false;
    memcpy(output,bytes.data(),length);return true;
  }
  bool write(const uint8_t* input,size_t length) {
    if(failWrite)return false;
    bytes.assign(input,input+length);if(corruptWrite)bytes.back()^=1;return true;
  }
  bool erase(){if(failErase)return false;bytes.clear();return true;}
  bool absent(){return !failRead && bytes.empty();}
};
static FixtureStorage storage;
static interaction::TrustStorage<FixtureStorage> trustStorage(storage,EnrollmentCrypto::sha256);
static interaction::DeviceTrust enrolled;
static unsigned saves=0;
static bool storageFailure=false;
static bool enrollmentGate=true;
static bool loseGateOnSave=false;
static bool local_gate(uint32_t,uint32_t){return enrollmentGate;}
static bool save_enrollment(const interaction::DeviceTrust& value) {
  if(storageFailure)return false;
  if(!trustStorage.save(value))return false;
  enrolled=value;++saves;if(loseGateOnSave)enrollmentGate=false;return true;
}
int main() {
  interaction::DeviceTrust trust;strcpy(trust.deviceId,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
  for(unsigned i=0;i<32;++i)trust.key[i]=static_cast<uint8_t>(i+1);
  trust.optedIn=true;interaction::AuthSession session(hash,random);session.configure(trust,17);
  interaction::UsbInteraction layer(hash,random);layer.configure(trust,17);
  interaction::PermissionSerial serialOwner(hash,random,serial_clock);serialOwner.configure(trust,17);
  interaction::PermissionController serialUi;
  interaction::EnrollmentDevice<EnrollmentCrypto> enrollment(save_enrollment,local_gate);
  std::string line;
  while(std::getline(std::cin,line)) {
    JsonDocument input,result;bool ok=false;std::string reply,body;
    if(line.size()<=4095 && deserializeJson(input,line)==DeserializationError::Ok && input["now"].is<uint32_t>()) {
      const uint32_t now=input["now"];const char* op=input["op"]|"";
      serialNow=now;
      if(!strcmp(op,"open"))ok=session.open(input["message"].as<JsonObjectConst>(),now,reply);
      else if(!strcmp(op,"prove"))ok=session.prove(input["message"].as<JsonObjectConst>(),now,reply);
      else if(!strcmp(op,"receive"))ok=session.receive(input["message"].as<JsonObjectConst>(),now,body);
      else if(!strcmp(op,"send"))ok=session.send(input["body"]|"",now,reply);
      else if(!strcmp(op,"poll")){session.poll(now);ok=true;}
      else if(!strcmp(op,"close")){session.close();ok=true;}
      else if(!strcmp(op,"fail_crypto")){cryptoFailure=true;ok=true;}
      else if(!strcmp(op,"opt_out")){trust.optedIn=false;session.configure(trust,17);layer.configure(trust,17);ok=true;}
      else if(!strcmp(op,"empty_key")){memset(trust.key,0,sizeof(trust.key));session.configure(trust,17);layer.configure(trust,17);ok=true;}
      else if(!strcmp(op,"enroll_arm"))ok=enrollment.arm("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",17,now);
      else if(!strcmp(op,"enroll_begin"))ok=enrollment.begin(input["message"].as<JsonObjectConst>(),now,reply);
      else if(!strcmp(op,"enroll_confirm"))ok=enrollment.confirm_physical(input["displayedRevision"]|enrollment.revision(),input["visible"]==true,input["awake"]==true,now);
      else if(!strcmp(op,"enroll_commit"))ok=enrollment.commit(input["message"].as<JsonObjectConst>(),now,reply);
      else if(!strcmp(op,"enroll_cancel")){enrollment.cancel();ok=true;}
      else if(!strcmp(op,"enroll_poll")){enrollment.poll(now);ok=true;}
      else if(!strcmp(op,"storage_failure")){storageFailure=true;ok=true;}
      else if(!strcmp(op,"lose_enrollment_gate")){enrollmentGate=false;ok=true;}
      else if(!strcmp(op,"lose_gate_on_save")){loseGateOnSave=true;ok=true;}
      else if(!strcmp(op,"enrolled_session")){enrolled.optedIn=true;session.configure(enrolled,17);ok=true;}
      else if(!strcmp(op,"storage_read_fail")){storage.failRead=true;ok=true;}
      else if(!strcmp(op,"storage_write_fail")){storage.failWrite=true;ok=true;}
      else if(!strcmp(op,"storage_corrupt_write")){storage.corruptWrite=true;ok=true;}
      else if(!strcmp(op,"storage_erase_fail")){storage.failErase=true;ok=true;}
      else if(!strcmp(op,"storage_save_fixture")){auto value=trust;value.optedIn=input["optedIn"]==true;ok=trustStorage.save(value);}
      else if(!strcmp(op,"storage_load"))ok=trustStorage.load(enrolled);
      else if(!strcmp(op,"serial_handle")) {
        serialOwner.poll(now,serialConnected);ok=serialOwner.handle(input["message"].as<JsonObjectConst>(),now,reply);
      } else if(!strcmp(op,"serial_earn")) {
        const auto current=serialOwner.snapshot();const auto context=serialOwner.context(true,true);
        serialUi.update(current,context,now);serialUi.displayed(true);
        if(input["deny"]==true)serialUi.deny(now);
        else if(serialUi.press(now-1800))serialUi.pressing(now,true);
        const auto value=serialUi.take(current,context,now);
        serialOwner.observe_ui(true,true,now);
        ok=serialOwner.offer_ui(value,true,true,now,ui_commit,&serialUi);
      } else if(!strcmp(op,"serial_observe")) {
        const bool visible=input["visible"]==true,awake=input["awake"]==true;
        serialOwner.observe_ui(visible,awake,now);
        serialUi.update(serialOwner.snapshot(),serialOwner.context(visible,awake),now);ok=true;
      } else if(!strcmp(op,"serial_transmit")) {
        serialConnected=input["connected"]|true;serialCapacity=input["capacity"]|2048u;
        partialWrite=input["partial"]==true;signDelay=input["signDelay"]|0u;serialOutput.clear();
        disconnectOnSign=input["disconnectOnSign"]==true;
        capacityCalls=0;capacityDelay=input["capacityDelay"]|0u;
        ok=serialOwner.transmit(serial_connected,serial_capacity,serial_write);signDelay=0;disconnectOnSign=false;
        reply=serialOutput;
      } else if(!strcmp(op,"serial_cancel")){serialOwner.cancel_ui();ok=true;}
      else if(!strcmp(op,"storage_forget"))ok=trustStorage.forget();
      else if(!strcmp(op,"storage_corrupt")){if(!storage.bytes.empty())storage.bytes[input["index"].as<unsigned>()%storage.bytes.size()]^=1;ok=true;}
      else if(!strcmp(op,"storage_short")){if(!storage.bytes.empty())storage.bytes.pop_back();ok=true;}
      else if(!strcmp(op,"layer_handle"))ok=layer.handle(input["message"].as<JsonObjectConst>(),now,reply);
      else if(!strcmp(op,"layer_poll")){layer.poll(now);ok=true;}
      else if(!strcmp(op,"layer_deny")) {
        const auto& current=layer.snapshot();interaction::PermissionEnvelope envelope;
        envelope.epoch=current.epoch;envelope.revision=current.revision;envelope.prompt=current.request;
        envelope.decision=interaction::Decision::deny;
        if(input["wrongNonce"]==true)strcpy(envelope.prompt.nonce,"wrong");
        ok=layer.decision(envelope,now,reply);
      }
    }
    result["ok"]=ok;result["authenticated"]=session.authenticated();result["body"]=body;
    result["enrollmentState"]=static_cast<unsigned>(enrollment.state());result["code"]=enrollment.code();
    result["enrollmentRevision"]=enrollment.revision();
    result["saves"]=saves;result["enrolledOptedIn"]=enrolled.optedIn;
    result["storedBytes"]=storage.bytes.size();
    result["layerTrusted"]=layer.trusted();result["requestPresent"]=layer.snapshot().request.present;
    result["serialQueued"]=serialOwner.queued();result["serialWrites"]=serialWrites;
    result["requestId"]=layer.snapshot().request.id;result["requestNonce"]=layer.snapshot().request.nonce;
    if(!reply.empty()) {
      JsonDocument response;
      if(deserializeJson(response,reply)==DeserializationError::Ok)result["reply"]=response.as<JsonObjectConst>();
    }
    std::string output;serializeJson(result,output);std::cout<<output<<std::endl;
  }
}
