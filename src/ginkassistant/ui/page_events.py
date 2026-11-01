"""
Page -> Python events for the HTML screens (chat, login, Media Studio).

Toga's WebView can't call Python, so each page queues what the person did (ginkEmit) and Python
polls ginkTake() a few times a second. The first version emptied the queue as soon as the page
answered -- so when a slow phone answered after Python had stopped waiting (2 s), the events
were gone: a sent message, a tap. Now every event carries a number, and the page keeps it until the
NEXT poll says it arrived (ginkTake(ack, page)). Python skips numbers it has already handled, so
an event is handled exactly once, even if an answer comes late or twice. A reloaded page has a new
page id, so counting starts again.

The page side is QUEUE_JS (the same three functions in every page):
  ginkEmit(type, value)    -- queue an event
  ginkTake(ack, page)      -- drop events up to `ack` (if `page` is this page), return the rest
"""
import asyncio
import json

QUEUE_JS = r"""  var ginkEvents = [], ginkSeq = 0, ginkPage = String(Date.now()) + Math.random().toString(36).slice(2, 8);
  function ginkEmit(type, value) { ginkEvents.push({seq: ++ginkSeq, type: type, value: value === undefined ? null : value}); }
  function ginkTake(ack, page) {   /* ui/page_events.py: kept until the next poll confirms it arrived */
    if (page === ginkPage) ginkEvents = ginkEvents.filter(function (e) { return e.seq > ack; });
    return JSON.stringify({page: ginkPage, events: ginkEvents});
  }
"""


class EventQueue:
    def __init__(self):
        self.page, self.ack = "", 0

    def accept(self, raw) -> list:
        """The page's answer -> the events not handled yet, as [{"type", "value"}]."""
        try:
            data = json.loads(raw) if isinstance(raw, str) and raw else raw
            if isinstance(data, str):                 # some platforms JSON-encode the string again
                data = json.loads(data)
        except Exception:
            return []
        if isinstance(data, list):                    # an old page without numbers
            return [e for e in data if isinstance(e, dict)]
        if not isinstance(data, dict):
            return []
        page = str(data.get("page") or "")
        if page != self.page:                         # a new or reloaded page: count from the start
            self.page, self.ack = page, 0
        fresh = []
        for e in data.get("events") or []:
            try:
                seq = int(e.get("seq") or 0)
            except (AttributeError, TypeError, ValueError):
                continue
            if seq > self.ack:
                fresh.append((seq, {"type": e.get("type"), "value": e.get("value")}))
        if fresh:
            self.ack = max(s for s, _ in fresh)
        return [ev for _, ev in sorted(fresh, key=lambda x: x[0])]

    async def take(self, web_view, timeout: float = 2.0) -> list:
        """Never raises; [] if the page didn't answer in time (its events stay queued for next time)."""
        try:
            raw = await asyncio.wait_for(
                web_view.evaluate_javascript(f"ginkTake({self.ack}, {json.dumps(self.page)})"), timeout=timeout)
        except Exception:
            return []
        return self.accept(raw)
