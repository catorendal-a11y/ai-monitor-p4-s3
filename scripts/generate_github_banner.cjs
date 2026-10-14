// Native SVG layout using existing, synthetic actual-UI screenshots.
// Requires Node.js and sharp. Run: node scripts/generate_github_banner.cjs
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const root = path.resolve(__dirname, '..');
const destination = path.join(root, 'docs/media');
const picture = name => 'data:image/png;base64,' + fs.readFileSync(path.join(root, name)).toString('base64');
const orbit = picture('docs/ui/orbit-ocean.png');
const nova = picture('docs/nova-preview.png');
const svg = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1280" height="640" viewBox="0 0 1280 640">
<title>AI Monitor — ESP32-P4 and experimental ESP32-S3 desk companion</title>
<desc>NOVA and ORBIT actual UI previews with synthetic data. Local token activity, readable provider quotas, USB touchscreen and a Windows installer.</desc>
<defs>
 <linearGradient id="bg" x2="1" y2="1"><stop stop-color="#08251d"/><stop offset="1" stop-color="#071420"/></linearGradient>
 <radialGradient id="glow"><stop stop-color="#0e8591" stop-opacity=".23"/><stop offset="1" stop-color="#0e8591" stop-opacity="0"/></radialGradient>
 <pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#c2ffde" opacity=".08"/></pattern>
 <filter id="shadow" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dy="12" stdDeviation="16" flood-color="#000" flood-opacity=".5"/></filter>
 <clipPath id="orbitClip"><rect x="640" y="137" width="570" height="342" rx="10"/></clipPath>
 <clipPath id="novaClip"><rect x="532" y="354" width="364" height="218.4" rx="9"/></clipPath>
</defs>
<rect width="1280" height="640" fill="url(#bg)"/>
<rect width="1280" height="640" fill="url(#dots)"/>
<ellipse cx="1030" cy="300" rx="510" ry="450" fill="url(#glow)"/>
<g font-family="Segoe UI,Arial,sans-serif">
 <rect x="64" y="72" width="6" height="20" rx="3" fill="#96f7ba"/>
 <text x="84" y="89" font-size="15" font-weight="700" letter-spacing="2" fill="#9af3bb">OPEN SOURCE · ESP32 · LVGL</text>
 <text x="64" y="167" font-size="54" font-weight="800" letter-spacing="-1" fill="#f1fff7">AI MONITOR</text>
 <text x="64" y="235" font-size="34" font-weight="600" fill="#d4eee5">A desk companion</text>
 <text x="64" y="279" font-size="34" font-weight="600" fill="#d4eee5">for your AI tools.</text>
 <g fill="#0c3129" stroke="#2a564c">
  <rect x="64" y="320" width="94" height="36" rx="18"/><rect x="168" y="320" width="94" height="36" rx="18"/>
  <rect x="272" y="320" width="139" height="36" rx="18"/><rect x="64" y="367" width="130" height="36" rx="18"/>
 </g>
 <g font-size="15" font-weight="600" fill="#d7eee6" text-anchor="middle">
  <text x="111" y="343">Codex</text><text x="215" y="343">ZCode</text>
  <text x="341.5" y="343">Claude Code</text><text x="129" y="390">Gemini CLI</text>
 </g>
 <text x="64" y="453" font-size="20" fill="#f1fff7">Local token activity. Usage at a glance.</text>
 <text x="64" y="486" font-size="18" fill="#90b7aa">Connect by USB. Choose your providers.</text>
 <text x="64" y="542" font-size="16" font-weight="600" fill="#9af3bb">2 robots · 4 themes · Windows installer</text>
 <text x="64" y="603" font-size="14" fill="#87a89e">github.com/catorendal-a11y/ai-monitor-p4-s3</text>
</g>
<rect x="628" y="125" width="594" height="366" rx="21" fill="#03111b" stroke="#386272" stroke-width="2" filter="url(#shadow)"/>
<image x="640" y="137" width="570" height="342" xlink:href="${orbit}" clip-path="url(#orbitClip)"/>
<rect x="520" y="342" width="388" height="242.4" rx="20" fill="#061e15" stroke="#3b6750" stroke-width="2" filter="url(#shadow)"/>
<image x="532" y="354" width="364" height="218.4" xlink:href="${nova}" clip-path="url(#novaClip)"/>
<text x="1220" y="605" font-family="Segoe UI,Arial,sans-serif" font-size="12" text-anchor="end" fill="#87a89e">Actual UI · synthetic preview data</text>
</svg>`;

(async () => {
  fs.mkdirSync(destination, {recursive: true});
  fs.writeFileSync(path.join(destination, 'github-preview.svg'), svg);
  const output = path.join(destination, 'github-preview.png');
  await sharp(Buffer.from(svg)).png({compressionLevel: 9}).toFile(output);
  if (fs.statSync(output).size >= 1000000) throw new Error('Social preview exceeds GitHub size limit');
  console.log('Generated 1280x640 native-vector banner and PNG social preview.');
})().catch(error => { console.error(error.message); process.exitCode = 1; });
