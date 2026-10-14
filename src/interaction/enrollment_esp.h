#pragma once
#include "enrollment.h"
#include "crypto_esp.h"
namespace interaction {
struct EspEnrollmentCrypto {
  using Key=esp_crypto::EcdhKey;
  static bool random(uint8_t* output,size_t length){return esp_crypto::random(output,length);}
  static bool hmac(const uint8_t* key,const uint8_t* input,size_t length,uint8_t* output) {
    return esp_crypto::hmac_sha256(key,input,length,output);
  }
  static bool sha256(const uint8_t* input,size_t length,uint8_t* output){return esp_crypto::sha256(input,length,output);}
  static bool hkdf(const uint8_t* shared,const uint8_t* salt,const uint8_t* info,size_t length,uint8_t* output) {
    return esp_crypto::hkdf_sha256(shared,salt,info,length,output);
  }
};
// The serial owner must explicitly initialize esp_crypto and provide transactional storage.
// No instance is created or registered by production startup at this checkpoint.
using EspEnrollmentDevice=EnrollmentDevice<EspEnrollmentCrypto>;
}
