#pragma once
#include <cstdint>
#include <cstring>
namespace interaction {
inline constexpr uint32_t lease_ms=30000;
struct PermissionRequest {
  char id[97]{},tool[65]{},hint[513]{};
  char nonce[65]{};
  bool present=false,displaySupported=false;
  bool equals(const PermissionRequest& other)const {
    return present==other.present && displaySupported==other.displaySupported &&
      !strcmp(id,other.id) && !strcmp(nonce,other.nonce) && !strcmp(tool,other.tool) && !strcmp(hint,other.hint);
  }
};
struct InteractionSnapshot {
  bool fresh=false;
  uint32_t receivedAt=0,epoch=0,revision=0;
  uint32_t leaseMs=lease_ms;
  PermissionRequest request;
};
}
