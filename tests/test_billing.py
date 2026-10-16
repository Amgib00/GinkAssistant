"""Billing: country detection, local methods, and money-safety rules."""
import asyncio, hashlib, hmac, json, os, sys, time
os.environ["TOGA_BACKEND"] = "toga_dummy"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import pytest


def test_country_detection():
    from ginkassistant.services import billing_catalog as c
    assert c.detect_country(tz="Africa/Dakar") == ("SN", "timezone")
    assert c.detect_country(tz="Africa/Freetown") == ("SL", "timezone")
    assert c.detect_country(tz="Etc/UTC", locale="fr_SN") == ("SN", "locale")
    assert c.detect_country(chosen="ci", tz="Africa/Dakar") == ("CI", "chosen")         # user's choice wins
    assert c.detect_country(cdn_header="NG", tz="Africa/Dakar") == ("NG", "network")
    assert c.detect_country() == ("", "unknown")
    assert c.country_name("SN") == "Senegal" and c.flag("SN") == "\U0001F1F8\U0001F1F3"


def test_methods_follow_country_and_your_accounts(monkeypatch):
    from ginkassistant.services import billing_catalog as c
    for k in ("CINETPAY_API_KEY", "CINETPAY_SITE_ID", "PAYSTACK_SECRET_KEY", "GINK_PRICES"):
        monkeypatch.delenv(k, raising=False)
    assert c.options_for("SN")["available"] is False                                   # no accounts yet
    monkeypatch.setenv("CINETPAY_API_KEY", "k"); monkeypatch.setenv("CINETPAY_SITE_ID", "1")
    sn = c.options_for("SN")
    assert [m["name"] for m in sn["methods"]] == ["Wave", "Orange Money", "Free Money", "Debit / credit card"]
    assert sn["currency"] == "XOF" and sn["plans"][0]["display"] == "3\u202f000 FCFA"
    ci = c.options_for("CI")
    assert "MTN MoMo" in [m["name"] for m in ci["methods"]]
    ng = c.options_for("NG")                       # no Naira account -> card charged in XOF, clearly said
    assert [m["id"] for m in ng["methods"]] == ["card"] and ng["currency"] == "XOF" and "charged in XOF" in ng["note"]
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk"); monkeypatch.setenv("PAYSTACK_CURRENCIES", "NGN,GHS,KES")
    ng = c.options_for("NG")
    assert ng["currency"] == "NGN" and ng["methods"][0]["provider"] == "paystack" and ng["note"] == ""
    assert c.options_for("KE")["methods"][0]["name"] == "M-Pesa"
    monkeypatch.setenv("GINK_PRICES", json.dumps({"XOF": {"pro_1m": 2500}}))
    assert [p["id"] for p in c.options_for("SN")["plans"]] == ["pro_1m"]


