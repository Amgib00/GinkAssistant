"""Live information tools against realistic copies of each free API's responses."""
import asyncio, os, sys
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import httpx

TODAY = date.today()
DAYS = [(TODAY + timedelta(days=i)).isoformat() for i in range(7)]


def handler(request: httpx.Request):
    url, q = str(request.url), dict(request.url.params)
    if "geocoding-api.open-meteo.com" in url:
        name = q["name"].lower()
        assert "," not in name, "searches must use the bare city name"
        if name == "nowhere":
            return httpx.Response(200, json={"generationtime_ms": 0.3})
        places = {"dakar": ("Dakar", "Senegal", 14.69, -17.44, "Africa/Dakar"),
                  "tokyo": ("Tokyo", "Japan", 35.69, 139.69, "Asia/Tokyo")}
        n, c, lat, lon, tz = places.get(name, ("Thi\u00e8s", "Senegal", 14.79, -16.93, "Africa/Dakar"))
        return httpx.Response(200, json={"results": [{"name": n, "country": c, "latitude": lat, "longitude": lon, "timezone": tz}]})
    if "air-quality-api" in url:
        return httpx.Response(200, json={"current": {"us_aqi": 132, "pm2_5": 48.2, "pm10": 190.0, "dust": 310.0}})
    if "api.open-meteo.com/v1/forecast" in url:
        if "daylight_duration" in q.get("daily", ""):
            return httpx.Response(200, json={"daily": {"time": DAYS[:2], "sunrise": [f"{DAYS[0]}T07:21", f"{DAYS[1]}T07:21"],
                                                       "sunset": [f"{DAYS[0]}T19:05", f"{DAYS[1]}T19:04"],
                                                       "daylight_duration": [42240.0, 42180.0]}})
        return httpx.Response(200, json={
            "current": {"temperature_2m": 29.4, "apparent_temperature": 33.1, "relative_humidity_2m": 74,
                        "weather_code": 2, "wind_speed_10m": 14.2},
            "daily": {"time": DAYS, "weather_code": [2, 63, 3, 0, 0, 1, 95],
                      "temperature_2m_max": [31.2, 28.0, 30, 31, 32, 31, 29], "temperature_2m_min": [24.1, 23.5, 24, 24, 25, 24, 23],
                      "precipitation_probability_max": [10, 80, 20, 0, 0, 5, 60], "precipitation_sum": [0, 12, 0, 0, 0, 0, 8],
                      "wind_speed_10m_max": [22, 30, 18, 15, 16, 17, 35], "uv_index_max": [9.1, 6.0, 8, 9, 9, 9, 7],
                      "sunrise": [f"{d}T07:21" for d in DAYS], "sunset": [f"{d}T19:05" for d in DAYS]}})
    if "api.aladhan.com" in url:
        return httpx.Response(200, json={"code": 200, "data": {
            "timings": {"Fajr": "05:52", "Sunrise": "07:09", "Dhuhr": "13:11", "Asr": "16:28", "Maghrib": "19:08", "Isha": "20:21"},
            "date": {"hijri": {"day": "18", "month": {"en": "Rab\u012b\u02bf al-awwal"}, "year": "1448"}}}})
    if "open.er-api.com" in url:
        base = url.rsplit("/", 1)[1]
        rates = {"USD": {"XOF": 562.3, "EUR": 0.857, "USD": 1}, "XOF": {"USD": 0.001778, "XOF": 1},
                 "EUR": {"NGN": 1712.4, "XOF": 655.957}}
        if base not in rates:
            return httpx.Response(200, json={"result": "error"})
        return httpx.Response(200, json={"result": "success", "time_last_update_utc": "Sat, 10 Oct 2026 00:02:31 +0000",
                                         "rates": rates[base]})
    if "coingecko" in url:
        return httpx.Response(200, json={"bitcoin": {"usd": 118250.0, "usd_24h_change": -1.84}} if q["ids"] == "bitcoin" else {})
    if "ipwho.is" in url:
        return httpx.Response(200, json={"success": True, "city": "Pikine", "country": "Senegal", "latitude": 14.75,
                                         "longitude": -17.39, "timezone": {"id": "Africa/Dakar"}})
    return httpx.Response(404)


