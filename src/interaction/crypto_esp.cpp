#include "crypto_esp.h"
#include "auth_session.h"
#include <mbedtls/md.h>
#include <mbedtls/ctr_drbg.h>
#include <esp_random.h>
#include <bootloader_random.h>

namespace interaction::esp_crypto {
static mbedtls_ctr_drbg_context generator;
static bool initialized=false;
static int entropy(void*,unsigned char* output,size_t length) {
  if(!output || length>256)return -1;
  // Product has no RF/ADC consumers. Briefly enable the documented physical entropy
  // source; never rely on an unseeded/pseudo-random stream for enrollment/session nonces.
  bootloader_random_enable();esp_fill_random(output,length);bootloader_random_disable();return 0;
}
bool hmac_sha256(const uint8_t* key,const uint8_t* input,size_t length,uint8_t* output) {
  if(!key || !input || !output || length>2048)return false;
  const auto* algorithm=mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  return algorithm && mbedtls_md_hmac(algorithm,key,32,input,length,output)==0;
}
bool sha256(const uint8_t* input,size_t length,uint8_t* output) {
  if(!input || !output || !length || length>2048)return false;
  const auto* algorithm=mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  return algorithm && mbedtls_md(algorithm,input,length,output)==0;
}
bool initialize() {
  if(initialized)return true;
  // Known-answer self-test only. This fixture key is never an enrolled/production key.
  uint8_t key[32],digest[32];for(unsigned i=0;i<32;++i)key[i]=i+1;
  static const char message[]="AIM crypto self-test";
  const bool known=hmac_sha256(key,reinterpret_cast<const uint8_t*>(message),sizeof(message)-1,digest) &&
    encode_hex(digest,sizeof(digest))=="bbd83789f92b05c9dd291916101cf26c527f3245837ae724fb28c9e1ce6df932";
  wipe(key,sizeof(key));wipe(digest,sizeof(digest));if(!known)return false;
  mbedtls_ctr_drbg_init(&generator);
  static const unsigned char personalization[]="AI Monitor USB interaction v1";
  if(mbedtls_ctr_drbg_seed(&generator,entropy,nullptr,personalization,sizeof(personalization)-1)!=0) {
    mbedtls_ctr_drbg_free(&generator);return false;
  }
  initialized=true;return true;
}
bool random(uint8_t* output,size_t length) {
  return initialized && output && length>0 && length<=256 && mbedtls_ctr_drbg_random(&generator,output,length)==0;
}
static int rng(void*,unsigned char* output,size_t length){return random(output,length)?0:-1;}
bool hkdf_sha256(const uint8_t* shared,const uint8_t* salt,const uint8_t* info,size_t length,uint8_t* output) {
  if(!shared || !salt || !info || !output || length>256)return false;
  uint8_t prk[32];
  if(!hmac_sha256(salt,shared,32,prk)){wipe(prk,sizeof(prk));return false;}
  std::string expand(reinterpret_cast<const char*>(info),length);expand+='\x01';
  const bool ok=hmac_sha256(prk,reinterpret_cast<const uint8_t*>(expand.data()),expand.size(),output);
  wipe(prk,sizeof(prk));return ok;
}
EcdhKey::EcdhKey(){mbedtls_ecp_group_init(&group_);mbedtls_mpi_init(&private_);mbedtls_ecp_point_init(&public_);}
EcdhKey::~EcdhKey(){mbedtls_ecp_point_free(&public_);mbedtls_mpi_free(&private_);mbedtls_ecp_group_free(&group_);}
bool EcdhKey::generate(uint8_t* output) {
  if(generated_ || !initialized || !output || mbedtls_ecp_group_load(&group_,MBEDTLS_ECP_DP_SECP256R1)!=0 ||
     mbedtls_ecdh_gen_public(&group_,&private_,&public_,rng,nullptr)!=0)return false;
  size_t length=0;
  generated_=mbedtls_ecp_point_write_binary(&group_,&public_,MBEDTLS_ECP_PF_UNCOMPRESSED,&length,output,65)==0 && length==65;
  return generated_;
}
bool EcdhKey::shared(const uint8_t* peer,uint8_t* secret) {
  if(!generated_ || !peer || !secret || peer[0]!=4)return false;
  mbedtls_ecp_point point;mbedtls_mpi result;mbedtls_ecp_point_init(&point);mbedtls_mpi_init(&result);
  const bool ok=mbedtls_ecp_point_read_binary(&group_,&point,peer,65)==0 &&
    mbedtls_ecp_check_pubkey(&group_,&point)==0 && mbedtls_ecdh_compute_shared(&group_,&result,&point,&private_,rng,nullptr)==0 &&
    mbedtls_mpi_write_binary(&result,secret,32)==0;
  mbedtls_mpi_free(&result);mbedtls_ecp_point_free(&point);return ok;
}
}
