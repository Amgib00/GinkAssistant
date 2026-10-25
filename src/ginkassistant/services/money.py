"""A simple money book for people and small businesses: income and expenses, kept on this device
(SQLite next to Gink's other data). Amounts are stored per currency, never converted silently."""
import datetime as _dt
import sqlite3
import time

PERIODS = ("today", "week", "month", "year", "all")


class MoneyBook:
    def __init__(self, path: str):
        self.path = path
        with self._db() as con:
            con.execute("CREATE TABLE IF NOT EXISTS money (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, "
                        "kind TEXT NOT NULL, amount REAL NOT NULL, currency TEXT NOT NULL, category TEXT, note TEXT)")

    def _db(self):
        return sqlite3.connect(self.path)

    def add(self, kind: str, amount, currency: str, category: str = "", note: str = "", when: str = "") -> dict:
        kind = "income" if str(kind).lower() in ("income", "in", "sale", "sales", "earned") else "expense"
        try:
            amount = round(float(str(amount).replace(",", "").replace(" ", "")), 2)
        except ValueError:
            raise ValueError("The amount should be a number, like 45000.")
        if amount <= 0:
            raise ValueError("The amount should be more than zero.")
        currency = (currency or "").strip().upper()[:5] or "XOF"
        ts = time.time()
        if when:
            try:
                ts = _dt.datetime.strptime(when[:10], "%Y-%m-%d").timestamp() + 12 * 3600
            except ValueError:
                raise ValueError("Give the date as YYYY-MM-DD.")
        category = " ".join(str(category or "").split())[:40].lower() or ("sales" if kind == "income" else "other")
        with self._db() as con:
            rid = con.execute("INSERT INTO money (ts, kind, amount, currency, category, note) VALUES (?, ?, ?, ?, ?, ?)",
                              (ts, kind, amount, currency, category, str(note or "")[:200])).lastrowid
        return {"id": rid, "kind": kind, "amount": amount, "currency": currency, "category": category}

    def summary(self, period: str = "month", now: float = None) -> dict:
        period = period if period in PERIODS else "month"
        now_dt = _dt.datetime.fromtimestamp(now or time.time())
        start = {"today": now_dt.replace(hour=0, minute=0, second=0, microsecond=0),
                 "week": (now_dt - _dt.timedelta(days=now_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
                 "month": now_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
                 "year": now_dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
                 "all": _dt.datetime(1970, 1, 2)}[period].timestamp()
        with self._db() as con:
            rows = con.execute("SELECT kind, currency, category, SUM(amount), COUNT(*) FROM money WHERE ts >= ? "
                               "GROUP BY kind, currency, category ORDER BY SUM(amount) DESC", (start,)).fetchall()
        by_currency = {}
        for kind, cur, cat, total, n in rows:
            c = by_currency.setdefault(cur, {"income": 0.0, "expense": 0.0, "expense_by_category": {}, "income_by_category": {}})
            c[kind] += total
            c[f"{kind}_by_category"][cat] = round(total, 2)
        for c in by_currency.values():
            c["income"], c["expense"] = round(c["income"], 2), round(c["expense"], 2)
            c["balance"] = round(c["income"] - c["expense"], 2)
        return {"period": period, "currencies": by_currency, "entries": sum(r[4] for r in rows)}

    def undo_last(self) -> bool:
        with self._db() as con:
            row = con.execute("SELECT id FROM money ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                con.execute("DELETE FROM money WHERE id=?", row)
        return bool(row)
