"""
Async HTTP client for GinkAssistant's FastAPI backend -- rewritten to
match the routes actually defined in the real __main__.py, not the
earlier guesses:

    POST {base_url}/send-otp    ?email=...            -> {"status": "success"}
    POST {base_url}/verify-otp  ?email=...&otp=...     -> {"token": ..., "email": ...}

Two things this corrects from earlier versions:
  - No /login (email+password) route exists anywhere in the live app --
    dropped entirely, since __main__.py's GinkAppManager demonstrably
    launches the OTP screen.
  - No /me (session-validation) route exists either, so there's nothing
    to check a saved token against on relaunch. Auto-login here just
    trusts a locally saved session rather than round-tripping to a route
    that isn't there -- if the token has actually expired, the next
    place that would notice is whatever backend call fails, not this
    client.
  - typing_speed/device/behavioral_data params are gone too -- those
    belonged to auth_service.py's router, which is never mounted onto
    the real `app` and is dead code.

The chat itself doesn't go through this client at all -- GroqBrain
(services/groq_worker.py) talks to Groq directly, matching the real
LLMWorker. This client is purely for login.
"""

from dataclasses import dataclass

import httpx


class ApiError(Exception):
    """A clean, user-facing API failure."""


@dataclass
class Session:
    token: str
    email: str
    name: str = ""


class TwoFactorRequired(Exception):
    """The password (or code, or Google...) was right; now the authenticator code is needed."""
    def __init__(self, ticket: str, email: str = ""):
        super().__init__("Enter the code from your authenticator app.")
        self.ticket, self.email = ticket, email


def unreachable(exc: Exception) -> "ApiError":
    """Say WHY the server couldn't be reached, and what to do -- plus a short technical
    detail, so one screenshot is enough to fix a problem on someone's phone."""
    detail = f"{type(exc).__name__}: {exc}".strip().rstrip(":")[:160]
    low = detail.lower()
    if isinstance(exc, httpx.TimeoutException):
        msg = ("The Gink server didn't answer in time. If it was asleep it can take up to a minute "
               "to wake up, so please try again.")
    elif "certificate" in low or "ssl" in low:
        msg = ("Gink couldn't make a secure connection to the server. Check that your phone's date and "
               "time are set automatically (Settings > Date & time), then try again.")
    elif any(k in low for k in ("name or service not known", "nodename nor servname", "getaddrinfo",
                                "no address associated", "name resolution", "errno -2", "errno 7")):
        msg = "Gink couldn't find its server on the internet. Check that Wi-Fi or mobile data is on."
    elif "network is unreachable" in low or "no route to host" in low:
        msg = "There's no internet connection. Check your Wi-Fi or mobile data."
    elif "connection refused" in low:
        msg = "The Gink server refused the connection. It may be restarting, so try again in a minute."
    else:
        msg = "Can't reach the Gink server. Check your connection."
    return ApiError(f"{msg} (Details: {detail})")


def device_headers() -> dict:
    """Tell the server which app this is, so Settings > Account can list "Gink for Mac" etc."""
    from .platform_utils import is_android, is_ios
    import sys
    if is_android():
        name = "Gink on Android"
    elif is_ios():
        name = "Gink on iPhone or iPad"
    else:
        name = {"darwin": "Gink for Mac", "win32": "Gink for Windows"}.get(sys.platform, "Gink for Linux")
    return {"X-Gink-Device": name}


