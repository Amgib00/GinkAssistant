// Gink Pro prices on the website.
// The app's server shows the real prices (GINK_PRICES on the server). These below are
// the PLACEHOLDERS from services/billing_catalog.py -- keep PRICES_CONFIRMED false until
// they match what you actually charge, then set it to true to show them here.
var PRICES_CONFIRMED = false;
var PRICES = {
  XOF: { label: "FCFA", m1: 3000, m3: 8000, m12: 30000, zero: true },
  NGN: { label: "NGN", m1: 4500, m3: 12000, m12: 45000 },
  GHS: { label: "GHS", m1: 60, m3: 160, m12: 600 },
  KES: { label: "KES", m1: 650, m3: 1750, m12: 6500 },
  ZAR: { label: "ZAR", m1: 90, m3: 240, m12: 900 },
  USD: { label: "USD", m1: 5, m3: 13, m12: 50 }
};
(function () {
  if (!PRICES_CONFIRMED) return;
  var box = document.getElementById("currency"), price = document.getElementById("pro-price"), note = document.getElementById("pro-note");
  function money(v, c) { return (c === "XOF" ? v.toLocaleString("fr-FR") + " FCFA" : PRICES[c].label + " " + v.toLocaleString()); }
  function show(c) {
    var p = PRICES[c];
    price.classList.remove("price-later");
    price.innerHTML = "";
    price.appendChild(document.createTextNode(money(p.m1, c) + " "));
    var s = document.createElement("small"); s.textContent = "a month"; price.appendChild(s);
    note.textContent = "Or " + money(p.m3, c) + " for 3 months, " + money(p.m12, c) + " for a year.";
    box.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.c === c ? "true" : "false"); });
  }
  Object.keys(PRICES).forEach(function (c) {
    var b = document.createElement("button"); b.type = "button"; b.dataset.c = c; b.textContent = PRICES[c].label;
    b.addEventListener("click", function () { show(c); }); box.appendChild(b);
  });
  box.hidden = false;
  show("XOF");
})();
