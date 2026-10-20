// Draws the NOVA robot poses as SVG (assets/nova/*.svg) from one parametric template, so the eight
// poses stay consistent. NOVA is a sentinel, not a mascot: a chamfered helmet, a dark visor with two
// slanted light slits instead of round eyes, a blade antenna, segmented arms with clamps and an LED
// strip on the chest. The glow and ground-shadow ellipses are kept exactly as before: the firmware
// crops frames to the union of every pose, so changing them would change image sizes and flash use.
//
//   node scripts/generate_nova_art.cjs        then        node scripts/generate_nova_assets.cjs
const fs = require('fs');
const path = require('path');
const out = path.resolve(__dirname, '..', 'assets', 'nova');

const GREEN = '#35D07F', AMBER = '#FFAA00', YELLOW = '#FFC857', RED = '#FF5252', DIM = '#7EADB9', CYAN = '#79D5E8';
const mirror = (points) => points.map(([x, y]) => [466 - x, y]);          // the robot is symmetric about x = 233
const poly = (points) => points.map(([x, y]) => `${x},${y}`).join(' ');

// Each pose: accent colour, eyes (polygons or strokes), what the chest screen shows, lit LEDs, arms.
const POSES = {
  work:      { accent: GREEN,  eyes: { slits: [[168,196],[220,204],[220,216],[168,211]] }, screen: 'prompt', leds: 3 },
  blink:     { accent: GREEN,  eyes: { lines: true },                                   screen: 'prompt', leds: 3 },
  attention: { accent: YELLOW, eyes: { slits: [[166,200],[172,196],[222,196],[222,214],[166,214]] }, screen: 'question', leds: 2 },
  error:     { accent: RED,    eyes: { slits: [[166,190],[222,208],[222,220],[166,206]], glitch: true }, screen: 'bang', leds: 1 },
  low:       { accent: AMBER,  eyes: { slits: [[170,203],[218,208],[218,214],[170,212]] }, screen: 'battery', leds: 1 },
  critical:  { accent: RED,    eyes: { slits: [[166,192],[222,210],[222,217],[166,201]], glitch: true }, screen: 'battery', leds: 1 },
  done:      { accent: GREEN,  eyes: { chevrons: true },                                 screen: 'check', leds: 5, armsUp: true },
  sleep:     { accent: DIM,    eyes: { sleepLines: true },                               screen: 'moon', leds: 0, dim: true },
};

function eyes(p) {
  const a = p.accent, e = p.eyes;
  let s = '';
  if (e.slits) {
    const left = e.slits, right = mirror(e.slits);
    if (e.glitch) s += `<polygon points="${poly(left)}" fill="${CYAN}" opacity=".24" transform="translate(5 2)"/><polygon points="${poly(right)}" fill="${CYAN}" opacity=".24" transform="translate(5 2)"/>`;
    s += `<ellipse cx="194" cy="206" rx="40" ry="26" fill="url(#eg)"/><ellipse cx="272" cy="206" rx="40" ry="26" fill="url(#eg)"/>`;
    s += `<polygon points="${poly(left)}" fill="${a}"/><polygon points="${poly(right)}" fill="${a}"/>`;
    // a thin bright core makes the slit read as a lit tube
    const shrink = (pts) => {
      const cx = pts.reduce((t, q) => t + q[0], 0) / pts.length, cy = pts.reduce((t, q) => t + q[1], 0) / pts.length;
      return pts.map(([x, y]) => [cx + (x - cx) * 0.8, cy + (y - cy) * 0.36]);
    };
    s += `<polygon points="${poly(shrink(left))}" fill="#F2FFF8" opacity=".85"/><polygon points="${poly(shrink(right))}" fill="#F2FFF8" opacity=".85"/>`;
  } else if (e.chevrons) {
    s += `<ellipse cx="194" cy="204" rx="40" ry="26" fill="url(#eg)"/><ellipse cx="272" cy="204" rx="40" ry="26" fill="url(#eg)"/>`;
    s += `<polyline points="172,214 194,194 216,214" fill="none" stroke="${a}" stroke-width="9" stroke-linejoin="miter" stroke-linecap="square"/>`;
    s += `<polyline points="250,214 272,194 294,214" fill="none" stroke="${a}" stroke-width="9" stroke-linejoin="miter" stroke-linecap="square"/>`;
  } else if (e.lines) {
    s += `<rect x="170" y="205" width="48" height="4" fill="${a}"/><rect x="248" y="205" width="48" height="4" fill="${a}"/>`;
  } else if (e.sleepLines) {
    s += `<rect x="172" y="205" width="44" height="3" fill="${DIM}" opacity=".7"/><rect x="250" y="205" width="44" height="3" fill="${DIM}" opacity=".7"/>`;
  }
  return s;
}

