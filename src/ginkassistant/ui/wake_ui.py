"""
The "Hey Gink" glow: a soft, moving colour border around the whole window
(Gink lime, cyan, violet, pink) like Siri's edge glow, plus a small caption.

Four edge strips carry a moving rainbow gradient and the edges glow inward
in cycling colours -- plain long-supported CSS, so it shows on every WebKit
(older Safari and Android web views included).

Python -> page: wakeGlow("listening" | "thinking" | "speaking" | "off"), wakeCaption(text),
                wakeChip(state, label, detail)  -- the "Hey Gink" status chip in the composer
                (states: services/wake_status.py). Clicking it -> ginkEmit('wake_chip').
"""

CSS = r"""
  /* Works in every WebKit (no masks / @property): four edge strips with a moving
     rainbow gradient + a soft inner glow whose colour cycles. */
  #wake-glow { position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 90; pointer-events: none;
    opacity: 0; transition: opacity 0.4s ease; border-radius: 14px; }
  #wake-glow.on { opacity: 1; animation: wake-hue 4s linear infinite; }
  #wake-glow i { position: absolute; display: block;
    background: linear-gradient(90deg, #A8F03C, #2FE0C8, #5B8CFF, #A35BFF, #FF5FA2, #FFB347, #A8F03C);
    background-size: 300% 100%; animation: wake-flow 3s linear infinite; filter: saturate(1.2); }
  #wake-glow i.t { top: 0; left: 0; right: 0; height: 5px; }
  #wake-glow i.b { bottom: 0; left: 0; right: 0; height: 5px; animation-direction: reverse; }
  #wake-glow i.l { top: 0; bottom: 0; left: 0; width: 5px;
    background: linear-gradient(180deg, #A8F03C, #2FE0C8, #5B8CFF, #A35BFF, #FF5FA2, #FFB347, #A8F03C); background-size: 100% 300%;
    animation-name: wake-flow-v; animation-direction: reverse; }
  #wake-glow i.r { top: 0; bottom: 0; right: 0; width: 5px;
    background: linear-gradient(180deg, #A8F03C, #2FE0C8, #5B8CFF, #A35BFF, #FF5FA2, #FFB347, #A8F03C); background-size: 100% 300%;
    animation-name: wake-flow-v; }
  @keyframes wake-flow { from { background-position: 0% 0; } to { background-position: 300% 0; } }
  @keyframes wake-flow-v { from { background-position: 0 0%; } to { background-position: 0 300%; } }
  @keyframes wake-hue {
    0%, 100% { box-shadow: inset 0 0 38px 8px rgba(168,240,60,0.55); }
    25% { box-shadow: inset 0 0 38px 8px rgba(47,224,200,0.55); }
    50% { box-shadow: inset 0 0 38px 8px rgba(163,91,255,0.5); }
    75% { box-shadow: inset 0 0 38px 8px rgba(255,95,162,0.5); }
  }
  #wake-glow.thinking i { animation-duration: 1.2s; }
  #wake-glow.speaking i.t, #wake-glow.speaking i.b { height: 8px; }
  #wake-glow.speaking i.l, #wake-glow.speaking i.r { width: 8px; }
  #wake-cap { position: fixed; left: 50%; bottom: 120px; transform: translateX(-50%) translateY(8px); z-index: 91;
    pointer-events: none; opacity: 0; transition: opacity 0.3s, transform 0.3s; max-width: 70vw; text-align: center;
    background: rgba(18,20,18,0.82); color: #fff; padding: 9px 18px; border-radius: 999px; font-size: 15px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.25); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #wake-cap.on { opacity: 1; transform: translateX(-50%); }
  body.reduced-motion #wake-glow, body.reduced-motion #wake-glow i { animation: none; }
  body.reduced-motion #wake-glow.on { box-shadow: inset 0 0 38px 8px rgba(168,240,60,0.55); }

  /* "Hey Gink" status chip: always shows whether Gink is listening for its name */
  #wake-chip { display: none; align-items: center; gap: 6px; margin-left: 4px; padding: 4px 10px 4px 8px;
    border: 1px solid var(--border, #E3E6DF); border-radius: 999px; background: transparent; cursor: pointer;
    font: inherit; font-size: 12.5px; color: var(--text-muted, #6B7268); white-space: nowrap; max-width: 210px; }
  #wake-chip.show { display: inline-flex; }
  #wake-chip:hover { background: rgba(0,0,0,0.04); }
  #wake-chip:focus-visible { outline: 2px solid var(--accent, #3F8212); outline-offset: 2px; }
  #wake-chip .wd { width: 8px; height: 8px; border-radius: 50%; flex: none; background: #9AA096; }
  #wake-chip .wl { overflow: hidden; text-overflow: ellipsis; }
  #wake-chip.ready .wd { background: #3F8212; animation: wake-dot 2.4s ease-in-out infinite; }
  #wake-chip.ready { color: inherit; }
  #wake-chip.active .wd { background: #A8F03C; box-shadow: 0 0 0 3px rgba(168,240,60,0.35); }
  #wake-chip.starting .wd, #wake-chip.retrying .wd { background: #E0A100; }
  #wake-chip.problem { border-color: rgba(209,67,67,0.45); color: #B23535; }
  #wake-chip.problem .wd { background: #D14343; }
  @keyframes wake-dot { 0%, 100% { box-shadow: 0 0 0 0 rgba(63,130,18,0.45); } 50% { box-shadow: 0 0 0 4px rgba(63,130,18,0); } }
  body.reduced-motion #wake-chip .wd { animation: none; }
  body.home #wake-chip .wl { display: none; }           /* the centred pill: just the dot */
  body.home #wake-chip { padding: 6px; border-color: transparent; }
  @media (max-width: 520px) { #wake-chip .wl { display: none; } #wake-chip { padding: 6px; } }
"""

