// Phone menu: open/close, Escape and link clicks close it.
(function () {
  var btn = document.querySelector(".menu-toggle"), nav = document.getElementById("site-nav");
  if (!btn || !nav) return;
  function set(open) { nav.classList.toggle("open", open); btn.setAttribute("aria-expanded", open ? "true" : "false"); }
  btn.addEventListener("click", function () { set(!nav.classList.contains("open")); });
  nav.addEventListener("click", function (e) { if (e.target.closest("a")) set(false); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") { set(false); } });
})();
