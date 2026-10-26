"""
Chat-page extras, injected like ui/settings_page.py:

* Spinner: centred, with a label that follows what Gink is really doing
  ("Thinking…", "Searching the web…", "Writing…"); Python sets it with
  setSpinLabel(). If nothing happens for a while it says so honestly
  ("Still thinking…").
* Logo handover: the finished-reply logo shows only under the newest reply.
  It fades away the moment a new answer starts and fades in, centred, when
  that answer is done.
* Buttons under every Gink reply: Copy, Read aloud, Retry, thumbs up/down
  (down asks an optional reason). Feedback goes to the server WITHOUT any
  message text.
* Sidebar chat menu: Rename, Pin / Unpin, Export chat, Delete.
* "Jump to latest" button when scrolled up.
* Shortcuts: Ctrl/Cmd+Shift+O new chat, Ctrl/Cmd+K search chats, "/" type a message.
"""

ICONS = {
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "speak": '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/>',
    "retry": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "up": '<path d="M7 11v9H4v-9zM7 11l4-8a2 2 0 0 1 2 2v4h5.5a2 2 0 0 1 2 2.3l-1.2 7A2 2 0 0 1 17.3 20H7"/>',
    "down": '<path d="M17 13V4h3v9zM17 13l-4 8a2 2 0 0 1-2-2v-4H5.5a2 2 0 0 1-2-2.3l1.2-7A2 2 0 0 1 6.7 4H17"/>',
    "rename": '<path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
    "pin": '<path d="M9 4h6l-1 6 4 3v2h-5v5l-1 1-1-1v-5H6v-2l4-3z"/>',
    "export": '<path d="M12 4v11M7.5 10.5L12 15l4.5-4.5"/><path d="M5 19h14"/>',
    "jump": '<path d="M12 5v14M6 13l6 6 6-6"/>',
}


def icon(name: str, size: int = 16, filled: bool = False) -> str:
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