function screen(p) {
  const a = p.accent;
  const text = (glyph, size) => `<text x="233.5" y="${size > 24 ? 305 : 303}" font-family="Consolas, 'Courier New', monospace" font-size="${size}" font-weight="700" fill="${a}" text-anchor="middle">${glyph}</text>`;
  switch (p.screen) {
    case 'prompt': return text('&gt;_', 25);
    case 'question': return text('?', 27);
    case 'bang': return text('!', 27);
    case 'check': return `<polyline points="219,296 231,306 249,285" fill="none" stroke="${a}" stroke-width="5" stroke-linejoin="miter" stroke-linecap="square"/>`;
    case 'moon': return `<path d="M243 283 A14 14 0 1 0 248 307 A12 12 0 0 1 243 283" fill="${DIM}" opacity=".8"/>`;
    case 'battery': {
      const w = p.accent === RED ? 5 : 12;
      return `<rect x="205" y="286" width="48" height="22" fill="none" stroke="${a}" stroke-width="1.5"/><rect x="254" y="292" width="4" height="10" fill="${a}"/><rect x="210" y="291" width="${w}" height="12" fill="${a}"/>`;
    }
  }
  return '';
}

function arms(p) {
  const stroke = '#33464E';
  const clamp = (cx, cy) => {
    const pts = [[cx-9,cy-13],[cx+9,cy-13],[cx+13,cy-9],[cx+13,cy+9],[cx+9,cy+13],[cx-9,cy+13],[cx-13,cy+9],[cx-13,cy-9]];
    return `<polygon points="${poly(pts)}" fill="#3E555E" stroke="#25363D" stroke-width="2"/><line x1="${cx-6}" y1="${cy}" x2="${cx+6}" y2="${cy}" stroke="${p.accent}" stroke-opacity=".7" stroke-width="2"/>`;
  };
  const hex = (cx, cy) => {
    const pts = [0, 60, 120, 180, 240, 300].map((deg) => [cx + 12 * Math.cos(deg * Math.PI / 180), cy + 12 * Math.sin(deg * Math.PI / 180)]);
    return `<polygon points="${poly(pts)}" fill="#2B3D45" stroke="#4A636D" stroke-width="1.5"/>`;
  };
  let d, left, right;
  if (p.armsUp) { d = 'M172 291 L139 270 L113 236 M294 291 L330 267 L357 232'; left = [110, 233]; right = [360, 229]; }
  else { d = 'M170 288 L143 304 L128 319 M295 288 L325 304 L337 318'; left = [125, 321]; right = [340, 321]; }
  return `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="13" stroke-linejoin="miter" stroke-linecap="butt"/>` +
         clamp(...left) + clamp(...right) + hex(p.armsUp ? 172 : 170, p.armsUp ? 291 : 288) + hex(p.armsUp ? 294 : 295, p.armsUp ? 291 : 288);
}

function leds(p) {
  let s = '';
  for (let i = 0; i < 5; i++) {
    const lit = i < p.leds;
    s += `<rect x="${171 + i * 26}" y="340" width="20" height="8" fill="${lit ? p.accent : '#1B2B31'}" ${lit ? '' : 'stroke="#2A3D45" stroke-width="1"'}/>`;
    if (lit) s += `<rect x="${171 + i * 26}" y="340" width="20" height="3" fill="#FFFFFF" opacity=".28"/>`;
  }
  return s;
}