@pytest.fixture
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("GINK_DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("CINETPAY_API_KEY", "apikey"); monkeypatch.setenv("CINETPAY_SITE_ID", "445566")
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_x"); monkeypatch.setenv("PAYSTACK_CURRENCIES", "NGN")
    monkeypatch.delenv("GINK_PRICES", raising=False)
    from fastapi.testclient import TestClient
    from ginkassistant.services import backend_server as b
    calls, provider_state = [], {}

    def fake_post(url, payload, headers=None):
        calls.append((url, payload))
        if url.endswith("/v2/payment"):                          # CinetPay init (docs' example response)
            return 200, {"code": "201", "message": "CREATED", "data": {
                "payment_token": "tok", "payment_url": "https://checkout.cinetpay.com/payment/tok"}}
        if url.endswith("/v2/payment/check"):
            st = provider_state.get(payload["transaction_id"], ("WAITING_FOR_CUSTOMER", "3000", "XOF"))
            code = "00" if st[0] == "ACCEPTED" else "662"
            return 200, {"code": code, "message": "x", "data": {"amount": st[1], "currency": st[2], "status": st[0]}}
        if "paystack.co/transaction/initialize" in url:
            return 200, {"status": True, "data": {"authorization_url": "https://checkout.paystack.com/abc",
                                                  "reference": payload["reference"]}}
        return 404, {}

    def fake_get(url, headers=None):
        ref = url.rsplit("/", 1)[1]
        st = provider_state.get(ref, ("ongoing", 0, "NGN"))
        return 200, {"status": True, "data": {"status": st[0], "amount": st[1], "currency": st[2]}}
    monkeypatch.setattr(b, "_http_post_json", fake_post)
    monkeypatch.setattr(b, "_http_get_json", fake_get)
    client = TestClient(b.app)
    auth = lambda email: {"Authorization": "Bearer " + b._token_response(email, "Ibrahim Kargbo")["token"]}
    return b, client, auth, calls, provider_state


def test_cinetpay_payment_flow_is_money_safe(server):
    b, c, auth, calls, state = server
    me = auth("ib@x.co")
    opts = c.get("/billing/options", params={"tz": "Africa/Dakar"}, headers=me).json()
    assert opts["country"] == "SN" and opts["source"] == "timezone" and opts["status"]["plan"] == "free"
    assert c.get("/billing/options").status_code == 401                       # must be signed in
    r = c.post("/billing/checkout", json={"plan": "pro_1m", "method": "wave", "country": "SN"}, headers=me).json()
    ref = r["reference"]
    assert r["payment_url"].startswith("https://checkout.cinetpay.com/") and ref.isalnum()
    init = calls[-1][1]
    assert init["amount"] == 3000 and init["amount"] % 5 == 0 and init["currency"] == "XOF"
    assert init["channels"] == "MOBILE_MONEY" and init["lang"] == "fr"
    assert init["notify_url"].endswith("/billing/notify/cinetpay")
    # user still approving on their phone -> pending, NOT failed
    assert c.get("/billing/status", params={"reference": ref}, headers=me).json()["payment"] == "pending"
    # someone else can't look at (or trigger) my payment
    assert c.get("/billing/status", params={"reference": ref}, headers=auth("eve@x.co")).status_code == 404
    # CinetPay pings with GET, then notifies (possibly several times)
    assert c.get("/billing/notify/cinetpay").status_code == 200
    state[ref] = ("ACCEPTED", "3000", "XOF")
    for _ in range(3):
        assert c.post("/billing/notify/cinetpay", data={"cpm_trans_id": ref, "cpm_site_id": "445566"}).status_code == 200
    st = c.get("/billing/status", params={"reference": ref}, headers=me).json()
    assert st["plan"] == "pro" and st["payment"] == "success"
    assert 29.9 * 86400 < st["pro_until"] - time.time() < 30.1 * 86400      # credited exactly once
    # buying again adds to the end date
    ref2 = c.post("/billing/checkout", json={"plan": "pro_3m", "method": "orange_money", "country": "SN"}, headers=me).json()["reference"]
    state[ref2] = ("ACCEPTED", "8000", "XOF")
    st2 = c.get("/billing/status", params={"reference": ref2}, headers=me).json()
    assert round((st2["pro_until"] - st["pro_until"]) / 86400) == 91
    # a forged notification with the wrong site id does nothing
    ref3 = c.post("/billing/checkout", json={"plan": "pro_12m", "method": "card", "country": "SN"}, headers=me).json()["reference"]
    assert calls[-1][1]["channels"] == "CREDIT_CARD"
    state[ref3] = ("ACCEPTED", "30000", "XOF")
    c.post("/billing/notify/cinetpay", data={"cpm_trans_id": ref3, "cpm_site_id": "999"})
    with b._db_lock:
        con = b._billing_db(); row = con.execute("SELECT status FROM payments WHERE reference=?", (ref3,)).fetchone(); con.close()
    assert row[0] == "pending"


def test_wrong_amount_or_refusal_never_credits(server):
    b, c, auth, calls, state = server
    me = auth("ib@x.co")
    ref = c.post("/billing/checkout", json={"plan": "pro_12m", "method": "wave", "country": "SN"}, headers=me).json()["reference"]
    state[ref] = ("ACCEPTED", "100", "XOF")                                   # paid 100 instead of 30 000
    st = c.get("/billing/status", params={"reference": ref}, headers=me).json()
    assert st["payment"] == "failed" and st["plan"] == "free"
    ref2 = c.post("/billing/checkout", json={"plan": "pro_1m", "method": "wave", "country": "SN"}, headers=me).json()["reference"]
    state[ref2] = ("REFUSED", "3000", "XOF")
    assert c.get("/billing/status", params={"reference": ref2}, headers=me).json()["payment"] == "failed"
    assert c.post("/billing/checkout", json={"plan": "pro_1m", "method": "mpesa", "country": "SN"},
                  headers=me).status_code == 422                               # not a Senegal method
    assert "didn't go through" in c.get("/billing/return", params={"ref": ref2}).text


def test_paystack_webhook_signature(server):
    b, c, auth, calls, state = server
    me = auth("ada@x.ng")
    r = c.post("/billing/checkout", json={"plan": "pro_1m", "method": "card", "country": "NG"}, headers=me).json()
    ref = r["reference"]
    assert calls[-1][1]["amount"] == 450000 and calls[-1][1]["currency"] == "NGN"   # kobo
    body = json.dumps({"event": "charge.success", "data": {"reference": ref}}).encode()
    assert c.post("/billing/webhook/paystack", content=body, headers={"x-paystack-signature": "forged"}).status_code == 401
    state[ref] = ("success", 450000, "NGN")
    sig = hmac.new(b"sk_test_x", body, hashlib.sha512).hexdigest()
    assert c.post("/billing/webhook/paystack", content=body, headers={"x-paystack-signature": sig}).status_code == 200
    assert c.get("/billing/status", headers=me).json()["plan"] == "pro"


def test_pro_screen_shows_local_options(tmp_path, monkeypatch):
    import toga
    from ginkassistant.ui import pro_screen as ps
    opts = {"country": "SN", "country_name": "Senegal", "flag": "\U0001F1F8\U0001F1F3", "currency": "XOF",
            "source": "timezone", "available": True, "note": "", "status": {"plan": "free", "pro_until": 0},
            "countries": [{"code": "SN", "name": "Senegal"}, {"code": "CI", "name": "C\u00f4te d'Ivoire"}],
            "plans": [{"id": "pro_1m", "months": 1, "label": "1 month", "display": "3\u202f000 FCFA", "per_month": "x"}],
            "methods": [{"id": "wave", "name": "Wave"}, {"id": "card", "name": "Debit / credit card"}]}
    async def fake_opts(self, token, tz="", locale="", country=""): return opts
    monkeypatch.setattr(ps.ApiClient, "billing_options", fake_opts)
    app = toga.App("t", "org.t")
    app.session_token = "tok"
    class S: base_url = "http://t"
    app.state = S()

    async def go():
        scr = ps.ProScreen(app, on_back=lambda: None)
        await asyncio.sleep(0.05)
        return scr
    scr = asyncio.run(go())
    assert "Senegal" in scr.country_label.text and "time zone" in scr.country_label.text
    assert [b.text for b in scr.methods_box.children] == ["Wave", "Debit / credit card"]
    assert scr.pay_btn.text == "Pay 3\u202f000 FCFA with Wave" and scr.pay_btn.enabled
