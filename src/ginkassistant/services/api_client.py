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


class ApiClient:
    def __init__(self, base_url: str, timeout: float = None):
        self.base_url = base_url.rstrip("/")
        from .server_config import wait_for
        self.timeout = timeout or wait_for(base_url)   # online servers may need ~60 s to wake

    async def send_otp(self, email: str) -> None:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/send-otp", params={"email": email})
        if resp.status_code != 200:
            raise ApiError(self._detail(resp, "Failed to send the code. Check your connection."))

    async def verify_otp(self, email: str, otp: str) -> Session:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}{path}", json=payload)
        except httpx.HTTPError:
            raise ApiError("Can't reach the Gink server. Check your connection.")
        data = self._json(resp)
        if resp.status_code != 200:
            detail = data.get("detail", default_error)
            if isinstance(detail, list):          # FastAPI validation errors
                detail = default_error
            raise ApiError(detail)
        return data

    def _session(self, data: dict, email: str) -> Session:
        if "token" not in data:
            raise ApiError("The server didn't return a session.")
        return Session(token=data["token"], email=data.get("email", email), name=data.get("name", ""))

    async def login(self, email: str, password: str) -> Session:
        data = await self._post("/auth/login", {"email": email, "password": password}, "Couldn't log in.")
        return self._session(data, email)

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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
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
            async with httpx.AsyncClient(timeout=10) as client:
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

    async def _authed(self, method: str, path: str, token: str, **kw) -> dict:
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.request(method, f"{self.base_url}{path}",
                                            headers={"Authorization": f"Bearer {token}"}, **kw)
        except httpx.HTTPError:
            raise ApiError("Can't reach the Gink server. Check your connection.")
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
            async with httpx.AsyncClient(timeout=8) as client:
                r = await client.get(f"{self.base_url}/info")
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

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
            async with httpx.AsyncClient(timeout=200) as client:
                resp = await client.post(f"{self.base_url}/media/image", headers={"Authorization": f"Bearer {token}"},
                                         json={"prompt": prompt, "aspect_ratio": aspect_ratio, "style": style})
        except httpx.HTTPError:
            raise ApiError("Can't reach the Gink server. Check your connection.")
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
