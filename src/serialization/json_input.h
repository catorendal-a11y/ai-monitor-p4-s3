#pragma once
#include <cstddef>
#include <cstdint>

namespace serialization {
inline bool utf8_valid(const uint8_t* bytes,size_t length) {
  for (size_t i=0;i<length;) {
    const uint8_t first=bytes[i++];
    if (first<128) continue;
    unsigned count; uint32_t value,minimum;
    if (first>=0xc2 && first<=0xdf) { count=1; value=first&31; minimum=128; }
    else if (first>=0xe0 && first<=0xef) { count=2; value=first&15; minimum=2048; }
    else if (first>=0xf0 && first<=0xf4) { count=3; value=first&7; minimum=65536; }
    else return false;
    if (count>length-i) return false;
    for (unsigned j=0;j<count;++j) {
      const uint8_t next=bytes[i++]; if ((next&0xc0)!=0x80) return false;
      value=(value<<6)|(next&63);
    }
    if (value<minimum || value>0x10ffff || (value>=0xd800 && value<=0xdfff)) return false;
  }
  return true;
}
inline bool space(uint8_t value) { return value==' ' || value=='\t' || value=='\r' || value=='\n'; }
// ArduinoJson accepts some non-JSON forms. Validate grammar first, without allocation.
// Property names must be unescaped ASCII. Hash collisions conservatively reject input.
class JsonPreflight {
 public:
  JsonPreflight(const uint8_t* bytes,size_t length):bytes_(bytes),length_(length) {}
  bool object() {
    whitespace();
    if (peek()!='{' || !value(0)) return false;
    whitespace(); return position_==length_;
  }
 private:
  const uint8_t* bytes_;
  size_t length_,position_=0;
  uint8_t peek() const { return position_<length_ ? bytes_[position_] : 0; }
  void whitespace() { while (position_<length_ && space(peek())) ++position_; }
  bool take(uint8_t ch) { if (peek()!=ch) return false; ++position_; return true; }
  static bool digit(uint8_t ch) { return ch>='0' && ch<='9'; }
  bool hex4(uint16_t& result) {
    result=0;
    for (unsigned i=0;i<4;++i) {
      const auto ch=peek(); unsigned nibble;
      if (digit(ch)) nibble=ch-'0';
      else if (ch>='a' && ch<='f') nibble=ch-'a'+10;
      else if (ch>='A' && ch<='F') nibble=ch-'A'+10;
      else return false;
      ++position_; result=static_cast<uint16_t>((result<<4)|nibble);
    }
    return true;
  }
  bool string(uint32_t* key=nullptr) {
    if (!take('"')) return false;
    uint32_t hash=2166136261u; size_t count=0;
    while (position_<length_) {
      const auto ch=bytes_[position_++];
      if (ch=='"') { if (key) { if (!count) return false; *key=hash; } return true; }
      if (ch<32 || (key && (ch<33 || ch>126 || ch=='\\'))) return false;
      ++count; hash=(hash^ch)*16777619u;
      if (ch!='\\') continue;
      const auto escaped=peek(); if (!escaped) return false; ++position_;
      if (escaped=='u') {
        uint16_t code; if (!hex4(code)) return false;
        if (code>=0xdc00 && code<=0xdfff) return false;
        if (code>=0xd800 && code<=0xdbff) {
          uint16_t low;
          if (!take('\\') || !take('u') || !hex4(low) || low<0xdc00 || low>0xdfff) return false;
        }
      } else if (escaped!='"' && escaped!='\\' && escaped!='/' && escaped!='b' && escaped!='f' &&
                 escaped!='n' && escaped!='r' && escaped!='t') return false;
    }
    return false;
  }
  bool literal(const char* word) {
    for (;*word;++word) if (!take(static_cast<uint8_t>(*word))) return false;
    return true;
  }
  bool number() {
    take('-');
    if (!take('0')) {
      if (peek()<'1' || peek()>'9') return false;
      do { ++position_; } while (digit(peek()));
    }
    if (take('.')) { if (!digit(peek())) return false; do { ++position_; } while (digit(peek())); }
    if (take('e') || take('E')) {
      if (!take('+')) take('-');
      if (!digit(peek())) return false;
      do { ++position_; } while (digit(peek()));
    }
    return true;
  }
  bool value(unsigned depth) {
    whitespace();
    const auto ch=peek();
    if (ch=='"') return string();
    if (ch=='t') return literal("true");
    if (ch=='f') return literal("false");
    if (ch=='n') return literal("null");
    if (ch!='{' && ch!='[') return number();
    if (depth>=12) return false;
    ++position_; whitespace();
    const bool isObject=ch=='{'; const uint8_t close=isObject ? '}' : ']';
    if (take(close)) return true;
    uint32_t keys[24]{}; unsigned keyCount=0;
    do {
      whitespace();
      if (isObject) {
        uint32_t key;
        if (keyCount>=24 || !string(&key)) return false;
        for (unsigned i=0;i<keyCount;++i) if (keys[i]==key) return false;
        keys[keyCount++]=key;
        whitespace(); if (!take(':')) return false;
      }
      if (!value(depth+1)) return false;
      whitespace(); if (take(close)) return true;
    } while (take(','));
    return false;
  }
};
inline bool strict_object(const uint8_t* bytes,size_t length,size_t maximum=8192) {
  return bytes && length && length<=maximum && utf8_valid(bytes,length) && JsonPreflight(bytes,length).object();
}
}  // namespace serialization
