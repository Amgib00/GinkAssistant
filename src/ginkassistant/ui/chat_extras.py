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
  /* while the steps list shows the current step, the spinner's label would only repeat it */
  .gsteps:not(.done) ~ .gink-spin { display: none; }
  /* one animated mark at a time: with the working logo below, the small spinning one beside the label goes */
  .gink-spin.with-logo .gink-spinner { display: none; }
  .gink-spin.with-logo .spin-label { margin-left: 0; }
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
  /* the working mark: compact and in line with the reply (it used to be 104px in the middle of the page) */
  .work-logo { width: 40px; height: 40px; margin: 14px 0 0; }
  .work-logo svg { display: block; width: 40px; height: 40px; overflow: visible;
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
  /* ---------- code blocks (0.1.160): calm and readable, in the page's own light or dark colours ----------
     The language (or the file's name) at the top left, small icon buttons at the top right (wrap, save, copy),
     the code under it, coloured by services/markdown_render.py. Long code folds, with "Show all N lines". */
  :root { --code-bg: #F7F7F4; --code-border: #E3E6DE; --code-text: #1F2420; --code-muted: #687066; --code-hover: rgba(28, 33, 29, 0.07); }
  body.theme-dark { --code-bg: #181C19; --code-border: #2B312C; --code-text: #E2E8E1; --code-muted: #98A196; --code-hover: rgba(255, 255, 255, 0.08); }
  .code-block { position: relative; margin: 14px 0 !important; max-width: 100%; overflow: hidden;
    background: var(--code-bg) !important; border: 1px solid var(--code-border) !important; border-radius: 12px !important; }
  .code-block-bar { display: flex; align-items: center; gap: 2px; padding: 7px 7px 0 14px !important;
    background: transparent !important; border: 0 !important; min-height: 36px; }
  .code-block-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    color: var(--code-muted) !important; font-family: inherit !important; font-size: 12.5px !important; font-weight: 500; letter-spacing: 0.01em; }
  .code-block-bar button { flex: none; width: 30px; height: 30px; padding: 0 !important; margin: 0; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center; border: 0 !important; border-radius: 8px !important;
    background: transparent !important; color: var(--code-muted) !important; font: inherit; }
  .code-block-bar button:hover { background: var(--code-hover) !important; color: var(--code-text) !important; }
  .code-block-bar button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .code-block-bar button svg { width: 16px; height: 16px; }
  .code-block-bar button.on { color: var(--accent) !important; }
  .code-block-body { position: relative; display: flex; background: transparent; }
  .code-block-body .codehilite { flex: 1; min-width: 0; background: transparent !important; }
  .code-block-body pre { margin: 0 !important; padding: 4px 16px 15px !important; background: transparent !important;
    color: var(--code-text) !important; overflow-x: auto; tab-size: 4; -moz-tab-size: 4;
    font: 13px/1.62 ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace !important; }
  .code-block-body pre code { font: inherit !important; background: none !important; padding: 0 !important; border: 0 !important; color: inherit; }
  .code-block-body .lns { flex: none; padding: 4px 0 15px 14px; padding-right: 2px; text-align: right; white-space: pre; color: var(--code-muted);
    opacity: 0.7; font: 13px/1.62 ui-monospace, 'SF Mono', SFMono-Regular, Menlo, Consolas, monospace; user-select: none; -webkit-user-select: none; }
  .code-block.wrap pre { white-space: pre-wrap !important; overflow-wrap: anywhere; }
  .code-block.wrap .lns { display: none; }
  .code-block.collapsed .code-block-body { max-height: 380px; overflow: hidden; }
  .code-block.collapsed .code-block-body::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 72px;
    background: linear-gradient(rgba(0, 0, 0, 0), var(--code-bg)); pointer-events: none; }
  .code-more { display: block; width: 100%; border: 0; border-top: 1px solid var(--code-border); background: transparent;
    color: var(--code-muted); font: inherit; font-size: 12.5px; padding: 9px; cursor: pointer; }
  .code-more:hover { color: var(--code-text); background: var(--code-hover); }
  .code-tip { position: absolute; top: 40px; right: 8px; z-index: 2; padding: 3px 8px; border-radius: 6px; font-size: 11.5px; font-weight: 600;
    background: var(--code-text); color: var(--code-bg); pointer-events: none; opacity: 0; transition: opacity 0.15s; }
  .code-tip.show { opacity: 1; }
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
  /* ---------- sidebar: the day headings (Pinned, Today, Yesterday...) -- small, plain, sentence case ---------- */
  .recents-head { font-size: 12.5px; font-weight: 500; color: var(--text-muted); padding: 16px 10px 6px; }
  .recents-head:first-child { padding-top: 10px; }
  #row-menu button svg { width: 16px; height: 16px; margin-right: 10px; color: var(--text-muted); flex: none; }
  /* ---------- jump to latest ---------- */
  #jump {                       /* inside the shell (moved there on load): just above the composer, however tall it is */
    position: absolute; left: 50%; bottom: calc(var(--composer-h, 140px) + 10px); transform: translateX(-50%) translateY(10px); z-index: 25;
    width: 36px; height: 36px; border-radius: 50%; border: 1px solid var(--border); background: var(--bg);
    color: var(--text-main); box-shadow: 0 4px 14px rgba(0,0,0,0.12); cursor: pointer; opacity: 0; pointer-events: none;
    display: flex; align-items: center; justify-content: center; transition: opacity 0.2s, transform 0.2s;
  }
  #jump.show { opacity: 1; pointer-events: auto; transform: translateX(-50%); }
  body.home #jump { display: none; }
  /* Question cards (Gink asks with tappable choices) */
  .qcard { border: 1px solid var(--border); border-radius: 16px; background: var(--surface); margin: 10px 0; overflow: hidden; max-width: 640px; }
  .qcard .qq { font-weight: 650; padding: 14px 16px 6px; }
  .qcard .qo { display: block; width: 100%; text-align: left; background: none; border: 0; border-top: 1px solid var(--border);
               padding: 12px 16px; font: inherit; color: var(--text-main); cursor: pointer; }
  .qcard .qo:hover, .qcard .qo.on { background: var(--elevated); }
  .qcard .qo.on { font-weight: 650; }
  .qcard .qe { display: flex; gap: 10px; align-items: center; border-top: 1px solid var(--border); padding: 8px 16px; }
  .qcard .qe input { flex: 1; border: 0; outline: none; background: transparent; font: inherit; color: var(--text-main); padding: 4px 0; }
  .qcard .qf { display: flex; align-items: center; gap: 10px; border-top: 1px solid var(--border); padding: 8px 12px; color: var(--text-muted); }
  .qcard .qf button { background: none; border: 0; font: inherit; color: var(--text-main); cursor: pointer; padding: 4px 8px; border-radius: 8px; }
  .qcard .qf button:disabled { opacity: .35; cursor: default; }
  .qcard .qsend { width: 32px; height: 32px; border-radius: 50% !important; background: var(--text-main) !important; color: var(--surface) !important; }
  .qcard.done .qo, .qcard.done .qe, .qcard.done .qf .qsend, .qcard.done .qf .qskip { display: none; }
  .qcard .qans { padding: 0 16px 12px; color: var(--text-muted); }
  /* "Recalled memory" above an answer */
  .recalled { display: flex; gap: 8px; align-items: baseline; color: var(--text-muted); font-size: 13.5px; margin: 6px 0 2px; cursor: pointer; }
  .recalled b { color: var(--text-main); font-weight: 600; } .recalled .rm { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 520px; }
  .recalled.open .rm { white-space: normal; }
  /* The code viewer: long code in a panel on the right (Copy / Download, Expand, Close, line numbers) */
  #codeview { position: fixed; top: 0; right: 0; bottom: 0; width: min(50vw, 780px); z-index: 60; display: flex; flex-direction: column;
              background: var(--surface); border-left: 1px solid var(--border); box-shadow: -8px 0 30px rgba(0,0,0,.08); }
  #codeview.wide { width: 100vw; }
  #codeview .cvh { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-bottom: 1px solid var(--border); }
  #codeview .cvt { font-weight: 650; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #codeview .cvb { font-size: 11px; font-weight: 700; color: var(--text-muted); letter-spacing: .04em; }
  #codeview .cvg { flex: 1; }
  #codeview .cvh button { border: 1px solid var(--border); background: var(--bg); color: var(--text-main); font: inherit; font-size: 13px;
                          border-radius: 8px; padding: 5px 10px; cursor: pointer; }
  #codeview .cvcopy { border-radius: 8px 0 0 8px !important; } #codeview .cvmore { border-radius: 0 8px 8px 0 !important; margin-left: -9px; padding: 5px 7px !important; }
  #codeview .cvicon { border: 0 !important; background: transparent !important; font-size: 17px !important; padding: 4px 7px !important; }
  #codeview .cvmenu { position: absolute; top: 46px; right: 70px; background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
                      box-shadow: 0 10px 30px rgba(0,0,0,.15); padding: 4px; z-index: 2; }
  #codeview .cvmenu button { display: block; width: 100%; text-align: left; border: 0; background: none; padding: 7px 12px; }
  #codeview .cvmenu button:hover { background: var(--elevated); }
  #codeview .cvbody { flex: 1; overflow: auto; }
  #codeview .cvframe { flex: 1; width: 100%; border: 0; background: #fff; }
  #codeview .cvpub { background: var(--text-main) !important; color: var(--surface) !important; border-color: var(--text-main) !important; font-weight: 600; }
  #codeview .cvpubbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 12px; font-size: 13px;
                        border-bottom: 1px solid var(--border); background: var(--elevated); }
  #codeview .cvpubbar.err { color: var(--danger, #c0392b); }
  #codeview .cvpubbar .cvurl { font-family: ui-monospace, Menlo, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 55%; }
  #codeview .cvpubbar button { border: 1px solid var(--border); background: var(--surface); color: var(--text-main); border-radius: 8px; padding: 3px 9px; font: inherit; cursor: pointer; }
  #codeview .cvtabs { display: inline-flex; margin-left: 10px; border: 1px solid var(--border); border-radius: 9px; overflow: hidden; }
  #codeview .cvtabs button { border: 0 !important; border-radius: 0 !important; background: transparent !important; padding: 4px 11px !important; color: var(--text-muted) !important; }
  #codeview .cvtabs button.on { background: var(--elevated) !important; color: var(--text-main) !important; font-weight: 600; }
  #codeview [hidden] { display: none !important; }
  #codeview .cvbody .code-block { margin: 0; border: 0; border-radius: 0; }
  #codeview .cvbody code { font-size: inherit; line-height: inherit; }   /* same line height as the numbers: no drift */
  #codeview .cvbody .code-block-body { border: 0; border-radius: 0; max-height: none !important; }
  body.viewer-open #shell { right: min(50vw, 780px); }
  @media (max-width: 899px) { #codeview { width: 100vw; } body.viewer-open #shell { right: 0; } }
  /* Artifacts (0.1.161): the finished things Gink makes -- a card in the chat, opened in the viewer */
  .artcard { display: flex; align-items: center; gap: 12px; margin: 10px 0; padding: 10px 12px 10px 10px; max-width: 520px;
             border: 1px solid var(--border); border-radius: 14px; background: var(--surface); cursor: pointer; color: var(--text-main);
             transition: border-color .15s ease, box-shadow .15s ease; }
  .artcard:hover { border-color: var(--text-muted); box-shadow: 0 2px 12px rgba(0,0,0,.07); }
  .artcard:focus-visible { outline: 2px solid var(--accent, #3F8212); outline-offset: 2px; }
  .artcard.on { border-color: var(--accent, #3F8212); box-shadow: 0 0 0 1px var(--accent, #3F8212); }
  .artcard .arti { flex: none; width: 44px; height: 44px; border-radius: 11px; display: flex; align-items: center; justify-content: center;
                   background: var(--elevated); color: var(--accent, #3F8212); }
  .artcard .artm { min-width: 0; flex: 1; }
  .artcard .artt { font-weight: 650; font-size: 14.5px; line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .artcard .artk { display: flex; align-items: center; gap: 6px; margin-top: 2px; font-size: 12.5px; color: var(--text-muted); }
  .artcard .artv { font-size: 11px; font-weight: 700; padding: 0 6px; border-radius: 6px; background: var(--elevated); color: var(--text-main); }
  .artcard .arto { flex: none; font-size: 13px; font-weight: 600; padding: 6px 12px; border-radius: 9px; border: 1px solid var(--border); }
  /* Scheduled tasks (0.1.161): the AI's ```schedule block becomes this card; the server runs the task at its time */
  .tskcard { margin: 10px 0; padding: 12px 14px; max-width: 520px; border: 1px solid var(--border); border-radius: 14px;
             background: var(--surface); color: var(--text-main); }
  .tskcard .tsk-top { display: flex; align-items: flex-start; gap: 12px; }
  .tskcard .tsk-ic { flex: none; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
                     background: var(--elevated); color: var(--accent, #3F8212); }
  .tskcard .tsk-m { min-width: 0; flex: 1; }
  .tskcard .tsk-t { font-weight: 650; font-size: 14.5px; line-height: 1.3; overflow-wrap: anywhere; }
  .tskcard .tsk-w { margin-top: 2px; font-size: 12.5px; color: var(--text-muted); }
  .tskcard .tsk-s { flex: none; display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600;
                    padding: 3px 9px; border-radius: 999px; background: var(--elevated); color: var(--text-muted); white-space: nowrap; }
  .tskcard .tsk-s i { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .tskcard.on .tsk-s { color: var(--accent, #3F8212); background: var(--accent-soft, #EEF8E1); }
  .tskcard.err .tsk-s { color: var(--danger, #C93B32); }
  .tskcard .tsk-q { margin: 10px 0 0 52px; font-size: 13.5px; line-height: 1.45; color: var(--text-main);
                    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .tskcard .tsk-n { margin: 8px 0 0 52px; font-size: 12.5px; color: var(--text-muted); }
  .tskcard.err .tsk-n { color: var(--danger, #C93B32); }
  .tskcard .tsk-a { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0 0 52px; }
  .tskcard .tsk-a button { font: inherit; font-size: 13px; font-weight: 600; padding: 6px 12px; border-radius: 9px; cursor: pointer;
                           border: 1px solid var(--border); background: transparent; color: var(--text-main); }
  .tskcard .tsk-a button.primary { background: var(--accent, #3F8212); border-color: var(--accent, #3F8212); color: var(--on-accent, #fff); }
  .tskcard .tsk-a button:hover { border-color: var(--text-muted); }
  .tskcard .tsk-a button:focus-visible { outline: 2px solid var(--accent, #3F8212); outline-offset: 2px; }
  .tskcard .tsk-a button[disabled] { opacity: .5; cursor: default; }
  @media (max-width: 480px) { .tskcard .tsk-q, .tskcard .tsk-n, .tskcard .tsk-a { margin-left: 0; } }
  #codeview .cvver { display: inline-flex; align-items: center; gap: 2px; font-size: 12.5px; color: var(--text-muted); white-space: nowrap; }
  #codeview .cvver button { border: 0 !important; background: transparent !important; padding: 2px 6px !important; font-size: 16px !important; }
  #codeview .cvver button:disabled { opacity: .35; cursor: default; }
  #codeview .cvdoc { flex: 1; overflow: auto; padding: 28px clamp(18px, 5vw, 56px) 56px; }
  #codeview .cvdoc-in { max-width: 720px; margin: 0 auto; font-size: 15.5px; line-height: 1.65; }
  #codeview .cvdoc-in h1 { font-size: 1.7em; line-height: 1.2; margin: 0 0 .6em; } #codeview .cvdoc-in h2 { font-size: 1.3em; margin: 1.4em 0 .5em; }
  #codeview .cvimg { flex: 1; overflow: auto; display: flex; align-items: center; justify-content: center; padding: 24px;
                     background: repeating-conic-gradient(var(--elevated) 0 25%, transparent 0 50%) 0 0 / 20px 20px; }
  #codeview .cvimg img { max-width: 100%; max-height: 100%; }
  /* Sources: a button in the answer's action row, opening the list (official ones first, with a badge) */
  .ga.gsrc { width: auto; display: inline-flex; align-items: center; gap: 7px; padding: 0 10px 0 6px; border-radius: 999px;
             font-size: 13px; font-weight: 600; color: var(--text-main); }
  .gsrc .stack { display: inline-flex; position: relative; }
  .gsrc .stack span { width: 22px; height: 22px; border-radius: 50%; display: inline-grid; place-items: center; font-size: 11px;
                      font-weight: 700; color: #fff; margin-left: -7px; box-shadow: 0 0 0 2px var(--surface); position: relative; overflow: hidden; }
  .gsrc .stack span:first-child { margin-left: 0; }
  /* real logos (0.1.156): the site's own icon covers the letter once it arrives (GET /icon/{host} on Gink's server) */
  .gsrc .stack span img, .gsources .si img { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: contain;
                      opacity: 0; transition: opacity 0.2s; }
  .gsrc .stack span.logo, .gsources .si.logo { background: #fff !important; }
  .gsrc .stack span.logo { box-shadow: 0 0 0 2px var(--surface), inset 0 0 0 1px rgba(0, 0, 0, 0.08); }
  .gsrc .stack span.logo img { opacity: 1; padding: 3px; }
  .gsources .si.logo { box-shadow: inset 0 0 0 1px var(--border); }
  .gsources .si.logo img { opacity: 1; padding: 5px; }
  .gsrc .stack .logo b, .gsources .si.logo b { visibility: hidden; }
  /* the first source is official: a small green check on its logo, like a verified mark */
  .gsrc .stack .ok { position: absolute; left: 13px; bottom: -3px; width: 11px; height: 11px; border-radius: 50%; background: #1F9D55;
                     box-shadow: 0 0 0 1.5px var(--surface); display: grid; place-items: center; z-index: 2; }
  .gsrc .stack .ok svg { width: 7px; height: 7px; }
  .gsources { margin: 8px 0 4px; border: 1px solid var(--border); border-radius: 16px; padding: 6px; max-width: 560px; background: var(--surface);
              box-shadow: 0 8px 24px rgba(28, 33, 29, 0.06); animation: word-in 0.25s ease both; }
  .gsources a { display: flex; align-items: center; gap: 12px; padding: 8px 10px; border-radius: 11px; color: var(--text-main); text-decoration: none;
                border-bottom: 0; transition: background 0.15s; }
  .gsources a::after { content: none; }
  .gsources a + a { margin-top: 2px; }
  .gsources a:hover { background: var(--elevated); }
  .gsources .go { flex: none; width: 16px; height: 16px; color: var(--text-muted); opacity: 0.7; }
  .gsources a:hover .go { opacity: 1; color: var(--text-main); }
  .gsources .si { width: 28px; height: 28px; border-radius: 8px; flex: none; display: grid; place-items: center; color: #fff; font-weight: 700; font-size: 13px;
                  position: relative; overflow: hidden; }
  .gsources .st { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .gsources .st b { font-weight: 600; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .gsources .st small { color: var(--text-muted); font-size: 12px; }
  .gsources .off { flex: none; font-size: 11px; font-weight: 700; color: #1F6F3A; background: #DDF5E3; border-radius: 999px; padding: 3px 9px; }
  body.theme-dark .gsources .off { color: #9BE0AE; background: rgba(46, 158, 85, 0.18); }
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
    if (host && !host.querySelector('.work-logo')) host.appendChild(workLogo());   // the animated working mark
    var sp = host ? host.querySelector('.gink-spin') : null;
    if (sp) sp.classList.add('with-logo');            // one animated mark at a time (the small spinner hides)
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
    // the Sources button opens its own list: this listener runs first (capture) and stopping the click here
    // meant tapping "5 sources" did nothing (fixed in 0.1.156)
    if (b.classList.contains('gsrc')) return;
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

  // ---- code blocks: icon buttons (wrap, save, copy), long code folds, copy and save that work in the apps ----
  var CODE_ICONS = {
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    save: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7.5 10.5L12 15l4.5-4.5"/><path d="M5 19h14"/></svg>',
    wrap: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M4 12h13a3 3 0 0 1 0 6h-4M4 17h5"/><path d="M15 16l-2 2 2 2"/></svg>',
    open: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7"/></svg>'
  };
  function codeText(block) { var c = block.querySelector('pre code') || block.querySelector('pre'); return c ? (c.innerText || c.textContent || '') : ''; }
  function codeButton(what, title, icon) {
    return '<button type="button" data-code="' + what + '" title="' + title + '" aria-label="' + title + '">' + icon + '</button>';
  }
  function enhanceCodeBlocks(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll('.code-block:not([data-enh])'), function (block) {
      block.setAttribute('data-enh', '1');
      var bar = block.querySelector('.code-block-bar');
      Array.prototype.forEach.call(bar.querySelectorAll('button'), function (b) { b.parentNode.removeChild(b); });
      var text = codeText(block).replace(/\n$/, ''), n = text ? text.split('\n').length : 0;
      var wide = text.split('\n').some(function (l) { return l.length > 90; });
      bar.insertAdjacentHTML('beforeend',
        (wide ? codeButton('wrap', 'Wrap long lines', CODE_ICONS.wrap) : '') +
        (n >= 15 ? codeButton('open', 'Open in the code viewer', CODE_ICONS.open) : '') +
        codeButton('save', 'Save to a file', CODE_ICONS.save) + codeButton('copy', 'Copy code', CODE_ICONS.copy));
      if (n > 22) {
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
    if (what === 'open') { openCodeViewer(block); return; }
    if (what === 'copy') {
      copyText(codeText(block).replace(/\n$/, ''), function () {
        b.innerHTML = CODE_ICONS.check; b.classList.add('on'); b.setAttribute('aria-label', 'Copied');
        var tip = block.querySelector('.code-tip');
        if (!tip) { tip = document.createElement('span'); tip.className = 'code-tip'; tip.setAttribute('role', 'status'); block.appendChild(tip); }
        tip.textContent = 'Copied'; tip.classList.add('show');
        setTimeout(function () { b.innerHTML = CODE_ICONS.copy; b.classList.remove('on'); b.setAttribute('aria-label', 'Copy code'); tip.classList.remove('show'); }, 1600);
      });
    } else if (what === 'wrap') {
      b.classList.toggle('on', block.classList.toggle('wrap'));
    } else if (what === 'save') {
      var label = (block.querySelector('.code-block-label').textContent || '').trim();
      var ext = {python: 'py', javascript: 'js', typescript: 'ts', html: 'html', css: 'css', java: 'java', kotlin: 'kt',
                 swift: 'swift', go: 'go', rust: 'rs', c: 'c', cpp: 'cpp', csharp: 'cs', php: 'php', ruby: 'rb', sql: 'sql',
                 bash: 'sh', shell: 'sh', json: 'json', yaml: 'yml', dart: 'dart', r: 'r'}[label.toLowerCase()];
      ginkEmit('save_code', {name: label.indexOf('.') > 0 ? label : 'gink-code.' + (ext || 'txt'), code: codeText(block).replace(/\n$/, '')});
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
  function nearBottom() { return atEnd(220); }
  document.addEventListener('DOMContentLoaded', function () {             // the conversation scrolls inside #scroller
    scroller().addEventListener('scroll', function () {
      document.getElementById('jump').classList.toggle('show', !nearBottom() && !document.body.classList.contains('home'));
    }, {passive: true});
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
    d.style.cssText = 'position:fixed;top:0;right:0;bottom:0;left:0;z-index:10000;display:grid;place-items:center;background:rgba(0,0,0,.35)';
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
  // ---- "What's new" after an update (apps)
  window.showWhatsNew = function (version, sections) {
    var old = document.getElementById('whatsnew'); if (old) old.remove();
    var d = document.createElement('div'); d.id = 'whatsnew'; d.setAttribute('role', 'dialog'); d.setAttribute('aria-label', "What's new");
    d.style.cssText = 'position:fixed;top:0;right:0;bottom:0;left:0;z-index:10000;display:grid;place-items:center;background:rgba(0,0,0,.35)';
    var box = document.createElement('div');
    box.style.cssText = 'width:min(520px,92vw);max-height:80vh;overflow:auto;background:var(--surface);color:var(--text-main);border-radius:16px;' +
      'padding:22px;box-shadow:0 12px 40px rgba(0,0,0,.25);font:14.5px/1.55 system-ui,sans-serif';
    var h = document.createElement('h3'); h.textContent = 'What\u2019s new in Gink ' + version; h.style.margin = '0 0 10px';
    box.appendChild(h);
    (sections || []).forEach(function (sec) {
      if (sections.length > 1) { var v = document.createElement('div'); v.textContent = 'Version ' + sec[0];
        v.style.cssText = 'font-weight:700;font-size:13px;color:var(--text-muted);margin:12px 0 4px'; box.appendChild(v); }
      var ul = document.createElement('ul'); ul.style.cssText = 'margin:0;padding-left:20px';
      sec[1].forEach(function (pt) { var li = document.createElement('li'); li.textContent = pt; li.style.margin = '4px 0'; ul.appendChild(li); });
      box.appendChild(ul);
    });
    var row = document.createElement('div'); row.style.cssText = 'display:flex;justify-content:flex-end;margin-top:16px';
    var ok = document.createElement('button'); ok.textContent = 'Got it';
    ok.style.cssText = 'font:inherit;font-weight:650;border:0;border-radius:999px;padding:8px 18px;cursor:pointer;background:var(--text-main);color:var(--surface)';
    ok.onclick = function () { d.remove(); }; row.appendChild(ok); box.appendChild(row);
    d.appendChild(box); d.onclick = function (e) { if (e.target === d) d.remove(); };
    document.body.appendChild(d); ok.focus();
  };
  // ---- Question cards: an answer's ```ask {"questions":[{"q":..., "options":[...]}]}``` becomes tappable choices
  window.upgradeQuestionCards = function (root) {
    Array.prototype.slice.call(root.querySelectorAll('.code-block')).forEach(function (block) {
      var label = block.querySelector('.code-block-label'); if (!label || label.textContent.trim().toLowerCase() !== 'ask') return;
      var data; try { data = JSON.parse(block.querySelector('code').textContent); } catch (e) { return; }
      var qs = (data.questions || []).filter(function (q) { return q && q.q && (q.options || []).length; }).slice(0, 3);
      if (!qs.length) return;
      var card = document.createElement('div'); card.className = 'qcard'; card.setAttribute('role', 'group');
      var st = { i: 0, answers: qs.map(function () { return null; }) };
      function el(t, c, txt) { var x = document.createElement(t); if (c) x.className = c; if (txt != null) x.textContent = txt; return x; }
      function draw() {
        card.innerHTML = ''; var q = qs[st.i];
        card.appendChild(el('div', 'qq', q.q));
        q.options.slice(0, 4).forEach(function (o) {
          var b = el('button', 'qo' + (st.answers[st.i] === String(o) ? ' on' : ''), String(o));
          b.onclick = function () { st.answers[st.i] = String(o); next(); }; card.appendChild(b);
        });
        var row = el('div', 'qe'); row.appendChild(el('span', '', '\u270e'));
        var inp = el('input'); inp.placeholder = 'Something else'; inp.setAttribute('aria-label', 'Something else');
        var own = st.answers[st.i]; if (own && q.options.map(String).indexOf(own) < 0) inp.value = own;
        inp.onkeydown = function (e) { if (e.key === 'Enter' && inp.value.trim()) { e.preventDefault(); st.answers[st.i] = inp.value.trim(); next(); } };
        row.appendChild(inp); card.appendChild(row);
        var f = el('div', 'qf');
        var prev = el('button', '', '\u2039'); prev.disabled = st.i === 0; prev.onclick = function () { st.i--; draw(); };
        var nx = el('button', '', '\u203a'); nx.disabled = st.i === qs.length - 1; nx.onclick = function () { st.i++; draw(); };
        f.appendChild(prev); f.appendChild(el('span', '', (st.i + 1) + ' of ' + qs.length)); f.appendChild(nx);
        var gap = el('span'); gap.style.flex = '1'; f.appendChild(gap);
        var skip = el('button', 'qskip', 'Skip'); skip.onclick = function () { st.answers[st.i] = st.answers[st.i] || '(skipped)'; next(); };
        var send = el('button', 'qsend', '\u2191'); send.setAttribute('aria-label', 'Send the answers');
        send.disabled = st.answers.some(function (a) { return !a; }); send.onclick = submit;
        f.appendChild(skip); f.appendChild(send); card.appendChild(f);
      }
      function next() { if (st.i < qs.length - 1) st.i++; draw(); }
      function finish(answers) {                     // the card as answered: the questions and what was chosen
        card.classList.add('done'); card.innerHTML = '';
        card.appendChild(el('div', 'qq', 'Your answers'));
        qs.forEach(function (q, i) { card.appendChild(el('div', 'qans', q.q + ' \u2014 ' + (answers[i] || 'answered in the chat'))); });
      }
      card._finish = function (text) { finish(parseAnswers(qs, text)); };
      function submit() {
        // "My answers:" so the AI reads them as answers to its questions (not as the person asking it the question:
        // before 0.1.160, "What OS does your laptop use? macOS" got "I don't run on a laptop myself")
        var text = 'My answers:\n' + qs.map(function (q, i) { return '\u2022 ' + q.q + ' \u2192 ' + st.answers[i]; }).join('\n');
        finish(st.answers);
        ginkEmit('send', text);
      }
      draw(); block.parentNode.replaceChild(card, block);
    });
  };
  // What the person answered, from their next message: "My answers:\n- Q -> A" (0.1.160) or the older "Q A".
  function parseAnswers(qs, text) {
    text = String(text || '');
    return qs.map(function (q) {
      var lines = text.split('\n');
      for (var i = 0; i < lines.length; i++) {
        var ln = lines[i].replace(/^\s*[\u2022*-]\s*/, '');
        if (ln.indexOf(q.q) !== 0) continue;
        var rest = ln.slice(q.q.length).replace(/^\s*(\u2192|->|:|\u2014|-)?\s*/, '');
        if (rest) return rest;
      }
      return '';
    });
  }
  // A question card stays answerable only until the person's next message. Opening a chat again redraws its cards,
  // so the message after a card closes it, with the answers it held -- an answered card never comes back blank.
  window.closeQuestionCards = function (text) {
    Array.prototype.forEach.call(document.querySelectorAll('.qcard:not(.done)'), function (card) {
      if (card._finish) card._finish(text);
    });
  };
  // ---- "Recalled memory": the memories Gink is using for this answer
  window.showRecalled = function (items) {
    if (!items || !items.length) return;
    var feed = document.getElementById('feed') || document.body;
    var row = document.createElement('div'); row.className = 'recalled'; row.setAttribute('role', 'note');
    var icon = document.createElement('span'); icon.textContent = '\u21ba'; row.appendChild(icon);
    var b = document.createElement('b'); b.textContent = items.length === 1 ? 'Recalled memory' : 'Recalled ' + items.length + ' memories'; row.appendChild(b);
    var m = document.createElement('span'); m.className = 'rm'; m.textContent = items.map(function (x) { return x.text || x; }).join(' \u00b7 ');
    row.appendChild(m); row.title = 'Tap to see all';
    row.onclick = function () { row.classList.toggle('open'); };
    feed.appendChild(row);
  };
  // ---- The viewer (like Claude's): long code -- and artifacts, the finished things Gink makes (0.1.161): a web page or
  // app, an SVG, a Mermaid diagram, a document, a long code file. A card in the chat; the viewer shows a preview (a
  // sealed sandbox: its scripts run, but it can't reach Gink), the code or the document, its versions, Copy, Download,
  // Publish (pages, images), Expand and Close.
  var CV = { text: '', name: '', art: null };
  var CV_LANGS = {python: ['Python', 'py'], javascript: ['JavaScript', 'js'], typescript: ['TypeScript', 'ts'], html: ['HTML', 'html'],
                  css: ['CSS', 'css'], java: ['Java', 'java'], kotlin: ['Kotlin', 'kt'], swift: ['Swift', 'swift'], go: ['Go', 'go'],
                  rust: ['Rust', 'rs'], bash: ['Shell', 'sh'], shell: ['Shell', 'sh'], sql: ['SQL', 'sql'], json: ['JSON', 'json'],
                  c: ['C', 'c'], cpp: ['C++', 'cpp'], csharp: ['C#', 'cs'], php: ['PHP', 'php'], ruby: ['Ruby', 'rb'], dart: ['Dart', 'dart'],
                  svg: ['SVG', 'svg'], mermaid: ['Diagram', 'mmd'], markdown: ['Markdown', 'md'], yaml: ['YAML', 'yml'],
                  jsx: ['React', 'jsx'], tsx: ['React', 'tsx'], vue: ['Vue', 'vue'], xml: ['XML', 'xml'], r: ['R', 'r']};
  var MERMAID_VERSION = '11.17.2';
  var GINK_WEBAPP = /^https?:$/.test(location.protocol) && location.hostname !== 'gink.local';
  function cvName(block, lang) {
    if (lang.indexOf('.') > 0) return lang;                              // the label is already a file name
    var prev = block.previousElementSibling, re = /([A-Za-z0-9_-]+\.(py|js|ts|jsx|tsx|html|css|json|java|kt|swift|go|rs|sh|sql|c|cpp|cs|php|rb|dart|yml|yaml|toml|md))\b/;
    for (var i = 0; prev && i < 3; i++, prev = prev.previousElementSibling) { var m = re.exec(prev.textContent || ''); if (m) return m[1]; }
    return '';
  }
  window.openCodeViewer = function (block) {
    var lang = (block.querySelector('.code-block-label').textContent || '').trim().toLowerCase();
    var file = cvName(block, lang), info = CV_LANGS[lang] || [lang ? lang.charAt(0).toUpperCase() + lang.slice(1) : 'Code', lang || 'txt'];
    var ext = file ? file.split('.').pop() : info[1];
    var title = file ? file.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').replace(/^./, function (c) { return c.toUpperCase(); })
                     : info[0] + ' code';
    var text = codeText(block).replace(/\n$/, ''), body = block.querySelector('.code-block-body');
    var design = /^(html?|svg|xml)$/.test(ext) && /<(html|body|div|svg|style|section|main|h1|p)\b/i.test(text);
    cvOpen({ title: title, badge: ext.toUpperCase().slice(0, 4), text: text, name: file || ('gink-code.' + ext),
             codeHTML: body ? body.outerHTML : '', kind: design ? (/^\s*<svg\b/i.test(text) ? 'image' : 'page') : 'code' });
  };
  function cvPanel() {
    var v = document.getElementById('codeview');
    if (v) return v;
    v = document.createElement('aside'); v.id = 'codeview'; v.setAttribute('aria-label', 'Code viewer');
    v.innerHTML = '<div class="cvh"><span class="cvt"></span><span class="cvb"></span>' +
      '<span class="cvver" hidden><button class="cvprev" aria-label="Older version">‹</button><span class="cvvn"></span>' +
      '<button class="cvnext" aria-label="Newer version">›</button></span>' +
      '<span class="cvtabs" hidden><button data-tab="preview">Preview</button><button data-tab="code">Code</button></span><span class="cvg"></span>' +
      '<button class="cvpub" hidden>Publish</button>' +
      '<button class="cvcopy">Copy</button><button class="cvmore" aria-label="More">⌄</button>' +
      '<button class="cvicon cvwide" title="Expand" aria-label="Expand">⤢</button>' +
      '<button class="cvicon cvclose" title="Close" aria-label="Close">×</button></div><div class="cvbody"></div>' +
      '<div class="cvdoc" hidden></div><div class="cvimg" hidden></div>';
    document.body.appendChild(v);
    v.querySelector('.cvcopy').onclick = function () { var b = this; copyText(CV.text, function () { b.textContent = 'Copied';
      setTimeout(function () { b.textContent = 'Copy'; }, 1500); }); };
    v.querySelector('.cvmore').onclick = function (e) {
      e.stopPropagation(); var old = v.querySelector('.cvmenu'); if (old) { old.remove(); return; }
      var m = document.createElement('div'); m.className = 'cvmenu';
      m.innerHTML = '<button data-cv="copy">Copy</button><button data-cv="download">Download</button>' +
        (CV.art && CV.art.kind === 'page' && (GINK_WEBAPP || !(window.matchMedia && matchMedia('(hover: none)').matches)) ?   // computers: the app opens the browser
          '<button data-cv="tab">' + (GINK_WEBAPP ? 'Open in a new tab' : 'Open in your browser') + '</button>' : '');
      m.onclick = function (ev) { var a = ev.target.getAttribute('data-cv'); m.remove();
        if (a === 'copy') v.querySelector('.cvcopy').click();
        else if (a === 'tab') cvNewTab(cvFullPage(CV.text, CV.art ? CV.art.title : ''));
        else ginkEmit('save_code', {name: CV.name, code: CV.text}); };
      v.appendChild(m);
    };
    v.querySelector('.cvpub').onclick = function () {
      this.disabled = true; this.textContent = 'Publishing…';
      ginkEmit('publish_design', {html: cvFullPage(CV.text, v.querySelector('.cvt').textContent), title: v.querySelector('.cvt').textContent});
    };
    v.querySelector('.cvtabs').onclick = function (e) { var t = e.target.getAttribute && e.target.getAttribute('data-tab'); if (t) cvShow(t); };
    v.querySelector('.cvwide').onclick = function () { var w = v.classList.toggle('wide'); this.title = w ? 'Make smaller' : 'Expand'; };
    v.querySelector('.cvclose').onclick = function () { v.remove(); document.body.classList.remove('viewer-open'); artMark(null); };
    v.querySelector('.cvprev').onclick = function () { artStep(-1); };
    v.querySelector('.cvnext').onclick = function () { artStep(1); };
    document.addEventListener('click', function () { var m = v.querySelector('.cvmenu'); if (m) m.remove(); });
    v.addEventListener('keydown', function (e) { if (e.key === 'Escape') v.querySelector('.cvclose').click(); });
    return v;
  }
  function cvOpen(o) {
    var v = cvPanel();
    CV.text = o.text || ''; CV.name = o.name || 'gink-file.txt'; CV.art = o;
    v.querySelector('.cvt').textContent = o.title; v.querySelector('.cvb').textContent = o.badge || '';
    var ver = v.querySelector('.cvver'), many = o.versions && o.versions.length > 1;
    ver.hidden = !many;
    if (many) {
      var at = o.versions.indexOf(o.id);
      v.querySelector('.cvvn').textContent = 'v' + (at + 1) + ' of ' + o.versions.length;
      v.querySelector('.cvprev').disabled = at <= 0; v.querySelector('.cvnext').disabled = at >= o.versions.length - 1;
    }
    // the code, with line numbers (the chat's blocks have none); a document: its reading view
    v.querySelector('.cvbody').innerHTML = o.codeHTML ? '<div class="code-block cv-inner" data-enh="1">' + o.codeHTML + '</div>' : '';
    var cvb = v.querySelector('.cvbody .code-block-body'), cvn = CV.text ? CV.text.split('\n').length : 0;
    if (cvb && cvn > 1 && !cvb.querySelector('.lns')) {
      var lns = document.createElement('div'); lns.className = 'lns';
      var nums = []; for (var li = 1; li <= cvn; li++) nums.push(li);
      lns.textContent = nums.join('\n'); cvb.insertBefore(lns, cvb.firstChild);
    }
    v.querySelector('.cvdoc').innerHTML = o.kind === 'document' ? '<div class="cvdoc-in">' + (o.docHTML || '') + '</div>' : '';
    var design = o.kind === 'page' || o.kind === 'image' || o.kind === 'diagram';
    v.querySelector('.cvtabs').hidden = !design;
    var pub = v.querySelector('.cvpub'); pub.hidden = !(o.kind === 'page' || o.kind === 'image'); pub.disabled = false; pub.textContent = 'Publish';
    var bar = v.querySelector('.cvpubbar'); if (bar) bar.remove();
    cvShow(o.kind === 'document' ? 'doc' : design ? 'preview' : 'code');
    document.body.classList.add('viewer-open');
  }
  window.cvOpen = cvOpen;
  // A fragment or an SVG becomes a whole page (to preview and to publish)
  function cvFullPage(text, title) {
    if (/<!doctype html|<html[\s>]/i.test(text)) return text;
    var svg = /^\s*<svg\b/i.test(text), t = document.createElement('div'); t.textContent = title || 'My design';
    return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' +
      '<title>' + t.innerHTML + '</title></head><body' + (svg ? ' style="margin:0;display:grid;place-items:center;min-height:100vh"' : '') +
      '>' + text + '</body></html>';
  }
  // A diagram: Mermaid draws it inside the sealed preview (the library comes from Gink's server only when needed)
  function cvDiagramPage(code) {
    var t = document.createElement('div'); t.textContent = code;
    var dark = document.body.classList.contains('theme-dark');
    var src = (typeof window.GINK_ICONS === 'string' && window.GINK_ICONS ? window.GINK_ICONS : location.origin) +
              '/vendor/mermaid.min.js?v=' + MERMAID_VERSION;
    return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' +
      '<style>html,body{margin:0;min-height:100%;background:' + (dark ? '#1d2023' : '#ffffff') + '}body{display:flex;justify-content:center;' +
      'padding:28px 16px;box-sizing:border-box;font-family:system-ui,sans-serif}.mermaid{width:100%;text-align:center}' +
      '.mermaid svg{min-width:min(100%,620px);max-width:100%;height:auto}#e{color:#b3261e;white-space:pre-wrap}</style>' +
      '</head><body><pre class="mermaid">' + t.innerHTML + '</pre><div id="e"></div><script src="' + src + '"><\/script><script>' +
      'try{mermaid.initialize({startOnLoad:false,securityLevel:"strict",theme:"' + (dark ? 'dark' : 'default') + '"});' +
      'mermaid.run().catch(function(x){document.getElementById("e").textContent="This diagram has a mistake: "+(x&&x.message||x);});}' +
      'catch(x){document.getElementById("e").textContent="The diagram couldn\\u2019t be drawn (are you online?).";}<\/script></body></html>';
  }
  // The sealed preview: in the apps, a sandboxed srcdoc frame; on the web, Gink's /artifact/frame (its own sandbox CSP,
  // so the page's libraries from the web load, and it never inherits the web app's rights)
  function cvFrame(v, html) {
    var old = v.querySelector('.cvframe'); if (old) old.remove();
    old = document.createElement('iframe'); old.className = 'cvframe';
    old.setAttribute('sandbox', 'allow-scripts allow-modals allow-forms allow-popups');   // never the page's own origin
    old.setAttribute('title', 'Preview'); v.appendChild(old);
    if (GINK_WEBAPP) {
      var sent = false;
      old.addEventListener('load', function () {
        if (sent) return; sent = true;
        try { old.contentWindow.postMessage({ type: 'gink-artifact', html: html }, '*'); } catch (e) {}
      });
      old.src = '/artifact/frame';
    } else old.srcdoc = html;
    return old;
  }
  function cvNewTab(html) {                       // the web app opens it: the same sealed page, in a tab of its own
    ginkEmit('artifact_tab', { html: html });
  }
  // Publishing finished: the link (Copy link, Open), or why it failed
  window.cvPublished = function (url, error) {
    var v = document.getElementById('codeview'); if (!v) return;
    var pub = v.querySelector('.cvpub'); pub.disabled = false; pub.textContent = 'Publish';
    var bar = v.querySelector('.cvpubbar'); if (bar) bar.remove();
    bar = document.createElement('div'); bar.className = 'cvpubbar' + (url ? '' : ' err');
    if (url) {
      pub.hidden = true;
      var a = document.createElement('span'); a.className = 'cvurl'; a.textContent = url;
      var cp = document.createElement('button'); cp.textContent = 'Copy link';
      cp.onclick = function () { copyText(url, function () { cp.textContent = 'Copied'; setTimeout(function () { cp.textContent = 'Copy link'; }, 1500); }); };
      var op = document.createElement('button'); op.textContent = 'Open'; op.onclick = function () { ginkEmit('open_url', url); };
      bar.appendChild(document.createTextNode('Published · ')); bar.appendChild(a); bar.appendChild(cp); bar.appendChild(op);
    } else bar.textContent = error || 'Publishing didn’t work. Please try again.';
    v.querySelector('.cvh').insertAdjacentElement('afterend', bar);
  };
  // Preview | Code for designs; the reading view for documents
  function cvShow(tab) {
    var v = document.getElementById('codeview'); if (!v) return;
    var body = v.querySelector('.cvbody'), doc = v.querySelector('.cvdoc'), img = v.querySelector('.cvimg'), old = v.querySelector('.cvframe');
    var o = CV.art || {};
    v.querySelectorAll('.cvtabs button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-tab') === tab); });
    body.hidden = tab !== 'code'; doc.hidden = tab !== 'doc'; img.hidden = true;
    if (old) old.hidden = true;
    if (tab !== 'preview') return;
    if (o.kind === 'image' && /^\s*<svg\b/i.test(CV.text)) {         // an SVG: shown as a picture (no scripts at all)
      img.hidden = false; img.innerHTML = '';
      var pic = new Image(); pic.alt = o.title || 'Image';
      pic.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(CV.text.indexOf('xmlns') > 0 ? CV.text : CV.text.replace(/<svg\b/i, '<svg xmlns="http://www.w3.org/2000/svg"'));
      img.appendChild(pic);
      return;
    }
    if (old && old.getAttribute('data-for') === String(o.id || CV.text.length)) { old.hidden = false; return; }
    old = cvFrame(v, o.kind === 'diagram' ? cvDiagramPage(CV.text) : cvFullPage(CV.text, o.title || ''));
    old.setAttribute('data-for', String(o.id || CV.text.length));
  }

  // ---- Artifacts in the chat: which blocks are artifacts, their cards, versions (same title = a new version)
  var ARTS = [];                                   // {id, key, title, kind, ...} in the order they appeared
  var ART_ICONS = {
    page: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/></svg>',
    image: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="9" cy="9" r="2"/><path d="M21 15l-5-5L5 21"/></svg>',
    diagram: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="5" rx="1.2"/><rect x="14" y="16" width="7" height="5" rx="1.2"/><rect x="14" y="3" width="7" height="5" rx="1.2"/><path d="M6.5 8v5.5a2 2 0 0 0 2 2H14M10 5.5h4"/></svg>',
    document: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6M9 9h2"/></svg>',
    code: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 7l-5 5 5 5M16 7l5 5-5 5M13.5 4l-3 16"/></svg>'
  };
  var ART_KIND = { page: ['Web page', '#2F6FB3'], image: ['Image', '#A3274F'], diagram: ['Diagram', '#0F7C74'],
                   document: ['Document', '#B4530F'], code: ['Code', '#7A3FB3'] };
  function artKey(t) { return String(t || '').toLowerCase().replace(/\s+/g, ' ').trim(); }
  function artWhat(block) {                       // a code block -> its artifact kind ('' = stays in the chat)
    var lang = (block.getAttribute('data-lang') || '').toLowerCase(), title = block.getAttribute('data-title') || '';
    if (lang === 'map' || lang === 'ask' || lang === 'schedule') return '';
    var text = codeText(block), lines = text.split('\n').length;
    if (lang === 'mermaid') return 'diagram';
    if ((lang === 'svg' || lang === 'xml' || lang === 'html') && /^\s*(<\?xml[^>]*>\s*)?<svg\b[\s\S]*<\/svg>\s*$/i.test(text)) return 'image';
    if ((lang === 'html' || lang === 'htm') && (/<!doctype html|<html[\s>]/i.test(text) || (title && /<(body|div|main|section|style|script)\b/i.test(text)))) return 'page';
    if ((lang === 'markdown' || lang === 'md') && title) return 'document';
    if (title && lines >= 3) return 'code';
    return lines >= 40 && lang !== 'text' && lang !== 'bash' ? 'code' : '';
  }
  function artTitle(kind, block, text) {
    var t = block.getAttribute('data-title') || '';
    if (t) return t;
    if (kind === 'page') { var m = /<title[^>]*>([^<]{1,80})<\/title>/i.exec(text); if (m) return m[1].trim(); }
    if (kind === 'document') { var h = block.querySelector('h1, h2, h3'); if (h && h.textContent.trim()) return h.textContent.trim().slice(0, 80); }
    var label = (block.querySelector('.code-block-label') || {}).textContent || '';
    if (label.indexOf('.') > 0) return label.trim();
    return { page: 'Web page', image: 'Image', diagram: 'Diagram', document: 'Document' }[kind] ||
           ((CV_LANGS[label.trim().toLowerCase()] || [''])[0] || 'Code') + (kind === 'code' ? ' code' : '');
  }
  function artMark(id) { Array.prototype.forEach.call(document.querySelectorAll('.artcard'), function (c) { c.classList.toggle('on', c.getAttribute('data-art') === id); }); }
  function artEntry(id) { for (var i = 0; i < ARTS.length; i++) if (ARTS[i].id === id) return ARTS[i]; return null; }
  function artOpen(entry) {
    var same = ARTS.filter(function (a) { return a.key === entry.key; }).map(function (a) { return a.id; });
    entry.versions = same;
    cvOpen(entry); artMark(entry.id);
  }
  function artStep(d) {
    var o = CV.art; if (!o || !o.versions) return;
    var at = o.versions.indexOf(o.id) + d, next = artEntry(o.versions[at]);
    if (next) artOpen(next);
  }
  window.openArtifact = function (id) { var e = artEntry(id); if (e) artOpen(e); };
  window.upgradeArtifacts = function (root) {     // after an answer is drawn: its artifacts become cards
    ARTS = ARTS.filter(function (a) { return a.card && a.card.isConnected; });
    var found = [];
    Array.prototype.slice.call((root || document).querySelectorAll('.code-block, .doc-block')).forEach(function (block) {
      if (block.closest('.artcard, #codeview, .qcard, .gmap')) return;
      var isDoc = block.classList.contains('doc-block'), kind = isDoc ? 'document' : artWhat(block);
      if (!kind) return;
      var text = isDoc ? (block.getAttribute('data-md') || (block.querySelector('.doc-block-body') || block).innerText || '') : codeText(block).replace(/\n$/, '');
      var title = artTitle(kind, block, text), key = artKey(title);
      var lang = isDoc ? 'markdown' : (block.getAttribute('data-lang') || 'text').toLowerCase();
      var info = CV_LANGS[lang] || [lang.toUpperCase(), lang || 'txt'];
      var label = (block.querySelector('.code-block-label') || {}).textContent || '';
      var ext = kind === 'page' ? 'html' : kind === 'image' ? 'svg' : kind === 'diagram' ? 'mmd' : kind === 'document' ? 'md' : info[1];
      var name = label.indexOf('.') > 0 ? label.trim() : (title.replace(/[\\/:*?"<>|]+/g, '').trim().slice(0, 60) || 'gink-file') +
                 (/\.[a-z0-9]{1,6}$/i.test(title) ? '' : '.' + ext);
      var body = block.querySelector('.code-block-body');
      var entry = { id: 'art' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7), key: key, title: title, kind: kind,
                    text: text, name: name, codeHTML: body ? body.outerHTML : '',
                    docHTML: isDoc ? ((block.querySelector('.doc-block-body') || {}).innerHTML || '') : '',
                    badge: kind === 'code' ? (ext || 'txt').toUpperCase().slice(0, 4) : ART_KIND[kind][0].toUpperCase() };
      entry.version = ARTS.filter(function (a) { return a.key === key; }).length + 1;
      var card = document.createElement('div');
      card.className = 'artcard'; card.tabIndex = 0; card.setAttribute('role', 'button'); card.setAttribute('data-art', entry.id);
      card.style.setProperty('--ac', ART_KIND[kind][1]);
      card.innerHTML = '<div class="arti">' + ART_ICONS[kind] + '</div><div class="artm"><div class="artt"></div><div class="artk"><span></span></div></div>' +
                       '<span class="arto">Open</span>';
      card.querySelector('.artt').textContent = title;
      var nLines = text ? text.split('\n').length : 0;
      card.querySelector('.artk span').textContent = kind === 'code' ? info[0] + ', ' + nLines + ' lines' : ART_KIND[kind][0];
      if (entry.version > 1) { var vb = document.createElement('span'); vb.className = 'artv'; vb.textContent = 'v' + entry.version; card.querySelector('.artk').appendChild(vb); }
      card.setAttribute('aria-label', 'Open ' + title + ', ' + card.querySelector('.artk span').textContent + (entry.version > 1 ? ', version ' + entry.version : ''));
      card.addEventListener('click', function () { artOpen(entry); });
      card.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); artOpen(entry); } });
      block.parentNode.replaceChild(card, block);
      entry.card = card; ARTS.push(entry); found.push(entry);
    });
    return found.length;
  };
  // A new answer opens its artifact by itself (the last one), or its longest code, on larger screens -- never for
  // chats opened from history
  window.__sentAt = 0;
  window.autoOpenCode = function (el) {
    if (!window.__sentAt || Date.now() - window.__sentAt > 10 * 60 * 1000 || window.innerWidth < 900) return;
    var cards = el.querySelectorAll('.artcard');
    if (cards.length) { window.openArtifact(cards[cards.length - 1].getAttribute('data-art')); return; }
    var best = null, most = 0;
    Array.prototype.forEach.call(el.querySelectorAll('.code-block'), function (b) {
      var n = codeText(b).split('\n').length; if (n > most) { most = n; best = b; } });
    if (best && most >= 30) openCodeViewer(best);
  };
  // ---- Sources: the answer's "Sources" list becomes a button in its action row (official ones first)
  var SRC_COLORS = ['#2F6FB3', '#3F7D12', '#B4530F', '#7A3FB3', '#0F7C74', '#A3274F'];
  function srcHost(u) { try { return new URL(u).hostname.replace(/^www\./, ''); } catch (e) { return u; } }
  function srcColor(h) { var n = 0; for (var i = 0; i < h.length; i++) n = (n * 31 + h.charCodeAt(i)) % 997; return SRC_COLORS[n % SRC_COLORS.length]; }
  // A source's mark: its site's real logo (fetched by Gink's server, never from the device: GINK_ICONS + /icon/{host}),
  // over a coloured first letter that stays if the site has no logo.
  function srcIcon(h, cls) {
    var i = document.createElement('span'); i.className = cls; i.style.background = srcColor(h);
    var letter = document.createElement('b'); letter.textContent = h.charAt(0).toUpperCase(); i.appendChild(letter);
    if (typeof window.GINK_ICONS === 'string' && /^[a-z0-9.-]+$/i.test(h)) {
      var im = document.createElement('img'); im.alt = ''; im.decoding = 'async';
      try { im.referrerPolicy = 'no-referrer'; } catch (e) {}
      im.onload = function () { if (im.naturalWidth > 4) i.classList.add('logo'); else im.remove(); };
      im.onerror = function () { im.remove(); };
      im.src = window.GINK_ICONS + '/icon/' + encodeURIComponent(h.toLowerCase());
      i.appendChild(im);
    }
    return i;
  }
  window.upgradeSources = function (el) {
    var head = null;
    Array.prototype.forEach.call(el.querySelectorAll('strong'), function (s) {
      if (!head && /^sources$/i.test((s.textContent || '').trim()) && s.parentNode && s.parentNode.tagName === 'P') head = s;
    });
    if (!head) return;
    var p = head.parentNode, list = [], nodes = [p];
    function take(scope) {
      Array.prototype.forEach.call(scope.querySelectorAll('a[href^="http"]'), function (a) {
        var after = '', n = a.nextSibling;
        while (n && !(n.nodeType === 1 && (n.tagName === 'A' || n.tagName === 'BR'))) { after += n.textContent || ''; n = n.nextSibling; }
        var li = a.closest('li'); if (li) after += li.textContent.replace(a.textContent, '');
        // only Gink's own marker (" \u00b7 official", added by the server after checking the address) earns the badge --
        // not any text that happens to say "official" (an AI-written list could say anything)
        list.push({ url: a.href, title: (a.textContent || '').trim() || srcHost(a.href), official: /\u00b7\s*official\s*$/i.test(after.trim()) });
      });
    }
    take(p);
    var next = p.nextElementSibling;
    if (next && (next.tagName === 'UL' || next.tagName === 'OL')) { take(next); nodes.push(next); }
    if (!list.length) return;
    var bar = el.querySelector('.gactions'); if (!bar) return;
    nodes.forEach(function (n) { n.remove(); });
    var btn = document.createElement('button'); btn.className = 'ga gsrc'; btn.type = 'button';
    btn.setAttribute('aria-expanded', 'false'); btn.title = 'Where this answer comes from';
    var stack = document.createElement('span'); stack.className = 'stack'; stack.setAttribute('aria-hidden', 'true');
    list.slice(0, 3).forEach(function (s) { stack.appendChild(srcIcon(srcHost(s.url), '')); });
    if (list[0].official) {                     // official first (the server ranks them): a green check on its logo
      var ok = document.createElement('i'); ok.className = 'ok';
      ok.innerHTML = '<svg viewBox="0 0 12 12" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.2l2.3 2.3 4.7-5"/></svg>';
      stack.appendChild(ok);
      btn.title = 'Where this answer comes from \u2014 official sources first';
    }
    btn.appendChild(stack);
    btn.appendChild(document.createTextNode(list.length + (list.length === 1 ? ' source' : ' sources')));
    var panel = document.createElement('div'); panel.className = 'gsources'; panel.hidden = true; panel.setAttribute('role', 'list');
    list.forEach(function (s) {
      var h = srcHost(s.url), a = document.createElement('a'); a.href = s.url; a.setAttribute('role', 'listitem'); a.title = s.url;
      var ic = srcIcon(h, 'si');
      var tx = document.createElement('span'); tx.className = 'st';
      var b = document.createElement('b'); b.textContent = s.title; var sm = document.createElement('small'); sm.textContent = h;
      tx.appendChild(b); tx.appendChild(sm); a.appendChild(ic); a.appendChild(tx);
      if (s.official) { var o = document.createElement('span'); o.className = 'off'; o.textContent = 'Official'; a.appendChild(o); }
      var go = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); go.setAttribute('class', 'go'); go.setAttribute('viewBox', '0 0 24 24');
      go.innerHTML = '<path d="M7 17L17 7M9 7h8v8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>';
      a.appendChild(go);
      panel.appendChild(a);
    });
    btn.onclick = function (e) { e.stopPropagation(); panel.hidden = !panel.hidden; btn.setAttribute('aria-expanded', String(!panel.hidden)); };
    bar.insertBefore(btn, bar.firstChild);
    bar.parentNode.insertBefore(panel, bar.nextSibling);
  };

  // ---- Scheduled tasks (0.1.161): a ```schedule block ({title, task, every, at, day, date}) becomes a card. In a new
  // answer the task is made at once (the apps / web app ask Gink's server: POST /tasks); in a chat opened again the
  // card shows the task as it is now. The server runs it at its time and puts the result in the task's own chat.
  var TSK = { loaded: false, asked: false, bySource: {}, byId: {}, pending: {}, errors: {} };
  var TSK_DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
  var TSK_ICON = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2.5M9 2h6"/></svg>';
  function tskHash(t) { var h = 2166136261; for (var i = 0; i < t.length; i++) { h ^= t.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return h.toString(36); }
  function tskData(raw) {
    var d = raw && typeof raw === 'object' ? raw : null; if (!d) return null;
    var task = String(d.task || d.prompt || '').trim(); if (!task) return null;
    var every = String(d.every || 'daily').toLowerCase().replace(/^every\s+/, '').replace(/^(day)$/, 'daily').replace(/^(week)$/, 'weekly')
      .replace(/^(month)$/, 'monthly').replace(/^(hour)$/, 'hourly').replace(/^weekday$/, 'weekdays');
    var out = { title: String(d.title || '').trim().slice(0, 80), task: task.slice(0, 4000), every: every, at: String(d.at || '08:00').trim() };
    if (d.day !== undefined && d.day !== null && d.day !== '') out.day = d.day;
    if (d.date) out.date = String(d.date).slice(0, 10);
    return out;
  }
  function tskWhen(d) {
    var at = d.at || '08:00';
    if (d.when) return d.when;
    if (d.every === 'hourly') return 'Every hour at :' + String(at).slice(-2);
    if (d.every === 'weekdays') return 'Weekdays at ' + at;
    if (d.every === 'weekly') { var n = typeof d.day === 'number' ? TSK_DAYS[d.day % 7] : String(d.day || ''); return 'Every ' + (n ? n.charAt(0).toUpperCase() + n.slice(1) : 'week') + ' at ' + at; }
    if (d.every === 'monthly') return 'Every month on day ' + (d.day || 1) + ' at ' + at;
    if (d.every === 'once') return 'Once' + (d.date ? ', ' + d.date : '') + ' at ' + at;
    return 'Every day at ' + at;
  }
  function tskNext(ts) {
    if (!ts) return '';
    var d = new Date(ts * 1000), now = new Date(), tm = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    var day = new Date(now.getFullYear(), now.getMonth(), now.getDate()), diff = Math.round((new Date(d.getFullYear(), d.getMonth(), d.getDate()) - day) / 86400000);
    return 'next: ' + (diff === 0 ? 'today' : diff === 1 ? 'tomorrow' : d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })) + ', ' + tm;
  }
  function tskDraw(card) {
    var src = card.getAttribute('data-src'), d = card._data, t = TSK.bySource[src] || null, err = TSK.errors[src];
    if (t && TSK.byId[t.id]) t = TSK.byId[t.id];
    var gone = card._made && !t && TSK.loaded && !TSK.pending[src];
    var state = TSK.pending[src] ? 'busy' : err ? 'err' : t ? (t.enabled ? 'on' : (t.runs && t.every === 'once' ? 'done' : 'paused')) : (gone ? 'gone' : (TSK.loaded ? 'none' : 'wait'));
    card.className = 'tskcard' + (state === 'on' ? ' on' : state === 'err' ? ' err' : '');
    var label = { busy: 'Scheduling…', err: 'Not scheduled', on: 'Scheduled', paused: 'Paused', done: 'Done', gone: 'Deleted', none: 'Not scheduled', wait: '…' }[state];
    var shown = t || d, el = function (tag, cls, txt) { var x = document.createElement(tag); if (cls) x.className = cls; if (txt != null) x.textContent = txt; return x; };
    card.innerHTML = '';
    var top = el('div', 'tsk-top'), ic = el('div', 'tsk-ic'); ic.innerHTML = TSK_ICON;
    var m = el('div', 'tsk-m'); m.appendChild(el('div', 'tsk-t', shown.title || 'Scheduled task'));
    var w = tskWhen(shown) + (t && t.enabled && t.next_run ? ' · ' + tskNext(t.next_run) : '');
    m.appendChild(el('div', 'tsk-w', w));
    var pill = el('span', 'tsk-s'); pill.appendChild(el('i')); pill.appendChild(document.createTextNode(label));
    top.appendChild(ic); top.appendChild(m); top.appendChild(pill); card.appendChild(top);
    card.appendChild(el('div', 'tsk-q', shown.task || ''));
    var note = err || (state === 'on' ? 'Gink does this by itself at that time and puts the result in its own chat — even when your apps are closed.' :
                       state === 'none' ? 'This task isn’t scheduled.' : state === 'gone' ? 'This task was deleted. Its results stay in its chat.' : '');
    if (t && t.last_status && t.last_status !== 'ok' && t.last_note && state !== 'err') note = 'Last run: ' + t.last_note;
    if (note) card.appendChild(el('div', 'tsk-n', note));
    var acts = el('div', 'tsk-a');
    function btn(text, fn, primary) { var b = el('button', primary ? 'primary' : '', text); b.type = 'button'; b.onclick = function (e) { e.stopPropagation(); fn(b); }; acts.appendChild(b); return b; }
    if (t) {
      btn('Open its chat', function () { ginkEmit('task_open', { id: t.id, chat_id: t.chat_id }); }, true);
      if (t.enabled) btn('Run now', function (b) { b.disabled = true; ginkEmit('task_action', { action: 'run', id: t.id }); });
      if (state !== 'done') btn(t.enabled ? 'Pause' : 'Resume', function (b) { b.disabled = true; ginkEmit('task_action', { action: t.enabled ? 'pause' : 'resume', id: t.id }); });
      btn('Delete', function (b) { b.disabled = true; ginkEmit('task_action', { action: 'delete', id: t.id }); });
    } else if (state === 'err' || state === 'none' || state === 'gone') {
      btn(state === 'gone' ? 'Schedule again' : (state === 'err' ? 'Try again' : 'Schedule it'), function () { tskCreate(card); }, true);
    }
    if (acts.children.length) card.appendChild(acts);
    card.setAttribute('aria-label', 'Scheduled task: ' + (shown.title || '') + ' — ' + label);
  }
  function tskCards() { return Array.prototype.slice.call(document.querySelectorAll('.tskcard[data-src]')); }
  function tskRefresh() { tskCards().forEach(tskDraw); }
  function tskCreate(card) {
    var src = card.getAttribute('data-src');
    if (TSK.pending[src]) return;
    TSK.pending[src] = true; delete TSK.errors[src]; card._made = true;
    tskRefresh();
    ginkEmit('task_create', Object.assign({}, card._data, { source: src }));
  }
  // the apps / web app: the tasks as they are now (after a load, a change, a sync)
  window.setTasks = function (list) {
    TSK.loaded = true; TSK.bySource = {}; TSK.byId = {};
    (list || []).forEach(function (t) { TSK.byId[t.id] = t; if (t.source) TSK.bySource[t.source] = t; });
    tskRefresh();
  };
  // ... the answer to a card's task_create: the task, or why not
  window.taskResult = function (source, task, error) {
    delete TSK.pending[source];
    if (task && task.id) { TSK.byId[task.id] = task; TSK.bySource[source] = task; delete TSK.errors[source]; }
    else TSK.errors[source] = error || 'That didn’t work. Please try again.';
    tskRefresh();
  };
  window.upgradeSchedules = function (root, isNew) {
    Array.prototype.slice.call(root.querySelectorAll('.code-block')).forEach(function (block) {
      var label = block.querySelector('.code-block-label'); if (!label || label.textContent.trim().toLowerCase() !== 'schedule') return;
      var code = block.querySelector('code'), d;
      try { d = tskData(JSON.parse(code ? code.textContent : '')); } catch (e) { d = null; }
      if (!d) return;
      var card = document.createElement('div'); card.setAttribute('role', 'group');
      card.setAttribute('data-src', 'blk_' + tskHash(JSON.stringify(d)));
      card._data = d; card.className = 'tskcard';
      block.parentNode.replaceChild(card, block);
      var src = card.getAttribute('data-src');
      if (isNew && !TSK.bySource[src]) tskCreate(card);
      else { tskDraw(card); if (!TSK.loaded && !TSK.asked) { TSK.asked = true; ginkEmit('tasks_load', null); } }
    });
  };
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
