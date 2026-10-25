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

import asyncio
import json

import toga
from toga.style import Pack

from .branding import LOGO_DATA_URI, LOGO_SPINNER_DATA_URI
from .theme import css_vars
from ..services.markdown_render import PYGMENTS_CSS, escape_for_plain_text, render_markdown_body

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
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
    min-height: 100%;
  }
  ::selection { background: var(--accent); color: var(--on-accent); }
  a { color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--accent-soft); }
  a:hover { border-bottom-color: var(--accent); }
  a { cursor: pointer; }
  a.opening { opacity: 0.55; }
  a[href^="http"]::after { content: " \\2197"; font-size: 0.8em; }
  #feed { max-width: 760px; margin: 0 auto; padding: 56px 20px 190px; }
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
  .row { display: flex; margin-bottom: 20px; }
  .row.user { margin-bottom: 14px; }
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
    white-space: pre-wrap;
    word-wrap: break-word;
  }
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
  .msg-logo { display: block; width: 26px; height: 26px; margin: 14px auto 0; opacity: 0.95; }
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
  hr { border: none; border-top: 1px solid var(--border); }
  /* ---------- composer (bottom input card) ---------- */
  #composer-wrap {
    position: fixed; left: 0; right: 0; bottom: 0;
    padding: 10px 20px 8px;
    background: linear-gradient(to bottom, rgba(255,255,255,0), var(--bg) 22px);
  }
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
  #cstatus { max-width: 760px; margin: 6px auto 0; min-height: 16px; font-size: 12px; color: var(--accent); text-align: center; }
  .disclaimer { max-width: 760px; margin: 2px auto 0; font-size: 11px; color: var(--text-muted); text-align: center; }
  @media (max-width: 520px) {
    #composer-wrap { padding: 8px 10px 6px; }
    .model .tier { display: none; }
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
  body.home #composer-wrap { transform: translateY(calc(-50vh + 103px)); background: transparent; }
  body.home #composer {
    display: flex; align-items: center; gap: 2px;
    border-radius: 30px; padding: 8px 10px 8px 8px; border-color: transparent;
    box-shadow: 0 6px 28px rgba(28, 33, 29, 0.10), 0 1px 3px rgba(28, 33, 29, 0.06);
  }
  /* the text box is moved INTO the row by layoutComposer() in home
     mode (works in every web engine, unlike display:contents/order) */
  body.home .crow { flex: 1; }
  body.home #cin { flex: 1; width: auto; padding: 6px 6px; min-height: 0; max-height: 120px; }
  body.home .crow > .spacer, body.home #orb { display: none; }
  body.home #send:not(.ready) { display: none; }      /* only shows once you type */
  body.home .model .tier { display: none; }
  body.home .model::after { content: " \\2304"; color: var(--text-muted); font-size: 13px; }
  body.home .menu { bottom: auto; top: 46px; }         /* drop menus downward from the centre */
  body.home #cstatus, body.home .disclaimer { opacity: 0; }
  body.home #feed { padding-bottom: 40px; }
  #welcome { transition: opacity 0.3s; }
  body.home #welcome { margin-top: calc(50vh - 141px); }
  .today-wrap { display: none; text-align: center; margin-top: 16px; }
  body.home .today-wrap { display: block; animation: word-in 0.8s ease 1s both; }
  .today {
    display: inline-block; font-size: 13px; color: var(--accent);
    background: var(--accent-soft); border-radius: 999px; padding: 6px 14px;
  }
  .today:empty { display: none; }
  @media (max-height: 560px) {
    body.home #composer-wrap { transform: translateY(calc(-50vh + 170px)); }
    body.home #welcome { margin-top: 30px; }
  }
  @media (prefers-reduced-motion: reduce) { #composer-wrap, body { transition: none; } }
  /* ---------- sidebar ----------
     Hidden by default on narrow windows; touching the left edge with the
     mouse slides it out ("peek"), leaving slides it away again. The
     sidebar icon pins it open (content moves over). */
  :root { --side-w: 272px; }
  #side {
    position: fixed; top: 0; bottom: 0; left: 0; width: var(--side-w); z-index: 30;
    background: var(--sidebar); border-right: 1px solid var(--border);
    display: flex; flex-direction: column;
    transform: translateX(-100%); transition: transform 0.28s cubic-bezier(0.22, 1, 0.36, 1), box-shadow 0.28s;
  }
  body.pinned #side, body.peek #side { transform: translateX(0); }
  body.peek:not(.pinned) #side { box-shadow: 8px 0 30px rgba(28, 33, 29, 0.12); }
  #edge { position: fixed; top: 0; bottom: 0; left: 0; width: 14px; z-index: 29; }
  body.pinned #edge { display: none; }
  body { transition: padding-left 0.28s cubic-bezier(0.22, 1, 0.36, 1), background 0.5s ease; }
  body.pinned { padding-left: var(--side-w); }
  #composer-wrap { left: 0; }
  body.pinned #composer-wrap { left: var(--side-w); }
  /* ONE sidebar button, always in the same top-left spot, above the
     sidebar: click = open/close, hover = slides open, leave = slides away */
  #tb-toggle { position: fixed; top: 10px; left: 12px; z-index: 35; }
  body.pinned #tb-toggle, body.peek #tb-toggle { background: var(--elevated); }
  #topbar { position: fixed; top: 10px; left: 52px; z-index: 28; display: flex; align-items: center; transition: left 0.28s; }
  body.pinned #topbar { left: calc(var(--side-w) + 16px); }
  .wordmark { font-weight: 700; font-size: 16px; color: var(--text-main); padding: 0 4px; }
  .wordmark span { color: var(--text-muted); font-weight: 500; }
  .side-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 12px 6px 56px; min-height: 34px; }
  .side-head .brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px; }
  .side-head .brand img { width: 26px; height: 26px; padding: 4px; border-radius: 8px; background: var(--logo-tile); margin-right: 8px; }
  .side-head .brand { gap: 0; }
  .nav { padding: 4px 8px; }
  .nav button, .recent {
    display: flex; align-items: center; gap: 12px; width: 100%;
    border: none; background: transparent; font: inherit; font-size: 14.5px; color: var(--text-main);
    padding: 8px 10px; border-radius: 10px; cursor: pointer; text-align: left;
  }
  .nav button:hover, .recent:hover { background: var(--elevated); }
  .nav svg { width: 19px; height: 19px; flex: none; margin-right: 12px; }
  .nav button > img { margin-right: 10px; }      /* the Gink Genie lamp: 21px + 10px = an icon's 19px + 12px */
  .nav .pro-nav { color: var(--accent); font-weight: 600; }
  .nav button { gap: 0; }
  #side-search { display: none; margin: 2px 8px 6px; }
  #side-search input {
    width: 100%; border: 1px solid var(--border); border-radius: 10px; padding: 8px 10px;
    font: inherit; font-size: 14px; background: var(--bg); color: var(--text-main); outline: none;
  }
  #side-search input:focus { border-color: var(--accent); }
  body.searching #side-search { display: block; }
  .side-label { font-size: 13px; color: var(--text-muted); padding: 14px 18px 6px; }
  #recents { flex: 1; overflow-y: auto; padding: 0 8px 8px; }
  .recent { position: relative; padding-right: 34px; }
  .recent .t { overflow: hidden; white-space: nowrap; text-overflow: ellipsis; flex: 1; }
  .recent.current { background: var(--hover, #E6EADF); font-weight: 500; }
  .recent .more {
    position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
    width: 28px; height: 28px; border-radius: 8px; border: none; background: transparent;
    color: var(--text-muted); display: none; align-items: center; justify-content: center; cursor: pointer;
  }
  .recent:hover .more, .recent.current .more { display: flex; }
  .recent .more:hover { background: var(--bg); color: var(--text-main); }
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
  .empty-recents { color: var(--text-muted); font-size: 13px; padding: 4px 12px; }
  #row-menu { position: fixed; z-index: 40; min-width: 150px; }
  #row-menu .danger { color: var(--danger); }
  .side-foot {
    display: flex; align-items: center; padding: 12px 14px;
    border-top: 1px solid var(--border);
  }
  .avatar {
    width: 32px; height: 32px; border-radius: 50%; flex: none; margin-right: 10px;
    background: linear-gradient(135deg, var(--accent), var(--logo-lime));
    color: #fff; font-weight: 700; font-size: 14px; display: flex; align-items: center; justify-content: center;
  }
  .side-foot .who { flex: 1; font-size: 14.5px; font-weight: 500; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
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
    body.pinned #composer-wrap { left: 0; }
    body.pinned #topbar { left: 12px; }
    body.pinned #side { box-shadow: 8px 0 30px rgba(28, 33, 29, 0.18); }
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
  /* ---------- icon rail (sidebar closed, desktop) ---------- */
  #rail {
    position: fixed; top: 0; bottom: 0; left: 0; width: 60px; z-index: 27;
    display: flex; flex-direction: column; align-items: center; padding: 54px 0 14px;
  }
  #rail .ibtn { margin-bottom: 6px; color: var(--text-muted); }
  #rail .ibtn:hover { color: var(--text-main); }
  #rail .spacer { flex: 1; }
  #rail .avatar { margin: 6px 0 0; width: 32px; height: 32px; cursor: pointer; font-size: 13px; }
  body.pinned #rail { display: none; }
  @media (min-width: 761px) { body:not(.pinned) { padding-left: 60px; } body:not(.pinned) #composer-wrap { left: 60px; } }
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
  body.home #atts { position: absolute; left: 12px; right: 12px; bottom: 100%; margin-bottom: 8px; justify-content: center; }
  body.home #composer { position: relative; }
  #composer.dragging { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
  .uatts { display: flex; flex-wrap: wrap; justify-content: flex-end; margin-bottom: 6px; max-width: 460px; }
  .uatts .att { margin: 0 0 6px 8px; animation: none; }
  .uatts .att.photo { padding: 0; border: none; background: none; }
  .uatts .att.photo img { width: 160px; height: auto; max-height: 200px; margin: 0; border-radius: 14px; border: 1px solid var(--border); }
  .sync-line { font-size: 11.5px; color: var(--text-muted); display: block; font-weight: 400; }
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
    <button class="ibtn" data-rail="genie" title="Gink Genie"><img src="data:image/png;base64,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" alt="" style="width:21px;height:13px;border-radius:3px;object-fit:cover;flex:none"></button>
    <button class="ibtn" data-rail="media" title="Media Studio"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="M20.5 16l-5-5-8 8.5"/></svg></button>
    <div class="spacer"></div>
    <button class="ibtn" data-rail="settings" title="Settings"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg></button>
    <div class="avatar" id="rail-avatar" data-rail="settings" title="Account">G</div>
  </nav>
  <button class="ibtn tb-toggle" id="tb-toggle" title="Sidebar"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="17" height="17" rx="4"/><path d="M10 9l-3 3 3 3M14 9l3 3-3 3"/></svg></button>
  <div id="topbar">
    <div class="wordmark">Gink <span>Assistant</span></div>
  </div>
  <aside id="side">
    <div class="side-head">
      <div class="brand"><img src="__LOGO_DATA_URI__" alt="">Gink</div>
    </div>
    <div class="nav">
      <button data-nav="new"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h8"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>New chat</button>
      <button data-nav="search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg>Search chats</button>
      <button data-nav="tasks"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="2"/></svg>Workspace</button>
      <button data-nav="media"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="M20.5 16l-5-5-8 8.5"/></svg>Media Studio</button>
      <button data-nav="genie"><img src="data:image/png;base64,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" alt="" style="width:21px;height:13px;border-radius:3px;object-fit:cover;flex:none">Gink Genie</button>
    </div>
    <div id="side-search"><input id="side-q" placeholder="Search chats" autocomplete="off"></div>
    <div class="side-label">Recents</div>
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
  <div id="feed">
    <div id="welcome">
      <h1 data-text="__WELCOME_TITLE__">__WELCOME_TITLE__</h1>
      <p>__WELCOME_SUBTITLE__</p>
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
    <div class="disclaimer">Gink is AI and can make mistakes. Please double-check responses.</div>
  </div>
<script>
  var LOGO_URI = "__LOGO_DATA_URI__";
  var SPIN_URI = "__SPIN_DATA_URI__";
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
  }
  function peek(on) {
    clearTimeout(peekTimer);
    if (on) { if (!hoverBlocked) document.body.classList.add('peek'); }
    else peekTimer = setTimeout(function () { document.body.classList.remove('peek'); }, 260);
  }
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
  function renderRecents() {
    var q = (document.getElementById('side-q').value || '').toLowerCase();
    var box = document.getElementById('recents'); box.innerHTML = '';
    var shown = sessions.filter(function (s) { return !q || s.title.toLowerCase().indexOf(q) >= 0; });
    if (!shown.length) {
      var e = document.createElement('div'); e.className = 'empty-recents';
      e.innerText = q ? 'No chats match \u201c' + q + '\u201d' : 'Your chats will appear here';
      box.appendChild(e); return;
    }
    var pinned = shown.filter(function (s) { return s.pinned; }), rest = shown.filter(function (s) { return !s.pinned; });
    shown = pinned.concat(rest);
    shown.forEach(function (s, i) {
      if (pinned.length && (i === 0 || i === pinned.length)) {
        var h = document.createElement('div'); h.className = 'recents-head';
        h.textContent = i === 0 ? 'Pinned' : 'Recent'; box.appendChild(h);
      }
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

    var edge = document.getElementById('edge'), side = document.getElementById('side');
    var tb = document.getElementById('tb-toggle');
    edge.addEventListener('mouseenter', function () { peek(true); });
    tb.addEventListener('mouseenter', function () { peek(true); });
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
    document.querySelector('.nav').addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      var what = b.getAttribute('data-nav');
      if (what === 'search') {
        var on = !document.body.classList.contains('searching');
        document.body.classList.toggle('searching', on);
        if (on) document.getElementById('side-q').focus(); else { document.getElementById('side-q').value = ''; renderRecents(); }
        return;
      }
      if (what === 'new') ginkEmit('new_chat'); else ginkEmit('open', what);
      if (window.innerWidth < 760) setPinned(false);
    });
    document.getElementById('side-q').addEventListener('input', renderRecents);
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
    var d = document.createElement('div'); d.className = 'att' + (a.kind === 'image' && !removable ? ' photo' : '');
    if (a.loading) d.className += ' loading';
    var ext = (a.name.split('.').pop() || 'file').slice(0, 4);
    if (a.thumb) { var im = document.createElement('img'); im.src = a.thumb; d.appendChild(im); }
    else { var f = document.createElement('div'); f.className = 'ficon'; f.textContent = ext; d.appendChild(f); }
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
    refreshSend();
  }
  function readAndEmit(file) {
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
  // and Python polls ginkTake() a few times a second (WebChatFeed.poll).
  var ginkEvents = [];
  function ginkEmit(type, value) { ginkEvents.push({type: type, value: value === undefined ? null : value}); }
  function ginkTake() { var out = JSON.stringify(ginkEvents); ginkEvents = []; return out; }

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
    document.getElementById('model').addEventListener('click', function (e) {
      e.stopPropagation(); var m = document.getElementById('model-menu'); var was = m.classList.contains('hidden'); closeMenus(); if (was) m.classList.remove('hidden');
    });
    document.getElementById('plus-menu').addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return; closeMenus(); ginkEmit('menu', b.getAttribute('data-act'));
    });
    document.getElementById('model-menu').addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return; closeMenus(); ginkEmit('model', b.getAttribute('data-id'));
    });
    document.addEventListener('click', closeMenus);
    refreshSend(); t.focus();
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
  function setModels(models, currentId) {
    var menu = document.getElementById('model-menu'); menu.innerHTML = '';
    models.forEach(function (m) {
      var b = document.createElement('button'); b.setAttribute('data-id', m.id);
      b.innerHTML = '<span></span><span class="hint"></span>';
      b.children[0].innerText = m.name; b.children[1].innerText = m.tier || '';
      if (m.id === currentId) { b.classList.add('sel'); document.getElementById('model-name').innerText = m.name; document.getElementById('model-tier').innerText = m.tier || ''; }
      menu.appendChild(b);
    });
  }

  function scrollDown() { window.scrollTo(0, document.body.scrollHeight); }

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
    var nearBottom = (window.innerHeight + window.scrollY) >= document.body.scrollHeight - 160;
    st.innerHTML = html;
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

  function setPlainText(id, text) {
    var el = document.getElementById(id);
    if (el) { el.innerText = text; scrollDown(); }
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
    upgradeVideoLinks(el);
    upgradeFileLinks(el);
    enhanceCodeBlocks(el);
    addGinkActions(el, id);
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
    html = html.replace("__THEME_VARS__", css_vars())
    return html



class WebChatFeed:
    """Thin async wrapper around a toga.WebView running the chat-feed
    page. Call methods on this instead of touching the WebView directly."""

    def __init__(self, welcome_title: str = "Gink Ai Assistant", welcome_subtitle: str = "Ready to help with your workflows."):
        self.web_view = toga.WebView(style=Pack(flex=1))
        self.web_view.set_content("https://gink.local/", _build_page_html(welcome_title, welcome_subtitle))

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
        try:
            raw = await asyncio.wait_for(self.web_view.evaluate_javascript("ginkTake()"), timeout=2.0)
        except Exception:
            return []
        try:
            if isinstance(raw, (list, dict)):
                return raw if isinstance(raw, list) else []
            data = json.loads(raw) if raw else []
            if isinstance(data, str):          # some platforms JSON-encode the string again
                data = json.loads(data)
            return data if isinstance(data, list) else []
        except Exception:
            return []

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

    async def set_today(self, text: str):
        """Small chip under the centred welcome bar ("Next alarm 06:30 today")."""
        await self._js(f"setToday({json.dumps(text or '')})")

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

    async def add_complete_assistant_message(self, message_id: str, raw_markdown: str):
        """For loading history -- adds the row and renders it fully in
        one go, no streaming needed since it's already complete text."""
        await self.start_assistant_message(message_id)
        await self.finalize_message(message_id, raw_markdown)

def _build_page_html(welcome_title, welcome_subtitle):
    from . import agent_ui, chat_extras, settings_page, update_ui, voice_ui, wake_ui
    return agent_ui.inject(update_ui.inject(wake_ui.inject(voice_ui.inject(chat_extras.inject(settings_page.inject(
        _build_page_html_base(welcome_title, welcome_subtitle)))))))