CSS = r"""
  /* ---------- spinner with a label, centred ---------- */
  /* a reply spans the whole chat column, so the spinner and the logo sit in the true middle */
  .row > .assistant-text { flex: 1 1 auto; min-width: 0; }
  /* spinner on the LEFT with its label beside it (Claude-style) */
  .gink-spin { display: flex; flex-direction: row; align-items: center; justify-content: flex-start; margin: 10px 0 4px; }
  .gink-spin .gink-spinner { margin: 0; width: 22px !important; height: 22px !important; flex: none; }
  .spin-label {
    /* plain text + a gentle fade: works in every web engine (older Safari drew
       gradient-clipped text as invisible) */
    margin: 0 0 0 10px; font-size: 14px; color: var(--text-muted); letter-spacing: 0.01em;
    animation: label-fade 1.8s ease-in-out infinite;
  }
  @keyframes label-fade { 0%, 100% { opacity: 1; } 50% { opacity: 0.55; } }
  body.reduced-motion .spin-label { opacity: 1; }
  /* ---------- steps timeline ("Worked for 12s") ---------- */
  .gsteps { margin: 2px 0 10px; }
  .gsteps .ghead { display: inline-flex; align-items: center; font-size: 14px; color: var(--text-muted); cursor: default;
    border: none; background: none; padding: 2px 0; font-family: inherit; }
  .gsteps.done .ghead { cursor: pointer; }
  .gsteps.done .ghead:hover { color: var(--text-main); }
  .gsteps .ghead .chev { margin-left: 6px; transition: transform 0.15s; font-size: 12px; }
  .gsteps.open .ghead .chev { transform: rotate(90deg); }
  .gsteps ol { list-style: none; margin: 8px 0 0; padding: 0; }
  .gsteps.done:not(.open) ol { display: none; }
  .gsteps li { position: relative; display: flex; align-items: flex-start; padding: 0 0 14px 30px; font-size: 14.5px; color: var(--text-main); line-height: 1.4; }
  .gsteps li:last-child { padding-bottom: 2px; }
  .gsteps li::before { content: ""; position: absolute; left: 9px; top: 22px; bottom: 2px; width: 1px; background: var(--border); }
  .gsteps li:last-child::before { display: none; }
  .gsteps li svg { position: absolute; left: 0; top: 1px; color: var(--text-muted); }
  .gsteps li.now { color: var(--text-muted); }
  .gsteps li.now svg { color: var(--accent); animation: step-spin 2.4s linear infinite; }
  @keyframes step-spin { to { transform: rotate(360deg); } }
  body.reduced-motion .gsteps li.now svg { animation: none; }

  /* ---------- big centred logo; the middle animates while Gink works (Claude-style) ---------- */
  .work-logo { width: 104px; height: 104px; margin: 18px auto 0; }
  .work-logo svg { display: block; width: 104px; height: 104px; overflow: visible;
    animation: logo-turn 6s linear infinite; }            /* the whole snowflake spins slowly */
  @keyframes logo-turn { to { transform: rotate(360deg); } }
  .work-logo .hex-inner { transform-box: fill-box; transform-origin: center;
    animation: hex-step 2.6s cubic-bezier(0.65, 0, 0.35, 1) infinite; }
  /* the arms are joined to the outer hexagon's corners, so it stays still and only pulses in colour */
  .work-logo .lime .hex-outer { animation: hex-pulse 2.6s ease-in-out infinite; }
  /* inner hexagon: a quick eased turn, a short rest, another turn (60 deg = looks the same, so it loops seamlessly) */
  @keyframes hex-step {
    0% { transform: rotate(0deg) scale(1); }
    35% { transform: rotate(60deg) scale(0.86); }
    50% { transform: rotate(60deg) scale(0.86); }
    85% { transform: rotate(120deg) scale(1); }
    100% { transform: rotate(120deg) scale(1); }
  }
  @keyframes hex-pulse { 0%, 100% { stroke: #A8F03C; } 40% { stroke: #7FD319; } }
  /* tips light up one arm after another */
  .work-logo .lime .tip { animation: tip-glow 2.6s ease-in-out infinite; }
  .work-logo .lime .t1 { animation-delay: -2.17s; } .work-logo .lime .t2 { animation-delay: -1.73s; }
  .work-logo .lime .t3 { animation-delay: -1.3s; } .work-logo .lime .t4 { animation-delay: -0.87s; }
  .work-logo .lime .t5 { animation-delay: -0.43s; }
  @keyframes tip-glow { 0%, 100% { stroke: #A8F03C; } 50% { stroke: #5FB80F; } }
  body.reduced-motion .work-logo svg,
  body.reduced-motion .work-logo .hex-inner, body.reduced-motion .work-logo .hex-outer,
  body.reduced-motion .work-logo .tip { animation: none; }

  /* ---------- thumbnails at the right of a step ---------- */
  .gsteps li .stxt { flex: 1; min-width: 0; padding-top: 1px; }
  .gsteps li .smedia { display: flex; margin-left: 12px; flex: none; }
  .gsteps li .smedia img { width: 56px; height: 40px; object-fit: cover; border-radius: 7px; border: 1px solid var(--border);
    margin-left: 6px; background: var(--elevated); box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  .gsteps li .smedia .sfile { height: 40px; min-width: 40px; padding: 0 8px; border-radius: 7px; margin-left: 6px; display: flex;
    align-items: center; justify-content: center; font-size: 11px; font-weight: 700; color: #fff; background: #6E756D; }
  .gsteps li .smedia .sfile.PDF { background: #D9483B; } .gsteps li .smedia .sfile.DOCX { background: #2B65C9; }
  .gsteps li .smedia .sfile.XLSX, .gsteps li .smedia .sfile.CSV { background: #1E7B45; }

  /* ---------- generating glow (images, PDFs, documents...) ---------- */
  .creating .gink-spin .gink-spinner { display: none; }       /* the glow shows progress; the label stays */
  .creating .gink-spin .spin-label { margin-left: 0; }
  .gen-glow { position: relative; overflow: hidden; border-radius: 18px; border: 1px solid var(--border);
    background: var(--bg); margin: 8px 0 6px; max-width: 460px; }
  .gen-glow.image { height: 300px; }
  .gen-glow.file { height: 86px; display: flex; align-items: center; padding: 0 16px; }
  .gen-glow::before { content: ""; position: absolute; left: -20%; right: -20%; top: -60%; height: 140%;
    background: radial-gradient(ellipse at 50% 0%, rgba(168,240,60,0.38) 0%, rgba(168,240,60,0.16) 38%, rgba(168,240,60,0.05) 62%, rgba(168,240,60,0) 75%);
    animation: glow-breathe 3.2s ease-in-out infinite; }
  .gen-glow::after { content: ""; position: absolute; top: 0; bottom: 0; width: 45%; left: -50%;
    background: linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,0.55), rgba(255,255,255,0));
    animation: glow-sweep 2.6s ease-in-out infinite; }
  body.theme-dark .gen-glow::after { background: linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,0.07), rgba(255,255,255,0)); }
  @keyframes glow-breathe { 0%, 100% { opacity: 0.75; transform: scale(1); } 50% { opacity: 1; transform: scale(1.06); } }
  @keyframes glow-sweep { from { left: -50%; } to { left: 110%; } }
  .gen-glow .gtxt { position: absolute; left: 0; right: 0; bottom: 16px; text-align: center; font-size: 13.5px; color: var(--text-muted); z-index: 1; }
  .gen-glow.file .gtxt { position: static; text-align: left; margin-left: 14px; }
  .gen-glow .gdoc { width: 42px; height: 50px; border-radius: 8px; background: rgba(168,240,60,0.28); z-index: 1; flex: none; }
  body.reduced-motion .gen-glow::before, body.reduced-motion .gen-glow::after { animation: none; }

  /* ---------- logo handover ---------- */
  .msg-logo.arriving { animation: logo-in 0.45s cubic-bezier(0.22, 1, 0.36, 1) both; }
  .msg-logo.leaving { animation: logo-out 0.25s ease-in both; }
  @keyframes logo-in { from { opacity: 0; transform: scale(0.7) rotate(-40deg); } to { opacity: 0.95; transform: none; } }
  @keyframes logo-out { to { opacity: 0; transform: scale(0.7); } }
  /* ---------- buttons under Gink's replies ---------- */
  .gactions { display: flex; align-items: center; margin: 8px 0 0 -6px; opacity: 0; transition: opacity 0.15s; flex-wrap: wrap; }
  .row:hover .gactions, .gactions.latest, .gactions.open { opacity: 1; }
  @media (hover: none) { .gactions { opacity: 1; } }
  .ga {
    width: 30px; height: 30px; border: none; background: transparent; border-radius: 8px; color: var(--text-muted);
    display: inline-flex; align-items: center; justify-content: center; cursor: pointer; padding: 0;
  }
  .ga:hover { background: var(--elevated); color: var(--text-main); }
  .ga.on { color: var(--accent); }
  .ga.done { color: var(--accent); }
  .reasons { display: flex; flex-wrap: wrap; align-items: center; margin-left: 6px; }
  .reasons span { font-size: 12.5px; color: var(--text-muted); margin-right: 6px; }
  .reasons button {
    font: inherit; font-size: 12.5px; border: 1px solid var(--border); background: var(--bg); color: var(--text-main);
    border-radius: 999px; padding: 3px 10px; margin: 2px 4px 2px 0; cursor: pointer;
  }
  .reasons button:hover { border-color: var(--accent); color: var(--accent); }
  .thanks { font-size: 12.5px; color: var(--accent); margin-left: 8px; }
  /* ---------- code blocks (redesigned) ---------- */
  .code-block { border: 1px solid #2F332E !important; border-radius: 12px !important; overflow: hidden; background: #1C1E1A !important; margin: 12px 0 !important; max-width: 100%; }
  .code-block-bar { background: #262924 !important; border-bottom: 1px solid #33372F !important; padding: 6px 8px 6px 14px !important; display: flex; align-items: center; }
  .code-block-label { color: #C9D1C6 !important; font-size: 12.5px !important; font-weight: 500; display: flex; align-items: center; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .code-block-label .ldot { width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; flex: none; }
  .code-block-bar button {
    background: transparent !important; color: #AAB3A7 !important; border: 1px solid transparent !important; border-radius: 7px !important;
    font-size: 12px !important; padding: 4px 9px !important; margin-left: 2px; cursor: pointer; display: inline-flex; align-items: center;
  }
  .code-block-bar button:hover { background: #33372F !important; color: #fff !important; }
  .code-block-bar button svg { width: 14px; height: 14px; margin-right: 5px; }
  .code-block-bar button.on { color: #A8F03C !important; }
  .code-block-body { position: relative; display: flex; background: #1C1E1A; }
  .code-block-body .lns {
    flex: none; padding: 14px 0 14px 12px; text-align: right; color: #5D665A; font: 12.5px/1.6 'SF Mono', Menlo, Consolas, monospace;
    user-select: none; -webkit-user-select: none; white-space: pre; border-right: 1px solid #2B2F29; padding-right: 10px;
  }
  .code-block-body .codehilite { flex: 1; min-width: 0; background: transparent !important; }
  .code-block-body pre { background: transparent !important; margin: 0 !important; padding: 14px 16px !important; overflow-x: auto; font: 12.5px/1.6 'SF Mono', Menlo, Consolas, monospace !important; color: #E6EDE3; }
  .code-block.wrap pre { white-space: pre-wrap !important; word-break: break-word; }
  .code-block.wrap .lns { display: none; }
  .code-block.collapsed .code-block-body { max-height: 420px; overflow: hidden; }
  .code-block.collapsed .code-block-body::after {
    content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 70px;
    background: linear-gradient(rgba(28,30,26,0), #1C1E1A);
  }
  .code-more { display: block; width: 100%; border: none; border-top: 1px solid #2F332E; background: #222520; color: #C9D1C6; font: inherit; font-size: 12.5px; padding: 8px; cursor: pointer; }
  .code-more:hover { color: #A8F03C; }
  .assistant-text p code, .assistant-text li code { background: var(--elevated); color: var(--text-main); border: 1px solid var(--border); padding: 1px 5px; border-radius: 5px; font-size: 0.9em; }
  /* ---------- file cards (files Gink made) ---------- */
  .fcard {
    display: flex; align-items: center; max-width: 460px; margin: 12px 0 6px; padding: 12px 14px;
    border: 1px solid var(--border); border-radius: 14px; background: var(--bg); text-decoration: none; color: var(--text-main);
  }
  .fcard .ficon2 {
    width: 42px; height: 50px; border-radius: 8px; flex: none; margin-right: 12px; display: flex; align-items: center;
    justify-content: center; font-size: 11px; font-weight: 700; color: #fff; letter-spacing: 0.02em;
  }
  .fcard .ficon2.pdf { background: #D9483B; } .fcard .ficon2.docx { background: #2B65C9; }
  .fcard .ficon2.xlsx, .fcard .ficon2.csv { background: #1E7B45; } .fcard .ficon2.other { background: #6E756D; }
  .fcard .fmeta { flex: 1; min-width: 0; }
  .fcard .fname { font-weight: 600; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .fcard .fsize { font-size: 12.5px; color: var(--text-muted); margin-top: 2px; }
  .fcard button {
    font: inherit; font-size: 13px; border: 1px solid var(--border); background: var(--bg); color: var(--text-main);
    border-radius: 999px; padding: 6px 13px; margin-left: 6px; cursor: pointer; white-space: nowrap;
  }
  .fcard button:hover { border-color: var(--accent); color: var(--accent); }
  .fcard button.primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
  .icard { max-width: 460px; margin: 12px 0 6px; border: 1px solid var(--border); border-radius: 16px; overflow: hidden; background: var(--bg); }
  .icard .ipic { display: block; width: 100%; min-height: 160px; background: var(--elevated); cursor: zoom-in; }
  .icard .ipic img { display: block; width: 100%; height: auto; }
  .icard .ibar { display: flex; align-items: center; padding: 8px 10px 8px 14px; }
  .icard .ibar .fname { flex: 1; min-width: 0; font-size: 13px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .icard .ibar button { font: inherit; font-size: 13px; border: 1px solid var(--border); background: var(--bg); color: var(--text-main);
    border-radius: 999px; padding: 5px 12px; margin-left: 6px; cursor: pointer; }
  .icard .ibar button:hover { border-color: var(--accent); color: var(--accent); }
  /* ---------- sidebar: pinned group ---------- */
  .recents-head { font-size: 12px; color: var(--text-muted); padding: 10px 10px 4px; }
  .recent.pinned .t::before { content: "\1F4CC"; font-size: 11px; margin-right: 6px; opacity: 0.7; }
  #row-menu button svg { width: 16px; height: 16px; margin-right: 10px; color: var(--text-muted); flex: none; }
  /* ---------- jump to latest ---------- */
  #jump {
    position: fixed; left: 50%; bottom: 150px; transform: translateX(-50%) translateY(10px); z-index: 25;
    width: 36px; height: 36px; border-radius: 50%; border: 1px solid var(--border); background: var(--bg);
    color: var(--text-main); box-shadow: 0 4px 14px rgba(0,0,0,0.12); cursor: pointer; opacity: 0; pointer-events: none;
    display: flex; align-items: center; justify-content: center; transition: opacity 0.2s, transform 0.2s;
  }
  #jump.show { opacity: 1; pointer-events: auto; transform: translateX(-50%); }
  body.pinned #jump { left: calc(50% + var(--side-w) / 2); }
  body.home #jump { display: none; }
"""

