# NOVA assets

Robot geometry is the approved NOVA SVG concept. The SVG sources are retained here; firmware images are generated with scripts/generate_nova_assets.cjs.

OpenAI mark: https://cdn.openai.com/brand/OpenAI-Logos-2025.zip (white monoblossom, original geometry).
ZCode mark: https://github.com/zai-org/ZCode/blob/main/packages/ui/src/components/ui/ZCodeAboutLogo.tsx (original three paths).
Brandmarks belong to their respective owners.

## NOVA artwork

The eight NOVA poses (`work`, `attention`, `error`, `done`, `low`, `critical`, `sleep`, `blink`) are drawn by
`scripts/generate_nova_art.cjs` from one parametric template, so they stay consistent: a chamfered helmet, a dark
visor with two slanted light slits, a blade antenna, segmented arms with clamps and an LED strip on the chest.
The glow and ground-shadow ellipses must stay as they are: the firmware crops every frame to the union of all
poses, and changing them changes image sizes and flash use. After editing the script run, in order:

```text
node scripts/generate_nova_art.cjs
node scripts/generate_nova_assets.cjs
.venv/Scripts/python.exe scripts/generate_companion_lz4.py --cc gcc
.venv/Scripts/python.exe scripts/generate_terminal_assets.py
```

## Other companions

ORBIT (`scripts/generate_orbit_svg.cjs`), CLAUDE (`scripts/generate_claude_svg.cjs`), WRAITH
(`scripts/generate_wraith_svg.cjs`) and GLITCH (`scripts/generate_glitch_svg.cjs`) are drawn the same way into
`assets/orbit`, `assets/claude`, `assets/wraith` and `assets/glitch`. All five are original artwork (CLAUDE is a pixel
rendition of the Claude Code banner critter, see `assets/claude/SOURCES.md`). WRAITH and GLITCH exist only on the P4
build (`src/companion_features.h`): the S3 image has no flash for more frames and treats a stored choice of them as NOVA.
