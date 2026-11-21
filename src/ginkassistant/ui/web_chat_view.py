"""
Chat feed rendered via toga.WebView -- real HTML/CSS/JS, not just native
Toga widgets, per explicit request to use HTML/CSS/JS alongside Python
rather than relying only on Pack-styled widgets. This is what actually
gets rounded bubbles, a real shadow, proper markdown rendering, and
syntax-highlighted code with a working Copy button -- none of which
toga.Pack can do (confirmed earlier: no border-radius, no box-shadow, no
border-color support at all).

API used (confirmed against Toga's own docs before building this):
  web_view.set_content(root_url, html)      -- load the page once
  await web_view.evaluate_javascript(js)    -- call into it afterward
On Android and Windows, a JS error here fails silently (returns None,
raises nothing) rather than surfacing an exception -- worth testing the
JS on those platforms specifically rather than assuming "no error" means
"worked".

Streams raw text into the DOM token-by-token as it arrives (cheap, no
flicker), then replaces that one message with fully-parsed
markdown+syntax-highlighted HTML once the response is complete --
re-parsing markdown on every token would be wasteful and would flicker
the whole message on every update.

The header/sidebar/input bar stay native Toga widgets -- they're plain
layout and form controls with no need for CSS, and native widgets are
simpler and more predictable for text entry than reimplementing an
<input> inside a WebView and bridging its events back to Python.

Real link-handling bug, two attempts: clicking a real link in a reply
navigated the WHOLE chat WebView away to that external site, with no way
back -- since the WebView IS the chat feed, that meant losing it
entirely. First fix used toga.WebView's on_navigation_starting hook to
block external navigation and hand it to webbrowser.open() instead --
that part worked, but it turned out Toga's own internal handling of this
hook has a bug: an internal cleanup step that runs after ANY
on_navigation_starting call (regardless of what it returns) tries to
reset the widget's tracked URL, and crashes doing so ("WebView can only
display http:// and https:// URLs") when the page was loaded via
set_content() rather than a plain URL -- confirmed from the actual
traceback, not guessed. Since that crash happens in Toga's own code
after the handler runs, no return-value logic on this end could have
avoided it.

Fixed instead at the JS level, inside the page itself: clicking a link
calls e.preventDefault() and hands the URL to Python to open (see the <script>
  // Fallbacks for older web engines (some older Android phones)
  if (window.NodeList && !NodeList.prototype.forEach) NodeList.prototype.forEach = Array.prototype.forEach;
  if (window.Element && !Element.prototype.matches) Element.prototype.matches = Element.prototype.webkitMatchesSelector || Element.prototype.msMatchesSelector;
  if (window.Element && !Element.prototype.closest) Element.prototype.closest = function (sel) {
    var el = this; while (el && el.nodeType === 1) { if (el.matches(sel)) return el; el = el.parentElement; } return null;
  };
block below), which never touches on_navigation_starting or Toga's
buggy cleanup at all. This relies on the standard, common behavior of
native WebView components (WKWebView, WebView2, WebKitGTK, Android
WebView) delegating "open in new window" requests to the system's
default browser rather than opening a real new window themselves, since
an embedded WebView generally can't -- a reasonable expectation across
these engines, though not something confirmed Toga-specific the way the
on_navigation_starting API itself was, so it's worth actually testing
link clicks after this change rather than assuming.
"""

import json

import toga
from toga.style import Pack

