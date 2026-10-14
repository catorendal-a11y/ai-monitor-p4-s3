#include "interaction/enrollment_lease.h"
#include <cassert>
int main() {
  interaction::EnrollmentLease lease;
  assert(!lease.valid(0,true));
  lease.start(100);assert(lease.valid(3099,true));assert(!lease.valid(3100,true));
  assert(!lease.renew(3100,true));assert(!lease.valid(3101,true));
  lease.start(200);assert(!lease.renew(201,false));assert(!lease.valid(202,true));
  lease.start(UINT32_MAX-1000);assert(lease.renew(500,true));
  assert(lease.valid(3499,true));assert(!lease.renew(3500,true));
  lease.start(0);lease.cancel();assert(!lease.renew(1,true));
  lease.start(0);assert(lease.renew(2999,true));assert(lease.valid(5998,true));
  assert(!lease.valid(5999,true));
}