HTML = r"""
  <button id="jump" title="Jump to latest" aria-label="Jump to latest">__I_jump__</button>
"""

JS = r"""
  // ======================= chat extras =======================
  var GI = __GICONS__;
  var GINK_LOGO_SVG = __GINK_LOGO__;

  // ---- spinner (left) + step timeline + generating glow + logo handover ----
  var spinClocks = {}, toolLabel = {}, spinState = {};
  var CLOCK = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>';
  var GENERIC = /^(Thinking|Still thinking|Writing|Taking a little longer)/;
  function retireLogo() {
    if (!lastLogoMsgId) return;
    var prev = document.getElementById(lastLogoMsgId), logo = prev ? prev.querySelector('.msg-logo') : null;
    if (logo) { logo.classList.remove('arriving'); logo.classList.add('leaving'); setTimeout(function () { if (logo.parentNode) logo.parentNode.removeChild(logo); }, 260); }
    var bar = prev ? prev.querySelector('.gactions') : null;
    if (bar) bar.classList.remove('latest');
    lastLogoMsgId = null;
  }
  function stepText(t) { return String(t || '').replace(/[\u2026.]+$/, ''); }
  function renderSteps(el, st, done) {
    var box = el.querySelector('.gsteps');
    if (!st.steps.length) { if (box) box.parentNode.removeChild(box); return; }
    if (!box) { box = document.createElement('div'); box.className = 'gsteps'; el.insertBefore(box, el.firstChild); }
    var secs = Math.max(1, Math.round((Date.now() - st.t0) / 1000));
    box.className = 'gsteps' + (done ? ' done' : '');
    box.innerHTML = '<button class="ghead" type="button">' + (done ? 'Worked for ' + secs + 's<span class="chev">\u203a</span>' : 'Working\u2026') + '</button><ol>' +
      st.steps.map(function (t, i) { var now = !done && i === st.steps.length - 1;
        return '<li class="' + (now ? 'now' : '') + '">' + CLOCK + '<span class="stxt"></span></li>'; }).join('') + '</ol>';
    Array.prototype.forEach.call(box.querySelectorAll('li'), function (li, i) {
      li.querySelector('.stxt').textContent = stepText(st.steps[i]);
      var items = (st.media || {})[stepText(st.steps[i])];
      if (!items || !items.length) return;
      var strip = document.createElement('span'); strip.className = 'smedia';
      items.slice(0, 3).forEach(function (m) {
        if (m.kind === 'img' && m.src) { var im = document.createElement('img'); im.src = m.src; im.alt = m.text || ''; im.title = m.text || ''; strip.appendChild(im); }
        else if (m.kind === 'file') { var f = document.createElement('span'); f.className = 'sfile ' + (m.text || ''); f.textContent = (m.text || 'FILE').slice(0, 4); f.title = m.title || ''; strip.appendChild(f); }
      });
      li.appendChild(strip);
    });
  }
  function showGenerating(el, kind, text) {
    var g = el.querySelector('.gen-glow');
    if (g && g.className.indexOf(kind) >= 0) return;
    if (g) g.parentNode.removeChild(g);
    g = document.createElement('div'); g.className = 'gen-glow ' + kind;
    g.innerHTML = (kind === 'file' ? '<div class="gdoc"></div>' : '') + '<div class="gtxt"></div>';
    g.querySelector('.gtxt').textContent = text;
    var spin = el.querySelector('.gink-spin'); el.insertBefore(g, spin || null);
    el.classList.add('creating');
  }
  function setSpinLabel(id, text) {
    var el = document.getElementById(id), lab = el ? el.querySelector('.spin-label') : null;
    if (!lab) return;
    lab.textContent = text; toolLabel[id] = true;
    var st = spinState[id] || (spinState[id] = {t0: Date.now(), steps: []});
    if (!GENERIC.test(text) && st.steps[st.steps.length - 1] !== text) { st.steps.push(text); renderSteps(el, st, false); }
    if (/creating your image|creating an image/i.test(text)) showGenerating(el, 'image', 'Creating your image\u2026');
    else if (/making your file|creating your (pdf|document|file)/i.test(text)) showGenerating(el, 'file', 'Making your file\u2026');
  }
  function setStepMedia(id, label, items) {
    var el = document.getElementById(id); if (!el) return;
    var st = spinState[id] || (spinState[id] = {t0: Date.now(), steps: []});
    st.media = st.media || {};
    var key = stepText(label);
    if (!st.steps.some(function (t) { return stepText(t) === key; })) st.steps.push(label);   // quick answers had no live step
    st.media[key] = items || [];
    renderSteps(el, st, false);
  }
  function workLogo() {
    var w = document.createElement('div'); w.className = 'work-logo';
    w.innerHTML = GINK_LOGO_SVG;           // ui/logo_svg.py: arms, outer + inner hexagon as separate parts
    return w;
  }
  function noteWriting(id) {
    var el = document.getElementById(id), lab = el ? el.querySelector('.spin-label') : null;
    if (lab && lab.textContent !== 'Writing\u2026') { lab.textContent = 'Writing\u2026'; toolLabel[id] = false; }
    var g = el ? el.querySelector('.gen-glow') : null;          // the real result is arriving
    if (g && el.querySelector('.stream') && el.querySelector('.stream').textContent.trim()) { g.parentNode.removeChild(g); el.classList.remove('creating'); }
  }
  function startSpinClock(id) {
    spinState[id] = spinState[id] || {t0: Date.now(), steps: []};
    var host = document.getElementById(id);
    if (host && !host.querySelector('.work-logo')) host.appendChild(workLogo());   // centred logo + ring of dots
    var t0 = spinState[id].t0;
    spinClocks[id] = setInterval(function () {
      var el = document.getElementById(id), lab = el ? el.querySelector('.spin-label') : null;
      if (!lab) { clearInterval(spinClocks[id]); return; }
      if (toolLabel[id] || lab.textContent === 'Writing\u2026') return;   // real progress is showing
      var s = (Date.now() - t0) / 1000;
      if (s > 25) lab.textContent = 'Taking a little longer than usual\u2026';
      else if (s > 8) lab.textContent = 'Still thinking\u2026';
    }, 1000);
  }
  function stopSpinClock(id) {
    clearInterval(spinClocks[id]); delete spinClocks[id]; delete toolLabel[id];
    var st = spinState[id], el = document.getElementById(id);
    if (el) el.classList.remove('creating');
    if (st && el && st.steps.length) renderSteps(el, st, true);     // "Worked for 12s" summary, folded
    delete spinState[id];
  }
  document.addEventListener('click', function (e) {
    var h = e.target.closest && e.target.closest('.gsteps.done .ghead'); if (!h) return;
    h.parentNode.classList.toggle('open');
  });

  // ---- buttons under Gink's replies ----
  function replyText(el) {
    var c = el.cloneNode(true);
    Array.prototype.forEach.call(c.querySelectorAll('.gactions, .msg-logo, .gink-spin, .vcards, .code-block-bar'), function (n) { n.parentNode.removeChild(n); });
    return (c.innerText || c.textContent || '').trim();
  }
  function questionBefore(el) {
    var row = el.closest('.row'), p = row ? row.previousElementSibling : null;
    while (p && !p.classList.contains('user')) p = p.previousElementSibling;
    var b = p ? p.querySelector('.bubble') : null;
    return b ? b.innerText : '';
  }
  function addGinkActions(el, id) {
    var old = el.querySelector('.gactions'); if (old) old.parentNode.removeChild(old);
    var bar = document.createElement('div'); bar.className = 'gactions latest';
    bar.innerHTML =
      '<button class="ga" data-ga="copy" title="Copy">' + GI.copy + '</button>' +
      '<button class="ga" data-ga="speak" title="Read aloud">' + GI.speak + '</button>' +
      '<button class="ga" data-ga="retry" title="Retry">' + GI.retry + '</button>' +
      '<button class="ga" data-ga="up" title="Good answer">' + GI.up + '</button>' +
      '<button class="ga" data-ga="down" title="Bad answer">' + GI.down + '</button>';
    el.appendChild(bar);
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('.gactions .ga'); if (!b) return;   // not the reason chips
    e.stopPropagation();
    var el = b.closest('.assistant-text'), bar = b.closest('.gactions'), what = b.getAttribute('data-ga');
    var text = replyText(el);
    if (what === 'copy') {
      copyText(text, function () { b.innerHTML = GI.check; b.classList.add('done');
        setTimeout(function () { b.innerHTML = GI.copy; b.classList.remove('done'); }, 1500); });
    } else if (what === 'speak') { ginkEmit('read_aloud', text);
    } else if (what === 'retry') { var q = questionBefore(el); if (q) ginkEmit('send', q);
    } else if (what === 'up' || what === 'down') {
      if (bar.getAttribute('data-rated')) return;
      bar.setAttribute('data-rated', what);
      b.classList.add('on');
      bar.querySelector(what === 'up' ? '[data-ga="down"]' : '[data-ga="up"]').style.display = 'none';
      if (what === 'up') { ginkEmit('feedback', {rating: 'up', chars: text.length}); thanks(bar); return; }
      bar.classList.add('open');
      var r = document.createElement('div'); r.className = 'reasons';
      r.innerHTML = '<span>What went wrong?</span><button data-reason="wrong">Wrong</button><button data-reason="not_helpful">Not helpful</button>' +
                    '<button data-reason="too_long">Too long</button><button data-reason="unsafe">Unsafe</button><button data-reason="other">Other</button>';
      bar.appendChild(r);
      r.addEventListener('click', function (ev) {
        var rb = ev.target.closest('button'); if (!rb) return; ev.stopPropagation();
        ginkEmit('feedback', {rating: 'down', reason: rb.getAttribute('data-reason'), chars: text.length});
        r.parentNode.removeChild(r); thanks(bar);
      });
      setTimeout(function () {                       // no reason picked -> still count the thumbs down
        if (r.parentNode) { ginkEmit('feedback', {rating: 'down', reason: '', chars: text.length}); r.parentNode.removeChild(r); thanks(bar); }
      }, 20000);
    }
  }, true);
  function thanks(bar) {
    var t = document.createElement('span'); t.className = 'thanks'; t.textContent = 'Thanks for the feedback';
    bar.appendChild(t); setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); bar.classList.remove('open'); }, 2500);
  }

  // ---- code blocks: language dot, line numbers, wrap, collapse, copy/save that work in the app ----
  var LANG_COLORS = {python: '#3572A5', py: '#3572A5', javascript: '#F1E05A', js: '#F1E05A', typescript: '#3178C6', ts: '#3178C6',
    html: '#E34C26', css: '#563D7C', java: '#B07219', kotlin: '#A97BFF', swift: '#F05138', go: '#00ADD8', rust: '#DEA584',
    c: '#555555', cpp: '#F34B7D', 'c++': '#F34B7D', csharp: '#178600', cs: '#178600', php: '#4F5D95', ruby: '#701516', sql: '#E38C00',
    bash: '#89E051', sh: '#89E051', shell: '#89E051', json: '#8BC34A', yaml: '#CB171E', dart: '#00B4AB', r: '#198CE7'};
  var CODE_ICONS = {
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    save: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7.5 10.5L12 15l4.5-4.5"/><path d="M5 19h14"/></svg>',
    wrap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M4 12h13a3 3 0 0 1 0 6h-4M4 17h5"/><path d="M15 16l-2 2 2 2"/></svg>'
  };
  function codeText(block) { var c = block.querySelector('pre code') || block.querySelector('pre'); return c ? (c.innerText || c.textContent || '') : ''; }
  function enhanceCodeBlocks(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll('.code-block:not([data-enh])'), function (block) {
      block.setAttribute('data-enh', '1');
      var bar = block.querySelector('.code-block-bar'), label = block.querySelector('.code-block-label');
      var lang = (label.textContent || '').trim().toLowerCase(), isFile = lang.indexOf('.') > 0;
      var key = isFile ? lang.split('.').pop() : lang;
      var dot = document.createElement('span'); dot.className = 'ldot'; dot.style.background = LANG_COLORS[key] || '#7D857B';
      label.insertBefore(dot, label.firstChild);
      Array.prototype.forEach.call(bar.querySelectorAll('button'), function (b) { b.parentNode.removeChild(b); });
      bar.insertAdjacentHTML('beforeend',
        '<button data-code="wrap" title="Wrap long lines">' + CODE_ICONS.wrap + 'Wrap</button>' +
        '<button data-code="save" title="Save to a file">' + CODE_ICONS.save + 'Save</button>' +
        '<button data-code="copy" title="Copy code">' + CODE_ICONS.copy + 'Copy</button>');
      var text = codeText(block).replace(/\n$/, ''), n = text ? text.split('\n').length : 0;
      var body = block.querySelector('.code-block-body');
      if (n > 1 && body) {
        var lns = document.createElement('div'); lns.className = 'lns';
        var nums = []; for (var i = 1; i <= n; i++) nums.push(i);
        lns.textContent = nums.join('\n'); body.insertBefore(lns, body.firstChild);
      }
      if (n > 24) {
        block.classList.add('collapsed');
        var more = document.createElement('button'); more.className = 'code-more';
        more.textContent = 'Show all ' + n + ' lines'; block.appendChild(more);
        more.addEventListener('click', function () {
          var c = block.classList.toggle('collapsed'); more.textContent = c ? 'Show all ' + n + ' lines' : 'Show less';
        });
      }
    });
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('.code-block-bar button[data-code]'); if (!b) return;
    e.preventDefault(); e.stopPropagation();
    var block = b.closest('.code-block'), what = b.getAttribute('data-code');
    if (what === 'copy') {
      copyText(codeText(block), function () { b.innerHTML = CODE_ICONS.check + 'Copied'; b.classList.add('on');
        setTimeout(function () { b.innerHTML = CODE_ICONS.copy + 'Copy'; b.classList.remove('on'); }, 1600); });
    } else if (what === 'wrap') {
      b.classList.toggle('on', block.classList.toggle('wrap'));
    } else if (what === 'save') {
      var label = (block.querySelector('.code-block-label').textContent || '').trim();
      var ext = {python: 'py', javascript: 'js', typescript: 'ts', html: 'html', css: 'css', java: 'java', kotlin: 'kt',
                 swift: 'swift', go: 'go', rust: 'rs', c: 'c', cpp: 'cpp', csharp: 'cs', php: 'php', ruby: 'rb', sql: 'sql',
                 bash: 'sh', shell: 'sh', json: 'json', yaml: 'yml', dart: 'dart', r: 'r'}[label.toLowerCase()];
      ginkEmit('save_code', {name: label.indexOf('.') > 0 ? label : 'gink-code.' + (ext || 'txt'), code: codeText(block)});
    }
  }, true);
  // the older inline handlers (still in replies being streamed) use the same working paths
  function copyCodeBlock(button) { var b = button.closest('.code-block'); copyText(codeText(b), function () { button.innerText = 'Copied'; setTimeout(function () { button.innerText = 'Copy'; }, 1500); }); }
  function downloadCodeBlock(button) { var b = button.closest('.code-block'), l = b.querySelector('.code-block-label').innerText.trim();
    ginkEmit('save_code', {name: l.indexOf('.') > 0 ? l : 'gink-code.txt', code: codeText(b)}); }

  // ---- file cards: links like [📕 Plan.pdf · 27 KB](gink://file/Plan.pdf) ----
  function upgradeFileLinks(root) {
    if (!root) return;
    Array.prototype.slice.call(root.querySelectorAll('a[href^="gink://file/"]')).forEach(function (a) {
      var name = decodeURIComponent(a.getAttribute('href').slice('gink://file/'.length));
      var label = (a.textContent || '').replace(/^\S+\s/, ''), size = (label.split(' \u00b7 ')[1] || '');
      var ext = (name.split('.').pop() || '').toLowerCase(), isImg = ext === 'png' || ext === 'jpg' || ext === 'jpeg';
      var card = document.createElement('div');
      if (isImg) {
        card.className = 'icard';
        card.innerHTML = '<div class="ipic" title="Open"></div><div class="ibar"><span class="fname"></span>' +
          '<button data-f="open">Open</button><button data-f="save">Save as\u2026</button></div>';
        card.querySelector('.ipic').setAttribute('data-thumb-for', name);
        ginkEmit('file_thumb', name);
      } else {
        var cls = ['pdf', 'docx', 'xlsx', 'csv'].indexOf(ext) >= 0 ? ext : 'other';
        card.className = 'fcard';
        card.innerHTML = '<div class="ficon2 ' + cls + '"></div><div class="fmeta"><div class="fname"></div><div class="fsize"></div></div>' +
          '<button data-f="open" class="primary">Open</button><button data-f="save">Save as\u2026</button>';
        card.querySelector('.ficon2').textContent = ext.toUpperCase().slice(0, 4);
        card.querySelector('.fsize').textContent = size + (size ? ' \u00b7 ' : '') + ({pdf: 'PDF document', docx: 'Word document', xlsx: 'Excel spreadsheet', csv: 'Spreadsheet (CSV)', md: 'Markdown', html: 'Web page', txt: 'Text'}[ext] || 'File');
      }
      card.setAttribute('data-file', name);
      card.querySelector('.fname').textContent = name;
      var p = a.parentNode, host = (p && p.tagName === 'P' && p.textContent.trim() === (a.textContent || '').trim()) ? p : a;
      host.parentNode.replaceChild(card, host);
    });
  }
  function setFileThumb(name, dataUrl) {
    if (!dataUrl) return;                       // no preview -> keep the placeholder, never a broken image
    Array.prototype.forEach.call(document.querySelectorAll('[data-thumb-for]'), function (el) {
      if (el.getAttribute('data-thumb-for') !== name || el.querySelector('img')) return;
      var im = document.createElement('img'); im.src = dataUrl; im.alt = name; el.appendChild(im);
    });
  }
  document.addEventListener('click', function (e) {
    var card = e.target.closest && e.target.closest('[data-file]'); if (!card) return;
    var b = e.target.closest('button'), pic = e.target.closest('.ipic');
    if (!b && !pic) return;
    e.preventDefault(); e.stopPropagation();
    ginkEmit(b && b.getAttribute('data-f') === 'save' ? 'file_save' : 'file_open', card.getAttribute('data-file'));
  }, true);

  // ---- sidebar chat menu: Rename / Pin / Export ----
  document.addEventListener('click', function () {
    var m = document.getElementById('row-menu');
    if (!m || m.classList.contains('hidden') || !rowMenuFor) return;
    var s = sessions.filter(function (x) { return x.id === rowMenuFor; })[0];
    document.querySelector('#row-pin span').textContent = s && s.pinned ? 'Unpin' : 'Pin';
  });
  document.getElementById('row-menu').addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b || !rowMenuFor) return;
    var what = b.getAttribute('data-row'), id = rowMenuFor;
    var s = sessions.filter(function (x) { return x.id === id; })[0] || {};
    if (what === 'rename') { closeMenus(); promptRename(id, s.title || ''); }
    else if (what === 'pin') { closeMenus(); s.pinned = !s.pinned; renderRecents(); ginkEmit('pin_session', {id: id, pinned: !!s.pinned}); }
    else if (what === 'archive') { closeMenus(); ginkEmit('archive_session', {id: id, archived: true}); }
    else if (what === 'share') { closeMenus(); ginkEmit('share_session', id); }
    else if (what === 'export') { closeMenus(); ginkEmit('export_session', id); }
  });
  function promptRename(id, current) {
    var back = document.getElementById('modal-back'), modal = back.querySelector('.modal'), old = modal.innerHTML;
    modal.innerHTML = '<h3>Rename chat</h3><input class="s-input" id="rn-input" style="width:100%" maxlength="120">' +
      '<div class="actions"><button class="pill ghost" id="rn-cancel">Cancel</button><button class="pill" id="rn-ok" style="background:var(--accent);color:var(--on-accent);border:1px solid var(--accent)">Save</button></div>';
    var inp = modal.querySelector('#rn-input'); inp.value = current;
    function done() { back.classList.remove('open'); modal.innerHTML = old; rebindDeleteModal(); }
    function save() {
      var t = inp.value.trim(); if (!t) return;
      sessions.forEach(function (x) { if (x.id === id) x.title = t; }); renderRecents();
      ginkEmit('rename_session', {id: id, title: t}); done();
    }
    modal.querySelector('#rn-cancel').addEventListener('click', done);
    modal.querySelector('#rn-ok').addEventListener('click', save);
    inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); save(); } if (e.key === 'Escape') done(); });
    back.classList.add('open'); setTimeout(function () { inp.focus(); inp.select(); }, 30);
  }

  // ---- jump to latest ----
  function nearBottom() { return (window.innerHeight + window.scrollY) >= document.body.scrollHeight - 220; }
  window.addEventListener('scroll', function () {
    document.getElementById('jump').classList.toggle('show', !nearBottom() && !document.body.classList.contains('home'));
  });
  document.getElementById('jump').addEventListener('click', function () { scrollDown(); this.classList.remove('show'); });

  // ---- automatic history: drafts ----
  function setComposerText(text) {
    var t = cin(); t.value = text || ''; autoGrow(); refreshSend();
  }
  var draftTimer = null;
  document.addEventListener('DOMContentLoaded', function () {
    cin().addEventListener('input', function () {
      clearTimeout(draftTimer);
      draftTimer = setTimeout(function () { draftTimer = null; ginkEmit('draft', cin().value); }, 600);
    });
  });
  // switching chats: save the draft first, so the last few keystrokes aren't lost
  var _emitRaw = ginkEmit;
  ginkEmit = function (type, value) {
    if ((type === 'select_session' || type === 'new_chat') && draftTimer) {
      clearTimeout(draftTimer); draftTimer = null; _emitRaw('draft', cin().value);
    }
    _emitRaw(type, value);
  };

  // ---- keyboard shortcuts (listed in Settings -> Keyboard) ----
  document.addEventListener('keydown', function (e) {
    var mod = e.metaKey || e.ctrlKey, k = (e.key || '').toLowerCase();
    var typing = /input|textarea|select/i.test((e.target && e.target.tagName) || '');
    var overlay = (typeof VC !== 'undefined' && VC.open) || (typeof S !== 'undefined' && S.open);
    if (mod && e.shiftKey && k === 'o') { e.preventDefault(); ginkEmit('new_chat'); }
    else if (mod && e.shiftKey && k === 'v') { e.preventDefault(); if (!overlay) voiceButton(); }
    else if (mod && e.shiftKey && k === 'c') {
      e.preventDefault();
      var all = document.querySelectorAll('.row .assistant-text'), last = all.length ? all[all.length - 1] : null;
      if (last) copyText(replyText(last), function () { setStatus('Copied the last reply'); setTimeout(function () { setStatus(''); }, 1800); });
    }
    else if (mod && !e.shiftKey && (k === '.' || k === '\\')) { e.preventDefault(); setPinned(!document.body.classList.contains('pinned')); }
    else if (mod && !e.shiftKey && k === 'k') {
      e.preventDefault(); setPinned(true); document.body.classList.add('searching');
      setTimeout(function () { document.getElementById('side-q').focus(); }, 250);
    } else if (!mod && e.key === '/' && !typing && KB.single_keys && !overlay) { e.preventDefault(); cin().focus(); }
    else if (e.key === 'Escape' && !overlay && typeof composerBusy !== 'undefined' && (composerBusy || speakingNow)) {
      var st = document.getElementById('stop'); if (st && st.style.display !== 'none') { e.preventDefault(); st.click(); }
    }
  });
  // Shared chat links: a small window with the public link, Copy and Open
  window.showShareLink = function (url, title) {
    var old = document.getElementById('share-dlg'); if (old) old.remove();
    var d = document.createElement('div'); d.id = 'share-dlg'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-label', 'Shared link');
    d.style.cssText = 'position:fixed;inset:0;z-index:10000;display:grid;place-items:center;background:rgba(0,0,0,.35)';
    var box = document.createElement('div');
    box.style.cssText = 'width:min(460px,92vw);background:var(--surface);color:var(--text-main);border-radius:16px;padding:20px;' +
      'box-shadow:0 12px 40px rgba(0,0,0,.25);font:14.5px/1.5 system-ui,sans-serif';
    var h = document.createElement('h3'); h.textContent = 'Link created'; h.style.margin = '0 0 6px';
    var p = document.createElement('p'); p.style.cssText = 'margin:0 0 12px;opacity:.75';
    p.textContent = 'Anyone with this link can read a snapshot of \u201c' + (title || 'this chat') + '\u201d. Later messages aren\u2019t included. Manage links in Settings > Privacy.';
    var input = document.createElement('input'); input.readOnly = true; input.value = url;
    input.style.cssText = 'width:100%;box-sizing:border-box;padding:9px 11px;border-radius:10px;border:1px solid var(--border);background:transparent;color:inherit;font:inherit';
    var row = document.createElement('div'); row.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;margin-top:14px';
    function btn(text, primary, fn) {
      var b = document.createElement('button'); b.textContent = text; b.onclick = fn;
      b.style.cssText = 'font:inherit;font-weight:650;border:0;border-radius:999px;padding:8px 16px;cursor:pointer;' +
        (primary ? 'background:var(--text-main);color:var(--surface)' : 'background:transparent;color:inherit;box-shadow:inset 0 0 0 1.5px var(--border)');
      row.appendChild(b); return b;
    }
    btn('Close', false, function () { d.remove(); });
    btn('Open', false, function () { ginkEmit('open_url', url); });
    var copy = btn('Copy link', true, function () {
      input.select();
      var ok = function () { copy.textContent = 'Copied'; };
      if (navigator.clipboard) navigator.clipboard.writeText(url).then(ok, function () { try { document.execCommand('copy'); ok(); } catch (e) {} });
      else { try { document.execCommand('copy'); ok(); } catch (e) {} }
    });
    if (!url) {                                   // a problem instead of a link: explain it, Close only
      h.textContent = 'Couldn\u2019t create the link'; p.textContent = title || 'Please try again.';
      input.style.display = 'none'; row.querySelectorAll('button').forEach(function (b, i) { if (i) b.remove(); });
    }
    box.appendChild(h); box.appendChild(p); box.appendChild(input); box.appendChild(row); d.appendChild(box);
    d.onclick = function (e) { if (e.target === d) d.remove(); };
    document.body.appendChild(d); input.select();
  };
  // ---- the "/" prompt menu: built-in prompts + the person's own (Settings > Personalization > Prompt library)
  var SLASH_BUILTIN = [
    ['Summarize', 'Summarize this in a few short points:\n\n'],
    ['Fix grammar', 'Fix the grammar and spelling, keeping my meaning and tone:\n\n'],
    ['Translate to French', 'Translate this into French:\n\n'],
    ['Translate to English', 'Translate this into English:\n\n'],
    ['Explain simply', 'Explain this simply, as if I were 12:\n\n'],
    ['Write an email', 'Write a short, polite email that says:\n\n'],
    ['Help me reply', 'Help me reply to this message:\n\n'],
    ['Give me ideas', 'Give me 10 ideas for:\n\n'],
    ['Quiz me', 'Quiz me with 5 questions about:\n\n']
  ];
  var MY_PROMPTS = [];
  window.setPrompts = function (list) { MY_PROMPTS = (list || []).map(function (p) { return [String(p.text).split('\n')[0].slice(0, 48), String(p.text) + (/\s$/.test(p.text) ? '' : ' ')]; }); };
  var slash = { el: null, items: [], idx: 0 };
  function slashBox() {
    if (slash.el) return slash.el;
    var m = document.createElement('div'); m.id = 'slash-menu'; m.setAttribute('role', 'listbox'); m.setAttribute('aria-label', 'Prompts');
    m.style.cssText = 'position:absolute;left:0;right:0;bottom:calc(100% + 8px);max-height:300px;overflow:auto;display:none;z-index:40;' +
      'background:var(--surface);color:var(--text-main);border:1px solid var(--border);border-radius:14px;padding:6px;box-shadow:0 10px 30px rgba(0,0,0,.15)';
    var host = document.getElementById('composer'); host.style.position = host.style.position || 'relative'; host.appendChild(m);
    slash.el = m; return m;
  }
  function slashClose() { if (slash.el) slash.el.style.display = 'none'; slash.items = []; }
  function slashOpen(query) {
    var q = query.toLowerCase(), m = slashBox();
    var mine = MY_PROMPTS.map(function (p) { return p.concat(['Yours']); });
    slash.items = mine.concat(SLASH_BUILTIN).filter(function (p) { return !q || p[0].toLowerCase().indexOf(q) >= 0 || p[1].toLowerCase().indexOf(q) >= 0; }).slice(0, 12);
    if (!slash.items.length) return slashClose();
    slash.idx = Math.min(slash.idx, slash.items.length - 1);
    m.innerHTML = '';
    slash.items.forEach(function (p, i) {
      var row = document.createElement('div'); row.setAttribute('role', 'option'); row.setAttribute('aria-selected', i === slash.idx ? 'true' : 'false');
      row.style.cssText = 'padding:7px 10px;border-radius:9px;cursor:pointer;display:flex;gap:10px;align-items:baseline;' + (i === slash.idx ? 'background:var(--elevated)' : '');
      var t = document.createElement('b'); t.textContent = p[0]; t.style.cssText = 'font-weight:650;white-space:nowrap';
      var d = document.createElement('span'); d.textContent = p[2] ? 'your prompt' : p[1].replace(/\s+/g, ' ').trim().slice(0, 60);
      d.style.cssText = 'color:var(--text-muted);font-size:.9em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
      row.appendChild(t); row.appendChild(d);
      row.addEventListener('mousedown', function (e) { e.preventDefault(); slashPick(i); });
      m.appendChild(row);
    });
    m.style.display = 'block';
  }
  function slashPick(i) {
    var p = slash.items[i], box = document.getElementById('cin'); if (!p || !box) return;
    box.value = p[1]; slashClose(); box.focus(); box.setSelectionRange(box.value.length, box.value.length);
    box.dispatchEvent(new Event('input', { bubbles: true }));
  }
  document.addEventListener('input', function (e) {
    if (!e.target || e.target.id !== 'cin') return;
    var v = e.target.value, mt = /^\/([^\n]{0,40})$/.exec(v);
    if (mt) { slash.idx = 0; slashOpen(mt[1]); } else slashClose();
  });
  document.addEventListener('keydown', function (e) {                // before the normal Enter-to-send
    if (!slash.items.length || !e.target || e.target.id !== 'cin') return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault(); slash.idx = (slash.idx + (e.key === 'ArrowDown' ? 1 : -1) + slash.items.length) % slash.items.length;
      slashOpen(/^\/(.*)$/.exec(e.target.value)[1]);
    } else if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); e.stopImmediatePropagation(); slashPick(slash.idx); }
    else if (e.key === 'Escape') { e.preventDefault(); slashClose(); }
  }, true);
  document.addEventListener('click', function (e) { if (slash.el && !slash.el.contains(e.target) && e.target.id !== 'cin') slashClose(); });
"""


def inject(page: str) -> str:
    import json as _json
    html = HTML
    for name in ICONS:
        html = html.replace(f"__I_{name}__", icon(name, 18))
    page = page.replace("__ICON_RENAME__", icon("rename")).replace("__ICON_PIN__", icon("pin")) \
               .replace("__ICON_EXPORT__", icon("export"))
    i = page.index("</style>")
    page = page[:i] + CSS + page[i:]
    page = page.replace("<script>", html + "\n<script>", 1)
    i = page.rindex("</script>")
    from .logo_svg import logo_svg
    js = JS.replace("__GICONS__", _json.dumps({k: icon(k) for k in ICONS})).replace("__GINK_LOGO__", _json.dumps(logo_svg(104)))
    return page[:i] + js + page[i:]
