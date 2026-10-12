#pragma once
#include <cstdint>
namespace diagnostics {
struct PpaBenchmark {
  const char* status = "not-run";
  uint32_t width = 800, height = 480, samples = 0;
  uint32_t cpuMedianUs = 0, ppaMedianUs = 0;
  bool bitExact = false, resourcesRetained = false;
};
void run_isolated_ppa_benchmark();
PpaBenchmark ppa_benchmark_result();
}
