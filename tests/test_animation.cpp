#include "companions/builtin_animation.h"
#include "companions/animation.h"
#include <iostream>
#include <string>
static int failures=0;
#define CHECK(x) do {if(!(x)){std::cerr<<__LINE__<<": "<<#x<<"\n";++failures;}}while(0)
int main() {
  using namespace companions;
  const std::string hash(64,'a');
  const std::string asset="{\"id\":\"one\",\"file\":\"one.raw\",\"width\":2,\"height\":1,\"originX\":28,\"originY\":0,"
    "\"encodedBytes\":6,\"decodedBytes\":6,\"encodedSha256\":\""+hash+"\",\"decodedSha256\":\""+hash+"\"}";
  const std::string clip="{\"mood\":\"working\",\"loop\":true,\"frames\":[{\"id\":\"one\",\"durationMs\":100},{\"id\":\"one\",\"durationMs\":200}]}";
  const std::string valid="{\"version\":2,\"name\":\"Test\",\"format\":\"RGB565A8\",\"codec\":\"raw\",\"fallback\":\"working\",\"frames\":["+asset+"],\"animations\":["+clip+"]}";
  AnimationManifest manifest;auto parse=[&](const std::string& value){return parse_animation_manifest(reinterpret_cast<const uint8_t*>(value.data()),value.size(),manifest);};
  CHECK(parse(valid));CHECK(manifest.version==2 && manifest.frameCount==1 && manifest.animationCount==1);
  CHECK(manifest.resolve(Mood::attention)==manifest.find(Mood::working));
  for(const auto& fault:{std::pair<std::string,std::string>{"\"version\":2","\"version\":true"},
      {"\"loop\":true","\"loop\":1"},{"\"durationMs\":100","\"durationMs\":39"},
      {"\"durationMs\":100","\"durationMs\":60001"},{"\"durationMs\":100","\"durationMs\":true"},
      {"one.raw","../one.raw"},{"\"id\":\"one\",\"durationMs\":100","\"id\":\"missing\",\"durationMs\":100"},
      {"\"fallback\":\"working\"","\"fallback\":\"success\""},
      {"\"codec\":\"raw\"","\"codec\":\"zip\""},
      {"\"version\":2","\"version\":2,\"unknown\":true"}}) {
    auto bad=valid;bad.replace(bad.find(fault.first),fault.first.size(),fault.second);
    CHECK(!parse(bad));CHECK(manifest.frameCount==1 && manifest.version==2);
  }
  CHECK(!parse(valid+"{}"));CHECK(!parse(std::string(max_manifest_bytes+1,' ')));
  auto duplicate=valid;duplicate.replace(duplicate.find("\"animations\":["),14,"\"animations\":["+clip+",");CHECK(!parse(duplicate));
  AnimationPlayer player;Animation sequence{Mood::working,true,2,{{1,100},{2,200}}};
  CHECK(player.select(&sequence,0xfffffff0u));CHECK(player.frame(0xfffffff0u)==1);
  CHECK(player.frame(84)==2);CHECK(player.frame(284)==1);CHECK(player.frame(584)==1);
  CHECK(player.select(&sequence,584));CHECK(player.frame(634)==1);
  CHECK(player.select(&sequence,634,true));CHECK(player.frame(734)==2);
  Animation success{Mood::success,false,2,{{3,100},{4,200}}};
  CHECK(player.select(&success,0));CHECK(player.frame(99)==3);CHECK(!player.finished());
  CHECK(player.frame(100)==4);CHECK(player.frame(300)==4 && player.finished());
  CHECK(player.frame(0xfffffff0u)==4 && player.finished());
  CHECK(!player.select(nullptr,0));Animation empty;CHECK(!player.select(&empty,0));
  for(const auto& built:builtin_animations){CHECK(player.select(&built,10));CHECK(player.frame(10)<6);}
  if(failures)return 1;
  std::cout<<"Versioned bounded animation manifest, atomic rejection, timing, loop, fallback and rollover tests passed\n";
}
