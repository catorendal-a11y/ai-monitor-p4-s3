# Terminal artwork

`nova.json` contains four 40 × 26 RGB rasters generated from the project's
original NOVA vectors in `assets/nova/`: work, attention, error and done.
They retain the original artwork's MIT license and attribution; see
`assets/nova/SOURCES.md`. No third-party provider marks are included.

Regenerate with `.venv\Scripts\python.exe scripts/generate_terminal_assets.py`.
Qt is a development dependency for generation only. The terminal uses Python's
standard library and Rich to draw the pixels as colored half-block cells.
