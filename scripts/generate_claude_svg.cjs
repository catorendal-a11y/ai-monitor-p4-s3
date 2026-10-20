// CLAUDE companion: the Claude Code banner critter as pixel art, armoured. The silhouette and the
// orange stay (it is still that critter); the face becomes a dark visor with lit slits instead of
// two black dots, it gets short horns, a vent on the chest and a belt line, and the cute extras
// (sparks, sleeping letters) are gone. The banner draws the critter with quadrant block characters,
// so one source pixel is half a terminal cell: twice as tall as wide. Each source pixel here is U
// wide and 2U tall. The halo and ground-shadow ellipses stay exactly as before: the firmware crops
// frames to the union of every pose, so changing them would change image sizes and flash use.
//
//   node scripts/generate_claude_svg.cjs        then        node scripts/generate_nova_assets.cjs
const fs = require('fs');
const path = require('path');
const directory = path.resolve(__dirname, '../assets/claude');
fs.mkdirSync(directory, {recursive:true});

const U = 18;                 // one square sub-pixel; a source pixel is U x 2U
const X0 = 53, Y0 = 40;       // 18 columns x 12 sub-rows, centered on the 430 x 284 canvas
const BODY = '#D77757', SHADE = '#B95F42', DARK = '#120D0B', PLATE = '#3A241C';
const HOT = '#FFF1E6', AMBER = '#FFC857', RED = '#FF6572', DIM = '#A08E82';

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

// Lit eye cells as [column, sub-row] for the left eye; the right eye mirrors around the centre (17 - column).
const EYES = {
  work:     { cells: [[5,2],[6,2],[7,3]], color: HOT },       // a slit sloping toward the centre
  low:      { cells: [[5,3],[6,3]], color: AMBER },
  critical: { cells: [[5,2],[6,3],[7,3]], color: RED },
  done:     { cells: [[5,3],[6,2],[7,3]], color: HOT },       // a raised chevron
  sleep:    { cells: [[5,3],[6,3]], color: DIM, opacity: .6 },
  blink:    { cells: [[5,3],[6,3]], color: HOT },
};

for (const pose of ['work','done','low','critical','sleep','blink']) {
  const glow = pose === 'critical' ? '#FF6572' : pose === 'low' ? '#FFBE6E' : BODY;
  const rows = base.map(row => row.slice());
  rows[1].push(5, 12);  // fill the banner's eye holes; the visor is drawn over them below
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
  // A shade on the lower body edge and a darker belt line keep the flat banner look readable on dark themes.
  body.push(rect(3, 7, 12, 1, SHADE, '.55'), rect(3, 6, 12, 1, PLATE, '.55'));
  // Horns: two short spikes on top of the head.
  body.push(rect(3, -1, 1, 1, BODY), rect(14, -1, 1, 1, BODY), rect(3, -2, 1, 1, SHADE), rect(14, -2, 1, 1, SHADE));
  // The visor: a dark band across the face with the lit slits inside it.
  body.push(rect(4, 2, 10, 2, DARK));
  const eye = EYES[pose];
  const lit = [];
  for (const [col, sub] of eye.cells) {
    lit.push(rect(col, sub, 1, 1, eye.color, eye.opacity), rect(17 - col, sub, 1, 1, eye.color, eye.opacity));
  }
  // The chest vent, with two lit cells when the critter is awake.
  lit.push(rect(7, 5, 4, 1, DARK));
  if (pose !== 'sleep') lit.push(rect(8, 5, 1, 1, eye.color, '.9'), rect(9, 5, 1, 1, eye.color, '.9'));
  if (pose === 'critical') {
    // Alarm mark above the head.
    extra.push(rect(8.5, -2, 1, 2, RED), rect(8.5, 0.5, 1, 0.6, RED));
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="430" height="284" viewBox="0 0 430 284"><title>CLAUDE ${pose}</title>
<defs><radialGradient id="halo"><stop stop-color="${glow}" stop-opacity="${pose === 'sleep' ? '.07' : '.16'}"/><stop offset="1" stop-color="${glow}" stop-opacity="0"/></radialGradient></defs>
<ellipse cx="215" cy="140" rx="170" ry="130" fill="url(#halo)"/><ellipse cx="215" cy="${Y0 + 10 * U + 22}" rx="120" ry="11" fill="#0B0705" fill-opacity=".55"/>
${body.join('')}${lit.join('')}${extra.join('')}</svg>`;
  fs.writeFileSync(path.join(directory, pose + '.svg'), svg + '\n');
}
console.log('Generated six CLAUDE pixel-art poses.');
