#pragma once
// Actual native cryptography for synthetic enrollment interoperability. No USB/NVS.
#include <algorithm>
#if defined(_WIN32) && !defined(BCRYPT_KDF_RAW_SECRET)
// Older MinGW headers omit this documented Windows 10+ KDF identifier.
#define BCRYPT_KDF_RAW_SECRET L"TRUNCATE"
#endif
#if !defined(_WIN32)
#include <openssl/ec.h>
#include <openssl/core_names.h>
#include <openssl/params.h>
#endif
struct EnrollmentCrypto {
  class Key {
   public:
    Key()=default;
    Key(const Key&)=delete;Key& operator=(const Key&)=delete;
#if defined(_WIN32)
    ~Key(){if(key_)BCryptDestroyKey(key_);if(algorithm_)BCryptCloseAlgorithmProvider(algorithm_,0);}
    bool generate(uint8_t* output) {
      if(cryptoFailure || key_ || BCryptOpenAlgorithmProvider(&algorithm_,BCRYPT_ECDH_P256_ALGORITHM,nullptr,0)<0 ||
         BCryptGenerateKeyPair(algorithm_,&key_,256,0)<0 || BCryptFinalizeKeyPair(key_,0)<0)return false;
      uint8_t blob[sizeof(BCRYPT_ECCKEY_BLOB)+64]{};ULONG length=0;
      if(BCryptExportKey(key_,nullptr,BCRYPT_ECCPUBLIC_BLOB,blob,sizeof(blob),&length,0)<0 || length!=sizeof(blob))return false;
      output[0]=4;memcpy(output+1,blob+sizeof(BCRYPT_ECCKEY_BLOB),64);return true;
    }
    bool shared(const uint8_t* peer,uint8_t* output) {
      if(cryptoFailure || !key_ || peer[0]!=4)return false;
      uint8_t blob[sizeof(BCRYPT_ECCKEY_BLOB)+64]{};
      BCRYPT_ECCKEY_BLOB header{BCRYPT_ECDH_PUBLIC_P256_MAGIC,32};memcpy(blob,&header,sizeof(header));
      memcpy(blob+sizeof(header),peer+1,64);BCRYPT_KEY_HANDLE publicKey=nullptr;BCRYPT_SECRET_HANDLE secret=nullptr;
      bool ok=BCryptImportKeyPair(algorithm_,nullptr,BCRYPT_ECCPUBLIC_BLOB,&publicKey,blob,sizeof(blob),0)>=0;
      if(ok)ok=BCryptSecretAgreement(key_,publicKey,&secret,0)>=0;
      ULONG length=0;
      if(ok)ok=BCryptDeriveKey(secret,BCRYPT_KDF_RAW_SECRET,nullptr,output,32,&length,0)>=0 && length==32;
      // Microsoft documents RAW_SECRET as little endian; P-256 ECDH uses big endian here.
      if(ok)std::reverse(output,output+32);
      if(secret)BCryptDestroySecret(secret);
      if(publicKey)BCryptDestroyKey(publicKey);
      return ok;
    }
   private:BCRYPT_ALG_HANDLE algorithm_=nullptr;BCRYPT_KEY_HANDLE key_=nullptr;
#else
    ~Key(){if(key_)EVP_PKEY_free(key_);}
    bool generate(uint8_t* output) {
      if(cryptoFailure || key_)return false;
      auto* context=EVP_PKEY_CTX_new_id(EVP_PKEY_EC,nullptr);
      bool ok=context && EVP_PKEY_keygen_init(context)>0 &&
        EVP_PKEY_CTX_set_ec_paramgen_curve_nid(context,NID_X9_62_prime256v1)>0 && EVP_PKEY_keygen(context,&key_)>0;
      size_t length=0;
      if(ok)ok=EVP_PKEY_get_octet_string_param(key_,OSSL_PKEY_PARAM_PUB_KEY,output,65,&length)>0 && length==65;
      if(context)EVP_PKEY_CTX_free(context);
      return ok;
    }
    bool shared(const uint8_t* peer,uint8_t* output) {
      if(cryptoFailure || !key_ || peer[0]!=4)return false;
      char group[]="prime256v1";
      OSSL_PARAM params[]={OSSL_PARAM_construct_utf8_string(OSSL_PKEY_PARAM_GROUP_NAME,group,0),
        OSSL_PARAM_construct_octet_string(OSSL_PKEY_PARAM_PUB_KEY,const_cast<uint8_t*>(peer),65),OSSL_PARAM_construct_end()};
      auto* import=EVP_PKEY_CTX_new_from_name(nullptr,"EC",nullptr);EVP_PKEY* publicKey=nullptr;
      bool ok=import && EVP_PKEY_fromdata_init(import)>0 && EVP_PKEY_fromdata(import,&publicKey,EVP_PKEY_PUBLIC_KEY,params)>0;
      auto* context=ok?EVP_PKEY_CTX_new(key_,nullptr):nullptr;size_t length=32;
      if(ok)ok=context && EVP_PKEY_derive_init(context)>0 && EVP_PKEY_derive_set_peer(context,publicKey)>0 &&
        EVP_PKEY_derive(context,output,&length)>0 && length==32;
      if(context)EVP_PKEY_CTX_free(context);
      if(publicKey)EVP_PKEY_free(publicKey);
      if(import)EVP_PKEY_CTX_free(import);
      return ok;
    }
   private:EVP_PKEY* key_=nullptr;
#endif
  };
  static bool random(uint8_t* output,size_t length){if(cryptoFailure)return false;return ::random(output,length);}
  static bool hmac(const uint8_t* key,const uint8_t* input,size_t length,uint8_t* output){return ::hash(key,input,length,output);}
  static bool sha256(const uint8_t* input,size_t length,uint8_t* output) {
    if(cryptoFailure)return false;
#if defined(_WIN32)
    BCRYPT_ALG_HANDLE algorithm=nullptr;BCRYPT_HASH_HANDLE handle=nullptr;DWORD bytes=0,returned=0;
    if(BCryptOpenAlgorithmProvider(&algorithm,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)return false;
    bool ok=BCryptGetProperty(algorithm,BCRYPT_OBJECT_LENGTH,reinterpret_cast<PUCHAR>(&bytes),sizeof(bytes),&returned,0)>=0;
    std::vector<uint8_t> object(bytes);
    if(ok)ok=BCryptCreateHash(algorithm,&handle,object.data(),bytes,nullptr,0,0)>=0;
    if(ok)ok=BCryptHashData(handle,const_cast<PUCHAR>(input),static_cast<ULONG>(length),0)>=0;
    if(ok)ok=BCryptFinishHash(handle,output,32,0)>=0;
    if(handle)BCryptDestroyHash(handle);
    BCryptCloseAlgorithmProvider(algorithm,0);return ok;
#else
    unsigned int bytes=0;return EVP_Digest(input,length,output,&bytes,EVP_sha256(),nullptr)>0 && bytes==32;
#endif
  }
  static bool hkdf(const uint8_t* shared,const uint8_t* salt,const uint8_t* info,size_t length,uint8_t* output) {
    uint8_t prk[32]{};bool ok=hmac(salt,shared,32,prk);
    std::string expand(reinterpret_cast<const char*>(info),length);expand+='\x01';
    if(ok)ok=hmac(prk,reinterpret_cast<const uint8_t*>(expand.data()),expand.size(),output);
    interaction::wipe(prk,sizeof(prk));return ok;
  }
};
