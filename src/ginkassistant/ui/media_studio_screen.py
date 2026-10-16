"""
Media Studio -- create images, keep them in a gallery.

* Prompt + style presets (Photo, Illustration, 3D, Sticker, Poster, Logo,
  Watercolour, Anime) + aspect ratio (square, wide, tall, ...).
* Images are made through YOUR Gink server (services/image_service.py ->
  POST /media/image), which holds the Google key and applies the plan's daily
  image limit. The counter shows what's left today.
* Gallery of everything you've made: open, save as, reuse the prompt, delete.
* Video: Google is retiring the Veo models (22 Oct 2026); video returns once
  it's moved to their replacement -- the tab says so instead of failing.

Drawn as one HTML page in a WebView, talking to Python through the same
polling bridge as the chat page.
"""

import asyncio
import json

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from ..services.api_client import ApiClient, ApiError
from ..services.image_service import ASPECTS, STYLES, ImageService
from ..services.paths import data_dir
from .theme import css_vars

STYLE_LABELS = {"": "None", "photo": "Photo", "illustration": "Illustration", "3d": "3D", "sticker": "Sticker",
                "poster": "Poster", "logo": "Logo", "watercolor": "Watercolour", "anime": "Anime"}
ASPECT_LABELS = {"1:1": "Square", "16:9": "Wide", "9:16": "Tall", "4:3": "Landscape", "3:4": "Portrait"}

