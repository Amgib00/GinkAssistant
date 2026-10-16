"""
The "Hey Gink" glow: a soft, moving colour border around the whole window
(Gink lime, cyan, violet, pink) like Siri's edge glow, plus a small caption.

Four edge strips carry a moving rainbow gradient and the edges glow inward
in cycling colours -- plain long-supported CSS, so it shows on every WebKit
(older Safari and Android web views included).

Python -> page: wakeGlow("listening" | "thinking" | "speaking" | "off"), wakeCaption(text)
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
