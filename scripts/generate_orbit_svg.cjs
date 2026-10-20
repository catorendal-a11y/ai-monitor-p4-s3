// ORBIT: a hovering sensor drone with six expressions. A faceted hull, one wide scanner lens instead
// of eyes, a dashed orbit ring with a satellite, thin segmented arms with claws and a chest core.
// The halo and ground-shadow ellipses stay exactly as before: the firmware crops frames to the union
// of every pose, so changing them would change image sizes and flash use.
//
//   node scripts/generate_orbit_svg.cjs        then        node scripts/generate_nova_assets.cjs
const fs = require('fs');
const path = require('path');
const directory = path.resolve(__dirname, '../assets/orbit');
fs.mkdirSync(directory, {recursive:true});
const poly = (points) => points.map(([x, y]) => `${x},${y}`).join(' ');
const CYAN = '#67D5FF', AMBER = '#FFBE6E', RED = '#FF6572', DIM = '#7EADB9', GHOST = '#8EE8FF';

function lens(pose, color) {
  const glowLens = `<ellipse cx="215" cy="104" rx="70" ry="20" fill="url(#beam)"/>`;
  switch (pose) {
    case 'work':
      return glowLens + `<polygon points="${poly([[170,99],[260,99],[267,105],[260,111],[170,111],[163,105]])}" fill="${color}"/>` +
        `<polygon points="${poly([[170,102],[260,102],[262,105],[260,108],[170,108],[168,105]])}" fill="#F2FDFF" opacity=".8"/>` +
        `<polygon points="${poly([[204,97],[228,97],[233,105],[228,113],[204,113],[199,105]])}" fill="#FFFFFF" opacity=".95"/>`;
    case 'done': {   // a level meter that settled high
      const bars = [[176,6],[191,12],[206,18],[221,24],[236,18],[251,12]];
      return glowLens + bars.map(([x, h]) => `<rect x="${x}" y="${105 - h}" width="9" height="${h * 2}" fill="${color}"/>`).join('');
    }
    case 'low':
      return `<polygon points="${poly([[188,101],[242,101],[247,105],[242,109],[188,109],[183,105]])}" fill="${color}" opacity=".85"/>` +
        `<rect x="205" y="116" width="20" height="3" fill="${color}" opacity=".6"/>`;
    case 'critical': {   // a broken, jittering scan line with a cyan ghost
      const pieces = [[168,99,48],[222,105,26],[254,97,18]];
      return `<g opacity=".3" transform="translate(5 2)">${pieces.map(([x, y, w]) => `<rect x="${x}" y="${y}" width="${w}" height="9" fill="${GHOST}"/>`).join('')}</g>` +
        pieces.map(([x, y, w]) => `<rect x="${x}" y="${y}" width="${w}" height="9" fill="${color}"/>`).join('');
    }
    case 'sleep':
      return `<rect x="172" y="104" width="86" height="3" fill="${DIM}" opacity=".5"/>`;
    default:   // blink
      return `<rect x="172" y="103" width="86" height="4" fill="${color}"/>`;
  }
}

function core(pose, color) {
  const fill = pose === 'low' ? `<polygon points="215,190 224,200 215,210 206,200" fill="${color}" opacity=".35"/>` :
               pose === 'sleep' ? '' : `<polygon points="215,186 228,200 215,214 202,200" fill="${color}"/>`;
  return `<polygon points="215,178 231,200 215,222 199,200" fill="#06111A" stroke="${color}" stroke-opacity="${pose === 'sleep' ? '.3' : '.8'}"/>${fill}`;
}

