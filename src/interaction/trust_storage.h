#pragma once
#include "auth_session.h"
#include <array>

namespace interaction {
using Sha256=bool(*)(const uint8_t*,size_t,uint8_t*);
// Storage returns only complete fixed-size records. Missing/corrupt/unavailable all fail closed.
// One atomic blob; no persisted opt-in or authority flags. Checksum detects corruption,
// not malicious modification. Device physical flash protection is a separate boundary.
template<class Storage> class TrustStorage {
 public:
  static constexpr size_t bytes=104;
  TrustStorage(Storage& storage,Sha256 hash):storage_(storage),hash_(hash){}
  bool load(DeviceTrust& trust) {
    wipe(trust.key,sizeof(trust.key));trust=DeviceTrust{};
    std::array<uint8_t,bytes> record{};uint8_t digest[32]{};
    bool ok=hash_ && storage_.read(record.data(),record.size()) &&
      !memcmp(record.data(),"AIMTRST1",8) && hash_(record.data(),72,digest);
    unsigned difference=0;
    if(ok)for(unsigned i=0;i<32;++i)difference|=digest[i]^record[72+i];
    ok=ok && !difference;
    if(ok) {
      memcpy(trust.deviceId,record.data()+8,32);memcpy(trust.key,record.data()+40,32);
      unsigned key=0;for(auto value:trust.key)key|=value;
      ok=hex_string(trust.deviceId,32) && key;
    }
    wipe(record.data(),record.size());wipe(digest,sizeof(digest));
    if(!ok){wipe(trust.key,sizeof(trust.key));trust=DeviceTrust{};}
    return ok;
  }
  bool save(const DeviceTrust& trust) {
    unsigned key=0;for(auto value:trust.key)key|=value;
    if(!hash_ || !hex_string(trust.deviceId,32) || !key || trust.optedIn)return false;
    std::array<uint8_t,bytes> record{};
    memcpy(record.data(),"AIMTRST1",8);memcpy(record.data()+8,trust.deviceId,32);
    memcpy(record.data()+40,trust.key,32);
    bool ok=hash_(record.data(),72,record.data()+72) && storage_.write(record.data(),record.size());
    DeviceTrust verified;
    if(ok)ok=load(verified) && !strcmp(verified.deviceId,trust.deviceId) && !memcmp(verified.key,trust.key,32);
    wipe(verified.key,sizeof(verified.key));wipe(record.data(),record.size());return ok;
  }
  bool forget() {
    if(!storage_.erase())return false;
    // The backend must distinguish absence from I/O failure when verifying erasure.
    return storage_.absent();
  }
 private:Storage& storage_;Sha256 hash_;
};
}