from .branding import BRAND_TILE_DATA_URI, LOGO_DATA_URI, LOGO_SPINNER_DATA_URI
from .theme import css_vars
from ..services.markdown_render import PYGMENTS_CSS, render_markdown_body

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, interactive-widget=resizes-content">
<style>
  :root { __THEME_VARS__ }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    background: var(--bg);
    font-family: -apple-system, 'Segoe UI', Roboto, sans-serif;
    color: var(--text-main);
    font-size: 15px;
    line-height: 1.6;
    height: 100%;
    overflow: hidden;
    overscroll-behavior: none;
    -webkit-text-size-adjust: 100%;
  }
  /* ---------- the app shell (0.1.155) ----------
     The page itself never scrolls: #shell is exactly the visible area (sized from visualViewport by
     fitViewport(), so the phone keyboard can't push it around or leave it behind), the conversation
     scrolls inside #scroller, the composer sits at the bottom of the shell, and #headbar keeps the top
     solid so replies never show through the header. */
  :root { --app-h: 100vh; }
  @supports (height: 100dvh) { :root { --app-h: 100dvh; } }
  #shell { position: fixed; top: 0; left: 0; right: 0; height: var(--app-h);
    transition: left 0.28s cubic-bezier(0.22, 1, 0.36, 1), right 0.28s cubic-bezier(0.22, 1, 0.36, 1); }
  #scroller { position: absolute; top: 0; left: 0; right: 0; bottom: 0; overflow-x: hidden; overflow-y: auto;
    -webkit-overflow-scrolling: touch; overscroll-behavior-y: contain; }
  #headbar { position: absolute; top: 0; left: 0; right: 0; height: calc(54px + env(safe-area-inset-top, 0px)); z-index: 4;
    background: var(--bg); pointer-events: none; opacity: 0; transition: opacity 0.25s, box-shadow 0.25s; }
  body:not(.home) #headbar { opacity: 1; }
  body.scrolled:not(.home) #headbar { box-shadow: 0 1px 0 var(--border), 0 6px 18px rgba(28, 33, 29, 0.05); }
  ::selection { background: var(--accent); color: var(--on-accent); }
  a { color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--accent-soft); }
  a:hover { border-bottom-color: var(--accent); }
  a { cursor: pointer; }
  a.opening { opacity: 0.55; }
  a[href^="http"]::after { content: " \\2197"; font-size: 0.8em; }
  #feed { max-width: 760px; margin: 0 auto; padding: calc(60px + env(safe-area-inset-top, 0px)) 20px calc(var(--composer-h, 150px) + 40px); }
  @media (max-width: 520px) { #feed { padding-left: 16px; padding-right: 16px; } }
  #welcome {
    text-align: center;
    margin-top: 72px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  #welcome .logo {
    width: 88px; height: 88px; margin-bottom: 18px;
    padding: 14px; border-radius: 26px; background: var(--logo-tile);
    box-shadow: 0 8px 24px rgba(14, 22, 17, 0.18);
    animation: gink-enter 0.6s ease-out, gink-breathe 3.2s ease-in-out 0.6s infinite;
  }
  @keyframes gink-enter {
    from { opacity: 0; transform: scale(0.75) translateY(12px); }
    to { opacity: 1; transform: scale(1) translateY(0); }
  }
  @keyframes gink-breathe {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.04); }
  }
  @media (prefers-reduced-motion: reduce) {
    #welcome .logo, .gink-spinner { animation: none; }
  }
  #welcome p { color: var(--text-muted); font-size: 15px; margin: 8px 0 0; max-width: 420px; }
  .row { display: flex; margin-bottom: 18px; }
  .row.user { margin-bottom: 2px; }          /* its action row (copy, edit) already leaves the space */
  .row.user { justify-content: flex-end; }
  .bubble {
    max-width: 460px;
    padding: 11px 16px;
    border-radius: 18px 18px 4px 18px;
    background: var(--elevated);
    border: 1px solid var(--border);
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  .assistant-text {
    max-width: 720px;
    min-width: 0;                      /* a flex item: may shrink, so a wide table can't widen the page */
    white-space: pre-wrap;
    word-wrap: break-word;
    overflow-wrap: anywhere;
  }
  .row > .assistant-text { flex: 1 1 auto; }
  .assistant-text img { max-width: 100%; height: auto; }
  .assistant-text.rendered { white-space: normal; }
  .assistant-text.rendered p:first-child { margin-top: 0; }
  .assistant-text strong { color: var(--text-main); }
  .assistant-text h1, .assistant-text h2, .assistant-text h3 { color: var(--text-main); line-height: 1.3; }
  blockquote { margin: 10px 0; padding: 2px 14px; border-left: 3px solid var(--accent); color: var(--text-muted); }
  pre {
    background: #10171A;
    color: #E6EDE8;
    padding: 16px;
    margin: 0;
    overflow-x: auto;
  }
  code { font-family: 'SF Mono', Consolas, monospace; font-size: 13px; }
  .code-block {
    max-width: 720px;
    margin: 10px 0;
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--border);
  }
  .code-block-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 12px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  .code-block-label {
    flex: 1;
    font-family: 'SF Mono', Consolas, monospace;
    font-size: 12px;
    color: var(--text-muted);
  }
  .code-copy-btn, .code-download-btn, .doc-copy-btn, .doc-download-btn {
    background: var(--elevated);
    color: var(--text-main);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    cursor: pointer;
  }
  .code-copy-btn:hover, .code-download-btn:hover,
  .doc-copy-btn:hover, .doc-download-btn:hover { border-color: var(--accent); color: var(--accent); }
  /* spinner rides at the end of the reply while it's being written,
     moving down with the text; finished replies keep a still mark */
  .gink-spinner {
    display: block; width: 30px; height: 30px; margin: 8px 0 2px;
    animation: gink-spin 1.6s linear infinite;
  }
  .assistant-text > .gink-spinner:first-child { margin-top: 2px; }
  @keyframes gink-spin { to { transform: rotate(360deg); } }

  /* ---------- People: faces in your photos, grouped on this device (like Photos on iPhone) ---------- */
  #people-back { position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 420; background: rgba(0, 0, 0, 0.34); display: grid; place-items: center; padding: 16px;
    -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px); animation: pp-fade .2s ease both; }
  @keyframes pp-fade { from { opacity: 0; } }
  .pp-card { width: min(880px, 100%); height: min(720px, calc(100vh - 32px)); display: flex; flex-direction: column; background: var(--surface);
    color: var(--text-main); border: 1px solid var(--border); border-radius: 22px; box-shadow: 0 30px 80px rgba(0, 0, 0, .3); overflow: hidden;
    animation: pp-up .28s cubic-bezier(.2, .9, .25, 1.1) both; }
  @keyframes pp-up { from { transform: translateY(14px) scale(.98); opacity: 0; } }
  .pp-head { display: flex; align-items: center; gap: 10px; padding: 16px 18px 12px; border-bottom: 1px solid var(--border); }
  .pp-titles { flex: 1; min-width: 0; }
  .pp-title { font-size: 20px; font-weight: 650; letter-spacing: -.01em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .pp-sub { color: var(--text-muted); font-size: 12.5px; margin-top: 2px; }
  .pp-btn { border: 1px solid var(--border); background: var(--surface); color: var(--text-main); border-radius: 999px; padding: 8px 14px;
    font: inherit; font-size: 13.5px; cursor: pointer; white-space: nowrap; }
  .pp-btn:hover { border-color: var(--accent); }
  .pp-btn.primary { background: var(--accent); color: var(--on-accent); border-color: var(--accent); font-weight: 600; }
  .pp-btn.danger { color: #d93025; }
  .pp-icon { border: 0; background: transparent; color: var(--text-muted); width: 34px; height: 34px; border-radius: 10px; cursor: pointer; font-size: 18px; flex: none; }
  .pp-icon:hover { background: var(--elevated, rgba(127,127,127,.12)); color: var(--text-main); }
  .pp-progress { padding: 8px 18px; font-size: 13px; color: var(--text-muted); display: flex; align-items: center; gap: 10px; }
  .pp-bar { flex: 1; height: 4px; border-radius: 4px; background: var(--elevated, rgba(127,127,127,.15)); overflow: hidden; }
  .pp-bar i { display: block; height: 100%; width: 0; background: var(--accent); transition: width .3s; }
  .pp-body { flex: 1; overflow: auto; padding: 16px 18px 22px; }
  .pp-section { font-size: 13px; font-weight: 650; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; margin: 6px 2px 12px; }
  .pp-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); gap: 16px 12px; margin-bottom: 22px; }
  .pp-tile { border: 0; background: transparent; color: inherit; font: inherit; cursor: pointer; display: flex; flex-direction: column; align-items: center;
    gap: 6px; padding: 8px 4px; border-radius: 16px; }
  .pp-tile:hover, .pp-tile:focus-visible { background: var(--elevated, rgba(127,127,127,.1)); outline: none; }
  .pp-face { width: 92px; height: 92px; border-radius: 50%; object-fit: cover; background: var(--elevated, #ddd);
    box-shadow: 0 4px 14px rgba(0,0,0,.14), inset 0 0 0 1px rgba(0,0,0,.05); }
  .pp-name { font-size: 14px; font-weight: 600; max-width: 110px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pp-name.empty { color: var(--accent); font-weight: 600; }
  .pp-count { font-size: 12px; color: var(--text-muted); }
  .pp-photos { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; }
  .pp-photo { position: relative; border-radius: 12px; overflow: hidden; background: var(--elevated, #eee); aspect-ratio: 1; }
  .pp-photo img { width: 100%; height: 100%; object-fit: cover; display: block; }
  /* engines without aspect-ratio (Safari before 15): square tiles the old way */
  @supports not (aspect-ratio: 1) { .pp-photo::before { content: ""; display: block; padding-top: 100%; }
    .pp-photo img { position: absolute; top: 0; left: 0; } }
  .pp-photo .pp-not { position: absolute; top: 6px; right: 6px; border: 0; border-radius: 999px; padding: 4px 9px; font: inherit; font-size: 11.5px;
    background: rgba(0,0,0,.55); color: #fff; cursor: pointer; opacity: 0; transition: opacity .15s; }
  .pp-photo:hover .pp-not, .pp-photo .pp-not:focus-visible { opacity: 1; }
  .pp-person-top { display: flex; align-items: center; gap: 16px; margin-bottom: 18px; flex-wrap: wrap; }
  .pp-person-top .pp-face { width: 76px; height: 76px; }
  .pp-name-in { flex: 1; min-width: 180px; font: inherit; font-size: 18px; font-weight: 600; border: 1px solid var(--border); border-radius: 12px;
    padding: 9px 12px; background: transparent; color: inherit; }
  .pp-name-in:focus { outline: none; border-color: var(--accent); }
  .pp-intro { max-width: 520px; margin: 30px auto; text-align: center; }
  .pp-intro .pp-big { font-size: 46px; }
  .pp-intro h3 { font-size: 20px; margin: 10px 0 8px; }
  .pp-intro p { color: var(--text-muted); font-size: 14px; line-height: 1.55; margin: 0 0 10px; }
  .pp-intro ul { text-align: left; color: var(--text-muted); font-size: 13.5px; line-height: 1.6; margin: 10px auto 18px; padding-left: 20px; max-width: 440px; }
  .pp-note { color: var(--text-muted); font-size: 12.5px; margin-top: -6px; }
  @media (max-width: 640px) { .pp-card { height: calc(100vh - 20px); border-radius: 18px; } .pp-grid { grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); }
    .pp-face { width: 76px; height: 76px; } .pp-photos { grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); } }
  @media (prefers-reduced-motion: reduce) { #people-back, .pp-card { animation: none; } }

  /* ---------- Lock Gink: the screen that covers everything until Face ID / Touch ID / Windows Hello / a passkey ---------- */
  #app-lock { position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 2000; display: grid; place-items: center; padding: 24px; text-align: center;
    background: radial-gradient(120% 90% at 50% 0%, #1f2b24 0%, #121815 55%, #0c100e 100%); color: #f5f7f4;
    animation: lock-in .25s ease both; }
  @keyframes lock-in { from { opacity: 0; } }
  .lock-card { width: min(360px, 100%); display: flex; flex-direction: column; align-items: center; gap: 14px; }
  .lock-mark { width: 64px; height: 64px; border-radius: 18px; background: rgba(255,255,255,.07); display: grid; place-items: center;
    box-shadow: 0 10px 40px rgba(0,0,0,.35), inset 0 0 0 1px rgba(255,255,255,.08); }
  .lock-mark img { width: 38px; height: 38px; }
  .lock-title { font-size: 22px; font-weight: 650; letter-spacing: -.01em; margin-top: 4px; }
  .lock-sub { color: rgba(245,247,244,.68); font-size: 14px; line-height: 1.45; min-height: 20px; }
  .lock-go { margin-top: 6px; border: 0; border-radius: 999px; padding: 13px 26px; font: inherit; font-size: 15.5px; font-weight: 650;
    cursor: pointer; background: #A8F03C; color: #10200a; display: inline-flex; align-items: center; gap: 10px; }
  .lock-go:disabled { opacity: .55; cursor: default; }
  .lock-go svg { width: 20px; height: 20px; }
  .lock-out { background: transparent; border: 0; color: rgba(245,247,244,.6); font: inherit; font-size: 13.5px; cursor: pointer; padding: 6px 10px;
    border-radius: 8px; }
  .lock-out:hover { color: #fff; background: rgba(255,255,255,.06); }
  @media (prefers-reduced-motion: reduce) { #app-lock { animation: none; } }

  /* ---------- Live camera: point, ask, point again -- each question goes with what the camera sees right now ---------- */
  #live-cam { position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 450; background: #000; color: #fff; display: flex; flex-direction: column;
    animation: cam-fade .2s ease both; }
  #live-cam video { flex: 1; min-height: 0; width: 100%; object-fit: cover; background: #000; }
  .live-top { position: absolute; top: 0; left: 0; right: 0; display: flex; align-items: center; gap: 10px; padding: 14px 16px;
    background: linear-gradient(rgba(0,0,0,.55), transparent); }
  .live-dot { width: 9px; height: 9px; border-radius: 50%; background: #ff453a; box-shadow: 0 0 0 4px rgba(255,69,58,.25); animation: live-pulse 1.6s infinite; }
  @keyframes live-pulse { 50% { box-shadow: 0 0 0 8px rgba(255,69,58,0); } }
  .live-title { font-weight: 650; letter-spacing: -.01em; flex: 1; }
  .live-x, .live-flip { border: 0; border-radius: 999px; width: 36px; height: 36px; background: rgba(255,255,255,.16); color: #fff; font-size: 17px;
    cursor: pointer; -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); }
  .live-bottom { position: absolute; left: 0; right: 0; bottom: 0; padding: 12px 14px 18px; background: linear-gradient(transparent, rgba(0,0,0,.7) 30%); }
  .live-answer { max-height: 32vh; overflow: auto; margin: 0 auto 10px; max-width: 760px; padding: 12px 14px; border-radius: 16px; font-size: 15px; line-height: 1.45;
    background: rgba(28,28,30,.72); -webkit-backdrop-filter: blur(24px) saturate(160%); backdrop-filter: blur(24px) saturate(160%); white-space: pre-wrap; }
  .live-answer:empty { display: none; }
  .live-hint { text-align: center; font-size: 12.5px; color: rgba(255,255,255,.72); margin: 0 auto 10px; max-width: 760px; }
  .live-ask { display: flex; gap: 8px; max-width: 760px; margin: 0 auto; }
  .live-ask input { flex: 1; min-width: 0; border: 0; border-radius: 999px; padding: 12px 16px; font: inherit; font-size: 15px; color: #fff;
    background: rgba(255,255,255,.14); outline: none; }
  .live-ask input::placeholder { color: rgba(255,255,255,.6); }
  .live-ask button { border: 0; border-radius: 999px; padding: 0 18px; font: inherit; font-weight: 650; cursor: pointer; background: #A8F03C; color: #10200a; }
  .live-ask .live-mic { background: rgba(255,255,255,.16); color: #fff; padding: 0 14px; }
  .live-ask .live-mic.on { background: #ff453a; }
  #live-cam.busy .live-ask button[type=submit] { opacity: .5; pointer-events: none; }
  .live-flash { position: absolute; top: 0; right: 0; bottom: 0; left: 0; background: #fff; opacity: 0; pointer-events: none; }
  .live-flash.go { animation: live-flash .35s ease; }
  @keyframes live-flash { 15% { opacity: .55; } }
  @media (prefers-reduced-motion: reduce) { #live-cam, .live-dot, .live-flash.go { animation: none; } }

  /* ---------- notifications (Apple style) ---------- */
  #notify-host { position: fixed; top: 14px; right: 14px; z-index: 1000; display: flex; flex-direction: column; gap: 10px;
    width: min(372px, calc(100vw - 28px)); pointer-events: none; }
  .gnote { pointer-events: auto; position: relative; display: flex; gap: 11px; padding: 12px 14px 12px 12px; border-radius: 18px;
    background: rgba(250, 250, 250, 0.78); color: #1d1d1f; border: 1px solid rgba(0, 0, 0, 0.06);
    -webkit-backdrop-filter: blur(28px) saturate(180%); backdrop-filter: blur(28px) saturate(180%);
    box-shadow: 0 10px 34px rgba(0, 0, 0, 0.16), 0 1px 3px rgba(0, 0, 0, 0.08);
    animation: gn-in .5s cubic-bezier(.2, .9, .25, 1.15) both; transition: transform .2s; }
  .gnote.out { animation: gn-out .3s ease forwards; }
  @keyframes gn-in { from { opacity: 0; transform: translateX(30px) scale(.96); } to { opacity: 1; transform: none; } }
  @keyframes gn-out { to { opacity: 0; transform: translateX(40px) scale(.96); } }
  body.theme-dark .gnote { background: rgba(44, 44, 46, 0.78); color: #f5f5f7; border-color: rgba(255, 255, 255, 0.08); }
  .gn-ic { flex: none; width: 38px; height: 38px; border-radius: 10px; background: #151D23; display: grid; place-items: center; font-size: 20px;
    box-shadow: inset 0 0 0 1px rgba(255,255,255,.06); }
  .gnote.warn .gn-ic { background: #FFF1D6; }
  body.theme-dark .gnote.warn .gn-ic { background: #4a3a14; }
  .gn-main { flex: 1; min-width: 0; }
  .gn-top { display: flex; justify-content: space-between; font-size: 11px; letter-spacing: .04em; opacity: .55; margin-bottom: 1px; }
  .gn-title { font-weight: 600; font-size: 14px; line-height: 1.3; }
  .gn-body { font-size: 13.5px; line-height: 1.35; opacity: .85; margin-top: 1px; word-wrap: break-word; }
  .gn-acts { display: flex; gap: 8px; margin-top: 10px; }
  .gn-acts button { flex: 1; border: 0; border-radius: 10px; padding: 7px 10px; font: inherit; font-size: 13px; font-weight: 500; cursor: pointer;
    background: rgba(120, 120, 128, 0.16); color: inherit; }
  .gn-acts button.primary { background: var(--accent); color: var(--on-accent); }
  .gn-acts button:hover { filter: brightness(0.96); }
  .gn-x { position: absolute; top: -7px; left: -7px; width: 22px; height: 22px; border-radius: 50%; border: 1px solid rgba(0,0,0,.1);
    background: rgba(250,250,250,.95); color: #444; font-size: 14px; line-height: 18px; padding: 0; cursor: pointer; opacity: 0; transition: opacity .15s; }
  .gnote:hover .gn-x, .gnote:focus-within .gn-x { opacity: 1; }
  @media (hover: none) { .gn-x { opacity: .9; } }
  @media (max-width: 600px) { #notify-host { left: 50%; right: auto; transform: translateX(-50%); top: 10px; }
    @keyframes gn-in { from { opacity: 0; transform: translateY(-24px) scale(.97); } to { opacity: 1; transform: none; } }
    @keyframes gn-out { to { opacity: 0; transform: translateY(-24px) scale(.97); } } }
  @media (prefers-reduced-motion: reduce) { .gnote, .gnote.out { animation-duration: .01s; } }
  .msg-logo { display: block; width: 22px; height: 22px; margin: 12px 0 0; opacity: 0.9; }   /* in line with the reply */
  .msg-logo.landing { animation: logo-land 1.3s cubic-bezier(.3,.7,.3,1); }
  @keyframes logo-land { 0% { transform: rotate(-200deg) scale(.5); opacity: 0; } 55% { opacity: 1; } 100% { transform: rotate(0) scale(1); } }
  .assistant-text .stream > *:last-child { margin-bottom: 0; }
  /* ---------- user message actions ---------- */
  .row.user { flex-direction: column; align-items: flex-end; }
  .uactions {
    display: flex; align-items: center; margin-top: 4px; opacity: 0; transition: opacity 0.15s;
    position: relative;
  }
  .row.user:hover .uactions, .uactions.open, .row.user:focus-within .uactions { opacity: 1; }
  @media (hover: none) { .uactions { opacity: 1; } }
  .ua {
    width: 30px; height: 30px; border: none; background: transparent; border-radius: 8px;
    color: var(--text-muted); display: inline-flex; align-items: center; justify-content: center;
    cursor: pointer; padding: 0; margin-left: 2px;
  }
  .ua:hover { background: var(--elevated); color: var(--text-main); }
  .ua svg { width: 16px; height: 16px; }
  .ua.done { color: var(--accent); }
  .uactions .menu { bottom: auto; top: 34px; right: 0; min-width: 230px; }
  .menu button svg { width: 17px; height: 17px; flex: none; margin-right: 10px; color: var(--text-muted); }
  p code, li code { background: var(--elevated); color: var(--accent); padding: 2px 5px; border-radius: 5px; }
  .doc-block {
    max-width: 720px;
    margin: 10px 0;
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
  }
  .doc-block-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  .doc-block-label {
    flex: 1;
    font-size: 12px;
    font-weight: 600;
    color: var(--accent-dim);
  }
  .doc-block-body {
    padding: 18px 20px;
    background: var(--elevated);
    line-height: 1.65;
  }
  .doc-block-body > *:first-child { margin-top: 0; }
  .doc-block-body > *:last-child { margin-bottom: 0; }
  table { border-collapse: collapse; }
  th, td { border: 1px solid var(--border); padding: 6px 10px; }
  th { background: var(--surface); }
  /* a soft shadow at an edge shows there's more to swipe to (the shadows stay put, the covers scroll) */
  .table-wrap { max-width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 10px 0; overscroll-behavior-x: contain;
    background: linear-gradient(to right, var(--bg) 30%, transparent) left center / 28px 100% no-repeat local,
                linear-gradient(to left, var(--bg) 30%, transparent) right center / 28px 100% no-repeat local,
                radial-gradient(farthest-side at 0 50%, rgba(0, 0, 0, .16), transparent) left center / 10px 100% no-repeat scroll,
                radial-gradient(farthest-side at 100% 50%, rgba(0, 0, 0, .16), transparent) right center / 10px 100% no-repeat scroll; }
  .table-wrap table { margin: 0; min-width: 100%; }
  .table-wrap th, .table-wrap td { vertical-align: top; text-align: left; overflow-wrap: normal; word-break: normal; }
  hr { border: none; border-top: 1px solid var(--border); }
  /* ---------- composer (bottom input card) ---------- */
  #composer-wrap {
    position: absolute; left: 0; right: 0; bottom: 0; z-index: 5;
    padding: 10px 20px calc(8px + env(safe-area-inset-bottom, 0px));
    background: linear-gradient(to bottom, rgba(255,255,255,0), var(--bg) 22px);
  }
  body.kb #composer-wrap { padding-bottom: 8px; }         /* the keyboard covers the home-indicator strip */
  /* the see-through band above the box (and the status lines) let a drag or the mouse wheel reach the conversation */
  #composer-wrap, #composer-wrap .today-wrap, #cstatus, #composer-wrap .disclaimer, #suggest { pointer-events: none; }
  #composer, .sug, .today { pointer-events: auto; }
  #composer {
    max-width: 760px; margin: 0 auto;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow: 0 2px 10px rgba(28, 33, 29, 0.06);
    padding: 12px 12px 8px 16px;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  #composer:focus-within { border-color: #CDD3C6; box-shadow: 0 3px 14px rgba(28, 33, 29, 0.09); }
  #cin {
    width: 100%; border: none; outline: none; resize: none;
    font: inherit; font-size: 15px; line-height: 1.5;
    color: var(--text-main); background: transparent;
    max-height: 180px; min-height: 24px; padding: 2px 0 6px;
  }
  #cin::placeholder { color: #9AA096; }
  .crow { display: flex; align-items: center; gap: 4px; }
  .spacer { flex: 1; }
  .ibtn {
    width: 34px; height: 34px; border-radius: 10px; border: none;
    background: transparent; color: var(--text-main);
    display: inline-flex; align-items: center; justify-content: center;
    cursor: pointer; padding: 0;
  }
  .ibtn:hover { background: var(--elevated); }
  .ibtn svg { width: 19px; height: 19px; }
  .ibtn.on { color: var(--accent); background: var(--accent-soft); }
  .ibtn:disabled { opacity: 0.4; cursor: default; }
  #send.ready { background: var(--accent); color: var(--on-accent); }
  #send.on, #send.speaking { color: var(--accent); background: var(--accent-soft); animation: orb-pulse 1.2s ease-in-out infinite; }
  #send.busy:not(.ready) { opacity: 0.55; }
  #send.ready:hover { filter: brightness(1.08); }
  .model {
    border: none; background: transparent; cursor: pointer;
    font: inherit; font-size: 14px; color: var(--text-main);
    padding: 6px 8px; border-radius: 10px; white-space: nowrap;
  }
  .model:hover { background: var(--elevated); }
  .model .tier { color: var(--text-muted); margin-left: 6px; }
  /* status orb: a ring that breathes while Gink is listening/thinking */
  .orb {
    width: 18px; height: 18px; border-radius: 50%;
    border: 2.5px solid var(--accent); margin: 0 6px; box-sizing: border-box;
    transition: all 0.2s;
  }
  .orb.busy { border-color: var(--accent); animation: orb-pulse 1.1s ease-in-out infinite; }
  .orb.listening { background: var(--accent-soft); animation: orb-pulse 0.8s ease-in-out infinite; }
  .orb.speaking { border-color: var(--logo-lime); animation: orb-pulse 0.6s ease-in-out infinite; }
  @keyframes orb-pulse { 0%,100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.25); opacity: 0.7; } }
  .menu-anchor { position: relative; }
  .menu {
    position: absolute; bottom: 42px; min-width: 230px;
    background: var(--bg); border: 1px solid var(--border); border-radius: 14px;
    box-shadow: 0 10px 30px rgba(28, 33, 29, 0.14); padding: 6px; z-index: 10;
  }
  .menu.left { left: -4px; }
  .menu.right { right: 0; }
  .menu.hidden { display: none; }
  .menu button {
    display: flex; align-items: center; gap: 10px; width: 100%;
    border: none; background: transparent; font: inherit; font-size: 14px;
    color: var(--text-main); text-align: left; padding: 9px 10px;
    border-radius: 9px; cursor: pointer;
  }
  .menu button:hover { background: var(--elevated); }
  .menu .hint { color: var(--text-muted); font-size: 12px; margin-left: auto; }
  .menu .sel::after { content: "\\2713"; margin-left: auto; color: var(--accent); }
  #model-menu { min-width: 300px; }
  #model-menu .mm-col { display: flex; flex-direction: column; gap: 2px; }
  #model-menu .mm-name { font-weight: 600; } #model-menu .mm-desc { color: var(--text-muted); font-size: 12.5px; }
  #model-menu .mm-back { color: var(--text-muted); font-weight: 600; }
  #model-menu .mm-note { color: var(--text-muted); font-size: 12.5px; padding: 2px 10px 6px; line-height: 1.4; }
  #model-menu .mm-badge { font-size: 11.5px; border: 1px solid var(--border); border-radius: 999px; padding: 1px 8px; color: var(--text-muted); }
  #model-menu .mm-badge.warn { background: rgba(255, 190, 60, .16); color: inherit; }
  #model-menu .sel .mm-badge { margin-right: 6px; }
  #cstatus { max-width: 760px; margin: 6px auto 0; min-height: 16px; font-size: 12px; color: var(--accent); text-align: center; }
  .disclaimer { max-width: 760px; margin: 2px auto 0; font-size: 11px; color: var(--text-muted); text-align: center; }
  @media (max-width: 520px) {
    #composer-wrap { padding: 8px 10px calc(6px + env(safe-area-inset-bottom, 0px)); }
    body.kb #composer-wrap { padding-bottom: 6px; }
    .model .tier { display: none; }
    .model { max-width: 34vw; overflow: hidden; text-overflow: ellipsis; }   /* a long model name never pushes the mic out */
  }
  /* ---------- welcome ("home") state ----------
     Empty chat: the composer is a single pill in the middle of the
     screen with the greeting above it. On the first message body loses
     .home and the composer glides down to its normal bottom card. */
  body { transition: background 0.5s ease; }
  body.home {
    background:
      radial-gradient(ellipse 70% 55% at 50% 58%, rgba(168, 240, 60, 0.20), rgba(168, 240, 60, 0) 70%),
      radial-gradient(ellipse 60% 45% at 30% 30%, rgba(63, 130, 18, 0.07), rgba(63, 130, 18, 0) 70%),
      var(--bg);
    min-height: 100vh;
  }
  #composer-wrap { transition: transform 0.55s cubic-bezier(0.22, 1, 0.36, 1), background 0.4s; }
  body.home #composer-wrap { transform: translateY(calc(var(--app-h) * -0.5 + 103px)); background: transparent; }
  body.home #composer {
    display: flex; align-items: center; gap: 2px;
    border-radius: 30px; padding: 8px 10px 8px 8px; border-color: transparent;
    box-shadow: 0 6px 28px rgba(28, 33, 29, 0.10), 0 1px 3px rgba(28, 33, 29, 0.06);
  }
  /* the text box is moved INTO the row by layoutComposer() in home
     mode (works in every web engine, unlike display:contents/order) */
  body.home .crow { flex: 1; min-width: 0; }
  /* min-width 0: the text box shrinks on a narrow phone instead of pushing the mic out of the pill */
  body.home #cin { flex: 1; width: auto; min-width: 0; padding: 6px 6px; min-height: 0; max-height: 120px; }
  body.home .crow > .spacer, body.home #orb { display: none; }
  body.home #send:not(.ready) { display: none; }      /* only shows once you type */
  body.home .model .tier { display: none; }
  body.home .model::after { content: " \\2304"; color: var(--text-muted); font-size: 13px; }
  body.home .menu { bottom: auto; top: 46px; }         /* drop menus downward from the centre */
  body.home #cstatus, body.home .disclaimer { opacity: 0; }
  body.home #feed { padding-bottom: 40px; }
  #welcome { transition: opacity 0.3s; }
  body.home #welcome { margin-top: calc(var(--app-h) * 0.5 - 182px); }   /* greeting + subtitle clear the composer */
  .today-wrap { display: none; text-align: center; margin-top: 16px; }
  /* home: a few ways to start, under the composer (gone once the chat begins) */
  #suggest { display: none; }
  /* out of the flow, so the composer's centred position (it depends on this bar's height) doesn't move */
  body.home #suggest { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; max-width: 780px;
    position: absolute; left: 0; right: 0; top: calc(100% - 22px); margin: 0 auto; padding: 0 16px;
    animation: word-in 0.8s ease 1.1s both; }
  .sug { border: 1px solid var(--border); background: var(--surface, var(--bg)); color: var(--text-main); border-radius: 999px;
    padding: 8px 14px; font: inherit; font-size: 13.5px; cursor: pointer; transition: border-color .15s, background .15s, transform .15s; }
  .sug:hover { border-color: var(--accent); background: var(--accent-soft); }
  .sug:active { transform: scale(0.97); }
  @media (max-width: 520px) { body.home #suggest { gap: 6px; } .sug { padding: 7px 12px; font-size: 13px; } }
  @media (prefers-reduced-motion: reduce) { body.home #suggest { animation: none; } }
  body.home .today-wrap { display: block; animation: word-in 0.8s ease 1s both; }
  .today {
    display: inline-block; font-size: 13px; color: var(--accent);
    background: var(--accent-soft); border-radius: 999px; padding: 6px 14px;
  }
  .today:empty { display: none; }
  /* short (a landscape phone, or the keyboard is up): the box sits low, the greeting at the top, no ideas row */
  body.home.short #composer-wrap { transform: translateY(calc(var(--app-h) * -0.5 + 170px)); }
  body.home.short #welcome { margin-top: 16px; }
  body.home.tiny #suggest, body.home.kb #suggest { display: none; }
  body.home.kb #composer-wrap { transform: none; }
  body.home.kb #welcome { margin-top: 8px; }
  @media (prefers-reduced-motion: reduce) { #composer-wrap, body { transition: none; } }
  /* ---------- sidebar ----------
     Hidden by default on narrow windows; touching the left edge with the
     mouse slides it out ("peek"), leaving slides it away again. The
     sidebar icon pins it open (content moves over). */
  :root { --side-w: 260px; }
  #side {
    position: fixed; top: 0; bottom: 0; left: 0; width: var(--side-w); z-index: 30;
    background: var(--sidebar); border-right: 1px solid var(--border);
    display: flex; flex-direction: column;
    transform: translateX(-100%); transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.28s;
  }
  body.pinned #side, body.peek #side { transform: translateX(0); }
  body.peek:not(.pinned) #side { box-shadow: 0 0 30px rgba(0, 0, 0, 0.12); }
  #edge { position: fixed; top: 0; bottom: 0; left: 0; width: 14px; z-index: 29; }
  body.pinned #edge { display: none; }
  body { transition: padding-left 0.28s cubic-bezier(0.22, 1, 0.36, 1), background 0.5s ease; }
  body.pinned { padding-left: var(--side-w); }
  body.pinned #shell { left: var(--side-w); }
  /* ONE sidebar button, above the sidebar: top left while it's closed (the logo, on the icon rail), the
     sidebar's top right while it's open. Click = open/close. */
  #tb-toggle { position: fixed; top: calc(10px + env(safe-area-inset-top, 0px)); left: 10px; z-index: 35; }
  /* Temporary chat: not saved, not synced, gone when you leave it */
  #temp-btn { position: fixed; top: calc(10px + env(safe-area-inset-top, 0px)); right: 14px; z-index: 28; display: none; align-items: center; padding: 6px 12px;
              border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--text-main); font: inherit;
              font-size: 13px; font-weight: 600; cursor: pointer; }
  body.home #temp-btn { display: inline-flex; }
  #temp-btn svg { flex: none; margin-right: 6px; }
  body.temporary #temp-btn { background: var(--text-main); color: var(--surface); border-color: var(--text-main); }
  #temp-banner { position: fixed; top: 54px; left: 50%; transform: translateX(-50%); z-index: 27; display: none; align-items: center;
                 padding: 6px 14px; border-radius: 999px; background: var(--text-main); color: var(--surface); font-size: 13px; font-weight: 600;
                 box-shadow: 0 4px 14px rgba(0,0,0,.15); max-width: calc(100vw - 160px); }
  #temp-banner span { font-weight: 400; opacity: .8; margin-left: 6px; }
  #temp-banner svg { flex: none; margin-right: 8px; }
  /* the keyboard panned the visible area (iPhone): the top buttons move with it, like the shell */
  #tb-toggle, #topbar, #temp-btn { transform: translateY(var(--vv-top, 0px)); }
  #temp-banner { transform: translate(-50%, var(--vv-top, 0px)); }
  body.temporary #temp-banner { display: inline-flex; }
  body.temporary #composer { border-style: dashed; }
  #topbar { position: fixed; top: calc(10px + env(safe-area-inset-top, 0px)); left: 56px; z-index: 28; display: flex; align-items: center;
    min-height: 40px; transition: left 0.28s; }
  @media (min-width: 761px) { #topbar { left: 72px; } }
  body.pinned #topbar { left: calc(var(--side-w) + 16px); }
  .wordmark { font-weight: 700; font-size: 16px; color: var(--text-main); padding: 0 4px; }
  .wordmark span { color: var(--text-muted); font-weight: 500; }
  /* ---------- the sidebar (0.1.157): plain and quiet ----------
     Like the sidebars people already know: the logo and "Gink" at the top (the button that closes the
     sidebar sits at its right), plain rows -- New chat, Search chats, Workspace, Media Studio, Gink Genie --,
     your chats under small day headings (Pinned, Today, Yesterday, Previous 7 days...) and your account at
     the bottom. No glow, no raised cards, no badges: keyboard shortcuts show only while you point at a row.
     Spacing uses margins, never flex "gap" -- older Mac web views ignore gap (icons touched their labels). */
  :root { --side-hover: rgba(0, 0, 0, 0.045); --side-active: rgba(0, 0, 0, 0.075); --side-line: rgba(0, 0, 0, 0.07); }
  html.theme-dark, body.theme-dark { --side-hover: rgba(255, 255, 255, 0.06); --side-active: rgba(255, 255, 255, 0.1);
    --side-line: rgba(255, 255, 255, 0.08); }
  #side { border-right: 1px solid var(--side-line); }
  /* the logo (the glowing tile): ONE copy, as a background -- the brand and the top of the icon rail */
  .gmark { display: block; width: 28px; height: 28px; flex: none; border-radius: 8px;
    background: url(__BRAND_TILE_URI__) center / 100% 100% no-repeat; }
  .side-head { display: flex; align-items: center; flex: none; height: calc(60px + env(safe-area-inset-top, 0px));
    padding: env(safe-area-inset-top, 0px) 58px 0 14px; }
  .side-head .brand { display: flex; align-items: center; min-width: 0; font-size: 17px; font-weight: 600; letter-spacing: -0.01em;
    color: var(--text-main); }
  .side-head .gmark { margin-right: 10px; }
  .side-nav { flex: none; padding: 0 8px 6px; }
  .srow { position: relative; display: flex; align-items: center; width: 100%; height: 36px; margin: 0 0 1px; padding: 0 10px;
    border: 0; border-radius: 10px; background: transparent; color: var(--text-main); font: inherit; font-size: 14px;
    text-align: left; cursor: pointer; transition: background 0.12s; }
  .srow:hover { background: var(--side-hover); }
  .srow svg { width: 18px; height: 18px; flex: none; margin-right: 10px; }
  .srow .lbl { flex: 1; min-width: 0; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  /* a row's keyboard shortcut: quiet text, only while you point at the row */
  .nk { flex: none; margin-left: 8px; font-size: 12px; color: var(--text-muted); white-space: nowrap; opacity: 0; transition: opacity 0.12s; }
  .nk:empty { display: none; }
  .srow:hover .nk { opacity: 1; }
  /* Search chats looks like the other rows; click it and it's a search box */
  #side-search { cursor: pointer; }
  #side-search input { flex: 1; min-width: 0; height: 100%; margin: 0; padding: 0; border: 0; border-radius: 0; outline: none;
    background: transparent; font: inherit; font-size: 14px; color: var(--text-main); cursor: pointer; -webkit-appearance: none; appearance: none; }
  #side-search input::placeholder { color: var(--text-main); opacity: 1; }
  #side-search:focus-within { background: var(--side-active); cursor: text; }
  #side-search:focus-within input { cursor: text; }
  #side-search:focus-within input::placeholder { color: var(--text-muted); }
  #side-search:focus-within .nk { display: none; }
  #recents { flex: 1; overflow-y: auto; padding: 2px 8px 12px; scrollbar-width: thin; scrollbar-color: transparent transparent; }
  #recents:hover { scrollbar-color: var(--border) transparent; }
  .recent { position: relative; display: flex; align-items: center; width: 100%; height: 36px; margin: 0 0 1px; padding: 0 34px 0 10px;
    border: 0; border-radius: 10px; background: transparent; color: var(--text-main); font: inherit; font-size: 14px; text-align: left;
    cursor: pointer; transition: background 0.12s; }
  .recent:hover { background: var(--side-hover); }
  .recent.current { background: var(--side-active); }
  .recent .t { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; flex: 1; }
  .recent .more {
    position: absolute; right: 4px; top: 50%; transform: translateY(-50%); padding: 0;
    width: 28px; height: 28px; border-radius: 8px; border: none; background: transparent;
    color: var(--text-muted); display: none; align-items: center; justify-content: center; cursor: pointer;
  }
  .recent:hover .more, .recent.current .more { display: flex; }
  .recent .more:hover { background: var(--side-hover); color: var(--text-main); }
  .recent .more svg { width: 16px; height: 16px; }
  /* a chat just saved to history: slides in, glows, title types itself out */
  .recent.fresh { animation: recent-in 0.45s cubic-bezier(0.22, 1, 0.36, 1), recent-glow 1.6s ease-out; }
  @keyframes recent-in { from { opacity: 0; transform: translateX(-14px); } to { opacity: 1; transform: none; } }
  @keyframes recent-glow { 0% { background: var(--accent-soft); } 100% { background: transparent; } }
  .recent.current.fresh { animation: recent-in 0.45s cubic-bezier(0.22, 1, 0.36, 1); }
  .recent .t.typing::after {
    content: ""; display: inline-block; width: 2px; height: 1em; margin-left: 1px; vertical-align: -2px;
    background: var(--accent); animation: caret 0.8s steps(1) infinite;
  }
  @keyframes caret { 50% { opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .recent.fresh { animation: none; } }
  .empty-recents { color: var(--text-muted); font-size: 13px; padding: 6px 12px; line-height: 1.45; }
  #row-menu { position: fixed; z-index: 40; min-width: 150px; }
  #row-menu .danger { color: var(--danger); }
  .side-foot { position: relative; display: flex; align-items: center; flex: none; margin: 9px 8px calc(8px + env(safe-area-inset-bottom, 0px));
    padding: 6px 4px 6px 8px; border-radius: 10px; transition: background 0.12s; }
  .side-foot::before { content: ""; position: absolute; left: -8px; right: -8px; top: -9px; height: 1px; background: var(--side-line); }
  .side-foot:hover { background: var(--side-hover); }
  .avatar {
    width: 32px; height: 32px; border-radius: 50%; flex: none; margin-right: 10px; overflow: hidden;
    background: var(--accent); color: var(--on-accent); font-weight: 600; font-size: 13px;
    display: flex; align-items: center; justify-content: center;
  }
  .side-foot .avatar { width: 30px; height: 30px; }
  .side-foot .who { flex: 1; min-width: 0; font-size: 14px; font-weight: 500; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .side-foot #gear { flex: none; width: 32px; height: 32px; color: var(--text-muted); }
  .side-foot #gear:hover { color: var(--text-main); background: var(--side-hover); }
  @media (hover: none) and (pointer: coarse) { .srow, .recent { height: 40px; font-size: 15px; } }
  /* phones: the sidebar slides over a dimmed page (tap outside to close) */
  #side-scrim { position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 29; background: rgba(0, 0, 0, 0.32); opacity: 0;
    pointer-events: none; transition: opacity 0.25s; }
  /* the sidebar button: on the icon rail it's the logo (point at it: "open sidebar"); while the sidebar is
     open it sits at the sidebar's top right and closes it. Phones: always the sidebar icon. */
  #tb-toggle { width: 40px; height: 40px; border-radius: 10px; color: var(--text-main);
    transition: left 0.28s cubic-bezier(0.22, 1, 0.36, 1), background 0.12s; }
  #tb-toggle:hover { background: var(--side-hover); }
  #tb-toggle svg { width: 20px; height: 20px; }
  #tb-toggle .gmark { display: none; }
  body.pinned #tb-toggle, body.peek #tb-toggle { left: calc(var(--side-w) - 50px); }
  @media (min-width: 761px) {
    body:not(.pinned):not(.peek) #tb-toggle .gmark { display: block; }
    body:not(.pinned):not(.peek) #tb-toggle .tb-panel { display: none; }
    body:not(.pinned):not(.peek) #tb-toggle:hover .gmark { display: none; }
    body:not(.pinned):not(.peek) #tb-toggle:hover .tb-panel { display: block; }
  }
  /* ---------- delete dialog ---------- */
  #modal-back {
    position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 50; background: rgba(28, 33, 29, 0.28);
    display: none; align-items: center; justify-content: center; padding: 20px;
  }
  #modal-back.open { display: flex; animation: fade-in 0.15s ease-out; }
  @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
  .modal {
    background: var(--bg); border-radius: 20px; width: 100%; max-width: 440px;
    box-shadow: 0 20px 60px rgba(28, 33, 29, 0.25); padding: 22px 22px 18px;
    animation: pop-in 0.18s cubic-bezier(0.22, 1, 0.36, 1);
  }
  @keyframes pop-in { from { transform: scale(0.96); opacity: 0; } to { transform: scale(1); opacity: 1; } }
  .modal h3 { margin: 0 0 14px; font-size: 18px; font-weight: 600; }
  .modal p { margin: 0 0 6px; font-size: 15px; }
  .modal .sub { color: var(--text-muted); font-size: 13.5px; }
  .modal .actions { display: flex; justify-content: flex-end; margin-top: 18px; }
  .modal .actions .pill + .pill { margin-left: 10px; }
  .pill { font: inherit; font-size: 14.5px; border-radius: 999px; padding: 8px 18px; cursor: pointer; }
  .pill.ghost { background: var(--bg); border: 1px solid var(--border); color: var(--text-main); }
  .pill.ghost:hover { background: var(--elevated); }
  .pill.danger { background: #E5251B; border: 1px solid #E5251B; color: #fff; font-weight: 500; }
  .pill.danger:hover { filter: brightness(1.07); }
  @media (max-width: 760px) {
    body.pinned { padding-left: 0; }                 /* phones: sidebar overlays */
    body.pinned #shell { left: 0; }
    body.pinned #topbar { left: 12px; }
    #side { width: min(86vw, 320px); border-right: 0; }
    body.pinned #side, body.peek #side { box-shadow: 0 0 40px rgba(0, 0, 0, 0.2); }
    body.pinned #side-scrim, body.peek #side-scrim { opacity: 1; pointer-events: auto; }
    body.pinned #tb-toggle, body.peek #tb-toggle { left: calc(min(86vw, 320px) - 50px); }
  }
  /* ---------- Gemini-style welcome ----------
     Big light greeting that rises in word by word, your name in a moving
     green gradient, a slow ambient glow behind the centred bar, and the
     bar's placeholder cycling through things you can ask. */
  #welcome h1 {
    font-size: 36px; font-weight: 400; letter-spacing: -0.02em; line-height: 1.25;
    max-width: 680px; margin: 0 auto;
  }
  #welcome h1 .w { display: inline-block; opacity: 0; transform: translateY(14px); filter: blur(4px);
    animation: word-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) forwards; }
  @keyframes word-in { to { opacity: 1; transform: none; filter: none; } }
  #welcome h1 .name {
    font-weight: 500;
    background: linear-gradient(90deg, #3F8212, #7BBF22, #A8F03C, #5DA312, #3F8212);
    background-size: 300% 100%; -webkit-background-clip: text; background-clip: text; color: transparent;
    animation: word-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) forwards, shimmer 6s linear 0.8s infinite;
  }
  @keyframes shimmer { to { background-position: 300% 0; } }
  #welcome p:empty { display: none; }
  #welcome p { opacity: 0; animation: word-in 0.8s ease 0.9s forwards; }
  .aura { position: fixed; z-index: -1; border-radius: 50%; pointer-events: none; opacity: 0; transition: opacity 0.8s; }
  body.home .aura { opacity: 1; }
  .aura.a1 { width: 56vw; height: 56vw; max-width: 760px; max-height: 760px; left: 50%; top: 52%;
    margin: -28vw 0 0 -28vw; background: radial-gradient(circle, rgba(168,240,60,0.26), rgba(168,240,60,0) 62%);
    animation: aura1 18s ease-in-out infinite alternate; }
  .aura.a2 { width: 40vw; height: 40vw; left: 26%; top: 18%;
    background: radial-gradient(circle, rgba(63,130,18,0.10), rgba(63,130,18,0) 65%);
    animation: aura2 22s ease-in-out infinite alternate; }
  @keyframes aura1 { from { transform: translate(-6%, 2%) scale(1); } to { transform: translate(6%, -4%) scale(1.12); } }
  @keyframes aura2 { from { transform: translate(0, 0); } to { transform: translate(18%, 10%); } }
  body.home { background: var(--bg); }
  body.home #composer { transition: box-shadow 0.3s; }
  body.home #composer:focus-within { box-shadow: 0 10px 40px rgba(63, 130, 18, 0.16), 0 1px 3px rgba(28, 33, 29, 0.06); }
  @media (max-width: 520px) { #welcome h1 { font-size: 27px; } }
  @media (prefers-reduced-motion: reduce) {
    #welcome h1 .w, #welcome p { animation: none; opacity: 1; transform: none; filter: none; }
    .aura { animation: none; }
  }
  /* ---------- icon rail: the sidebar, collapsed (desktop) ----------
     0.1.158: the lighter look of the older rail again -- on the page itself (no tinted column, no line), light
     grey icons that darken when you point at them, 40px buttons 4px apart: New chat (a pencil), Search chats,
     Workspace, Gink Genie, Media Studio; Settings and your account at the bottom. The logo stays on top: it's
     the sidebar button (point at it and it shows "open sidebar"). */
  #rail {
    position: fixed; top: 0; bottom: 0; left: 0; width: 60px; z-index: 27;
    display: flex; flex-direction: column; align-items: center; padding: calc(54px + env(safe-area-inset-top, 0px)) 0 14px;
  }
  #rail .ibtn { width: 40px; height: 40px; border-radius: 12px; margin: 0 0 4px; color: var(--text-muted); transition: background 0.15s, color 0.15s; }
  #rail .ibtn:hover { color: var(--text-main); background: var(--side-hover); }
  #rail .ibtn svg { width: 20px; height: 20px; }
  #rail .spacer { flex: 1; }
  #rail .avatar { margin: 8px 0 0; width: 32px; height: 32px; cursor: pointer; font-size: 13px; }
  body.pinned #rail { display: none; }
  @media (min-width: 761px) { body:not(.pinned) { padding-left: 60px; } body:not(.pinned) #shell { left: 60px; } }
  @media (max-width: 760px) { #rail { display: none; } }
  /* ---------- attachments ---------- */
  #atts { display: none; flex-wrap: wrap; margin: 0 0 8px; }
  #atts.has { display: flex; }
  .att {
    display: flex; align-items: center; max-width: 240px; margin: 0 8px 6px 0; padding: 5px 8px 5px 5px;
    background: var(--elevated); border: 1px solid var(--border); border-radius: 12px; font-size: 13px;
    animation: word-in 0.3s ease both;
  }
  .att img { width: 38px; height: 38px; object-fit: cover; border-radius: 8px; margin-right: 8px; flex: none; }
  .att .ficon {
    width: 38px; height: 38px; border-radius: 8px; margin-right: 8px; flex: none; display: flex;
    align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent);
    font-size: 11px; font-weight: 700; text-transform: uppercase;
  }
  .att .meta { overflow: hidden; min-width: 0; }
  .att .nm { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
  .att .nt { color: var(--text-muted); font-size: 11.5px; display: block; }
  .att .x {
    margin-left: 6px; border: none; background: transparent; color: var(--text-muted); cursor: pointer;
    width: 22px; height: 22px; border-radius: 6px; font-size: 15px; line-height: 1; flex: none;
  }
  .att .x:hover { background: var(--bg); color: var(--text-main); }
  .att.loading { opacity: 0.6; }
  /* attachments live INSIDE the box, on their own line above the text (Gemini-style), on the new-chat bar too */
  body.home #composer { flex-wrap: wrap; }
  body.home #composer.with-atts { border-radius: 24px; }
  body.home #atts { flex-basis: 100%; order: -1; margin: 4px 4px 6px; justify-content: flex-start; }
  .att.pic { position: relative; padding: 0; border-radius: 16px; overflow: hidden; background: transparent; }
  .att.pic img { width: 96px; height: 96px; margin: 0; border-radius: 16px; }
  .att.pic .meta { display: none; }
  .att.pic .vbadge { position: absolute; left: 6px; bottom: 6px; padding: 1px 7px; border-radius: 999px; background: rgba(0, 0, 0, .6);
                     color: #fff; font-size: 11px; font-weight: 600; line-height: 17px; pointer-events: none; }
  .att.pic .x { position: absolute; top: 5px; right: 5px; margin: 0; background: rgba(0, 0, 0, .55); color: #fff; border-radius: 50%; }
  .att.pic .x:hover { background: rgba(0, 0, 0, .75); color: #fff; }
  body.home #composer { position: relative; }
  #composer.dragging { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
  .uatts { display: flex; flex-wrap: wrap; justify-content: flex-end; margin-bottom: 6px; max-width: 460px; }
  .uatts .att { margin: 0 0 6px 8px; animation: none; }
  .uatts .att.photo { padding: 0; border: none; background: none; }
  .uatts .att.photo img { width: 160px; height: auto; max-height: 200px; margin: 0; border-radius: 14px; border: 1px solid var(--border); }
  .sync-line { font-size: 12px; color: var(--text-muted); display: block; font-weight: 400; overflow: hidden; text-overflow: ellipsis; }
  .side-foot .who { line-height: 1.25; }
  /* ---------- video cards ---------- */
  .vcards { display: -webkit-flex; display: flex; -webkit-flex-wrap: wrap; flex-wrap: wrap; margin: 12px 0 4px; }
  .vcard {
    display: block; margin: 0 12px 12px 0; width: 230px; max-width: 100%; border: 1px solid var(--border); border-radius: 14px; overflow: hidden;
    background: var(--bg); cursor: pointer; text-decoration: none; color: var(--text-main);
    transition: transform 0.15s, box-shadow 0.15s; border-bottom: 1px solid var(--border);
  }
  .vcard:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(28,33,29,0.12); }
  .vcard .thumb { position: relative; padding-top: 56.25%; background: #111 center/cover no-repeat; }
  .vcard .play {
    position: absolute; left: 50%; top: 50%; width: 46px; height: 46px; margin: -23px 0 0 -23px; border-radius: 50%;
    background: rgba(0,0,0,0.62); display: flex; align-items: center; justify-content: center; transition: background 0.15s;
  }
  .vcard:hover .play { background: #E5251B; }
  .vcard .play::after { content: ""; border-left: 15px solid #fff; border-top: 9px solid transparent; border-bottom: 9px solid transparent; margin-left: 4px; }
  .vcard .dur {
    position: absolute; right: 7px; bottom: 7px; background: rgba(0,0,0,0.78); color: #fff; font-size: 11.5px;
    font-weight: 600; padding: 2px 6px; border-radius: 5px;
  }
  .vcard .dur.live { background: #E5251B; }
  .vcard .info { padding: 9px 11px 11px; }
  .vcard .vt { font-size: 13.5px; font-weight: 600; line-height: 1.35; max-height: 2.7em; overflow: hidden; }
  .vcard .vm { font-size: 12px; color: var(--text-muted); margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .vcard.playing { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft); }
  a.vcard::after { content: none !important; }
  /* ---------- Stop ring: shows while Gink is thinking or speaking ---------- */
  #stop .ring {
    position: relative; display: block; width: 19px; height: 19px; border-radius: 50%;
    border: 2.5px solid var(--accent); box-sizing: border-box;
    animation: ring-breathe 1.4s ease-in-out infinite;
  }
  #stop:hover .ring { animation: none; }
  #stop:hover .ring::after {        /* a small stop square on hover */
    content: ""; position: absolute; left: 4.5px; top: 4.5px; width: 5px; height: 5px;
    border-radius: 1px; background: var(--accent);
  }
  @keyframes ring-breathe { 0%, 100% { transform: scale(1); opacity: 1; } 50% { transform: scale(0.86); opacity: 0.75; } }
  /* ---------- phones and tablets (touch) ----------
     16px text in every box: iPhone zooms the whole page into a smaller one when you tap it, and stays
     zoomed and shifted sideways after the keyboard closes. No hover strip at the left edge either (a tap
     there opened the sidebar). */
  @media (hover: none) and (pointer: coarse) {
    input:not([type=checkbox]):not([type=radio]):not([type=range]):not([type=color]):not([type=file]), textarea, select {
      font-size: 16px !important; }
    #edge { display: none; }
  }
  __PYGMENTS_CSS__
</style>
</head>
<body class="home">
  <div id="edge"></div>
  <div class="aura a1"></div><div class="aura a2"></div>
  <nav id="rail">
    <button class="ibtn" data-rail="new" title="New chat"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h8"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg></button>
    <button class="ibtn" data-rail="search" title="Search chats"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg></button>
    <button class="ibtn" data-rail="tasks" title="Workspace"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/></svg></button>
    <button class="ibtn" data-rail="genie" title="Gink Genie"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><g transform="matrix(-1 0 0 1 24 0)"><path d="M2 10.2c1.9.1 3.4 1.2 4.7 2.2 1 .8 2.2 1.4 3.7 1.4h4c2 0 3.7-1.2 4.2-3"/><path d="M7.2 13.4c.7 2 2.6 3.2 4.8 3.2h1.6c2.1 0 3.9-1.3 4.5-3.2"/><path d="M10.6 10.9c0-1.5 1.1-2.6 2.6-2.6s2.6 1.1 2.6 2.6"/><path d="M13.2 8.3V6.9"/><circle cx="13.2" cy="5.9" r="1.1" fill="currentColor" stroke="none"/><path d="M18.6 11.2c1.3-.4 2.7.2 3 1.4.3 1.2-.6 2.4-2 2.6-.5.1-1 0-1.4-.2"/><path d="M11.4 16.6l-.6 2.2h5l-.6-2.2"/><path d="M9.6 18.8h6.6"/></g></svg></button>
    <button class="ibtn" data-rail="media" title="Media Studio"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="M20.5 16l-5-5-8 8.5"/></svg></button>
    <div class="spacer"></div>
    <button class="ibtn" data-rail="settings" title="Settings"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg></button>
    <div class="avatar" id="rail-avatar" data-rail="settings" title="Account">G</div>
  </nav>
  <button class="ibtn tb-toggle" id="tb-toggle" title="Open sidebar" aria-label="Open or close the sidebar"><span class="gmark" aria-hidden="true"></span><svg class="tb-panel" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="3.5"/><path d="M9.5 4.5v15"/></svg></button>
  <div id="side-scrim" aria-hidden="true"></div>
  <div id="topbar">
    <div class="wordmark">Gink <span>Assistant</span></div>
  </div>
  <aside id="side" aria-label="Chats and places">
    <div class="side-head">
      <div class="brand"><span class="gmark" aria-hidden="true"></span><span>Gink</span></div>
    </div>
    <div class="side-nav">
      <button type="button" class="srow" data-nav="new"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h8"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg><span class="lbl">New chat</span><span class="nk" id="nk-new"></span></button>
      <label class="srow" id="side-search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg><input id="side-q" placeholder="Search chats" autocomplete="off" aria-label="Search chats"><span class="nk" id="nk-search"></span></label>
      <button type="button" class="srow" data-nav="tasks"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/></svg><span class="lbl">Workspace</span></button>
      <button type="button" class="srow" data-nav="scheduled"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2.5M9 2h6"/></svg><span class="lbl">Scheduled</span></button>
      <button type="button" class="srow" data-nav="media"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="M20.5 16l-5-5-8 8.5"/></svg><span class="lbl">Media Studio</span></button>
      <button type="button" class="srow" data-nav="genie"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><g transform="matrix(-1 0 0 1 24 0)"><path d="M2 10.2c1.9.1 3.4 1.2 4.7 2.2 1 .8 2.2 1.4 3.7 1.4h4c2 0 3.7-1.2 4.2-3"/><path d="M7.2 13.4c.7 2 2.6 3.2 4.8 3.2h1.6c2.1 0 3.9-1.3 4.5-3.2"/><path d="M10.6 10.9c0-1.5 1.1-2.6 2.6-2.6s2.6 1.1 2.6 2.6"/><path d="M13.2 8.3V6.9"/><circle cx="13.2" cy="5.9" r="1.1" fill="currentColor" stroke="none"/><path d="M18.6 11.2c1.3-.4 2.7.2 3 1.4.3 1.2-.6 2.4-2 2.6-.5.1-1 0-1.4-.2"/><path d="M11.4 16.6l-.6 2.2h5l-.6-2.2"/><path d="M9.6 18.8h6.6"/></g></svg><span class="lbl">Gink Genie</span></button>
    </div>
    <div id="recents"></div>
    <div class="side-foot">
      <div class="avatar" id="avatar">G</div>
      <div class="who"><span id="who">Gink user</span><span class="sync-line" id="sync-line"></span></div>
      <button class="ibtn" id="gear" title="Settings"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg></button>
    </div>
  </aside>
  <div class="menu hidden" id="row-menu">
    <button data-row="rename">__ICON_RENAME__Rename</button>
    <button data-row="pin" id="row-pin">__ICON_PIN__<span>Pin</span></button>
    <button data-row="export">__ICON_EXPORT__Export chat</button>
    <button data-row="share"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" style="width:16px;height:16px" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg>Share link</button>
    <button data-row="archive"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" style="width:16px;height:16px" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8M10 12h4"/></svg>Archive</button>
    <button class="danger" data-row="delete"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" style="width:16px;height:16px" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>Delete</button>
  </div>
  <div id="modal-back">
    <div class="modal" role="dialog" aria-modal="true">
      <h3>Delete chat?</h3>
      <p>This will delete <b id="del-title"></b>.</p>
      <p class="sub">This can\u2019t be undone.</p>
      <div class="actions">
        <button class="pill ghost" id="del-cancel">Cancel</button>
        <button class="pill danger" id="del-ok">Delete</button>
      </div>
    </div>
  </div>
  <button id="temp-btn" type="button" aria-pressed="false" title="A chat that isn't saved or synced"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="width:17px;height:17px"><path d="M6 20V11a6 6 0 0 1 12 0v9l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5z"/><circle cx="10" cy="11" r=".6" fill="currentColor"/><circle cx="14" cy="11" r=".6" fill="currentColor"/></svg>Temporary</button>
  <div id="temp-banner" role="status"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="width:17px;height:17px"><path d="M6 20V11a6 6 0 0 1 12 0v9l-2-1.5-2 1.5-2-1.5-2 1.5-2-1.5z"/><circle cx="10" cy="11" r=".6" fill="currentColor"/><circle cx="14" cy="11" r=".6" fill="currentColor"/></svg>Temporary chat <span>· not saved, not synced, gone when you leave it</span></div>
  <div id="shell">
  <div id="headbar" aria-hidden="true"></div>
  <div id="scroller">
  <div id="feed">
    <div id="welcome">
      <h1 data-text="__WELCOME_TITLE__">__WELCOME_TITLE__</h1>
      <p>__WELCOME_SUBTITLE__</p>
    </div>
  </div>
  </div>
  <div id="composer-wrap">
    <div id="composer">
      <div id="atts"></div>
      <textarea id="cin" rows="1" placeholder="Write a message\u2026"></textarea>
      <div class="crow">
        <div class="menu-anchor">
          <button class="ibtn" id="plus" title="More"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg></button>
          <div class="menu left hidden" id="plus-menu">
            <button data-act="attach">📎 Add photos or files <span class="hint">or paste / drop</span></button>
            <button data-act="camera">\U0001F4F7 Camera <span class="hint">point and ask \u2014 Gink works out the rest</span></button>
            <button data-act="briefing">☀️ Morning briefing</button>
            <button data-act="tasks">\u2705 Tasks &amp; alarms</button>
            <button data-act="song">\U0001F3B5 Identify a song</button>
            <button data-act="news">\U0001F4F0 Today's news</button>
            <button data-act="media">\U0001F3A8 Media Studio</button>
            <button data-act="newchat">\u270F\uFE0F New chat <span class="hint">clears this view</span></button>
          </div>
        </div>
        <span class="spacer"></span>
        <div class="menu-anchor">
          <button class="model" id="model" title="Choose model"><span id="model-name">Gink</span><span class="tier" id="model-tier"></span></button>
          <div class="menu right hidden" id="model-menu"></div>
        </div>
        <button class="ibtn" id="mic" title="Dictate \u2014 speak once, edit, then send"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg></button>
        <button class="ibtn" id="stop" title="Stop" aria-label="Stop" style="display:none"><span class="ring"></span></button>
        <button class="ibtn" id="send" title="Voice conversation"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/></svg></button>
      </div>
    </div>
    <div class="today-wrap"><span class="today" id="today-chip"></span></div>
    <div id="cstatus"></div>
    <div id="suggest" role="group" aria-label="Ideas to start with">
      <button type="button" class="sug" data-fill="Plan my day: ">\u2600\ufe0f Plan my day</button>
      <button type="button" class="sug" data-fill="Search the web for ">\U0001F50E Search the web</button>
      <button type="button" class="sug" data-open="media">\U0001F3A8 Make an image</button>
      <button type="button" class="sug" data-open="genie">\U0001F9DE Build with Genie</button>
      <button type="button" class="sug" data-fill="Explain simply: ">\U0001F4A1 Explain something</button>
    </div>
    <div class="disclaimer">Gink is AI and can make mistakes. Please double-check responses.</div>
  </div>
  </div>
<script>
  var LOGO_URI = "__LOGO_DATA_URI__";
  var SPIN_URI = "__SPIN_DATA_URI__";

  // ---- the visible area (0.1.155) --------------------------------------------------------------
  // The shell is sized to what you can actually see (visualViewport): the phone keyboard, Safari's
  // bars and Android's keyboard handling can't push the composer to the top, hide it, or leave a gap.
  // The conversation scrolls inside #scroller; the page itself never scrolls (no sideways drift).
  var NO_HOVER = !!(window.matchMedia && matchMedia('(hover: none)').matches);
  function scroller() { return document.getElementById('scroller') || document.scrollingElement || document.documentElement; }
  function atEnd(slack) { var s = scroller(); return s.scrollTop + s.clientHeight >= s.scrollHeight - (slack || 80); }
  window.ginkScrollEnd = function (smooth) {
    var s = scroller();
    if (smooth && s.scrollTo) { try { s.scrollTo({top: s.scrollHeight, behavior: 'smooth'}); return; } catch (e) {} }
    s.scrollTop = s.scrollHeight;
  };
  var VV = {tallest: {}, stick: true, last: ''};
  function typingNow() {
    var a = document.activeElement;
    return !!a && (/^(input|textarea|select)$/i.test(a.tagName || '') || !!a.isContentEditable);
  }
  function fitViewport() {
    var vv = window.visualViewport, zoomed = !!vv && vv.scale > 1.01;      // pinch-zoomed: leave it to the browser
    var h = Math.round((vv && !zoomed) ? vv.height : window.innerHeight);
    var top = Math.round((vv && !zoomed) ? Math.max(0, vv.offsetTop) : 0);
    var w = window.innerWidth, body = document.body;
    if (!h || !body) return;
    VV.tallest[w] = Math.max(VV.tallest[w] || 0, h);
    body.classList.toggle('kb', NO_HOVER && typingNow() && h < VV.tallest[w] - 120);   // the keyboard is up
    body.classList.toggle('short', h < 560);
    body.classList.toggle('tiny', h < 470);
    var key = h + ':' + top;
    if (key === VV.last) return;
    var stick = VV.stick;
    VV.last = key;
    document.documentElement.style.setProperty('--app-h', h + 'px');
    document.documentElement.style.setProperty('--vv-top', top + 'px');
    var shell = document.getElementById('shell');
    if (shell) shell.style.transform = top ? 'translateY(' + top + 'px)' : '';
    if (stick) ginkScrollEnd(false);                  // the newest message stays in view above the keyboard
  }
  (function () {
    var later = function () { setTimeout(fitViewport, 60); setTimeout(fitViewport, 360); };
    if (window.visualViewport) {
      visualViewport.addEventListener('resize', fitViewport);
      visualViewport.addEventListener('scroll', fitViewport);
    }
    window.addEventListener('resize', fitViewport);
    window.addEventListener('orientationchange', later);
    document.addEventListener('focusin', later);
    document.addEventListener('focusout', later);
    document.addEventListener('DOMContentLoaded', function () {
      var s = scroller(), shell = document.getElementById('shell'), wrap = document.getElementById('composer-wrap');
      s.addEventListener('scroll', function () {
        VV.stick = atEnd(80);
        document.body.classList.toggle('scrolled', s.scrollTop > 4);
      }, {passive: true});
      var jump = document.getElementById('jump');                  // "jump to latest" rides above the composer
      if (jump && shell && jump.parentNode !== shell) shell.appendChild(jump);
      function composerHeight() {
        if (!wrap) return;
        var was = VV.stick;
        document.documentElement.style.setProperty('--composer-h', Math.round(wrap.offsetHeight) + 'px');
        if (was && !document.body.classList.contains('home')) ginkScrollEnd(false);
      }
      if (window.ResizeObserver && wrap) new ResizeObserver(composerHeight).observe(wrap); else setInterval(composerHeight, 1000);
      if (wrap) wrap.addEventListener('wheel', function (e) {     // the wheel over the box still scrolls the conversation
        if (e.ctrlKey) return;                                        // (pinch-zoom on a trackpad)
        for (var n = e.target; n && n !== wrap; n = n.parentNode)
          if (n.scrollHeight > n.clientHeight + 1 && /(auto|scroll)/.test(getComputedStyle(n).overflowY)) return;   // it scrolls itself
        s.scrollTop += e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      }, {passive: true});
      composerHeight(); fitViewport();
    });
  })();
  // Wide tables scroll sideways in their own box instead of widening the whole page
  function wrapTables(root) {
    if (!root || !root.querySelectorAll) return;
    var list = root.querySelectorAll('table');
    for (var i = 0; i < list.length; i++) {
      var t = list[i], p = t.parentNode;
      if (!p || (p.classList && p.classList.contains('table-wrap'))) continue;
      var box = document.createElement('div'); box.className = 'table-wrap';
      p.insertBefore(box, t); box.appendChild(t);
      // columns as wide as their words need: a long "What we know" column gets room, short ones stay narrow
      var rows = t.rows || [], longest = [];
      for (var r = 0; r < rows.length; r++)
        for (var c = 0; c < rows[r].cells.length; c++)
          longest[c] = Math.max(longest[c] || 0, (rows[r].cells[c].textContent || '').trim().length);
      if (rows.length)
        for (var k = 0; k < rows[0].cells.length; k++) {
          var n = longest[k] || 0;
          rows[0].cells[k].style.minWidth = (n > 90 ? 240 : n > 40 ? 180 : n > 14 ? 120 : 72) + 'px';
        }
    }
  }
  // Tracks which message currently has the logo mark, so finalizeMessage()
  // can move it: remove from wherever it was, add to the reply that just
  // finished. It always sits at the end of the conversation so far,
  // rather than staying pinned to the first reply forever. Reset on
  // clearFeed() since old element ids won't exist in the fresh feed.
  var lastLogoMsgId = null;

  // Link clicks must never navigate THIS page away (see module docstring).
  // An embedded WebView can't reliably open new windows (window.open
  // silently does nothing on macOS), so link clicks go to Python, which
  // opens them in your default browser -- or the right app on a phone
  // (mailto:, tel:, maps, YouTube, ...).
  document.addEventListener('click', function(e) {
    var link = e.target.closest && e.target.closest('a');
    if (link && link.getAttribute('href')) {
      var href = link.getAttribute('href');
      if (href.charAt(0) === '#') return;            // in-page anchors stay here
      if (link.hasAttribute('download')) return;     // downloads (Export...) must reach the browser
      e.preventDefault();
      ginkEmit('open_url', link.href || href);
      link.classList.add('opening');
      setTimeout(function () { link.classList.remove('opening'); }, 900);
    }
  });

  // ---- welcome greeting -------------------------------------------
  var userFirst = '';
  function renderGreeting() {
    var h = document.querySelector('#welcome h1'); if (!h) return;
    var text = h.getAttribute('data-text') || h.textContent; h.innerHTML = '';
    text.split(' ').forEach(function (word, i) {
      var span = document.createElement('span'); span.className = 'w';
      var bare = word.replace(/[^A-Za-z\u00C0-\u024F'-]/g, '');
      if (userFirst && bare && bare.toLowerCase() === userFirst.toLowerCase()) {
        span.className = 'w name'; span.textContent = bare;
        h.appendChild(span);
        var rest = word.slice(word.indexOf(bare) + bare.length);
        if (rest) { var r = document.createElement('span'); r.className = 'w'; r.textContent = rest; r.style.animationDelay = (0.08 * i + 0.05) + 's'; h.appendChild(r); }
      } else { span.textContent = word; h.appendChild(span); }
      span.style.animationDelay = (0.08 * i) + 's';
      h.appendChild(document.createTextNode(' '));
    });
  }
  var EXAMPLES = ['Ask Gink', 'Wake me up at 6:30', 'Remind me to call Mom at 5', 'Plan my week',
                  'What\u2019s the news today?', 'Help me study for my exam', 'Ask Gink'];
  var exIdx = 0, exTimer = null;
  function cyclePlaceholder() {
    clearTimeout(exTimer);
    if (!document.body.classList.contains('home')) return;
    var t = cin(); if (t.value || document.activeElement === t) { exTimer = setTimeout(cyclePlaceholder, 3000); return; }
    exIdx = (exIdx + 1) % EXAMPLES.length; t.placeholder = EXAMPLES[exIdx];
    exTimer = setTimeout(cyclePlaceholder, exIdx === 0 ? 6000 : 2600);
  }

  // ---- sidebar ----------------------------------------------------
  var sessions = [], rowMenuFor = null, deleteFor = null, peekTimer = null;
  var hoverBlocked = false;   // after a click-to-close, don't re-open until the mouse leaves
  function sideOpen() { return document.body.classList.contains('pinned') || document.body.classList.contains('peek'); }
  function setPinned(on) {
    document.body.classList.toggle('pinned', on);
    document.body.classList.remove('peek');
    try { localStorage.setItem('gink-side-pinned', on ? '1' : '0'); } catch (e) {}
    syncToggle();
  }
  function syncToggle() {                              // the sidebar button's tooltip: what a click will do
    var tb = document.getElementById('tb-toggle');
    if (tb) tb.title = sideOpen() ? 'Close sidebar' : 'Open sidebar';
  }
  function peek(on) {
    clearTimeout(peekTimer);
    if (on && NO_HOVER) return;                       // touch screens: only the button opens the sidebar
    if (on) {
      if (hoverBlocked || document.body.classList.contains('peek')) return;   // already open: just don't close it
      // a moment's rest first: passing the edge on the way to the icon rail no longer slides the sidebar over it
      peekTimer = setTimeout(function () { if (!hoverBlocked) { document.body.classList.add('peek'); syncToggle(); } }, PEEK_DELAY);
    } else peekTimer = setTimeout(function () { document.body.classList.remove('peek'); syncToggle(); }, 260);
  }
  var PEEK_DELAY = 300;
  function toggleSidebar() {
    if (sideOpen()) { setPinned(false); hoverBlocked = true; }   // click to close
    else { setPinned(true); }                                     // click to open
  }
  var knownIds = null, typedTitles = {};   // knownIds null = first load (no animation)
  function typeTitle(span, text) {
    span.classList.add('typing'); span.textContent = '';
    var i = 0, step = Math.max(14, Math.min(38, 900 / Math.max(text.length, 1)));
    (function next() {
      if (!document.body.contains(span)) return;
      i++; span.textContent = text.slice(0, i);
      if (i < text.length) setTimeout(next, step);
      else setTimeout(function () { span.classList.remove('typing'); }, 500);
    })();
  }
  // Chats grouped by day, newest first (s.when: ms since 1970 -- the apps and the web app send it)
  function dayGroup(ms) {
    if (!ms) return 'Recents';
    var now = new Date(), start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime(), day = 86400000;
    if (ms >= start) return 'Today';
    if (ms >= start - day) return 'Yesterday';
    if (ms >= start - 7 * day) return 'Previous 7 days';
    if (ms >= start - 30 * day) return 'Previous 30 days';
    try { return new Date(ms).toLocaleDateString(undefined, {month: 'long', year: 'numeric'}); } catch (e) { return 'Older'; }
  }
  function recentsHead(box, text) {
    var h = document.createElement('div'); h.className = 'recents-head'; h.textContent = text; box.appendChild(h);
  }
  function renderRecents() {
    var q = (document.getElementById('side-q').value || '').toLowerCase();
    var box = document.getElementById('recents'); box.innerHTML = '';
    var shown = sessions.filter(function (s) { return !q || s.title.toLowerCase().indexOf(q) >= 0; });
    if (!shown.length) {
      recentsHead(box, q ? 'Results' : 'Recents');
      var e = document.createElement('div'); e.className = 'empty-recents';
      e.innerText = q ? 'No chats match \u201c' + q + '\u201d' : 'Your chats will appear here';
      box.appendChild(e); return;
    }
    var pinned = shown.filter(function (s) { return s.pinned; }), rest = shown.filter(function (s) { return !s.pinned; });
    shown = pinned.concat(rest);
    var lastHead = null;
    shown.forEach(function (s) {
      var head = q ? 'Results' : s.pinned ? 'Pinned' : dayGroup(s.when);
      if (head !== lastHead) { lastHead = head; recentsHead(box, head); }
      var b = document.createElement('div'); b.className = 'recent' + (s.current ? ' current' : '') + (s.pinned ? ' pinned' : '');
      b.setAttribute('data-id', s.id); b.setAttribute('role', 'button');
      b.innerHTML = '<span class="t"></span><button class="more" title="More"><svg viewBox=\\"0 0 24 24\\" fill=\\"currentColor\\"><circle cx=\\"5\\" cy=\\"12\\" r=\\"1.6\\"/><circle cx=\\"12\\" cy=\\"12\\" r=\\"1.6\\"/><circle cx=\\"19\\" cy=\\"12\\" r=\\"1.6\\"/></svg></button>';
      b.title = s.title;
      var span = b.querySelector('.t');
      box.appendChild(b);                  // on the page FIRST: typeTitle stops if its element isn't on the page
      if (s.animate && typedTitles[s.id] !== s.title) {
        typedTitles[s.id] = s.title;
        b.classList.add('fresh'); typeTitle(span, s.title);
      } else {
        span.textContent = s.title;
      }
    });
  }
  function setSessions(list) {
    sessions = list || [];
    var ids = {};
    sessions.forEach(function (s) {
      ids[s.id] = s.title;
      // animate chats that just appeared (newly saved, or branched) -- and a chat
      // whose title just changed (its automatic smart title arriving)
      s.animate = knownIds !== null && (!(s.id in knownIds) || knownIds[s.id] !== s.title);
    });
    knownIds = ids;
    renderRecents();
    sessions.forEach(function (s) { s.animate = false; });   // only once
  }
  function setUser(name, photo, callName) {
    document.getElementById('who').textContent = name || 'Gink user';
    var initial = (name || 'G').trim().charAt(0).toUpperCase();
    ['avatar', 'rail-avatar'].forEach(function (id) {
      var el = document.getElementById(id); if (!el) return;
      if (photo) { el.innerHTML = ''; var im = document.createElement('img'); im.src = photo; im.alt = '';
        im.style.cssText = 'width:100%;height:100%;object-fit:cover;border-radius:50%'; el.appendChild(im); el.style.overflow = 'hidden'; }
      else { el.textContent = initial; }
    });
    var first = (callName || name || '').trim().split(' ')[0];
    if (first && first !== userFirst) { userFirst = first; renderGreeting(); }
  }
  function openDelete(id) {
    var s = sessions.filter(function (x) { return x.id === id; })[0];
    deleteFor = id;
    document.getElementById('del-title').innerText = s ? s.title : 'this chat';
    document.getElementById('modal-back').classList.add('open');
    document.getElementById('del-cancel').focus();
  }
  function closeDelete() { deleteFor = null; document.getElementById('modal-back').classList.remove('open'); }

  document.addEventListener('DOMContentLoaded', function () {
    var pinned = window.innerWidth >= 1000;
    try { var saved = localStorage.getItem('gink-side-pinned'); if (saved !== null) pinned = saved === '1'; } catch (e) {}
    if (window.innerWidth < 760) pinned = false;
    document.body.classList.toggle('pinned', pinned);
    syncToggle();

    var edge = document.getElementById('edge'), side = document.getElementById('side');
    var tb = document.getElementById('tb-toggle');
    edge.addEventListener('mouseenter', function () { peek(true); });
    side.addEventListener('mouseenter', function () { peek(true); });
    function leave(e) {
      var to = e.relatedTarget;
      if (to && (side.contains(to) || tb.contains(to) || to === edge)) return;   // still on the sidebar
      hoverBlocked = false; peek(false);
    }
    side.addEventListener('mouseleave', leave);
    tb.addEventListener('mouseleave', leave);
    edge.addEventListener('mouseleave', leave);
    tb.addEventListener('click', toggleSidebar);
    document.getElementById('gear').addEventListener('click', function () { ginkEmit('open', 'settings'); });
    document.getElementById('rail').addEventListener('click', function (e) {
      var b = e.target.closest('[data-rail]'); if (!b) return;
      var what = b.getAttribute('data-rail');
      if (what === 'new') ginkEmit('new_chat');
      else if (what === 'search') { setPinned(true); document.body.classList.add('searching'); setTimeout(function () { document.getElementById('side-q').focus(); }, 300); }
      else ginkEmit('open', what);
    });
    renderGreeting(); exTimer = setTimeout(cyclePlaceholder, 3500);
    document.getElementById('suggest').addEventListener('click', function (e) {
      var b = e.target.closest('.sug'); if (!b) return;
      if (b.getAttribute('data-open')) { ginkEmit('open', b.getAttribute('data-open')); return; }
      var cin = document.getElementById('cin'); cin.value = b.getAttribute('data-fill'); cin.focus();
      cin.dispatchEvent(new Event('input', { bubbles: true }));
      try { cin.setSelectionRange(cin.value.length, cin.value.length); } catch (err) {}
    });
    side.addEventListener('click', function (e) {                       // New chat and the places
      var b = e.target.closest('[data-nav]'); if (!b) return;
      var what = b.getAttribute('data-nav');
      if (what === 'new') ginkEmit('new_chat');
      else if (what === 'scheduled') { if (window.openSettings) openSettings('schedules'); }   // scheduled tasks (0.1.161)
      else ginkEmit('open', what);
      if (window.innerWidth < 760) setPinned(false);
    });
    document.getElementById('side-scrim').addEventListener('click', function () { setPinned(false); hoverBlocked = true; });
    var mac = /Mac|iPhone|iPad/.test(navigator.platform || '');          // the keyboard shortcuts, shown where there's a keyboard
    if (!NO_HOVER) {
      document.getElementById('nk-new').textContent = mac ? '\u21e7\u2318O' : 'Ctrl \u21e7 O';
      document.getElementById('nk-search').textContent = mac ? '\u2318K' : 'Ctrl K';
    }
    document.getElementById('side-q').addEventListener('input', renderRecents);
    document.getElementById('side-q').addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { this.value = ''; renderRecents(); this.blur(); }
    });
    document.getElementById('recents').addEventListener('click', function (e) {
      var row = e.target.closest('.recent'); if (!row) return;
      var id = row.getAttribute('data-id');
      if (e.target.closest('.more')) {
        e.stopPropagation();
        var m = document.getElementById('row-menu'), r = e.target.closest('.more').getBoundingClientRect();
        closeMenus(); rowMenuFor = id;
        m.style.left = Math.min(r.left, window.innerWidth - 170) + 'px'; m.style.top = (r.bottom + 4) + 'px';
        m.classList.remove('hidden'); return;
      }
      ginkEmit('select_session', id);
      if (window.innerWidth < 760) setPinned(false);
    });
    document.getElementById('row-menu').addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      closeMenus(); if (b.getAttribute('data-row') === 'delete' && rowMenuFor) openDelete(rowMenuFor);
    });
    document.getElementById('del-cancel').addEventListener('click', closeDelete);
    document.getElementById('del-ok').addEventListener('click', function () {
      if (deleteFor) { ginkEmit('delete_session', deleteFor); sessions = sessions.filter(function (s) { return s.id !== deleteFor; }); renderRecents(); }
      closeDelete();
    });
    document.getElementById('modal-back').addEventListener('click', function (e) { if (e.target.id === 'modal-back') closeDelete(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeDelete(); closeMenus(); } });
    renderRecents();
  });

  // ---- attachments ------------------------------------------------
  function attChip(a, removable, idx) {
    var d = document.createElement('div');
    d.className = 'att' + (a.kind === 'image' && !removable ? ' photo' : '') + (removable && a.thumb ? ' pic' : '');
    if (a.loading) d.className += ' loading';
    var ext = (a.name.split('.').pop() || 'file').slice(0, 4);
    if (a.thumb) { var im = document.createElement('img'); im.src = a.thumb; d.appendChild(im); }
    else { var f = document.createElement('div'); f.className = 'ficon'; f.textContent = ext; d.appendChild(f); }
    if (a.kind === 'video' && a.thumb && removable) {       // a video's first frame: a play mark and its length
      var vb = document.createElement('span'); vb.className = 'vbadge';
      vb.textContent = '\u25b6 ' + String(a.note || '').split('\u00b7').pop().trim(); d.appendChild(vb);
    }
    if (removable || a.kind !== 'image') {
      var meta = document.createElement('span'); meta.className = 'meta';
      var nm = document.createElement('span'); nm.className = 'nm'; nm.textContent = a.name; meta.appendChild(nm);
      if (a.note || a.loading) { var nt = document.createElement('span'); nt.className = 'nt'; nt.textContent = a.loading ? 'Reading\u2026' : a.note; meta.appendChild(nt); }
      d.appendChild(meta);
    }
    if (removable && !a.loading) {
      var x = document.createElement('button'); x.className = 'x'; x.title = 'Remove'; x.textContent = '\u00d7';
      x.addEventListener('click', function () { ginkEmit('remove_attachment', idx); });
      d.appendChild(x);
    }
    return d;
  }
  var composerAtts = [];
  function setAttachments(list) {
    composerAtts = list || [];
    var box = document.getElementById('atts'); box.innerHTML = '';
    composerAtts.forEach(function (a, i) { box.appendChild(attChip(a, true, i)); });
    box.classList.toggle('has', composerAtts.length > 0);
    var comp = document.getElementById('composer'); if (comp) comp.classList.toggle('with-atts', composerAtts.length > 0);
    refreshSend();
  }
  // ---- videos (0.1.162): a few frames, in order, go to the AI as pictures -- the video itself stays here. The
  // browser engine plays it (no extra library): <video> + canvas, at evenly spaced moments.
  var VIDEO_RE = /\\.(mp4|mov|m4v|webm|3gp|avi|mkv)$/i;
  function isVideo(file) { return /^video\\//.test(file.type || '') || VIDEO_RE.test(file.name || ''); }
  function videoFrames(src, done) {
    var v = document.createElement('video'), frames = [], times = [], k = 0, over = false;
    v.muted = true; v.playsInline = true; v.preload = 'auto';
    function end(err) {
      if (over) return; over = true; clearTimeout(timer);
      var d = v.duration;
      try { v.removeAttribute('src'); v.load(); } catch (e) {}
      done(err, frames, isFinite(d) ? d : 0);
    }
    var timer = setTimeout(function () { end(frames.length ? null : 'slow'); }, 25000);
    v.onerror = function () { end('unreadable'); };
    v.onloadedmetadata = function () {
      var d = isFinite(v.duration) && v.duration > 0 ? v.duration : 1, n = d < 3 ? 2 : d < 15 ? 4 : 5;
      for (var i = 0; i < n; i++) times.push(Math.min(Math.max(0, d - 0.1), (i + 0.5) * d / n));
      v.currentTime = times[0];
    };
    v.onseeked = function () {
      try {
        var w = v.videoWidth, h = v.videoHeight;
        if (!w || !h) return end('unreadable');
        var sc = Math.min(1, 960 / Math.max(w, h)), c = document.createElement('canvas');
        c.width = Math.round(w * sc); c.height = Math.round(h * sc);
        c.getContext('2d').drawImage(v, 0, 0, c.width, c.height);
        frames.push({at: Math.round(times[k] * 10) / 10, data: c.toDataURL('image/jpeg', 0.82)});
      } catch (e) { return end('unreadable'); }
      k++;
      if (k < times.length) v.currentTime = times[k]; else end(null);
    };
    v.src = src;
  }
  function videoToChat(src, name, after) {
    setAttachments(composerAtts.concat([{name: name, kind: 'file', loading: true}]));
    videoFrames(src, function (err, frames, duration) {
      if (after) after();
      ginkEmit('attach_video', err || !frames.length ? {name: name, error: err || 'unreadable'}
                                                     : {name: name, duration: duration, frames: frames});
    });
  }
  window.videoFromData = function (dataUrl, name) { videoToChat(dataUrl, name); };   // the apps' file picker
  function readAndEmit(file) {
    if (isVideo(file)) {                                   // only its frames leave the page: no 20 MB limit here
      var vurl = URL.createObjectURL(file);
      return videoToChat(vurl, file.name || ('video-' + Date.now() + '.mp4'), function () { URL.revokeObjectURL(vurl); });
    }
    if (file.size > 20 * 1024 * 1024) { setStatus(file.name + ' is over 20 MB.'); return; }
    var name = file.name || ('pasted-' + Date.now() + '.png');
    setAttachments(composerAtts.concat([{name: name, kind: 'file', loading: true}]));
    var r = new FileReader();
    r.onload = function () {
      var url = r.result;
      if (/^image\\//.test(file.type) && !/gif/.test(file.type)) {
        // shrink big photos here so the hand-off to Python stays small
        var img = new Image();
        img.onload = function () {
          var max = 1600, w = img.width, h = img.height, k = Math.min(1, max / Math.max(w, h));
          var c = document.createElement('canvas'); c.width = Math.round(w * k); c.height = Math.round(h * k);
          c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
          ginkEmit('attach_data', {name: name.replace(/\\.\\w+$/, '') + '.jpg', data: c.toDataURL('image/jpeg', 0.88)});
        };
        img.onerror = function () { ginkEmit('attach_data', {name: name, data: url}); };
        img.src = url;
      } else { ginkEmit('attach_data', {name: name, data: url}); }
    };
    r.readAsDataURL(file);
  }
  document.addEventListener('DOMContentLoaded', function () {
    var comp = document.getElementById('composer');
    cin().addEventListener('paste', function (e) {
      var items = (e.clipboardData && e.clipboardData.files) || [];
      if (items.length) { e.preventDefault(); Array.prototype.forEach.call(items, readAndEmit); }
    });
    ['dragenter', 'dragover'].forEach(function (ev) {
      document.addEventListener(ev, function (e) { e.preventDefault(); comp.classList.add('dragging'); });
    });
    ['dragleave', 'drop'].forEach(function (ev) {
      document.addEventListener(ev, function (e) { e.preventDefault(); if (ev === 'drop' || !e.relatedTarget) comp.classList.remove('dragging'); });
    });
    document.addEventListener('drop', function (e) {
      var files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length) Array.prototype.forEach.call(files, readAndEmit);
    });
  });
  function setSyncStatus(text) { var el = document.getElementById('sync-line'); if (el) el.textContent = text || ''; }

  // ---- video cards ---------------------------------------------------
  // Links like "[▶ Title — Channel · 12:34](https://www.youtube.com/watch?v=ID)" become cards.
  var YT_RE = /(?:youtube\\.com\\/watch\\?v=|youtu\\.be\\/|youtube\\.com\\/live\\/)([A-Za-z0-9_-]{11})/;
  function upgradeVideoLinks(root) {
    if (!root) return;
    var links = Array.prototype.slice.call(root.querySelectorAll('a[href]'));
    var groups = [];
    links.forEach(function (a) {
      var text = a.textContent || '', m = (a.getAttribute('href') || '').match(YT_RE);
      if (!m || text.charAt(0) !== '\u25b6') return;
      var body = text.replace(/^\u25b6\\s*/, ''), parts = body.split(' \u2014 ');
      var title = parts[0], meta = (parts[1] || '').split(' \u00b7 ');
      var dur = '', rest = [];
      meta.forEach(function (x) { if (/^\\d+(:\\d\\d)+$/.test(x) || x === 'LIVE') dur = x; else if (x) rest.push(x); });
      var card = document.createElement('a');
      card.className = 'vcard'; card.setAttribute('data-vid', m[1]); card.setAttribute('data-title', title);
      card.innerHTML = '<div class="thumb"><div class="play"></div></div><div class="info"><div class="vt"></div><div class="vm"></div></div>';
      card.querySelector('.thumb').style.backgroundImage = "url('https://i.ytimg.com/vi/" + m[1] + "/hqdefault.jpg')";
      if (dur) { var d = document.createElement('span'); d.className = 'dur' + (dur === 'LIVE' ? ' live' : ''); d.textContent = dur === 'LIVE' ? '\u25cf LIVE' : dur; card.querySelector('.thumb').appendChild(d); }
      card.querySelector('.vt').textContent = title;
      card.querySelector('.vm').textContent = rest.join(' \u00b7 ');
      // a paragraph that only held this link is replaced; cards next to each other share one grid
      var p = a.parentNode, host = (p && p.tagName === 'P' && p.textContent.trim() === text.trim()) ? p : a;
      var prev = host.previousElementSibling;
      var grid = (prev && prev.className === 'vcards') ? prev : null;
      if (!grid) { grid = document.createElement('div'); grid.className = 'vcards'; host.parentNode.insertBefore(grid, host); }
      grid.appendChild(card); host.parentNode.removeChild(host);
    });
  }
  function markPlaying(id) {
    document.querySelectorAll('.vcard').forEach(function (c) { c.classList.toggle('playing', c.getAttribute('data-vid') === id); });
  }
  document.addEventListener('click', function (e) {
    var c = e.target.closest && e.target.closest('.vcard');
    if (!c) return;
    e.preventDefault(); e.stopPropagation();
    markPlaying(c.getAttribute('data-vid'));
    ginkEmit('play_video', {id: c.getAttribute('data-vid'), title: c.getAttribute('data-title')});
  }, true);

  // ---- composer + bridge ----------------------------------------------
  // Toga's WebView has no JS->Python callback, so the page queues events
  // and Python polls ginkTake(ack, page) a few times a second (WebChatFeed.poll, ui/page_events.py).
  var ginkEvents = [], ginkSeq = 0, ginkPage = String(Date.now()) + Math.random().toString(36).slice(2, 8);
  function ginkEmit(type, value) { ginkEvents.push({seq: ++ginkSeq, type: type, value: value === undefined ? null : value}); }
  function ginkTake(ack, page) {   /* ui/page_events.py: kept until the next poll confirms it arrived */
    if (page === ginkPage) ginkEvents = ginkEvents.filter(function (e) { return e.seq > ack; });
    return JSON.stringify({page: ginkPage, events: ginkEvents});
  }

  var SEND_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M6 11l6-6 6 6"/></svg>';
  var WAVE_ICON = null;
  var composerBusy = false, voiceOn = false;

  function cin() { return document.getElementById('cin'); }
  function autoGrow() {
    var t = cin();
    if (!t.value) { t.style.height = ''; return; }     // empty: natural one-line height
    t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 180) + 'px';
  }
  function syncPlaceholder() {
    var home = document.body.classList.contains('home');
    cin().placeholder = home ? 'Ask Gink' : 'Write a message\u2026';
    layoutComposer(home);
  }
  // Home: [+][text box][model][mic] in one pill row.
  // Chat: text box on top, controls row underneath.
  function layoutComposer(home) {
    var t = cin(), row = document.querySelector('#composer .crow'), spacer = row.querySelector('.spacer');
    t.rows = 1;
    if (home && t.parentNode !== row) { row.insertBefore(t, spacer); }
    else if (!home && t.parentNode === row) { row.parentNode.insertBefore(t, row); }
    t.style.height = '';                 // re-measure after the browser re-lays it out
    setTimeout(autoGrow, 0);
  }
  document.addEventListener('DOMContentLoaded', function () {
    new MutationObserver(syncPlaceholder).observe(document.body, {attributes: true, attributeFilter: ['class']});
    syncPlaceholder();
  });

  var speakingNow = false;
  function refreshSend() {
    var b = document.getElementById('send');
    var st = document.getElementById('stop');
    if (WAVE_ICON === null) WAVE_ICON = b.innerHTML;
    var hasText = cin().value.trim().length > 0 || (typeof composerAtts !== 'undefined' && composerAtts.length > 0);
    if (hasText) { b.innerHTML = SEND_ICON; b.classList.add('ready'); b.title = 'Send'; b.classList.remove('on'); }
    else { b.innerHTML = WAVE_ICON; b.classList.remove('ready'); b.title = voiceOn ? 'Stop voice conversation' : 'Voice conversation'; b.classList.toggle('on', voiceOn); }
    b.disabled = composerBusy && hasText;
    // While Gink thinks or speaks, the ring replaces the voice button and acts as Stop.
    var showStop = composerBusy || speakingNow;
    if (st) st.style.display = showStop ? '' : 'none';
    b.style.display = (composerBusy || (speakingNow && !hasText)) ? 'none' : '';
  }
  function submitComposer() {
    var text = cin().value.trim();
    if ((!text && !composerAtts.length) || composerBusy) return;
    if (composerAtts.some(function (a) { return a.loading; })) { setStatus('Still reading your file\u2026'); return; }
    window.__sentAt = Date.now();                     // answers after this may open the code viewer
    if (!composerAtts.length && window.peopleIntercept && peopleIntercept(text)) {   // "photos of Awa": People, on this device
      cin().value = ''; autoGrow(); refreshSend(); return;
    }
    ginkEmit('send', text);
    cin().value = ''; autoGrow(); refreshSend();
  }
  function closeMenus() { document.querySelectorAll('.menu').forEach(function (m) { m.classList.add('hidden'); }); }

  document.addEventListener('DOMContentLoaded', function () {
    var t = cin();
    t.addEventListener('input', function () { autoGrow(); refreshSend(); });
    t.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.isComposing) {
        // Settings -> Keyboard: Enter sends (Shift+Enter = new line), or Cmd/Ctrl+Enter sends (Enter = new line)
        var mod = e.metaKey || e.ctrlKey;
        if (KB.send_mod ? mod : (!e.shiftKey && !mod)) { e.preventDefault(); submitComposer(); }
        else if (!KB.send_mod && mod) { e.preventDefault(); submitComposer(); }
      }
    });
    document.getElementById('send').addEventListener('click', function () {
      if (cin().value.trim()) submitComposer(); else voiceButton();
    });
    document.getElementById('mic').addEventListener('click', function () { ginkEmit('dictate'); });
    document.getElementById('stop').addEventListener('click', function () {
      ginkEmit('stop');
      speakingNow = false; composerBusy = false; refreshSend();   // respond instantly; Python confirms
    });
    document.getElementById('plus').addEventListener('click', function (e) {
      e.stopPropagation(); var m = document.getElementById('plus-menu'); var was = m.classList.contains('hidden'); closeMenus(); if (was) m.classList.remove('hidden');
    });
    var mbtn = document.getElementById('model'), mmenu = document.getElementById('model-menu');
    function openModelMenu() { clearTimeout(MM.timer); if (mmenu.classList.contains('hidden')) { closeMenus(); MM.view = 'main'; drawModelMenu(); mmenu.classList.remove('hidden'); } }
    function laterCloseModelMenu() { clearTimeout(MM.timer); MM.timer = setTimeout(function () { mmenu.classList.add('hidden'); }, 350); }
    mbtn.addEventListener('click', function (e) {
      e.stopPropagation(); if (mmenu.classList.contains('hidden')) openModelMenu(); else mmenu.classList.add('hidden');
    });
    if (window.matchMedia && matchMedia('(hover: hover)').matches) {        // mouse: opens on touch, closes on leaving
      mbtn.addEventListener('mouseenter', openModelMenu); mbtn.addEventListener('mouseleave', laterCloseModelMenu);
      mmenu.addEventListener('mouseenter', function () { clearTimeout(MM.timer); }); mmenu.addEventListener('mouseleave', laterCloseModelMenu);
    }
    document.getElementById('plus-menu').addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return; closeMenus();
      if (b.getAttribute('data-act') === 'camera') { openCamera(); return; }
      ginkEmit('menu', b.getAttribute('data-act'));
    });
    document.getElementById('model-menu').addEventListener('click', function (e) {
      e.stopPropagation(); var b = e.target.closest('button'); if (!b) return;
      if (b.hasAttribute('data-view')) { MM.view = b.getAttribute('data-view'); drawModelMenu(); return; }
      if (b.hasAttribute('data-back')) { MM.view = 'main'; drawModelMenu(); return; }
      if (b.hasAttribute('data-effort')) { MM.effort = b.getAttribute('data-effort'); drawModelMenu(); closeMenus();
        ginkEmit('setting', {key: 'effort', value: MM.effort}); return; }
      if (b.hasAttribute('data-id')) { closeMenus(); MM.current = b.getAttribute('data-id'); setModels([], MM.current);
        ginkEmit('model', MM.current); }
    });
    document.addEventListener('click', closeMenus);
    refreshSend(); if (!NO_HOVER) t.focus();      // phones: the keyboard opens when YOU tap the box
  });

  // ---- called from Python --------------------------------------------
  var lastToday = '';
  function setToday(text) {
    lastToday = text || '';
    var c = document.getElementById('today-chip');
    if (c) c.innerText = lastToday;
  }
  function setComposerBusy(busy) { composerBusy = busy; var o = document.getElementById('orb'); if (o) o.classList.toggle('busy', busy); document.getElementById('send').classList.toggle('busy', busy); refreshSend(); }
  function setVoiceOn(on) { voiceOn = on; var o = document.getElementById('orb'); if (o) o.classList.toggle('listening', on); refreshSend(); }
  function setSpeaking(on) { speakingNow = !!on; refreshSend(); }
  function setDictating(on) { var m = document.getElementById('mic'); m.classList.toggle('on', on); m.disabled = on; }
  function setStatus(text) { document.getElementById('cstatus').innerText = text || ''; }
  function insertComposerText(text) { var t = cin(); t.value = t.value ? (t.value.replace(/\\s+$/, '') + ' ' + text) : text; autoGrow(); refreshSend(); t.focus(); }
  // ---- The model menu (like Claude's): the current model, Effort, More models (only Gink's three)
  var GINK_MODELS = [
    {id: 'openai/gpt-oss-120b', name: 'Gink Crystal', desc: 'For complex work and everyday tasks'},
    {id: 'openai/gpt-oss-20b', name: 'Gink Flake', desc: 'The fastest, for quick answers'},
    {id: 'qwen/qwen3.8-27b', name: 'Gink Prism', desc: 'Careful reasoning, in many languages'}];
  var EFFORTS = [['low', 'Low'], ['medium', 'Medium', 'Recommended'], ['high', 'High'], ['extra', 'Extra'],
                 ['max', 'Max', '\u26a0 Uses more of your limit']];
  var MM = {current: '', names: {}, available: [], effort: 'medium', view: 'main', timer: null};
  function mmInfo(id) {
    for (var i = 0; i < GINK_MODELS.length; i++) if (GINK_MODELS[i].id === id) return GINK_MODELS[i];
    return {id: id, name: MM.names[id] || 'Gink', desc: /^gink-/.test(id) ? 'Gink\u2019s own model' : ''};
  }
  // ---- Camera: no modes to choose. Gink's server looks at every photo with the same rules (services/vision_rules.py):
  // it works out what the picture needs -- reads text, finds what's wrong and how to fix it, solves homework,
  // explains what's inside things -- and is careful with anything about health. Your chat shows only your question.
  var CARE_MODE = false;                       // a workspace in healthcare mode (the apps and the web app say so)
  window.setCareMode = function (on) { CARE_MODE = !!on; var h = document.querySelector('#live-cam .live-hint'); if (h) h.textContent = liveHint(); };
  function liveHint() {
    return CARE_MODE ? 'Healthcare workspace: never point the camera at patients, wristbands, charts or screens with patient details.'
                     : 'Point at anything and ask \u2014 or just say it. Don\u2019t film people without their permission, or patient records.';
  }
  function openCamera() { openLive(); }

  // ---- Live camera: the camera stays on, full screen. Each question (typed or spoken -- the microphone listens by
  // itself) goes with the frame the camera sees at that moment; the answer shows over the picture and lands in the
  // chat as usual. Nothing is sent until you ask, and Live closes when you leave the window. Where the camera can't
  // run inside the page (some app windows), Gink takes a photo with the system camera instead.
  var LIVE = null;
  function liveLastAnswer() {
    var all = document.querySelectorAll('#feed .assistant-text'); var el = all[all.length - 1];
    if (!el || el.querySelector('.gink-spin')) return '';
    return (el.innerText || el.textContent || '').trim();
  }
  function closeLive() {
    if (!LIVE) return;
    try { if (LIVE.stream) LIVE.stream.getTracks().forEach(function (t) { t.stop(); }); } catch (e) {}
    if (LIVE.screen && !LIVE.stream) ginkEmit('screen_view', { on: false });    // the apps stop sending frames
    try { if (LIVE.rec) LIVE.rec.abort(); } catch (e) {}
    if (LIVE.obs) LIVE.obs.disconnect();
    clearTimeout(LIVE.again);
    document.removeEventListener('keydown', LIVE.onKey);
    document.removeEventListener('visibilitychange', LIVE.onVis);
    LIVE.el.remove(); LIVE = null;
  }
  function liveFrame(video) {                        // the camera, a shared screen (video) or the apps' screen frames (img)
    var w = video.videoWidth || video.naturalWidth, h = video.videoHeight || video.naturalHeight; if (!w) return '';
    var k = Math.min(1, 1280 / Math.max(w, h)), c = document.createElement('canvas');
    c.width = Math.round(w * k); c.height = Math.round(h * k);
    c.getContext('2d').drawImage(video, 0, 0, c.width, c.height);
    return c.toDataURL('image/jpeg', 0.85);
  }
  function openLive(facing) {                        // facing: 'environment' | 'user' | 'screen' (screen view)
    closeLive();
    var md = navigator.mediaDevices, screen = facing === 'screen', start;
    if (screen) {
      if (window.GINK_NATIVE_SCREEN) start = Promise.resolve(null);              // the apps send the frames (liveScreenFrame)
      else if (md && md.getDisplayMedia) start = md.getDisplayMedia({ video: true, audio: false });
      else { if (window.lmSay) lmSay('Screen view isn\u2019t available here: use the Gink app or a computer browser.'); return; }
    } else {
      if (!md || !md.getUserMedia) { cameraFallback(); return; }             // the system camera instead
      start = md.getUserMedia({ video: { facingMode: facing || 'environment', width: { ideal: 1920 } }, audio: false });
    }
    start.then(function (stream) {
      var root = document.createElement('div'); root.id = 'live-cam'; root.setAttribute('role', 'dialog'); root.setAttribute('aria-label', screen ? 'Live screen view' : 'Live camera');
      if (screen) root.className = 'screen';
      var video;
      if (stream) { video = document.createElement('video'); video.autoplay = true; video.playsInline = true; video.muted = true; video.srcObject = stream; }
      else { video = document.createElement('img'); video.className = 'live-shot'; video.alt = 'Your screen'; ginkEmit('screen_view', { on: true }); }
      if (stream) stream.getVideoTracks().forEach(function (t) { t.onended = function () { if (LIVE && LIVE.stream === stream) closeLive(); }; });   // "Stop sharing"
      var flash = document.createElement('div'); flash.className = 'live-flash';
      var top = document.createElement('div'); top.className = 'live-top';
      top.innerHTML = '<span class="live-dot"></span><span class="live-title">' + (screen ? 'Live \u00b7 Your screen' : 'Live') + '</span>';
      var flip = document.createElement('button'); flip.type = 'button'; flip.className = 'live-flip';
      flip.title = screen ? 'Use the camera' : 'Switch camera'; flip.textContent = screen ? '\U0001F4F7' : '\u21BB';
      var scr = document.createElement('button'); scr.type = 'button'; scr.className = 'live-flip'; scr.title = 'Show Gink your screen'; scr.textContent = '\U0001F5A5';
      var x = document.createElement('button'); x.type = 'button'; x.className = 'live-x'; x.title = 'Close'; x.textContent = '\u2715';
      top.appendChild(flip);
      if (!screen && window.screenViewAvailable && screenViewAvailable()) top.appendChild(scr);
      top.appendChild(x);
      var bottom = document.createElement('div'); bottom.className = 'live-bottom';
      var answer = document.createElement('div'); answer.className = 'live-answer'; answer.setAttribute('aria-live', 'polite');
      var hint = document.createElement('div'); hint.className = 'live-hint';
      hint.textContent = screen ? 'Gink looks at your screen each time you ask \u2014 nothing is sent until then.' : liveHint();
      var form = document.createElement('form'); form.className = 'live-ask';
      var input = document.createElement('input'); input.placeholder = 'Ask, or just press Ask'; input.setAttribute('aria-label', 'Ask');
      var mic = document.createElement('button'); mic.type = 'button'; mic.className = 'live-mic'; mic.title = 'Speak'; mic.textContent = '\U0001F3A4';
      var go = document.createElement('button'); go.type = 'submit'; go.textContent = 'Ask';
      form.appendChild(input);
      var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SR) form.appendChild(mic);
      form.appendChild(go);
      bottom.appendChild(answer); bottom.appendChild(hint); bottom.appendChild(form);
      root.appendChild(video); root.appendChild(flash); root.appendChild(top); root.appendChild(bottom);
      document.body.appendChild(root);
      LIVE = { el: root, stream: stream, facing: facing || 'environment', rec: null, obs: null, waiting: false, hands: !!SR,
               quiet: 0, again: 0, screen: screen, pendingQ: '' };
      function ask(q) {
        if (!LIVE || LIVE.waiting) return;
        var text = (q || '').trim() || (screen ? 'What\u2019s on my screen?' : 'What\u2019s this?');   // nothing typed: Gink works it out
        var data = liveFrame(video); if (!data) { LIVE.pendingQ = text; return; }          // no frame yet: ask when one arrives
        flash.classList.remove('go'); void flash.offsetWidth; flash.classList.add('go');
        LIVE.waiting = true; root.classList.add('busy'); answer.textContent = 'Looking\u2026'; input.value = '';
        setTimeout(function () { if (LIVE && LIVE.waiting) window.liveDone(); }, 90000);
        ginkEmit('live_ask', { data: data, name: 'live-' + new Date().toISOString().slice(11, 19).replace(/:/g, '') + '.jpg', question: text });
      }
      form.onsubmit = function (e) { e.preventDefault(); ask(input.value); };
      LIVE.ask = ask;
      x.onclick = closeLive;
      flip.onclick = function () { openLive(screen ? 'environment' : LIVE && LIVE.facing === 'environment' ? 'user' : 'environment'); };
      scr.onclick = function () { openLive('screen'); };
      function listen() {
        if (!LIVE || LIVE.rec || LIVE.waiting || !SR || document.hidden) return;
        var rec = new SR(), heard = false; rec.interimResults = true; rec.lang = document.documentElement.lang || navigator.language || 'en';
        LIVE.rec = rec; mic.classList.add('on');
        rec.onresult = function (e) { var t = ''; for (var i = 0; i < e.results.length; i++) t += e.results[i][0].transcript; input.value = t;
          heard = heard || !!t.trim();
          if (e.results[e.results.length - 1].isFinal && t.trim()) { LIVE.quiet = 0; rec.stop(); ask(t); } };
        rec.onend = function () {
          if (!LIVE) return;
          LIVE.rec = null; mic.classList.remove('on');
          // hands-free: silence ends a listening turn, so listen again -- for about a minute of quiet, then the mic
          // waits for a tap (no endless listening in an empty room)
          if (LIVE.hands && !LIVE.waiting && !heard) {
            LIVE.quiet++;
            if (LIVE.quiet <= 8) LIVE.again = setTimeout(function () { if (LIVE && LIVE.listen) LIVE.listen(); }, 400);
            else { LIVE.hands = false; input.placeholder = 'Ask, or tap \U0001F3A4 to talk'; }
          }
        };
        rec.onerror = function (e) { if (LIVE && e && (e.error === 'not-allowed' || e.error === 'service-not-allowed' || e.error === 'audio-capture')) LIVE.hands = false; };
        try { rec.start(); } catch (err) { LIVE.rec = null; mic.classList.remove('on'); }
      }
      LIVE.listen = listen;
      mic.onclick = function () {                                       // the mic listens by itself; tap to pause it
        if (LIVE.rec) { LIVE.hands = false; clearTimeout(LIVE.again); LIVE.rec.stop(); return; }
        LIVE.hands = true; LIVE.quiet = 0; input.placeholder = 'Ask, or just press Ask'; listen();
      };
      // the answer arrives in the chat as usual: mirror it over the picture as it streams in
      var feed = document.getElementById('feed');
      LIVE.obs = new MutationObserver(function () {
        if (!LIVE || !LIVE.waiting) return;
        var a = liveLastAnswer(); if (a) answer.textContent = a;
      });
      if (feed) LIVE.obs.observe(feed, { childList: true, subtree: true, characterData: true });
      LIVE.onKey = function (e) { if (e.key === 'Escape') closeLive(); };
      document.addEventListener('keydown', LIVE.onKey);
      LIVE.onVis = function () { if (document.hidden && !screen) closeLive(); };   // left the window: camera and mic go off
      // (screen view keeps going: you're showing Gink another window)
      document.addEventListener('visibilitychange', LIVE.onVis);
      setTimeout(function () { input.focus(); if (LIVE && LIVE.hands) listen(); }, 300);   // hands-free from the start
      if (window.LIVE_PENDING) {                                            // "look at my screen": asked by itself
        var pending = window.LIVE_PENDING; window.LIVE_PENDING = '';
        setTimeout(function () { if (LIVE && LIVE.ask === ask) ask(pending); }, stream ? 900 : 0);
      }
    }).catch(function (err) {
      if (screen) { window.LIVE_PENDING = ''; if (window.lmSay) lmSay('Screen sharing was cancelled.'); return; }
      cameraFallback();                                                // no camera here (or not allowed): take a photo
    });
  }
  function cameraFallback() {                                            // a photo with the system camera instead
    ginkEmit('camera', 'auto');                                          // (the server's photo rules do the rest)
  }
  window.liveDone = function () {                                       // the reply finished (apps + web app call this)
    if (!LIVE) return;
    LIVE.waiting = false; LIVE.el.classList.remove('busy');
    var a = liveLastAnswer(); if (a) LIVE.el.querySelector('.live-answer').textContent = a;
    if (LIVE.hands && LIVE.listen) { LIVE.quiet = 0; LIVE.again = setTimeout(function () { if (LIVE && LIVE.listen) LIVE.listen(); }, 1500); }   // ready for the next one
  };

  // ---- People: like Photos on iPhone. The faces in photos you share with Gink (and photos you add here) are found and
  // grouped ON THIS DEVICE -- a face detector and a face "fingerprint" model (face-api, /app/faces/) run in this page --
  // so you can name people and find their photos. Faces never leave the device: not to Gink's server, not to the AI,
  // not to your other devices (the apps keep People in a file on this device; the web app in this browser).
  // Off until turned on (Settings > Privacy > People); never in a healthcare workspace or a temporary chat; Live camera
  // frames aren't kept. peopleConfigure({base, native}) / peopleLoad(data, on) / peopleSetOn(on) / peopleAuto(dataUrl) /
  // peopleAddPhotos([{name, data}]) / peopleDeleteAll() / openPeople(name). Saves: native -> 'people_save'; web -> IndexedDB.
  var PEOPLE = {on: false, base: '/app/faces/', native: false, configured: false, loading: null, photos: {}, faces: {}, people: {},
                queue: [], busy: false, done: 0, total: 0, found: 0, saveTimer: 0, view: 'all', person: '', error: ''};
  var PEOPLE_MATCH = 0.5;                  // face "fingerprints" closer than this are the same person
  var PEOPLE_MAX = 400;                    // photos kept on this device (the oldest go first)
  var PEOPLE_MIN_FACE = 36;                // smaller faces (pixels) are too blurry to recognise
  function peopleAllowed() { return PEOPLE.on && !CARE_MODE; }
  function peopleId(prefix) { return prefix + Date.now().toString(36) + Math.random().toString(36).slice(2, 7); }
  function peopleHash(s) {                 // the same photo twice is kept once
    var h = 2166136261, n = Math.min(s.length, 60000);
    for (var i = 0; i < n; i += 7) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return 'ph' + (h >>> 0).toString(36) + s.length.toString(36);
  }
  function peopleDist(a, b) { var s = 0; for (var i = 0; i < a.length; i++) { var d = a[i] - b[i]; s += d * d; } return Math.sqrt(s); }
  function peopleData() { return {v: 1, photos: PEOPLE.photos, faces: PEOPLE.faces, people: PEOPLE.people}; }
  function peopleIdb(op, value) {          // the web app: one record in this browser's IndexedDB
    return new Promise(function (resolve) {
      try {
        var req = indexedDB.open('gink-people', 1);
        req.onupgradeneeded = function () { req.result.createObjectStore('kv'); };
        req.onerror = function () { resolve(null); };
        req.onsuccess = function () {
          var db = req.result, tx = db.transaction('kv', op === 'get' ? 'readonly' : 'readwrite'), st = tx.objectStore('kv');
          var r = op === 'get' ? st.get('state') : op === 'put' ? st.put(value, 'state') : st.delete('state');
          r.onsuccess = function () { resolve(op === 'get' ? r.result : true); db.close(); };
          r.onerror = function () { resolve(null); db.close(); };
        };
      } catch (e) { resolve(null); }
    });
  }
  function peopleSave() {
    clearTimeout(PEOPLE.saveTimer);
    PEOPLE.saveTimer = setTimeout(function () {
      if (PEOPLE.native) ginkEmit('people_save', JSON.stringify(peopleData())); else peopleIdb('put', peopleData());
    }, 1200);
  }
  window.peopleConfigure = function (opts) {
    opts = opts || {};
    if (opts.base) PEOPLE.base = String(opts.base).replace(/\\/?$/, '/');
    PEOPLE.native = !!opts.native; PEOPLE.configured = true;
    if (!PEOPLE.native) peopleIdb('get').then(function (d) { if (d) window.peopleLoad(d, PEOPLE.on); });
  };
  window.peopleLoad = function (d, on) {
    d = d || {};
    PEOPLE.photos = d.photos || {}; PEOPLE.faces = d.faces || {}; PEOPLE.people = d.people || {};
    if (on !== undefined) PEOPLE.on = !!on;
    peopleRender();
  };
  window.peopleSetOn = function (on) {
    PEOPLE.on = !!on;
    if (!PEOPLE.on) { PEOPLE.queue = []; }
    else if (PEOPLE_PENDING.list.length && Date.now() - PEOPLE_PENDING.at < 600000) {     // the photos you just shared, too
      var waiting = PEOPLE_PENDING.list; PEOPLE_PENDING.list = [];
      peopleEnqueue(waiting.map(function (d) { return {data: d, from: 'chat'}; }));
    }
    peopleRender();
  };
  // People has no button (0.1.156): it works by itself. While it's off, photos you share wait here (10 minutes,
  // the last 4) and the first time Gink offers ONCE to turn it on (faces are sensitive: never without a yes) --
  // a yes groups those photos straight away, and every photo after. Never temporary chats, Live frames or care.
  var PEOPLE_PENDING = {list: [], at: 0};
  window.peoplePending = function (list) {
    if (PEOPLE.on || CARE_MODE) return;
    PEOPLE_PENDING.list = (list || []).filter(function (d) { return /^data:image\\//.test(String(d || '')); }).slice(-4);
    PEOPLE_PENDING.at = Date.now();
    if (!PEOPLE_PENDING.list.length) return;
    var asked = true;
    try { asked = !!localStorage.getItem('gink-people-offered'); localStorage.setItem('gink-people-offered', '1'); } catch (e) {}
    if (asked) return;
    ginkNotify({id: 'people-offer', system: false, icon: '\U0001F465', title: 'Group the people in your photos?', timeout: 0,
                body: 'Like Photos on iPhone: Gink finds the faces in photos you share and groups them by person \u2014 on this device only. Then ask \u201cshow me photos of Awa\u201d.',
                actions: [{label: 'Not now'}, {label: 'Turn on', primary: true,
                           run: function () { ginkEmit('setting', {key: 'people_on', value: true}); }}]});
  };
  window.peopleDeleteAll = function () {
    PEOPLE.photos = {}; PEOPLE.faces = {}; PEOPLE.people = {}; PEOPLE.queue = []; PEOPLE.view = 'all';
    if (PEOPLE.native) ginkEmit('people_save', JSON.stringify(peopleData())); else peopleIdb('delete');
    peopleRender();
  };

  // the face model: downloaded once (about 8 MB), then it runs here
  function peopleLib() {
    if (PEOPLE.loading) return PEOPLE.loading;
    PEOPLE.loading = new Promise(function (resolve, reject) {
      if (window.faceapi) return resolve(window.faceapi);
      var s = document.createElement('script'); s.src = PEOPLE.base + 'face-api.js'; s.async = true;
      s.onload = function () { window.faceapi ? resolve(window.faceapi) : reject(new Error('no model')); };
      s.onerror = function () { reject(new Error('download')); };
      document.head.appendChild(s);
    }).then(function (fa) {
      var tf = fa.tf, models = PEOPLE.base + 'models';
      var backend = tf && tf.setBackend ? Promise.resolve(tf.setBackend('webgl')).then(function (ok) { return ok ? ok : tf.setBackend('cpu'); },
                                                                                        function () { return tf.setBackend('cpu'); })
                                        : Promise.resolve();
      return backend.then(function () { return tf && tf.ready ? tf.ready() : null; }).then(function () {
        return Promise.all([fa.nets.tinyFaceDetector.loadFromUri(models), fa.nets.faceLandmark68Net.loadFromUri(models),
                            fa.nets.faceRecognitionNet.loadFromUri(models)]);
      }).then(function () { return fa; });
    });
    PEOPLE.loading.catch(function () { PEOPLE.loading = null; });
    return PEOPLE.loading;
  }
  function peopleImage(src) {
    return new Promise(function (resolve, reject) {
      var im = new Image(); im.onload = function () { resolve(im); }; im.onerror = function () { reject(new Error('image')); }; im.src = src;
    });
  }
  function peopleCanvas(im, sx, sy, sw, sh, w, h, q) {
    var c = document.createElement('canvas'); c.width = w; c.height = h;
    c.getContext('2d').drawImage(im, sx, sy, sw, sh, 0, 0, w, h);
    return c.toDataURL('image/jpeg', q);
  }
  function peopleNearest(d) {
    var best = null, bd = 9;
    Object.keys(PEOPLE.people).forEach(function (id) { var x = peopleDist(d, PEOPLE.people[id].c); if (x < bd) { bd = x; best = PEOPLE.people[id]; } });
    return {p: best, d: bd};
  }
  function peopleAssign(face) {            // the nearest person, or someone new
    var n = peopleNearest(face.d), p = n.p && n.d < PEOPLE_MATCH ? n.p : null;
    if (!p) { p = {id: peopleId('p'), name: '', faces: [], c: face.d.slice(), cover: face.id}; PEOPLE.people[p.id] = p; }
    p.faces.push(face.id); face.person = p.id;
    var k = p.faces.length;
    for (var i = 0; i < p.c.length; i++) p.c[i] = Math.round((p.c[i] + (face.d[i] - p.c[i]) / k) * 1e4) / 1e4;
    return p;
  }
  window.peopleAssign = peopleAssign;
  function peopleDropFace(fid) {
    var f = PEOPLE.faces[fid]; if (!f) return;
    var p = PEOPLE.people[f.person];
    if (p) {
      p.faces = p.faces.filter(function (x) { return x !== fid; });
      if (!p.faces.length) delete PEOPLE.people[p.id];
      else { if (p.cover === fid) p.cover = p.faces[0]; peopleRecenter(p); }
    }
    delete PEOPLE.faces[fid];
  }
  function peopleRecenter(p) {
    var c = null;
    p.faces.forEach(function (fid) { var d = PEOPLE.faces[fid] && PEOPLE.faces[fid].d; if (!d) return;
      if (!c) c = d.map(function () { return 0; }); for (var i = 0; i < d.length; i++) c[i] += d[i] / p.faces.length; });
    if (c) p.c = c.map(function (v) { return Math.round(v * 1e4) / 1e4; });
  }
  function peopleDropPhoto(pid) {
    Object.keys(PEOPLE.faces).forEach(function (fid) { if (PEOPLE.faces[fid].photo === pid) peopleDropFace(fid); });
    delete PEOPLE.photos[pid];
  }
  function peopleTrim() {                  // keep the newest PEOPLE_MAX photos
    var ids = Object.keys(PEOPLE.photos).sort(function (a, b) { return PEOPLE.photos[a].added - PEOPLE.photos[b].added; });
    while (ids.length > PEOPLE_MAX) peopleDropPhoto(ids.shift());
  }
  function peopleLook(item) {              // one photo: its faces, grouped
    var pid = peopleHash(item.data);
    if (PEOPLE.photos[pid]) return Promise.resolve(0);
    return Promise.all([peopleLib(), peopleImage(item.data)]).then(function (r) {
      var fa = r[0], im = r[1];
      return fa.detectAllFaces(im, new fa.TinyFaceDetectorOptions({inputSize: 512, scoreThreshold: 0.5}))
        .withFaceLandmarks().withFaceDescriptors().then(function (found) {
          found = (found || []).filter(function (x) { return x.detection.box.width >= PEOPLE_MIN_FACE; });
          if (!found.length || !peopleAllowed()) return 0;
          var W = im.naturalWidth || im.width, H = im.naturalHeight || im.height, k = Math.min(1, 360 / Math.max(W, H));
          PEOPLE.photos[pid] = {id: pid, thumb: peopleCanvas(im, 0, 0, W, H, Math.round(W * k), Math.round(H * k), 0.76),
                                added: Date.now(), from: item.from || 'added'};
          found.forEach(function (x) {
            var b = x.detection.box, side = Math.max(b.width, b.height) * 1.5;
            var sx = Math.max(0, b.x + b.width / 2 - side / 2), sy = Math.max(0, b.y + b.height / 2 - side / 2);
            side = Math.min(side, W - sx, H - sy);
            var face = {id: peopleId('f'), photo: pid, crop: peopleCanvas(im, sx, sy, side, side, 96, 96, 0.82),
                        d: Array.prototype.map.call(x.descriptor, function (v) { return Math.round(v * 1e4) / 1e4; }),
                        score: Math.round(x.detection.score * 100) / 100};
            PEOPLE.faces[face.id] = face; peopleAssign(face);
          });
          peopleTrim(); peopleSave();
          return found.length;
        });
    });
  }
  function peopleNext() {
    if (PEOPLE.busy) return;
    var item = PEOPLE.queue.shift();
    if (!item) { peopleProgress(); return; }
    PEOPLE.busy = true;
    peopleLook(item).then(function (n) { PEOPLE.found += n || 0; }, function (e) {
      PEOPLE.error = e && (e.message === 'download' || e.message === 'no model')
        ? 'The face model couldn’t be downloaded. Check your connection, then add the photos again.' : '';
      if (PEOPLE.error) PEOPLE.queue = [];
    }).then(function () { PEOPLE.busy = false; PEOPLE.done++; peopleProgress(); peopleRender(true); peopleNext(); });
  }
  function peopleEnqueue(items) {
    if (!peopleAllowed() || !items.length) return;
    if (!PEOPLE.queue.length && !PEOPLE.busy) { PEOPLE.done = 0; PEOPLE.total = 0; PEOPLE.found = 0; PEOPLE.error = ''; }
    PEOPLE.queue = PEOPLE.queue.concat(items); PEOPLE.total += items.length;
    peopleProgress(); peopleNext();
  }
  window.peopleAuto = function (data, from) {           // a photo just shared in a chat (never Live frames, never temporary chats)
    if (!peopleAllowed() || !/^data:image\\//.test(String(data || ''))) return;
    peopleEnqueue([{data: data, from: from || 'chat'}]);
  };
  window.peopleAddPhotos = function (list) {
    peopleEnqueue((list || []).filter(function (x) { return x && /^data:image\\//.test(String(x.data || '')); })
                              .map(function (x) { return {data: x.data, from: 'added'}; }));
  };
  function peopleFromFiles(files) {        // the web app: photos chosen here, made smaller first
    var list = Array.prototype.slice.call(files || []).filter(function (f) { return /^image\\//.test(f.type); }).slice(0, 200);
    var out = [];
    return list.reduce(function (chain, f) {
      return chain.then(function () {
        return new Promise(function (resolve) {
          var url = URL.createObjectURL(f);
          peopleImage(url).then(function (im) {
            var W = im.naturalWidth, H = im.naturalHeight, k = Math.min(1, 1280 / Math.max(W, H));
            out.push({name: f.name, data: peopleCanvas(im, 0, 0, W, H, Math.round(W * k), Math.round(H * k), 0.88)});
          }, function () {}).then(function () { URL.revokeObjectURL(url); resolve(); });
        });
      });
    }, Promise.resolve()).then(function () { window.peopleAddPhotos(out); });
  }

  // the People window
  function peopleCount(p) {
    var photos = {}; p.faces.forEach(function (fid) { var f = PEOPLE.faces[fid]; if (f) photos[f.photo] = 1; });
    return Object.keys(photos).length;
  }
  function peopleFind(name) {
    var n = String(name || '').trim().toLowerCase(); if (!n) return null;
    var all = Object.keys(PEOPLE.people).map(function (id) { return PEOPLE.people[id]; }).filter(function (p) { return p.name; });
    return all.filter(function (p) { return p.name.toLowerCase() === n; })[0]
        || all.filter(function (p) { return p.name.toLowerCase().split(' ')[0] === n.split(' ')[0]; })[0] || null;
  }
  function peopleRename(p, name) {
    name = String(name || '').replace(/[<>]/g, '').trim().slice(0, 60);
    var same = name && peopleFind(name);
    if (same && same !== p && same.name.toLowerCase() === name.toLowerCase()) {      // the same name: the same person
      p.faces.forEach(function (fid) { if (PEOPLE.faces[fid]) PEOPLE.faces[fid].person = same.id; });
      same.faces = same.faces.concat(p.faces); peopleRecenter(same); delete PEOPLE.people[p.id];
      PEOPLE.person = same.id;
    } else {
      p.name = name;
    }
    peopleSave(); peopleRender();
  }
  function peopleEl(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; }
  function peopleProgress() {
    var bar = document.querySelector('#people-back .pp-progress'); if (!bar) return;
    var working = PEOPLE.busy || PEOPLE.queue.length;
    if (!working && !PEOPLE.error && !PEOPLE.total) { bar.hidden = true; return; }
    bar.hidden = false; bar.innerHTML = '';
    var t = peopleEl('span', '', PEOPLE.error ? PEOPLE.error : working
      ? 'Looking for faces… ' + Math.min(PEOPLE.done + 1, PEOPLE.total) + ' of ' + PEOPLE.total
      : 'Done: ' + PEOPLE.found + (PEOPLE.found === 1 ? ' face' : ' faces') + ' in ' + PEOPLE.total + (PEOPLE.total === 1 ? ' photo.' : ' photos.'));
    bar.appendChild(t);
    if (working) { var b = peopleEl('div', 'pp-bar'), i = peopleEl('i'); i.style.width = Math.round(100 * PEOPLE.done / Math.max(1, PEOPLE.total)) + '%';
                   b.appendChild(i); bar.appendChild(b); }
  }
  function peopleTile(p) {
    var b = peopleEl('button', 'pp-tile'); b.type = 'button';
    var cover = PEOPLE.faces[p.cover] || PEOPLE.faces[p.faces[0]];
    var im = peopleEl('img', 'pp-face'); im.alt = ''; if (cover) im.src = cover.crop;
    var n = peopleEl('div', 'pp-name' + (p.name ? '' : ' empty'), p.name || 'Add name');
    var c = peopleCount(p), k = peopleEl('div', 'pp-count', c + (c === 1 ? ' photo' : ' photos'));
    b.appendChild(im); b.appendChild(n); b.appendChild(k);
    b.onclick = function () { PEOPLE.view = 'person'; PEOPLE.person = p.id; peopleRender(); };
    return b;
  }
  function peopleRender(quiet) {
    var back = document.getElementById('people-back'); if (!back) return;
    var body = back.querySelector('.pp-body'), title = back.querySelector('.pp-title'), sub = back.querySelector('.pp-sub');
    var bk = back.querySelector('.pp-back'), add = back.querySelector('.pp-add');
    var p = PEOPLE.view === 'person' ? PEOPLE.people[PEOPLE.person] : null;
    if (PEOPLE.view === 'person' && !p) PEOPLE.view = 'all';
    if (quiet && PEOPLE.view === 'person' && document.activeElement && document.activeElement.classList.contains('pp-name-in')) return;
    bk.hidden = !p; add.hidden = !peopleAllowed();
    body.innerHTML = '';
    if (CARE_MODE) {
      title.textContent = 'People'; sub.textContent = '';
      var c = peopleEl('div', 'pp-intro'); c.appendChild(peopleEl('div', 'pp-big', '\U0001F3E5'));
      c.appendChild(peopleEl('h3', '', 'Off in healthcare workspaces'));
      c.appendChild(peopleEl('p', '', 'Patients’ faces must never be grouped or kept, so People is switched off while you’re in a workspace in healthcare mode.'));
      body.appendChild(c); return;
    }
    if (!PEOPLE.on) {
      title.textContent = 'People'; sub.textContent = 'Find people in your photos';
      var intro = peopleEl('div', 'pp-intro'); intro.appendChild(peopleEl('div', 'pp-big', '\U0001F465'));
      intro.appendChild(peopleEl('h3', '', 'Find people in your photos'));
      intro.appendChild(peopleEl('p', '', 'Like Photos on iPhone: Gink finds the faces in photos you share with it and groups them by person, so you can name people and see all their photos.'));
      var ul = peopleEl('ul');
      ['Faces are found and grouped on this device only — never sent to Gink’s server, the AI or your other devices.',
       'Only photos you share in chats or add here. Never Live camera frames, never temporary chats.',
       'Delete everything any time in Settings > Privacy > People.'].forEach(function (t) { ul.appendChild(peopleEl('li', '', t)); });
      intro.appendChild(ul);
      var on = peopleEl('button', 'pp-btn primary', 'Turn on People'); on.type = 'button';
      on.onclick = function () { ginkEmit('setting', {key: 'people_on', value: true}); };
      intro.appendChild(on); body.appendChild(intro); return;
    }
    if (p) {
      title.textContent = p.name || 'Add a name'; sub.textContent = peopleCount(p) + (peopleCount(p) === 1 ? ' photo' : ' photos');
      var top = peopleEl('div', 'pp-person-top'), face = peopleEl('img', 'pp-face'); face.alt = '';
      var cover = PEOPLE.faces[p.cover] || PEOPLE.faces[p.faces[0]]; if (cover) face.src = cover.crop;
      var input = peopleEl('input', 'pp-name-in'); input.placeholder = 'Add a name'; input.value = p.name || ''; input.setAttribute('aria-label', 'Name');
      input.onkeydown = function (e) { if (e.key === 'Enter') { e.preventDefault(); input.blur(); } };
      input.onchange = function () { peopleRename(p, input.value); };
      var forget = peopleEl('button', 'pp-btn danger', 'Forget this person'); forget.type = 'button';
      forget.onclick = function () {
        p.faces.slice().forEach(peopleDropFace);
        Object.keys(PEOPLE.photos).forEach(function (pid) {
          if (!Object.keys(PEOPLE.faces).some(function (fid) { return PEOPLE.faces[fid].photo === pid; })) delete PEOPLE.photos[pid]; });
        PEOPLE.view = 'all'; peopleSave(); peopleRender();
      };
      top.appendChild(face); top.appendChild(input); top.appendChild(forget); body.appendChild(top);
      var grid = peopleEl('div', 'pp-photos');
      p.faces.forEach(function (fid) {
        var f = PEOPLE.faces[fid], ph = f && PEOPLE.photos[f.photo]; if (!ph) return;
        var tile = peopleEl('div', 'pp-photo'), im = peopleEl('img'); im.alt = ''; im.src = ph.thumb; im.loading = 'lazy';
        var not = peopleEl('button', 'pp-not', p.name ? 'Not ' + p.name.split(' ')[0] : 'Not this person'); not.type = 'button';
        not.onclick = function () {               // a wrong face: it becomes someone else
          p.faces = p.faces.filter(function (x) { return x !== fid; }); peopleRecenter(p);
          var q = {id: peopleId('p'), name: '', faces: [fid], c: f.d.slice(), cover: fid}; PEOPLE.people[q.id] = q; f.person = q.id;
          if (!p.faces.length) { delete PEOPLE.people[p.id]; PEOPLE.view = 'all'; } else if (p.cover === fid) p.cover = p.faces[0];
          peopleSave(); peopleRender();
        };
        tile.appendChild(im); tile.appendChild(not); grid.appendChild(tile);
      });
      body.appendChild(grid);
      if (!p.name) setTimeout(function () { try { input.focus(); } catch (e) {} }, 60);
      return;
    }
    title.textContent = 'People'; sub.textContent = 'Grouped on this device · faces never leave it';
    var everyone = Object.keys(PEOPLE.people).map(function (id) { return PEOPLE.people[id]; });
    var named = everyone.filter(function (x) { return x.name; }).sort(function (a, b) { return a.name.localeCompare(b.name); });
    var more = everyone.filter(function (x) { return !x.name && peopleCount(x) >= 2; }).sort(function (a, b) { return peopleCount(b) - peopleCount(a); });
    var once = everyone.length - named.length - more.length;
    if (!named.length && !more.length) {
      var e = peopleEl('div', 'pp-intro'); e.appendChild(peopleEl('div', 'pp-big', '\U0001F5BC️'));
      e.appendChild(peopleEl('h3', '', once ? 'Keep going' : 'No one yet'));
      e.appendChild(peopleEl('p', '', 'Photos you send to Gink appear here, grouped by person, once someone is in two or more of them. You can also add photos.'));
      body.appendChild(e);
    }
    if (named.length) { body.appendChild(peopleEl('div', 'pp-section', 'People'));
      var g1 = peopleEl('div', 'pp-grid'); named.forEach(function (x) { g1.appendChild(peopleTile(x)); }); body.appendChild(g1); }
    if (more.length) { body.appendChild(peopleEl('div', 'pp-section', named.length ? 'Not named yet' : 'Name the people you know'));
      var g2 = peopleEl('div', 'pp-grid'); more.forEach(function (x) { g2.appendChild(peopleTile(x)); }); body.appendChild(g2); }
    if (once) body.appendChild(peopleEl('div', 'pp-note', once + (once === 1 ? ' face seen once isn’t shown.' : ' faces seen once aren’t shown.')));
  }
  window.openPeople = function (name) {
    var back = document.getElementById('people-back');
    if (!back) {
      back = document.createElement('div'); back.id = 'people-back'; back.setAttribute('role', 'dialog'); back.setAttribute('aria-label', 'People');
      back.innerHTML = '<div class="pp-card"><div class="pp-head"><button type="button" class="pp-icon pp-back" aria-label="All people" hidden>‹</button>' +
        '<div class="pp-titles"><div class="pp-title">People</div><div class="pp-sub"></div></div>' +
        '<button type="button" class="pp-btn pp-add">Add photos</button><button type="button" class="pp-icon pp-x" aria-label="Close">✕</button></div>' +
        '<div class="pp-progress" hidden></div><div class="pp-body"></div>' +
        '<input type="file" accept="image/*" multiple hidden class="pp-file"></div>';
      document.body.appendChild(back);
      back.addEventListener('click', function (e) { if (e.target === back) back.remove(); });
      back.querySelector('.pp-x').onclick = function () { back.remove(); };
      back.querySelector('.pp-back').onclick = function () { PEOPLE.view = 'all'; peopleRender(); };
      var file = back.querySelector('.pp-file');
      back.querySelector('.pp-add').onclick = function () { if (PEOPLE.native) ginkEmit('people_pick', true); else file.click(); };
      file.onchange = function () { peopleFromFiles(file.files); file.value = ''; };
      back.addEventListener('keydown', function (e) { if (e.key === 'Escape') back.remove(); });
    }
    var who = name ? peopleFind(name) : null;
    PEOPLE.view = who ? 'person' : 'all'; PEOPLE.person = who ? who.id : '';
    peopleRender(); peopleProgress();
  };
  // "show me photos of Awa": People answers on this device (the request never goes to the AI)
  // "show my people", "who's in my photos", "open people": People opens (on; off -> the intro that turns it on;
  // in a healthcare workspace it says why it's off). "photos of Awa" only for someone already named in People.
  var PEOPLE_OPEN = /^(?:please\\s+)?(?:(?:show|open|see|view)(?:\\s+me)?\\s+(?:all\\s+)?(?:my\\s+|the\\s+)?(?:people|faces)(?:\\s+in\\s+my\\s+(?:photos?|pictures?|pics))?|people|who(?:'s|\u2019s|\\s+is|\\s+are)\\s+in\\s+my\\s+(?:photos?|pictures?|pics))[\\s.?!]*$/i;
  window.peopleIntercept = function (text) {
    if (PEOPLE_OPEN.test(String(text || '').trim())) { window.openPeople(); return true; }
    if (!peopleAllowed()) return false;
    var m = /^(?:please\\s+)?(?:show|find|see|open)(?:\\s+me)?(?:\\s+(?:all|my|the))*\\s+(?:photos?|pictures?|pics?|images?)\\s+(?:of|with)\\s+(.+?)[\\s.?!]*$/i.exec(String(text || '').trim());
    if (!m) return false;
    var who = peopleFind(m[1].replace(/^(?:my|the)\\s+/i, ''));
    if (!who) return false;
    window.openPeople(who.name);
    return true;
  };

  // ---- Lock Gink (Settings > Privacy): covers everything -- chats, Settings, the Live camera -- until the DEVICE says it's
  // you (Face ID, Touch ID, Windows Hello, the phone's face/fingerprint/PIN; in a browser, a passkey). Gink never sees a
  // face or a fingerprint. appLock(true, {label: "Face ID", message}) / appLock(false). The apps and the web app answer
  // 'unlock' and 'lock_signout'.
  var FACE_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2M20 16v2a2 2 0 0 1-2 2h-2M8 20H6a2 2 0 0 1-2-2v-2"/><path d="M9 9.5v1M15 9.5v1M12 9.5v3.5h-1M9.5 15.5c1.4 1.2 3.6 1.2 5 0"/></svg>';
  var PRINT_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M6.5 7.5A7 7 0 0 1 18.8 9.6"/><path d="M5.2 12.4c0-1.1.2-2.1.6-3"/><path d="M8.4 19.6c1-1.7 1.6-3.6 1.6-5.6a2 2 0 0 1 4 0c0 1.1-.1 2.2-.3 3.2"/><path d="M12 14c0 2.9-.8 5.4-2.1 7.4"/><path d="M15.8 20.3c.6-1.8.9-3.8.9-5.8a4.7 4.7 0 0 0-9.4 0c0 1.2-.2 2.3-.5 3.3"/><path d="M19 15.4c.1-.6.1-1.2.1-1.9"/></svg>';
  var KEY_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="15" r="4"/><path d="M10.9 12.1L20 3M16 7l3 3M14 9l2 2"/></svg>';
  function lockIcon(label) { return /face|optic/i.test(label) ? FACE_SVG : /touch|finger/i.test(label) ? PRINT_SVG : KEY_SVG; }
  // The phone's status bar takes the page's colour (Android app: services/android_chrome.py; the web
  // app: the browser's theme-color), light or dark with the theme, dark behind the lock screen.
  var lastBars = '';
  window.syncBars = function () {
    var locked = !!document.getElementById('app-lock');
    var bg = locked ? '#121815' : (getComputedStyle(document.body).getPropertyValue('--bg') || '').trim() || '#FFFFFF';
    var dark = locked || document.body.classList.contains('theme-dark');
    var meta = document.querySelector('meta[name="theme-color"]'); if (meta) meta.setAttribute('content', bg);
    var key = bg + (dark ? ':dark' : ':light');
    if (key === lastBars) return;
    lastBars = key; ginkEmit('bars', {bg: bg, dark: dark});
  };
  document.addEventListener('DOMContentLoaded', function () { setTimeout(syncBars, 0); });
  window.appLock = function (on, opts) {
    opts = opts || {};
    var el = document.getElementById('app-lock');
    if (!on) { if (el) el.remove(); document.documentElement.classList.remove('gink-locked'); syncBars(); return; }
    if (typeof closeLive === 'function') closeLive();                       // the camera never stays on behind the lock
    var pb = document.getElementById('people-back'); if (pb) pb.remove();   // nor People
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    document.documentElement.classList.add('gink-locked');
    if (!el) {
      el = document.createElement('div'); el.id = 'app-lock'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true');
      el.setAttribute('aria-label', 'Gink is locked');
      el.innerHTML = '<div class="lock-card"><div class="lock-mark"><img alt="" src="' + SPIN_URI + '"></div>' +
        '<div class="lock-title">Gink is locked</div><div class="lock-sub" aria-live="polite"></div>' +
        '<button type="button" class="lock-go"></button><button type="button" class="lock-out">Sign out</button></div>';
      document.body.appendChild(el);
      el.querySelector('.lock-go').onclick = function () { ginkEmit('unlock', true); };
      el.querySelector('.lock-out').onclick = function () { ginkEmit('lock_signout', true); };
    }
    var label = opts.label || 'Face ID';
    var go = el.querySelector('.lock-go');
    go.innerHTML = lockIcon(label) + '<span></span>'; go.querySelector('span').textContent = opts.busy ? 'Checking\u2026' : 'Unlock with ' + label;
    go.disabled = !!opts.busy;
    el.querySelector('.lock-sub').textContent = opts.message || ('Use ' + label + ' to open Gink.');
    if (!opts.busy) setTimeout(function () { try { go.focus(); } catch (e) {} }, 30);
    syncBars();
  };
  window.isAppLocked = function () { return !!document.getElementById('app-lock'); };
  document.addEventListener('keydown', function (e) {           // locked: keys reach only the lock screen
    var el = document.getElementById('app-lock');
    if (el && !el.contains(e.target)) { e.preventDefault(); e.stopPropagation(); }
  }, true);
  // away and back: the apps also watch the window; this catches phones and browsers (the page is hidden in between)
  document.addEventListener('visibilitychange', function () { ginkEmit('page_visibility', document.hidden ? 'hidden' : 'visible'); });

  // ---- Notifications, Apple style: frosted cards that slide in at the top right (top centre on phones), stack,
  // and leave by themselves. ginkNotify({id, title, body, icon, kind, actions: [{label, emit, value, url, primary}],
  // timeout}) -- the same id replaces its card; timeout 0 = stays until closed or dismissed (ginkDismiss(id)).
  var NOTIFY_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#A8F03C" stroke-width="1.7" stroke-linecap="round"><path d="M12 3v18M4.2 7.5l15.6 9M19.8 7.5l-15.6 9"/><path d="M12 6.5l-2-2M12 6.5l2-2M12 17.5l-2 2M12 17.5l2 2"/></svg>';
  function notifyHost() {
    var h = document.getElementById('notify-host');
    if (!h) { h = document.createElement('div'); h.id = 'notify-host'; h.setAttribute('aria-live', 'polite'); document.body.appendChild(h); }
    return h;
  }
  function ginkDismiss(id) {
    var n = id && document.querySelector('.gnote[data-id="' + id + '"]');
    if (!n || n.classList.contains('out')) return;
    n.classList.add('out'); setTimeout(function () { if (n.parentNode) n.parentNode.removeChild(n); }, 320);
  }
  function ginkNotify(o) {
    o = o || {}; var host = notifyHost(), id = o.id || ('n' + Date.now() + Math.random().toString(36).slice(2, 6));
    var old = host.querySelector('.gnote[data-id="' + id + '"]'); if (old) old.parentNode.removeChild(old);
    var n = document.createElement('div'); n.className = 'gnote' + (o.kind ? ' ' + o.kind : ''); n.setAttribute('data-id', id);
    n.setAttribute('role', o.kind === 'alert' ? 'alert' : 'status');
    var ic = document.createElement('div'); ic.className = 'gn-ic'; ic.innerHTML = o.icon ? '' : NOTIFY_ICON; if (o.icon) ic.textContent = o.icon;
    var main = document.createElement('div'); main.className = 'gn-main';
    var top = document.createElement('div'); top.className = 'gn-top';
    var app = document.createElement('span'); app.textContent = 'GINK'; var when = document.createElement('span'); when.textContent = 'now';
    top.appendChild(app); top.appendChild(when);
    var t = document.createElement('div'); t.className = 'gn-title'; t.textContent = o.title || 'Gink';
    var b = document.createElement('div'); b.className = 'gn-body'; b.textContent = o.body || '';
    main.appendChild(top); main.appendChild(t); if (o.body) main.appendChild(b);
    (o.links || []).forEach(function (l) { var a = document.createElement('a'); a.href = l.url; a.textContent = l.label; a.className = 'gn-link'; main.appendChild(a); });
    if (o.actions && o.actions.length) {
      var row = document.createElement('div'); row.className = 'gn-acts';
      o.actions.forEach(function (a) {
        var btn = document.createElement('button'); btn.type = 'button'; btn.textContent = a.label; if (a.primary) btn.className = 'primary';
        btn.onclick = function (e) { e.stopPropagation(); if (a.emit) ginkEmit(a.emit, a.value === undefined ? null : a.value);
          if (a.url) ginkEmit('open_url', a.url); if (typeof a.run === 'function') a.run(); ginkDismiss(id); };
        row.appendChild(btn);
      });
      main.appendChild(row);
    }
    var x = document.createElement('button'); x.type = 'button'; x.className = 'gn-x'; x.setAttribute('aria-label', 'Close'); x.textContent = '\u00d7';
    x.onclick = function (e) { e.stopPropagation(); ginkDismiss(id); if (o.onclose) o.onclose(); };
    n.appendChild(x); n.appendChild(ic); n.appendChild(main);
    host.insertBefore(n, host.firstChild);
    while (host.children.length > 4) host.removeChild(host.lastChild);           // at most four at once, like a stack
    var ms = o.timeout === undefined ? 6000 : o.timeout;
    if (ms > 0) { var timer = setTimeout(function () { ginkDismiss(id); }, ms);
      n.addEventListener('mouseenter', function () { clearTimeout(timer); });
      n.addEventListener('mouseleave', function () { timer = setTimeout(function () { ginkDismiss(id); }, 2500); }); }
    var x0 = null;                                                             // swipe it away (touch)
    n.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; }, {passive: true});
    n.addEventListener('touchmove', function (e) { if (x0 !== null) n.style.transform = 'translateX(' + Math.max(0, e.touches[0].clientX - x0) + 'px)'; }, {passive: true});
    n.addEventListener('touchend', function (e) { var dx = (e.changedTouches[0].clientX - (x0 || 0)); x0 = null;
      if (dx > 80) ginkDismiss(id); else n.style.transform = ''; });
    // on the device too when Gink isn't in front (0.1.162): the web app's browser notifications. (The apps post
    // their own from Python: services/system_notify.py.) system: false = a quick confirmation, the page only.
    if (o.system !== false && typeof window.ginkSystemNotify === 'function') { try { window.ginkSystemNotify(o); } catch (e) {} }
    return id;
  }
  // Gink's status (GET /status): a notification while something on Gink's side isn't working; gone when it's fixed
  function statusBar(status, message) {
    if (!message || status === 'ok') { ginkDismiss('status'); return; }
    var m = /^Gink is having trouble with (.+?) right now[.] (.*)$/.exec(message);    // the title already says "trouble"
    var body = m ? m[1].charAt(0).toUpperCase() + m[1].slice(1) + ' isn\u2019t working right now. ' + m[2] : message;
    ginkNotify({id: 'status', kind: status === 'notice' ? '' : 'warn', title: status === 'notice' ? 'Notice' : 'Gink is having trouble',
                body: body, icon: status === 'notice' ? '\u2139\ufe0f' : '\u26a0\ufe0f', timeout: 0});
  }
  // "We've updated our privacy policy and terms" -- once per change (the date from the server's /info)
  function policyNotice(date, privacy, terms) {
    ginkNotify({id: 'policy', title: 'Privacy policy and terms updated',
      body: 'What Gink does with your data, in plain words (' + new Date(date + 'T12:00:00Z').toLocaleDateString() + ').',
      timeout: 0, actions: [{label: 'Read', url: privacy, emit: 'policy_seen', value: date}, {label: 'OK', primary: true, emit: 'policy_seen', value: date}]});
  }
  function setModels(models, currentId) {
    MM.available = (models || []).map(function (m) { MM.names[m.id] = m.name; return m.id; });
    MM.current = currentId || MM.current;
    document.getElementById('model-name').innerText = mmInfo(MM.current).name;
    document.getElementById('model-tier').innerText = '';
    drawModelMenu();
  }
  window.setEffort = function (e) { if (e) { MM.effort = e; drawModelMenu(); } };
  function mmButton(attrs, html) {
    var b = document.createElement('button'); Object.keys(attrs).forEach(function (k) { b.setAttribute(k, attrs[k]); });
    b.innerHTML = html; return b;
  }
  function esc(t) { var d = document.createElement('div'); d.textContent = t; return d.innerHTML; }
  function drawModelMenu() {
    var menu = document.getElementById('model-menu'); if (!menu) return; menu.innerHTML = '';
    if (MM.view === 'effort') {
      menu.appendChild(mmButton({'data-back': '1', 'class': 'mm-back'}, '\u2039&nbsp; Effort'));
      var note = document.createElement('div'); note.className = 'mm-note';
      note.textContent = 'Higher effort means more thorough responses, but takes longer and uses your limits faster.'; menu.appendChild(note);
      EFFORTS.forEach(function (e) {
        menu.appendChild(mmButton({'data-effort': e[0], 'class': e[0] === MM.effort ? 'sel' : ''},
          '<span>' + esc(e[1]) + '</span>' + (e[2] ? '<span class="mm-badge' + (e[0] === 'max' ? ' warn' : '') + '">' + esc(e[2]) + '</span>' : '')));
      });
      return;
    }
    if (MM.view === 'models') {
      menu.appendChild(mmButton({'data-back': '1', 'class': 'mm-back'}, '\u2039&nbsp; More models'));
      var own = MM.available.filter(function (id) { return /^gink-/.test(id) && id !== 'gink-search' && !GINK_MODELS.some(function (m) { return m.id === id; }); })
        .map(function (id) { return {id: id, name: MM.names[id] || 'Gink', desc: 'Gink\u2019s own model'}; });   // tools/gink_model
      GINK_MODELS.filter(function (m) { return !MM.available.length || MM.available.indexOf(m.id) >= 0; }).concat(own).forEach(function (m) {
        menu.appendChild(mmButton({'data-id': m.id, 'class': 'mm-model' + (m.id === MM.current ? ' sel' : '')},
          '<span class="mm-col"><span class="mm-name">' + esc(m.name) + '</span><span class="mm-desc">' + esc(m.desc) + '</span></span>'));
      });
      return;
    }
    var cur = mmInfo(MM.current);
    menu.appendChild(mmButton({'data-view': 'models', 'class': 'mm-model sel'},
      '<span class="mm-col"><span class="mm-name">' + esc(cur.name) + '</span><span class="mm-desc">' + esc(cur.desc) + '</span></span>'));
    var effortName = (EFFORTS.filter(function (e) { return e[0] === MM.effort; })[0] || EFFORTS[1])[1];
    menu.appendChild(mmButton({'data-view': 'effort'}, '<span>Effort</span><span class="hint">' + esc(effortName) + '&nbsp; \u203a</span>'));
    menu.appendChild(mmButton({'data-view': 'models'}, '<span>More models</span><span class="hint">\u203a</span>'));
  }

  var LOADING_CHAT = false;                   // while a whole chat is drawn at once, no jumping
  function scrollDown() { if (!LOADING_CHAT) ginkScrollEnd(false); }
  // Opening a chat: glide smoothly to its end, and the snowflake spins once as it lands
  window.glideToEnd = function () {
    var still = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    var logos = document.querySelectorAll('.msg-logo'), logo = logos[logos.length - 1];
    if (logo && !still) { logo.classList.remove('arriving', 'landing'); void logo.offsetWidth; logo.classList.add('landing'); }
    if (still) { ginkScrollEnd(false); return; }
    scroller().scrollTop = 0;
    requestAnimationFrame(function () { ginkScrollEnd(true); });
  };
  // The whole chat in one go: no "Thinking..." placeholders flickering while it loads
  window.loadChat = function (items) {
    LOADING_CHAT = true;
    try {
      (items || []).forEach(function (m) {
        if (m.role === 'user') addUserMessage(m.text, []);
        else { addAssistantMessage(m.id, ''); finalizeMessage(m.id, m.html); }
      });
    } finally { LOADING_CHAT = false; }
    glideToEnd();
  };

  function hideWelcome() {
    var w = document.getElementById('welcome');
    if (w) { w.remove(); }
    if (document.body.classList.contains('home')) {
      document.body.classList.remove('home');   // composer glides to the bottom
      setTimeout(scrollDown, 560);
    }
  }

  function clearFeed() {
    document.getElementById('feed').innerHTML = '';
    userIdx = 0;
    lastLogoMsgId = null;
  }

  // ---- temporary chat (the host keeps it out of history and sync)
  window.setTemporary = function (on) {
    document.body.classList.toggle('temporary', !!on);
    var b = document.getElementById('temp-btn'); if (b) b.setAttribute('aria-pressed', on ? 'true' : 'false');
  };
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('#temp-btn'); if (!b) return;
    var on = !document.body.classList.contains('temporary');
    setTemporary(on); ginkEmit('temporary', on);
  });

  function showWelcome(title, subtitle) {
    var feed = document.getElementById('feed');
    var div = document.createElement('div');
    div.id = 'welcome';
    div.innerHTML = '<h1></h1><p></p>';
    div.querySelector('h1').setAttribute('data-text', title);
    div.querySelector('p').textContent = subtitle;
    feed.appendChild(div);
    renderGreeting();
    document.body.classList.add('home');      // composer returns to the centre
    exIdx = 0; exTimer = setTimeout(cyclePlaceholder, 3500);
    if (lastToday) setToday(lastToday);
  }

  // ---- user message + its actions (Retry / Edit / Copy / More) ----
  var userIdx = 0;
  var UA_ICONS = {
    retry: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></svg>', edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>', copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>', check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    dots: '<svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/></svg>', branch: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="8" r="2"/><path d="M6 7v10M18 10c0 4-6 3-11.5 7.5"/></svg>', speak: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/></svg>', web: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.7 2.5 14.3 0 17M12 3.5c-2.5 2.7-2.5 14.3 0 17"/></svg>', quote: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M7 7h4v4c0 3-1.5 5-4 6M15 7h4v4c0 3-1.5 5-4 6"/></svg>'
  };
  function copyText(text, done) {
    function fallback() {
      var ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch (e) {} ta.remove(); done && done();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
    else fallback();
  }
  function addUserMessage(text, atts) {
    hideWelcome();
    var feed = document.getElementById('feed');
    var row = document.createElement('div');
    row.className = 'row user';
    row.setAttribute('data-idx', userIdx++);
    if (atts && atts.length) {
      var at = document.createElement('div'); at.className = 'uatts';
      atts.forEach(function (a) { at.appendChild(attChip(a, false)); });
      row.appendChild(at);
    }
    var bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.innerText = text;
    if (text) row.appendChild(bubble);
    var bar = document.createElement('div');
    bar.className = 'uactions';
    bar.innerHTML =
      '<button class="ua" data-ua="retry" title="Retry">' + UA_ICONS.retry + '</button>' +
      '<button class="ua" data-ua="edit" title="Edit">' + UA_ICONS.edit + '</button>' +
      '<button class="ua" data-ua="copy" title="Copy">' + UA_ICONS.copy + '</button>' +
      '<button class="ua" data-ua="more" title="More">' + UA_ICONS.dots + '</button>' +
      '<div class="menu hidden">' +
        '<button data-ua="branch">' + UA_ICONS.branch + ' Branch to new chat</button>' +
        '<button data-ua="speak">' + UA_ICONS.speak + ' Read aloud</button>' +
        '<button data-ua="web">' + UA_ICONS.web + ' Search the web for this</button>' +
        '<button data-ua="quote">' + UA_ICONS.quote + ' Quote in reply</button>' +
      '</div>';
    row.appendChild(bar);
    feed.appendChild(row);
    if (window.closeQuestionCards) closeQuestionCards(text);      // an earlier question card is answered now
    scrollDown();
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('.uactions button');
    if (!b) return;
    e.stopPropagation();
    var row = b.closest('.row.user'), bub = row.querySelector('.bubble'), text = bub ? bub.innerText : '';
    var idx = parseInt(row.getAttribute('data-idx'), 10), what = b.getAttribute('data-ua');
    var bar = row.querySelector('.uactions'), menu = bar.querySelector('.menu');
    if (what !== 'more') { closeMenus(); bar.classList.remove('open'); }
    if (what === 'more') {
      var was = menu.classList.contains('hidden'); closeMenus();
      if (was) { menu.classList.remove('hidden'); bar.classList.add('open'); } else bar.classList.remove('open');
    } else if (what === 'copy') {
      copyText(text, function () { b.innerHTML = UA_ICONS.check; b.classList.add('done');
        setTimeout(function () { b.innerHTML = UA_ICONS.copy; b.classList.remove('done'); }, 1500); });
    } else if (what === 'edit') {
      var t = cin(); t.value = text; autoGrow(); refreshSend(); t.focus();
      try { t.setSelectionRange(text.length, text.length); } catch (err) {}
    } else if (what === 'quote') {
      var q = cin(); q.value = '> ' + text.split('\\n').join('\\n> ') + '\\n\\n' + q.value; autoGrow(); refreshSend(); q.focus();
    } else if (what === 'retry') { ginkEmit('send', text);
    } else if (what === 'branch') { ginkEmit('branch', idx);
    } else if (what === 'speak') { ginkEmit('read_aloud', text);
    } else if (what === 'web') { ginkEmit('send', 'Search the web for: ' + text); }
  }, true);

  function addAssistantMessage(id, label) {
    hideWelcome();
    retireLogo();                          // the previous reply's logo fades away now
    var feed = document.getElementById('feed');
    var row = document.createElement('div');
    row.className = 'row';
    var el = document.createElement('div');
    el.className = 'assistant-text';
    el.id = id;
    // Branded spinner shown while waiting for the first token (or the
    // whole reply, for a non-streamed skill answer) -- centered in its
    // own row rather than sitting inline at the text's start.
    // appendToken() and finalizeMessage() both clear it the moment real
    // content actually arrives, so it never lingers alongside real text.
    el.innerHTML = '<div class="stream"></div><div class="gink-spin"><img class="gink-spinner" src="' + SPIN_URI + '" alt=""><span class="spin-label"></span></div>';
    el.querySelector('.spin-label').textContent = label || 'Thinking…';
    row.appendChild(el);
    feed.appendChild(row);
    startSpinClock(id);
    if (label && !GENERIC.test(label)) setSpinLabel(id, label);   // a specific first step joins the timeline
    scrollDown();
  }

  // Fallback plain-text streaming (used only if rendering isn't available).
  function appendToken(id, token) {
    var el = document.getElementById(id);
    if (!el) return;
    var st = el.querySelector('.stream');
    if (st) { st.innerText += token; } else { el.innerText += token; }
    scrollDown();
  }
  // Live-rendered streaming: Python sends the reply-so-far already
  // turned into HTML (so **bold** shows as bold, never as asterisks).
  // The spinning logo stays right after the newest text, so it moves
  // down the page as Gink writes.
  function renderStream(id, html) {
    var el = document.getElementById(id);
    if (!el) return;
    var st = el.querySelector('.stream');
    if (!st) return;
    el.classList.add('rendered');
    var nearBottom = atEnd(160);
    st.innerHTML = html;
    wrapTables(st);
    if (html) noteWriting(id);
    if (nearBottom) scrollDown();
  }

  function copyDocBlock(button) {
    // innerText of the already-rendered body, not the stored raw
    // markdown -- the browser has already turned **bold** into real
    // bold, # into a heading, etc., so reading the rendered text back
    // out gives clean prose with no literal markdown characters left in
    // it, rather than copying the source syntax verbatim.
    var body = button.closest('.doc-block').querySelector('.doc-block-body');
    var text = body.innerText;
    navigator.clipboard.writeText(text).then(function() {
      var original = button.innerText;
      button.innerText = 'Copied!';
      setTimeout(function() { button.innerText = original; }, 1500);
    });
  }

  function downloadDocBlock(button) {
    var body = button.closest('.doc-block').querySelector('.doc-block-body');
    var text = body.innerText;
    var blob = new Blob([text], { type: 'text/plain' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'gink-document.txt';
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function copyCodeBlock(button) {
    var block = button.closest('.code-block');
    var codeEl = block.querySelector('code') || block.querySelector('.code-block-body');
    navigator.clipboard.writeText(codeEl.innerText).then(function() {
      var original = button.innerText;
      button.innerText = 'Copied!';
      setTimeout(function() { button.innerText = original; }, 1500);
    });
  }

  function downloadCodeBlock(button) {
    var block = button.closest('.code-block');
    var codeEl = block.querySelector('code') || block.querySelector('.code-block-body');
    var label = block.querySelector('.code-block-label').innerText;
    // Use the detected filename directly when there is one (it contains
    // a dot, e.g. "tic_tac_toe.py"); fall back to a generic name when
    // the label is just the language (no filename was found in the code).
    var filename = label.indexOf('.') !== -1 ? label : 'gink-code.txt';
    var blob = new Blob([codeEl.innerText], { type: 'text/plain' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // While an answer streams in, its map and question blocks (JSON) stay out of sight: they become the map and the
  // question card when the answer is done (finalizeMessage).
  function streamView(text) {
    return String(text == null ? '' : text).replace(/(^|\\n)```(?:map|ask|schedule)[^\\n]*(?:\\n[\\s\\S]*?(?:\\n```[ \\t]*(?=\\n|$)|$)|$)/g,
                                                    function (m, pre) { return pre; })
      // an artifact being written: its name, not its code ("Making \u201cPomodoro timer\u201d\u2026")
      .replace(/(^|\\n)```[\\w+#.\\-]*[ \\t]+title=["']([^"'\\n]{1,120})["'][^\\n]*(?:\\n[\\s\\S]*?(\\n```[ \\t]*(?=\\n|$))|[\\s\\S]*$)/g,
               function (m, pre, title, end) { return pre + (end ? '\\u2713 \\u201c' + title + '\\u201d is ready' : '\\u270e Making \\u201c' + title + '\\u201d\\u2026'); })
      .replace(/\\s+$/, '');
  }
  window.streamView = streamView;
  function setPlainText(id, text) {
    var el = document.getElementById(id);
    if (el) { el.innerText = streamView(text); scrollDown(); }
  }

  function finalizeMessage(id, renderedHtml) {
    var el = document.getElementById(id);
    if (!el) { return; }
    el.classList.add('rendered');
    el.innerHTML = renderedHtml;          // replaces the stream + spinner

    // Move the logo mark here: remove it from wherever it was (the
    // previous reply), then add it to this one -- disappearing from the
    // old spot and reappearing at the end of the newest reply, on a loop
    // for every response rather than staying fixed on the first one.
    if (lastLogoMsgId) {
      var prevEl = document.getElementById(lastLogoMsgId);
      var prevLogo = prevEl ? prevEl.querySelector('.msg-logo') : null;
      if (prevLogo) { prevLogo.remove(); }
    }
    stopSpinClock(id);
    wrapTables(el);
    upgradeVideoLinks(el);
    upgradeFileLinks(el);
    if (window.upgradeQuestionCards) upgradeQuestionCards(el);     // before code blocks: ```ask``` becomes a card
    if (window.upgradeSchedules) upgradeSchedules(el, !LOADING_CHAT);  // ```schedule``` becomes a task card (0.1.161)
    if (window.upgradeMaps) upgradeMaps(el);                       // ```map``` becomes a live map, by itself
    if (window.upgradeArtifacts) upgradeArtifacts(el);             // finished things become artifact cards (0.1.161)
    enhanceCodeBlocks(el);
    if (!LOADING_CHAT && window.autoOpenCode) autoOpenCode(el);        // long code in a new answer: the viewer
    addGinkActions(el, id);
    if (window.upgradeSources) upgradeSources(el);                     // the Sources list -> a button in that row
    if (!LOADING_CHAT && window.liveDone) setTimeout(window.liveDone, 0);  // Live camera: show the finished answer
    var logoImg = document.createElement('img');
    logoImg.className = 'msg-logo arriving';
    logoImg.src = SPIN_URI;
    logoImg.alt = 'Gink';
    el.appendChild(logoImg);
    lastLogoMsgId = id;
    // Copy/Download buttons on code blocks are now generated directly
    // in the HTML by services/markdown_render.py (header bar with a
    // detected filename or the language as a label), with
    // copyCodeBlock()/downloadCodeBlock() wired the same way as the
    // document block's -- no per-pre JS loop needed here anymore.
    scrollDown();
  }
</script>
</body>
</html>
"""


def _close_open_markdown(text: str) -> str:
    """Mid-stream text often ends inside an unfinished **bold** or *italic*
    or `code` span, which would show its raw asterisks/backticks until the
    closing marker arrives. Trim the dangling opener so only complete
    formatting is shown; the full text renders properly at the end."""
    import re as _re
    fence_count = text.count("```")
    if fence_count % 2 == 1:
        return text + "\n```"              # close an open code block
    tail_start = text.rfind("\n") + 1
    line = text[tail_start:]
    for marker in ("**", "__", "`", "*", "_"):
        stripped = line.replace("**", "\0\0") if marker in ("*",) else line
        count = (line.count(marker) if marker not in ("*",) else stripped.count("*"))
        if count % 2 == 1:
            pos = line.rfind(marker)
            # leave list bullets ("* item") alone
            if marker == "*" and _re.match(r"^\s*\*\s", line) and pos == line.find("*"):
                continue
            line = line[:pos] + line[pos + len(marker):]
    return text[:tail_start] + line


def _build_page_html_base(welcome_title: str, welcome_subtitle: str) -> str:
    html = _PAGE_TEMPLATE.replace("__PYGMENTS_CSS__", PYGMENTS_CSS)
    html = html.replace("__WELCOME_TITLE__", welcome_title)
    html = html.replace("__WELCOME_SUBTITLE__", welcome_subtitle)
    html = html.replace("__SPIN_DATA_URI__", LOGO_SPINNER_DATA_URI)
    html = html.replace("__LOGO_DATA_URI__", LOGO_DATA_URI)
    html = html.replace("__BRAND_TILE_URI__", BRAND_TILE_DATA_URI)
    html = html.replace("__THEME_VARS__", css_vars())
    return html



class WebChatFeed:
    """Thin async wrapper around a toga.WebView running the chat-feed
    page. Call methods on this instead of touching the WebView directly."""

    def __init__(self, welcome_title: str = "Gink Ai Assistant", welcome_subtitle: str = "Ready to help with your workflows.",
                 start_locked: bool = False):
        self.web_view = toga.WebView(style=Pack(flex=1))
        self.web_view.set_content("https://gink.local/", _build_page_html(welcome_title, welcome_subtitle, start_locked))

    async def _js(self, script: str):
        try:
            await self.web_view.evaluate_javascript(script)
        except Exception:
            pass  # see module docstring -- Android/Windows swallow JS errors anyway

    async def clear(self):
        await self._js("clearFeed()")

    # -- composer bridge -------------------------------------------------

    async def poll(self) -> list:
        """Collects what the user did in the HTML composer since the last
        call: [{"type": "send"|"dictate"|"voice_toggle"|"menu"|"model",
        "value": ...}]. Never raises; returns [] if the page isn't ready."""
        if getattr(self, "_events", None) is None:
            from .page_events import EventQueue
            self._events = EventQueue()
        return await self._events.take(self.web_view)        # each event exactly once (ui/page_events.py)

    async def set_busy(self, busy: bool):
        await self._js(f"setComposerBusy({'true' if busy else 'false'})")

    async def set_voice_on(self, on: bool):
        await self._js(f"setVoiceOn({'true' if on else 'false'})")

    async def set_speaking(self, on: bool):
        await self._js(f"setSpeaking({'true' if on else 'false'})")

    async def set_dictating(self, on: bool):
        await self._js(f"setDictating({'true' if on else 'false'})")

    async def show_update(self, version: str):
        await self._js(f"showUpdate({json.dumps(version)})")
        self._device_too(f"Gink {str(version).lstrip('v')} is available", "Download the new version when you\u2019re ready.",
                         "update")

    async def hide_update(self):
        await self._js("hideUpdate()")

    async def set_status(self, text: str):
        await self._js(f"setStatus({json.dumps(text or '')})")

    async def insert_text(self, text: str):
        await self._js(f"insertComposerText({json.dumps(text)})")

    async def render_stream(self, message_id: str, raw_markdown: str):
        """Shows the reply-so-far as formatted text (bold, lists, code)
        instead of raw markdown, with the spinner after it."""
        rendered = render_markdown_body(_close_open_markdown(raw_markdown))
        await self._js(f"renderStream({json.dumps(message_id)}, {json.dumps(rendered)})")

    async def set_attachments(self, chips: list):
        await self._js(f"setAttachments({json.dumps(chips)})")

    async def add_user_message_with(self, text: str, chips: list):
        await self._js(f"addUserMessage({json.dumps(text)}, {json.dumps(chips)})")

    async def set_sync_status(self, text: str):
        await self._js(f"setSyncStatus({json.dumps(text or '')})")

    async def set_settings_state(self, state: dict):
        await self._js(f"setSettingsState({json.dumps(state)})")

    async def open_settings(self, panel: str = "general"):
        await self._js(f"openSettings({json.dumps(panel)})")

    async def close_settings(self):
        await self._js("window.closeSettings && closeSettings()")

    async def show_whats_new(self, version: str, sections: list):
        await self._js(f"showWhatsNew({json.dumps(version)}, {json.dumps(sections)})")

    async def cv_published(self, url: str = "", error: str = ""):
        await self._js(f"cvPublished({json.dumps(url or None)}, {json.dumps(error)})")

    async def set_tasks(self, tasks: list):
        """Scheduled tasks as they are now: the chat's task cards show them (ui/chat_extras.py)."""
        await self._js(f"if (window.setTasks) setTasks({json.dumps(tasks or [])})")

    async def task_result(self, source: str, task: dict = None, error: str = ""):
        """The answer to a card's task_create: the task made, or why not."""
        await self._js(f"if (window.taskResult) taskResult({json.dumps(source)}, {json.dumps(task)}, {json.dumps(error)})")

    async def set_effort(self, effort: str):
        await self._js(f"setEffort({json.dumps(effort or 'medium')})")

    async def show_recalled(self, items: list):
        await self._js(f"showRecalled({json.dumps([{'text': i.get('text', '')} for i in items])})")

    async def set_prompts(self, prompts: list):
        await self._js(f"setPrompts({json.dumps(prompts)})")

    async def set_temporary(self, on: bool):
        await self._js(f"setTemporary({json.dumps(bool(on))})")

    async def show_share_link(self, url: str, title: str = ""):
        await self._js(f"showShareLink({json.dumps(url)}, {json.dumps(title)})")

    async def settings_toast(self, text: str, kind: str = "ok"):
        await self._js(f"settingsToast({json.dumps(text)}, {json.dumps(kind)})")

    async def set_appearance(self, theme: str, font: str, motion: str):
        await self._js(f"setAppearance({json.dumps(theme)}, {json.dumps(font)}, {json.dumps(motion)})")

    # -- voice conversation (ui/voice_ui.py) + keyboard prefs ----------------
    async def set_voice_config(self, cfg: dict):
        await self._js(f"setVoiceConfig({json.dumps(cfg)})")

    async def voice_state(self, state: str, text: str = ""):
        await self._js(f"voiceUiState({json.dumps(state)}, {json.dumps(text)})")

    async def voice_caption(self, you=None, gink=None):
        await self._js(f"voiceUiCaption({json.dumps(you)}, {json.dumps(gink)})")

    async def voice_level(self, level: float):
        await self._js(f"voiceUiLevel({float(level):.2f})")

    async def set_keyboard_prefs(self, prefs: dict):
        await self._js(f"setKeyboardPrefs({json.dumps(prefs)})")

    async def wake_glow(self, state: str):
        """'listening' | 'thinking' | 'speaking' | 'off' (ui/wake_ui.py)."""
        await self._js(f"wakeGlow({json.dumps(state)})")

    async def ask_birth_year(self, message: str = "", blocked: bool = False):
        """The one-time birth-year question (ui/settings_page.py askBirthYear)."""
        await self._js(f"askBirthYear({json.dumps(message or '')}, {'true' if blocked else 'false'})")

    async def birth_year_done(self):
        await self._js("birthYearDone()")

    async def wake_chip(self, state: str, label: str = "", detail: str = ""):
        """The "Hey Gink" status chip in the composer (ui/wake_ui.py, services/wake_status.py)."""
        await self._js(f"wakeChip({json.dumps(state)}, {json.dumps(label or '')}, {json.dumps(detail or '')})")

    async def wake_caption(self, text: str):
        await self._js(f"wakeCaption({json.dumps(text or '')})")

    async def set_composer_text(self, text: str):
        await self._js(f"setComposerText({json.dumps(text or '')})")

    async def set_file_thumb(self, name: str, data_url: str):
        await self._js(f"setFileThumb({json.dumps(name)}, {json.dumps(data_url)})")

    async def set_sessions(self, sessions: list):
        """Recents list: [{"id", "title", "current"}], newest first."""
        await self._js(f"setSessions({json.dumps(sessions)})")

    async def set_user(self, name: str, photo: str = "", call_name: str = ""):
        await self._js(f"setUser({json.dumps(name)}, {json.dumps(photo or '')}, {json.dumps(call_name or '')})")

    # -- People (faces grouped on this device; the page does the work, the app keeps the file) --------
    async def people_configure(self, base: str):
        await self._js(f"window.peopleConfigure && peopleConfigure({json.dumps({'base': base, 'native': True})})")

    async def people_load(self, data: dict, on: bool):
        await self._js(f"window.peopleLoad && peopleLoad({json.dumps(data or {})}, {'true' if on else 'false'})")

    async def people_set_on(self, on: bool):
        await self._js(f"window.peopleSetOn && peopleSetOn({'true' if on else 'false'})")

    async def set_server(self, base: str):
        """Gink's server address: the sources' logos come from it (GET /icon/{host}), never straight from the sites."""
        await self._js(f"window.GINK_ICONS = {json.dumps(str(base or '').rstrip('/'))}")

    async def people_auto(self, data_url: str):
        await self._js(f"window.peopleAuto && peopleAuto({json.dumps(data_url)}, 'chat')")

    async def open_people(self):
        await self._js("window.closeSettings && closeSettings(); window.openPeople && openPeople()")

    async def people_pending(self, data_urls: list):
        """People is off: these photos wait (the page offers once to turn it on; a yes groups them)."""
        await self._js(f"window.peoplePending && peoplePending({json.dumps(list(data_urls)[-4:])})")

    async def people_add_photos(self, photos: list):
        await self._js(f"window.peopleAddPhotos && peopleAddPhotos({json.dumps(photos)})")

    async def people_delete_all(self):
        await self._js("window.peopleDeleteAll && peopleDeleteAll()")

    async def app_lock(self, on: bool, label: str = "", message: str = "", busy: bool = False):
        """Lock Gink: the lock screen over everything (on) or gone (off)."""
        opts = json.dumps({"label": label, "message": message, "busy": busy})
        await self._js(f"window.appLock && appLock({'true' if on else 'false'}, {opts})")

    async def set_care_mode(self, on: bool):
        """A workspace in healthcare mode: the Live camera shows the patient-privacy reminder."""
        await self._js(f"window.setCareMode && setCareMode({'true' if on else 'false'})")

    async def set_today(self, text: str):
        """Small chip under the centred welcome bar ("Next alarm 06:30 today")."""
        await self._js(f"setToday({json.dumps(text or '')})")

    # The device's own notification too (0.1.162): main_screen sets this to services/system_notify.post (Notification
    # Center on a Mac...), which shows it only when Gink isn't in front. (title, body, id) -> None
    on_system_notify = None

    def _device_too(self, title: str, body: str, nid: str = ""):
        if self.on_system_notify is not None:
            try:
                self.on_system_notify(title, body, nid)
            except Exception:
                pass                                       # a notification must never break the chat

    async def video_from_data(self, data_url: str, name: str):
        """A video from the apps' file picker: the page takes its frames (videoFromData), then sends attach_video."""
        await self._js(f"window.videoFromData && videoFromData({json.dumps(data_url)}, {json.dumps(name)})")

    async def notify(self, title: str, body: str = "", icon: str = "", kind: str = "", timeout: int = 6000,
                     actions: list = None, nid: str = "", system: bool = True):
        """An Apple-style notification card in the window (ui: ginkNotify) -- and on the device when Gink isn't in
        front (system=False: a quick confirmation of something the person just did)."""
        opts = {"title": title, "body": body, "icon": icon, "kind": kind, "timeout": timeout, "actions": actions or []}
        if nid:
            opts["id"] = nid
        await self._js(f"ginkNotify({json.dumps(opts)})")
        if system:
            self._device_too(title, body, nid)

    async def status_bar(self, status: str, message: str):
        await self._js(f"statusBar({json.dumps(status)}, {json.dumps(message)})")
        if message and status not in ("ok", ""):
            self._device_too("Notice" if status == "notice" else "Gink is having trouble", message, "status")

    async def policy_notice(self, date: str, privacy: str, terms: str):
        await self._js(f"policyNotice({json.dumps(date)}, {json.dumps(privacy)}, {json.dumps(terms)})")
        self._device_too("Privacy policy and terms updated", "What Gink does with your data, in plain words.", "policy")

    async def set_models(self, models: list, current_id: str):
        await self._js(f"setModels({json.dumps(models)}, {json.dumps(current_id)})")

    async def show_welcome(self, title: str, subtitle: str):
        await self._js(f"showWelcome({json.dumps(title)}, {json.dumps(subtitle)})")

    async def add_user_message(self, text: str):
        await self._js(f"addUserMessage({json.dumps(text)})")

    async def start_assistant_message(self, message_id: str, label: str = "Thinking\u2026"):
        await self._js(f"addAssistantMessage({json.dumps(message_id)}, {json.dumps(label)})")

    async def set_step_media(self, message_id: str, label: str, items: list):
        """Thumbnails at the right of a step line (created image, file badge, videos)."""
        await self._js(f"setStepMedia({json.dumps(message_id)}, {json.dumps(label)}, {json.dumps(items)})")

    async def set_spin_label(self, message_id: str, label: str):
        """What Gink is doing right now, under the spinner ("Searching the web…")."""
        await self._js(f"setSpinLabel({json.dumps(message_id)}, {json.dumps(label)})")

    async def append_token(self, message_id: str, token: str):
        await self._js(f"appendToken({json.dumps(message_id)}, {json.dumps(token)})")

    async def set_plain_text(self, message_id: str, text: str):
        await self._js(f"setPlainText({json.dumps(message_id)}, {json.dumps(text)})")

    async def finalize_message(self, message_id: str, raw_markdown: str):
        rendered = render_markdown_body(raw_markdown)
        await self._js(f"finalizeMessage({json.dumps(message_id)}, {json.dumps(rendered)})")

    async def load_chat(self, turns: list, new_id):
        """Draw a whole saved chat in one step (no placeholders), then glide to its end."""
        items = [{"role": "user", "text": t.get("content", "")} if t.get("role") == "user" else
                 {"role": "assistant", "id": new_id(), "html": render_markdown_body(t.get("content", ""))} for t in turns]
        await self._js(f"loadChat({json.dumps(items)})")

    async def add_complete_assistant_message(self, message_id: str, raw_markdown: str):
        """For loading history -- adds the row and renders it fully in
        one go, no streaming needed since it's already complete text."""
        await self.start_assistant_message(message_id)
        await self.finalize_message(message_id, raw_markdown)

def _build_page_html(welcome_title, welcome_subtitle, start_locked: bool = False):
    from . import agent_ui, chat_extras, compat, live_media, settings_page, update_ui, voice_ui, wake_ui
    page = live_media.inject(agent_ui.inject(update_ui.inject(wake_ui.inject(voice_ui.inject(chat_extras.inject(
        settings_page.inject(_build_page_html_base(welcome_title, welcome_subtitle))))))))
    page = compat.inject(page)                         # flex gap for older web engines (older Macs' app window)
    if start_locked:                                   # Lock Gink: covered from the very first frame
        i = page.rindex("</body>")
        page = page[:i] + "<script>window.appLock && appLock(true, {busy: true, message: 'Checking it\u2019s you\u2026'});</script>\n" + page[i:]
    return page