def live(city=""):
    from ginkassistant.services.live_info import LiveInfo
    return LiveInfo(city_fn=lambda: city, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def run(coro):
    return asyncio.run(coro)


def test_time_and_dates():
    li = live()
    assert "It's **" in run(li.get_time())["message"]
    tok = run(li.get_time("Tokyo"))
    assert tok["ok"] and "Tokyo, Japan" in tok["message"] and ("ahead" in tok["message"] or "same time" in tok["message"])
    assert run(li.get_time("nowhere"))["ok"] is False
    d = li.get_date(1)
    assert d["date"] == (TODAY + timedelta(days=1)).isoformat() and "Tomorrow" in d["message"]
    target = (TODAY + timedelta(days=33)).isoformat()
    u = li.days_until(target, "my exams")
    assert u["days"] == 33 and "33 days** until my exams (4 weeks and 5 days)" in u["message"]
    assert li.days_until("not a date")["ok"] is False


def test_weather_forms_and_location_fallbacks():
    li = live("Dakar, Senegal")
    now = run(li.get_weather())
    assert now["ok"] and "Dakar, Senegal: 29\u00b0C, partly cloudy" in now["message"] and "Sunrise 07:21" in now["message"]
    assert "approximate" not in now["message"]
    tmr = run(li.get_weather("Thies", "tomorrow"))
    assert "**Tomorrow**" in tmr["message"] and "80% chance of rain" in tmr["message"]
    week = run(li.get_weather(day="week"))
    assert week["message"].count("\n- ") == 7
    assert run(li.get_weather(day=(TODAY + timedelta(days=20)).isoformat()))["ok"] is False
    approx = run(live("").get_weather())                       # no city set -> from the connection
    assert "Pikine" in approx["message"] and "approximate" in approx["message"]


def test_air_sun_prayer():
    li = live("Dakar")
    air = run(li.get_air_quality())
    assert air["aqi"] == 132 and "unhealthy for sensitive groups" in air["message"] and "mask" in air["message"]
    sun = run(li.get_sun_times())
    assert "sunrise **07:21**, sunset **19:05** (11 h 44 min" in sun["message"]
    pr = run(li.get_prayer_times())
    assert pr["timings"]["Maghrib"] == "19:08" and "1448 AH" in pr["message"] and "Muslim World League" in pr["message"]


def test_money_and_maths():
    li = live()
    c = run(li.convert_currency(100, "dollars", "cfa"))
    assert c["ok"] and abs(c["result"] - 56230) < 0.01 and "100 USD = 56,230 XOF" in c["message"]
    assert "1,712" in run(li.convert_currency(1, "euro", "naira"))["message"]
    assert run(li.convert_currency(5, "zzz", "usd"))["ok"] is False
    b = run(li.get_crypto_price("btc"))
    assert "118,250 USD" in b["message"] and "\u25bc 1.8%" in b["message"]
    assert run(li.get_crypto_price("notacoin"))["ok"] is False
    assert li.calculate("15% of 80000")["value"] == 12000
    assert li.calculate("(1250*12)*0.18")["value"] == 2700
    assert li.calculate("2**99999")["ok"] is False and li.calculate("__import__('os')")["ok"] is False
    assert li.calculate("1/0")["ok"] is False


def test_agent_answers_live_questions_instantly(tmp_path):
    """Simple live questions skip the AI entirely (instant, works without a Groq key)."""
    from ginkassistant.services.actions import DeviceActions, TaskAgent, TaskStore, ToolRunner
    runner = ToolRunner(TaskStore(str(tmp_path / "t.db")), DeviceActions(str(tmp_path)))
    runner.live = live("Dakar")
    agent = TaskAgent(runner, api_key="")
    r = asyncio.run(agent.run("will it rain tomorrow?"))
    assert not r.used_ai and "80% chance of rain" in r.text
    assert "56,230 XOF" in asyncio.run(agent.run("100 dollars to cfa")).text
    assert "Tokyo" in asyncio.run(agent.run("what time is it in Tokyo")).text
    assert "12,000" in asyncio.run(agent.run("what's 15% of 80000")).text


def test_chat_brain_knows_now_and_city(tmp_path):
    from ginkassistant.services.groq_worker import GroqBrain
    brain = GroqBrain.__new__(GroqBrain)
    brain.memory_provider = None
    brain.city_fn = lambda: "Dakar, Senegal"
    prompt = brain._with_memory("You are Gink.")
    assert datetime.now().strftime("%A %d %B %Y") in prompt and "Dakar, Senegal" in prompt


def test_city_country_label_picks_the_right_country():
    from ginkassistant.services.live_info import LiveInfo
    def h(request):
        return httpx.Response(200, json={"results": [
            {"name": "Dakar", "country": "Somewhere Else", "latitude": 1, "longitude": 1, "timezone": "UTC"},
            {"name": "Dakar", "country": "Senegal", "country_code": "SN", "latitude": 14.69, "longitude": -17.44,
             "timezone": "Africa/Dakar"}]})
    li = LiveInfo(http_client=httpx.AsyncClient(transport=httpx.MockTransport(h)))
    p = asyncio.run(li.geocode("Dakar, Senegal"))
    assert p["country"] == "Senegal" and p["tz"] == "Africa/Dakar"
    assert asyncio.run(li.geocode("Dakar, SN"))["country"] == "Senegal"
