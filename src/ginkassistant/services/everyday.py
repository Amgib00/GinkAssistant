"""Everyday tools for Gink's agent: units, loans, bill splitting, passwords, random choices, QR codes.
All offline and on the device."""
import math
import os
import random as _random
import secrets
import string

# ---- units: (dimension, factor to the base unit)
UNITS = {
    "mm": ("length", 0.001), "cm": ("length", 0.01), "m": ("length", 1.0), "km": ("length", 1000.0),
    "in": ("length", 0.0254), "ft": ("length", 0.3048), "yd": ("length", 0.9144), "mi": ("length", 1609.344),
    "g": ("mass", 0.001), "kg": ("mass", 1.0), "t": ("mass", 1000.0), "oz": ("mass", 0.028349523125), "lb": ("mass", 0.45359237),
    "ml": ("volume", 0.001), "l": ("volume", 1.0), "gal": ("volume", 3.785411784), "ukgal": ("volume", 4.54609),
    "cup": ("volume", 0.2365882365), "floz": ("volume", 0.0295735295625),
    "m2": ("area", 1.0), "km2": ("area", 1e6), "ha": ("area", 10000.0), "acre": ("area", 4046.8564224), "ft2": ("area", 0.09290304),
    "kmh": ("speed", 1 / 3.6), "ms": ("speed", 1.0), "mph": ("speed", 0.44704), "knot": ("speed", 0.514444),
    "c": ("temperature", None), "f": ("temperature", None), "k": ("temperature", None),
}
ALIASES = {"meter": "m", "meters": "m", "metre": "m", "metres": "m", "kilometer": "km", "kilometers": "km", "kilometre": "km",
           "kilometres": "km", "mile": "mi", "miles": "mi", "foot": "ft", "feet": "ft", "inch": "in", "inches": "in",
           "yard": "yd", "yards": "yd", "centimeter": "cm", "centimeters": "cm", "millimeter": "mm", "kilogram": "kg",
           "kilograms": "kg", "kilo": "kg", "kilos": "kg", "gram": "g", "grams": "g", "pound": "lb", "pounds": "lb",
           "lbs": "lb", "ounce": "oz", "ounces": "oz", "tonne": "t", "tonnes": "t", "ton": "t", "liter": "l", "liters": "l",
           "litre": "l", "litres": "l", "milliliter": "ml", "millilitre": "ml", "gallon": "gal", "gallons": "gal",
           "cups": "cup", "hectare": "ha", "hectares": "ha", "acres": "acre", "km/h": "kmh", "kph": "kmh", "m/s": "ms",
           "knots": "knot", "°c": "c", "celsius": "c", "°f": "f", "fahrenheit": "f", "kelvin": "k", "sq m": "m2",
           "square meters": "m2", "square feet": "ft2", "sq ft": "ft2", "fl oz": "floz"}


def _unit(u: str) -> str:
    u = str(u or "").strip().lower()
    u = ALIASES.get(u, u)
    if u not in UNITS:
        raise ValueError(f"I don't know the unit \u201c{u}\u201d.")
    return u


def convert_units(value, from_unit: str, to_unit: str) -> dict:
    v = float(value)
    a, b = _unit(from_unit), _unit(to_unit)
    da, db = UNITS[a][0], UNITS[b][0]
    if da != db:
        raise ValueError(f"Can't convert {da} ({a}) to {db} ({b}).")
    if da == "temperature":
        kelvin = {"c": v + 273.15, "f": (v - 32) * 5 / 9 + 273.15, "k": v}[a]
        out = {"c": kelvin - 273.15, "f": (kelvin - 273.15) * 9 / 5 + 32, "k": kelvin}[b]
    else:
        out = v * UNITS[a][1] / UNITS[b][1]
    return {"value": v, "from": a, "to": b, "result": round(out, 6 if abs(out) < 1 else 4)}


def loan(amount, annual_rate_percent, months) -> dict:
    """Equal monthly payments (amortised loan)."""
    p, n = float(amount), int(months)
    r = float(annual_rate_percent) / 100 / 12
    if p <= 0 or n <= 0 or n > 600 or r < 0:
        raise ValueError("Give a positive amount, a rate of 0 or more, and 1 to 600 months.")
    pay = p / n if r == 0 else p * r / (1 - (1 + r) ** -n)
    total = pay * n
    return {"monthly_payment": round(pay, 2), "total_paid": round(total, 2), "total_interest": round(total - p, 2),
            "months": n, "amount": p, "annual_rate_percent": float(annual_rate_percent)}


def split_bill(total, people, tip_percent=0) -> dict:
    t, n = float(total), int(people)
    if t < 0 or n < 1:
        raise ValueError("Give a total and at least one person.")
    with_tip = t * (1 + float(tip_percent or 0) / 100)
    each = math.ceil(with_tip / n * 100) / 100          # rounded up to the cent, so the bill is covered
    return {"total_with_tip": round(with_tip, 2), "people": n, "each": each, "tip": round(with_tip - t, 2)}


def password(length=16, symbols=True) -> str:
    n = max(8, min(int(length or 16), 128))
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits] + (["!@#$%^&*-_=+?"] if symbols else [])
    while True:                                          # cryptographic, with every kind of character
        pw = "".join(secrets.choice("".join(pools)) for _ in range(n))
        if all(any(ch in pool for ch in pw) for pool in pools):
            return pw


def random_choice(kind: str = "coin", options=None, sides=6, count=1) -> list:
    rng = _random.SystemRandom()
    count = max(1, min(int(count or 1), 20))
    if kind == "coin":
        return [rng.choice(["heads", "tails"]) for _ in range(count)]
    if kind == "dice":
        s = max(2, min(int(sides or 6), 1000))
        return [rng.randint(1, s) for _ in range(count)]
    opts = [str(o) for o in (options or []) if str(o).strip()]
    if not opts:
        raise ValueError("Give me the options to pick from.")
    return [rng.choice(opts) for _ in range(count)]


def qr_png(folder: str, text: str, name: str = "QR code") -> str:
    """A QR code image (PNG) in `folder`; returns its path."""
    import segno
    text = str(text or "").strip()
    if not text or len(text) > 2000:
        raise ValueError("Give me the text or link for the QR code (up to 2000 characters).")
    os.makedirs(folder, exist_ok=True)
    from .file_maker import safe_name, unique_path
    path = unique_path(folder, safe_name(name or "QR code", "png"))
    segno.make(text, error="m").save(path, scale=10, border=4)
    return path


def wifi_qr_text(ssid: str, password_: str = "", security: str = "WPA") -> str:
    esc = lambda s: "".join("\\" + c if c in '\\;,:"' else c for c in str(s))
    sec = "nopass" if not password_ else (security or "WPA").upper()
    return f"WIFI:T:{sec};S:{esc(ssid)};" + (f"P:{esc(password_)};" if password_ else "") + ";"
