"""
The Android app's window (0.1.155): no teal title bar, status bars in the page's colours, and a
keyboard that makes room instead of covering the page.

Briefcase's Android template draws a teal ActionBar ("Gink" and a menu) and a dark-teal status bar
(colorPrimary / colorPrimaryDark). Its newer, edge-to-edge versions (Android 15's rules) also stopped
the keyboard from shrinking the app: the keyboard covered the bottom of the page and Android's WebView
panned the page around to show the box you were typing in (the message box jumping to the top of the
screen, the conversation disappearing).

pyproject.toml asks for a theme without an ActionBar (base_theme). This module, called by app.py:
  * hides the ActionBar anyway if there is one (an older build folder) -- not in Gink Genie, whose bar
    holds Home, Back, Reload and Open in browser;
  * makes the app end at the top of the keyboard (adjustResize, plus the keyboard's insets on the
    edge-to-edge template, whose own insets listener only knew the system bars);
  * colours the status and navigation bars like the page (set_bars, from the page's "bars" event:
    white with dark icons, or dark with light icons in the dark theme and behind the lock screen).

Nothing here may crash the app: every Android call is guarded and only noted (state()["error"]).
Off Android every function does nothing and returns False. Gink Genie has an identical copy
(src/ginkgenie/android_chrome.py -- the two apps don't share code), so this file imports nothing of Gink's.
"""
import os
import re
import sys

LOGIN_BG = "#EDF0E9"         # the sign-in page's soft background (ui/login_screen.py --soft)
DEFAULT_BG = "#FFFFFF"       # the chat page, light theme (ui/theme.py BG_MAIN)
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_state = {"setup": False, "listener": None, "bars": None, "error": ""}


def is_android() -> bool:
    return hasattr(sys, "getandroidapilevel") or "ANDROID_ARGUMENT" in os.environ


def state() -> dict:
    return dict(_state)


def _note(what: str, exc: Exception) -> None:
    _state["error"] = f"{what}: {type(exc).__name__}: {exc}"
    print(f"[Gink] Android window -- {_state['error']}", flush=True)


def _java():
    from java import cast, dynamic_proxy, jclass     # Chaquopy, only on Android
    return cast, dynamic_proxy, jclass


def _activity(app):
    impl = getattr(app, "_impl", None)
    return getattr(impl, "native", None)              # toga_android: the MainActivity


def normal_hex(color) -> str:
    """'#fff' -> '#FFFFFF'; anything that isn't a plain hex colour -> ''."""
    c = str(color or "").strip()
    if not _HEX.match(c):
        return ""
    if len(c) == 4:
        c = "#" + "".join(ch * 2 for ch in c[1:])
    return c.upper()


def _content_view(act):
    _cast, _proxy, jclass = _java()
    return act.findViewById(jclass("android.R$id").content)


def _status_bar_view(content):
    """The edge-to-edge template paints the status bar with a plain View next to the content view
    (MainActivity.setContentView). None on older templates, whose window isn't edge-to-edge."""
    cast, _proxy, jclass = _java()
    parent = content.getParent()
    if parent is None:
        return None
    group = cast(jclass("android.view.ViewGroup"), parent)
    for i in range(group.getChildCount()):
        child = group.getChildAt(i)
        if child is not None and not child.equals(content) and str(child.getClass().getName()) == "android.view.View":
            return child
    return None


def _hide_action_bar(act) -> None:
    bar = act.getSupportActionBar()
    if bar is not None:
        bar.hide()


def _keyboard_makes_room(act) -> None:
    cast, dynamic_proxy, jclass = _java()
    act.getWindow().setSoftInputMode(jclass("android.view.WindowManager$LayoutParams").SOFT_INPUT_ADJUST_RESIZE)
    content = _content_view(act)
    status = _status_bar_view(content)
    if status is None:                     # not edge-to-edge: adjustResize already shrinks the app
        return
    ViewCompat = jclass("androidx.core.view.ViewCompat")
    Type = jclass("androidx.core.view.WindowInsetsCompat$Type")
    Margins = jclass("android.view.ViewGroup$MarginLayoutParams")

    class KeyboardInsets(dynamic_proxy(jclass("androidx.core.view.OnApplyWindowInsetsListener"))):
        """The template's listener (system bars as margins, the status bar's height) + the keyboard."""
        def onApplyWindowInsets(self, view, insets):
            try:
                bars = insets.getInsets(Type.systemBars() | Type.displayCutout())
                keyboard = insets.getInsets(Type.ime())
                want = (bars.left, bars.top, bars.right, max(bars.bottom, keyboard.bottom))
                lp = cast(Margins, view.getLayoutParams())
                if (lp.leftMargin, lp.topMargin, lp.rightMargin, lp.bottomMargin) != want:
                    lp.setMargins(*want)
                    view.setLayoutParams(lp)
                slp = status.getLayoutParams()
                if slp.height != bars.top:
                    slp.height = bars.top
                    status.setLayoutParams(slp)
            except Exception as exc:       # never let an exception reach Android
                _note("keyboard insets", exc)
            return insets

    listener = KeyboardInsets()
    _state["listener"] = listener          # keep it alive
    ViewCompat.setOnApplyWindowInsetsListener(content, listener)
    ViewCompat.requestApplyInsets(content)


def setup(app, hide_title_bar: bool = True) -> bool:
    """Once, when the main window exists (app.py). True when everything worked."""
    if not is_android():
        return False
    act = _activity(app)
    if act is None:
        return False
    ok = True
    _state["bars"] = None                  # a new activity: colour its bars again
    steps = ((("title bar", _hide_action_bar),) if hide_title_bar else ()) + (("keyboard", _keyboard_makes_room),)
    for what, step in steps:
        try:
            step(act)
        except Exception as exc:
            ok = False
            _note(what, exc)
    _state["setup"] = True
    if hide_title_bar:                     # Gink: the status bar is the page's colour from the start
        set_bars(app, DEFAULT_BG, False)
    return ok


def set_bars(app, color, dark: bool) -> bool:
    """The status bar (and the navigation bar's strip) in the page's colour, icons readable on it."""
    if not is_android():
        return False
    hexa = normal_hex(color)
    act = _activity(app)
    if not hexa or act is None:
        return False
    if _state["bars"] == (hexa, bool(dark)):
        return True
    try:
        _cast, _proxy, jclass = _java()
        c = jclass("android.graphics.Color").parseColor(hexa)
        window = act.getWindow()
        decor = window.getDecorView()
        window.setStatusBarColor(c)                  # Android 14 and older
        window.setNavigationBarColor(c)
        decor.setBackgroundColor(c)                  # behind the gesture / navigation bar (edge-to-edge)
        status = _status_bar_view(_content_view(act))
        if status is not None:
            status.setBackgroundColor(c)             # Android 15+: the template paints the status bar itself
        controller = jclass("androidx.core.view.WindowCompat").getInsetsController(window, decor)
        controller.setAppearanceLightStatusBars(not dark)
        controller.setAppearanceLightNavigationBars(not dark)
        _state["bars"] = (hexa, bool(dark))
        return True
    except Exception as exc:
        _note("bar colours", exc)
        return False
