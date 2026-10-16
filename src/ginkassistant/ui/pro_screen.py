"""
Gink Pro: upgrade with the way people pay in YOUR country.

* Country comes from the server (your saved choice, else your device's time
  zone / region) and can be changed here.
* Plans are priced in local money; methods are the local ones (Wave, Orange
  Money, M-Pesa...) when available, otherwise card.
* Paying opens the provider's secure checkout in your browser (where
  mobile-money approvals and card 3-D Secure work properly). Gink then
  checks with the server until the payment is confirmed -- approving on
  your phone can take a minute.
"""

import asyncio
from datetime import datetime

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW

from ..services.api_client import ApiClient, ApiError
from ..services.device_region import region_locale, timezone_name
from .theme import (ACCENT, ACCENT_SOFT, BG_ELEVATED, BG_MAIN, BG_SURFACE, DANGER, ON_ACCENT,
                    TEXT_MAIN, TEXT_MUTED)

BENEFITS = [
    "\u26a1  Much higher daily limits",
    "\U0001F4F7  Photo, PDF and document analysis",
    "\U0001F5E3\ufe0f  Premium natural voices",
    "\U0001F3A8  Media Studio (images & video)",
    "\u2600\ufe0f  Morning briefing, sync and memory on all your devices",
]
POLL_SECONDS = 4
POLL_FOR = 15 * 60


def _open_in_browser(app, url: str) -> bool:
    try:
        res = app.task_runner.device.open_url(url)
        if getattr(res, "ok", False):
            return True
    except Exception:
        pass
    try:
        import webbrowser
        return webbrowser.open(url)
    except Exception:
        return False


