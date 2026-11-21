// Phone menu: open/close, Escape and link clicks close it.
(function () {
  var btn = document.querySelector(".menu-toggle"), nav = document.getElementById("site-nav");
  if (!btn || !nav) return;
  function set(open) { nav.classList.toggle("open", open); btn.setAttribute("aria-expanded", open ? "true" : "false"); }
  btn.addEventListener("click", function () { set(!nav.classList.contains("open")); });
  nav.addEventListener("click", function (e) { if (e.target.closest("a")) set(false); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { set(false); } });
})();

// Code samples with tabs (Python, JavaScript, Terminal). Without JavaScript every sample shows, one after another.
(function () {
  var boxes = document.querySelectorAll("[data-tabs]");
  Array.prototype.forEach.call(boxes, function (box) {
    var tabs = box.querySelectorAll('[role="tab"]'), panels = box.querySelectorAll('[role="tabpanel"]');
    if (!tabs.length) return;
    function pick(i, focus) {
      Array.prototype.forEach.call(tabs, function (t, j) {
        t.setAttribute("aria-selected", j === i ? "true" : "false"); t.tabIndex = j === i ? 0 : -1;
      });
      Array.prototype.forEach.call(panels, function (p, j) { p.hidden = j !== i; });
      if (focus) tabs[i].focus();
    }
    Array.prototype.forEach.call(tabs, function (t, i) {
      t.addEventListener("click", function () { pick(i); });
      t.addEventListener("keydown", function (e) {
        var n = tabs.length, to = e.key === "ArrowRight" ? (i + 1) % n : e.key === "ArrowLeft" ? (i + n - 1) % n :
          e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
        if (to >= 0) { e.preventDefault(); pick(to, true); }
      });
    });
    box.classList.add("tabs-on");
    pick(0);
  });
})();

// The download page: the button for this device first. Without JavaScript, the list below has everything.
(function () {
  var box = document.getElementById("dl-best");
  if (!box) return;
  var ua = navigator.userAgent || "",
      plat = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "",
      dl = box.getAttribute("data-repo") + "/releases/latest/download/", pick = null;
  if (/Android/i.test(ua)) pick = ["Download for Android", dl + "Gink-android.apk", "Android 7 or later. Phone says it isn’t compatible? Choose 32-bit below."];
  else if (/iPhone|iPad|iPod/i.test(ua) || (/Mac/i.test(plat) && navigator.maxTouchPoints > 1))
    pick = ["Open Gink on the web", box.getAttribute("data-web"), "The iPhone and iPad app is coming soon."];
  else if (/Mac/i.test(plat)) pick = ["Download for Mac", dl + "Gink-mac-arm64.dmg", "For Apple Silicon. On an Intel Mac, choose Intel below."];
  else if (/Win/i.test(plat)) pick = ["Download for Windows", dl + "Gink-windows-x64.msi", "Windows 10 or 11, 64-bit."];
  else if (/Linux/i.test(plat)) pick = ["Download for Linux", dl + "Gink-linux-amd64.deb", "Ubuntu 24.04+ or Debian 13+, 64-bit."];
  if (!pick) return;
  var a = box.querySelector("a"), note = box.querySelector(".dl-note");
  a.textContent = pick[0]; a.href = pick[1];
  if (note) note.textContent = pick[2] || "";
  box.hidden = false;
})();
