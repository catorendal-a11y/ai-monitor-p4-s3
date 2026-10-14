#pragma once
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <map>
#include <string>
#include <vector>

namespace fake_nvs {
inline std::map<std::string, std::vector<uint8_t>> values;
inline bool fail_open = false, fail_write = false;
inline unsigned writes = 0;
}
class Preferences {
 public:
  bool begin(const char*, bool = false) { return !fake_nvs::fail_open; }
  void end() {}
  size_t getBytesLength(const char* key) { return fake_nvs::values[key].size(); }
  size_t getBytes(const char* key, void* destination, size_t capacity) {
    const auto& bytes = fake_nvs::values[key];
    const size_t size = std::min(capacity, bytes.size());
    if (size) std::memcpy(destination, bytes.data(), size);
    return size;
  }
  size_t putBytes(const char* key, const void* value, size_t size) {
    ++fake_nvs::writes;
    if (fake_nvs::fail_write) return 0;
    const auto* bytes = static_cast<const uint8_t*>(value);
    fake_nvs::values[key] = std::vector<uint8_t>(bytes, bytes + size);
    return size;
  }
  uint8_t getUChar(const char* key, uint8_t fallback) { return get<uint8_t>(key, fallback); }
  uint16_t getUShort(const char* key, uint16_t fallback) { return get<uint16_t>(key, fallback); }
  bool getBool(const char* key, bool fallback) { return get<bool>(key, fallback); }
  size_t putUChar(const char* key, uint8_t value) { return putBytes(key, &value, sizeof(value)); }
  size_t putUShort(const char* key, uint16_t value) { return putBytes(key, &value, sizeof(value)); }
  size_t putBool(const char* key, bool value) { return putBytes(key, &value, sizeof(value)); }
 private:
  template<typename T> T get(const char* key, T fallback) {
    T value = fallback;
    const auto& bytes = fake_nvs::values[key];
    if (bytes.size() == sizeof(T)) std::memcpy(&value, bytes.data(), sizeof(T));
    return value;
  }
};
