// Render the existing, approved NOVA vectors for the native desktop app.
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const root = path.resolve(__dirname, '..');
const target = path.join(root, 'assets', 'desktop');
(async () => {
  fs.mkdirSync(target, {recursive: true});
  const sessionOnly = process.argv.includes('--session-only');
  for (const pose of (sessionOnly ? ['attention', 'error'] : ['done', 'work', 'attention', 'error'])) {
    await sharp(path.join(root, 'assets', 'nova', pose + '.svg')).resize(430, 284)
      .png().toFile(path.join(target, 'nova-' + pose + '.png'));
  }
  if (sessionOnly) { console.log('Rendered session-state poses from original NOVA vectors.'); return; }
  const nova = fs.readFileSync(path.join(root, 'assets', 'nova', 'work.svg')).toString('base64');
  const icon = `<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" rx="48" fill="#101d24"/><circle cx="128" cy="128" r="112" fill="#17352c"/><image x="-32" y="23" width="320" height="211" href="data:image/svg+xml;base64,${nova}"/></svg>`;
  await sharp(Buffer.from(icon)).png().toFile(path.join(target, 'nova-icon.png'));
  await sharp(Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect x="1" y="1" width="18" height="18" rx="4" fill="#35c987"/><path d="M5 10l3 3 7-7" fill="none" stroke="#071c12" stroke-width="2.5"/></svg>')).png().toFile(path.join(target, 'checked.png'));
  console.log('Generated desktop NOVA images from existing vector artwork.');
})().catch(error => {console.error(error.message); process.exit(1);});
