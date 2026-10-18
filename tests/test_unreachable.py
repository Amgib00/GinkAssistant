"""When the server can't be reached, the app says why and what to do (plus a short detail)."""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx, pytest
from ginkassistant.services.api_client import unreachable, ApiClient, ApiError


@pytest.mark.parametrize("exc, expect", [
    (httpx.ReadTimeout("timed out"), "can take up to a minute"),
    (httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: certificate is not yet valid"), "date and time"),
    (httpx.ConnectError("[Errno -2] Name or service not known"), "Wi-Fi or mobile data is on"),
    (httpx.ConnectError("[Errno 7] No address associated with hostname"), "Wi-Fi or mobile data is on"),
    (httpx.ConnectError("[Errno 101] Network is unreachable"), "no internet connection"),
    (httpx.ConnectError("[Errno 111] Connection refused"), "restarting"),
    (httpx.ConnectError(""), "Can't reach the Gink server"),
])
def test_reasons(exc, expect):
    msg = str(unreachable(exc))
    assert expect in msg and "(Details: " in msg and type(exc).__name__ in msg


def test_the_client_uses_it(monkeypatch):
    real = httpx.AsyncClient
    class Fail(real):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] bad")))
            super().__init__(*a, **k)
    monkeypatch.setattr(httpx, "AsyncClient", Fail)
    c = ApiClient("https://gink-server.onrender.com")
    with pytest.raises(ApiError, match="date and time"):
        asyncio.run(c._post("/auth/login", {}, "x"))
