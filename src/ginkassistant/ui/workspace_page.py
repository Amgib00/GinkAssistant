"""The Workspace page (tasks, reminders, alarms, timers, events) -- HTML for ui/tasks_screen.py's WebView.

Premium look: a date header, one "tell Gink" box, summary cards that filter, a segmented filter, items grouped
into Overdue / Today / Upcoming / Anytime / Done with round check circles, time chips, step progress bars and
hover actions; an empty state with examples. Light and dark from the app theme. Events go to Python through
ginkEmit (ui/page_events.py), exactly like Media Studio.
"""

PAGE = r"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { __THEME__ --radius: 16px; --ok: #2F9E44; --warn: #E8590C; }
  @media (prefers-color-scheme: dark) { :root { --bg: #111613; --surface: #161C18; --elevated: #1E2620; --border: #2A332C;
    --text-main: #E8EEE9; --text-muted: #94A096; --accent-soft: rgba(168,240,60,.12); } }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text-main); font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, sans-serif;
    -webkit-font-smoothing: antialiased; }
  button { font: inherit; color: inherit; }
  .wrap { max-width: 860px; margin: 0 auto; padding: 18px 22px 60px; }
  header { display: flex; align-items: center; gap: 12px; margin-bottom: 18px; }
  .back { width: 36px; height: 36px; border-radius: 12px; border: 1px solid var(--border); background: var(--surface); cursor: pointer;
    display: grid; place-items: center; transition: background .15s; }
  .back:hover { background: var(--elevated); }
  h1 { font-size: 24px; letter-spacing: -.02em; margin: 0; font-weight: 650; }
  .date { color: var(--text-muted); font-size: 13.5px; margin-top: 1px; }
  .grow { flex: 1; }
  .ghost { border: 1px solid var(--border); background: var(--surface); border-radius: 999px; padding: 7px 13px; font-size: 13px; cursor: pointer; }
  .ghost:hover { border-color: var(--accent); }
  .ghost[aria-pressed="true"] { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
  /* the "tell Gink" box */
  .ask { display: flex; align-items: center; gap: 10px; background: var(--surface); border: 1px solid var(--border); border-radius: 18px;
    padding: 8px 8px 8px 16px; box-shadow: 0 10px 30px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04); transition: border-color .2s, box-shadow .2s; }
  .ask:focus-within { border-color: var(--accent); box-shadow: 0 10px 34px rgba(80,140,20,.14); }
  .ask svg { color: var(--accent); flex: none; }
  .ask input { flex: 1; border: 0; background: transparent; outline: none; font-size: 15.5px; padding: 8px 0; color: var(--text-main); min-width: 0; }
  .go { border: 0; border-radius: 12px; background: var(--accent); color: var(--on-accent); padding: 9px 16px; font-weight: 600; cursor: pointer; }
  .go:disabled { opacity: .5; cursor: default; }
  .status { min-height: 20px; margin: 8px 4px 0; font-size: 13.5px; color: var(--text-muted); }
  .status.busy { background: linear-gradient(90deg, var(--text-muted) 0%, var(--accent) 50%, var(--text-muted) 100%); background-size: 200% 100%;
    -webkit-background-clip: text; background-clip: text; color: transparent; animation: shimmer 1.6s linear infinite; }
  @keyframes shimmer { to { background-position: -200% 0; } }
  /* summary cards */
  .cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0 16px; }
  .card { text-align: left; border: 1px solid var(--border); background: var(--surface); border-radius: var(--radius); padding: 14px; cursor: pointer;
    transition: transform .15s, border-color .15s, box-shadow .15s; }
  .card:hover { transform: translateY(-1px); box-shadow: 0 8px 22px rgba(0,0,0,.06); }
  .card.on { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
  .card .ic { width: 34px; height: 34px; border-radius: 11px; display: grid; place-items: center; font-size: 17px; margin-bottom: 10px; }
  .card b { display: block; font-size: 24px; letter-spacing: -.02em; line-height: 1; }
  .card span { color: var(--text-muted); font-size: 13px; }
  /* segmented filter */
  .seg { display: flex; gap: 4px; padding: 4px; background: var(--elevated); border-radius: 14px; overflow-x: auto; margin-bottom: 18px; scrollbar-width: none; }
  .seg button { border: 0; background: transparent; padding: 8px 14px; border-radius: 10px; cursor: pointer; white-space: nowrap; font-size: 13.5px; color: var(--text-muted); }
  .seg button.on { background: var(--surface); color: var(--text-main); box-shadow: 0 1px 3px rgba(0,0,0,.1); font-weight: 600; }
  /* sections + rows */
  .sec { margin: 22px 0 8px; display: flex; align-items: center; gap: 8px; font-size: 12.5px; font-weight: 650; letter-spacing: .04em;
    text-transform: uppercase; color: var(--text-muted); }
  .sec .n { background: var(--elevated); border-radius: 999px; padding: 1px 8px; font-size: 11.5px; letter-spacing: 0; }
  .sec.overdue { color: var(--danger); }
  .list { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
  .row { display: flex; align-items: flex-start; gap: 12px; padding: 13px 14px; border-top: 1px solid var(--border); position: relative; }
  .row:first-child { border-top: 0; }
  .row.step { padding-left: 50px; background: color-mix(in srgb, var(--elevated) 45%, transparent); }
  .chk { width: 22px; height: 22px; border-radius: 50%; border: 1.8px solid var(--border); background: transparent; cursor: pointer; flex: none;
    display: grid; place-items: center; margin-top: 1px; transition: border-color .15s, background .2s, transform .15s; }
  .chk:hover { border-color: var(--accent); transform: scale(1.06); }
  .chk svg { opacity: 0; transform: scale(.4); transition: all .2s cubic-bezier(.3,1.6,.5,1); color: var(--on-accent); }
  .row.done .chk { background: var(--accent); border-color: var(--accent); }
  .row.done .chk svg { opacity: 1; transform: scale(1); }
  .row.done .t { color: var(--text-muted); text-decoration: line-through; text-decoration-color: color-mix(in srgb, var(--text-muted) 60%, transparent); }
  .body { flex: 1; min-width: 0; }
  .t { font-size: 15px; word-wrap: break-word; }
  .meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
  .chip { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; padding: 3px 9px; border-radius: 999px; background: var(--elevated); color: var(--text-muted); }
  .chip.when { color: var(--accent); background: var(--accent-soft); }
  .chip.late { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }
  .bar { height: 5px; width: 120px; background: var(--elevated); border-radius: 999px; overflow: hidden; align-self: center; }
  .bar i { display: block; height: 100%; background: var(--accent); border-radius: 999px; }
  .kind { font-size: 18px; opacity: .9; margin-top: 1px; }
  .del { opacity: 0; border: 0; background: transparent; cursor: pointer; padding: 4px; border-radius: 8px; color: var(--text-muted); transition: opacity .15s; }
  .row:hover .del, .row:focus-within .del { opacity: 1; }
  .del:hover { color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent); }
  @media (hover: none) { .del { opacity: .7; } }
  .row.leaving { animation: leave .28s ease forwards; }
  @keyframes leave { to { opacity: 0; transform: translateX(16px); } }
  .row.arrive { animation: arrive .35s cubic-bezier(.2,.8,.2,1); }
  @keyframes arrive { from { opacity: 0; transform: translateY(-6px); } }
  /* empty state */
  .empty { text-align: center; padding: 46px 20px; border: 1px dashed var(--border); border-radius: var(--radius); background: var(--surface); }
  .empty .big { font-size: 40px; }
  .empty h3 { margin: 8px 0 4px; font-size: 18px; }
  .empty p { color: var(--text-muted); margin: 0 0 16px; font-size: 14px; }
  .ex { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
  .done-toggle { margin-top: 18px; }
  @media (max-width: 640px) {
    .wrap { padding: 12px 14px 48px; }
    .cards { grid-template-columns: repeat(2, 1fr); gap: 10px; }
    h1 { font-size: 21px; }
    .bar { width: 80px; }
  }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style></head><body>
<div class="wrap">
  <header>
    <button class="back" id="back" aria-label="Back"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg></button>
    <div><h1>Workspace</h1><div class="date" id="date"></div></div>
    <div class="grow"></div>
    <button class="ghost" id="clear" hidden>Clear done</button>
  </header>

  <div class="ask">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/></svg>
    <input id="cmd" placeholder="Tell Gink what to add — “remind me to call mum at 6”" aria-label="Tell Gink what to add" autocomplete="off">
    <button class="go" id="go">Add</button>
  </div>
  <div class="status" id="status" aria-live="polite"></div>

  <div class="cards" id="cards"></div>
  <div class="seg" id="seg" role="tablist"></div>
  <div id="lists"></div>
  <div class="done-toggle"><button class="ghost" id="showdone" aria-pressed="false">Show finished</button></div>
</div>
<script>
  var ginkEvents = [], ginkSeq = 0, ginkPage = String(Date.now()) + Math.random().toString(36).slice(2, 8);
  function ginkEmit(type, value) { ginkEvents.push({seq: ++ginkSeq, type: type, value: value === undefined ? null : value}); }
  function ginkTake(ack, page) {   /* ui/page_events.py: kept until the next poll confirms it arrived */
    if (page === ginkPage) ginkEvents = ginkEvents.filter(function (e) { return e.seq > ack; });
    return JSON.stringify({page: ginkPage, events: ginkEvents});
  }
  var $ = function (id) { return document.getElementById(id); };
  var KINDS = [["", "All"], ["task", "Tasks"], ["reminder", "Reminders"], ["alarm", "Alarms"], ["timer", "Timers"], ["event", "Events"]];
  var ICON = {task: "\u2705", reminder: "\uD83D\uDD14", alarm: "\u23F0", timer: "\u23F2\uFE0F", event: "\uD83D\uDCC5"};
  var CARDS = [["task", "Open tasks", "\u2705", "rgba(47,158,68,.14)"], ["upcoming", "Upcoming", "\uD83D\uDD14", "rgba(232,89,12,.12)"],
               ["alarm", "Alarms", "\u23F0", "rgba(59,91,219,.12)"], ["timer", "Timers", "\u23F2\uFE0F", "rgba(174,62,201,.12)"]];
  var S = {data: null, kind: "", showDone: false, busy: false};
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); }
  function check() { return '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>'; }
  function trash() { return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/></svg>'; }
  function row(it, step) {
    var meta = [];
    if (it.when) meta.push('<span class="chip ' + (it.overdue ? 'late' : 'when') + '">' + (it.overdue ? 'Overdue \u00b7 ' : '') + esc(it.when) + '</span>');
    if (it.device) meta.push('<span class="chip">On your device</span>');
    if (it.steps_total) meta.push('<span class="chip">' + it.steps_done + '/' + it.steps_total + ' steps</span><span class="bar"><i style="width:' +
      Math.round(100 * it.steps_done / it.steps_total) + '%"></i></span>');
    return '<div class="row' + (step ? ' step' : '') + (it.done ? ' done' : '') + '" data-id="' + it.id + '">' +
      '<button class="chk" data-act="' + (it.done ? 'undone' : 'done') + '" aria-label="' + (it.done ? 'Mark as not done' : 'Mark as done') + '">' + check() + '</button>' +
      '<div class="body"><div class="t">' + esc(it.title) + '</div>' + (meta.length ? '<div class="meta">' + meta.join('') + '</div>' : '') + '</div>' +
      (step ? '' : '<span class="kind" aria-hidden="true">' + (ICON[it.kind] || '\u2022') + '</span>') +
      '<button class="del" data-act="delete" aria-label="Delete">' + trash() + '</button></div>';
  }
  function render() {
    var d = S.data; if (!d) return;
    $("date").textContent = d.date;
    $("cards").innerHTML = CARDS.map(function (c) {
      var on = (c[0] === "upcoming" ? S.kind === "reminder" : S.kind === c[0]);
      return '<button class="card' + (on ? ' on' : '') + '" data-card="' + c[0] + '"><div class="ic" style="background:' + c[3] + '">' + c[2] + '</div><b>' +
        (d.stats[c[0]] || 0) + '</b><span>' + c[1] + '</span></button>';
    }).join('');
    $("seg").innerHTML = KINDS.map(function (k) { return '<button class="' + (S.kind === k[0] ? 'on' : '') + '" data-kind="' + k[0] + '" role="tab">' + k[1] + '</button>'; }).join('');
    $("clear").hidden = !d.done_count;
    $("showdone").setAttribute("aria-pressed", S.showDone ? "true" : "false");
    $("showdone").textContent = S.showDone ? "Hide finished" : "Show finished" + (d.done_count ? " (" + d.done_count + ")" : "");
    if (!d.groups.length) {
      $("lists").innerHTML = '<div class="empty"><div class="big">\u2728</div><h3>' + (S.kind ? 'Nothing here yet' : 'All clear') + '</h3>' +
        '<p>Tell Gink in your own words, and it keeps track for you.</p><div class="ex">' +
        ["Remind me to drink water in 30 minutes", "Wake me up at 6:30", "Help me plan my exam revision", "Set a timer for 10 minutes"]
          .map(function (x) { return '<button class="ghost" data-ex="' + esc(x) + '">' + esc(x) + '</button>'; }).join('') + '</div></div>';
      return;
    }
    $("lists").innerHTML = d.groups.map(function (g) {
      return '<div class="sec ' + g.key + '">' + esc(g.title) + ' <span class="n">' + g.items.length + '</span></div><div class="list">' +
        g.items.map(function (it) { return row(it, false) + (it.steps || []).map(function (s) { return row(s, true); }).join(''); }).join('') + '</div>';
    }).join('');
  }
  function setData(d) { S.data = d; S.kind = d.kind || ""; S.showDone = !!d.show_done; render(); }
  function setStatus(text, busy) { var s = $("status"); s.textContent = text || ""; s.className = "status" + (busy ? " busy" : ""); S.busy = !!busy; $("go").disabled = !!busy; }
  function send() { var v = $("cmd").value.trim(); if (!v || S.busy) return; setStatus("Working on it\u2026", true); ginkEmit("command", v); $("cmd").value = ""; }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("button"); if (!b) return;
    if (b.id === "back") return ginkEmit("back");
    if (b.id === "go") return send();
    if (b.id === "clear") return ginkEmit("clear_done");
    if (b.id === "showdone") return ginkEmit("show_done", !S.showDone);
    if (b.hasAttribute("data-kind")) return ginkEmit("filter", b.getAttribute("data-kind"));
    if (b.hasAttribute("data-card")) { var c = b.getAttribute("data-card"); return ginkEmit("filter", c === "upcoming" ? "reminder" : (S.kind === c ? "" : c)); }
    if (b.hasAttribute("data-ex")) { $("cmd").value = b.getAttribute("data-ex"); $("cmd").focus(); return; }
    var r = b.closest(".row"), act = b.getAttribute("data-act");
    if (r && act) {
      if (act === "delete") { r.classList.add("leaving"); setTimeout(function () { ginkEmit("delete", +r.getAttribute("data-id")); }, 240); }
      else { r.classList.toggle("done", act === "done"); setTimeout(function () { ginkEmit(act, +r.getAttribute("data-id")); }, 220); }
    }
  });
  $("cmd").addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
  ginkEmit("ready");
</script></body></html>
"""
