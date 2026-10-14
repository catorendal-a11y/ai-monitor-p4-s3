#pragma once
// ESP implementation of standard crypto primitives. Serial-owner only after initialization.
#include <cstddef>
#include <cstdint>
#include <mbedtls/ecdh.h>
namespace interaction::esp_crypto {
bool initialize();
bool random(uint8_t* output,size_t length);
bool hmac_sha256(const uint8_t* key,const uint8_t* input,size_t length,uint8_t* output);
bool sha256(const uint8_t* input,size_t length,uint8_t* output);
bool hkdf_sha256(const uint8_t* shared,const uint8_t* salt,const uint8_t* info,size_t length,uint8_t* output);
class EcdhKey {
 public:
  EcdhKey();~EcdhKey();
  EcdhKey(const EcdhKey&)=delete;EcdhKey& operator=(const EcdhKey&)=delete;
  bool generate(uint8_t* publicKey); // 65-byte uncompressed P-256 point.
  bool shared(const uint8_t* peer,uint8_t* secret); // Peer:65, secret:32.
 private:
  mbedtls_ecp_group group_;mbedtls_mpi private_;mbedtls_ecp_point public_;
  bool generated_=false;
};
}
