// Lock Gink in this browser -- for Gink Genie and the developer console (the web app has the same lock built in).
// Settings > Privacy > Lock Gink (stored in this browser: gink_prefs.app_lock, app_lock_after) covers the page when it
// opens and after you've been away, until a passkey on this device says it's you (Face ID, Touch ID, Windows Hello,
// your phone). Inside the Gink Genie app the app itself asks the device (Touch ID, Face ID, Windows Hello) instead:
// gink-genie://unlock -> GinkLock.unlocked() / GinkLock.failed(message). Gink never sees a face or a fingerprint.
(function () {
  "use strict";
  var LS = window.localStorage;
  var IN_APP = /GinkGenieApp/.test(navigator.userAgent || "");
  var state = { locked: false, away: null, busy: false, timer: 0 };

  function prefs() { try { return JSON.parse(LS.getItem("gink_prefs")) || {}; } catch (e) { return {}; } }
  function setPrefs(p) { try { LS.setItem("gink_prefs", JSON.stringify(p)); } catch (e) {} }
  function token() { try { return LS.getItem("gink_token") || sessionStorage.getItem("gink_token") || ""; } catch (e) { return ""; } }
  function enabled() { return !!prefs().app_lock && !!token(); }
  function afterMs() { var v = String(prefs().app_lock_after || "1"); return v === "launch" ? null : (parseFloat(v) || 1) * 60000; }
  function lastActive() { try { return parseFloat(LS.getItem("gink_unlocked_at") || "0") || 0; } catch (e) { return 0; } }
  function markActive() { try { LS.setItem("gink_unlocked_at", String(Date.now())); } catch (e) {} }

  // passkeys: the browser works with bytes, the server with base64url JSON
  function toBuf(s) { s = String(s).replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) s += "=";
    var b = atob(s), a = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a.buffer; }
  function toStr(buf) { if (!buf) return null; var b = new Uint8Array(buf), s = "";
    for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); }
  function post(path, body) {
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + token() },
                         body: JSON.stringify(body || {}) }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { if (!r.ok) throw new Error(j.detail || "That didn’t work."); return j; });
    });
  }
  function passkeyCheck() {
    if (!(window.PublicKeyCredential && navigator.credentials)) return Promise.reject(new Error("This browser doesn’t support passkeys."));
    return post("/account/passkeys/verify/begin").then(function (b) {
      var o = b.options; o.challenge = toBuf(o.challenge);
      (o.allowCredentials || []).forEach(function (c) { c.id = toBuf(c.id); });
      return navigator.credentials.get({ publicKey: o }).then(function (c) {
        return post("/account/passkeys/verify/finish", { request_id: b.request_id, credential: {
          id: c.id, rawId: toStr(c.rawId), type: c.type, clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
          response: { clientDataJSON: toStr(c.response.clientDataJSON), authenticatorData: toStr(c.response.authenticatorData),
                      signature: toStr(c.response.signature), userHandle: toStr(c.response.userHandle) } } });
      });
    }).catch(function (e) {
      if (e && (e.name === "NotAllowedError" || e.name === "AbortError")) throw new Error("Cancelled.");
      throw e;
    });
  }

  // the lock screen (the same look as Gink's)
  function el() { return document.getElementById("gink-lock"); }
  function show(message, busy) {
    var box = el();
    if (!box) {
      var css = document.createElement("style");
      css.textContent = "#gink-lock{position:fixed;top:0;right:0;bottom:0;left:0;z-index:2147483000;display:grid;place-items:center;padding:24px;text-align:center;" +
        "background:radial-gradient(120% 90% at 50% 0%,#1f2b24 0%,#121815 55%,#0c100e 100%);color:#f5f7f4;font:15px/1.45 system-ui,-apple-system,sans-serif}" +
        "#gink-lock .c{width:min(360px,100%);display:flex;flex-direction:column;align-items:center;gap:14px}" +
        "#gink-lock .t{font-size:22px;font-weight:650}#gink-lock .s{color:rgba(245,247,244,.68);font-size:14px;min-height:20px}" +
        "#gink-lock .g{border:0;border-radius:999px;padding:13px 26px;font:inherit;font-weight:650;cursor:pointer;background:#A8F03C;color:#10200a}" +
        "#gink-lock .g:disabled{opacity:.55;cursor:default}#gink-lock .o{background:none;border:0;color:rgba(245,247,244,.6);font:inherit;font-size:13.5px;cursor:pointer}";
      document.head.appendChild(css);
      box = document.createElement("div"); box.id = "gink-lock"; box.setAttribute("role", "dialog"); box.setAttribute("aria-modal", "true");
      box.innerHTML = '<div class="c"><div style="font-size:40px" aria-hidden="true">🔒</div><div class="t">Gink is locked</div>' +
        '<div class="s" aria-live="polite"></div><button type="button" class="g"></button><button type="button" class="o">Sign out</button></div>';
      document.body.appendChild(box);
      box.querySelector(".g").onclick = unlock;
      box.querySelector(".o").onclick = function () {
        try { LS.removeItem("gink_token"); sessionStorage.removeItem("gink_token"); } catch (e) {}
        location.replace("/login?next=" + encodeURIComponent(location.pathname));
      };
    }
    var how = IN_APP ? "Touch ID, Face ID or Windows Hello" : "a passkey";
    box.querySelector(".s").textContent = message || ("Unlock with " + how + ".");
    var go = box.querySelector(".g"); go.disabled = !!busy; go.textContent = busy ? "Checking…" : (IN_APP ? "Unlock" : "Unlock with a passkey");
    if (!busy) setTimeout(function () { try { go.focus(); } catch (e) {} }, 30);
  }
  function lock() {
    if (state.locked) return;
    state.locked = true;
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
    show("");
    if (IN_APP) unlock();                              // the app asks the device straight away
  }
  function unlock() {
    if (state.busy) return;
    state.busy = true; show("", true);
    if (IN_APP) {                                      // the Gink Genie app answers with GinkLock.unlocked() / .failed()
      clearTimeout(state.timer);
      state.timer = setTimeout(function () { if (state.busy) window.GinkLock.failed("Update the Gink Genie app to unlock it, or open Genie in your browser."); }, 60000);
      location.href = "gink-genie://unlock";
      return;
    }
    passkeyCheck().then(function () { window.GinkLock.unlocked(); }, function (e) { window.GinkLock.failed(e.message); });
  }
  window.GinkLock = {
    unlocked: function () { clearTimeout(state.timer); state.busy = false; state.locked = false; state.away = null; markActive();
                            var box = el(); if (box) box.remove(); },
    failed: function (message) { clearTimeout(state.timer); state.busy = false; show(message || "Not unlocked."); },
    lockNow: lock,
    checkAway: function (ms) {                         // the Gink Genie app: away from its window this long
      var after = afterMs();
      if (enabled() && after !== null && ms >= after) lock();
    },
    // Gink Genie's Settings: on or off -- the device (or a passkey) proves it's you first
    toggle: function (on, done) {
      var finish = function (ok, message) { if (ok) { var p = prefs(); p.app_lock = !!on; setPrefs(p); markActive(); } if (done) done(ok, message); };
      if (IN_APP) { window.GinkLock._pending = finish; location.href = "gink-genie://lock-" + (on ? "on" : "off"); return; }
      passkeyCheck().then(function () { finish(true); }, function (e) { finish(false, e.message); });
    },
    toggled: function (ok, message) { var f = window.GinkLock._pending; window.GinkLock._pending = null; if (f) f(!!ok, message); },
    enabled: enabled
  };
  document.addEventListener("keydown", function (e) {           // locked: keys reach only the lock screen
    var box = el(); if (box && !box.contains(e.target)) { e.preventDefault(); e.stopPropagation(); }
  }, true);
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) { if (!state.locked) state.away = Date.now(); return; }
    var after = afterMs();
    if (enabled() && after !== null && state.away && Date.now() - state.away >= after) lock();
    state.away = null;
  });
  setInterval(function () { if (!state.locked && !document.hidden) markActive(); }, 20000);
  function start() {
    var after = afterMs();
    if (enabled() && Date.now() - lastActive() > (after === null ? 60000 : after)) lock(); else if (!state.locked) markActive();
  }
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
})();
