"""Agent mode on the chat page: a live checklist of steps above the message box, and
"Gink wants to ... [Allow] [Don't allow]" before sensitive actions (services/actions/agent.py).
Python calls agentStep / agentAsk / agentEnd; the buttons send 'agent_answer' {id, ok}."""

_CSS = """
<style>
  #agent-panel { position: fixed; left: 50%; bottom: 128px; transform: translateX(-50%); z-index: 55; display: none;
    width: min(560px, calc(100vw - 32px)); max-height: 46vh; overflow: auto; padding: 12px 14px; border-radius: 16px;
    background: var(--elevated); color: var(--text-main); border: 1px solid var(--border);
    box-shadow: 0 10px 30px rgba(0,0,0,0.16); font-size: 14px; }
  #agent-panel.show { display: block; }
  #agent-panel .ag-title { font-weight: 650; margin-bottom: 6px; }
  #agent-panel ol { list-style: none; margin: 0; padding: 0; }
  #agent-panel li { display: flex; gap: 8px; align-items: flex-start; padding: 4px 0; color: var(--text-muted); }
  #agent-panel li .ic { width: 18px; flex: none; text-align: center; }
  #agent-panel li.done { color: var(--text-main); } #agent-panel li.running { color: var(--text-main); font-weight: 600; }
  #agent-panel li.failed .ic { color: #C42B1C; } #agent-panel li.done .ic { color: var(--accent, #3F7D12); }
  #agent-panel .ag-ask { margin-top: 10px; padding: 10px 12px; border-radius: 12px; background: var(--bg); border: 1px solid var(--border); }
  #agent-panel .ag-ask .q { font-weight: 650; margin-bottom: 8px; }
  #agent-panel .ag-ask button { border: 0; border-radius: 999px; padding: 7px 14px; font: inherit; font-weight: 650; cursor: pointer; margin-right: 6px; }
  #agent-panel .ag-ask .allow { background: var(--text-main); color: var(--bg); }
  #agent-panel .ag-ask .deny { background: transparent; color: var(--text-main); box-shadow: inset 0 0 0 1.5px var(--border); }
</style>
"""
_HTML = """
<div id="agent-panel" role="status" aria-live="polite">
  <div class="ag-title" id="ag-title">Working on it\u2026</div>
  <ol id="ag-steps"></ol>
  <div class="ag-ask" id="ag-ask" hidden>
    <div class="q" id="ag-q"></div>
    <button type="button" class="allow" id="ag-allow">Allow</button>
    <button type="button" class="deny" id="ag-deny">Don\u2019t allow</button>
  </div>
</div>
<script>
  (function () {
    var ICON = {running: '\\u25CB', asking: '?', done: '\\u2713', failed: '\\u2717', skipped: '\\u2298'};
    var askId = null, hideTimer = null;
    function panel() { return document.getElementById('agent-panel'); }
    window.agentStep = function (i, label, state) {
      clearTimeout(hideTimer); panel().classList.add('show');
      var list = document.getElementById('ag-steps'), li = list.children[i];
      if (!li) { li = document.createElement('li'); li.innerHTML = '<span class="ic"></span><span class="tx"></span>'; list.appendChild(li); }
      li.className = state; li.querySelector('.ic').textContent = ICON[state] || '\\u25CB';
      li.querySelector('.tx').textContent = label;                       // text only: never HTML
      var n = list.children.length;
      document.getElementById('ag-title').textContent = state === 'asking' ? 'Waiting for your OK' : 'Step ' + (i + 1) + ' of ' + n;
    };
    window.agentAsk = function (id, text) {
      askId = id; document.getElementById('ag-q').textContent = 'Gink wants to: ' + text;
      document.getElementById('ag-ask').hidden = false; panel().classList.add('show');
      document.getElementById('ag-allow').focus();
    };
    function answer(ok) {
      if (askId === null) return;
      document.getElementById('ag-ask').hidden = true; ginkEmit('agent_answer', {id: askId, ok: ok}); askId = null;
    }
    document.getElementById('ag-allow').onclick = function () { answer(true); };
    document.getElementById('ag-deny').onclick = function () { answer(false); };
    window.agentEnd = function () {
      document.getElementById('ag-ask').hidden = true; askId = null;
      var n = document.getElementById('ag-steps').children.length;
      document.getElementById('ag-title').textContent = 'Finished \\u00b7 ' + n + (n === 1 ? ' step' : ' steps');
      hideTimer = setTimeout(function () { panel().classList.remove('show'); document.getElementById('ag-steps').innerHTML = ''; }, 5000);
    };
  })();
</script>
"""


def inject(html: str) -> str:
    html = html.replace("</head>", _CSS + "</head>", 1)
    i = html.rindex("</body>")
    return html[:i] + _HTML + html[i:]
