// Generate transparent RGB565+A8 robot frames and original BGRA brand marks.
// Run with Node.js and sharp installed; generated C++ is committed with sources.
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const root = path.resolve(__dirname, '..');
const source = path.join(root, 'assets/nova');
const destination = path.join(root, 'src/ui');
const names = ['work', 'done', 'low', 'critical', 'sleep', 'blink'];
// Index order is the firmware's app_settings::Companion value.
const ROBOTS = ['nova', 'orbit', 'claude'];
const header = ['#pragma once', '#include <lvgl.h>', 'namespace nova_assets {'];
const cpp = ['// Generated from assets/nova/*.svg by scripts/generate_nova_assets.cjs.', '#include "nova_assets.h"', 'namespace nova_assets {'];
function emit(name, pixels, width, height, format, stride) {
  header.push(`extern const lv_image_dsc_t ${name};`);
  const pose = name.replace(/^(orbit|claude)_/, '');
  // P4 decodes non-work poses from LZ4; only the raw work pose stays as a fallback.
  const compressedPose = ['done','low','critical','sleep','blink'].includes(pose);
  if (compressedPose) cpp.push('#if !defined(CONFIG_IDF_TARGET_ESP32P4)');
  cpp.push(`alignas(4) static const uint8_t ${name}_pixels[] = {`);
  for (let i = 0; i < pixels.length; i += 24)
    cpp.push('  ' + [...pixels.subarray(i, i + 24)].map(value => '0x' + value.toString(16).padStart(2, '0')).join(',') + ',');
  cpp.push('};', `const lv_image_dsc_t ${name} = { {LV_IMAGE_HEADER_MAGIC, ${format}, 0, ${width}, ${height}, ${stride}, 0}, sizeof(${name}_pixels), ${name}_pixels, nullptr, nullptr };`);
  if (compressedPose) {
    const prefix = name.match(/^(orbit|claude)_/);
    const fallback = prefix ? prefix[1] + '_work' : 'work';
    cpp.push('#else', `const lv_image_dsc_t ${name} = { {LV_IMAGE_HEADER_MAGIC, ${format}, 0, ${width}, ${height}, ${stride}, 0}, sizeof(${fallback}_pixels), ${fallback}_pixels, nullptr, nullptr };`, '#endif');
  }
}
(async () => {
  const crops = {};
  for (const robot of ROBOTS) {
    let left=430,top=284,right=-1,bottom=-1;
    for (const pose of names) {
      const {data,info}=await sharp(path.join(root,'assets',robot,pose+'.svg')).ensureAlpha().raw().toBuffer({resolveWithObject:true});
      for (let y=0;y<info.height;y++) for (let x=0;x<info.width;x++) if (data[(y*info.width+x)*info.channels+3]) {
        left=Math.min(left,x);top=Math.min(top,y);right=Math.max(right,x);bottom=Math.max(bottom,y);
      }
    }
    if (right<left || bottom<top) throw new Error('Empty companion artwork');
    crops[robot]={left,top,width:right-left+1,height:bottom-top+1};
    header.push(`inline constexpr int16_t ${robot}_origin_x = ${left};`, `inline constexpr int16_t ${robot}_origin_y = ${top};`);
  }
  for (const robot of ROBOTS) for (const pose of [...names,'thumb']) {
    const name = robot === 'nova' && pose !== 'thumb' ? pose : robot + '_' + pose;
    const file = path.resolve(source,'..',robot, (pose === 'thumb' ? 'work' : pose) + '.svg');
    let pipeline = sharp(file);
    if (pose === 'thumb') pipeline = pipeline.resize(144,95);
    else pipeline = pipeline.extract(crops[robot]);
    const {data, info} = await pipeline.ensureAlpha().raw().toBuffer({resolveWithObject:true});
    const pixelCount = info.width * info.height;
    const rgb565 = Buffer.alloc(pixelCount * 3);
    for (let i = 0; i < info.width * info.height; ++i) {
      const offset = i * info.channels;
      const value = (data[offset] >> 3) << 11 | (data[offset + 1] >> 2) << 5 | data[offset + 2] >> 3;
      rgb565.writeUInt16LE(value, i * 2);
      rgb565[pixelCount * 2 + i] = data[offset + 3];
    }
    emit(name, rgb565, info.width, info.height, 'LV_COLOR_FORMAT_RGB565A8', info.width * 2);
  }
  for (const brand of ['openai', 'zcode']) for (const size of [24, 42, 48]) {
    const inner = brand === 'zcode' ? Math.round(size * 2 / 3) : size;
    const padding = Math.floor((size - inner) / 2);
    let pipeline = sharp(path.join(source, brand + '-logo-white.svg')).resize(inner,inner,{fit:'contain',background:{r:0,g:0,b:0,alpha:0}});
    if (inner !== size) pipeline = pipeline.extend({top:padding,bottom:size-inner-padding,left:padding,right:size-inner-padding,background:{r:0,g:0,b:0,alpha:0}});
    const {data} = await pipeline.ensureAlpha().raw().toBuffer({resolveWithObject:true});
    const bgra = Buffer.from(data);
    for (let i = 0; i < bgra.length; i += 4) { bgra[i] = data[i + 2]; bgra[i + 2] = data[i]; }
    emit(brand + size, bgra, size, size, 'LV_COLOR_FORMAT_ARGB8888', size * 4);
  }
  header.push('const lv_image_dsc_t* logo_for(const char* provider, unsigned size);', 'const lv_image_dsc_t* companion_pose(uint8_t companion, const lv_image_dsc_t* novaPose);', 'const lv_image_dsc_t* companion_thumb(uint8_t companion);', '}');
  cpp.push('const lv_image_dsc_t* logo_for(const char* provider, unsigned size) {',
    '  if (!provider) return nullptr;',
    '  if (strcmp(provider, "codex") == 0) return size == 24 ? &openai24 : (size == 42 ? &openai42 : &openai48);',
    '  if (strcmp(provider, "zcode") == 0) return size == 24 ? &zcode24 : (size == 42 ? &zcode42 : &zcode48);',
    '  return nullptr;', '}');
  cpp.push('const lv_image_dsc_t* companion_pose(uint8_t companion, const lv_image_dsc_t* novaPose) {');
  for (const [index, robot] of ROBOTS.entries()) if (index > 0) {
    cpp.push(`  if (companion == ${index}) {`);
    for (const name of names) cpp.push(`    if (novaPose == &${name}) return &${robot}_${name};`);
    cpp.push(`    return &${robot}_work;`, '  }');
  }
  cpp.push('  return novaPose;', '}');
  cpp.push('const lv_image_dsc_t* companion_thumb(uint8_t companion) {');
  for (const [index, robot] of ROBOTS.entries()) if (index > 0) cpp.push(`  if (companion == ${index}) return &${robot}_thumb;`);
  cpp.push('  return &nova_thumb;', '}', '}');
  cpp.splice(2, 0, '#include <cstring>');
  fs.writeFileSync(path.join(destination, 'nova_assets.h'), header.join('\n') + '\n');
  fs.writeFileSync(path.join(destination, 'nova_assets.cpp'), cpp.join('\n') + '\n');
  console.log('Generated '+ROBOTS.length*6+' transparent robot frames, '+ROBOTS.length+' thumbnails and 6 original-logo images.');
})().catch(error => { console.error(error.message); process.exit(1); });