class ApiClient:
    def __init__(self, base_url: str, timeout: float = None):
        self.base_url = base_url.rstrip("/")
        from .server_config import wait_for
        self.timeout = timeout or wait_for(base_url)   # online servers may need ~60 s to wake

    async def send_otp(self, email: str) -> None:
        async with httpx.AsyncClient(headers=device_headers(), timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/send-otp", params={"email": email})
        if resp.status_code != 200:
            raise ApiError(self._detail(resp, "Failed to send the code. Check your connection."))

    async def verify_otp(self, email: str, otp: str) -> Session:
        async with httpx.AsyncClient(headers=device_headers(), timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/verify-otp", params={"email": email, "otp": otp}
            )
        data = self._json(resp)
        if resp.status_code != 200 or "token" not in data:
            raise ApiError(data.get("detail", "Invalid or expired code."))
        return Session(token=data["token"], email=data.get("email", email))

    # -- accounts (password, verification, reset) -------------------------

    async def _post(self, path: str, payload: dict, default_error: str) -> dict:
        try:
            async with httpx.AsyncClient(headers=device_headers(), timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}{path}", json=payload)
        except httpx.HTTPError as e:
            raise unreachable(e)
        data = self._json(resp)
        if resp.status_code != 200:
            detail = data.get("detail", default_error)
            if isinstance(detail, list):          # FastAPI validation errors
                detail = default_error
            raise ApiError(detail)
        return data

    def _session(self, data: dict, email: str) -> Session:
        if data.get("twofa_required"):                  # two-step sign-in: the code comes next
            raise TwoFactorRequired(data.get("ticket", ""), data.get("email", email))
        if "token" not in data:
            raise ApiError("The server didn't return a session.")
        return Session(token=data["token"], email=data.get("email", email), name=data.get("name", ""))

    async def login(self, email: str, password: str) -> Session:
        data = await self._post("/auth/login", {"email": email, "password": password}, "Couldn't log in.")
        return self._session(data, email)

    async def verify_2fa(self, ticket: str, code: str) -> Session:
        data = await self._post("/auth/2fa", {"ticket": ticket, "code": code}, "That code didn't work.")
        return self._session(data, data.get("email", ""))

    # -- two-step sign-in settings (Settings > Account) ------------------------
    async def twofa_status(self, token: str) -> dict:
        return await self._authed("GET", "/account/2fa", token)

    async def twofa_setup(self, token: str) -> dict:
        return await self._authed("POST", "/account/2fa/setup", token)

    async def twofa_enable(self, token: str, code: str) -> dict:
        return await self._authed("POST", "/account/2fa/enable", token, json={"code": code})

    async def twofa_disable(self, token: str, code: str) -> dict:
        return await self._authed("POST", "/account/2fa/disable", token, json={"code": code})

    async def register(self, name: str, email: str, password: str) -> None:
        await self._post("/auth/register", {"name": name, "email": email, "password": password},
                         "Couldn't create the account.")

    async def verify_register(self, email: str, code: str) -> Session:
        data = await self._post("/auth/register/verify", {"email": email, "code": code}, "Invalid code.")
        return self._session(data, email)

    async def forgot_password(self, email: str) -> None:
        await self._post("/auth/forgot", {"email": email}, "Couldn't send the reset code.")

    async def reset_password(self, email: str, code: str, password: str) -> Session:
        data = await self._post("/auth/reset", {"email": email, "code": code, "password": password},
                                "Couldn't reset the password.")
        return self._session(data, email)

    # -- social / SSO sign-in ------------------------------------------------

    async def providers(self) -> dict:
        """{"google": {"enabled": bool, "label": "Google"}, ...}; {} if offline."""
        try:
            async with httpx.AsyncClient(headers=device_headers(), timeout=self.timeout) as client:
                resp = await client.get(f"{self.base_url}/auth/providers")
            return resp.json() if resp.status_code == 200 else {}
        except Exception:
            return {}

    async def oauth_begin(self, provider: str, state: str) -> None:
        await self._post(f"/auth/{provider}/begin", {"state": state}, "Couldn't start sign-in.")

    def oauth_start_url(self, provider: str, state: str) -> str:
        return f"{self.base_url}/auth/{provider}/start?state={state}"

    async def oauth_poll(self, state: str):
        """None while the user is still signing in, a Session when done."""
        try:
            async with httpx.AsyncClient(headers=device_headers(), timeout=10) as client:
                resp = await client.get(f"{self.base_url}/auth/poll", params={"state": state})
        except httpx.HTTPError:
            return None
        data = self._json(resp)
        if resp.status_code != 200:
            raise ApiError(data.get("detail", "Sign-in failed."))
        if data.get("status") == "pending":
            return None
        return self._session(data, data.get("email", ""))

    # -- billing (Gink Pro) ----------------------------------------------------

    async def _authed(self, method: str, path: str, token: str, timeout: float = 25, **kw) -> dict:
        try:
            async with httpx.AsyncClient(headers=device_headers(), timeout=timeout) as client:
                resp = await client.request(method, f"{self.base_url}{path}",
                                            headers={"Authorization": f"Bearer {token}"}, **kw)
        except httpx.HTTPError as e:
            raise unreachable(e)
        data = self._json(resp)
        if resp.status_code == 401:
            raise ApiError("Please sign out and sign in again.")
        if resp.status_code != 200:
            detail = data.get("detail", "Something went wrong.")
            raise ApiError(detail if isinstance(detail, str) else "Something went wrong.")
        return data

    async def billing_options(self, token: str, tz: str = "", locale: str = "", country: str = "") -> dict:
        return await self._authed("GET", "/billing/options", token,
                                  params={"tz": tz, "locale": locale, "country": country})

    async def set_country(self, token: str, country: str) -> dict:
        return await self._authed("POST", "/billing/country", token, json={"country": country})

    async def checkout(self, token: str, plan: str, method: str, country: str) -> dict:
        return await self._authed("POST", "/billing/checkout", token,
                                  json={"plan": plan, "method": method, "country": country})

    async def app_info(self) -> dict:
        try:
            async with httpx.AsyncClient(headers=device_headers(), timeout=8) as client:
                r = await client.get(f"{self.base_url}/info")
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    # -- websites ("make me a website for...") -----------------------------------
    async def create_site(self, token: str, prompt: str) -> dict:
        return await self._authed("POST", "/sites", token, json={"prompt": prompt}, timeout=200)

    async def edit_site(self, token: str, site_id: str, instruction: str) -> dict:
        return await self._authed("POST", f"/sites/{site_id}/edit", token, json={"instruction": instruction}, timeout=200)

    async def sites(self, token: str) -> list:
        return (await self._authed("GET", "/sites", token)).get("sites", [])

    async def delete_site(self, token: str, site_id: str) -> None:
        await self._authed("DELETE", f"/sites/{site_id}", token)

    # -- signed-in devices (Settings > Account) ---------------------------------
    async def sessions(self, token: str) -> list:
        return (await self._authed("GET", "/account/sessions", token)).get("sessions", [])

    async def revoke_session(self, token: str, sid: str) -> None:
        await self._authed("DELETE", f"/account/sessions/{sid}", token)

    async def sign_out_others(self, token: str) -> None:
        await self._authed("POST", "/account/sessions/sign-out-others", token)

    async def logout(self, token: str) -> None:
        """End this device's session on the server (best effort: logging out works offline too)."""
        try:
            await self._authed("POST", "/auth/logout", token)
        except Exception:
            pass

    async def billing_history(self, token: str) -> list:
        return (await self._authed("GET", "/billing/history", token)).get("payments", [])

    async def delete_account(self, token: str) -> None:
        await self._authed("POST", "/account/delete", token, json={"confirm": "DELETE"})

    async def feedback(self, token: str, rating: str, reason: str = "", model: str = "", chars: int = 0) -> None:
        await self._authed("POST", "/feedback", token,
                           json={"rating": rating, "reason": reason, "model": model, "chars": chars})

    async def generate_image(self, token: str, prompt: str, aspect_ratio: str = "1:1", style: str = "") -> dict:
        """Gink Cloud image creation. Raises ApiError with a friendly message
        (daily limit, refused prompt, not set up...)."""
        try:
            async with httpx.AsyncClient(headers=device_headers(), timeout=200) as client:
                resp = await client.post(f"{self.base_url}/media/image", headers={"Authorization": f"Bearer {token}"},
                                         json={"prompt": prompt, "aspect_ratio": aspect_ratio, "style": style})
        except httpx.HTTPError as e:
            raise unreachable(e)
        data = self._json(resp)
        if resp.status_code != 200:
            err = data.get("error") if isinstance(data.get("error"), dict) else {}
            msg = err.get("message") or data.get("detail") or "The image couldn't be created."
            raise ApiError(msg if isinstance(msg, str) else "The image couldn't be created.")
        return data

    async def ai_usage(self, token: str) -> dict:
        return await self._authed("GET", "/ai/usage", token)

    async def billing_status(self, token: str, reference: str = "") -> dict:
        return await self._authed("GET", "/billing/status", token, params={"reference": reference})

    @staticmethod
    def _json(resp):
        try:
            return resp.json()
        except Exception:
            return {}

    @classmethod
    def _detail(cls, resp, default: str) -> str:
        return cls._json(resp).get("detail", default)
