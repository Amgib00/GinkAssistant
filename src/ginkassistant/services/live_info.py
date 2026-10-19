"""
Real-time information for Gink -- all from free services that need no API
key, so it works for everyone out of the box:

  time / date / days-until / time zones .... the device clock + zoneinfo
  places, time zones ........................ Open-Meteo geocoding
  weather, sunrise/sunset, UV, wind ......... Open-Meteo forecast
  air quality (dust, PM2.5) ................. Open-Meteo air quality
  prayer times .............................. Aladhan
  currency rates (incl. XOF / CFA) .......... open.er-api.com
  crypto prices ............................. CoinGecko
  maths ..................................... a safe local calculator
  "where am I" fallback ..................... ipwho.is (approximate, from your connection)

Where you are: the city in Settings -> Location (best), otherwise an
approximate location from your internet connection (and Gink says so).

Every method returns {"ok": bool, "message": "<ready-to-show answer>", ...data}
so the agent can show it directly or reason over the numbers.
"""

import ast
import asyncio
import math
import operator
import re
from datetime import date, datetime, timedelta
from typing import Callable, Optional

import httpx

try:
    from zoneinfo import ZoneInfo
except ImportError:                              # very old Pythons
    ZoneInfo = None

WEATHER_CODES = {
    0: ("clear sky", "\u2600\ufe0f"), 1: ("mostly clear", "\U0001F324"), 2: ("partly cloudy", "\u26c5"),
    3: ("overcast", "\u2601\ufe0f"), 45: ("fog", "\U0001F32B"), 48: ("freezing fog", "\U0001F32B"),
    51: ("light drizzle", "\U0001F326"), 53: ("drizzle", "\U0001F326"), 55: ("heavy drizzle", "\U0001F327"),
    56: ("freezing drizzle", "\U0001F327"), 57: ("freezing drizzle", "\U0001F327"),
    61: ("light rain", "\U0001F326"), 63: ("rain", "\U0001F327"), 65: ("heavy rain", "\U0001F327"),
    66: ("freezing rain", "\U0001F327"), 67: ("freezing rain", "\U0001F327"),
    71: ("light snow", "\U0001F328"), 73: ("snow", "\U0001F328"), 75: ("heavy snow", "\u2744\ufe0f"),
    77: ("snow grains", "\U0001F328"), 80: ("rain showers", "\U0001F326"), 81: ("heavy showers", "\U0001F327"),
    82: ("violent showers", "\u26c8"), 85: ("snow showers", "\U0001F328"), 86: ("heavy snow showers", "\u2744\ufe0f"),
    95: ("thunderstorms", "\u26c8"), 96: ("thunderstorms with hail", "\u26c8"), 99: ("severe thunderstorms", "\u26c8"),
}
AQI_LEVELS = [(50, "good"), (100, "moderate"), (150, "unhealthy for sensitive groups"),
              (200, "unhealthy"), (300, "very unhealthy"), (10_000, "hazardous")]
CRYPTO_IDS = {"btc": "bitcoin", "bitcoin": "bitcoin", "eth": "ethereum", "ethereum": "ethereum",
              "sol": "solana", "solana": "solana", "bnb": "binancecoin", "xrp": "ripple", "ripple": "ripple",
              "ada": "cardano", "cardano": "cardano", "doge": "dogecoin", "dogecoin": "dogecoin",
              "usdt": "tether", "tether": "tether", "usdc": "usd-coin", "ton": "the-open-network",
              "trx": "tron", "tron": "tron", "ltc": "litecoin", "litecoin": "litecoin"}
CURRENCY_ALIASES = {"cfa": "XOF", "fcfa": "XOF", "cfa franc": "XOF", "franc cfa": "XOF", "dollar": "USD",
                    "dollars": "USD", "$": "USD", "euro": "EUR", "euros": "EUR", "\u20ac": "EUR",
                    "pound": "GBP", "pounds": "GBP", "\u00a3": "GBP", "naira": "NGN", "cedi": "GHS",
                    "cedis": "GHS", "dirham": "MAD", "rand": "ZAR", "yen": "JPY", "yuan": "CNY",
                    "rupee": "INR", "rupees": "INR", "leone": "SLE", "leones": "SLE", "dalasi": "GMD"}