for (const pose of ['work','done','low','critical','sleep','blink']) {
  const color = pose === 'critical' ? RED : pose === 'low' ? AMBER : pose === 'sleep' ? DIM : CYAN;
  const handY = pose === 'done' ? 150 : pose === 'low' || pose === 'sleep' ? 222 : 196;
  const handX = pose === 'done' ? 128 : 134;
  const claw = (x, y) => `<polygon points="${poly([[x - 12, y - 10], [x + 8, y], [x - 12, y + 10], [x - 5, y]])}" fill="#40607A" stroke="#8FB2C8" stroke-width="1.5"/>`;
  const armL = `M176 186 L${handX + 14} ${(186 + handY) / 2 + 6} L${handX + 4} ${handY}`;
  const armR = `M254 186 L${430 - handX - 14} ${(186 + handY) / 2 + 6} L${430 - handX - 4} ${handY}`;
  const hull = poly([[160,62],[270,62],[296,104],[270,146],[160,146],[134,104]]);
  const visor = poly([[168,82],[262,82],[278,104],[262,126],[168,126],[152,104]]);
  const body = poly([[176,158],[254,158],[268,198],[252,240],[178,240],[162,198]]);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="430" height="284" viewBox="0 0 430 284"><title>ORBIT ${pose}</title>
<defs><linearGradient id="shell" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#7396AD"/><stop offset=".5" stop-color="#34506A"/><stop offset="1" stop-color="#14263A"/></linearGradient>
<linearGradient id="face" x2="0" y2="1"><stop stop-color="#0D1D2B"/><stop offset="1" stop-color="#03080F"/></linearGradient>
<radialGradient id="halo"><stop stop-color="${color}" stop-opacity=".12"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient>
<radialGradient id="beam"><stop stop-color="${color}" stop-opacity="${pose === 'sleep' ? '.08' : '.3'}"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></radialGradient></defs>
<ellipse cx="215" cy="145" rx="160" ry="130" fill="url(#halo)"/><ellipse cx="215" cy="264" rx="91" ry="11" fill="#050E18" fill-opacity=".55"/>
<path d="M193 240l-17 20h78l-17-20" fill="url(#beam)"/><ellipse cx="215" cy="260" rx="62" ry="8" fill="none" stroke="${color}" stroke-opacity=".35" stroke-width="2"/>
<path d="${armL} ${armR}" fill="none" stroke="#4C6B82" stroke-width="8" stroke-linejoin="miter"/>
${claw(handX, handY)}<g transform="translate(430 0) scale(-1 1)">${claw(handX, handY)}</g>
<polygon points="${body}" fill="url(#shell)" stroke="#8FB2C8" stroke-width="1.5"/>
${core(pose, color)}
<path d="M184 228h26M220 228h26" stroke="${color}" stroke-opacity=".5" stroke-width="2"/>
<text x="215" y="236" text-anchor="middle" font-family="Segoe UI,Arial,sans-serif" font-size="9" font-weight="700" fill="#D6EAF7" letter-spacing="4" opacity=".75">ORBIT</text>
<ellipse cx="215" cy="105" rx="108" ry="30" transform="rotate(-18 215 105)" fill="none" stroke="#8EAFC7" stroke-opacity=".5" stroke-width="2.5" stroke-dasharray="14 9"/>
<line x1="215" y1="62" x2="215" y2="46" stroke="#8FB2C8" stroke-width="3"/><polygon points="215,38 221,45 215,52 209,45" fill="${color}"/>
<polygon points="${hull}" fill="url(#shell)" stroke="#A9C9DC" stroke-width="2"/>
<path d="M140 98 L162 66 L228 66" fill="none" stroke="${color}" stroke-opacity="${pose === 'sleep' ? '.12' : '.45'}" stroke-width="2"/>
<polygon points="${visor}" fill="url(#face)" stroke="${color}" stroke-opacity=".4" stroke-width="1.5"/>
<polygon points="176,82 224,82 192,126 168,126" fill="#CEE8FA" opacity=".04"/>
${lens(pose, color)}
<polygon points="287,66 294,73 287,80 280,73" fill="${color}" stroke="#E5F8FF" stroke-width="1"/>
</svg>`;
  fs.writeFileSync(path.join(directory, pose+'.svg'),svg+'\n');
}
console.log('Generated six ORBIT drone poses.');
