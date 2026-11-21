## 1. Build
- [x] 1.1 Server: vendored MapLibre (`/vendor`), Gink's style (`services/map_style.py`, `/vmap/style.json`), tile and font proxies with caches and per-address limits, place photos (`/place/photo`, `/place/img`, `/v1/places/photo`), web app CSP allows the map's worker
- [x] 1.2 Chat page (apps and web app): vector maps with markers, labels that make room, cards with photos and Directions, the bigger map, light/dark, sleep/wake, fallback to picture squares; map JSON hidden while an answer streams
- [x] 1.3 `category` in MAP_PROMPT (server, apps, web app); SDKs and CLI
- [x] 1.4 Device awareness (`services/device_info.py`) and `device_check` (`services/actions/health.py`)
- [x] 1.5 Fixes: question cards, Markdown blocks and sub-lists, duplicate questions, Info.plist texts (`tools/mac_permissions.py`, Catalina workflow), Gink's own links (`services/about_gink.py`), Genie's code blocks
- [x] 1.6 Website: real hero map (Zurich), social image, features, developers and blog

## 2. Check
- [x] 2.1 Tests: tests/test_real_maps.py, tests/test_device_awareness_fixes.py, tests/test_maps_voice_screen.py
- [x] 2.2 Real browser (Chromium): vector maps with Zurich OpenStreetMap data in light, dark and phone widths, card picks, zooming to street level, the bigger map, the theme switch; the picture-square fallback; question cards; Genie's answers; the website hero at desktop and phone widths
- [x] 2.3 Styles validated with MapLibre's style spec (light and dark)
