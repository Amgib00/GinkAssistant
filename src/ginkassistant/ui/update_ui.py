"""The "new version" notice on the chat page: a small bar under the top bar.
showUpdate(version) shows it; its buttons send 'update_get' / 'update_later' (ui/main_screen.py)."""

_CSS = """
<style>
  #update-bar { position: fixed; top: 58px; left: 50%; transform: translateX(-50%); z-index: 60; display: none;
    align-items: center; gap: 10px; padding: 8px 10px 8px 16px; border-radius: 999px; background: var(--elevated);
    color: var(--text-main); border: 1px solid var(--border); box-shadow: 0 6px 24px rgba(0,0,0,0.14); font-size: 14px;
    max-width: calc(100vw - 32px); }
  #update-bar.show { display: flex; }
  #update-bar button { border: 0; border-radius: 999px; padding: 6px 12px; font: inherit; font-weight: 650; cursor: pointer; }
  #update-bar .get { background: var(--text-main); color: var(--bg); }
  #update-bar .later { background: transparent; color: var(--text-muted); }
</style>
"""
_HTML = """
<div id="update-bar" role="status" aria-live="polite">
  <span id="update-text"></span>
  <button type="button" class="get" onclick="ginkEmit('update_get')">Download</button>
  <button type="button" class="later" onclick="hideUpdate(); ginkEmit('update_later')">Later</button>
</div>
<script>
  function showUpdate(version) {
    document.getElementById('update-text').textContent = 'Gink ' + String(version).replace(/^v/, '') + ' is available.';
    document.getElementById('update-bar').classList.add('show');
  }
  function hideUpdate() { document.getElementById('update-bar').classList.remove('show'); }
</script>
"""


def inject(html: str) -> str:
    html = html.replace("</head>", _CSS + "</head>", 1)
    i = html.rindex("</body>")
    return html[:i] + _HTML + html[i:]
