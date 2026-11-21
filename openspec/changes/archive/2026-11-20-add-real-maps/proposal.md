## Why

The owner asked for maps that "look 100% real", like the maps in other assistants: the 0.1.159 map was picture
squares with pins, and the website's hero map was a drawing. The same request listed bugs seen in recordings: Gink
didn't know which device it was on and asked for the operating system, "do a check now" gave steps instead of
checking, answered question cards came back blank when a chat was opened again, tables and lists right after a
sentence showed as raw text, Hey Gink heard only silence on the Catalina build, and Gink didn't know its own website
or repository.

## What Changes

- Real maps: vector street maps drawn on the device with MapLibre GL (vendored, BSD-3-Clause), in Gink's own light and
  dark styles, from OpenStreetMap data (OpenFreeMap) through Gink's server: `/vendor/*`, `/vmap/style.json`,
  `/vmap/t/{z}/{x}/{y}.pbf`, `/vmap/fonts/...`. Numbered, named markers in each place's colour; place cards with a
  photo (`/place/photo`, Wikipedia), kind, note and Directions; a bigger map; light/dark follows the app. The
  picture-square map stays as the fallback.
- The `map` block gains `category`; the API gains `/v1/places/photo`; both SDKs read `category` and get
  `place_photo` / `placePhoto`; `gink map --photos`.
- Device awareness and a real device check (`device_check` tool) in the apps' agent and chat.
- Fixes: question cards close with their answers; Markdown tables, lists and 2-space sub-lists render; a question
  sent twice is kept once; Info.plist privacy texts on the Catalina build (tools/mac_permissions.py); Gink's own links
  in every prompt (services/about_gink.py); Genie's answers formatted with the chat's code blocks; the website hero
  shows a real map.

## Out of scope

- Turn-by-turn routes, traffic, search inside the map, offline map downloads, satellite imagery.
- Serving Gink's map tiles to other websites (the endpoints are for Gink's own pages and apps).

## Impact

- New spec: maps. Modified spec: agent-mode.
- Platforms: macOS, Windows, Linux, Android (64/32-bit), iOS, web app, server, Developer API, CLI, Python and
  JavaScript SDKs, website.