PAGE = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { __THEME__ }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text-main); }
  header { display: flex; align-items: center; padding: 14px 20px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--bg); z-index: 5; }
  header h1 { font-size: 18px; margin: 0 0 0 12px; flex: 1; }
  .btn { font: inherit; font-size: 14px; border: 1px solid var(--border); background: var(--bg); color: var(--text-main); border-radius: 999px; padding: 7px 15px; cursor: pointer; }
  .btn:hover { border-color: var(--accent); color: var(--accent); }
  .btn.primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); font-weight: 600; }
  .btn.primary:disabled { opacity: 0.55; cursor: default; }
  .tabs { display: flex; padding: 0 20px; border-bottom: 1px solid var(--border); }
  .tabs button { border: none; background: none; font: inherit; font-size: 14px; padding: 12px 4px; margin-right: 22px; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; }
  .tabs button.on { color: var(--text-main); border-bottom-color: var(--accent); font-weight: 600; }
  main { max-width: 1100px; margin: 0 auto; padding: 22px 20px 60px; }
  .create { border: 1px solid var(--border); border-radius: 18px; padding: 16px; box-shadow: 0 2px 12px rgba(0,0,0,0.04); }
  textarea { width: 100%; min-height: 84px; border: none; outline: none; resize: vertical; font: inherit; font-size: 15px; color: var(--text-main); background: transparent; }
  .label { font-size: 12.5px; color: var(--text-muted); margin: 12px 0 6px; }
  .chips { display: flex; flex-wrap: wrap; }
  .chip { font: inherit; font-size: 13px; border: 1px solid var(--border); background: var(--bg); color: var(--text-main); border-radius: 999px; padding: 5px 12px; margin: 0 6px 6px 0; cursor: pointer; display: inline-flex; align-items: center; }
  .chip.on { border-color: var(--accent); background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .chip i { display: inline-block; border: 1.6px solid currentColor; border-radius: 2px; margin-right: 7px; }
  .row { display: flex; align-items: center; margin-top: 12px; }
  .row .left { flex: 1; font-size: 13px; color: var(--text-muted); }
  .msg { font-size: 13.5px; margin-top: 10px; min-height: 18px; }
  .msg.err { color: var(--danger); } .msg.ok { color: var(--accent); }
  .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; margin-top: 22px; }
  .tile { position: relative; border-radius: 14px; overflow: hidden; border: 1px solid var(--border); background: var(--elevated); }
  .tile img { display: block; width: 100%; height: auto; cursor: zoom-in; }
  .tile .cap { padding: 8px 10px; font-size: 12.5px; color: var(--text-muted); line-height: 1.35; max-height: 3.9em; overflow: hidden; }
  .tile .acts { display: flex; padding: 0 8px 8px; flex-wrap: wrap; }
  .tile .acts button { font: inherit; font-size: 12px; border: 1px solid var(--border); background: var(--bg); color: var(--text-main); border-radius: 999px; padding: 4px 10px; margin: 0 4px 4px 0; cursor: pointer; }
  .tile .acts button:hover { border-color: var(--accent); color: var(--accent); }
  .tile .acts button.del:hover { border-color: var(--danger); color: var(--danger); }
  /* "creating" tile: the same soft green glow as in the chat */
  .tile.pending { min-height: 240px; position: relative; overflow: hidden; background: var(--bg); }
  .tile.pending::before { content: ""; position: absolute; left: -20%; right: -20%; top: -60%; height: 140%;
    background: radial-gradient(ellipse at 50% 0%, rgba(168,240,60,0.38) 0%, rgba(168,240,60,0.16) 38%, rgba(168,240,60,0.05) 62%, rgba(168,240,60,0) 75%);
    animation: glow-breathe 3.2s ease-in-out infinite; }
  .tile.pending::after { content: ""; position: absolute; top: 0; bottom: 0; width: 45%; left: -50%;
    background: linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,0.55), rgba(255,255,255,0)); animation: glow-sweep 2.6s ease-in-out infinite; }
  @keyframes glow-breathe { 0%, 100% { opacity: 0.75; transform: scale(1); } 50% { opacity: 1; transform: scale(1.06); } }
  @keyframes glow-sweep { from { left: -50%; } to { left: 110%; } }
  .tile.pending span { position: absolute; left: 0; right: 0; bottom: 16px; text-align: center; font-size: 13px; color: var(--text-muted); z-index: 1; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .empty { text-align: center; color: var(--text-muted); padding: 50px 0; font-size: 14px; }
  .soon { text-align: center; padding: 60px 20px; color: var(--text-muted); line-height: 1.6; }
  .soon b { color: var(--text-main); font-size: 16px; display: block; margin-bottom: 6px; }
  @media (max-width: 560px) { .gallery { grid-template-columns: repeat(2, 1fr); gap: 8px; } main { padding: 14px 12px 40px; } }
</style></head><body>
<header><button class="btn" id="back">&larr; Back</button><h1>Media Studio</h1></header>
<div class="tabs"><button class="on" data-tab="images">Images</button><button data-tab="video">Video</button></div>
<main>
  <section id="tab-images">
    <div class="create">
      <textarea id="prompt" placeholder="Describe the image you want \u2014 e.g. a sunset over the Dakar corniche, colourful fishing boats in the foreground"></textarea>
      <div class="label">Style</div><div class="chips" id="styles"></div>
      <div class="label">Shape</div><div class="chips" id="aspects"></div>
      <div class="row"><div class="left" id="usage"></div><button class="btn primary" id="create">Create image</button></div>
      <div class="msg" id="msg"></div>
    </div>
    <div class="gallery" id="gallery"></div>
  </section>
  <section id="tab-video" style="display:none">
    <div class="soon"><b>Video is coming back soon</b>Google is retiring the video models Media Studio used (on 22 October 2026).<br>
      Video creation returns once Gink moves to Google's new video model.</div>
  </section>
</main>
<script>
  var ginkEvents = [];
  function ginkEmit(type, value) { ginkEvents.push({type: type, value: value === undefined ? null : value}); }
  function ginkTake() { var out = JSON.stringify(ginkEvents); ginkEvents = []; return out; }
  var STYLES = __STYLES__, ASPECTS = __ASPECTS__, state = {style: 'photo', aspect: '1:1', busy: false};
  function $(id) { return document.getElementById(id); }
  function esc(t) { var d = document.createElement('div'); d.textContent = t == null ? '' : String(t); return d.innerHTML; }
  function chips() {
    $('styles').innerHTML = STYLES.map(function (s) { return '<button class="chip' + (state.style === s[0] ? ' on' : '') + '" data-style="' + s[0] + '">' + esc(s[1]) + '</button>'; }).join('');
    $('aspects').innerHTML = ASPECTS.map(function (a) {
      var p = a[0].split(':'), w = +p[0], h = +p[1], k = 13 / Math.max(w, h);
      return '<button class="chip' + (state.aspect === a[0] ? ' on' : '') + '" data-aspect="' + a[0] + '"><i style="width:' + Math.round(w * k) + 'px;height:' + Math.round(h * k) + 'px"></i>' + esc(a[1]) + '</button>'; }).join('');
  }
  function setGallery(items) {
    var g = $('gallery'), pending = g.querySelector('.pending');
    if (!items.length) { g.innerHTML = '<div class="empty" style="grid-column:1/-1">Your images will appear here.</div>'; if (pending) g.insertBefore(pending, g.firstChild); return; }
    g.innerHTML = items.map(function (it) {
      return '<div class="tile" data-name="' + esc(it.name) + '"><img src="' + it.thumb + '" alt=""><div class="cap">' + esc(it.prompt) + '</div>' +
        '<div class="acts"><button data-a="open">Open</button><button data-a="save">Save as\u2026</button><button data-a="reuse">Use prompt</button><button data-a="delete" class="del">Delete</button></div></div>'; }).join('');
    if (pending) g.insertBefore(pending, g.firstChild);
    Array.prototype.forEach.call(g.querySelectorAll('.tile:not(.pending)'), function (t, i) { t.setAttribute('data-prompt', items[i].prompt); });
  }
  function setUsage(text) { $('usage').textContent = text || ''; }
  function setBusy(on) {
    state.busy = on; $('create').disabled = on; $('create').textContent = on ? 'Creating\u2026' : 'Create image';
    var g = $('gallery'), p = g.querySelector('.pending');
    if (on && !p) { p = document.createElement('div'); p.className = 'tile pending'; p.innerHTML = '<span>Creating your image\u2026</span>'; g.insertBefore(p, g.firstChild); var e = g.querySelector('.empty'); if (e) e.parentNode.removeChild(e); }
    if (!on && p) p.parentNode.removeChild(p);
  }
  function setMsg(text, kind) { var m = $('msg'); m.textContent = text || ''; m.className = 'msg' + (kind ? ' ' + kind : ''); }
  document.addEventListener('DOMContentLoaded', function () {
    chips();
    $('back').addEventListener('click', function () { ginkEmit('back'); });
    document.querySelector('.tabs').addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      Array.prototype.forEach.call(document.querySelectorAll('.tabs button'), function (x) { x.classList.toggle('on', x === b); });
      $('tab-images').style.display = b.getAttribute('data-tab') === 'images' ? '' : 'none';
      $('tab-video').style.display = b.getAttribute('data-tab') === 'video' ? '' : 'none';
    });
    document.querySelector('.create').addEventListener('click', function (e) {
      var s = e.target.closest('[data-style]'), a = e.target.closest('[data-aspect]');
      if (s) { state.style = s.getAttribute('data-style'); chips(); }
      if (a) { state.aspect = a.getAttribute('data-aspect'); chips(); }
    });
    $('create').addEventListener('click', function () {
      var p = $('prompt').value.trim();
      if (!p) { setMsg('Describe the image first.', 'err'); $('prompt').focus(); return; }
      if (state.busy) return;
      setMsg(''); setBusy(true); ginkEmit('create', {prompt: p, style: state.style, aspect: state.aspect});
    });
    $('prompt').addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) $('create').click(); });
    $('gallery').addEventListener('click', function (e) {
      var t = e.target.closest('.tile'); if (!t || t.classList.contains('pending')) return;
      var b = e.target.closest('button'), name = t.getAttribute('data-name');
      var act = b ? b.getAttribute('data-a') : (e.target.tagName === 'IMG' ? 'open' : null);
      if (!act) return;
      if (act === 'reuse') { $('prompt').value = t.getAttribute('data-prompt') || ''; $('prompt').focus(); window.scrollTo(0, 0); return; }
      if (act === 'delete' && !window.confirm('Delete this image?')) return;
      ginkEmit(act, name);
    });
    ginkEmit('ready');
  });
