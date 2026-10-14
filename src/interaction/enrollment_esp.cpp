#include "enrollment_esp.h"
// Compile-check the real ESP adapter even while production activation remains disconnected.
template class interaction::EnrollmentDevice<interaction::EspEnrollmentCrypto>;
