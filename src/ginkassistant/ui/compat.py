"""
Older web engines (0.1.157): flex "gap" for the app windows that don't have it.

The Mac app's window is the system's WebKit. On older Macs (Safari before 14.1 -- Catalina and older that
weren't updated) flex containers ignore `gap`: icons touched their labels in the sidebar, the "Temporary"
button's icon touched its word, chips and menus lost their spacing. Old Android System WebViews (before
Chrome 84) and older Linux WebKitGTK have the same gap.

FLEX_GAP_JS fixes that where it's needed and does nothing anywhere else: it checks once whether flex gap
works (a page that isn't laid out yet is checked again when it shows); if it doesn't, every flex container
that has a gap gets the same spacing as margins on its items
(the gap between two items goes on the first one's far side, or the second one's near side when the first
is a bit of text; auto margins are never replaced). It finds those containers from the page's own CSS
(the rules that set a gap) plus inline styles, redoes them when the page changes (new messages, menus
opening, the window resizing) and never lets an error reach the page.

Pages: the chat window (and through it the web app), the Workspace and Media Studio screens, the sign-in
screen and Gink Genie (services/web_app/genie.html carries a copy between its compat markers; a test keeps
the copy identical). Tests set window.GINK_GAP_POLYFILL = true to run it in a browser that has gap: it then
switches the native gap off on each container it fixes, so a screenshot shows exactly what an old engine
with the fix shows.
"""

