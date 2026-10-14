#pragma once
#include <cstddef>
#include <cstdint>

namespace companions {
// LVGL's byte RLE accepts a one-byte overrun by truncating it. Runtime frames
// require exact output, so validate the complete stream before calling it.
inline bool exact_rle(const uint8_t* input, size_t length, size_t outputBytes) {
  if (!input || !length || !outputBytes || length > 400000 || outputBytes > 366360) return false;
  size_t read = 0, written = 0;
  while (read < length) {
    const auto control = input[read++];
    const size_t count = control & 0x7fu;
    const size_t consumed = (control & 0x80u) ? count : 1;
    if (!count || consumed > length-read || count > outputBytes-written) return false;
    read += consumed; written += count;
  }
  return written == outputBytes;
}
}
