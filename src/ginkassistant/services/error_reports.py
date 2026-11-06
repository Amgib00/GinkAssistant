"""
Tells the Gink server when something breaks in the app, so problems are found without anyone having to
report them (owner dashboard: "Problems in the apps"). What's sent: the kind of error, its message and
where in Gink's code -- never chats, files or what the person typed. The server removes emails and keys
again. Off with Settings > Privacy > Send error reports (pref "send_errors").

install(app) hooks uncaught errors (main thread, other threads, asyncio); report(exc) is for errors
Gink catches and shows ("Something went wrong").
"""
import asyncio
import platform as _platform
import sys
import threading
import traceback

MAX_PER_RUN = 20
_sent = set()
_state = {"app": None, "count": 0}


def _enabled() -> bool:
    app = _state["app"]
    if app is None:
        return False
    try:
        from . import prefs
        return prefs.load(app).get("send_errors", True) is not False
    except Exception:
        return True


def _platform_name() -> str:
    from .platform_utils import is_android
    if is_android():
        return "android"
    if sys.platform == "darwin":
        return "ios" if _platform.system() == "iOS" else "macos"
    return "windows" if sys.platform.startswith("win") else sys.platform


def payload(exc: BaseException) -> dict:
    stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-6000:]
    return {"kind": type(exc).__name__, "message": str(exc)[:300], "stack": stack, "platform": _platform_name(),
            "version": str(getattr(_state["app"], "version", "") or "?")}


async def _send(data: dict) -> None:
    app = _state["app"]
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(app.state.base_url.rstrip("/") + "/errors", json=data)
    except Exception:
        pass                                               # never let reporting cause a problem itself


def report(exc: BaseException) -> None:
    """Send one error (each distinct error once per run, at most MAX_PER_RUN), if allowed."""
    if not _enabled() or _state["count"] >= MAX_PER_RUN:
        return
    data = payload(exc)
    key = (data["kind"], data["stack"][-400:])
    if key in _sent:
        return
    _sent.add(key)
    _state["count"] += 1
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_send(data))
    except RuntimeError:                                   # no loop here (another thread): send on our own
        threading.Thread(target=lambda: asyncio.run(_send(data)), daemon=True).start()


def install(app) -> None:
    _state["app"] = app
    previous = sys.excepthook

    def hook(kind, exc, tb):
        try:
            report(exc)
        finally:
            previous(kind, exc, tb)
    sys.excepthook = hook
    if hasattr(threading, "excepthook"):
        old_thread = threading.excepthook

        def thread_hook(args):
            try:
                if args.exc_value is not None:
                    report(args.exc_value)
            finally:
                old_thread(args)
        threading.excepthook = thread_hook


def watch_loop(loop) -> None:
    """Errors in background tasks (asyncio) are reported too."""
    old = loop.get_exception_handler()

    def handler(lp, context):
        exc = context.get("exception")
        if exc is not None:
            report(exc)
        if old is None:
            lp.default_exception_handler(context)
        else:
            old(lp, context)
    loop.set_exception_handler(handler)