def _cur(code: str) -> str:
    c = (code or "").strip().lower()
    return CURRENCY_ALIASES.get(c, c.upper())


def _fmt_num(x: float) -> str:
    if abs(x) >= 100:
        return f"{x:,.0f}"
    if abs(x) >= 1:
        return f"{x:,.2f}"
    return f"{x:.4g}"


# ------------------------------------------------------------------ calculator
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
        ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log10,
          "ln": math.log, "abs": abs, "round": round, "pi": math.pi, "e": math.e}


def safe_eval(expr: str) -> float:
    expr = (expr or "").replace("\u00d7", "*").replace("\u00f7", "/").replace("^", "**").replace(",", "")
    expr = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*", r"(\1/100)*", expr, flags=re.I)

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Name) and node.id in _FUNCS and not callable(_FUNCS[node.id]):
            return _FUNCS[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ValueError("unsupported expression")
    return ev(ast.parse(expr.strip(), mode="eval"))


class LiveInfo:
    def __init__(self, city_fn: Callable[[], str] = lambda: "", http_client=None):
        self.city_fn = city_fn            # Settings -> Location
        self.allowed_fn = lambda: True    # Settings -> Location -> "Use location in answers"
        self._http = http_client
        self._ip_place = None              # cached for the session

    # -- helpers -----------------------------------------------------------
    def _client(self):
        return self._http or httpx.AsyncClient(timeout=10, follow_redirects=True,
                                               headers={"User-Agent": "Gink/1.0"})

    async def _get(self, url: str, params: Optional[dict] = None) -> dict:
        if self._http:
            r = await self._http.get(url, params=params)
        else:
            async with self._client() as c:
                r = await c.get(url, params=params)
        r.raise_for_status()
        return r.json()

    async def geocode(self, name: str) -> Optional[dict]:
        # The search matches place NAMES, so "Dakar, Senegal" is searched as
        # "Dakar" and the country picks the right match among several.
        parts = [x.strip() for x in (name or "").split(",") if x.strip()]
        if not parts:
            return None
        city, country = parts[0], (parts[-1].lower() if len(parts) > 1 else "")
        data = await self._get("https://geocoding-api.open-meteo.com/v1/search",
                               {"name": city, "count": 10, "language": "en"})
        results = data.get("results") or []
        if not results:
            return None
        res = results[0]
        if country:
            res = next((r for r in results if country in (r.get("country", "").lower(),
                                                          (r.get("country_code") or "").lower())), res)
        return {"name": res.get("name", name), "country": res.get("country", ""),
                "lat": res["latitude"], "lon": res["longitude"], "tz": res.get("timezone"), "source": "search"}

    async def where(self, place: Optional[str] = None) -> Optional[dict]:
        """The place asked about, else Settings -> Location, else approximate (from the connection)."""
        if place and place.strip() and place.strip().lower() not in ("here", "my location", "me"):
            return await self.geocode(place.strip())
        city = (self.city_fn() or "").strip()
        if city:
            p = await self.geocode(city)
            if p:
                p["source"] = "settings"
                return p
        if not self.allowed_fn():
            return None                   # location turned off: ask the user instead
        return await self.approximate_place()

    async def approximate_place(self, fresh: bool = False):
        """The device's general area, estimated from its internet (IP) address. Cached per session."""
        if self._ip_place is None or fresh:
            try:
                d = await self._get("https://ipwho.is/")
                if d.get("success", True) and d.get("latitude") is not None:
                    self._ip_place = {"name": d.get("city") or "your area", "country": d.get("country", ""),
                                      "region": d.get("region", ""), "lat": d["latitude"], "lon": d["longitude"],
                                      "tz": (d.get("timezone") or {}).get("id"), "source": "approximate"}
                else:
                    self._ip_place = False
            except Exception:
                self._ip_place = False
        return self._ip_place or None

    @staticmethod
    def _label(p: dict) -> str:
        return p["name"] + (f", {p['country']}" if p.get("country") and p["country"] != p["name"] else "")

    @staticmethod
    def _approx_note(p: dict) -> str:
        return ("\n\n_Location is approximate (from your connection) \u2014 set your city in "
                "Settings \u2192 Location for exact results._") if p.get("source") == "approximate" else ""

    # -- time & date -------------------------------------------------------
    async def get_time(self, place: Optional[str] = None) -> dict:
        if not place:
            now = datetime.now().astimezone()
            return {"ok": True, "time": now.strftime("%H:%M"), "tz": now.strftime("%Z"),
                    "message": f"It's **{now:%H:%M}** ({now:%I:%M %p}) on {now:%A, %d %B %Y}."}
        p = await self.where(place)
        if not p or not p.get("tz") or ZoneInfo is None:
            return {"ok": False, "message": f"I couldn't find the time zone for \u201c{place}\u201d."}
        there = datetime.now(ZoneInfo(p["tz"]))
        here = datetime.now().astimezone()
        diff_h = (there.utcoffset() - here.utcoffset()).total_seconds() / 3600
        rel = "the same time as you" if diff_h == 0 else \
            f"{abs(diff_h):g} hour{'s' if abs(diff_h) != 1 else ''} {'ahead of' if diff_h > 0 else 'behind'} you"
        return {"ok": True, "time": there.strftime("%H:%M"), "tz": p["tz"],
                "message": f"In **{self._label(p)}** it's **{there:%H:%M}** ({there:%I:%M %p}), "
                           f"{there:%A %d %B} \u2014 {rel}."}

    def get_date(self, offset_days: int = 0) -> dict:
        d = date.today() + timedelta(days=int(offset_days or 0))
        which = {0: "Today", 1: "Tomorrow", -1: "Yesterday"}.get(int(offset_days or 0), d.strftime("%A"))
        iso = d.isocalendar()
        return {"ok": True, "date": d.isoformat(),
                "message": f"{which} is **{d:%A, %d %B %Y}** (week {iso[1]}, day {d.timetuple().tm_yday} "
                           f"of {366 if d.year % 4 == 0 and (d.year % 100 or d.year % 400 == 0) else 365})."}

    def days_until(self, target: str, label: str = "") -> dict:
        t = None
        for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d %Y", "%d/%m/%Y"):
            try:
                t = datetime.strptime(target.strip(), fmt).date()
                break
            except (ValueError, AttributeError):
                continue
        if not t:
            return {"ok": False, "message": f"I couldn't read the date \u201c{target}\u201d (try YYYY-MM-DD)."}
        n = (t - date.today()).days
        what = label or t.strftime("%A %d %B %Y")
        if n == 0:
            msg = f"{what} is **today**!"
        elif n > 0:
            weeks, days = divmod(n, 7)
            extra = f" ({weeks} week{'s' if weeks != 1 else ''}{f' and {days} day' + ('s' if days != 1 else '') if days else ''})" if n >= 14 else ""
            msg = f"**{n} day{'s' if n != 1 else ''}** until {what}{extra}."
        else:
            msg = f"{what} was **{-n} day{'s' if n != -1 else ''} ago**."
        return {"ok": True, "days": n, "message": msg}

    # -- weather -----------------------------------------------------------
    async def get_weather(self, place: Optional[str] = None, day: str = "now") -> dict:
        p = await self.where(place)
        if not p:
            return {"ok": False, "message": (f"I couldn't find \u201c{place}\u201d." if place else
                                             "Tell me a city, or set yours in Settings \u2192 Location.")}
        fc = await self._get("https://api.open-meteo.com/v1/forecast", {
            "latitude": p["lat"], "longitude": p["lon"], "timezone": "auto", "forecast_days": 7,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                     "precipitation_sum,wind_speed_10m_max,uv_index_max,sunrise,sunset"})
        daily, cur = fc["daily"], fc.get("current", {})
        where = self._label(p)
        day = (day or "now").strip().lower()

        def day_line(i, long=False):
            desc, icon = WEATHER_CODES.get(daily["weather_code"][i], ("mixed", "\U0001F321"))
            d = datetime.fromisoformat(daily["time"][i])
            name = "Today" if i == 0 else "Tomorrow" if i == 1 else d.strftime("%A")
            rain = daily["precipitation_probability_max"][i]
            line = (f"{icon} **{name}** ({d:%d %b}): {desc}, {round(daily['temperature_2m_min'][i])}\u2013"
                    f"{round(daily['temperature_2m_max'][i])}\u00b0C" + (f", {rain}% chance of rain" if rain is not None else ""))
            if long:
                sr, ss = daily["sunrise"][i][-5:], daily["sunset"][i][-5:]
                line += (f"\n- Wind up to {round(daily['wind_speed_10m_max'][i])} km/h \u00b7 UV {daily['uv_index_max'][i]:.0f}"
                         f" \u00b7 Sunrise {sr} \u00b7 Sunset {ss}")
            return line

        if day in ("week", "this week", "7 days", "forecast"):
            msg = f"**7-day forecast for {where}**\n\n" + "\n".join(f"- {day_line(i)}" for i in range(len(daily["time"])))
        elif day in ("today", "tomorrow") or re.match(r"\d{4}-\d{2}-\d{2}", day) or day in (
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
            idx = 0 if day == "today" else 1 if day == "tomorrow" else None
            if idx is None:
                for i, t in enumerate(daily["time"]):
                    dt = datetime.fromisoformat(t)
                    if t == day or dt.strftime("%A").lower() == day:
                        idx = i
                        break
            if idx is None:
                return {"ok": False, "message": "I only have the forecast for the next 7 days."}
            msg = f"**Weather in {where}**\n\n{day_line(idx, long=True)}"
        else:
            desc, icon = WEATHER_CODES.get(cur.get("weather_code"), ("mixed", "\U0001F321"))
            msg = (f"{icon} **{where}: {round(cur['temperature_2m'])}\u00b0C, {desc}** right now "
                   f"(feels like {round(cur['apparent_temperature'])}\u00b0C, humidity {cur['relative_humidity_2m']}%, "
                   f"wind {round(cur['wind_speed_10m'])} km/h).\n\n{day_line(0, long=True)}\n\n{day_line(1)}")
        return {"ok": True, "place": where, "message": msg + self._approx_note(p),
                "daily": {k: daily[k] for k in ("time", "temperature_2m_max", "temperature_2m_min",
                                                 "precipitation_probability_max", "weather_code")},
                "current": cur}

    async def get_air_quality(self, place: Optional[str] = None) -> dict:
        p = await self.where(place)
        if not p:
            return {"ok": False, "message": "Tell me a city, or set yours in Settings \u2192 Location."}
        d = await self._get("https://air-quality-api.open-meteo.com/v1/air-quality", {
            "latitude": p["lat"], "longitude": p["lon"], "timezone": "auto",
            "current": "us_aqi,pm2_5,pm10,dust"})
        c = d.get("current", {})
        aqi = c.get("us_aqi")
        if aqi is None:
            return {"ok": False, "message": f"No air-quality reading for {self._label(p)} right now."}
        level = next(name for limit, name in AQI_LEVELS if aqi <= limit)
        tip = ""
        if aqi > 100:
            tip = "\n\nConsider limiting long outdoor activity; a mask helps on dusty days."
        dust = f", dust {round(c['dust'])} \u00b5g/m\u00b3" if c.get("dust") is not None else ""
        return {"ok": True, "aqi": aqi,
                "message": f"\U0001F32C\ufe0f Air quality in **{self._label(p)}**: **{aqi} ({level})** \u2014 "
                           f"PM2.5 {c.get('pm2_5', 0):.0f}, PM10 {c.get('pm10', 0):.0f}{dust}.{tip}" + self._approx_note(p)}

    async def get_sun_times(self, place: Optional[str] = None, day: str = "today") -> dict:
        p = await self.where(place)
        if not p:
            return {"ok": False, "message": "Tell me a city, or set yours in Settings \u2192 Location."}
        fc = await self._get("https://api.open-meteo.com/v1/forecast", {
            "latitude": p["lat"], "longitude": p["lon"], "timezone": "auto", "forecast_days": 2,
            "daily": "sunrise,sunset,daylight_duration"})
        i = 1 if (day or "").lower() == "tomorrow" else 0
        d = fc["daily"]
        hours = d["daylight_duration"][i] / 3600
        return {"ok": True, "message": f"\U0001F305 In **{self._label(p)}** {'tomorrow' if i else 'today'}: sunrise "
                                       f"**{d['sunrise'][i][-5:]}**, sunset **{d['sunset'][i][-5:]}** "
                                       f"({int(hours)} h {round((hours % 1) * 60)} min of daylight)." + self._approx_note(p)}

    async def get_prayer_times(self, place: Optional[str] = None, day: str = "today") -> dict:
        p = await self.where(place)
        if not p:
            return {"ok": False, "message": "Tell me a city, or set yours in Settings \u2192 Location."}
        d = date.today() + timedelta(days=1 if (day or "").lower() == "tomorrow" else 0)
        data = await self._get(f"https://api.aladhan.com/v1/timings/{d:%d-%m-%Y}",
                               {"latitude": p["lat"], "longitude": p["lon"], "method": 3})
        t = data["data"]["timings"]
        hijri = data["data"]["date"]["hijri"]
        names = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
        now = datetime.now().strftime("%H:%M")
        nxt = next((n for n in names if n != "Sunrise" and t[n][:5] > now), None) if d == date.today() else None
        next_mark = "** \u2190 next"
        lines = "\n".join(f"- {'**' if n == nxt else ''}{n}: {t[n][:5]}{next_mark if n == nxt else ''}"
                          for n in names)
        return {"ok": True, "timings": {n: t[n][:5] for n in names},
                "message": f"\U0001F54C **Prayer times in {self._label(p)}** \u2014 {d:%A %d %B} "
                           f"({hijri['day']} {hijri['month']['en']} {hijri['year']} AH)\n\n{lines}\n\n"
                           f"_Muslim World League method; your local mosque may differ by a few minutes._"
                           + self._approx_note(p)}

    # -- money -------------------------------------------------------------
    async def convert_currency(self, amount: float, from_currency: str, to_currency: str) -> dict:
        src, dst = _cur(from_currency), _cur(to_currency)
        data = await self._get(f"https://open.er-api.com/v6/latest/{src}")
        if data.get("result") != "success":
            return {"ok": False, "message": f"I don't have rates for {src}."}
        rate = data["rates"].get(dst)
        if rate is None:
            return {"ok": False, "message": f"I don't have a rate from {src} to {dst}."}
        amount = float(amount or 1)
        updated = (data.get("time_last_update_utc") or "")[:16]
        return {"ok": True, "rate": rate, "result": amount * rate,
                "message": f"\U0001F4B1 **{_fmt_num(amount)} {src} = {_fmt_num(amount * rate)} {dst}** "
                           f"(1 {src} = {rate:.6g} {dst}; rates from {updated} UTC, banks and exchange shops add a margin)."}

    async def get_crypto_price(self, coin: str, currency: str = "usd") -> dict:
        cid = CRYPTO_IDS.get((coin or "").strip().lower(), (coin or "").strip().lower())
        cur = _cur(currency).lower()
        data = await self._get("https://api.coingecko.com/api/v3/simple/price",
                               {"ids": cid, "vs_currencies": cur, "include_24hr_change": "true"})
        if cid not in data or cur not in data[cid]:
            return {"ok": False, "message": f"I couldn't find a price for \u201c{coin}\u201d."}
        price = data[cid][cur]
        ch = data[cid].get(f"{cur}_24h_change")
        arrow = "\u25b2" if (ch or 0) >= 0 else "\u25bc"
        trend = f" ({arrow} {abs(ch):.1f}% in 24 h)" if ch is not None else ""
        return {"ok": True, "price": price,
                "message": f"\U0001FA99 **{cid.replace('-', ' ').title()}: {_fmt_num(price)} {cur.upper()}**{trend}."}

    # -- maths -------------------------------------------------------------
    def calculate(self, expression: str) -> dict:
        try:
            v = safe_eval(expression)
        except ZeroDivisionError:
            return {"ok": False, "message": "That divides by zero."}
        except Exception:
            return {"ok": False, "message": f"I couldn't calculate \u201c{expression}\u201d."}
        shown = f"{v:,.10g}" if isinstance(v, float) else f"{v:,}"
        return {"ok": True, "value": v, "message": f"\U0001F9EE {expression.strip()} = **{shown}**"}


def live_context(city: str = "") -> str:
    """One line for every AI system prompt, so plain chat knows 'now'."""
    now = datetime.now().astimezone()
    where = f" The user's location: {city}." if city else ""
    return (f"\n\nRight now it is {now:%A %d %B %Y, %H:%M} (UTC{now:%z}).{where} "
            f"Use this for anything about today, dates, ages or 'how long until'.")
