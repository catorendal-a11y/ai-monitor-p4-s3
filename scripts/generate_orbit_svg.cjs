// Original ORBIT geometry: a hovering capsule companion with six expressions.
const fs = require('fs');
const path = require('path');
const directory = path.resolve(__dirname, '../assets/orbit');
fs.mkdirSync(directory, {recursive:true});
for (const pose of ['work','done','low','critical','sleep','blink']) {
  const color = pose === 'critical' ? '#FF6572' : pose === 'low' ? '#FFBE6E' : '#67D5FF';
  const resting = pose === 'sleep' || pose === 'blink';
  const eyes = resting ? '<path d="M174 103h23m36 0h23" stroke="'+color+'" stroke-width="6" stroke-linecap="round"/>' :
    pose === 'done' ? '<path d="M173 104q12-20 24 0m36 0q12-20 24 0" fill="none" stroke="'+color+'" stroke-width="6" stroke-linecap="round"/>' :
    '<ellipse cx="185" cy="100" rx="12" ry="'+(pose==='critical'?14:pose==='low'?9:16)+'" fill="'+color+'"/><ellipse cx="245" cy="100" rx="12" ry="'+(pose==='critical'?14:pose==='low'?9:16)+'" fill="'+color+'"/><circle cx="181" cy="94" r="3" fill="#F4FCFF"/><circle cx="241" cy="94" r="3" fill="#F4FCFF"/>';
  const mouth = pose === 'critical' ? '<ellipse cx="215" cy="132" rx="8" ry="10" fill="'+color+'"/>' :
    pose === 'low' ? '<path d="M202 135q13-10 26 0" stroke="'+color+'" stroke-width="3" fill="none"/>' :
    resting ? '<path d="M209 132h12" stroke="'+color+'" stroke-width="3" stroke-linecap="round"/>' :
    '<path d="M200 130q15 14 30 0" stroke="'+color+'" stroke-width="3.5" fill="none" stroke-linecap="round"/>';
  const handY = pose === 'done' ? 151 : pose === 'low' || resting ? 220 : 190;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="430" height="284" viewBox="0 0 430 284"><title>ORBIT ${pose}</title>
<defs><linearGradient id="shell" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#A8C9DD"/><stop offset=".45" stop-color="#54758E"/><stop offset="1" stop-color="#263F55"/></linearGradient>
<linearGradient id="face" x2="0" y2="1"><stop stop-color="#142B3E"/><stop offset="1" stop-color="#060F1C"/></linearGradient>
<radialGradient id="halo"><stop stop-color="${color}" stop-opacity=".12"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient>
<radialGradient id="beam"><stop stop-color="${color}" stop-opacity=".3"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient></defs>
<ellipse cx="215" cy="145" rx="160" ry="130" fill="url(#halo)"/><ellipse cx="215" cy="264" rx="91" ry="11" fill="#050E18" fill-opacity=".55"/>
<path d="M193 235l-17 25h78l-17-25" fill="url(#beam)"/><ellipse cx="215" cy="260" rx="62" ry="8" fill="none" stroke="${color}" stroke-opacity=".35" stroke-width="2"/>
<path d="M174 190L139 ${handY}m117 0L291 ${handY}" stroke="#688DA8" stroke-width="13" stroke-linecap="round"/>
<circle cx="136" cy="${handY}" r="13" fill="url(#shell)" stroke="#B2D0E3"/><circle cx="294" cy="${handY}" r="13" fill="url(#shell)" stroke="#B2D0E3"/>
<ellipse cx="215" cy="206" rx="51" ry="42" fill="url(#shell)" stroke="#8CABC0" stroke-width="2"/>
<rect x="185" y="188" width="60" height="34" rx="15" fill="#0B1B2A" stroke="#A5C3D6"/>
<path d="M215 194v21m-11-10h22" stroke="${color}" stroke-width="3" stroke-linecap="round"/><circle cx="215" cy="205" r="5" fill="${color}"/>
<path d="M188 232q27 15 54 0" stroke="${color}" stroke-width="3" fill="none" opacity=".7"/>
<ellipse cx="215" cy="105" rx="103" ry="29" transform="rotate(-18 215 105)" fill="none" stroke="#8EAFC7" stroke-opacity=".5" stroke-width="3"/>
<ellipse cx="215" cy="103" rx="75" ry="70" fill="url(#shell)" stroke="#B3CDDE" stroke-width="2"/>
<path d="M159 77q12-27 43-31" stroke="#E0F2FC" stroke-width="3" fill="none" opacity=".5" stroke-linecap="round"/>
<rect x="154" y="72" width="122" height="78" rx="31" fill="url(#face)" stroke="#A3C8DF" stroke-opacity=".45"/>
<path d="M166 78h49l-32 66h-20" fill="#CEE8FA" fill-opacity=".04"/>
${eyes}${mouth}<circle cx="287" cy="70" r="7" fill="${color}" stroke="#E5F8FF" stroke-width="1.5"/>
<path d="M272 154q-20 8-42 12" stroke="${color}" stroke-width="2" opacity=".7" fill="none"/>
<text x="215" y="239" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-size="10" font-weight="600" fill="#F0F9FF" letter-spacing="2">ORBIT</text></svg>`;
  fs.writeFileSync(path.join(directory, pose+'.svg'),svg+'\n');
}
console.log('Generated six original ORBIT SVG poses.');