function robot(name, p) {
  const a = p.accent;
  const hole = [[166,166],[300,166],[318,184],[318,235],[300,251],[166,251],[148,235],[148,184]];
  const head = [[154,150],[312,150],[334,172],[334,247],[312,269],[154,269],[132,247],[132,172]];
  const body = [[165,263],[302,263],[302,318],[284,335],[183,335],[165,318]];
  const plate = [[163,312],[305,312],[313,320],[313,352],[305,360],[163,360],[155,352],[155,320]];
  const footL = [[164,342],[214,342],[223,350],[223,364],[164,364]];
  const footR = [[304,342],[254,342],[245,350],[245,364],[304,364]];
  const diamond = [[233,110],[245,122],[233,134],[221,122]];
  return `<svg xmlns="http://www.w3.org/2000/svg" width="430" height="284" viewBox="0 0 430 284"><title>NOVA ${name}</title><defs>
<linearGradient id="shell" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#3C515A"/><stop offset=".45" stop-color="#1F3037"/><stop offset="1" stop-color="#0F1B20"/></linearGradient>
<linearGradient id="visor" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#0F1D22"/><stop offset="1" stop-color="#04090C"/></linearGradient>
<radialGradient id="glow"><stop stop-color="${a}" stop-opacity=".07"/><stop offset=".55" stop-color="${a}" stop-opacity=".03"/><stop offset="1" stop-color="${a}" stop-opacity="0"/></radialGradient>
<radialGradient id="eg"><stop stop-color="${a}" stop-opacity="${p.dim ? '.05' : '.22'}"/><stop offset="1" stop-color="${a}" stop-opacity="0"/></radialGradient>
<linearGradient id="ant" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#F2FFF8"/><stop offset=".5" stop-color="${a}"/><stop offset="1" stop-color="${a}" stop-opacity=".55"/></linearGradient>
<clipPath id="vc"><polygon points="${poly(hole)}"/></clipPath>
</defs><g font-family="Segoe UI, Arial, sans-serif" transform="translate(-20 -90)"><ellipse cx="233" cy="240" rx="190" ry="150" fill="url(#glow)"/><ellipse cx="233" cy="366" rx="118" ry="14" fill="#0B161B"/><ellipse cx="233" cy="364" rx="95" ry="11" fill="#071014"/>
${arms(p)}
<rect x="183" y="318" width="16" height="26" fill="#2B3D45"/><rect x="267" y="318" width="16" height="26" fill="#2B3D45"/>
<polygon points="${poly(footL)}" fill="#243740" stroke="#4A636D" stroke-width="1.5"/><polygon points="${poly(footR)}" fill="#243740" stroke="#4A636D" stroke-width="1.5"/>
<polygon points="${poly(body)}" fill="url(#shell)" stroke="#4A636D" stroke-width="1.5"/>
<rect x="185" y="278" width="97" height="35" fill="#070F13" stroke="${a}" stroke-opacity=".4"/>
${screen(p)}
<polygon points="${poly(plate)}" fill="#0C171C" stroke="#4A636D" stroke-width="1.5"/>
<text x="234" y="331" font-size="11" font-weight="700" letter-spacing="7" fill="#5F7C87" text-anchor="middle">NOVA</text>
${leds(p)}
<line x1="233" y1="142" x2="233" y2="125" stroke="#5B7783" stroke-width="4"/>
<circle cx="233" cy="122" r="26" fill="none" stroke="${a}" stroke-opacity="${p.dim ? '.05' : '.12'}"/>
<polygon points="${poly(diamond)}" fill="url(#ant)" stroke="${a}" stroke-opacity=".6"/>
<polygon points="200,150 266,150 258,141 208,141" fill="#243740" stroke="#4A636D" stroke-width="1.5"/>
<rect x="124" y="190" width="8" height="42" fill="#1D2F36" stroke="#4A636D"/><rect x="334" y="190" width="8" height="42" fill="#1D2F36" stroke="#4A636D"/>
<polygon points="${poly(head)}" fill="url(#shell)" stroke="#5B7783" stroke-width="1.5"/>
<path d="M134 174 L155 152 L230 152" fill="none" stroke="${a}" stroke-opacity="${p.dim ? '.12' : '.4'}" stroke-width="2"/>
<polygon points="${poly(hole)}" fill="url(#visor)" stroke="${a}" stroke-opacity=".3" stroke-width="1.5"/>
<polygon points="196,166 244,166 200,251 160,251" fill="#BFE8D2" opacity=".04" clip-path="url(#vc)"/>
<polygon points="258,166 274,166 230,251 218,251" fill="#BFE8D2" opacity=".025" clip-path="url(#vc)"/>
<line x1="172" y1="238" x2="294" y2="238" stroke="${a}" stroke-opacity=".16"/><line x1="233" y1="235" x2="233" y2="241" stroke="${a}" stroke-opacity=".3"/>
${eyes(p)}
</g>
</svg>
`;
}

for (const [name, pose] of Object.entries(POSES)) {
  fs.writeFileSync(path.join(out, name + '.svg'), robot(name, pose));
}
console.log('Wrote ' + Object.keys(POSES).length + ' NOVA poses to assets/nova/');
