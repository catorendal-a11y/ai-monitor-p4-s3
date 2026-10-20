// GLITCH companion: a rogue terminal. A chamfered CRT monitor for a head, block-cursor eyes with a
// chromatic split, scanlines, bent rabbit-ear antennas, a vented chest and thin legs. Original
// artwork. The halo and ground-shadow ellipses match ORBIT's, so its frames crop to the same size.
//
//   node scripts/generate_glitch_svg.cjs        then        node scripts/generate_nova_assets.cjs
const fs = require('fs');
const path = require('path');
const directory = path.resolve(__dirname, '../assets/glitch');
fs.mkdirSync(directory, {recursive: true});
const poly = (points) => points.map(([x, y]) => `${x},${y}`).join(' ');
const MAGENTA = '#FF4FD8', GREEN = '#35D07F', AMBER = '#FFAA00', RED = '#FF5252', DIM = '#8D93A8', CYAN = '#4FE3FF';

function face(pose, c) {
  const block = (x, y, w, h, fill, opacity) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}"${opacity ? ` opacity="${opacity}"` : ''}/>`;
  // Both eyes with a chromatic split: a cyan copy to the left, a magenta copy to the right.
  const eyes = (y, h, color) => [174, 234].map((x) => block(x - 5, y, 22, h, CYAN, .45) + block(x + 5, y, 22, h, MAGENTA, .4) + block(x, y, 22, h, color)).join('');
  switch (pose) {
    case 'work': return `<ellipse cx="195" cy="104" rx="40" ry="34" fill="url(#eg)"/><ellipse cx="255" cy="104" rx="40" ry="34" fill="url(#eg)"/>` + eyes(84, 38, c) +
      block(174, 84, 22, 6, '#FFFFFF', .5) + block(234, 84, 22, 6, '#FFFFFF', .5);
    case 'done': return `<polyline points="180,108 200,128 250,84" fill="none" stroke="${CYAN}" stroke-opacity=".45" stroke-width="12" transform="translate(-5 0)"/>` +
      `<polyline points="180,108 200,128 250,84" fill="none" stroke="${MAGENTA}" stroke-opacity=".4" stroke-width="12" transform="translate(5 0)"/>` +
      `<polyline points="180,108 200,128 250,84" fill="none" stroke="${c}" stroke-width="12" stroke-linejoin="miter" stroke-linecap="square"/>`;
    case 'low': return eyes(112, 14, c);
    case 'critical': {   // torn slices, shifted sideways, and a crack across the glass
      const slice = (dx, y, h) => block(174 + dx, y, 22, h, c) + block(234 + dx, y, 22, h, c);
      return slice(-6, 84, 10) + slice(8, 96, 10) + slice(-4, 108, 10) + slice(10, 120, 8) +
        `<polyline points="150,60 176,84 168,100 196,124 188,150" fill="none" stroke="#FFFFFF" stroke-opacity=".4" stroke-width="2"/>`;
    }
    case 'sleep': return block(176, 108, 80, 3, DIM, .5) + block(160, 134, 10, 12, DIM, .45);
    default: return block(174, 104, 22, 4, c) + block(234, 104, 22, 4, c);   // blink
  }
}

for (const pose of ['work','done','low','critical','sleep','blink']) {
  const c = pose === 'done' ? GREEN : pose === 'low' ? AMBER : pose === 'critical' ? RED : pose === 'sleep' ? DIM : MAGENTA;
  const handY = pose === 'done' ? 176 : pose === 'low' || pose === 'sleep' ? 236 : 214;
  const claw = (x, y) => `<path d="M${x - 8} ${y - 8} L${x + 6} ${y} L${x - 8} ${y + 8}" fill="none" stroke="#9AA3BA" stroke-width="3" stroke-linejoin="miter"/>`;
  const caseShape = poly([[150,44],[280,44],[292,56],[292,150],[280,162],[150,162],[138,150],[138,56]]);
  const screen = poly([[154,58],[276,58],[280,62],[280,146],[276,150],[154,150],[150,146],[150,62]]);
  const torso = poly([[176,178],[254,178],[264,192],[260,236],[170,236],[166,192]]);
  const scan = Array.from({length: 15}, (_, i) => `<line x1="152" y1="${62 + i * 6}" x2="278" y2="${62 + i * 6}" stroke="#FFFFFF" stroke-opacity=".05"/>`).join('');
  const antenna = `<polyline points="190,44 170,20 150,12" fill="none" stroke="#8A93A8" stroke-width="3" stroke-linejoin="miter"/>` +
    `<polyline points="240,44 260,20 280,12" fill="none" stroke="#8A93A8" stroke-width="3" stroke-linejoin="miter"/>` +
    [[150,12],[280,12]].map(([x, y]) => `<polygon points="${x},${y - 6} ${x + 5},${y} ${x},${y + 6} ${x - 5},${y}" fill="${c}"/>`).join('');
  const vents = [0, 1, 2, 3].map((i) => `<rect x="186" y="${194 + i * 9}" width="${58 - i * 6}" height="3" fill="${pose === 'sleep' ? '#2A2F3B' : c}" opacity="${pose === 'sleep' ? 1 : .5 - i * .08}"/>`).join('');
  const arms = `<path d="M176 190 L150 ${(190 + handY) / 2 + 8} L142 ${handY}" fill="none" stroke="#5A6378" stroke-width="6" stroke-linejoin="miter"/>` +
    `<path d="M254 190 L280 ${(190 + handY) / 2 + 8} L288 ${handY}" fill="none" stroke="#5A6378" stroke-width="6" stroke-linejoin="miter"/>` +
    claw(142, handY) + `<g transform="translate(430 0) scale(-1 1)">${claw(142, handY)}</g>`;
  const legs = `<path d="M192 236 L186 254 M238 236 L244 254" stroke="#5A6378" stroke-width="6"/><rect x="172" y="252" width="28" height="6" fill="#3A4152"/><rect x="230" y="252" width="28" height="6" fill="#3A4152"/>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="430" height="284" viewBox="0 0 430 284"><title>GLITCH ${pose}</title>
<defs><linearGradient id="case" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#4A5164"/><stop offset=".5" stop-color="#262B38"/><stop offset="1" stop-color="#12151D"/></linearGradient>
<radialGradient id="halo"><stop stop-color="${c}" stop-opacity=".13"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></radialGradient>
<radialGradient id="eg"><stop stop-color="${c}" stop-opacity=".28"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></radialGradient></defs>
<ellipse cx="215" cy="145" rx="160" ry="130" fill="url(#halo)"/><ellipse cx="215" cy="264" rx="91" ry="11" fill="#050E18" fill-opacity=".55"/>
${legs}${arms}
<polygon points="${torso}" fill="url(#case)" stroke="#6A7388" stroke-width="1.5"/>${vents}
<rect x="205" y="162" width="20" height="16" fill="#1D212B" stroke="#6A7388"/>
${antenna}
<polygon points="${caseShape}" fill="url(#case)" stroke="#7A849B" stroke-width="1.5"/>
<polygon points="${screen}" fill="#03060A" stroke="${c}" stroke-opacity=".4" stroke-width="1.5"/>
${scan}${face(pose, c)}
<circle cx="278" cy="156" r="3" fill="${pose === 'sleep' ? '#2A2F3B' : c}"/>
</svg>`;
  fs.writeFileSync(path.join(directory, pose + '.svg'), svg + '\n');
}
console.log('Generated six GLITCH poses.');