class ProScreen:
    def __init__(self, app: toga.App, on_back, on_status_change=None):
        self.app = app
        self.on_back = on_back
        self.on_status_change = on_status_change
        self.opts = None
        self.plan = None
        self.method = None
        self.reference = None
        self._watching = False
        self.view = self._build()
        try:
            asyncio.get_event_loop().create_task(self.load())
        except RuntimeError:
            pass

    @property
    def api(self):
        return ApiClient(self.app.state.base_url)

    @property
    def token(self):
        return getattr(self.app, "session_token", None)

    # ------------------------------------------------------------------ UI
    def _build(self):
        bg = BG_SURFACE
        back = toga.Button("\u2190 Back", on_press=lambda w: self.close(),
                           style=Pack(margin_right=12, color=TEXT_MUTED, background_color=BG_ELEVATED))
        title = toga.Label("\u2728 Gink Pro", style=Pack(font_size=22, font_weight="bold", color=TEXT_MAIN,
                                                        background_color=bg))
        header = toga.Box(children=[back, title],
                          style=Pack(direction=ROW, align_items=CENTER, margin=(16, 18, 6, 18), background_color=bg))
        self.status = toga.Label("Loading\u2026", style=Pack(margin=(0, 20, 10, 20), color=TEXT_MUTED,
                                                            background_color=bg))
        benefits = toga.Box(children=[toga.Label(b, style=Pack(margin_bottom=5, color=TEXT_MAIN,
                                                               background_color=BG_ELEVATED)) for b in BENEFITS],
                            style=Pack(direction=COLUMN, margin=(0, 18, 12, 18), background_color=BG_ELEVATED))
        benefits_wrap = toga.Box(children=[toga.Box(children=[benefits], style=Pack(margin=12, background_color=BG_ELEVATED))],
                                 style=Pack(direction=COLUMN, margin=(0, 18, 14, 18), background_color=BG_ELEVATED))

        self.country_label = toga.Label("", style=Pack(flex=1, color=TEXT_MAIN, background_color=bg))
        self.country_pick = toga.Selection(items=[""], on_change=self._country_changed,
                                           style=Pack(width=220, color=TEXT_MAIN, background_color=BG_ELEVATED))
        self._suppress_country = True
        country_row = toga.Box(children=[self.country_label, self.country_pick],
                               style=Pack(direction=ROW, align_items=CENTER, margin=(0, 20, 12, 20), background_color=bg))

        self.plans_box = toga.Box(style=Pack(direction=ROW, margin=(0, 18, 10, 18), background_color=bg))
        self.methods_box = toga.Box(style=Pack(direction=ROW, margin=(0, 18, 6, 18), background_color=bg))
        self.methods_scroll = toga.ScrollContainer(content=self.methods_box, vertical=False,
                                                   style=Pack(height=52, background_color=bg))
        self.note = toga.Label("", style=Pack(margin=(0, 20, 8, 20), font_size=12, color=TEXT_MUTED, background_color=bg))
        self.pay_btn = toga.Button("Choose a plan and a way to pay", on_press=self._pay, enabled=False,
                                   style=Pack(margin=(4, 18, 6, 18), color=ON_ACCENT, background_color=ACCENT,
                                              font_weight="bold"))
        self.check_btn = toga.Button("I've paid \u2014 check now", on_press=self._check_now,
                                     style=Pack(margin=(0, 18, 6, 18), color=TEXT_MAIN, background_color=BG_ELEVATED))
        self.msg = toga.Label("", style=Pack(margin=(4, 20, 12, 20), color=ACCENT, background_color=bg))
        self.fine_print = toga.Label(
            "Pro is prepaid: it doesn't renew by itself, and buying again adds time to your current end date.",
            style=Pack(margin=(0, 20, 16, 20), font_size=11, color=TEXT_MUTED, background_color=bg))

        self.body = toga.Box(children=[header, self.status, benefits_wrap,
                                       toga.Label("Where are you paying from?", style=Pack(
                                           margin=(0, 20, 4, 20), font_weight="bold", color=TEXT_MAIN, background_color=bg)),
                                       country_row,
                                       toga.Label("Choose a plan", style=Pack(
                                           margin=(0, 20, 4, 20), font_weight="bold", color=TEXT_MAIN, background_color=bg)),
                                       self.plans_box,
                                       toga.Label("Pay with", style=Pack(
                                           margin=(4, 20, 4, 20), font_weight="bold", color=TEXT_MAIN, background_color=bg)),
                                       self.methods_scroll, self.note, self.pay_btn, self.msg, self.fine_print],
                             style=Pack(direction=COLUMN, background_color=bg))
        scroll = toga.ScrollContainer(content=self.body, horizontal=False, style=Pack(flex=1, background_color=bg))
        return toga.Box(children=[scroll], style=Pack(direction=COLUMN, flex=1, background_color=bg))

    def _chip(self, text, selected, on_press):
        return toga.Button(text, on_press=on_press,
                           style=Pack(margin=(0, 8, 0, 0),
                                      color=ON_ACCENT if selected else TEXT_MAIN,
                                      background_color=ACCENT if selected else BG_ELEVATED))

    # ------------------------------------------------------------------ data
    async def load(self, country: str = ""):
        if not self.token:
            self.status.text = "Sign out and sign in again to upgrade (your session isn't available)."
            return
        try:
            self.opts = await self.api.billing_options(self.token, tz=timezone_name(), locale=region_locale(),
                                                       country=country)
        except ApiError as exc:
            self.status.text = str(exc)
            self.status.style.color = DANGER
            return
        self._render()                       # show prices and methods right away
        try:
            self.usage = await asyncio.wait_for(self.api.ai_usage(self.token), timeout=8)
        except Exception:
            return                           # usage line is a nice-to-have
        self._render()

    def _render(self):
        o = self.opts
        st = o.get("status", {})
        u = getattr(self, "usage", None)
        today = f"  \u00b7  Today: {u['used']} of {u['limit']} messages used" if u else ""
        if st.get("plan") == "pro":
            until = datetime.fromtimestamp(st["pro_until"]).strftime("%d %B %Y")
            self.status.text = f"\u2705 You're on Gink Pro until {until}.{today}"
            self.status.style.color = ACCENT
        else:
            self.status.text = f"You're on the Free plan.{today}"
            self.status.style.color = TEXT_MUTED
        where = {"chosen": "your choice", "network": "your network", "timezone": "your device's time zone",
                 "locale": "your device's region", "unknown": "not detected \u2014 please choose"}.get(o.get("source"), "")
        self.country_label.text = (f"{o.get('flag', '')} {o.get('country_name') or 'Unknown'}  \u00b7  {where}")
        names = [c["name"] for c in o.get("countries", [])]
        self._codes = {c["name"]: c["code"] for c in o.get("countries", [])}
        self._suppress_country = True
        if names and list(self.country_pick.items) != names:
            self.country_pick.items = names
        if o.get("country_name") in names:
            self.country_pick.value = o["country_name"]
        self._suppress_country = False

        for box in (self.plans_box, self.methods_box):
            for c in list(box.children):
                box.remove(c)
        plans, methods = o.get("plans", []), o.get("methods", [])
        if not o.get("available"):
            self.note.text = ("Payments aren't set up on this Gink server yet. "
                              "(Server owner: see deploy/README.md \u2192 Payments.)")
            self._update_pay()
            return
        if self.plan not in [p["id"] for p in plans]:
            self.plan = plans[0]["id"] if plans else None
        if self.method not in [m["id"] for m in methods]:
            self.method = methods[0]["id"] if methods else None
        for p in plans:
            extra = f"  ({p['per_month']}/mo)" if p["months"] > 1 else ""
            self.plans_box.add(self._chip(f"{p['label']} \u00b7 {p['display']}{extra}", p["id"] == self.plan,
                                          lambda w, pid=p["id"]: self._select(plan=pid)))
        for m in methods:
            self.methods_box.add(self._chip(m["name"], m["id"] == self.method,
                                            lambda w, mid=m["id"]: self._select(method=mid)))
        self.note.text = o.get("note", "")
        self._update_pay()

    def _select(self, plan=None, method=None):
        if plan:
            self.plan = plan
        if method:
            self.method = method
        self._render()

    def _update_pay(self):
        o = self.opts or {}
        p = next((x for x in o.get("plans", []) if x["id"] == self.plan), None)
        m = next((x for x in o.get("methods", []) if x["id"] == self.method), None)
        self.pay_btn.enabled = bool(p and m) and not self._watching
        self.pay_btn.text = f"Pay {p['display']} with {m['name']}" if (p and m) else "Choose a plan and a way to pay"

    def _country_changed(self, widget):
        if self._suppress_country or not widget.value:
            return
        code = self._codes.get(widget.value)
        if code and code != (self.opts or {}).get("country"):
            asyncio.get_event_loop().create_task(self._save_country(code))

    async def _save_country(self, code):
        try:
            await self.api.set_country(self.token, code)
        except ApiError as exc:
            self.msg.text = str(exc)
        await self.load(code)

    # ------------------------------------------------------------------ paying
    async def _pay(self, widget):
        self.msg.text = "Opening secure checkout\u2026"
        self.msg.style.color = TEXT_MUTED
        try:
            res = await self.api.checkout(self.token, self.plan, self.method, self.opts.get("country", ""))
        except ApiError as exc:
            self.msg.text = str(exc)
            self.msg.style.color = DANGER
            return
        self.reference = res["reference"]
        if not _open_in_browser(self.app, res["payment_url"]):
            self.msg.text = "Couldn't open your browser. Copy this link: " + res["payment_url"]
            return
        self.msg.text = ("Finish paying in your browser. For mobile money, approve the request on your phone "
                         "\u2014 Gink will update by itself.")
        self.msg.style.color = TEXT_MUTED
        if self.check_btn not in self.body.children:
            self.body.insert(self.body.children.index(self.msg), self.check_btn)
        self._watching = True
        self._update_pay()
        await self._watch(self.reference)

    async def _watch(self, ref):
        loop = asyncio.get_event_loop()
        end = loop.time() + POLL_FOR
        while self._watching and self.reference == ref and loop.time() < end:
            if await self._check(ref):
                return
            await asyncio.sleep(POLL_SECONDS)
        if self._watching and self.reference == ref:
            self._watching = False
            self.msg.text = "Still waiting for confirmation. If you paid, tap \u201cI've paid \u2014 check now\u201d."
            self._update_pay()

    async def _check(self, ref) -> bool:
        try:
            st = await self.api.billing_status(self.token, ref)
        except ApiError:
            return False
        pay = st.get("payment")
        if pay == "success":
            self._watching = False
            until = datetime.fromtimestamp(st["pro_until"]).strftime("%d %B %Y")
            self.msg.text = f"\U0001F389 Thank you! Gink Pro is active until {until}."
            self.msg.style.color = ACCENT
            if self.check_btn in self.body.children:
                self.body.remove(self.check_btn)
            if self.on_status_change:
                self.on_status_change(st)
            await self.load()
            return True
        if pay == "failed":
            self._watching = False
            self.msg.text = "The payment didn't go through, and nothing was charged for Pro. You can try again."
            self.msg.style.color = DANGER
            if self.check_btn in self.body.children:
                self.body.remove(self.check_btn)
            self._update_pay()
            return True
        return False

    async def _check_now(self, widget):
        if self.reference:
            self.msg.text = "Checking\u2026"
            if not await self._check(self.reference):
                self.msg.text = ("Not confirmed yet. Mobile-money approvals can take a minute \u2014 "
                                 "Gink keeps checking in the background.")
                if not self._watching:
                    self._watching = True
                    self._update_pay()
                    await self._watch(self.reference)

    def close(self):
        self._watching = False
        self.on_back()


def build_pro_screen(app, on_back, on_status_change=None):
    return ProScreen(app, on_back, on_status_change).view
