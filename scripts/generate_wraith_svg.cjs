// WRAITH companion: a hooded, hovering figure with no legs. A jagged cloak, a hood with a dark void
// and two narrow blade-shaped eyes, floating angular hands on dotted tethers, a rune on the chest.
// Original artwork. The halo and ground-shadow ellipses match ORBIT's, so its frames crop to the
// same size.
//
//   node scripts/generate_wraith_svg.cjs        then        node scripts/generate_nova_assets.cjs
const fs = require('fs');
const path = require('path');
const directory = path.resolve(__dirname, '../assets/wraith');
fs.mkdirSync(directory, {recursive: true});
const poly = (points) => points.map(([x, y]) => `${x},${y}`).join(' ');
const mirror = (points) => points.map(([x, y]) => [430 - x, y]);          // symmetric about x = 215
const VIOLET = '#B388FF', GREEN = '#35D07F', AMBER = '#FFAA00', RED = '#FF5252', DIM = '#8C86A8', CYAN = '#79D5E8';

function eyes(pose, c) {
  const slit = [[190,96],[212,104],[212,113],[190,105]];
  const glow = `<ellipse cx="204" cy="104" rx="26" ry="16" fill="url(#eg)"/><ellipse cx="226" cy="104" rx="26" ry="16" fill="url(#eg)"/>`;
  const draw = (pts, fill, opacity) => `<polygon points="${poly(pts)}" fill="${fill}"${opacity ? ` opacity="${opacity}"` : ''}/><polygon points="${poly(mirror(pts))}" fill="${fill}"${opacity ? ` opacity="${opacity}"` : ''}/>`;
  switch (pose) {
    case 'work': return glow + draw(slit, c) + draw([[194,100],[210,105],[210,109],[194,104]], '#FFFFFF', .85);
    case 'done': return glow + `<polyline points="192,110 204,96 216,110" fill="none" stroke="${c}" stroke-width="6" stroke-linejoin="miter" stroke-linecap="square"/>` +
                         `<polyline points="214,110 226,96 238,110" fill="none" stroke="${c}" stroke-width="6" stroke-linejoin="miter" stroke-linecap="square"/>`;
    case 'low': return draw([[198,103],[212,106],[212,110],[198,109]], c, .85);
    case 'critical': return `<g transform="translate(4 2)">${draw([[194,96],[212,106],[212,113],[194,104]], CYAN, .28)}</g>` + glow + draw([[194,96],[212,106],[212,113],[194,104]], c);
    case 'sleep': return draw([[198,105],[212,105],[212,108],[198,108]], DIM, .55);
    default: return draw([[196,105],[212,105],[212,108],[196,108]], c);   // blink
  }
}

function rune(pose, c) {
  const outline = `<polygon points="215,176 231,198 215,220 199,198" fill="#05030B" stroke="${c}" stroke-opacity="${pose === 'sleep' ? '.3' : '.85'}"/>`;
  switch (pose) {
    case 'done': return outline + `<polyline points="206,198 213,206 225,190" fill="none" stroke="${c}" stroke-width="4" stroke-linejoin="miter" stroke-linecap="square"/>`;
    case 'critical': return outline + `<path d="M207 190 L223 206 M223 190 L207 206" stroke="${c}" stroke-width="4"/>`;
    case 'low': return outline + `<polygon points="215,192 223,198 215,204 207,198" fill="${c}" opacity=".45"/>`;
    case 'sleep': return outline;
    default: return outline + `<polygon points="215,186 227,198 215,210 203,198" fill="${c}"/>`;
  }
}

for (const pose of ['work','done','low','critical','sleep','blink']) {
  const c = pose === 'done' ? GREEN : pose === 'low' ? AMBER : pose === 'critical' ? RED : pose === 'sleep' ? DIM : VIOLET;
  const handY = pose === 'done' ? 118 : pose === 'low' || pose === 'sleep' ? 206 : 170;
  const hand = (x, y) => `<polygon points="${poly([[x - 12, y - 12], [x + 8, y - 8], [x + 12, y + 10], [x - 2, y + 20], [x - 14, y + 8]])}" fill="#1C1533" stroke="${c}" stroke-opacity=".7" stroke-width="1.5"/>`;
  const cloak = poly([[215,24],[172,62],[152,118],[140,176],[128,238],[160,226],[180,252],[200,232],[215,248],[230,232],[250,252],[270,226],[302,238],[290,176],[278,118],[258,62]]);
  const hood = poly([[215,48],[188,80],[184,120],[198,146],[215,154],[232,146],[246,120],[242,80]]);
  const shards = pose === 'sleep' ? '' : [[104,112],[322,92],[304,214],[118,226]].map(([x, y]) =>
    `<polygon points="${x},${y - 7} ${x + 5},${y} ${x},${y + 7} ${x - 5},${y}" fill="${c}" opacity=".5"/>`).join('');
  const tether = `<path d="M176 148 L146 ${handY - 10} M254 148 L284 ${handY - 10}" stroke="${c}" stroke-opacity=".45" stroke-width="2" stroke-dasharray="2 5" fill="none"/>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="430" height="284" viewBox="0 0 430 284"><title>WRAITH ${pose}</title>
<defs><linearGradient id="cloak" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#2E2450"/><stop offset=".5" stop-color="#18112F"/><stop offset="1" stop-color="#090611"/></linearGradient>
<radialGradient id="halo"><stop stop-color="${c}" stop-opacity=".13"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></radialGradient>
<radialGradient id="eg"><stop stop-color="${c}" stop-opacity="${pose === 'sleep' ? '.05' : '.3'}"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></radialGradient></defs>
<ellipse cx="215" cy="145" rx="160" ry="130" fill="url(#halo)"/><ellipse cx="215" cy="264" rx="91" ry="11" fill="#050E18" fill-opacity=".55"/>
<ellipse cx="215" cy="258" rx="52" ry="6" fill="none" stroke="${c}" stroke-opacity=".3" stroke-width="2"/>
${shards}${tether}
${hand(134, handY)}<g transform="translate(430 0) scale(-1 1)">${hand(134, handY)}</g>
<polygon points="${cloak}" fill="url(#cloak)" stroke="${c}" stroke-opacity=".5" stroke-width="1.5"/>
<path d="M172 62 L215 24 L258 62" fill="none" stroke="${c}" stroke-opacity="${pose === 'sleep' ? '.12' : '.5'}" stroke-width="2"/>
<path d="M160 170 L152 118 M270 170 L278 118" stroke="#000" stroke-opacity=".25" stroke-width="3"/>
<polygon points="${hood}" fill="#040208" stroke="${c}" stroke-opacity=".35" stroke-width="1.5"/>
${eyes(pose, c)}
${rune(pose, c)}
<path d="M170 232 L158 226 M260 232 L272 226" stroke="${c}" stroke-opacity=".3" stroke-width="2"/>
</svg>`;
  fs.writeFileSync(path.join(directory, pose + '.svg'), svg + '\n');
}
console.log('Generated six WRAITH poses.');
