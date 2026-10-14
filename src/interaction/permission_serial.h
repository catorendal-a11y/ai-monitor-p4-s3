#pragma once
#include "usb_interaction.h"
#include "permission_delivery.h"
namespace interaction {
// Adapter serializes calls with its task mutex. No LVGL, port, filesystem or wire opt-in here.
class PermissionSerial {
 public:
  using Clock=uint32_t(*)();
  using Connected=bool(*)();
  using Capacity=size_t(*)();
  using Write=size_t(*)(const uint8_t*,size_t);
  static constexpr size_t maxDecisionBytes=768;
  PermissionSerial(HashMac hash,RandomBytes random,Clock clock):usb_(hash,random),clock_(clock){}
  void configure(const DeviceTrust& trust,uint32_t boot) {
    usb_.configure(trust,boot);optedIn_=trust.optedIn;connected_=false;abort_=false;delivery_.cancel();
  }
  void poll(uint32_t now,bool connected) {
    connected_=connected;
    if(abort_ || !connected_ || !optedIn_){usb_.invalidate();delivery_.cancel();abort_=false;}
    usb_.poll(now);
    if(!usb_.trusted())delivery_.cancel();
  }
  bool handle(JsonObjectConst object,uint32_t now,std::string& reply) {
    poll(now,connected_);
    if(!connected_ || !optedIn_){reply.clear();return false;}
    const bool ok=usb_.handle(object,now,reply);
    if(!ok || !usb_.trusted())delivery_.cancel();
    return ok;
  }
  const InteractionSnapshot& snapshot()const{return usb_.snapshot();}
  PermissionContext context(bool visible,bool awake)const {
    return {connected_,optedIn_,usb_.trusted(),visible,awake,false};
  }
  void observe_ui(bool visible,bool awake,uint32_t now) {
    delivery_.update_local(usb_.snapshot(),context(visible,awake),now);
  }
  bool offer_ui(const PermissionEnvelope& value,bool visible,bool awake,uint32_t now,
                PermissionDelivery::Commit commit,void* owner) {
    return delivery_.offer(value,usb_.snapshot(),context(visible,awake),now,commit,owner);
  }
  void cancel_ui(){delivery_.cancel();abort_=true;}
  bool queued()const{return delivery_.queued();}
  // Called only by the existing serial owner, when ordinary output is empty. Never queues
  // approvals behind quota data. Capacity and connection are checked again after signing.
  bool transmit(Connected connected,Capacity capacity,Write write) {
    if(!clock_ || !connected || !capacity || !write)return false;
    uint32_t now=clock_();poll(now,connected());
    if(!delivery_.queued() || capacity()<maxDecisionBytes)return false;
    const auto value=delivery_.take(usb_.snapshot(),context(true,true),now);
    if(value.decision==Decision::none)return false;
    std::string packet;
    if(!usb_.decision(value,now,packet)){delivery_.cancel();return false;}
    const size_t remaining=capacity();
    now=clock_();poll(now,connected());
    // take() consumed the envelope, but the local observation remains usable for this
    // final post-crypto gate. No pending envelope is re-created or retried.
    if(!PermissionController::valid(value,usb_.snapshot(),context(true,true),now) ||
       !delivery_.local_valid(value,usb_.snapshot(),context(true,true),now) ||
       packet.empty() || packet.size()+1>maxDecisionBytes || remaining<packet.size()+1 || !connected()) {
      usb_.invalidate();delivery_.cancel();return false;
    }
    packet+='\n';
    const bool sent=write(reinterpret_cast<const uint8_t*>(packet.data()),packet.size())==packet.size();
    if(!sent){usb_.invalidate();delivery_.cancel();}
    return sent;
  }
 private:
  UsbInteraction usb_;
  PermissionDelivery delivery_;
  Clock clock_;
  bool connected_=false,optedIn_=false,abort_=false;
};
}
