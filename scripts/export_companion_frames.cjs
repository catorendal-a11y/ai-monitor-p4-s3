// Export trusted built-in vectors as the exact cropped RGB565+A8 pixel payload.
const fs=require('fs'),path=require('path'),crypto=require('crypto'),sharp=require('sharp');
const root=path.resolve(__dirname,'..');
const poses=['work','done','low','critical','sleep','blink'];
const position=process.argv.indexOf('--output');
if(position<0 || !process.argv[position+1]) throw new Error('Use --output DIRECTORY');
const output=path.resolve(process.argv[position+1]);
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const header=fs.readFileSync(path.join(root,'src/ui/nova_assets.h'),'utf8');
  const cpp=fs.readFileSync(path.join(root,'src/ui/nova_assets.cpp'),'utf8');
  const frames=[];
  for(const robot of ['nova','orbit']) for(const pose of poses){
    const left=Number(header.match(new RegExp(robot+'_origin_x = (\\d+)'))[1]);
    const top=Number(header.match(new RegExp(robot+'_origin_y = (\\d+)'))[1]);
    const symbol=robot==='nova'?pose:robot+'_'+pose;
    const dimensions=cpp.match(new RegExp('const lv_image_dsc_t '+symbol+' = \\{ \\{LV_IMAGE_HEADER_MAGIC, [^,]+, 0, (\\d+), (\\d+),'));
    if(!dimensions) throw new Error('Missing committed frame descriptor');
    const width=Number(dimensions[1]),height=Number(dimensions[2]);
    const {data,info}=await sharp(path.join(root,'assets',robot,pose+'.svg'))
      .extract({left,top,width,height}).ensureAlpha().raw().toBuffer({resolveWithObject:true});
    const pixels=info.width*info.height,raw=Buffer.alloc(pixels*3);
    for(let i=0;i<pixels;i++){
      const j=i*info.channels;
      raw.writeUInt16LE((data[j]>>3)<<11|(data[j+1]>>2)<<5|(data[j+2]>>3),i*2);
      raw[pixels*2+i]=data[j+3];
    }
    const committed=cpp.match(new RegExp(symbol+'_pixels\\[\\] = \\{([\\s\\S]*?)\\};'));
    const existing=Buffer.from(committed[1].match(/0x[0-9a-f]{2}/g).map(v=>parseInt(v,16)));
    if(!raw.equals(existing)) throw new Error('Export differs from committed pixels');
    const file=robot+'-'+pose+'.rgb565a8'; fs.writeFileSync(path.join(output,file),raw);
    frames.push({robot,pose,file,width,height,originX:left,originY:top,decodedBytes:raw.length,
      sha256:crypto.createHash('sha256').update(raw).digest('hex')});
  }
  fs.writeFileSync(path.join(output,'frames.json'),JSON.stringify({schema:1,format:'RGB565A8',frames},null,2)+'\n');
  console.log('Exported 12 trusted frames; all equal the committed pixel arrays.');
})().catch(error=>{console.error(error.message);process.exitCode=1;});