</script></body></html>"""


class MediaStudio:
    def __init__(self, app, on_back):
        self.app = app
        self.on_back = on_back
        self.images = getattr(app, "image_service", None) or ImageService(
            str(data_dir(app) / "files"), lambda: app.state.base_url, lambda: getattr(app, "session_token", None))
        page = (PAGE.replace("__THEME__", css_vars())
                .replace("__STYLES__", json.dumps([[k, STYLE_LABELS[k]] for k in STYLES]))
                .replace("__ASPECTS__", json.dumps([[a, ASPECT_LABELS[a]] for a in ASPECTS])))
        self.web = toga.WebView(style=Pack(flex=1))
        self.web.set_content("https://gink.local/media", page)
        self.token = object()
        app._media_studio_token = self.token
        self.view = toga.Box(children=[self.web], style=Pack(direction=COLUMN, flex=1))
        self.view._studio = self                     # for tests
        try:
            asyncio.get_event_loop().create_task(self.run())
        except RuntimeError:
            pass

    async def js(self, script: str):
        try:
            await asyncio.wait_for(self.web.evaluate_javascript(script), timeout=3)
        except Exception:
            pass

    async def call(self, fn, *args):
        await self.js(f"{fn}({', '.join(json.dumps(a) for a in args)})")

    async def poll(self):
        try:
            raw = await asyncio.wait_for(self.web.evaluate_javascript("ginkTake()"), timeout=2)
            data = json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
            return json.loads(data) if isinstance(data, str) else (data if isinstance(data, list) else [])
        except Exception:
            return []

    def alive(self):
        return getattr(self.app, "_media_studio_token", None) is self.token

    async def run(self):
        await asyncio.sleep(0.4)
        while self.alive():
            for ev in await self.poll():
                asyncio.create_task(self.handle(ev))
            await asyncio.sleep(0.15)

    async def refresh_gallery(self):
        loop = asyncio.get_event_loop()
        items = []
        for it in self.images.gallery()[:60]:
            try:
                thumb = await loop.run_in_executor(None, self.images.thumb_data_url, it["name"], 480)
            except Exception:
                continue
            items.append({"name": it["name"], "prompt": it.get("prompt", ""), "thumb": thumb})
        await self.call("setGallery", items)

    async def refresh_usage(self):
        token = getattr(self.app, "session_token", None)
        if not token:
            return await self.call("setUsage", "Sign in again to create images.")
        try:
            u = await ApiClient(self.app.state.base_url).ai_usage(token)
            if "images_limit" in u:
                left = max(0, u["images_limit"] - u.get("images_used", 0))
                await self.call("setUsage", f"{left} of {u['images_limit']} images left today"
                                            + ("" if u.get("plan") == "pro" else " \u00b7 more with Gink Pro"))
        except Exception:
            pass

    async def handle(self, ev):
        kind, value = ev.get("type"), ev.get("value")
        if kind == "ready":
            await self.refresh_gallery()
            await self.refresh_usage()
        elif kind == "back":
            self.app._media_studio_token = None
            self.on_back()
        elif kind == "create" and isinstance(value, dict):
            try:
                await self.images.create(value.get("prompt", ""), value.get("aspect", "1:1"), value.get("style", ""))
                await self.call("setBusy", False)
                await self.call("setMsg", "Done \u2014 saved to your gallery.", "ok")
                await self.refresh_gallery()
            except ApiError as exc:
                await self.call("setBusy", False)
                await self.call("setMsg", str(exc), "err")
            except Exception as exc:
                await self.call("setBusy", False)
                await self.call("setMsg", f"The image couldn't be created ({exc.__class__.__name__}).", "err")
            await self.refresh_usage()
        elif kind in ("open", "save") and value:
            opener = getattr(self.app, "gink_file_action", None)
            if opener:
                await opener(kind, str(value))
        elif kind == "delete" and value:
            self.images.delete(str(value))
            await self.refresh_gallery()


def build_media_studio_screen(app, on_back):
    return MediaStudio(app, on_back).view
