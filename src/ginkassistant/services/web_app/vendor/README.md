# Vendored libraries

- `maplibre-gl.js`, `maplibre-gl.css`: MapLibre GL JS 5.24.1 (https://github.com/maplibre/maplibre-gl-js),
  3-Clause BSD licence (`MAPLIBRE-LICENSE.txt`). Unchanged except the source-map comment removed.
  Served by Gink's server at `/vendor/maplibre-gl.js` and `/vendor/maplibre-gl.css` and loaded by the chat page
  (`ui/live_media.py`) only when an answer has a map. Draws the vector maps (0.1.160).

To update: `npm pack maplibre-gl@5.x`, copy `dist/maplibre-gl.js` (minus its last `//# sourceMappingURL=` line),
`dist/maplibre-gl.css` and `LICENSE.txt`, then change `MAPLIBRE_VERSION` in `ui/live_media.py`.
