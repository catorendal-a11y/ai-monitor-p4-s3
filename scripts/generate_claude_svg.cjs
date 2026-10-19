// CLAUDE companion: the Claude Code banner critter as pixel art, with six expressions.
// The banner draws it with quadrant block characters, so one source pixel is half a
// terminal cell: twice as tall as wide. Each source pixel here is U wide and 2U tall.
const fs = require('fs');
const path = require('path');
const directory = path.resolve(__dirname, '../assets/claude');
fs.mkdirSync(directory, {recursive:true});

const U = 18;                 // one square sub-pixel; a source pixel is U x 2U
const X0 = 53, Y0 = 40;       // 18 columns x 12 sub-rows, centered on the 430 x 284 canvas
const BODY = '#D77757', SHADE = '#B95F42', EYE = '#141414';

// Source rows from the banner (columns 0..17); every row is two sub-rows tall.
const base = [
  [3,4,5,6,7,8,9,10,11,12,13,14],
  [3,4,6,7,8,9,10,11,13,14],
  [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16],
  [3,4,5,6,7,8,9,10,11,12,13,14],
  [4,6,11,13],
];

function rect(col, sub, w, h, fill, opacity) {
  return `<rect x="${X0 + col * U}" y="${Y0 + sub * U}" width="${w * U}" height="${h * U}" fill="${fill}"` +
    (opacity ? ` opacity="${opacity}"` : '') + ' shape-rendering="crispEdges"/>';
}

for (const pose of ['work','done','low','critical','sleep','blink']) {
  const glow = pose === 'critical' ? '#FF6572' : pose === 'low' ? '#FFBE6E' : BODY;
  const rows = base.map(row => row.slice());
  rows[1].push(5, 12);  // fill the banner's eye holes; each pose draws its own eyes below
  const extra = [];
  // Arms live on source row 2 at columns 1-2 and 15-16.
  const armless = row => row.filter(col => col > 2 && col < 15);
  if (pose === 'done' || pose === 'critical') {
    rows[2] = armless(rows[2]);                       // arms raised beside the head
    extra.push(rect(2, 2, 1, 2, BODY), rect(1, 0, 1, 2, BODY), rect(15, 2, 1, 2, BODY), rect(16, 0, 1, 2, BODY));
  } else if (pose === 'low') {
    rows[2] = armless(rows[2]);                       // arms hanging low
    extra.push(rect(1, 6, 2, 2, BODY), rect(15, 6, 2, 2, BODY));
  } else if (pose === 'sleep') {
    rows[2] = armless(rows[2]);                       // arms tucked in
  }
  const body = [];
  rows.forEach((row, index) => row.forEach(col => body.push(rect(col, index * 2, 1, 2, BODY))));
  // A one-sub-pixel shade on the lower body edge keeps the flat banner look readable on dark themes.
  body.push(rect(3, 7, 12, 1, SHADE, '.55'));
  // Eye holes are column 5 and 12 of source row 1 (sub-rows 2-3).
  const eyes = [];
  for (const col of [5, 12]) {
    if (pose === 'blink' || pose === 'sleep') eyes.push(rect(col, 3.5, 1, 0.5, EYE));                // closed
    else if (pose === 'low') eyes.push(rect(col, 3, 1, 1, EYE));                                     // tired, half open
    else if (pose === 'done') eyes.push(rect(col, 2, 1, 1, EYE));                                    // squint smile
    else eyes.push(rect(col, 2, 1, 2, EYE));                                                         // open
  }
  if (pose === 'critical') {
    // Alarm mark above the head.
    extra.push(rect(8.5, -2, 1, 2, '#FF6572'), rect(8.5, 0.5, 1, 0.6, '#FF6572'));
  }
  if (pose === 'done') {
    // Two small celebration sparks.
    for (const [cx, cy] of [[0, -1.5], [17, -1.5]]) {
      extra.push(rect(cx, cy - 0.5, 0.5, 1.5, '#FFD6C2'), rect(cx - 0.5, cy, 1.5, 0.5, '#FFD6C2'));
    }
  }
  const zs = pose === 'sleep' ?
    `<g fill="#E9D9C6" shape-rendering="crispEdges"><path opacity=".55" d="M${X0+15*U} ${Y0-0.2*U}h${U*0.9}v${U*0.3}l-${U*0.6} ${U*0.6}h${U*0.6}v${U*0.3}h-${U*0.9}v-${U*0.3}l${U*0.6}-${U*0.6}h-${U*0.6}z"/>` +
    `<path opacity=".8" d="M${X0+16.4*U} ${Y0-1.9*U}h${U*1.3}v${U*0.4}l-${U*0.9} ${U*0.9}h${U*0.9}v${U*0.4}h-${U*1.3}v-${U*0.4}l${U*0.9}-${U*0.9}h-${U*0.9}z"/></g>` : '';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="430" height="284" viewBox="0 0 430 284"><title>CLAUDE ${pose}</title>
<defs><radialGradient id="halo"><stop stop-color="${glow}" stop-opacity="${pose === 'sleep' ? '.07' : '.16'}"/><stop offset="1" stop-color="${glow}" stop-opacity="0"/></radialGradient></defs>
<ellipse cx="215" cy="140" rx="170" ry="130" fill="url(#halo)"/><ellipse cx="215" cy="${Y0 + 10 * U + 22}" rx="120" ry="11" fill="#0B0705" fill-opacity=".55"/>
${body.join('')}${eyes.join('')}${extra.join('')}${zs}</svg>`;
  fs.writeFileSync(path.join(directory, pose + '.svg'), svg + '\n');
}
console.log('Generated six CLAUDE pixel-art poses.');
