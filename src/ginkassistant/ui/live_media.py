"""
Maps, voice messages and screen view on the chat page (the apps' window and Gink on the web share it) -- 0.1.159,
real maps 0.1.160.

* Maps, by themselves: an answer about real places ends with a ```map block (the AI is asked for one: MAP_PROMPT in
  services/backend_server.py and the apps' / web app's system prompts). upgradeMaps(root) turns each block into a real
  street map drawn on the device (MapLibre GL, loaded from Gink's server only when a map appears: GINK_ICONS +
  /vendor/maplibre-gl.js) in Gink's own style (/vmap/style.json, services/map_style.py), light or dark like the app,
  from OpenStreetMap data through the server (/vmap/t/..., /vmap/fonts/...). Each place: a numbered marker in its
  kind's colour with its name beside it, and a card under the map with its photo (/place/photo), kind, note and
  Directions. Nothing to press. A device that can't draw it (no WebGL, an old browser, an older server) gets the old
  map of picture squares (/tiles) with the same cards. Places without coordinates are looked up through the server
  too (/geo/search), never straight from the device.
* Voice messages: press and hold the microphone to record, let go to send (a quick tap still dictates into the box).
  The web app records in the page (window.ginkVoiceRecorder = 'page', MediaRecorder); the apps record with their own
  microphone code (page -> 'voice_message' {action: 'start' | 'stop' | 'cancel'}). The message shows as a voice bubble
  (markVoiceMessage) and Gink answers out loud by itself.
* Screen view: Live can look at your screen instead of the camera -- getDisplayMedia in browsers; in the apps the
  window asks the app for frames (page -> 'screen_view' {on}, app -> liveScreenFrame(dataUrl)). Saying "look at my
  screen" starts it by itself (openScreenView(question)).

Kept as raw strings (r\"\"\") so JavaScript backslashes need no escaping.
"""

