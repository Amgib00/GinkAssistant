"""Tests run the same everywhere: never with the developer's real .env (server address, AI keys...), and never
on the internet.

app.py loads the project's .env when imported. On the owner's Mac that made tests use the real Render
address and even call the real AI ("Wake Up Reminder"). GitHub has no .env, so this matches it.

No internet (0.1.162): a test that forgets to mock a request used to reach the real Gink server or the voice service
on GitHub's runners (open internet: slow wake-ups, real "sign in again" answers) but not on a machine behind a proxy
-- the same test passed in one place and failed in the other. Now every test sees the same thing: names don't
resolve and only this computer (127.0.0.1, ::1, local sockets) can be reached. A test that wants an address to
resolve replaces the lookup itself (web_reader._resolve, for example)."""
import ipaddress
import os
import socket

import dotenv
import dotenv.main

_no_dotenv = lambda *a, **k: False
dotenv.load_dotenv = _no_dotenv
dotenv.main.load_dotenv = _no_dotenv

for _name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(_name, None)          # straight to the (blocked) internet, never through a proxy on this computer

_LOCAL_NAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback", "testserver"}
_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _local(host) -> bool:
    """True for this computer: no name (binding), a loopback or "any" address, localhost."""
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    host = str(host).strip("[]").split("%")[0]
    if host == "" or host.lower() in _LOCAL_NAMES:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_unspecified


def _is_ip(host) -> bool:
    try:
        ipaddress.ip_address(str(host).strip("[]").split("%")[0])
        return True
    except ValueError:
        return False


def _getaddrinfo(host, *args, **kwargs):
    if _local(host) or _is_ip(host if not isinstance(host, bytes) else host.decode("ascii", "ignore")):
        return _real_getaddrinfo(host, *args, **kwargs)
    raise socket.gaierror(socket.EAI_NONAME, f"Name or service not known ({host}: tests have no internet)")


def _check(sock, address):
    if sock.family == getattr(socket, "AF_UNIX", object()):
        return
    host = address[0] if isinstance(address, tuple) else address
    if not _local(host):
        raise ConnectionRefusedError(111, f"Connection refused ({host}: tests have no internet)")


def _connect(self, address):
    _check(self, address)
    return _real_connect(self, address)


def _connect_ex(self, address):
    try:
        _check(self, address)
    except ConnectionRefusedError:
        return 111
    return _real_connect_ex(self, address)


socket.getaddrinfo = _getaddrinfo
socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex


import pytest  # noqa: E402  (after the guards above, on purpose)


@pytest.fixture
def genie_srv(tmp_path, monkeypatch):
    """Gink Genie's simulated server and AI (tests/test_genie.py), for the other Genie test files."""
    import test_genie
    yield from test_genie.genie_server(tmp_path, monkeypatch)
