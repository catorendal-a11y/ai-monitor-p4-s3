#pragma once
#include <cstddef>
#include <cstdint>

namespace diagnostics {
// Exact existing logical-to-panel mapping: destination row W-1-x, column y.
inline bool rotate_to_panel(const uint16_t* input, size_t inputPixels, uint16_t* output,
                            size_t outputPixels, unsigned width, unsigned height) {
  if (!input || !output || input == output || width == 0 || height == 0 || width > 800 || height > 480) return false;
  const size_t pixels = static_cast<size_t>(width) * height;
  if (pixels > inputPixels || pixels > outputPixels) return false;
  for (unsigned row = 0; row < height; ++row)
    for (unsigned column = 0; column < width; ++column)
      output[(width - 1 - column) * height + row] = input[row * width + column];
  return true;
}
}  // namespace diagnostics