CSS = r"""
  /* ---------- maps in answers ---------- */
  .gmap { position: relative; margin: 10px 0 6px; border: 1px solid var(--border); border-radius: 16px; overflow: hidden;
          background: var(--elevated); max-width: 720px; }
  .gmap-view { position: relative; height: 300px; overflow: hidden; background: #F5F4F0; }
  body.theme-dark .gmap-view { background: #1D2023; }
  .gmap-view > .gm-canvas { position: absolute; left: 0; top: 0; right: 0; bottom: 0; overflow: hidden; }  /* beats .maplibregl-map */
  .gm-canvas.raster { background: #dfe7dc; cursor: grab; touch-action: none; -webkit-user-select: none; user-select: none; }
  body.theme-dark .gm-canvas.raster { background: #2a302b; }
  .gm-canvas.raster.drag { cursor: grabbing; }
  .gmap img.tile { position: absolute; width: 256px; height: 256px; max-width: none; pointer-events: none; }
  body.theme-dark .gmap img.tile { filter: brightness(.82) contrast(1.08) saturate(.85); }
  .gm-chip { position: absolute; left: 10px; top: 10px; z-index: 5; max-width: calc(100% - 70px); display: flex;
             align-items: center; padding: 6px 11px 6px 9px; border-radius: 999px; background: var(--bg); color: var(--text-main);
             font-size: 13px; font-weight: 600; box-shadow: 0 1px 4px rgba(0,0,0,.16), 0 0 0 1px rgba(0,0,0,.04);
             pointer-events: none; }
  .gm-chip svg { flex: none; margin-right: 6px; color: #2F6B1F; }
  body.theme-dark .gm-chip svg { color: #8BC34A; }
  .gm-chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .gm-bigbtn { position: absolute; right: 10px; top: 80px; z-index: 5; width: 30px; height: 30px; border: 0; border-radius: 8px;
               background: var(--bg); color: var(--text-main); display: flex; align-items: center; justify-content: center;
               cursor: pointer; box-shadow: 0 1px 4px rgba(0,0,0,.16), 0 0 0 1px rgba(0,0,0,.04); padding: 0; }
  .gm-bigbtn:hover { background: var(--elevated); }
  .gm-bigbtn:focus-visible, .gm-card:focus-visible, .gm-mk:focus-visible, .gm-dir:focus-visible {
    outline: 2px solid #2F6B1F; outline-offset: 2px; }
  /* the vector map (MapLibre): controls and attribution in Gink's look */
  .gmap .maplibregl-ctrl-group { border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.16), 0 0 0 1px rgba(0,0,0,.04); }
  .gm-attr { position: absolute; right: 0; bottom: 0; z-index: 5; max-width: calc(100% - 12px); padding: 1px 7px 2px;
             border-top-left-radius: 7px; background: rgba(255,255,255,.78); color: #4A4E54; font: 10.5px/1.5 system-ui, sans-serif;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .gmap a[href]::after { content: none; }                    /* no "↗" from the chat's links on the map's own */
  .gmap a[href] { border-bottom: 0; }
  .gm-attr a { color: inherit; text-decoration: none; margin-left: 5px; }
  .gm-attr a:first-child { margin-left: 0; }
  .gm-attr a:hover { text-decoration: underline; }
  body.theme-dark .gm-attr { background: rgba(29,32,35,.78); color: #C3C7CC; }
  body.theme-dark .gmap .maplibregl-ctrl-group { background: #2B2F33; }
  body.theme-dark .gmap .maplibregl-ctrl-group button + button { border-top-color: #41464C; }
  body.theme-dark .gmap .maplibregl-ctrl button .maplibregl-ctrl-icon { filter: invert(1) brightness(.9); }
  .gmap .maplibregl-cooperative-gesture-screen { font-size: 15px; }
  /* places: a round marker in the place's colour, its number, its name beside it */
  .gm-mk { width: 28px; height: 28px; padding: 0; border: 0; background: none; cursor: pointer; }
  .gm-mk .gm-dot { position: absolute; left: 0; top: 0; width: 28px; height: 28px; box-sizing: border-box; border-radius: 50%;
                   background: var(--c, #2F6B1F); border: 2.5px solid #fff; color: #fff; font: 700 12px/23px system-ui, sans-serif;
                   text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,.32); transition: transform .15s ease; }
  .gm-mk.on { z-index: 4; }
  .gm-mk.on .gm-dot { transform: scale(1.18); box-shadow: 0 0 0 4px var(--ring, rgba(47,107,31,.24)), 0 3px 9px rgba(0,0,0,.36); }
  .gm-mk .gm-lbl { position: absolute; left: 33px; top: 50%; transform: translateY(-50%); white-space: nowrap; max-width: 190px;
                   overflow: hidden; text-overflow: ellipsis; font: 650 12.5px/1.25 system-ui, -apple-system, sans-serif; color: #1F2225;
                   text-shadow: 0 0 2px #fff, 0 0 2px #fff, 0 0 3px #fff, 0 0 4px #fff; pointer-events: none; }
  .gm-mk.left .gm-lbl { left: auto; right: 33px; text-align: right; }
  .gm-mk.nolbl .gm-lbl { visibility: hidden; }
  body.theme-dark .gm-mk .gm-dot { border-color: #1D2023; }
  body.theme-dark .gm-mk .gm-lbl { color: #ECEEF0; text-shadow: 0 0 2px #1D2023, 0 0 2px #1D2023, 0 0 3px #1D2023, 0 0 4px #1D2023; }
  /* the places under the map: photo, name, kind, note, directions */
  .gm-cards { display: flex; gap: 8px; overflow-x: auto; padding: 10px; scroll-snap-type: x mandatory; scrollbar-width: thin;
              -webkit-overflow-scrolling: touch; overscroll-behavior-x: contain; }
  .gm-card { position: relative; flex: 0 0 auto; width: 272px; max-width: calc(100% - 28px); display: flex; padding: 8px;
             box-sizing: border-box; border-radius: 12px; border: 1px solid var(--border); background: var(--bg); cursor: pointer;
             scroll-snap-align: start; text-align: left; color: var(--text-main); }
  .gm-cards.few .gm-card { flex: 1 1 0; width: auto; max-width: none; }
  .gm-card:hover { border-color: var(--text-muted); }
  .gm-card.on { border-color: var(--c, #2F6B1F); box-shadow: 0 0 0 1px var(--c, #2F6B1F); }
  .gm-ph { position: relative; flex: none; width: 72px; height: 72px; margin-right: 10px; border-radius: 9px; overflow: hidden;
           background: var(--elevated); display: flex; align-items: center; justify-content: center; color: var(--c, #2F6B1F); }
  .gm-ph img { position: absolute; left: 0; top: 0; width: 100%; height: 100%; object-fit: cover; }
  .gm-ph .gm-n { position: absolute; left: 5px; top: 5px; z-index: 1; min-width: 19px; height: 19px; padding: 0 4px; box-sizing: border-box;
                 border-radius: 10px; background: var(--c, #2F6B1F); color: #fff; font: 700 11px/19px system-ui, sans-serif;
                 text-align: center; box-shadow: 0 0 0 1.5px #fff; }
  .gm-tx { min-width: 0; flex: 1; display: flex; flex-direction: column; padding-right: 30px; }
  .gm-nm { font-size: 14px; font-weight: 650; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .gm-ct { display: flex; align-items: center; margin-top: 2px; font-size: 12px; color: var(--text-muted); }
  .gm-ct i { flex: none; width: 7px; height: 7px; margin-right: 6px; border-radius: 50%; background: var(--c, #2F6B1F); }
  .gm-nt { margin-top: 3px; font-size: 12.5px; line-height: 1.35; color: var(--text-muted); display: -webkit-box; -webkit-line-clamp: 2;
           -webkit-box-orient: vertical; overflow: hidden; }
  .gm-dir { position: absolute; right: 8px; top: 8px; width: 28px; height: 28px; border-radius: 50%; border: 1px solid var(--border);
            display: flex; align-items: center; justify-content: center; color: var(--text-main); background: var(--bg); }
  .gm-dir:hover { background: var(--elevated); }
  .gmap-note { padding: 0 14px 10px; font-size: 12.5px; color: var(--text-muted); }
  .gmap-view + .gmap-note { padding-top: 10px; }
  /* the old map (picture squares): for devices that can't draw vector maps */
  .gmap-pin { position: absolute; width: 26px; height: 26px; margin: -26px 0 0 -13px; border-radius: 50% 50% 50% 0;
              transform: rotate(-45deg); background: var(--c, #2F6B1F); border: 2px solid #fff; box-shadow: 0 2px 6px rgba(0,0,0,.35);
              display: flex; align-items: center; justify-content: center; cursor: pointer; z-index: 2; }
  .gmap-pin span { transform: rotate(45deg); color: #fff; font: 700 11px/1 system-ui, sans-serif; }
  .gmap-pin.on { z-index: 3; box-shadow: 0 0 0 4px rgba(47,107,31,.25), 0 2px 6px rgba(0,0,0,.35); }
  .gmap-zoom { position: absolute; right: 10px; top: 10px; z-index: 4; display: flex; flex-direction: column; }
  .gmap-zoom button { width: 30px; height: 30px; border: 1px solid var(--border); background: var(--bg); color: var(--text-main);
                      font: 600 17px/1 system-ui, sans-serif; cursor: pointer; padding: 0; }
  .gmap-zoom button:first-child { border-radius: 8px 8px 0 0; } .gmap-zoom button:last-child { border-radius: 0 0 8px 8px; margin-top: -1px; }
  .gmap-attr { position: absolute; right: 0; bottom: 0; z-index: 4; font: 10.5px/1.4 system-ui, sans-serif; padding: 1px 6px;
               background: rgba(255,255,255,.8); color: #333; border-top-left-radius: 6px; }
  .gmap-attr a { color: #333; }
  .gmap-tip { position: absolute; z-index: 5; transform: translate(-50%, -100%); margin-top: -34px; padding: 5px 9px; border-radius: 8px;
              background: var(--bg); color: var(--text-main); border: 1px solid var(--border); font-size: 12.5px; white-space: nowrap;
              box-shadow: 0 4px 14px rgba(0,0,0,.18); pointer-events: none; }
  /* a bigger map, over the chat */
  .gmap-overlay { position: fixed; left: 0; top: 0; right: 0; bottom: 0; z-index: 90; display: flex; align-items: center;
                  justify-content: center; padding: 3vh 3vw; background: rgba(0,0,0,.45); }
  .gmap-overlay .gmap { margin: 0; width: 100%; max-width: 1200px; height: 100%; display: flex; flex-direction: column;
                        box-shadow: 0 18px 60px rgba(0,0,0,.35); }
  .gmap-overlay .gmap-view { flex: 1; height: auto; min-height: 0; }
  .gmap-hold { margin: 10px 0 6px; border: 1px dashed var(--border); border-radius: 16px; max-width: 720px; }
  @media (max-width: 560px) { .gmap-view { height: 260px; } .gmap-overlay { padding: 0; } .gmap-overlay .gmap { border-radius: 0; } }
  @media (prefers-reduced-motion: reduce) { .gm-mk .gm-dot { transition: none; } }

  /* ---------- voice messages ---------- */
  #vm-bar { position: absolute; left: 10px; right: 10px; bottom: 10px; z-index: 6; display: none; align-items: center;
            padding: 10px 14px; border-radius: 14px; background: var(--elevated); border: 1px solid var(--border);
            color: var(--text-main); font-size: 14px; box-shadow: 0 6px 20px rgba(0,0,0,.14); }
  #vm-bar.on { display: flex; }
  #vm-bar .dot { width: 10px; height: 10px; border-radius: 50%; background: #DC2626; margin-right: 10px; animation: vmPulse 1.1s infinite; }
  #vm-bar .tm { font-variant-numeric: tabular-nums; font-weight: 650; margin-right: 10px; }
  #vm-bar .hint { color: var(--text-muted); }
  @keyframes vmPulse { 50% { opacity: .35; } }
  #mic.vm-rec { background: #DC2626 !important; color: #fff !important; }
  .row.user .vmsg { display: flex; align-items: center; justify-content: flex-end; margin: 0 0 4px; font-size: 12.5px; color: var(--text-muted); }
  .row.user .vmsg audio { height: 32px; max-width: 240px; margin-left: 8px; }
  @media (prefers-reduced-motion: reduce) { #vm-bar .dot { animation: none; } }

  /* ---------- screen view (Live) ---------- */
  #live-cam.screen video, #live-cam img.live-shot { flex: 1; min-height: 0; width: 100%; object-fit: contain; background: #000; }
"""

