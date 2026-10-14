#pragma once
#include "auth_session.h"
#include "permission_controller.h"

namespace interaction {
// Serial-owner domain. The UI still earns/commits the physical decision; this class never does.
class UsbInteraction {
 public:
  UsbInteraction(HashMac hash,RandomBytes random):auth_(hash,random){}
  void configure(const DeviceTrust& trust,uint32_t bootId) {
    auth_.configure(trust,bootId);clear_request();revision_=0;ledgerCount_=0;
  }
  bool handle(JsonObjectConst object,uint32_t now,std::string& reply) {
    reply.clear();poll(now);
    if(!text_field(object["cmd"],0,40))return invalidate();
    const char* command=object["cmd"];
    if(!strcmp(command,"interaction_open")) {
      clear_request();const bool ok=auth_.open(object,now,reply);++revision_;return ok;
    }
    if(!strcmp(command,"interaction_prove")) {
      const bool ok=auth_.prove(object,now,reply);
      if(ok){ledgerCount_=0;for(auto& entry:ledger_)entry={};}
      ++revision_;return ok;
    }
    if(strcmp(command,"interaction"))return invalidate();
    std::string raw;
    if(!auth_.receive(object,now,raw))return invalidate();
    JsonDocument document;
    if(deserializeJson(document,raw)!=DeserializationError::Ok)return invalidate();
    const auto body=document.as<JsonObjectConst>();
    if(!text_field(body["kind"],0,24))return invalidate();
    const char* kind=body["kind"];
    if(!strcmp(kind,"heartbeat")) {
      if(body.size()!=1)return invalidate();
      return auth_.send("{\"kind\":\"heartbeat\"}",now,reply);
    }
    if(!strcmp(kind,"close")) {
      if(body.size()!=1)return invalidate();
      const bool ok=auth_.send("{\"kind\":\"closed\"}",now,reply);auth_.close();clear_request();return ok;
    }
    if(!strcmp(kind,"cancel")) {
      if(body.size()!=4 || !matches(body))return invalidate();
      clear_request();return auth_.send("{\"kind\":\"cancelled\"}",now,reply);
    }
    if(strcmp(kind,"request") || body.size()!=7 || (snapshot_.request.present && !decided_) ||
       !text_field(body["requestId"],32) || !hex_string(body["requestId"],32) ||
       !text_field(body["nonce"],64) || !hex_string(body["nonce"],64) ||
       !body["revision"].is<uint32_t>() || body["revision"].as<uint32_t>()!=1 ||
       !body["expiresInMs"].is<uint32_t>() || !body["expiresInMs"].as<uint32_t>() || body["expiresInMs"].as<uint32_t>()>25000 ||
       !text_field(body["tool"],0,64) || !text_field(body["hint"],0,320) || ledgerCount_>=32)return invalidate();
    for(const char* c=body["tool"].as<const char*>();*c;++c)
      if(!((*c>='a' && *c<='z') || (*c>='A' && *c<='Z') || (*c>='0' && *c<='9') || *c=='_' || *c=='-'))return invalidate();
    for(const char* c=body["hint"].as<const char*>();*c;++c)if(*c<32 || *c>126)return invalidate();
    const char* id=body["requestId"],*nonce=body["nonce"];
    for(unsigned i=0;i<ledgerCount_;++i)if(!strcmp(id,ledger_[i].id) || !strcmp(nonce,ledger_[i].nonce))return invalidate();
    auto& entry=ledger_[ledgerCount_++];strcpy(entry.id,id);strcpy(entry.nonce,nonce);
    snapshot_={};snapshot_.fresh=true;snapshot_.receivedAt=now;snapshot_.leaseMs=body["expiresInMs"];
    snapshot_.epoch=auth_.epoch();snapshot_.revision=1;decided_=false;
    auto& request=snapshot_.request;request.present=request.displaySupported=true;
    strcpy(request.id,id);strcpy(request.nonce,nonce);strcpy(request.tool,body["tool"]);strcpy(request.hint,body["hint"]);
    ++revision_;
    JsonDocument acknowledgement;acknowledgement["kind"]="received";acknowledgement["requestId"]=id;
    acknowledgement["nonce"]=nonce;acknowledgement["revision"]=1;
    std::string response;serializeJson(acknowledgement,response);
    if(!auth_.send(response,now,reply))return invalidate();
    return true;
  }
  // The caller must have already passed PermissionView's UI-owner take/commit gates.
  // This second transport gate binds that earned decision to current authenticated authority.
  bool decision(const PermissionEnvelope& value,uint32_t now,std::string& reply) {
    reply.clear();poll(now);
    if(decided_ || !auth_.authenticated() || !snapshot_.fresh || !snapshot_.request.present ||
       now-snapshot_.receivedAt>=snapshot_.leaseMs || value.epoch!=snapshot_.epoch || value.revision!=snapshot_.revision ||
       !value.prompt.equals(snapshot_.request) || (value.decision!=Decision::once && value.decision!=Decision::deny))return false;
    decided_=true; // Consume before signing/write; failed or ambiguous delivery is never retried.
    JsonDocument document;document["kind"]="decision";document["requestId"]=value.prompt.id;
    document["nonce"]=value.prompt.nonce;document["revision"]=value.revision;
    document["decision"]=value.decision==Decision::once?"allow":"deny";
    std::string body;serializeJson(document,body);
    if(!auth_.send(body,now,reply))return invalidate();
    return true;
  }
  void poll(uint32_t now) {
    const bool was=auth_.authenticated();auth_.poll(now);
    if((was && !auth_.authenticated()) || (snapshot_.fresh && now-snapshot_.receivedAt>=snapshot_.leaseMs))clear_request();
  }
  bool trusted()const{return auth_.authenticated();}
  const InteractionSnapshot& snapshot()const{return snapshot_;}
  uint32_t publication_revision()const{return revision_;}
  const std::string& session()const{return auth_.session();}
  bool invalidate(){auth_.close();clear_request();return false;}
 private:
  struct Identity {char id[33]{},nonce[65]{};};Identity ledger_[32];unsigned ledgerCount_=0;
  AuthSession auth_;InteractionSnapshot snapshot_;uint32_t revision_=0;bool decided_=false;
  void clear_request(){snapshot_={};decided_=false;++revision_;}
  bool matches(JsonObjectConst value)const {
    return snapshot_.request.present && text_field(value["requestId"],32) && text_field(value["nonce"],64) &&
      value["revision"].is<uint32_t>() && value["revision"].as<uint32_t>()==snapshot_.revision &&
      !strcmp(value["requestId"],snapshot_.request.id) && !strcmp(value["nonce"],snapshot_.request.nonce);
  }
};
}
