"""
Which country is the user in, what does Gink Pro cost there, and how can
they pay? Runs on the SERVER (backend_server.py imports it).

Country, best signal first:
  1. the country the user picked on the Pro screen (saved on the account)
  2. a country header from a CDN in front of the server, if any
     (Cloudflare "CF-IPCountry")
  3. the device's time zone ("Africa/Dakar" -> SN), mapped with the
     standard tz database's zone.tab -- offline, free, no lookup service
  4. the device's region setting ("fr_SN" -> SN)
The user can always change it; payment providers do their own checks too.

Payment accounts only accept certain currencies (a CinetPay account opened
in Senegal charges in XOF only), so the server is told what YOUR accounts
accept via env vars (see deploy/README.md):
  CINETPAY_API_KEY, CINETPAY_SITE_ID, CINETPAY_CURRENCIES  (default "XOF")
  PAYSTACK_SECRET_KEY, PAYSTACK_CURRENCIES                 (e.g. "NGN,GHS,KES,ZAR,USD")
A user sees their country's own methods when one of your accounts takes
their currency; otherwise card payment in a currency you do accept,
labelled as such.

Prices are YOURS to set: GINK_PRICES='{"XOF": {"pro_1m": 3000, ...}, ...}'.
The defaults below are placeholders, not recommendations.
"""

import json
import os
from typing import Dict, List, Optional, Tuple

PLANS = [
    {"id": "pro_1m", "months": 1, "label": "1 month"},
    {"id": "pro_3m", "months": 3, "label": "3 months"},
    {"id": "pro_12m", "months": 12, "label": "12 months"},
]

DEFAULT_PRICES = {   # placeholders -- override with GINK_PRICES
    "XOF": {"pro_1m": 3000, "pro_3m": 8000, "pro_12m": 30000},
    "XAF": {"pro_1m": 3000, "pro_3m": 8000, "pro_12m": 30000},
    "GNF": {"pro_1m": 45000, "pro_3m": 120000, "pro_12m": 450000},
    "NGN": {"pro_1m": 4500, "pro_3m": 12000, "pro_12m": 45000},
    "GHS": {"pro_1m": 60, "pro_3m": 160, "pro_12m": 600},
    "KES": {"pro_1m": 650, "pro_3m": 1750, "pro_12m": 6500},
    "ZAR": {"pro_1m": 90, "pro_3m": 240, "pro_12m": 900},
    "USD": {"pro_1m": 5, "pro_3m": 13, "pro_12m": 50},
}
ZERO_DECIMAL = {"XOF", "XAF", "GNF", "CDF"}       # no cents

UEMOA = {"SN", "CI", "ML", "BF", "BJ", "TG", "NE", "GW"}
CEMAC = {"CM", "GA", "CG", "TD", "CF", "GQ"}
COUNTRY_CURRENCY = {**{c: "XOF" for c in UEMOA}, **{c: "XAF" for c in CEMAC},
                    "GN": "GNF", "NG": "NGN", "GH": "GHS", "KE": "KES", "ZA": "ZAR", "US": "USD"}

# Local ways to pay, per country (what users recognise). The provider's own
# checkout shows the final list, which depends on your merchant contract.
LOCAL_METHODS = {
    "SN": [("wave", "Wave"), ("orange_money", "Orange Money"), ("free_money", "Free Money")],
    "CI": [("orange_money", "Orange Money"), ("mtn_momo", "MTN MoMo"), ("moov_money", "Moov Money"), ("wave", "Wave")],
    "ML": [("orange_money", "Orange Money"), ("moov_money", "Moov Money")],
    "BF": [("orange_money", "Orange Money"), ("moov_money", "Moov Money")],
    "BJ": [("mtn_momo", "MTN MoMo"), ("moov_money", "Moov Money")],
    "TG": [("tmoney", "T-Money"), ("flooz", "Flooz")],
    "NE": [("airtel_money", "Airtel Money"), ("moov_money", "Moov Money")],
    "CM": [("mtn_momo", "MTN MoMo"), ("orange_money", "Orange Money")],
    "GN": [("orange_money", "Orange Money"), ("mtn_momo", "MTN MoMo")],
    "GH": [("mtn_momo", "MTN MoMo"), ("telecel_cash", "Telecel Cash"), ("at_money", "AT Money")],
    "KE": [("mpesa", "M-Pesa")],
    "NG": [("bank_transfer", "Bank transfer"), ("ussd", "USSD")],
}

# Which provider serves which currencies at all (your account narrows it further).
PROVIDER_CURRENCIES = {
    "cinetpay": {"XOF", "XAF", "GNF", "CDF", "USD"},
    "paystack": {"NGN", "GHS", "KES", "ZAR", "USD", "XOF"},
}


# ---------------------------------------------------------------- tz data
def _tz_table(name: str) -> List[str]:
    try:
        import importlib.resources as r
        return r.files("tzdata").joinpath("zoneinfo", name).read_text(encoding="utf-8").splitlines()
    except Exception:
        try:
            with open(f"/usr/share/zoneinfo/{name}", encoding="utf-8") as f:
                return f.read().splitlines()
        except Exception:
            return []


_ZONES: Optional[Dict[str, str]] = None
_NAMES: Optional[Dict[str, str]] = None