JS = r"""
  function lmSay(text) {                            // a short notice (or the status line under the message box)
    if (window.ginkNotify) ginkNotify({ id: 'live-media', title: text, timeout: 4500, system: false });
    else if (typeof setStatus === 'function') setStatus(text);
  }
  window.lmSay = lmSay;

  // ============================ maps in answers ============================
  // A real, vector map (MapLibre GL, drawn on the device from OpenStreetMap data: Gink's server /vmap/...) with the
  // places marked, named and listed under it with their photos. Devices that can't draw it (no WebGL, an old
  // browser, an older Gink server) get the old map of picture squares (/tiles) -- the same places, the same cards.
  var GMAP = { tile: 256, minZ: 2, maxZ: 18 };
  var MAPLIBRE_VERSION = '5.24.1';
  function gmServer() { return typeof window.GINK_ICONS === 'string' ? window.GINK_ICONS : ''; }
  function gmProject(lat, lon, z) {                  // world pixels at zoom z (Web Mercator)
    var s = GMAP.tile * Math.pow(2, z), r = Math.max(-85.05, Math.min(85.05, lat)) * Math.PI / 180;
    return { x: (lon + 180) / 360 * s, y: (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * s };
  }
  function gmUnproject(x, y, z) {
    var s = GMAP.tile * Math.pow(2, z), n = Math.PI - 2 * Math.PI * y / s;
    return { lat: 180 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n))), lon: x / s * 360 - 180 };
  }
  function gmStore(name) { try { return JSON.parse(localStorage.getItem(name) || '{}') || {}; } catch (e) { return {}; } }
  function gmKeep(name, key, value) {
    try { var c = gmStore(name), ks = Object.keys(c); if (ks.length > 300) delete c[ks[0]]; c[key] = value; localStorage.setItem(name, JSON.stringify(c)); } catch (e) {}
  }
  function gmGeoCache() { return gmStore('gink_geo'); }
  function gmGeocode(q) {                             // through Gink's server; remembered in this browser
    var key = String(q || '').toLowerCase().trim(), cache = gmGeoCache();
    if (!key) return Promise.resolve(null);
    if (cache[key]) return Promise.resolve(cache[key]);
    return fetch(gmServer() + '/geo/search?limit=1&q=' + encodeURIComponent(q)).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) {
        var p = j && j.places && j.places[0]; if (!p) return null;
        var hit = { lat: p.lat, lon: p.lon, display: p.display || '' };
        gmKeep('gink_geo', key, hit);
        return hit;
      }).catch(function () { return null; });
  }
  function gmOsm(p) { return 'https://www.openstreetmap.org/?mlat=' + p.lat + '&mlon=' + p.lon + '#map=16/' + p.lat + '/' + p.lon; }
  function gmApple() { return /Mac|iPhone|iPad|iPod/.test(navigator.platform || '') || /iPhone|iPad|Macintosh/.test(navigator.userAgent || ''); }
  function gmDirections(p) {                         // the device's own maps app: Apple Maps on Apple devices, else Google Maps
    if (gmApple()) return 'https://maps.apple.com/?daddr=' + p.lat + ',' + p.lon + '&q=' + encodeURIComponent(p.name);
    return 'https://www.google.com/maps/dir/?api=1&destination=' + p.lat + ',' + p.lon;
  }
  function gmFit(points, w, h) {                     // the zoom and centre that show every place
    if (!points.length) return { z: 2, lat: 20, lon: 0 };
    if (points.length === 1) return { z: 15, lat: points[0].lat, lon: points[0].lon };
    for (var z = 17; z >= GMAP.minZ; z--) {
      var xs = [], ys = [];
      points.forEach(function (p) { var q = gmProject(p.lat, p.lon, z); xs.push(q.x); ys.push(q.y); });
      var minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs), minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
      if (maxX - minX <= w - 70 && maxY - minY <= h - 80) {
        var c = gmUnproject((minX + maxX) / 2, (minY + maxY) / 2, z);
        return { z: z, lat: c.lat, lon: c.lon };
      }
    }
    return { z: GMAP.minZ, lat: points[0].lat, lon: points[0].lon };
  }

  // ---- what kind of place: its colour, its picture, its name ----
  var GM_ICON = {
    food: '<path d="M7 3v7M4.5 3v4.5a2.5 2.5 0 0 0 5 0V3M7 10v11M17.5 3c-2 1.4-3 3.8-3 6.5V13h3v8"/>',
    cafe: '<path d="M4 9h12v4.5A5.5 5.5 0 0 1 10.5 19h-1A5.5 5.5 0 0 1 4 13.5zM16 10.5h1.5a2.5 2.5 0 0 1 0 5H16M8 3.5v2.5M12 3.5v2.5"/>',
    bar: '<path d="M5 4h14l-7 8zM12 12v8M8 20h8"/>',
    shop: '<path d="M5.5 8h13l-1 12.5h-11zM9 8V6.5a3 3 0 0 1 6 0V8"/>',
    museum: '<path d="M3 9.5L12 4l9 5.5M5.5 11v7M10 11v7M14 11v7M18.5 11v7M3.5 20.5h17"/>',
    sight: '<path d="M4 8.5h3.2L9 6h6l1.8 2.5H20V19H4z"/><circle cx="12" cy="13.3" r="3.3"/>',
    park: '<path d="M12 3l5 7h-3l4 6H6l4-6H7zM12 16v5"/>',
    beach: '<path d="M3 19c2.2 0 2.2-1.4 4.5-1.4s2.3 1.4 4.5 1.4 2.2-1.4 4.5-1.4 2.3 1.4 4.5 1.4M4.5 12a7.5 7.5 0 0 1 15 0zM12 12v5"/>',
    hotel: '<path d="M3 18.5V6.5M3 14h18v4.5M21 14v-2.5a3 3 0 0 0-3-3h-7V14"/><circle cx="7" cy="10.7" r="1.7"/>',
    transport: '<path d="M8 3.5h8a3 3 0 0 1 3 3V14a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3V6.5a3 3 0 0 1 3-3zM5 10h14M8.5 21l2-4M15.5 21l-2-4"/>',
    health: '<path d="M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z"/>',
    school: '<path d="M2.5 9.5L12 5l9.5 4.5L12 14zM6.5 11.5v4.8c3 2 8 2 11 0v-4.8"/>',
    worship: '<path d="M12 2.5v4M10 4.5h4M6 21v-8.5l6-4.5 6 4.5V21M10 21v-3.5a2 2 0 0 1 4 0V21M3.5 21h17"/>',
    other: '<path d="M12 21s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/>'
  };
  var GM_KIND = {                                     // colours dark enough for white numbers on them
    food: ['#C2410C', 'Restaurant'], cafe: ['#8A5A2B', 'Café'], bar: ['#6741D9', 'Bar'], shop: ['#3B5BDB', 'Shop'],
    museum: ['#7048E8', 'Museum'], sight: ['#0B7285', 'Sight'], park: ['#2A7D3A', 'Park'], beach: ['#0C7489', 'Beach'],
    hotel: ['#A61E4D', 'Hotel'], transport: ['#1864AB', 'Transport'], health: ['#C92A2A', 'Health'],
    school: ['#9C4A00', 'School'], worship: ['#495057', 'Place of worship'], other: ['#2F6B1F', 'Place']
  };
  var GM_SAME = { restaurant: 'food', eat: 'food', dining: 'food', coffee: 'cafe', 'café': 'cafe', bakery: 'cafe', pub: 'bar',
    nightlife: 'bar', club: 'bar', market: 'shop', shopping: 'shop', store: 'shop', gallery: 'museum', art: 'museum',
    attraction: 'sight', landmark: 'sight', monument: 'sight', viewpoint: 'sight', nature: 'park', garden: 'park', zoo: 'park',
    hike: 'park', lodging: 'hotel', stay: 'hotel', hostel: 'hotel', station: 'transport', airport: 'transport',
    hospital: 'health', pharmacy: 'health', clinic: 'health', university: 'school', education: 'school', church: 'worship',
    mosque: 'worship', temple: 'worship', synagogue: 'worship', religion: 'worship' };
  var GM_GUESS = [                                    // matched on the words without accents: "café" -> "cafe"
    ['cafe', /\b(cafes?|coffee|espresso|tea ?room|bakery|patisserie|boulangerie|konditorei|confiserie)\b/],
    ['bar', /\b(bar|pub|brewery|brewpub|wine|cocktails?|taproom|biergarten|speakeasy)\b/],
    ['museum', /\b(museum|musee|museo|gallery|galerie|kunsthaus|kunsthalle|art (centre|center)|exhibition)\b/],
    ['food', /\b(restaurants?|bistro|trattoria|osteria|pizzeria|brasserie|eatery|diner|grill|kitchen|sushi|ramen|taqueria|noodles?|steakhouse|burgers?|street food|food)\b/],
    ['hotel', /\b(hotel|hostel|inn|resort|lodge|guest ?house|b&b|motel)\b/],
    ['beach', /\b(beach|plage|playa|praia|strand)\b/],
    ['park', /\b(park|parc|parque|garden|gardens|jardin|forest|nature reserve|zoo|botanical|national park|trail)\b/],
    ['transport', /\b(station|airport|terminal|harbou?r|ferry|metro|railway|bus stop|hauptbahnhof|gare)\b/],
    ['health', /\b(hospital|clinic|pharmacy|doctor|dentist|medical)\b/],
    ['school', /\b(school|university|college|campus|academy|institute)\b/],
    ['worship', /\b(church|cathedral|mosque|temple|synagogue|shrine|basilica|chapel|monastery|pagoda|abbey)\b/],
    ['shop', /\b(shop|store|market|mall|boutique|bazaar|souk|department)\b/],
    ['sight', /\b(tower|castle|palace|monument|square|bridge|old town|landmark|viewpoint|lookout|statue|fort|fortress|ruins|memorial|opera|theatre|theater)\b/]
  ];
  function gmKind(p) {
    var k = String(p.category || p.kind || p.type || '').toLowerCase().trim();
    k = GM_SAME[k] || k;
    if (GM_KIND[k]) return k;
    var text = ((p.name || '') + ' ' + (p.note || '')).toLowerCase();
    try { text = text.normalize('NFD').replace(/[̀-ͯ]/g, ''); } catch (e) {}
    for (var i = 0; i < GM_GUESS.length; i++) if (GM_GUESS[i][1].test(text)) return GM_GUESS[i][0];
    return 'other';
  }
  function gmRgba(hex, a) {
    var n = parseInt(String(hex).slice(1), 16);
    return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function gmSvg(kind, size) {
    return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
           'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (GM_ICON[kind] || GM_ICON.other) + '</svg>';
  }

  // ---- a picture of each place: Wikipedia's, through Gink's server (/place/photo); remembered here for a week ----
  var GM_PHOTOS = {};
  function gmPhoto(p) {
    var key = (p.name + '|' + p.lat.toFixed(3) + '|' + p.lon.toFixed(3)).toLowerCase();
    if (GM_PHOTOS[key]) return GM_PHOTOS[key];
    var seen = gmStore('gink_place_photos')[key];
    if (seen && Date.now() - seen.t < 7 * 864e5) return (GM_PHOTOS[key] = Promise.resolve(seen.u || ''));
    GM_PHOTOS[key] = fetch(gmServer() + '/place/photo?name=' + encodeURIComponent(p.name) + '&lat=' + p.lat + '&lon=' + p.lon)
      .then(function (r) { return r.ok ? r.json() : (r.status === 404 ? {} : null); })
      .then(function (j) {
        if (j === null) { delete GM_PHOTOS[key]; return ''; }     // the server had a problem: ask again another time
        var u = (j && typeof j.image === 'string' && /^https?:\/\//.test(j.image)) ? j.image : '';
        gmKeep('gink_place_photos', key, { u: u, t: Date.now() });
        return u;
      }).catch(function () { delete GM_PHOTOS[key]; return ''; });
    return GM_PHOTOS[key];
  }

  // ---- the vector map ----
  var GM_LIB = null, GM_VECTOR = { broken: '' };
  function gmCanVector() {
    if (window.ginkVectorMaps === false || GM_VECTOR.broken) return false;
    if (!window.Worker || !window.Blob || !window.URL || !URL.createObjectURL || !Object.hasOwn || !Array.prototype.at) return false;
    if (navigator.deviceMemory && navigator.deviceMemory < 2) return false;     // a phone with very little memory: squares
    if (GM_VECTOR.gl == null) {
      try {
        var cv = document.createElement('canvas'), gl = cv.getContext('webgl2') || cv.getContext('webgl');
        GM_VECTOR.gl = !!gl;
        var lose = gl && gl.getExtension('WEBGL_lose_context'); if (lose) lose.loseContext();
      } catch (e) { GM_VECTOR.gl = false; }
    }
    return GM_VECTOR.gl;
  }
  function gmLib() {                                  // MapLibre, from Gink's server, only once a map is needed
    if (window.maplibregl && window.maplibregl.Map) return Promise.resolve(window.maplibregl);
    if (GM_LIB) return GM_LIB;
    GM_LIB = new Promise(function (ok, fail) {
      var base = gmServer() + '/vendor/maplibre-gl', v = '?v=' + MAPLIBRE_VERSION, amd = window.define;
      if (!document.querySelector('link[data-gink-maplibre]')) {
        var css = document.createElement('link'); css.rel = 'stylesheet'; css.href = base + '.css' + v;
        css.setAttribute('data-gink-maplibre', '1'); document.head.appendChild(css);
      }
      var s = document.createElement('script'); s.src = base + '.js' + v; s.async = true;
      var timer = setTimeout(function () { fail(new Error('timeout')); }, 25000);
      function done() { clearTimeout(timer); if (amd) window.define = amd; }
      if (amd && amd.amd) window.define = undefined;  // a page with an AMD loader: still make the global
      s.onload = function () { done(); if (window.maplibregl && window.maplibregl.Map) ok(window.maplibregl); else fail(new Error('no maplibre')); };
      s.onerror = function () { done(); fail(new Error('load')); };
      document.head.appendChild(s);
    });
    GM_LIB.catch(function () { GM_LIB = null; });
    return GM_LIB;
  }
  function gmTheme() { return document.body.classList.contains('theme-dark') ? 'dark' : 'light'; }
  function gmLang() {
    var l = String(document.documentElement.lang || navigator.language || 'en').slice(0, 2).toLowerCase();
    return /^[a-z]{2}$/.test(l) ? l : 'en';
  }
  function gmAbs(u) { try { return new URL(u, location.href).href; } catch (e) { return u; } }
  function gmStyleUrl(theme) { return gmAbs(gmServer() + '/vmap/style.json?theme=' + theme + '&lang=' + gmLang()); }
  var GM_INK = {                                      // the style's own pictures, drawn here (no sprite file)
    light: { halo: '#FFFFFF', shield: ['#FFFFFF', '#C9C5BC'] }, dark: { halo: '#1D2023', shield: ['#3A3F45', '#555B62'] },
    poi: { food: '#F76707', shop: '#4C6EF5', culture: '#7950F2', nature: '#37B24D', health: '#F03E3E', transport: '#1C7ED6',
           lodging: '#BE4BDB', other: '#868E96' }
  };
  function gmImages(map, theme) {
    map.on('styleimagemissing', function (e) {
      var id = e.id, ink = GM_INK[map._ginkTheme || theme] || GM_INK.light, pr = 2, cv = document.createElement('canvas'), g;
      if (map.hasImage(id)) return;
      if (id === 'gink-shield') {
        cv.width = cv.height = 20 * pr; g = cv.getContext('2d'); g.scale(pr, pr);
        g.beginPath(); g.moveTo(5, 1); g.lineTo(15, 1); g.quadraticCurveTo(19, 1, 19, 5); g.lineTo(19, 15); g.quadraticCurveTo(19, 19, 15, 19);
        g.lineTo(5, 19); g.quadraticCurveTo(1, 19, 1, 15); g.lineTo(1, 5); g.quadraticCurveTo(1, 1, 5, 1); g.closePath();
        g.fillStyle = ink.shield[0]; g.fill(); g.lineWidth = 1; g.strokeStyle = ink.shield[1]; g.stroke();
        map.addImage(id, g.getImageData(0, 0, cv.width, cv.height), { pixelRatio: pr, stretchX: [[6 * pr, 14 * pr]],
                     stretchY: [[6 * pr, 14 * pr]], content: [4 * pr, 3 * pr, 16 * pr, 17 * pr] });
      } else if (id.indexOf('gink-poi-') === 0) {
        cv.width = cv.height = 14 * pr; g = cv.getContext('2d'); g.scale(pr, pr);
        g.beginPath(); g.arc(7, 7, 6.2, 0, 2 * Math.PI); g.fillStyle = ink.halo; g.fill();
        g.beginPath(); g.arc(7, 7, 4.5, 0, 2 * Math.PI); g.fillStyle = GM_INK.poi[id.slice(9)] || GM_INK.poi.other; g.fill();
        map.addImage(id, g.getImageData(0, 0, cv.width, cv.height), { pixelRatio: pr });
      }
    });
  }
  function gmVector(canvas, places, opts) {          // -> a promise of { pick, focus, resize, sleep, big }
    return gmLib().then(function (ml) {
      return new Promise(function (ok, fail) {
        var theme = gmTheme(), map, mks = [], sel = -1, settled = false, tilesOk = 0, tilesBad = 0, styleOk = false;
        var w = canvas.clientWidth || 600, padR = Math.min(150, Math.round(w * 0.3));
        var o = { container: canvas, style: gmStyleUrl(theme), attributionControl: false, cooperativeGestures: true,
                  dragRotate: false, pitchWithRotate: false, touchPitch: false, maxZoom: 18.5, minZoom: 1, fadeDuration: 120,
                  maxTileCacheSize: 120 };
        if (opts.cam) { o.center = opts.cam.center; o.zoom = opts.cam.zoom; }
        else if (places.length === 1) { o.center = [places[0].lon, places[0].lat]; o.zoom = 15; }
        else {
          var b = new ml.LngLatBounds();
          places.forEach(function (p) { b.extend([p.lon, p.lat]); });
          o.bounds = b; o.fitBoundsOptions = { padding: { top: 60, bottom: 46, left: 46, right: padR }, maxZoom: 15.5 };
        }
        var ctrl = null;
        var give = function (err) {                     // settle once: the map works -- or it goes, and the old one comes
          if (settled) return; settled = true;
          if (err) { try { map.remove(); } catch (e) {} fail(err); } else ok(ctrl);
        };
        try { map = new ml.Map(o); } catch (e) { fail(e); return; }
        try {
          map._ginkTheme = theme;
          map.touchZoomRotate.disableRotation();
          map.keyboard.disableRotation && map.keyboard.disableRotation();
          map.addControl(new ml.NavigationControl({ showCompass: false }), 'top-right');
          var credits = document.createElement('div'); credits.className = 'gm-attr';   // always in sight, one line
          credits.innerHTML = '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a>' +
            '<a href="https://openmaptiles.org/" target="_blank" rel="noopener">© OpenMapTiles</a>' +
            '<a href="https://openfreemap.org/" target="_blank" rel="noopener">OpenFreeMap</a>';
          canvas.appendChild(credits);
          gmImages(map, theme);
          map.on('error', function (e) {                  // the style itself failed: the old map; map pieces failing: count
            if (!styleOk) { give(new Error('style ' + ((e && e.error && e.error.status) || ''))); return; }
            if (e && (e.tile || e.sourceId === 'omt')) { tilesBad++; if (tilesBad >= 6 && !tilesOk) give(new Error('tiles')); }
          });
          map.on('sourcedata', function (e) { if (e.sourceId === 'omt' && e.tile) tilesOk++; });
          map.on('style.load', function () {              // room for our places: the map's own names step aside for them
            styleOk = true;
            try {
              map.addSource('gink-places', { type: 'geojson', data: { type: 'FeatureCollection', features: places.map(function (p) {
                return { type: 'Feature', properties: { name: p.name }, geometry: { type: 'Point', coordinates: [p.lon, p.lat] } }; }) } });
              if (!map.hasImage('gink-hole')) map.addImage('gink-hole', { width: 32, height: 32, data: new Uint8Array(32 * 32 * 4) });
              map.addLayer({ id: 'gink-places', type: 'symbol', source: 'gink-places',
                layout: { 'icon-image': 'gink-hole', 'icon-allow-overlap': true, 'text-field': ['get', 'name'],
                          'text-font': ['Noto Sans Bold'], 'text-size': 13, 'text-anchor': 'left', 'text-offset': [1.3, 0],
                          'text-allow-overlap': true, 'text-max-width': 40 },
                paint: { 'icon-opacity': 0, 'text-opacity': 0 } });
            } catch (e) {}
          });
          map.on('load', function () { map._ginkLoaded = true; declutter(); setTimeout(function () { if (!tilesBad || tilesOk) give(); }, 0); });
          setTimeout(function () { if (!settled) give(styleOk ? null : new Error('slow')); }, 30000);   // a slow network: still the real map once it has its style
          places.forEach(function (p, i) {
            var el = document.createElement('button'); el.type = 'button'; el.className = 'gm-mk';
            el.style.setProperty('--c', GM_KIND[p.kind][0]); el.style.setProperty('--ring', gmRgba(GM_KIND[p.kind][0], 0.26));
            el.innerHTML = '<span class="gm-dot"></span><span class="gm-lbl"></span>';
            el.firstChild.textContent = String(i + 1); el.lastChild.textContent = p.name;
            el.setAttribute('aria-label', (i + 1) + '. ' + p.name);
            el.addEventListener('click', function (e) { e.stopPropagation(); pick(i, true); });
            mks.push({ el: el, w: 0, m: new ml.Marker({ element: el, anchor: 'center' }).setLngLat([p.lon, p.lat]).addTo(map) });
          });
          var raf = 0;
          function declutter() {                          // a name that would cover another place or name moves left, or hides
            raf = 0; if (!map) return;                    // (the chosen place's name goes first)
            var W = canvas.clientWidth, order = places.map(function (_, i) { return i; });
            var pts = places.map(function (p) { return map.project([p.lon, p.lat]); });
            var boxes = pts.map(function (q) { return { x: q.x - 15, y: q.y - 15, w: 30, h: 30 }; });     // every marker
            var at = canvas.getBoundingClientRect();         // and what floats over the map: title, buttons, credits
            Array.prototype.forEach.call(canvas.parentNode.querySelectorAll('.gm-chip, .gm-bigbtn, .gm-attr, .maplibregl-ctrl-group'), function (el) {
              var r = el.getBoundingClientRect(); if (r.width) boxes.push({ x: r.left - at.left - 4, y: r.top - at.top - 4, w: r.width + 8, h: r.height + 8 });
            });
            if (sel >= 0) order.sort(function (a, b2) { return (b2 === sel) - (a === sel); });
            function free(r) {
              if (r.x < 4 || r.x + r.w > W - 4) return false;
              return !boxes.some(function (t) { return r.x < t.x + t.w && t.x < r.x + r.w && r.y < t.y + t.h && t.y < r.y + r.h; });
            }
            order.forEach(function (i) {
              var mk = mks[i], q = pts[i]; if (!mk.w) mk.w = Math.min(190, mk.el.lastChild.offsetWidth || 0);
              var right = { x: q.x + 17, y: q.y - 9, w: mk.w, h: 18 }, left = { x: q.x - 17 - mk.w, y: q.y - 9, w: mk.w, h: 18 };
              var side = free(right) ? right : (free(left) ? left : null);
              mk.el.classList.toggle('left', side === left);
              mk.el.classList.toggle('nolbl', !side);
              if (side) boxes.push(side);
            });
          }
          map.on('move', function () { if (!raf) raf = requestAnimationFrame(declutter); });
          map.on('resize', declutter);
          function pick(i, fromMap) {
            sel = i;
            mks.forEach(function (mk, j) { mk.el.classList.toggle('on', j === i); });
            if (!fromMap) {
              var p = places[i], still = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
              map.easeTo({ center: [p.lon, p.lat], zoom: Math.max(map.getZoom(), 14.5), duration: still ? 0 : 650 });
            }
            declutter();
            if (fromMap && opts.onPick) opts.onPick(i);
          }
          ctrl = {
            kind: 'vector',
            pick: function (i) { pick(i, false); },
            resize: function () { map.resize(); declutter(); },
            big: function (on) { if (on) map.cooperativeGestures.disable(); else map.cooperativeGestures.enable(); map.resize(); declutter(); },
            theme: function (t) {                         // the app switched light / dark
              if (map._ginkTheme === t) return;
              map._ginkTheme = t;
              ['gink-shield'].concat(Object.keys(GM_INK.poi).map(function (k) { return 'gink-poi-' + k; }))
                .forEach(function (id) { if (map.hasImage(id)) map.removeImage(id); });
              map.setStyle(gmStyleUrl(t), { diff: false });
            },
            cam: function () { var c = map.getCenter(); return { center: [c.lng, c.lat], zoom: map.getZoom() }; },
            sleep: function () { try { map.remove(); } catch (e) {} map = null; }
          };
        } catch (e) { give(e); }
      });
    });
  }

  // ---- the old map: picture squares (no WebGL) ----
  function gmMap(view, places, onPick) {
    var st = { z: 2, cx: 0, cy: 0, tiles: {}, pins: [] };
    var layer = document.createElement('div'); layer.style.cssText = 'position:absolute;left:0;top:0;right:0;bottom:0';
    view.appendChild(layer);
    var tip = document.createElement('div'); tip.className = 'gmap-tip'; tip.style.display = 'none'; view.appendChild(tip);
    function size() { return { w: view.clientWidth || 600, h: view.clientHeight || 280 }; }
    function draw() {
      var sz = size(), n = Math.pow(2, st.z), left = st.cx - sz.w / 2, top = st.cy - sz.h / 2, want = {};
      for (var tx = Math.floor(left / GMAP.tile); tx <= Math.floor((left + sz.w) / GMAP.tile); tx++) {
        for (var ty = Math.floor(top / GMAP.tile); ty <= Math.floor((top + sz.h) / GMAP.tile); ty++) {
          if (ty < 0 || ty >= n) continue;
          var wx = ((tx % n) + n) % n, key = st.z + '/' + wx + '/' + ty + '@' + tx, img = st.tiles[key];
          if (!img) {
            img = document.createElement('img'); img.className = 'tile'; img.alt = ''; img.draggable = false;
            img.src = gmServer() + '/tiles/' + st.z + '/' + wx + '/' + ty + '.png';
            img.onerror = function () { this.style.visibility = 'hidden'; };
            layer.appendChild(img); st.tiles[key] = img;
          }
          img.style.left = Math.round(tx * GMAP.tile - left) + 'px'; img.style.top = Math.round(ty * GMAP.tile - top) + 'px';
          want[key] = 1;
        }
      }
      Object.keys(st.tiles).forEach(function (k) { if (!want[k]) { st.tiles[k].remove(); delete st.tiles[k]; } });
      st.pins.forEach(function (pin) {
        var q = gmProject(pin.place.lat, pin.place.lon, st.z);
        pin.el.style.left = Math.round(q.x - left) + 'px'; pin.el.style.top = Math.round(q.y - top) + 'px';
      });
      if (st.open) { var q2 = gmProject(st.open.lat, st.open.lon, st.z); tip.style.left = Math.round(q2.x - left) + 'px'; tip.style.top = Math.round(q2.y - top) + 'px'; }
    }
    function setView(lat, lon, z) {
      st.z = Math.max(GMAP.minZ, Math.min(GMAP.maxZ, z));
      var c = gmProject(lat, lon, st.z); st.cx = c.x; st.cy = c.y; draw();
    }
    function zoomAt(dz, px, py) {                     // zoom keeping the point under the cursor in place
      var sz = size(), z2 = Math.max(GMAP.minZ, Math.min(GMAP.maxZ, st.z + dz)); if (z2 === st.z) return;
      if (px == null) { px = sz.w / 2; py = sz.h / 2; }
      var at = gmUnproject(st.cx - sz.w / 2 + px, st.cy - sz.h / 2 + py, st.z), k = Math.pow(2, z2 - st.z);
      var p = gmProject(at.lat, at.lon, z2);
      st.z = z2; st.cx = p.x - (px - sz.w / 2); st.cy = p.y - (py - sz.h / 2);
      Object.keys(st.tiles).forEach(function (k2) { st.tiles[k2].remove(); }); st.tiles = {}; draw();
      return k;
    }
    function pick(i, fromMap) {
      st.pins.forEach(function (p, j) { p.el.classList.toggle('on', j === i); });
      var pl = places[i]; if (!pl) return;
      st.open = pl; tip.textContent = pl.name; tip.style.display = 'block'; draw();
      if (fromMap && onPick) onPick(i);
    }
    places.forEach(function (pl, i) {
      var el = document.createElement('div'); el.className = 'gmap-pin'; el.title = pl.name;
      if (pl.kind && GM_KIND[pl.kind]) el.style.setProperty('--c', GM_KIND[pl.kind][0]);
      el.innerHTML = '<span></span>'; el.firstChild.textContent = String(i + 1);
      el.addEventListener('click', function (e) { e.stopPropagation(); pick(i, true); });
      view.appendChild(el); st.pins.push({ el: el, place: pl });
    });
    // drag, wheel, double-click and pinch
    var ptrs = {}, last = null, pinch = 0;
    view.addEventListener('pointerdown', function (e) {
      if (e.target.closest('.gmap-zoom, .gmap-attr, .gmap-pin')) return;
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY }; try { view.setPointerCapture(e.pointerId); } catch (err) {}
      last = { x: e.clientX, y: e.clientY }; view.classList.add('drag');
    });
    view.addEventListener('pointermove', function (e) {
      if (!ptrs[e.pointerId]) return;
      ptrs[e.pointerId] = { x: e.clientX, y: e.clientY };
      var ids = Object.keys(ptrs);
      if (ids.length === 2) {
        var a = ptrs[ids[0]], b = ptrs[ids[1]], d = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch && Math.abs(Math.log(d / pinch) / Math.LN2) >= 0.6) {
          var r = view.getBoundingClientRect(); zoomAt(d > pinch ? 1 : -1, (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top); pinch = d;
        } else if (!pinch) pinch = d;
        return;
      }
      if (last) { st.cx -= e.clientX - last.x; st.cy -= e.clientY - last.y; last = { x: e.clientX, y: e.clientY }; draw(); }
    });
    function up(e) { delete ptrs[e.pointerId]; if (!Object.keys(ptrs).length) { last = null; pinch = 0; view.classList.remove('drag'); } }
    view.addEventListener('pointerup', up); view.addEventListener('pointercancel', up);
    view.addEventListener('wheel', function (e) {
      if (!view.closest('.gmap-overlay') && !(e.ctrlKey || e.metaKey)) return;      // like the vector map: ⌘/Ctrl + scroll
      e.preventDefault(); var r = view.getBoundingClientRect();
      if (Math.abs(e.deltaY) > 2) zoomAt(e.deltaY < 0 ? 1 : -1, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    view.addEventListener('dblclick', function (e) { var r = view.getBoundingClientRect(); zoomAt(1, e.clientX - r.left, e.clientY - r.top); });
    var zoom = document.createElement('div'); zoom.className = 'gmap-zoom';
    zoom.innerHTML = '<button type="button" aria-label="Zoom in">+</button><button type="button" aria-label="Zoom out">−</button>';
    zoom.firstChild.onclick = function () { zoomAt(1); }; zoom.lastChild.onclick = function () { zoomAt(-1); };
    view.appendChild(zoom);
    var attr = document.createElement('div'); attr.className = 'gmap-attr';
    attr.innerHTML = '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors';
    view.appendChild(attr);
    var fit = gmFit(places, size().w, size().h); setView(fit.lat, fit.lon, fit.z);
    if (window.ResizeObserver) new ResizeObserver(function () { draw(); }).observe(view);
    return { kind: 'raster', pick: function (i) { var p = places[i]; if (p) { setView(p.lat, p.lon, Math.max(st.z, 15)); pick(i, false); } },
             setView: setView, resize: draw, big: draw, theme: function () {}, sleep: function () {} };
  }

  // ---- one map in an answer: wakes up when it scrolls into sight, sleeps when far away (few WebGL maps at once) ----
  var GM_LIVE = [];
  var GM_SEEN = window.IntersectionObserver ? new IntersectionObserver(function (es) {
    es.forEach(function (e) { var box = e.target; if (!box._gm) return; box._gm.seen = e.isIntersecting; if (e.isIntersecting) gmWake(box); });
  }, { rootMargin: '400px 0px' }) : null;
  function gmWake(box) {
    var g = box._gm; if (!g || g.ctrl || g.starting) return;
    g.starting = true;
    var canvas = g.canvas;
    function raster() {
      canvas.innerHTML = ''; canvas.className = 'gm-canvas raster';
      g.ctrl = gmMap(canvas, g.places, g.onPick); g.starting = false;
      if (g.sel >= 0) g.ctrl.pick(g.sel);
    }
    if (g.mode === 'raster' || !gmCanVector()) { g.mode = 'raster'; raster(); return; }
    gmVector(canvas, g.places, { cam: g.cam, onPick: g.onPick }).then(function (ctrl) {
      g.ctrl = ctrl; g.starting = false; g.mode = 'vector';
      if (g.sel >= 0) ctrl.pick(g.sel);
      GM_LIVE = GM_LIVE.filter(function (b) { return b !== box; }).concat([box]);
      while (GM_LIVE.length > 4) {                    // too many: the ones out of sight sleep
        var far = GM_LIVE.filter(function (b) { return !b._gm.seen && b !== box; })[0]; if (!far) break;
        gmSleep(far);
      }
    }, function (err) {
      var why = String((err && err.message) || err || '');
      window.ginkMapProblem = why;                    // for support: why this map is the old one
      if (/^(load|no maplibre|style 404)/.test(why)) GM_VECTOR.broken = why;   // this server or device can't: stop trying
      g.mode = 'raster'; raster();
    });
  }
  function gmSleep(box) {
    var g = box._gm; if (!g || !g.ctrl || g.ctrl.kind !== 'vector' || box.closest('.gmap-overlay')) return;
    g.cam = g.ctrl.cam(); g.ctrl.sleep(); g.ctrl = null; g.canvas.innerHTML = '';
    GM_LIVE = GM_LIVE.filter(function (b) { return b !== box; });
  }
  if (window.MutationObserver) new MutationObserver(function () {          // light / dark: the maps follow
    var t = gmTheme();
    GM_LIVE.forEach(function (b) { if (b._gm && b._gm.ctrl) b._gm.ctrl.theme(t); });
  }).observe(document.body, { attributes: true, attributeFilter: ['class'] });
  function gmBig(box, on) {                           // the map over the chat, bigger (Esc or the button: back)
    var g = box._gm; if (!g) return;
    if (on && !g.hold) {
      g.hold = document.createElement('div'); g.hold.className = 'gmap-hold'; g.hold.style.height = box.offsetHeight + 'px';
      box.parentNode.insertBefore(g.hold, box);
      var ov = document.createElement('div'); ov.className = 'gmap-overlay';
      ov.addEventListener('click', function (e) { if (e.target === ov) gmBig(box, false); });
      ov.appendChild(box); document.body.appendChild(ov);
      g.btn.setAttribute('aria-label', 'Smaller map'); g.btn.title = 'Smaller map'; g.btn.innerHTML = GM_SMALL;
      g.btn.focus();
    } else if (!on && g.hold) {
      var ov2 = box.parentNode; g.hold.parentNode.replaceChild(box, g.hold); g.hold = null; if (ov2) ov2.remove();
      g.btn.setAttribute('aria-label', 'Bigger map'); g.btn.title = 'Bigger map'; g.btn.innerHTML = GM_BIG;
    } else return;
    if (g.ctrl) setTimeout(function () { g.ctrl.big(on); }, 0);
  }
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    var ov = document.querySelector('.gmap-overlay .gmap'); if (ov) { e.stopPropagation(); gmBig(ov, false); }
  }, true);
  var GM_BIG = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>';
  var GM_SMALL = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/></svg>';
  var GM_DIR = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.8l9.2 9.2-9.2 9.2L2.8 12z"/><path d="M8.5 14v-2.5a1.5 1.5 0 0 1 1.5-1.5h5M13 7.8l2.2 2.2-2.2 2.2"/></svg>';

  function gmCards(box, places, strip) {              // the places under the map
    var g = box._gm;
    strip.className = 'gm-cards' + (places.length <= 2 ? ' few' : '');
    strip.setAttribute('role', 'list');
    places.forEach(function (p, i) {
      var k = GM_KIND[p.kind], card = document.createElement('div');
      card.className = 'gm-card'; card.tabIndex = 0; card.setAttribute('role', 'listitem'); card.style.setProperty('--c', k[0]);
      card.innerHTML = '<div class="gm-ph"><span class="gm-n"></span>' + gmSvg(p.kind, 26) + '</div>' +
        '<div class="gm-tx"><span class="gm-nm"></span><span class="gm-ct"><i></i><span></span></span><span class="gm-nt"></span></div>' +
        '<a class="gm-dir" target="_blank" rel="noopener">' + GM_DIR + '</a>';
      card.querySelector('.gm-n').textContent = String(i + 1);
      card.querySelector('.gm-nm').textContent = p.name; card.querySelector('.gm-nm').title = p.name;
      card.querySelector('.gm-ct span').textContent = k[1];
      var nt = card.querySelector('.gm-nt'); if (p.note) nt.textContent = p.note; else nt.remove();
      var dir = card.querySelector('.gm-dir'); dir.href = gmDirections(p);
      dir.setAttribute('aria-label', 'Directions to ' + p.name); dir.title = 'Directions';
      card.setAttribute('aria-label', (i + 1) + '. ' + p.name + ', ' + k[1] + (p.note ? '. ' + p.note : ''));
      function choose() { g.sel = i; gmSelect(box, i, false); if (g.ctrl) g.ctrl.pick(i); else gmWake(box); }
      card.addEventListener('click', function (e) { if (e.target.closest('a')) return; choose(); });
      card.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(); } });
      strip.appendChild(card);
      gmPhoto(p).then(function (u) {
        if (!u) return;
        var im = new Image(); im.alt = ''; im.decoding = 'async'; im.referrerPolicy = 'no-referrer';
        im.onload = function () { card.querySelector('.gm-ph').appendChild(im); var ic = card.querySelector('.gm-ph svg'); if (ic) ic.remove(); };
        im.src = u;
      });
    });
  }
  function gmSelect(box, i, scroll) {
    var g = box._gm; if (!g) return; g.sel = i;
    var cards = g.strip.children;
    Array.prototype.forEach.call(cards, function (c, j) { c.classList.toggle('on', j === i); });
    var c = cards[i];
    if (scroll && c) {                                // only the strip moves, never the chat
      var left = c.offsetLeft - 10, view = [g.strip.scrollLeft, g.strip.scrollLeft + g.strip.clientWidth];
      if (c.offsetLeft < view[0] || c.offsetLeft + c.offsetWidth > view[1]) g.strip.scrollTo({ left: Math.max(0, left), behavior: 'smooth' });
    }
  }

  window.upgradeMaps = function (root) {             // ```map blocks -> live maps, by themselves
    Array.prototype.slice.call((root || document).querySelectorAll('.code-block')).forEach(function (block) {
      var label = block.querySelector('.code-block-label');
      var lang = (block.getAttribute('data-lang') || (label ? label.textContent : '')).trim().toLowerCase();
      if (lang !== 'map') return;
      var data; try { data = JSON.parse((block.querySelector('code') || block).textContent); } catch (e) { return; }
      var raw = (data && (data.places || data.markers)) || [];
      raw = raw.filter(function (p) { return p && (p.name || p.query); }).slice(0, 10);
      if (!raw.length) return;
      var title = String(data.title || (raw.length === 1 ? raw[0].name || raw[0].query : raw.length + ' places')).slice(0, 120);
      var box = document.createElement('div'); box.className = 'gmap';
      var view = document.createElement('div'); view.className = 'gmap-view'; view.setAttribute('role', 'region');
      view.setAttribute('aria-label', 'Map: ' + title);
      var canvas = document.createElement('div'); canvas.className = 'gm-canvas';
      var chip = document.createElement('div'); chip.className = 'gm-chip';
      chip.innerHTML = gmSvg('other', 15) + '<span></span>'; chip.lastChild.textContent = title;
      var btn = document.createElement('button'); btn.type = 'button'; btn.className = 'gm-bigbtn';
      btn.setAttribute('aria-label', 'Bigger map'); btn.title = 'Bigger map'; btn.innerHTML = GM_BIG;
      btn.addEventListener('click', function () { gmBig(box, !box._gm.hold); });
      view.appendChild(canvas); view.appendChild(chip); view.appendChild(btn);
      var strip = document.createElement('div');
      box.appendChild(view); box.appendChild(strip);
      block.parentNode.replaceChild(box, block);
      box._gm = { canvas: canvas, strip: strip, btn: btn, places: [], sel: -1, ctrl: null, seen: false,
                  onPick: function (i) { gmSelect(box, i, true); } };
      Promise.all(raw.map(function (p) {              // coordinates given, or looked up by name / address
        var lat = parseFloat(p.lat), lon = parseFloat(p.lon != null ? p.lon : p.lng);
        var place = { name: String(p.name || p.query).slice(0, 120), note: String(p.note || '').slice(0, 240), category: p.category,
                      kind: '', lat: lat, lon: lon };
        place.kind = gmKind({ category: p.category || p.kind || p.type, name: place.name, note: place.note });
        if (isFinite(lat) && isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 && !(lat === 0 && lon === 0))
          return Promise.resolve(place);
        return gmGeocode(p.query || p.name).then(function (g) { if (!g) return null; place.lat = g.lat; place.lon = g.lon; return place; });
      })).then(function (found) {
        var places = found.filter(Boolean);
        box._gm.places = places;
        if (!places.length) {
          view.remove(); strip.remove(); var n = document.createElement('div'); n.className = 'gmap-note';
          n.textContent = 'Couldn’t find these places on the map.'; box.appendChild(n); return;
        }
        gmCards(box, places, strip);
        if (raw.length > places.length) {
          var miss = document.createElement('div'); miss.className = 'gmap-note';
          miss.textContent = (raw.length - places.length) + ' place' + (raw.length - places.length === 1 ? '' : 's') + ' couldn’t be found on the map.';
          box.appendChild(miss);
        }
        if (GM_SEEN) GM_SEEN.observe(box); else gmWake(box);
      });
    });
  };

  // ============================ voice messages ============================
  // Press and hold the microphone: record; let go: send. A quick tap still dictates into the box.
  var VM = { timer: 0, on: false, rec: null, chunks: [], start: 0, tick: 0, stream: null, swallow: false, cancel: false };
  function vmBar() {
    var bar = document.getElementById('vm-bar');
    if (!bar) {
      bar = document.createElement('div'); bar.id = 'vm-bar'; bar.setAttribute('role', 'status');
      bar.innerHTML = '<span class="dot"></span><span class="tm">0:00</span><span class="hint"></span>';
      var wrap = document.getElementById('composer') || document.getElementById('composer-wrap') || document.body;
      if (getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';
      wrap.appendChild(bar);
    }
    return bar;
  }
  function vmShow(on, hint) {
    var bar = vmBar(), mic = document.getElementById('mic');
    bar.classList.toggle('on', on); if (mic) mic.classList.toggle('vm-rec', on);
    if (hint) bar.querySelector('.hint').textContent = hint;
    clearInterval(VM.tick);
    if (on) {
      VM.start = Date.now(); bar.querySelector('.tm').textContent = '0:00';
      VM.tick = setInterval(function () {
        var s = Math.floor((Date.now() - VM.start) / 1000);
        bar.querySelector('.tm').textContent = Math.floor(s / 60) + ':' + ('0' + s % 60).slice(-2);
        if (s >= 120) vmStop(false);                    // two minutes at most
      }, 250);
    }
  }
  function vmPageRecorder() { return window.ginkVoiceRecorder === 'page' && window.MediaRecorder && navigator.mediaDevices; }
  function vmStart() {
    if (VM.on) return;
    VM.on = true; VM.swallow = true; VM.cancel = false;
    if (!vmPageRecorder()) {                          // the apps: their own microphone code records
      vmShow(true, 'Listening… speak, then pause · Esc to cancel');
      ginkEmit('voice_message', { action: 'start' });
      return;
    }
    vmShow(true, 'Recording · let go to send · Esc to cancel');
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      if (!VM.on) { stream.getTracks().forEach(function (t) { t.stop(); }); return; }
      VM.stream = stream; VM.chunks = [];
      var type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'].filter(function (t) {
        try { return MediaRecorder.isTypeSupported(t); } catch (e) { return false; } })[0];
      var rec = type ? new MediaRecorder(stream, { mimeType: type }) : new MediaRecorder(stream);
      VM.rec = rec;
      rec.ondataavailable = function (e) { if (e.data && e.data.size) VM.chunks.push(e.data); };
      rec.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        var secs = Math.round((Date.now() - VM.start) / 1000), blob = new Blob(VM.chunks, { type: rec.mimeType || type || 'audio/webm' });
        VM.rec = null; VM.stream = null;
        if (VM.cancel || secs < 1 || !blob.size) return;
        var fmt = /mp4/.test(blob.type) ? 'm4a' : /ogg/.test(blob.type) ? 'ogg' : 'webm', r = new FileReader();
        r.onload = function () {
          ginkEmit('voice_message', { action: 'done', data: String(r.result).split(',')[1] || '', format: fmt, secs: secs,
                                      url: URL.createObjectURL(blob) });
        };
        r.readAsDataURL(blob);
      };
      rec.start();
    }).catch(function () {
      VM.on = false; vmShow(false);
      lmSay('Allow the microphone to send voice messages.');
    });
  }
  function vmStop(cancel) {
    clearTimeout(VM.timer);
    if (!VM.on) return;
    VM.on = false; VM.cancel = !!cancel; vmShow(false);
    if (VM.rec) { try { VM.rec.stop(); } catch (e) {} }
    else if (VM.stream) VM.stream.getTracks().forEach(function (t) { t.stop(); });
    if (!vmPageRecorder()) ginkEmit('voice_message', { action: cancel ? 'cancel' : 'stop' });
  }
  window.voiceMessageDone = function () { if (VM.on) { VM.on = false; vmShow(false); } };   // the apps: listening ended
  window.markVoiceMessage = function (url, secs, text) {   // the message you just sent was a voice message
    var rows = Array.prototype.slice.call(document.querySelectorAll('#feed .row.user')).reverse(), row = rows[0];
    if (text) row = rows.filter(function (r) { var b = r.querySelector('.bubble'); return b && b.innerText.trim() === String(text).trim(); })[0];
    if (!row || row.querySelector('.vmsg')) return;
    var v = document.createElement('div'); v.className = 'vmsg';
    var label = document.createElement('span'); label.textContent = '🎤 Voice message' + (secs ? ' · ' + Math.floor(secs / 60) + ':' + ('0' + secs % 60).slice(-2) : '');
    v.appendChild(label);
    if (url) { var a = document.createElement('audio'); a.controls = true; a.src = url; a.preload = 'metadata'; v.appendChild(a); }
    row.insertBefore(v, row.firstChild);
  };
  document.addEventListener('pointerdown', function (e) {
    var mic = e.target.closest && e.target.closest('#mic'); if (!mic || mic.disabled || e.button > 0) return;
    VM.swallow = false; clearTimeout(VM.timer);
    VM.timer = setTimeout(vmStart, 380);                // held: a voice message
  });
  document.addEventListener('pointerup', function () { clearTimeout(VM.timer); if (VM.on && vmPageRecorder()) vmStop(false); });
  document.addEventListener('pointercancel', function () { clearTimeout(VM.timer); if (VM.on) vmStop(true); });
  document.addEventListener('click', function (e) {    // after holding, the release isn't a tap (no dictation)
    if (VM.swallow && e.target.closest && e.target.closest('#mic')) { e.preventDefault(); e.stopImmediatePropagation(); VM.swallow = false; }
  }, true);
  document.addEventListener('contextmenu', function (e) { if (e.target.closest && e.target.closest('#mic')) e.preventDefault(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && VM.on) vmStop(true); });

  // ============================ screen view ============================
  // Live with the screen instead of the camera. Browsers share a screen, window or tab (getDisplayMedia); the apps
  // send frames themselves (liveScreenFrame). openScreenView(question) starts it -- and asks -- by itself.
  window.GINK_SCREEN_RE = /\b(?:look at|see|check|read|watch|what'?s on|whats on|what is on|help me with|explain|share)\b[^.?!\n]{0,40}\bmy (?:screen|display|monitor)\b|\bscreen ?shar(?:e|ing)\b|\bshare (?:my |the )?screen\b/i;
  window.screenViewAvailable = function () {
    return !!(window.GINK_NATIVE_SCREEN || (navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia));
  };
  window.liveScreenFrame = function (dataUrl) {      // the apps: the newest picture of the screen
    if (!LIVE || !LIVE.screen || LIVE.stream) return;
    var img = LIVE.el.querySelector('img.live-shot'); if (!img) return;
    img.onload = function () { if (LIVE && LIVE.pendingQ && LIVE.ask) { var q = LIVE.pendingQ; LIVE.pendingQ = ''; LIVE.ask(q); } };
    img.src = dataUrl;
  };
  window.openScreenView = function (question) {
    if (!window.screenViewAvailable()) { lmSay('Screen view isn’t available here: use the Gink app or a computer browser.'); return false; }
    window.LIVE_PENDING = String(question || '');
    if (window.openLive) openLive('screen');
    return true;
  };
"""


def inject(page: str) -> str:
    """Adds the maps, voice messages and screen view to the chat page."""
    i = page.index("</style>")
    page = page[:i] + CSS + page[i:]
    i = page.rindex("</script>")
    return page[:i] + JS + page[i:]
