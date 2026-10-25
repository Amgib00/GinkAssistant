"""New abilities: money book, invoices, loans, bill splitting, units, passwords, random choices, QR codes."""
import os, string, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest
from ginkassistant.services import everyday as E
from ginkassistant.services.money import MoneyBook


def test_units():
    assert E.convert_units(100, "celsius", "°F")["result"] == 212
    assert E.convert_units(10, "km", "miles")["result"] == pytest.approx(6.2137, abs=1e-4)
    assert E.convert_units(50, "kg", "lbs")["result"] == pytest.approx(110.2311, abs=1e-4)
    assert E.convert_units(1, "hectare", "acres")["result"] == pytest.approx(2.4711, abs=1e-4)
    assert E.convert_units(0, "c", "k")["result"] == 273.15
    with pytest.raises(ValueError, match="Can't convert"):
        E.convert_units(5, "km", "kg")
    with pytest.raises(ValueError, match="don't know"):
        E.convert_units(5, "parsecs", "km")


def test_loan_split_password_random():
    r = E.loan(100000, 12, 12)
    assert r["monthly_payment"] == 8884.88 and r["total_interest"] == pytest.approx(6618.55, abs=0.05)
    assert E.loan(1200, 0, 12)["monthly_payment"] == 100
    with pytest.raises(ValueError):
        E.loan(-5, 10, 12)
    s = E.split_bill(100, 3)
    assert s["each"] == 33.34 and s["each"] * 3 >= 100                     # rounded up: the bill is covered
    assert E.split_bill(36000, 4, 10)["each"] == 9900
    pw = E.password(20)
    assert len(pw) == 20 and all(any(c in pool for c in pw) for pool in (string.ascii_lowercase, string.ascii_uppercase, string.digits))
    assert not any(c in "!@#$%^&*-_=+?" for c in E.password(12, symbols=False))
    assert set(E.random_choice("coin", count=20)) <= {"heads", "tails"}
    assert all(1 <= d <= 6 for d in E.random_choice("dice", count=20))
    assert E.random_choice("pick", options=["jollof", "thieb"])[0] in ("jollof", "thieb")
    with pytest.raises(ValueError):
        E.random_choice("pick", options=[])


def test_qr_codes_are_readable(tmp_path):
    path = E.qr_png(str(tmp_path), "https://gink-server.onrender.com/app", "Gink link")
    assert open(path, "rb").read(8) == b"\x89PNG\r\n\x1a\n"
    wifi = E.wifi_qr_text("Ibrahim's;Wi-Fi", "pa:ss")
    assert wifi == "WIFI:T:WPA;S:Ibrahim's\\;Wi-Fi;P:pa\\:ss;;"
    cv2 = pytest.importorskip("cv2")
    text, *_ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(path))
    assert text == "https://gink-server.onrender.com/app"                   # a real scanner reads it back


def test_money_book(tmp_path):
    book = MoneyBook(str(tmp_path / "money.db"))
    book.add("income", "45,000", "xof", "rice sales")
    book.add("expense", 12000, "XOF", "Transport")
    book.add("expense", 3000, "XOF", "transport")
    book.add("income", 500, "SLE", "")
    s = book.summary("month")
    xof = s["currencies"]["XOF"]
    assert xof["income"] == 45000 and xof["expense"] == 15000 and xof["balance"] == 30000
    assert xof["expense_by_category"] == {"transport": 15000} and s["currencies"]["SLE"]["income"] == 500   # never mixed
    with pytest.raises(ValueError):
        book.add("expense", -5, "XOF")
    with pytest.raises(ValueError):
        book.add("expense", "lots", "XOF")
    assert book.undo_last() and "SLE" not in book.summary("all")["currencies"]
    old = book.add("expense", 1000, "XOF", "rent", when="2020-01-15")
    assert book.summary("month")["currencies"]["XOF"]["expense"] == 15000      # not in this month
    assert book.summary("all")["currencies"]["XOF"]["expense"] == 16000


def test_abilities_through_the_agent(tmp_path):
    from ginkassistant.services.actions.tools import ToolRunner, TOOL_SPECS
    names = {t["function"]["name"] for t in TOOL_SPECS}
    assert {"record_money", "money_summary", "undo_last_money", "make_invoice", "loan_calculator", "split_bill",
            "convert_units", "generate_password", "random_choice", "make_qr_code"} <= names
    r = ToolRunner.__new__(ToolRunner)
    r.files_dir = None
    assert not r._t_record_money("income", 100, "XOF")["ok"]                   # no folder: says so
    r.files_dir = str(tmp_path / "files")
    assert "Income recorded: 45,000.00 XOF" in r._t_record_money("income", 45000, "XOF", "rice")["message"]
    r._t_record_money("expense", 5000, "XOF", "fuel")
    assert "balance 40,000.00" in r._t_money_summary("month")["message"]
    inv = r._t_make_invoice("Awa Diop", [{"description": "Dress", "quantity": 2, "unit_price": 15000},
                                         {"description": "Delivery", "quantity": 1, "unit_price": 2000}], "xof",
                            business_name="Ibrahim's Shop")
    assert inv["ok"] and inv["total"] == 32000 and os.path.getsize(inv["path"]) > 500 and inv["path"].endswith(".pdf")
    assert "gink://file/" in inv["message"]
    assert not r._t_make_invoice("X", [], "XOF")["ok"]
    qr = r._t_make_qr_code(wifi_name="Home", wifi_password="secret123")
    assert qr["ok"] and qr["path"].endswith(".png")
    assert r._t_convert_units(5, "km", "kg")["ok"] is False
    assert r._t_loan_calculator(100000, 12, 12)["monthly_payment"] == 8884.88
