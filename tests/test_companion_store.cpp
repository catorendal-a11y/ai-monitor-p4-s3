#include "companions/pack_store.h"
#include <cstring>
#include <iostream>
#include <string>
#include <vector>
static int failures=0;
#define CHECK(x) do{if(!(x)){std::cerr<<__LINE__<<": "<<#x<<"\n";++failures;}}while(0)
static bool hash(const uint8_t*,size_t,const char* expected){return std::string(expected)==std::string(64,'a');}
static bool decode(companions::Codec codec,const uint8_t* source,size_t count,uint8_t* target,size_t bytes){
 if(codec!=companions::Codec::raw || count!=bytes)return false;memcpy(target,source,count);return true;
}
int main(){
 using companions::PackStore;
 uint8_t first[4096]{},second[4096]{},scratch[16]{};
 PackStore store;
 CHECK(store.initialize(first,second,sizeof(first),scratch,sizeof(scratch),hash,decode));
 const std::string nonce(32,'1'),other(32,'2'),id(64,'a');
 const std::string digest(64,'a');
 const std::string manifest="{\"version\":2,\"name\":\"Fixture\",\"format\":\"RGB565A8\",\"codec\":\"raw\",\"fallback\":\"resting\",\"frames\":[{\"id\":\"one\",\"file\":\"one.raw\",\"width\":1,\"height\":1,\"originX\":0,\"originY\":0,\"encodedBytes\":3,\"decodedBytes\":3,\"encodedSha256\":\""+digest+"\",\"decodedSha256\":\""+digest+"\"}],\"animations\":[{\"mood\":\"resting\",\"loop\":true,\"frames\":[{\"id\":\"one\",\"durationMs\":100}]}]}";
 std::vector<uint8_t> blob(4+manifest.size()+3);
 for(unsigned i=0;i<4;++i)blob[i]=static_cast<uint8_t>(manifest.size()>>(8*i));
 memcpy(blob.data()+4,manifest.data(),manifest.size());
 blob[blob.size()-1]=255;
 CHECK(!store.active());
 CHECK(!store.begin(nonce.c_str(),5000,id.c_str(),0));
 CHECK(store.begin(nonce.c_str(),blob.size(),id.c_str(),0));
 CHECK(!store.chunk(other.c_str(),0,blob.data(),100,1));
 CHECK(!store.chunk(nonce.c_str(),1,blob.data(),100,1));
 CHECK(store.chunk(nonce.c_str(),0,blob.data(),100,1));
 CHECK(!store.finish(nonce.c_str(),2));
 CHECK(!store.active());
 CHECK(store.begin(nonce.c_str(),blob.size(),id.c_str(),3));
 for(size_t offset=0;offset<blob.size();offset+=100)
  CHECK(store.chunk(nonce.c_str(),offset,blob.data()+offset,std::min(size_t(100),blob.size()-offset),4));
 CHECK(store.finish(nonce.c_str(),5));
 CHECK(!store.active()); // Only UI activation can publish a verified complete pack.
 CHECK(store.activate());CHECK(store.active() && store.active()->frameCount==1);
 CHECK(store.frame(0) && store.frame(0)[2]==255);
 CHECK(!strcmp(store.active_id(),id.c_str()));
 CHECK(store.begin(other.c_str(),blob.size(),id.c_str(),6));
 auto corrupt=blob;corrupt[4]='X';
 for(size_t offset=0;offset<corrupt.size();offset+=100)
  CHECK(store.chunk(other.c_str(),offset,corrupt.data()+offset,std::min(size_t(100),corrupt.size()-offset),7));
 CHECK(!store.finish(other.c_str(),8));
 CHECK(store.active() && store.frame(0)[2]==255); // Failed replacement retains old pixels.
 CHECK(store.begin(other.c_str(),blob.size(),id.c_str(),9));
 store.expire(40010);
 CHECK(!store.chunk(other.c_str(),0,blob.data(),100,40011));
 store.disable();CHECK(!store.active());
 CHECK(!store.activate());
 if(failures)return 1;
 std::cout<<"Bounded staged companion transfer, UI activation and fallback tests passed\n";
}