def zone_to_country(tz: str) -> Optional[str]:
    global _ZONES
    if _ZONES is None:
        _ZONES = {}
        for line in _tz_table("zone.tab"):
            if line and not line.startswith("#"):
                parts = line.split("\t")
                if len(parts) >= 3:
                    _ZONES[parts[2]] = parts[0]
    return _ZONES.get((tz or "").strip())


def country_name(code: str) -> str:
    global _NAMES
    if _NAMES is None:
        _NAMES = {}
        for line in _tz_table("iso3166.tab"):
            if line and not line.startswith("#") and "\t" in line:
                c, n = line.split("\t", 1)
                _NAMES[c] = n.replace("\u2019", "'")
    return _NAMES.get((code or "").upper(), (code or "").upper())


def flag(code: str) -> str:
    code = (code or "").upper()
    if len(code) != 2 or not code.isalpha():
        return "\U0001F310"
    return "".join(chr(0x1F1E6 + ord(c) - 65) for c in code)


def all_countries() -> List[Tuple[str, str]]:
    country_name("SN")
    return sorted(_NAMES.items(), key=lambda kv: kv[1]) if _NAMES else []


def detect_country(chosen: str = "", cdn_header: str = "", tz: str = "", locale: str = "") -> Tuple[str, str]:
    """(ISO code or "", source) -- source is chosen | network | timezone | locale | unknown."""
    if chosen and len(chosen) == 2:
        return chosen.upper(), "chosen"
    if cdn_header and len(cdn_header) == 2 and cdn_header.upper() not in ("XX", "T1"):
        return cdn_header.upper(), "network"
    c = zone_to_country(tz)
    if c:
        return c, "timezone"
    loc = (locale or "").replace("-", "_")
    if "_" in loc:
        region = loc.split("_")[1][:2].upper()
        if len(region) == 2 and region.isalpha():
            return region, "locale"
    return "", "unknown"


# ---------------------------------------------------------------- config
def prices() -> Dict[str, Dict[str, int]]:
    raw = os.environ.get("GINK_PRICES", "").strip()
    if raw:
        try:
            custom = json.loads(raw)
            return {k.upper(): v for k, v in custom.items()}
        except ValueError:
            pass
    return DEFAULT_PRICES


def enabled_providers() -> Dict[str, set]:
    """provider -> currencies YOUR account accepts (only providers with keys set)."""
    out = {}
    if os.environ.get("CINETPAY_API_KEY") and os.environ.get("CINETPAY_SITE_ID"):
        cur = {c.strip().upper() for c in os.environ.get("CINETPAY_CURRENCIES", "XOF").split(",") if c.strip()}
        out["cinetpay"] = cur & PROVIDER_CURRENCIES["cinetpay"]
    if os.environ.get("PAYSTACK_SECRET_KEY"):
        cur = {c.strip().upper() for c in os.environ.get("PAYSTACK_CURRENCIES", "").split(",") if c.strip()}
        out["paystack"] = cur & PROVIDER_CURRENCIES["paystack"]
    return {k: v for k, v in out.items() if v}


def format_price(amount, currency: str) -> str:
    if currency in ZERO_DECIMAL:
        return f"{int(amount):,} {'FCFA' if currency in ('XOF', 'XAF') else currency}".replace(",", "\u202f")
    return f"{currency} {amount:,.2f}".replace(".00", "")


def _plan_list(currency: str) -> List[dict]:
    table = prices().get(currency, {})
    out = []
    for p in PLANS:
        if p["id"] in table:
            amt = table[p["id"]]
            per_month = amt / p["months"]
            out.append({**p, "price": amt, "currency": currency, "display": format_price(amt, currency),
                        "per_month": format_price(round(per_month) if currency in ZERO_DECIMAL else round(per_month, 2),
                                                  currency)})
    return out


def options_for(country: str) -> dict:
    """Everything the Pro screen needs for this country."""
    country = (country or "").upper()
    local_cur = COUNTRY_CURRENCY.get(country, "USD")
    enabled = enabled_providers()
    methods, currency, note = [], None, ""

    # 1) a provider account that takes the local currency -> local methods + card
    for prov, curs in enabled.items():
        if local_cur in curs and local_cur in prices():
            currency = local_cur
            for mid, name in LOCAL_METHODS.get(country, []):
                methods.append({"id": mid, "name": name, "kind": "mobile_money", "provider": prov})
            methods.append({"id": "card", "name": "Debit / credit card", "kind": "card", "provider": prov})
            break
    # 2) otherwise card, charged in a currency one of your accounts accepts
    if currency is None:
        for prov, curs in enabled.items():
            for cur in ("USD", "XOF", "EUR", "NGN", "GHS", "KES", "ZAR", "XAF"):
                if cur in curs and cur in prices():
                    currency = cur
                    methods.append({"id": "card", "name": "Debit / credit card", "kind": "card", "provider": prov})
                    if cur != local_cur:
                        note = (f"Local payment methods for {country_name(country) or 'your country'} aren't "
                                f"available yet \u2014 pay by card, charged in {cur}.")
                    break
            if currency:
                break
    return {
        "country": country, "country_name": country_name(country) if country else "",
        "flag": flag(country), "currency": currency or local_cur,
        "plans": _plan_list(currency) if currency else [],
        "methods": methods, "note": note,
        "available": bool(methods),
    }
