"""
Settings screen -- the home for things that got bolted on as stopgaps
elsewhere: the voice picker (currently also in main_screen.py's input
row -- kept there too for quick access, kept in sync here) and AI model
choice (previously hardcoded inline in services/groq_worker.py's
_cloud_reply()), plus genuinely new things: Launch at login (macOS-only,
real LaunchAgent implementation -- see services/launch_at_login.py for
why Windows/Linux and dev-mode runs don't get a working toggle) and an
About section.

Model list: starts from services/groq_worker.py's own DEFAULT_FALLBACKS
keys and PREFERRED_CASCADE (the models the app already has fallback
logic for), then refreshes against Groq's actual live model list for
this account once that call returns -- the static list is a reasonable
start, not a guess, but the live one is what's actually usable right
now.
"""

import asyncio

import toga
from toga.style import Pack
from toga.style.pack import CENTER, COLUMN, ROW

from ..services import launch_at_login
from ..services.groq_worker import DEFAULT_FALLBACKS, PREFERRED_CASCADE
from ..services.voice_bridge import VOICES

from ..services import server_config
from .theme import ACCENT, BG_ELEVATED, BG_SURFACE, COLOR_PRIMARY, DANGER, ON_ACCENT, TEXT_MAIN, TEXT_MUTED

BG_MAIN = BG_SURFACE

APP_VERSION = "0.1.0"


def _initial_model_choices() -> list:
    choices = [m for m in DEFAULT_FALLBACKS.keys() if m != "_global_default"]
    for m in PREFERRED_CASCADE:
        if m not in choices:
            choices.append(m)
    return choices