FLEX_GAP_JS = r"""/* Gink: flex "gap" for web engines without it (ui/compat.py) */
(function () {
  'use strict';
  var w = window, d = document;
  if (w.__ginkGapFix) return;
  w.__ginkGapFix = true;
  var FORCE = !!w.GINK_GAP_POLYFILL, started = false;
  function probe() {          // a column of two 1px boxes 1px apart: 3 = gap works, 2 = it doesn't, 0 = no layout yet
    var t = d.createElement('div');
    t.style.cssText = 'display:flex;flex-direction:column;row-gap:1px;position:absolute;left:-9999px;top:0;visibility:hidden';
    for (var i = 0; i < 2; i++) { var c = d.createElement('div'); c.style.height = '1px'; t.appendChild(c); }
    (d.body || d.documentElement).appendChild(t);
    var h = t.scrollHeight;
    t.parentNode.removeChild(t);
    return h;
  }
  function decide() {
    if (started) return;
    var h = 3;
    try { h = probe(); } catch (e) {}
    if (h === 2) start();
    else if (h !== 3) {                                     // hidden for now: decide once the page shows
      var again = function () { w.removeEventListener('load', again); w.removeEventListener('resize', again); decide(); };
      w.addEventListener('load', again); w.addEventListener('resize', again);
    }
  }
  if (FORCE) start(); else decide();

  function start() {
  started = true;
  d.documentElement.className += ' no-flex-gap';
  var EP = w.Element && w.Element.prototype;
  var matchesFn = EP && (EP.matches || EP.webkitMatchesSelector || EP.msMatchesSelector);
  function matches(el, s) { try { return !!matchesFn && matchesFn.call(el, s); } catch (e) { return false; } }
  function px(v) { v = parseFloat(v); return isFinite(v) ? v : 0; }
  function cs(el) { try { return w.getComputedStyle(el); } catch (e) { return null; } }

  // ---- the page's CSS: which rules set a gap (where to look) and which set auto margins (never replace)
  var sheetCount = -1, AUTO = [], GAPSEL = '';
  function clean(sel) {
    return sel.replace(/::?(before|after|placeholder|selection|marker|first-line|first-letter|backdrop|-webkit-[\w-]+|-moz-[\w-]+)(\([^)]*\))?/g, '')
              .replace(/:(hover|focus-within|focus-visible|focus|active|visited)\b/g, '').replace(/\s+/g, ' ').replace(/^\s+|\s+$/g, '');
  }
  function readSheets() {
    if (d.styleSheets.length === sheetCount) return;
    sheetCount = d.styleSheets.length; AUTO = [];
    var gaps = [];
    function walk(rules) {
      for (var i = 0; i < rules.length; i++) {
        var r = rules[i];
        if (!r.selectorText) { if (r.cssRules) { try { walk(r.cssRules); } catch (e) {} } continue; }
        var st = r.style; if (!st) continue;
        var a = {s: r.selectorText, marginLeft: st.marginLeft === 'auto', marginRight: st.marginRight === 'auto',
                 marginTop: st.marginTop === 'auto', marginBottom: st.marginBottom === 'auto'};
        if (a.marginLeft || a.marginRight || a.marginTop || a.marginBottom) AUTO.push(a);
        if (st.columnGap || st.rowGap || st.getPropertyValue('gap')) {
          var parts = r.selectorText.split(',');
          for (var k = 0; k < parts.length; k++) {
            var c = clean(parts[k]);
            if (!c || gaps.indexOf(c) >= 0) continue;
            try { d.querySelector(c); gaps.push(c); } catch (e) {}
          }
        }
      }
    }
    for (var i = 0; i < d.styleSheets.length; i++) { try { walk(d.styleSheets[i].cssRules || []); } catch (e) {} }
    GAPSEL = gaps.join(',');
  }
  function isAuto(el, side) {
    if (el.style && el.style[side] === 'auto') return true;
    for (var i = 0; i < AUTO.length; i++) if (AUTO[i][side] && matches(el, AUTO[i].s)) return true;
    return false;
  }

  // ---- one container: undo what we did, measure again, space its items with margins
  function remember(el, prop, owner) {
    var o = el.__ggOrig || (el.__ggOrig = {});
    if (!(prop in o)) o[prop] = el.style[prop];
    var list = owner.__ggItems || (owner.__ggItems = []);
    if (list.indexOf(el) < 0) list.push(el);
  }
  function addMargin(el, side, gap, owner) {
    var s = cs(el); if (!s) return;
    var base = px(s[side]);
    remember(el, side, owner);
    el.style[side] = (base + gap) + 'px';
  }
  function undo(box) {
    var list = box.__ggItems || [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i], o = el.__ggOrig;
      if (!o) continue;
      for (var p in o) if (o.hasOwnProperty(p)) el.style[p] = o[p];
      el.__ggOrig = null;
    }
    box.__ggItems = null;
    if (box.__ggBox) { box.style.columnGap = box.__ggBox[0]; box.style.rowGap = box.__ggBox[1]; box.__ggBox = null; }
  }
  function itemsOf(box) {
    var out = [];
    for (var n = box.firstChild; n; n = n.nextSibling) {
      if (n.nodeType === 1) {
        var s = cs(n);
        if (!s || s.display === 'none' || s.position === 'absolute' || s.position === 'fixed') continue;
        out.push(n);
      } else if (n.nodeType === 3 && /\S/.test(n.nodeValue)) out.push(n);
    }
    return out;
  }
  function fix(box) {
    undo(box);
    var s = cs(box);
    if (!s || (s.display !== 'flex' && s.display !== 'inline-flex')) return false;
    var cg = px(s.columnGap), rg = px(s.rowGap);
    if (cg <= 0 && rg <= 0) return false;
    if (FORCE) { box.__ggBox = [box.style.columnGap, box.style.rowGap]; box.style.columnGap = '0px'; box.style.rowGap = '0px'; }
    var dir = s.flexDirection || 'row', col = dir.indexOf('column') === 0, rev = dir.indexOf('reverse') > 0;
    var rtl = s.direction === 'rtl', wrap = !!s.flexWrap && s.flexWrap !== 'nowrap';
    var after = col ? (rev ? 'marginTop' : 'marginBottom') : ((rtl !== rev) ? 'marginLeft' : 'marginRight');
    var before = col ? (rev ? 'marginBottom' : 'marginTop') : ((rtl !== rev) ? 'marginRight' : 'marginLeft');
    var main = col ? rg : cg, cross = col ? cg : rg;
    var items = itemsOf(box), i;
    if (main > 0) {
      for (i = 0; i + 1 < items.length; i++) {
        var A = items[i], B = items[i + 1], aEl = A.nodeType === 1, bEl = B.nodeType === 1;
        if ((aEl && isAuto(A, after)) || (bEl && isAuto(B, before))) continue;     // an auto margin already holds them apart
        if (aEl) addMargin(A, after, main, box);              // the first item's far side...
        else if (bEl) addMargin(B, before, main, box);        // ...or, after a bit of text, the next item's near side
      }
    }
    if (wrap && cross > 0) {                       // the gap between wrapped lines: measured after the spacing above
      var els = [], lines = [], edge = null;
      for (i = 0; i < items.length; i++) if (items[i].nodeType === 1) els.push(items[i]);
      for (i = 0; i < els.length; i++) {
        var r = els[i].getBoundingClientRect();
        var start = col ? (rtl ? -r.right : r.left) : r.top, end = col ? (rtl ? -r.left : r.right) : r.bottom;
        if (edge === null) { edge = end; lines.push(0); continue; }
        if (start >= edge - 0.5) { lines.push(lines[lines.length - 1] + 1); edge = end; }
        else { lines.push(lines[lines.length - 1]); if (end > edge) edge = end; }
      }
      var side = col ? (rtl ? 'marginRight' : 'marginLeft') : (s.flexWrap === 'wrap-reverse' ? 'marginBottom' : 'marginTop');
      for (i = 0; i < els.length; i++) if (lines[i] > 0) addMargin(els[i], side, cross, box);
    }
    return true;
  }

  // ---- when: once now, then whenever the page changes (batched)
  var touched = [], queue = [], full = false, timer = 0, mo = null;
  var stats = w.ginkGapStats = {runs: 0, ms: 0, boxes: 0};          // how much work it does (tests watch it)
  function collect(root, out) {
    if (!root || root.nodeType !== 1) return;
    if ((GAPSEL && matches(root, GAPSEL)) || /gap/.test(root.getAttribute('style') || '')) out.push(root);
    var list;
    try { list = root.querySelectorAll((GAPSEL ? GAPSEL + ',' : '') + '[style*="gap"]'); } catch (e) { list = []; }
    for (var i = 0; i < list.length; i++) out.push(list[i]);
  }
  function run() {
    timer = 0;
    var all = full, list = queue, boxes = [], i, t0 = Date.now();
    full = false; queue = [];
    if (mo) mo.disconnect();
    try {
      readSheets();
      if (all) { collect(d.body, boxes); boxes = boxes.concat(touched); }
      else for (i = 0; i < list.length; i++) {
        var el = list[i];
        if (!el || el.nodeType !== 1 || !d.documentElement.contains(el)) continue;
        collect(el, boxes);
        if (el.parentNode && el.parentNode.nodeType === 1) boxes.push(el.parentNode);
      }
      boxes.sort(function (a, b) {                       // document order...
        if (a === b) return 0;
        var p = a.compareDocumentPosition(b);
        return (p & 4) ? -1 : (p & 2) ? 1 : 0;
      });
      var seen = [];
      for (i = boxes.length - 1; i >= 0; i--) {         // ...backwards: inner containers first (the outer ones measure them)
        var b = boxes[i];
        if (seen.indexOf(b) >= 0) continue;
        seen.push(b);
        var at = touched.indexOf(b);
        if (fix(b)) { if (at < 0) touched.push(b); }
        else if (at >= 0) touched.splice(at, 1);
      }
      stats.boxes = touched.length;
    } catch (e) {}
    stats.runs++; stats.ms += Date.now() - t0;
    if (mo) observe();
  }
  function later(el) {
    if (el) { if (queue.indexOf(el) < 0) queue.push(el); } else full = true;
    if (!timer) timer = setTimeout(run, 50);
  }
  function observe() {
    try {
      mo.observe(d.documentElement, {childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style', 'hidden', 'open']});
    } catch (e) {}
  }
  if (w.MutationObserver) {
    mo = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var r = records[i], t = r.target;
        if (r.type === 'childList') {
          later(t.nodeType === 1 ? t : t.parentNode);
          for (var j = 0; j < r.addedNodes.length; j++) if (r.addedNodes[j].nodeType === 1) later(r.addedNodes[j]);
        } else if (t === d.body || t === d.documentElement) {
          if (r.attributeName !== 'style') later(null);      // a page state (home, a theme...); its style is only sizes
        } else later(t);
      }
    });
    observe();
  }
  w.addEventListener('load', function () { later(null); });
  var rz = 0;
  w.addEventListener('resize', function () { clearTimeout(rz); rz = setTimeout(function () { later(null); }, 120); });
  w.ginkGapFix = function () { later(null); };
  later(null);
  }
})();
"""

_TAG = "<script>\n" + FLEX_GAP_JS + "</script>\n"


def inject(page: str) -> str:
    """The fix, just before the page's last </body> (the page's own markup and CSS are in by then)."""
    i = page.rindex("</body>")
    return page[:i] + _TAG + page[i:]


GENIE_START = "<!-- gink:compat (a copy of FLEX_GAP_JS in src/ginkassistant/ui/compat.py: flex gap for older web engines) -->\n"
GENIE_END = "<!-- /gink:compat -->\n"


def with_genie_copy(html: str) -> str:
    """genie.html is a static file the server sends as it is: its copy of the fix, refreshed (tools/build_web_app.py)."""
    block = GENIE_START + _TAG + GENIE_END
    if GENIE_START in html:
        a = html.index(GENIE_START)
        b = html.index(GENIE_END, a) + len(GENIE_END)
        return html[:a] + block + html[b:]
    i = html.rindex("</body>")
    return html[:i] + block + html[i:]