HTML = r"""
  <div id="wake-glow" aria-hidden="true"><i class="t"></i><i class="r"></i><i class="b"></i><i class="l"></i></div>
  <div id="wake-cap" role="status" aria-live="polite"></div>
"""

JS = r"""
  // ======================= "Hey Gink" glow =======================
  var WAKE_LABELS = {listening: 'Listening\u2026', thinking: 'Thinking\u2026', speaking: ''};
  function wakeGlow(state) {
    var g = document.getElementById('wake-glow'), c = document.getElementById('wake-cap');
    if (!state || state === 'off') { g.className = ''; c.classList.remove('on'); return; }
    g.className = 'on ' + state;
    if (WAKE_LABELS[state]) { c.textContent = WAKE_LABELS[state]; c.classList.add('on'); }
    else if (state === 'speaking') c.classList.remove('on');
  }
  function wakeChip(state, label, detail) {
    var c = document.getElementById('wake-chip');
    if (!c) {
      var row = document.querySelector('#composer .crow');
      if (!row) return;
      c = document.createElement('button');
      c.id = 'wake-chip'; c.type = 'button';
      c.innerHTML = '<span class="wd"></span><span class="wl"></span>';
      c.addEventListener('click', function () { ginkEmit('wake_chip'); });
      var anchor = row.querySelector('.menu-anchor');
      row.insertBefore(c, anchor ? anchor.nextSibling : row.firstChild);
    }
    if (!state || state === 'off') { c.className = ''; return; }
    c.className = 'show ' + state;
    c.querySelector('.wl').textContent = label || 'Hey Gink';
    c.title = detail || '';
    c.setAttribute('aria-label', detail || label || 'Hey Gink');
  }
  function wakeCaption(text) {
    var c = document.getElementById('wake-cap');
    if (text) { c.textContent = '\u201c' + text + '\u201d'; c.classList.add('on'); } else c.classList.remove('on');
  }
"""


def inject(page: str) -> str:
    i = page.index("</style>")
    page = page[:i] + CSS + page[i:]
    page = page.replace("<script>", HTML + "\n<script>", 1)
    i = page.rindex("</script>")
    return page[:i] + JS + page[i:]
