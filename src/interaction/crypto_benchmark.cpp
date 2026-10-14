#include "crypto_benchmark.h"
#if defined(AIM_USB_AUTH_BENCHMARK)
#include <Arduino.h>
#include <ArduinoJson.h>
#include "crypto_esp.h"
#include "auth_session.h"

namespace interaction {
std::string crypto_benchmark() {
  // One experiment per boot, using ephemeral test keys only. No NVS, trust enrollment,
  // provider permission, real hook or interaction-session authorization is exercised.
  static std::string cached;if(!cached.empty())return cached;
  JsonDocument report;report["type"]="crypto_benchmark";report["schema"]=1;
  report["ready"]=esp_crypto::initialize();
  uint8_t publicOne[65]{},publicTwo[65]{},one[32]{},two[32]{},key[32]{},hash[32]{};
  uint32_t generationUs=0,agreementUs=0,hmacUs=0;
  bool generated=false,agreed=false,hashed=false,derived=false;
  if(report["ready"]==true) {
    esp_crypto::EcdhKey first,second;
    auto started=micros();generated=first.generate(publicOne) && second.generate(publicTwo);generationUs=micros()-started;
    if(generated) {
      started=micros();agreed=first.shared(publicTwo,one) && second.shared(publicOne,two);agreementUs=micros()-started;
      unsigned difference=0;for(size_t i=0;i<32;++i)difference|=one[i]^two[i];agreed &= difference==0;
    }
    static const uint8_t info[]="AI-Monitor USB enrollment v1";
    uint8_t salt[32]{};salt[0]=1;
    if(agreed)derived=esp_crypto::hkdf_sha256(one,salt,info,sizeof(info)-1,key);
    static const uint8_t message[]="AIM benchmark fixture";
    if(derived) {started=micros();hashed=esp_crypto::hmac_sha256(key,message,sizeof(message)-1,hash);hmacUs=micros()-started;}
  }
  report["ecdhGenerated"]=generated;report["ecdhAgreed"]=agreed;report["hkdfDerived"]=derived;
  report["hmacVerified"]=hashed;report["twoKeygensUs"]=generationUs;report["twoAgreementsUs"]=agreementUs;report["hmacUs"]=hmacUs;
  report["internalFreeBytes"]=ESP.getFreeHeap();report["psramFreeBytes"]=ESP.getFreePsram();
  wipe(one,sizeof(one));wipe(two,sizeof(two));wipe(key,sizeof(key));wipe(hash,sizeof(hash));
  serializeJson(report,cached);return cached;
}
}
#endif