def build_settings_screen(app: toga.App, brain, selected_voice: dict, on_voice_changed, on_back, on_log_out=None):
    """brain: the GroqBrain instance (for preferred_model + live model
    refresh). selected_voice: the same {"value": ...} dict main_screen.py
    uses, so picking a voice here updates the one main_screen.py's own
    selector reads too. on_voice_changed(voice_key): called after a
    change here, so main_screen.py can update audio_engine.voice_key the
    same way its own selector does."""

    status_label = toga.Label("", style=Pack(color=TEXT_MUTED, font_size=12, margin_top=4, background_color=BG_MAIN))

    # -- AI model ---------------------------------------------------------

    model_selector = toga.Selection(
        items=_initial_model_choices(),
        value=brain.preferred_model if brain.preferred_model in _initial_model_choices() else _initial_model_choices()[0],
        style=Pack(width=320, margin_bottom=4, color=TEXT_MAIN, background_color=BG_ELEVATED),
    )

    def on_model_change(widget):
        brain.preferred_model = widget.value

    model_selector.on_change = on_model_change

    async def refresh_live_models():
        live = await brain.refresh_active_models()
        if not live:
            return
        current = model_selector.value
        model_selector.items = live
        if current in live:
            model_selector.value = current
        elif brain.preferred_model in live:
            model_selector.value = brain.preferred_model

    # -- Voice --------------------------------------------------------------

    voice_selector = toga.Selection(
        items=list(VOICES.keys()), value=selected_voice["value"],
        style=Pack(width=320, color=TEXT_MAIN, background_color=BG_ELEVATED),
    )

    def on_voice_change(widget):
        selected_voice["value"] = widget.value
        on_voice_changed(widget.value)

    voice_selector.on_change = on_voice_change

    # -- Launch at login ------------------------------------------------

    launch_supported = launch_at_login.is_supported()
    launch_switch = toga.Switch(
        "Launch Gink at login",
        value=launch_at_login.is_enabled() if launch_supported else False,
        enabled=launch_supported,
        style=Pack(color=TEXT_MAIN, background_color=BG_MAIN),
    )

    def on_launch_toggle(widget):
        ok = launch_at_login.enable() if widget.value else launch_at_login.disable()
        if not ok:
            status_label.text = "Couldn't update that -- see the app's logs for details."
            widget.value = not widget.value

    launch_switch.on_change = on_launch_toggle

    if launch_supported:
        launch_note = ""
    else:
        launch_note = (
            "Only available once Gink is installed as a packaged app on macOS "
            "-- not from a `python -m ginkassistant` dev run, and not yet "
            "implemented for Windows or Linux."
        )

    # -- Login server -------------------------------------------------------

    server_input = toga.TextInput(
        value=server_config.saved_url(app) or "",
        placeholder=app.state.base_url,
        style=Pack(width=320, margin_bottom=6, color=TEXT_MAIN, background_color=BG_ELEVATED),
    )
    server_status = toga.Label("", style=Pack(font_size=12, color=TEXT_MUTED, margin_top=4, background_color=BG_MAIN))

    async def on_test_server(widget):
        server_status.text = "Checking\u2026"
        server_status.style.color = TEXT_MUTED
        ok, msg = await server_config.check_server(server_input.value or app.state.base_url)
        server_status.text = msg
        server_status.style.color = ACCENT if ok else DANGER

    def on_save_server(widget):
        url = server_config.save_url(app, server_input.value or "")
        app.state.base_url = server_config.resolve_base_url(app)
        server_input.value = url
        server_status.text = f"Saved. Login now uses {app.state.base_url}"
        server_status.style.color = ACCENT

    server_buttons = toga.Box(
        style=Pack(direction=ROW, background_color=BG_MAIN),
        children=[
            toga.Button("Test connection", on_press=on_test_server,
                        style=Pack(margin_right=8, color=TEXT_MAIN, background_color=BG_ELEVATED)),
            toga.Button("Save", on_press=on_save_server,
                        style=Pack(color=ON_ACCENT, background_color=ACCENT, font_weight="bold")),
        ],
    )

    # -- Memory -------------------------------------------------------------
    memory = getattr(app, "memory", None)
    memory_box = toga.Box(style=Pack(direction=COLUMN, background_color=BG_MAIN))

    def refresh_memory():
        for child in list(memory_box.children):
            memory_box.remove(child)
        items = memory.list() if memory else []
        if not items:
            memory_box.add(toga.Label(
                "Nothing yet. Say \u201cremember that my exams start on 12 November\u201d in the chat.",
                style=Pack(font_size=12, color=TEXT_MUTED, background_color=BG_MAIN)))
            return
        for m in items:
            memory_box.add(toga.Box(
                style=Pack(direction=ROW, align_items=CENTER, margin_bottom=6, background_color=BG_MAIN),
                children=[
                    toga.Label(m["text"], style=Pack(flex=1, color=TEXT_MAIN, background_color=BG_MAIN)),
                    toga.Button("Forget", on_press=lambda w, uid=m["uid"]: (memory.forget(uid), refresh_memory()),
                                style=Pack(margin_left=8, color=DANGER, background_color=BG_ELEVATED)),
                ]))

    def forget_all(widget):
        if memory:
            memory.clear()
        refresh_memory()

    refresh_memory()
    memory_section_items = [
        toga.Label("Gink uses these in every answer. They sync to your account.",
                   style=Pack(font_size=12, color=TEXT_MUTED, margin_bottom=8, background_color=BG_MAIN)),
        memory_box,
        toga.Button("Forget everything", on_press=forget_all,
                    style=Pack(width=160, margin_top=6, color=DANGER, background_color=BG_ELEVATED)),
    ]

    # -- Morning briefing ----------------------------------------------------
    from ..services import prefs as prefs_svc
    p = prefs_svc.load(app)
    brief_on = toga.Switch("Brief me every morning", value=bool(p.get("briefing_enabled", True)),
                           style=Pack(color=TEXT_MAIN, background_color=BG_MAIN, margin_bottom=8))
    brief_time = toga.TextInput(value=p.get("briefing_time", "07:30"), placeholder="07:30",
                                style=Pack(width=90, color=TEXT_MAIN, background_color=BG_ELEVATED))
    city_input = toga.TextInput(value=prefs_svc.city(app), placeholder="e.g. Dakar",
                                style=Pack(width=220, color=TEXT_MAIN, background_color=BG_ELEVATED))
    city_status = toga.Label("", style=Pack(font_size=12, color=ACCENT, margin_top=6, background_color=BG_MAIN))

    async def save_city(widget):
        name = (city_input.value or "").strip()
        if not name:
            prefs_svc.save(app, city="", briefing_city="")
            city_status.text = "Cleared \u2014 Gink will use an approximate location from your connection."
            city_status.style.color = TEXT_MUTED
            return
        city_status.text = "Checking\u2026"
        try:
            place = await app.task_runner.live.geocode(name)
        except Exception:
            place = None
        if place is None:
            city_status.text = f"Couldn't find \u201c{name}\u201d. Check the spelling (or you're offline)."
            city_status.style.color = DANGER
            return
        label = place["name"] + (f", {place['country']}" if place.get("country") else "")
        prefs_svc.save(app, city=label, briefing_city=label)
        city_input.value = label
        city_status.text = f"Saved: {label} ({place.get('tz') or 'time zone unknown'})."
        city_status.style.color = ACCENT

    location_items = [
        toga.Label("Used for weather, air quality, sunrise/sunset, prayer times and your morning briefing.",
                   style=Pack(font_size=12, color=TEXT_MUTED, margin_bottom=8, background_color=BG_MAIN)),
        toga.Box(style=Pack(direction=ROW, align_items=CENTER, background_color=BG_MAIN), children=[
            city_input,
            toga.Button("Save", on_press=save_city,
                        style=Pack(margin_left=8, color=ON_ACCENT, background_color=ACCENT, font_weight="bold")),
        ]),
        city_status,
    ]
    brief_speak = toga.Switch("Read it aloud", value=bool(p.get("briefing_speak", True)),
                              style=Pack(color=TEXT_MAIN, background_color=BG_MAIN, margin_top=8))
    brief_status = toga.Label("", style=Pack(font_size=12, color=ACCENT, margin_top=6, background_color=BG_MAIN))

    def save_briefing(widget):
        t = (brief_time.value or "").strip()
        import re as _re
        mt = _re.fullmatch(r"(\d{1,2})[:.](\d{2})", t)
        if not mt or int(mt.group(1)) > 23 or int(mt.group(2)) > 59:
            brief_status.text = "Use a 24-hour time like 07:30."
            brief_status.style.color = DANGER
            return
        prefs_svc.save(app, briefing_enabled=bool(brief_on.value), briefing_time=f"{int(mt.group(1)):02d}:{mt.group(2)}",
                       briefing_speak=bool(brief_speak.value))
        brief_status.text = "Saved. You can also say \u201cbrief me\u201d any time."
        brief_status.style.color = ACCENT

    briefing_items = [
        brief_on,
        toga.Box(style=Pack(direction=ROW, align_items=CENTER, background_color=BG_MAIN),
                 children=[toga.Label("Time", style=Pack(margin_right=8, color=TEXT_MUTED, background_color=BG_MAIN)),
                           brief_time]),
        brief_speak,
        toga.Button("Save", on_press=save_briefing,
                    style=Pack(width=100, margin_top=8, color=ON_ACCENT, background_color=ACCENT, font_weight="bold")),
        brief_status,
    ]

    # -- Sync ----------------------------------------------------------------
    sync = getattr(app, "_sync_service", None)

    def sync_text():
        if not getattr(app, "session_token", None):
            return "Sign out and back in to turn on sync."
        if sync is None:
            return "Sync starts when you open the chat."
        if sync.last_error:
            return sync.last_error
        if sync.last_ok:
            import time as _t
            mins = int((_t.time() - sync.last_ok) // 60)
            return "Synced just now" if mins < 1 else f"Last synced {mins} min ago"
        return "Waiting to sync\u2026"

    sync_label = toga.Label(sync_text(), style=Pack(color=TEXT_MAIN, background_color=BG_MAIN))

    async def sync_now(widget):
        if sync is None:
            return
        sync_label.text = "Syncing\u2026"
        await sync.sync_once()
        sync_label.text = sync_text()

    sync_items = [
        toga.Label("Chats, Workspace tasks/reminders and memories sync to your account, so they "
                   "follow you between your phone and computer. Alarms stay on each device.",
                   style=Pack(font_size=12, color=TEXT_MUTED, margin_bottom=8, background_color=BG_MAIN)),
        sync_label,
        toga.Button("Sync now", on_press=sync_now,
                    style=Pack(width=110, margin_top=8, color=TEXT_MAIN, background_color=BG_ELEVATED)),
    ]

    # -- Account ------------------------------------------------------------
    # Log out moved here from the main screen header.
    account_items = [
        toga.Label(
            "You'll need a new email code to sign back in.",
            style=Pack(font_size=12, color=TEXT_MUTED, margin_bottom=8, background_color=BG_MAIN),
        )
    ]
    if on_log_out is not None:
        account_items.append(toga.Button(
            "Log out", on_press=lambda w: on_log_out(),
            style=Pack(width=140, color=DANGER, background_color=BG_ELEVATED),
        ))

    # -- Layout -----------------------------------------------------------

    def _section(title: str, *children):
        box = toga.Box(style=Pack(direction=COLUMN, margin_bottom=24, background_color=BG_MAIN))
        box.add(toga.Label(title, style=Pack(font_size=15, font_weight="bold", color=TEXT_MAIN, margin_bottom=8, background_color=BG_MAIN)))
        for child in children:
            box.add(child)
        return box

    sections = [
        _section(
            "AI model",
            model_selector,
            toga.Label(
                "Starts from a known list, refreshing against what's actually live on your Groq account.",
                style=Pack(font_size=12, color=TEXT_MUTED, background_color=BG_MAIN),
            ),
        ),
        _section("Voice", voice_selector),
        _section(
            "Login server",
            server_input,
            server_buttons,
            server_status,
            toga.Label(
                "Phones need your hosted server address (see deploy/README.md) or your "
                "computer's Wi-Fi address, e.g. http://192.168.1.20:8000. Leave empty for the default.",
                style=Pack(font_size=12, color=TEXT_MUTED, margin_top=6, background_color=BG_MAIN),
            ),
        ),
        _section(
            "Launch at login",
            launch_switch,
            *( [toga.Label(launch_note, style=Pack(font_size=12, color=TEXT_MUTED, margin_top=4, background_color=BG_MAIN))] if launch_note else [] ),
        ),
        _section("Location", *location_items),
        _section("Memory", *memory_section_items),
        _section("Morning briefing", *briefing_items),
        _section("Sync", *sync_items),
        _section("Account", *account_items),
        _section(
            "About",
            toga.Label("Gink Assistant", style=Pack(font_size=14, font_weight="bold", color=TEXT_MAIN, background_color=BG_MAIN)),
            toga.Label(f"Version {APP_VERSION}", style=Pack(font_size=12, color=TEXT_MUTED, background_color=BG_MAIN)),
        ),
        status_label,
    ]

    back_button = toga.Button(
        "\u2190 Back", on_press=lambda w: on_back(), style=Pack(width=90, background_color=BG_ELEVATED, color=TEXT_MUTED)
    )
    header = toga.Box(
        style=Pack(direction=ROW, align_items=CENTER, margin=14, background_color=BG_MAIN),
        children=[back_button, toga.Label("Settings", style=Pack(font_size=18, font_weight="bold", color=TEXT_MAIN, margin_left=10, background_color=BG_MAIN))],
    )

    body = toga.Box(style=Pack(direction=COLUMN, margin=24, background_color=BG_MAIN), children=sections)
    scroll = toga.ScrollContainer(content=body, style=Pack(flex=1, background_color=BG_MAIN))

    root = toga.Box(style=Pack(direction=COLUMN, flex=1, background_color=BG_MAIN), children=[header, scroll])

    asyncio.create_task(refresh_live_models())
    return root