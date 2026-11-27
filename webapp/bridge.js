/* Gink on the web -- the "bridge".
   The desktop app's chat page sends events (ginkEmit) to Python. On the web, this
   script handles them in the browser and talks ONLY to the Gink server that served
   the page (sign-in, AI, formatting, sync, images, voices).
   Chats are stored in the same format the desktop app syncs, so they appear on both. */
(function () {
  "use strict";
  var LS = window.localStorage;
  window.GINK_ICONS = "";              // the sources' real logos: this server's /icon/{host} (same site)
  function load(k, d) { try { var v = JSON.parse(LS.getItem(k)); return v == null ? d : v; } catch (e) { return d; } }
  function save(k, v) { try { LS.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function tokenName(t) {             // the account's name rides in the sign-in token (for "Hi Ibrahim")
    try { var p = String(t || "").split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
          return String(JSON.parse(decodeURIComponent(escape(atob(p + "===".slice((p.length + 3) % 4))))).name || ""); } catch (e) { return ""; }
  }

  var W = {
    // "Remember me" off keeps the sign-in in sessionStorage (until the browser closes): read both
    token: LS.getItem("gink_token") || sessionStorage.getItem("gink_token") || "",
    email: LS.getItem("gink_email") || sessionStorage.getItem("gink_email") || "",
    name: LS.getItem("gink_name") || sessionStorage.getItem("gink_name") ||
          tokenName(LS.getItem("gink_token") || sessionStorage.getItem("gink_token")),
    model: LS.getItem("gink_model") || "", models: [],
    sessions: load("gink_sessions", {}), dirty: load("gink_dirty", {}), since: parseFloat(LS.getItem("gink_since") || "0"),
    prefs: Object.assign({ theme: "system", chat_font: "sans", motion: "system", read_aloud: false, voice: "Female (Jenny)", reply_language: "auto",
                           style_base: "default", style_warmth: "default", style_enthusiasm: "default", style_emoji: "default", style_headers: "default" },
                         load("gink_prefs", {})),      // defaults first, so new settings show their real value
    current: null, busy: null, pendingCode: null, syncing: false
  };
  var DESKTOP_ONLY = "That\u2019s available in the Gink app on your computer or phone.";
  var PRICING = "https://amgib00.github.io/GinkAssistant/pricing.html";      // the website's plans page

  // ---------------------------------------------------------------- server
  function utcOffset() {                         // "+01:00": the clock only, no time zone name or region
    var m = -new Date().getTimezoneOffset(), a = Math.abs(m);
    return (m >= 0 ? "+" : "-") + ("0" + Math.floor(a / 60)).slice(-2) + ":" + ("0" + a % 60).slice(-2);
  }
  function placeHeaders(h) {                     // the device's time zone + language: answers fit their own country
    if (W.prefs.location_metadata === false) {   // Settings > Privacy > Location metadata off: the clock only
      h["X-Gink-Location"] = "off"; h["X-Gink-UTC-Offset"] = utcOffset(); return h;
    }
    try { var tz = Intl.DateTimeFormat().resolvedOptions().timeZone; if (tz) h["X-Gink-TZ"] = tz; } catch (e) {}
    try { var lang = (navigator.languages && navigator.languages[0]) || navigator.language; if (lang) h["X-Gink-Locale"] = lang; } catch (e) {}
    return h;
  }
  function api(path, body, opts) {
    opts = opts || {};
    var h = placeHeaders({ "Content-Type": "application/json" });
    if (W.token) h.Authorization = "Bearer " + W.token;
    return fetch(path, { method: body === undefined ? "GET" : "POST", headers: h,
                         body: body === undefined ? undefined : JSON.stringify(body), signal: opts.signal })
      .then(function (r) {
        if (r.status === 401 && W.token && !opts.noLogout) { signOut("Your session has ended. Please log in again."); throw new Error("signed out"); }
        return r;
      });
  }
  // ---- passkeys (WebAuthn): the browser works with bytes, the server with base64url JSON
  var WA = {
    toBuf: function (s) { s = String(s).replace(/-/g, "+").replace(/_/g, "/"); while (s.length % 4) s += "=";
      var b = atob(s), a = new Uint8Array(b.length); for (var i = 0; i < b.length; i++) a[i] = b.charCodeAt(i); return a.buffer; },
    toStr: function (buf) { if (!buf) return null; var b = new Uint8Array(buf), s = "";
      for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, ""); },
    create: function (o) {
      o.challenge = WA.toBuf(o.challenge); o.user.id = WA.toBuf(o.user.id);
      (o.excludeCredentials || []).forEach(function (c) { c.id = WA.toBuf(c.id); });
      return navigator.credentials.create({ publicKey: o }).then(function (c) {
        return { id: c.id, rawId: WA.toStr(c.rawId), type: c.type, authenticatorAttachment: c.authenticatorAttachment || undefined,
                 clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
                 response: { clientDataJSON: WA.toStr(c.response.clientDataJSON), attestationObject: WA.toStr(c.response.attestationObject),
                             transports: c.response.getTransports ? c.response.getTransports() : [] } };
      });
    },
    get: function (o) {
      o.challenge = WA.toBuf(o.challenge);
      (o.allowCredentials || []).forEach(function (c) { c.id = WA.toBuf(c.id); });
      return navigator.credentials.get({ publicKey: o }).then(function (c) {
        return { id: c.id, rawId: WA.toStr(c.rawId), type: c.type, authenticatorAttachment: c.authenticatorAttachment || undefined,
                 clientExtensionResults: c.getClientExtensionResults ? c.getClientExtensionResults() : {},
                 response: { clientDataJSON: WA.toStr(c.response.clientDataJSON), authenticatorData: WA.toStr(c.response.authenticatorData),
                             signature: WA.toStr(c.response.signature), userHandle: WA.toStr(c.response.userHandle) } };
      });
    },
    supported: function () { return !!(window.PublicKeyCredential && navigator.credentials); },
    cancelled: function (e) { return e && (e.name === "NotAllowedError" || e.name === "AbortError"); }
  };

  // ---- usage limit: the reset time in the person's own time, and a notice when it has reset
  function localReset(at) {
    var d = new Date(at * 1000), t = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    var today = new Date(), tomorrow = new Date(today.getTime() + 86400000);
    var day = d.toDateString() === today.toDateString() ? "today" : d.toDateString() === tomorrow.toDateString() ? "tomorrow"
            : d.toLocaleDateString([], { weekday: "long" });
    return t + " " + day;
  }
  function notice(text) {
    var old = document.getElementById("gink-notice"); if (old) old.remove();
    var box = document.createElement("div"); box.id = "gink-notice"; box.setAttribute("role", "status");
    box.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:9999;max-width:340px;display:flex;gap:12px;align-items:flex-start;" +
      "padding:14px 16px;border-radius:14px;background:var(--surface, #fff);color:var(--text, #151D23);" +
      "border:1px solid var(--border, rgba(0,0,0,.12));box-shadow:0 8px 28px rgba(0,0,0,.18);font:14px/1.45 system-ui,sans-serif";
    var msg = document.createElement("div"); msg.textContent = text; msg.style.flex = "1";
    var x = document.createElement("button"); x.textContent = "\u00d7"; x.setAttribute("aria-label", "Close");
    x.style.cssText = "border:0;background:none;color:inherit;font-size:18px;line-height:1;cursor:pointer;padding:0 2px";
    x.onclick = function () { box.remove(); };
    box.appendChild(msg); box.appendChild(x); document.body.appendChild(box);
  }
  function watchReset(at) {
    try { LS.setItem("gink_limit_reset", String(at)); } catch (e) {}
    var wait = at * 1000 - Date.now();
    if (wait <= 0) {
      try { LS.removeItem("gink_limit_reset"); } catch (e) {}
      return notice("Your usage limit has reset \u2014 you can send new messages. Pick up where you left off?");
    }
    if (wait < 2147483647) setTimeout(function () { watchReset(at); }, wait + 1500);
  }
  (function () { var at = Number(LS.getItem("gink_limit_reset") || 0); if (at) watchReset(at); })();

  function errorText(r) {
    return r.json().then(function (j) {
      var e = j.error || {};
      if (e.code === "daily_limit" && e.resets_at) {
        watchReset(e.resets_at);
        return String(e.message || "").replace(/at midnight \(UTC\)|midnight \(UTC\)/, "at " + localReset(e.resets_at));
      }
      var msg = (j.error && (j.error.message || j.error)) || j.detail || ("Something went wrong (" + r.status + ").");
      // the server says it in plain words (0.1.163); an older one passed the AI provider's own message on -- never
      // shown ("... in organization org_... Upgrade to Dev Tier")
      if (/\borg_[A-Za-z0-9]{6,}|Need more tokens|service tier/.test(String(msg)))
        return r.status === 413 ? "This chat has grown too long for Gink’s AI to read in one go. Start a new chat for the next step, or ask for a smaller change."
          : r.status === 429 ? "Gink’s AI is busy right now. Please try again in a little while."
          : "The AI service had a problem. Please try again in a moment.";
      if (r.status === 429 && e.code !== "daily_limit" && e.code !== "turn_limit" && e.code !== "busy")
        return "Gink’s AI is busy right now. Please try again in a little while.";
      return msg;
    }).catch(function () { return "Something went wrong (" + r.status + ")."; });
  }

  // ---------------------------------------------------------------- sign in
  var $ = function (id) { return document.getElementById(id); };
  function showSignIn(message) {
    // The full sign-in page (/login): log in, create account, codes, reset, two-step, Google...
    if (location.pathname.indexOf("/app") === 0) {
      location.replace("/login?next=" + encodeURIComponent(location.pathname + location.hash) + (message ? "&reason=ended" : ""));
      return;
    }
    $("web-signin").classList.add("open");
    if ($("ws-signup").hidden) tab("login");          // always start from a usable form (not a finished code step)
    $("ws-err").textContent = message || "";
    setTimeout(function () { ($("ws-login").hidden ? $("ws-semail") : $("ws-email")).focus(); }, 30);
  }
  function tab(which) {
    $("ws-tab-login").setAttribute("aria-selected", which === "login" ? "true" : "false");
    $("ws-tab-signup").setAttribute("aria-selected", which === "signup" ? "true" : "false");
    $("ws-login").hidden = which !== "login"; $("ws-signup").hidden = which !== "signup"; $("ws-code").hidden = true;
    $("ws-twofa").hidden = true; W.ticket = null;
    $("ws-err").textContent = "";
  }
  function busyForm(form, on) { var b = form.querySelector(".ws-go"); if (b) b.disabled = on; }
  function signedIn(res) {
    if (res && res.twofa_required) {                 // two-step sign-in: the authenticator code comes next
      W.ticket = res.ticket; W.email = res.email || W.email;
      ["ws-login", "ws-signup", "ws-code"].forEach(function (id) { $(id).hidden = true; });
      $("ws-twofa").hidden = false; $("ws-tfcode").value = ""; $("ws-tfcode").focus();
      $("ws-err").textContent = "";
      return;
    }
    W.token = res.token; W.email = res.email || W.email; W.name = res.name || W.name || "";
    LS.setItem("gink_token", W.token); LS.setItem("gink_email", W.email); LS.setItem("gink_name", W.name);
    $("web-signin").classList.remove("open");
    start();
  }
  function wireSignIn() {
    socialButtons(); wireTwoStep();
    $("ws-tab-login").onclick = function () { tab("login"); };
    $("ws-tab-signup").onclick = function () { tab("signup"); };
    $("ws-login").onsubmit = function (e) {
      e.preventDefault(); var f = e.target; busyForm(f, true); $("ws-err").textContent = "";
      W.email = $("ws-email").value.trim();
      api("/auth/login", { email: W.email, password: $("ws-pass").value }, { noLogout: true }).then(function (r) {
        return r.ok ? r.json().then(signedIn) : errorText(r).then(function (t) { $("ws-err").textContent = t; });
      }).catch(function () { $("ws-err").textContent = "Can't reach the Gink server."; }).then(function () { busyForm(f, false); });
    };
    $("ws-signup").onsubmit = function (e) {
      e.preventDefault(); var f = e.target; busyForm(f, true); $("ws-err").textContent = "";
      W.email = $("ws-semail").value.trim(); W.name = $("ws-name").value.trim();
      api("/auth/register", { email: W.email, name: W.name, password: $("ws-spass").value }, { noLogout: true }).then(function (r) {
        if (!r.ok) return errorText(r).then(function (t) { $("ws-err").textContent = t; });
        $("ws-signup").hidden = true; $("ws-code").hidden = false; $("ws-codein").focus();
      }).catch(function () { $("ws-err").textContent = "Can't reach the Gink server."; }).then(function () { busyForm(f, false); });
    };
    $("ws-code").onsubmit = function (e) {
      e.preventDefault(); var f = e.target; busyForm(f, true); $("ws-err").textContent = "";
      api("/auth/register/verify", { email: W.email, code: $("ws-codein").value.trim() }, { noLogout: true }).then(function (r) {
        return r.ok ? r.json().then(signedIn) : errorText(r).then(function (t) { $("ws-err").textContent = t; });
      }).catch(function () { $("ws-err").textContent = "Can't reach the Gink server."; }).then(function () { busyForm(f, false); });
    };
  }
  function wireTwoStep() {
    $("ws-twofa").onsubmit = function (e) {
      e.preventDefault(); var f = e.target; busyForm(f, true); $("ws-err").textContent = "";
      api("/auth/2fa", { ticket: W.ticket, code: $("ws-tfcode").value.trim() }, { noLogout: true }).then(function (r) {
        return r.ok ? r.json().then(signedIn) : errorText(r).then(function (t) { $("ws-err").textContent = t; });
      }).catch(function () { $("ws-err").textContent = "Can't reach the Gink server."; }).then(function () { busyForm(f, false); });
    };
  }
  // ---- Google / GitHub / Microsoft / Apple: the server's own sign-in flow
  //      (begin -> provider page in a pop-up -> the page asks /auth/poll until it's done)
  function socialButtons() {
    api("/auth/providers", undefined, { noLogout: true }).then(function (r) { return r.ok ? r.json() : {}; }).then(function (all) {
      var box = $("ws-social"); box.innerHTML = "";
      Object.keys(all || {}).forEach(function (key) {
        if (!all[key].enabled) return;
        var b = document.createElement("button"); b.type = "button";
        b.textContent = "Continue with " + all[key].label;
        b.onclick = function () { socialSignIn(key, b); };
        box.appendChild(b);
      });
      $("ws-social-wrap").hidden = !box.children.length;
    }).catch(function () {});
  }
  function socialSignIn(provider, btn) {
    var bytes = new Uint8Array(24); crypto.getRandomValues(bytes);
    var state = Array.prototype.map.call(bytes, function (x) { return ("0" + x.toString(16)).slice(-2); }).join("");
    // open the window NOW (inside the click), so pop-up blockers allow it
    var win = window.open("", "gink_signin", "width=520,height=700");
    if (!win) { $("ws-err").textContent = "Allow pop-ups for this page, then try again."; return; }
    btn.disabled = true; $("ws-err").textContent = "Finish signing in in the window that opened\u2026";
    api("/auth/" + provider + "/begin", { state: state }, { noLogout: true }).then(function (r) {
      if (!r.ok) return errorText(r).then(function (t) { throw new Error(t); });
      win.location.href = "/auth/" + provider + "/start?state=" + encodeURIComponent(state);
      var started = Date.now(), closedAt = 0;
      return new Promise(function (resolve, reject) {
        (function check() {
          if (Date.now() - started > 5 * 60 * 1000) return reject(new Error("Sign-in timed out. Try again."));
          // The pop-up was closed: check a few more seconds (it may have just finished), then stop waiting
          if (win.closed && !closedAt) closedAt = Date.now();
          if (closedAt && Date.now() - closedAt > 4000) {
            return reject(new Error("The sign-in window was closed before it finished. Try again."));
          }
          api("/auth/poll?state=" + state, undefined, { noLogout: true }).then(function (r) {
            if (r.status === 200) return r.json().then(function (j) { j.status === "pending" ? setTimeout(check, 1500) : resolve(j); });
            return errorText(r).then(function (t) { reject(new Error(t)); });
          }).catch(function () { setTimeout(check, 3000); });
        })();
      });
    }).then(function (res) {
      try { win.close(); } catch (e) {}
      $("ws-err").textContent = ""; signedIn(res);
    }).catch(function (e) {
      try { win.close(); } catch (x) {}
      $("ws-err").textContent = (e && e.message) || "Sign-in didn't finish. Try again.";
    }).then(function () { btn.disabled = false; });
  }
  function signOut(message) {
    W.token = ""; LS.removeItem("gink_token"); try { sessionStorage.removeItem("gink_token"); } catch (e) {}
    if (W.busy && W.busy.abort) W.busy.abort();
    showSignIn(message);
  }

  // ---------------------------------------------------------------- chats (desktop sync format)
  function now() { return Date.now() / 1000; }
  function stamp() { return new Date().toISOString().replace("T", " ").slice(0, 19); }
  function uid() { return (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)); }
  function persist() {                                   // temporary chats are never stored (nor synced)
    var keep = {}; Object.keys(W.sessions).forEach(function (k) { if (!W.sessions[k].temporary) keep[k] = W.sessions[k]; });
    save("gink_sessions", keep); save("gink_dirty", W.dirty);
  }
  function touch(id) { var s = W.sessions[id]; if (!s) return; s.updated = now(); if (!s.temporary) W.dirty[id] = true; persist(); }
  function leaveTemporary() {                            // a temporary chat is gone once you leave it
    var s = W.current && W.sessions[W.current];
    if (s && s.temporary) { delete W.sessions[W.current]; delete W.dirty[W.current]; }
    W.tempMode = false; setTemporary(false);
  }
  function titleOf(s) {
    if (s.title) return s.title;
    var first = (s.messages || []).filter(function (m) { return m.role === "user"; })[0];
    return first ? first.content.replace(/\s+/g, " ").slice(0, 60) : "New chat";
  }
  function refreshSidebar() {
    var list = Object.keys(W.sessions).map(function (k) { return W.sessions[k]; })
      .filter(function (s) { return !s.deleted && !s.archived && !s.temporary && (s.messages || []).length; })
      .sort(function (a, b) { return (b.pinned - a.pinned) || (b.updated - a.updated); })
      .map(function (s) { return { id: s.id, title: titleOf(s), current: s.id === W.current, pinned: !!s.pinned,
                                   when: Math.round((s.updated || 0) * 1000) }; });      // grouped by day in the sidebar
    setSessions(list);
  }
  setTimeout(function () { setPrompts(myPrompts()); syncPrompts(); }, 0);   // the "/" menu knows your prompts
  function newChat() {
    leaveTemporary();
    W.current = null; clearFeed();
    var first = (W.name || W.email || "").split(/[\s@]/)[0];
    var endings = ["what\u2019s on your mind?", "how can I help today?", "what shall we work on?",
                   "what would you like to explore?", "ready when you are."];
    var ending = endings[Math.floor(Math.random() * endings.length)];
    if (/\d{3,}/.test(first) || first === (W.email || "").split("@")[0]) first = "";    // never a name made from the email
    showWelcome(first ? "Hi " + first : "Hi there", ending.charAt(0).toUpperCase() + ending.slice(1));   // like the designs
    setComposerText(load("gink_draft_new", "") || "");
    refreshSidebar();
  }
  // An answer's text -> the server's formatting, for this visit: a chat opened again shows formatted at once (0.1.163)
  var RENDERED = typeof Map === "function" ? new Map() : null;
  function remember(text, html) {
    if (!RENDERED || typeof html !== "string") return;
    RENDERED.delete(text); RENDERED.set(text, html);
    if (RENDERED.size > 400) RENDERED.delete(RENDERED.keys().next().value);
  }
  function openSession(id) {
    window.__sentAt = 0;                                     // an old chat: its code never opens by itself
    if (id !== W.current) leaveTemporary();
    var s = W.sessions[id]; if (!s || s.deleted) return newChat();
    W.current = id; clearFeed(); hideWelcome();
    var msgs = s.messages || [], answers = [], after = {}, waiting = [];
    msgs.forEach(function (m, i) {
      if (m.role === "user") {
        addUserMessage(m.content);
        waiting.forEach(function (aid) { after[aid] = m.content; }); waiting = [];       // the reply to those answers
      } else { var aid = "w" + i + "-" + uid().slice(0, 8); addAssistantMessage(aid); answers.push([aid, m.content]); waiting.push(aid); }
    });
    // An answer formatted: as history (no task made again), and its question cards closed with what came next -- the
    // web app formats after the chat is drawn, so they stayed open and blank before (0.1.163)
    function show(aid, html) {
      (window.finalizeOld || finalizeMessage)(aid, html);
      if (after[aid] != null && window.closeQuestionCards) closeQuestionCards(after[aid], document.getElementById(aid));
    }
    var todo = [];
    answers.forEach(function (a) {
      var known = RENDERED && RENDERED.get(a[1] || "");
      if (typeof known === "string") show(a[0], known);
      else {
        // Saved answers show at once, already readable (never "Thinking...", never **raw** Markdown or an artifact's
        // code), then get the server's formatting when it arrives -- /render can be slow or not answer at all.
        (window.setQuickHtml || setPlainText)(a[0], a[1] || ""); todo.push(a);
      }
    });
    if (answers.length) { if (window.glideToEnd) glideToEnd(); }     // glide to the end of the opened chat
    if (todo.length) {
      var opened = id;
      var slow = new Promise(function (_, reject) { setTimeout(function () { reject(new Error("slow")); }, 10000); });
      Promise.race([api("/render", { items: todo.map(function (a) { return a[1] || ""; }) }), slow])
        .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error("render " + r.status)); })
        .then(function (j) {
          if (!j || !Array.isArray(j.html)) return;
          todo.forEach(function (a, i) { remember(a[1] || "", j.html[i]); });
          if (W.current !== opened) return;                    // another chat is open now
          todo.forEach(function (a, i) { if (typeof j.html[i] === "string") show(a[0], j.html[i]); });
          if (window.ginkScrollEnd) ginkScrollEnd(true);   // formatted answers can be taller
        }).catch(function () { /* the quick formatting stays: still readable */ });
    }
    setComposerText((load("gink_drafts", {}))[id] || "");
    refreshSidebar();
  }

  // ---------------------------------------------------------------- talking to the AI
  function niceModel(id) {             // "openai/gpt-oss-120b" -> "GPT-OSS 120B", "claude-sonnet-5-5" -> "Claude Sonnet 5.5"
    var GINK = { "gink-search": "Gink Search \u00b7 Free \u00b7 searches the web",
                 "openai/gpt-oss-20b": "Gink Flake \u00b7 Free \u00b7 GPT-OSS",            // Gink's names
                 "openai/gpt-oss-120b": "Gink Crystal \u00b7 Free \u00b7 GPT-OSS",
                 "qwen/qwen3.8-27b": "Gink Prism \u00b7 Free \u00b7 Qwen",
                 "claude-haiku-5-5": "Gink Flurry \u00b7 Pro \u00b7 Claude", "claude-sonnet-5-5": "Gink Frost \u00b7 Pro \u00b7 Claude",
                 "claude-opus-5-5": "Gink Glacier \u00b7 Pro \u00b7 Claude", "claude-fable-5-1": "Gink Aurora \u00b7 Pro \u00b7 Claude" };
    if (GINK[id]) return GINK[id];
    if (/^gink-/.test(String(id)))                    // Gink's own model (tools/gink_model): "gink-1" -> "Gink 1"
      return "Gink " + String(id).slice(5).split("-").map(function (w) { return w.charAt(0).toUpperCase() + w.slice(1); }).join(" ");
    var c = /^claude-([a-z]+)-(\d+)-(\d+)$/.exec(String(id));
    if (c) return "Claude " + c[1].charAt(0).toUpperCase() + c[1].slice(1) + " " + c[2] + "." + c[3] + " \u00b7 Pro";
    var n = String(id).split("/").pop().replace(/[-_]/g, " ");
    n = n.replace(/\b(\d+(?:\.\d+)?)([bkm])\b/gi, function (m, a, b) { return a + b.toUpperCase(); })
         .replace(/\bgpt oss\b/i, "GPT-OSS").replace(/\b(gpt|llm|ai)\b/gi, function (m) { return m.toUpperCase(); })
         .replace(/\b([a-z])/g, function (m) { return m.toUpperCase(); });
    return n;
  }
  function narrow(t) { return String(t).replace(/[\u202f\u2009\u200a\u2006\u2005\u2007]/g, " "); }
  // Settings > Personalization (mirrors services/personality.py)
  var STYLE_NOTES = { professional: "Write in a polished, professional tone.", friendly: "Write in a warm, friendly, conversational tone.",
    concise: "Be brief and to the point: short answers, no filler.", candid: "Be direct and candid: say plainly what you think, including disagreement.",
    playful: "Be playful and lighthearted where it fits, without getting in the way of the answer." };
  var LEVEL_NOTES = {
    style_warmth: { less: "Keep a neutral, matter-of-fact warmth.", more: "Be especially warm, encouraging and kind." },
    style_enthusiasm: { less: "Keep enthusiasm low-key; avoid exclamation marks.", more: "Be upbeat and enthusiastic." },
    style_emoji: { less: "Don't use emoji.", more: "Use a few fitting emoji." },
    style_headers: { less: "Prefer flowing paragraphs; avoid headers and bullet lists unless asked.", more: "Use headers and lists to structure longer answers." } };
  function personalityNote() {
    var parts = [STYLE_NOTES[W.prefs.style_base] || ""];
    Object.keys(LEVEL_NOTES).forEach(function (k) { parts.push(LEVEL_NOTES[k][W.prefs[k]] || ""); });
    var text = parts.filter(Boolean).join(" ");
    return text ? " How to write (the user's personalization): " + text : "";
  }
  function systemPrompt(voice) {
    var lang = W.prefs.reply_language && W.prefs.reply_language !== "auto" ? " Always answer in this language: " + W.prefs.reply_language + "." :
      " Reply in the same language the user writes in (for example French to French, Wolof to Wolof). If they mix languages, use the main one.";
    var who = W.name ? " The user's name is " + W.name.split(" ")[0] + "." : "";
    return "You are Gink, a warm, capable AI assistant. Answer clearly and helpfully, using Markdown for structure when it helps. " +
           "It is now " + new Date().toLocaleString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric",
           hour: "2-digit", minute: "2-digit" }) + " in the user's time zone (" +
           (Intl.DateTimeFormat().resolvedOptions().timeZone || "unknown") + "). Use this for any question about the time or date." +
           who + lang + personalityNote() +
           " Gink can build and edit websites for the user: never say you can't change their website. If they ask to" +
           " change it, tell them to say what to change (for example \u201cchange my website: add a photo gallery\u201d) and Gink will update it." +
           " When you have web search results, use them and keep the facts accurate." +
           " You're running in a web browser: you can't set alarms, reminders or tasks or control the user's computer here; " +
           "if asked, say that the Gink app can do it." + deviceNote() + " " + ABOUT_GINK +
           (voice ? " You're in a live voice conversation: reply in one to three short, natural spoken sentences, " +
                    "with no lists, headings, code, links or emojis." : "") +
           (W.prefs.instructions ? "\n\nThe person's own instructions for you (follow them unless they're unsafe): " +
                                  String(W.prefs.instructions).slice(0, 2000) : "") + profileNote() + memoryNote() +
           (voice ? "" : " " + MAP_PROMPT + " " + ARTIFACT_PROMPT + " " + SCHEDULE_PROMPT) +
           (voice ? "" : " " + ASK_PROMPT);
  }
  // What Gink knows about itself: the same words as services/about_gink.py (a test keeps them equal)
  var ABOUT_GINK = "About you: you are Gink, an AI assistant made by Gink AI (developer: Amgib00), with apps for Mac, Windows, Linux and Android, a web app and Gink Genie for building apps and websites. Your website is https://amgib00.github.io/GinkAssistant/ (downloads at https://amgib00.github.io/GinkAssistant/download.html), your source code is on GitHub at https://github.com/Amgib00/GinkAssistant, the developer platform (API keys, docs) is https://gink-server.onrender.com/developers and support is gink@ginkaisupport.com. When asked about Gink, its website, repository, download or support, give these exact links -- never a placeholder. What you can do now (0.1.164): scheduled tasks -- Gink's server does a task later or on a repeat by itself and the result arrives in its own chat (made from a chat or Settings > Scheduled tasks; Free has 3, Gink Pro 25 and hourly ones); artifacts -- pages, small apps, React apps, charts, tables (CSV), slides, SVGs, diagrams, documents and code files open beside the chat with their versions, a preview, Copy and Download; long chats keep working (older versions are left out to fit the AI's limits); you open the links people share, by yourself -- pages, PDFs, pictures, and social media posts and reels (Facebook, Instagram, TikTok, YouTube, X...): who posted it, its caption, what its picture shows; a reel attached as a video file you watch whole -- and search the web when an answer needs it; you read GitHub repositories, and on a computer you can work on code projects and run their tests; you watch videos people attach (a few frames, in order); in the Gink apps, something to do on the device -- a check of the camera, microphone or the whole device, an alarm, an app to open -- goes to Gink's own tools by itself, and Gink's notifications also show in the device's notifications. Your logo: a lime-green snowflake with six rounded arms on a dark navy rounded square -- the same snowflake turns while you work and marks the end of your answers. A picture of it is Gink's logo (you), not Snowflake Inc.'s (theirs is a light-blue snowflake).";
  // Which device the person is on, from their browser -- "which device am I using?" gets an answer, not a question
  function deviceNote() {
    var ua = navigator.userAgent || "", touch = (navigator.maxTouchPoints || 0) > 1;
    var os = /Android/.test(ua) ? "an Android phone or tablet" : /iPhone|iPod/.test(ua) ? "an iPhone" :
             /iPad/.test(ua) || (/Macintosh/.test(ua) && touch) ? "an iPad" : /Mac OS X|Macintosh/.test(ua) ? "a Mac" :
             /Windows/.test(ua) ? "a Windows PC" : /CrOS/.test(ua) ? "a Chromebook" : /Linux/.test(ua) ? "a Linux computer" : "";
    var br = /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera" : /Firefox\//.test(ua) ? "Firefox" :
             /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "a web browser";
    return os ? " The person is using Gink on the web, in " + br + " on " + os + " (from their browser). If they ask which " +
                "device or system they're using, tell them -- never ask which operating system they have. If they ask you to " +
                "check their device, say the Gink app does a full check by itself (" + "https://amgib00.github.io/GinkAssistant/download.html" + ")." : "";
  }
  // automatic (0.1.163): open requests are made, not questioned; question cards only for what only the person knows.
  // The same words as the apps' ASK_PROMPT (services/groq_worker.py; a test keeps them equal)
  var ASK_PROMPT = "Be automatic: when a request is open or leaves details to you -- \"make me anything\", \"surprise me\", \"add more to it\", \"continue\", \"improve it\", \"make it better\" -- don't ask what they want: choose something good yourself and make it, complete, then say in one short line what you chose and offer an idea or two for next. Only when you truly can't do a good job without something only they know (their own situation, their details, a date) ask 1 to 3 short questions as tappable choices: write one short sentence, then a fenced code block with the language ask containing JSON like {\"questions\": [{\"q\": \"Your question?\", \"options\": [\"Choice 1\", \"Choice 2\", \"Choice 3\"]}]} (2 to 4 short options each, never an \"Other\" option: the person can always type their own answer). Their reply starts with \"My answers:\" and lists each question with what they chose: those are answers about them and their situation, so carry on with what they asked for, without asking again. Never ask about style, colours or features you can choose well yourself, and don't ask for simple questions, facts, or when they already said what they want.";
  // automatic artifacts (0.1.161): the same words as the server's and the apps' ARTIFACT_PROMPT
  var ARTIFACT_PROMPT = "When you make something complete the person will keep or use -- a web page or small app (one HTML file with its CSS and JavaScript inside), a React component (jsx), an SVG image or logo, a diagram (Mermaid), a chart (chart: Chart.js JSON), a table of data (csv), slides (Markdown, one slide per part, parts split by a line with ---), a document written to keep (a letter, report, plan, essay, CV) or a code file longer than about 20 lines -- put it in ONE fenced block whose first line has its language and a short title, like ```html title=\"Pomodoro timer\", ```jsx title=\"Habit tracker\", ```svg title=\"Logo\", ```mermaid title=\"Sign-up flow\", ```chart title=\"Sales by month\", ```csv title=\"Budget\", ```slides title=\"Pitch\", ```document title=\"Cover letter\" (Markdown inside) or ```python title=\"invoice.py\". Gink shows it as an artifact the person can open, preview, copy and download -- never tell them to save, copy or paste it into a file. Make it excellent and finished: real content (no lorem ipsum, no \"...\" or placeholders), a clean modern design that works on a phone and in dark mode with readable colours, and everything working inside that one block (libraries only from cdnjs.cloudflare.com, cdn.jsdelivr.net or unpkg.com). Introduce it in a sentence and don't repeat it in your text. When they ask for changes or more, write the whole new version in a block with the same title, keeping everything that was there unless they asked to remove it. Short snippets and commands stay normal code blocks, with no title.";
  // maps in answers (the page draws them by itself): the same words as the server's and the apps' MAP_PROMPT
  var SCHEDULE_PROMPT = "When the person asks you to do something at a later time or on a repeat -- \"every morning at 8, give me the top news\", \"remind me on Friday at 5pm to call Sam\", \"each Monday, plan my week\" -- Gink can schedule it: say in one short sentence what will happen and when, then add a fenced code block with the language schedule containing JSON like {\"title\": \"Morning news\", \"task\": \"Give me the three biggest news stories of the day, with sources.\", \"every\": \"daily\", \"at\": \"08:00\"} (every is once, daily, weekdays, weekly, monthly or hourly; at is their local time, 24-hour; add \"day\" -- monday to sunday -- for weekly, \"day\" -- 1 to 31 -- for monthly, \"date\" -- YYYY-MM-DD -- for once). Write task as the complete instruction to carry out each time: it runs by itself later, with web search, and the result arrives in its own chat. The app shows the schedule by itself: don't mention the block. Only for things to do later or regularly -- never for a question to answer now.";
  var MAP_PROMPT = "When your answer is about real places someone could find on a map -- where something is, places to visit, eat or stay, an address, a route between towns, a list of locations -- add a map after your text: a fenced code block with the language map containing JSON like {\"title\": \"Short title\", \"places\": [{\"name\": \"Place name\", \"query\": \"Place name, street, city, country\", \"lat\": 0.0, \"lon\": 0.0, \"category\": \"museum\", \"note\": \"a few words\"}]} (1 to 10 places; category is one of food, cafe, bar, shop, museum, sight, park, beach, hotel, transport, health, school, worship, other; give lat and lon only when you know them precisely, and always a query precise enough to find the place). The map appears by itself: don't mention the block. Don't add a map for general knowledge with no particular place, and never for a private person's home.";
  // questions that need the internet search the web on their own, whatever model is picked
  var WEB_RE = /\b(search|look up|google|find out|latest|news|headlines|today'?s|this week|right now|currently|price of|cost of|how much (is|are|does)|exchange rate|who won|score|results? of|release date|weather|recherche|cherche|actualit\u00e9s?|derni\u00e8res? nouvelles|prix d|aujourd'hui|cette semaine)\b/i;
  var IMAGE_RE = /^\s*(please\s+)?(create|make|draw|generate|paint|design)\s+(me\s+)?(an?\s+)?(image|picture|photo|drawing|illustration|logo|poster)\b/i;
  var LINK_RE = /https?:\/\/[^\s<>()\[\]{}"'`]+/gi;

  // ---- links (0.1.164): the server opens every link in a message -- a reel, a post, a video, a PDF, a page -- and
  // the chat says so while it does ("Looking at the reel..."). Same words as services/link_kinds.busy_label.
  var LINK_SITES = [
    [/(^|\.)fb\.watch$/, [], "video"],
    [/(^|\.)(facebook\.com|fb\.com|fb\.me)$/, [[/^\/reels?\/|^\/share\/r\//, "reel"], [/\/videos?\/|^\/watch\b|^\/share\/v\//, "video"],
      [/\/posts\/|\/permalink|story\.php|^\/share\/p\/|\/photos?\/|photo\.php/, "post"], [/^\/events\//, "event"], [/^\/groups\//, "group"]], "page"],
    [/(^|\.)(instagram\.com|instagr\.am)$/, [[/^\/reels?\//, "reel"], [/^\/p\//, "post"], [/^\/tv\//, "video"], [/^\/stories\//, "story"]], "profile"],
    [/(^|\.)(youtube\.com|youtu\.be|youtube-nocookie\.com)$/, [[/^\/shorts\//, "short video"], [/^\/playlist/, "playlist"],
      [/^\/(@|c\/|channel\/|user\/)/, "channel"]], "video"],
    [/(^|\.)tiktok\.com$/, [[/\/video\/\d+/, "video"], [/\/photo\/\d+/, "photo post"], [/^\/@[^\/]+\/?$/, "profile"]], "video"],
    [/(^|\.)(x\.com|twitter\.com)$/, [[/\/status(es)?\/\d+/, "post"]], "profile"],
    [/(^|\.)(threads\.net|threads\.com|bsky\.app)$/, [[/\/post\//, "post"]], "profile"],
    [/(^|\.)(linkedin\.com|lnkd\.in)$/, [[/^\/posts\/|\/feed\/update\/|^\/pulse\//, "post"], [/^\/in\//, "profile"], [/^\/jobs\//, "job"]], "page"],
    [/(^|\.)(reddit\.com|redd\.it)$/, [[/\/comments\//, "post"]], "page"],
    [/(^|\.)(vimeo\.com|dailymotion\.com|dai\.ly)$/, [], "video"],
    [/(^|\.)twitch\.tv$/, [[/clip/, "clip"], [/\/videos\//, "video"]], "channel"],
    [/(^|\.)(open\.spotify\.com|spotify\.link)$/, [[/\/track\//, "song"], [/\/album\//, "album"], [/\/playlist\//, "playlist"],
      [/\/episode\//, "podcast episode"], [/\/show\//, "podcast"], [/\/artist\//, "artist"]], "music"],
    [/(^|\.)soundcloud\.com$/, [], "track"],
    [/(^|\.)(pinterest\.com|pin\.it)$/, [[/\/pin\//, "pin"]], "page"],
    [/(^|\.)medium\.com$/, [], "article"]
  ];
  function linkKind(url) {
    var parts = url.split("/"), host = (parts[2] || "").toLowerCase().replace(/:\d+$/, "").replace(/\.$/, ""),
        path = "/" + parts.slice(3).join("/").split(/[?#]/)[0], i, j;
    for (i = 0; i < LINK_SITES.length; i++) {
      if (!LINK_SITES[i][0].test(host)) continue;
      for (j = 0; j < LINK_SITES[i][1].length; j++) if (LINK_SITES[i][1][j][0].test(path)) return LINK_SITES[i][1][j][1];
      return LINK_SITES[i][2];
    }
    var last = path.split("/").pop(), ext = last.indexOf(".") >= 0 ? last.split(".").pop().toLowerCase() : "";
    return ext === "pdf" ? "PDF" : /^(jpe?g|png|gif|webp|avif|heic)$/.test(ext) ? "picture" :
           /^(mp4|mov|webm|m4v)$/.test(ext) ? "video" : /^(mp3|m4a|wav|ogg|flac|aac)$/.test(ext) ? "audio" : "page";
  }
  function linkLabel(text) {
    var urls = [], found = String(text || "").match(LINK_RE) || [], i, u, host;
    for (i = 0; i < found.length; i++) {
      u = found[i].replace(/[.,;:!?)"']+$/, "");
      host = (u.split("/")[2] || "").toLowerCase();
      if (host !== "github.com" && host !== "www.github.com" && urls.indexOf(u) < 0) urls.push(u);
    }
    if (!urls.length) return "";
    if (urls.length > 1) return "Opening the links\u2026";
    var kind = linkKind(urls[0]);
    if (/^(reel|video|short video|clip|story|picture)$/.test(kind)) return "Looking at the " + kind + "\u2026";
    if (/^(PDF|page|article)$/.test(kind)) return "Reading the " + kind + "\u2026";
    if (kind === "audio") return "Listening to the audio\u2026";
    return "Opening the " + kind + "\u2026";
  }

  // ---- attachments: photos stay in the browser; documents are read by the server
  W.atts = [];
  function chipOf(a) { return { name: a.name, kind: a.kind, thumb: a.thumb || "", note: a.note || "", loading: !!a.loading }; }
  function showAtts() { setAttachments(W.atts.map(chipOf)); }
  function historyText(msg, atts) {             // synced history keeps file NAMES, never contents
    return atts.length ? (msg ? msg + "\n\n" : "") + "\uD83D\uDCCE " + atts.map(function (a) { return a.name; }).join(", ") : msg;
  }
  function mmss(t) { t = Math.max(0, Math.round(t || 0)); return Math.floor(t / 60) + ":" + ("0" + (t % 60)).slice(-2); }
  function buildContent(msg, atts) {             // what the AI receives (same format as the apps: attachments.picture_parts)
    var docs = atts.filter(function (a) { return a.kind === "text"; }), imgs = atts.filter(function (a) { return a.kind === "image"; });
    var vids = atts.filter(function (a) { return a.kind === "video" && a.frames && a.frames.length; });
    var t = msg;
    if (docs.length) {
      t = docs.map(function (a) {
        return '<attached_file name="' + a.name.replace(/"/g, "'") + '"' + (a.note ? " (" + a.note + ")" : "") + ">\n" + a.text + "\n</attached_file>";
      }).join("\n\n") + "\n\n" + (msg || "Please read the attached file(s) and summarise the important points.");
    }
    if (!imgs.length && !vids.length) return t;
    var budget = 5, urls = [], notes = [];        // photos first, then each video's frames in order: 5 pictures at most
    imgs.forEach(function (a) { if (budget && a.data_url) { urls.push(a.data_url); budget--; } });
    vids.forEach(function (a) {
      if (!budget) return;
      var take = a.frames.slice(0, budget); budget -= take.length;
      notes.push("The video \u201c" + a.name + "\u201d" + (a.duration ? " (" + mmss(a.duration) + " long)" : "") + " is attached as " +
                 take.length + " pictures: frames taken from it in order, at " + take.map(function (f) { return mmss(f.at); }).join(", ") +
                 ". Treat them as one moving scene and describe what happens across them.");
      take.forEach(function (f) { urls.push(f.data); });
    });
    var asked = t || (notes.length && !imgs.length ? "What happens in this video?" : "What's in this image?");
    return [{ type: "text", text: notes.length ? notes.concat([asked]).join("\n\n") : asked }].concat(urls.map(function (u) {
      return { type: "image_url", image_url: { url: u } };
    }));
  }

  function send(text, opts) {
    opts = opts || {};
    text = (text || "").trim();
    var atts = opts.voice ? [] : W.atts.slice();
    if ((!text && !atts.length) || W.busy) return Promise.resolve("");
    // "look at my screen": Live screen view starts by itself and asks with what's on the screen
    if (!opts.voice && !atts.length && window.GINK_SCREEN_RE && GINK_SCREEN_RE.test(text) && window.screenViewAvailable &&
        screenViewAvailable() && window.openScreenView) { openScreenView(text); return Promise.resolve(""); }
    if (atts.some(function (a) { return a.loading; })) {
      setStatus("Wait a moment: a file is still loading."); setTimeout(function () { setStatus(""); }, 3000);
      return Promise.resolve("");
    }
    if (!W.current) {
      W.current = W.tempMode ? "tmp-" + uid() : uid();
      W.sessions[W.current] = { id: W.current, messages: [], title: "", pinned: false, deleted: false, updated: now(),
                                temporary: !!W.tempMode };
      save("gink_draft_new", "");
    }
    var s = W.sessions[W.current];
    hideWelcome(); addUserMessage(text, atts.map(chipOf));
    if (W.prefs.use_memory !== false && window.showRecalled) showRecalled(recallMemories(text));   // "Recalled memory"
    s.messages.push({ role: "user", content: historyText(text, atts), ts: stamp() }); touch(s.id); refreshSidebar();
    var content = buildContent(text, atts);
    var photos = atts.filter(function (a) { return a.kind === "image" && a.data_url && !/^live-/.test(a.name || ""); })
                     .map(function (a) { return a.data_url; });                 // never Live frames
    if (photos.length && !s.temporary && !W.care) {
      if (W.prefs.people_on && typeof peopleAuto === "function") photos.forEach(function (d) { peopleAuto(d, "chat"); });
      else if (typeof peoplePending === "function") peoplePending(photos);    // off: Gink offers once; a yes groups these too
    }
    W.atts = []; showAtts();
    var drafts = load("gink_drafts", {}); delete drafts[s.id]; save("gink_drafts", drafts);
    var aid = "a" + uid().slice(0, 12);
    addAssistantMessage(aid, "Thinking\u2026");
    setComposerBusy(true);
    var web = !atts.length && (W.model === "gink-search" || WEB_RE.test(text.replace(LINK_RE, " ")));   // a link's own words aren't a search
    var opening = !atts.length ? linkLabel(text) : "";
    if (opening) setSpinLabel(aid, opening);                 // the server opens the link first (0.1.164)
    else if (web) setSpinLabel(aid, "Searching the web\u2026");
    var job = !atts.length && siteFollowUp(s, text) ? makeSite(text, aid, true, s.site, s)
            : SITE_EDIT_RE.test(text) && !atts.length ? makeSite(text, aid, true, null, s)
            : SITE_RE.test(text) && !atts.length ? makeSite(text, aid, false, null, s)
            : IMAGE_RE.test(text) && (!atts.length || photoOf(atts)) ? makeImage(text, aid, photoOf(atts)) : chat(s, aid, { voice: opts.voice, last: content, web: web });
    return job.then(function (reply) {
      if (reply) { s.messages.push({ role: "assistant", content: reply, ts: stamp() }); touch(s.id); }
      W.busy = null; setComposerBusy(false); refreshSidebar(); sync();
      // A lasting fact they mentioned is remembered BY ITSELF (the server uses the apps' rules: never health, never in
      // a healthcare workspace), with Undo in the notification. Never in a temporary chat, never when memory is off.
      if (reply && text && !atts.length && !s.temporary && W.prefs.use_memory !== false && W.prefs.memory_suggest !== false &&
          text.length <= 400) {
        api("/memory/auto", { text: text, sensitive: keepSensitive() }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
          if (j && j.saved) remembered(j.saved, "mem-auto");
        }).catch(function () {});
      }
      if (reply && !s.temporary && W.token && W.prefs.use_memory !== false && W.prefs.memory_suggest !== false) memgen(s);
      return reply;
    });
  }

  // ---- memory: "Generate memory from chats" and "Include sensitive topics in memory" (Settings > Memory)
  function keepSensitive() { return W.prefs.memory_sensitive === true && !W.teen && !W.care; }   // the server checks too
  function remembered(m, nid) {                    // a memory Gink kept by itself: in this browser too, with Undo
    var all = W.memories || {};
    Object.keys(all).forEach(function (id) { if (m.replaced && all[id].text === m.replaced) delete all[id]; });
    all[m.id] = { text: m.text, created: Date.now() / 1000 }; W.memories = all; save("gink_memories", all);
    if (typeof ginkNotify === "function") ginkNotify({ id: nid || "mem-auto", title: m.replaced ? "Updated" : "Remembered", body: m.text,
      icon: "\uD83E\uDDE0", timeout: 6000, actions: [{ label: "Undo", emit: "memory_undo", value: { id: m.id, replaced: m.replaced || "" } }] });
  }
  W.memgen = {};                                   // chat -> how many of the person's messages were looked at
  function memgen(s) {                             // every 4 messages they send: the AI's picks (server rules apply)
    var said = s.messages.filter(function (m) { return m.role === "user"; }).length;
    if (W.care || said - (W.memgen[s.id] || 0) < 4) return;
    W.memgen[s.id] = said;
    var msgs = s.messages.slice(-16).map(function (m) {
      return { role: m.role, content: typeof m.content === "string" ? m.content.slice(0, 1500) : "" }; });
    api("/memory/generate", { messages: msgs, sensitive: keepSensitive() }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { ((j && j.saved) || []).forEach(function (m, i) { remembered(m, "mem-gen-" + i); }); }).catch(function () {});
  }
  function importMemories(text) {                  // "Import memory from other AI providers": the other assistant's answer
    return api("/memory/import", { text: String(text || "").slice(0, 200000), sensitive: keepSensitive() }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || "That didn\u2019t work. Please try again.");
        var all = W.memories || {};
        (j.saved || []).forEach(function (m) {
          Object.keys(all).forEach(function (id) { if (m.replaced && all[id].text === m.replaced) delete all[id]; });
          all[m.id] = { text: m.text, created: Date.now() / 1000 };
        });
        W.memories = all; save("gink_memories", all);
        var n = (j.saved || []).length, bits = [n ? "Added " + n + (n === 1 ? " memory." : " memories.") : "Nothing new to add."];
        if (j.skipped_sensitive) bits.push("Skipped " + j.skipped_sensitive + " about sensitive topics (turn on \u201cInclude sensitive topics in memory\u201d to keep them).");
        if (j.skipped) bits.push("Skipped " + j.skipped + " Gink never keeps (like passwords or numbers).");
        if (j.full) bits.push("Gink\u2019s memory is full: forget something first.");
        settingsToast(bits.join(" "));
      });
    }).catch(function (err) { settingsToast(err.message); });
  }

  function chat(s, aid, opts) {
    opts = opts || {};
    var ctrl = new AbortController(); W.busy = ctrl;
    var history = s.messages.slice(-24).map(function (m) { return { role: m.role, content: m.content }; });
    if (opts.last !== undefined && history.length) history[history.length - 1].content = opts.last;   // files + photos
    var body = { model: W.model || undefined, stream: true, messages: [{ role: "system", content: systemPrompt(opts.voice) }].concat(history) };
    if (/^openai\/gpt-oss/.test(W.model || "openai/gpt-oss")) {                 // the model menu's Effort
      var eff = W.prefs.effort || "medium";
      body.reasoning_effort = { low: "low", medium: "medium", high: "high", extra: "high", max: "high" }[eff] || "medium";
      if (eff === "max") body.max_tokens = 32000;
    }
    if (opts.web) body.gink_web = true;                       // the server runs it as a web search
    var text = "";
    return api("/ai/openai/v1/chat/completions", body, { signal: ctrl.signal }).then(function (r) {
      if (!r.ok) return errorText(r).then(function (t) { setPlainText(aid, t); return ""; });
      var reader = r.body.getReader(), dec = new TextDecoder(), buf = "";
      function pump() {
        return reader.read().then(function (part) {
          if (part.done) return;
          buf += dec.decode(part.value, { stream: true });
          var lines = buf.split("\n"); buf = lines.pop();
          lines.forEach(function (line) {
            line = line.trim();
            if (line.indexOf("data:") !== 0) return;
            var data = line.slice(5).trim();
            if (!data || data === "[DONE]") return;
            try {
              var d = JSON.parse(data);
              if (d.error) {                // the server says these in plain words now; an older one: never the raw slip
                var em = String(d.error.message || "") + " " + String(d.error.code || "");
                text += text ? "\n\n*The answer stopped early because the AI service had a problem. Ask again to get the rest.*"
                  : /tool_use_failed|tool choice is none|called a tool/i.test(em)
                    ? "The AI service tripped over that one. Please ask again — it usually works the second time."
                    : (d.error.message || "The AI service had a problem.");
                setPlainText(aid, text); return;
              }
              if (d.gink_status === "searching") setSpinLabel(aid, "Searching the web\u2026");   // automatic searches too
              var piece = d.choices && d.choices[0] && d.choices[0].delta && d.choices[0].delta.content;
              if (piece) { text += piece; (window.setQuickText || setPlainText)(aid, narrow(text)); }   // formatted as it arrives
            } catch (e) {}
          });
          return pump();
        });
      }
      return pump().then(function () { return finish(aid, text); });
    }).catch(function (e) {
      if (e && e.name === "AbortError") { text = (text ? text + "\n\n" : "") + "*Stopped.*"; return finish(aid, text); }
      if (e && e.message === "signed out") return "";
      setPlainText(aid, "Can't reach the Gink server. Check your connection and try again.");
      return "";
    });
  }
  function finish(aid, text) {
    if (!text) { setPlainText(aid, "No answer came back. Please try again."); return ""; }
    return api("/render", { markdown: text }).then(function (r) { return r.json(); }).then(function (j) {
      remember(text, j.html);
      finalizeMessage(aid, j.html);
      if (W.prefs.read_aloud || W.voiceReply) readAloud(text);       // a voice message gets a spoken answer, by itself
      W.voiceReply = false;
      return text;
    }).catch(function () { setPlainText(aid, text); return text; });
  }
  // ---- websites: "make me a website for..." / "change my website: ..."
  var SITE_RE = /\b(make|build|create|design|generate|cr\u00e9e|fais)\b[^.?!]{0,50}\b(website|web site|site web|site internet|landing page|web ?page)\b/i;
  var SITE_EDIT_RE = /\b(change|edit|update|modify|modifie|change)\b[^.?!]{0,20}\b(my|the|mon|le) (website|site)\b/i;
  function siteLink(j, intro) {
    var url = String(j.url || ""), safe = /^https?:\/\//.test(url) ? url : "#";
    var a = document.createElement("a"); a.href = safe; a.target = "_blank"; a.rel = "noopener"; a.textContent = j.title || "your website";
    return "<p>" + intro + " " + a.outerHTML + "</p><p class=\"muted\">" + escHtml(url) +
           "</p><p>Ask me to change anything on it \u2014 for example \u201cmake the header green\u201d.</p>";
  }
  function escHtml(t) { var d = document.createElement("div"); d.textContent = t; return d.innerHTML; }
  // A follow-up right after Gink built or changed a website in this chat ("good, add more to it",
  // "make it blue") changes THAT website -- it used to go to the plain chat, which said it couldn't.
  var SITE_HINT_RE = /\b(add|change|make|remove|delete|put|include|update|edit|replace|use|set|move|insert|more|less|bigger|smaller|darker|lighter|colou?rs?|section|pages?|buttons?|images?|photos?|pictures?|logo|fonts?|text|title|header|footer|menu|gallery|contact|prices?|it)\b/i;
  var NOT_EDIT_RE = /^\s*(what|why|how|who|when|where|which|is|are|do|does|can you explain|explain|thanks?|thank you|merci|ok(ay)?|great|nice|cool|perfect)\b|\?\s*$/i;
  function siteFollowUp(s, text) {
    var last = null;
    (s.messages || []).forEach(function (m) { if (m.role === "assistant") last = m; });
    var afterSite = last && /^(Your website is live:|Updated your website:)/.test(String(last.content || ""));
    return !!afterSite && SITE_HINT_RE.test(text) && !NOT_EDIT_RE.test(text);
  }
  function makeSite(text, aid, editing, siteId, session) {
    W.busy = { abort: function () {} };
    setSpinLabel(aid, editing ? "Updating your website\u2026" : "Building your website\u2026 (about a minute)");
    var go = editing
      ? (siteId ? Promise.resolve(siteId) : api("/sites").then(function (r) { return r.json(); }).then(function (j) {
          if (!j.sites || !j.sites.length) throw new Error("You don\u2019t have a website yet \u2014 ask me to make one.");
          return j.sites[0].id;
        })).then(function (id) { return api("/sites/" + encodeURIComponent(id) + "/edit", { instruction: text }); })
      : api("/sites", { prompt: text });
    return go.then(function (r) {
      if (!r.ok) return errorText(r).then(function (t) { setPlainText(aid, t); return ""; });
      return r.json().then(function (j) {
        if (session && j.id) { session.site = j.id; touch(session.id); }         // the website of this chat
        finalizeMessage(aid, siteLink(j, editing ? "Updated:" : "Your website is live:"));
        return (editing ? "Updated your website: " : "Your website is live: ") + j.title + " " + j.url;
      });
    }).catch(function (e) { setPlainText(aid, (e && e.message && e.message !== "signed out") ? e.message : "Can't reach the Gink server."); return ""; });
  }

  // An image request with one photo attached starts from that photo (like Media Studio's "Use a photo")
  function photoOf(atts) {
    if (!atts || atts.length !== 1) return "";
    var a = atts[0], url = String(a.data_url || a.dataUrl || a.url || "");
    var m = /^data:image\/(jpeg|png|webp);base64,(.+)$/.exec(url);
    return m ? m[2] : "";
  }
  function makeImage(prompt, aid, photo) {
    W.busy = { abort: function () {} };
    setSpinLabel(aid, photo ? "Creating your image from the photo\u2026" : "Creating your image\u2026");
    var body = { prompt: prompt, aspect_ratio: photo ? "3:4" : "1:1" };
    if (photo) body.photo_b64 = photo;
    return api("/media/image", body).then(function (r) {
      if (!r.ok) return errorText(r).then(function (t) { setPlainText(aid, t); return ""; });
      return r.json().then(function (j) {
        var src = "data:" + (j.mime_type || "image/png") + ";base64," + j.image_b64;
        finalizeMessage(aid, '<p>Here\u2019s your image.</p><p><img alt="" style="max-width:100%;border-radius:14px" src="' + src + '"></p>');
        return "Here\u2019s your image (made on the web).";
      });
    }).catch(function () { setPlainText(aid, "Can't reach the Gink server."); return ""; });
  }

  // ---------------------------------------------------------------- voice in the browser
  var audio = null;
  function plainForSpeech(text) {
    return String(text).replace(/```[\s\S]*?```/g, " ").replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
                       .replace(/[*_#>`|~]/g, "").replace(/\s+/g, " ").trim().slice(0, 1400);
  }
  function speakThen(text, done, persona) {
    done = done || function () {};
    if (audio) { audio.pause(); audio = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    var plain = plainForSpeech(text), finished = false;
    function end() { if (!finished) { finished = true; setSpeaking(false); done(); } }
    api("/voice/speak", { text: plain, persona: persona || W.prefs.voice || "Female (Jenny)" }).then(function (r) {
      if (!r.ok) throw new Error("voice");
      return r.json();
    }).then(function (j) {
      audio = new Audio("data:" + (j.mime_type || "audio/wav") + ";base64," + j.audio_b64);
      setSpeaking(true); audio.onended = end; audio.onerror = end; return audio.play();
    }).catch(function () {
      if ("speechSynthesis" in window) {                        // the browser's own voice instead
        var u = new SpeechSynthesisUtterance(plain); u.onend = end; u.onerror = end;
        setSpeaking(true); speechSynthesis.speak(u);
      } else end();
    });
  }
  function readAloud(text) { speakThen(text); }
  function stopSpeaking() {
    if (audio) { audio.pause(); audio = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    setSpeaking(false);
  }
  var Rec = window.SpeechRecognition || window.webkitSpeechRecognition, rec = null;
  function dictate() {
    if (!Rec) { setStatus("Dictation needs Chrome, Edge or Safari."); setTimeout(function () { setStatus(""); }, 3000); return; }
    if (rec) { rec.stop(); return; }
    rec = new Rec(); rec.lang = navigator.language || "en-US"; rec.interimResults = false;
    setDictating(true);
    rec.onresult = function (e) {
      var said = e.results[0][0].transcript, box = document.getElementById("cin");
      setComposerText(((box && box.value) ? box.value + " " : "") + said);
    };
    rec.onend = function () { rec = null; setDictating(false); };
    rec.onerror = function () { rec = null; setDictating(false); };
    rec.start();
  }
  // ---- "Hey Gink" in the browser: the browser's speech recognition listens while this tab is visible
  // (Chrome sends what it hears to Google, Safari to Apple: Settings says so). On "Hey Gink", voice mode opens.
  var WK = { rec: null, status: "", blocked: false };
  var WAKE_RE = /\b(hey|hi|ok|okay)[ ,]+(gink|ginks|king|kink|jink|jinks|jinx|jing|ginkgo|ging)\b/i;
  var WAKE_SHORT_RE = /^\s*(gink|ginks|jink|jinks|jinx|ginkgo)\b/i;          // just "Gink" (Settings > Voice)
  function wakeHeard(t) { return WAKE_RE.test(t) || (W.prefs.wake_short !== false && WAKE_SHORT_RE.test(t)); }
  function wakeStatus(text) { if (WK.status !== text) { WK.status = text; pushSettings(); } }
  function wakeWanted() { return !!(W.prefs.wake_enabled && Rec && W.token && !V.on && !WK.blocked && !W.voiceOff && document.visibilityState === "visible"); }
  function wakeStart() {
    if (WK.rec) return;
    if (!wakeWanted()) {
      if (!W.prefs.wake_enabled) wakeStatus("Off");
      else if (!Rec) wakeStatus("Not available in this browser (try Chrome, Edge or Safari)");
      else if (!WK.blocked && !V.on) wakeStatus("Paused while this tab is in the background");
      return;
    }
    var r = new Rec(); r.lang = navigator.language || "en-US"; r.continuous = true; r.interimResults = true;
    r.onresult = function (e) {
      for (var i = e.resultIndex; i < e.results.length; i++) {
        if (wakeHeard(e.results[i][0].transcript)) {
          wakeStop();
          if (typeof wakeGlow === "function") wakeGlow("listening");      // the same glow as the apps
          if (typeof startVoice === "function") startVoice();
          return;
        }
      }
    };
    r.onerror = function (e) {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        WK.blocked = true; wakeStatus("Microphone blocked: allow the microphone for this site in your browser, then switch this on again");
      }
    };
    r.onend = function () { WK.rec = null; setTimeout(wakeStart, 400); };     // browsers stop after a while: carry on
    try { r.start(); WK.rec = r; wakeStatus("Listening for \u201cHey Gink\u201d in this browser tab"); }
    catch (err) { wakeStatus("Couldn\u2019t start listening (" + (err && err.message || err) + ")"); }
  }
  function wakeStop() { var r = WK.rec; WK.rec = null; if (r) { r.onend = null; try { r.abort(); } catch (e) {} } }
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "visible") wakeStart(); else wakeStop(); });

  // ---- voice conversations in the browser: listen -> think -> speak -> listen again
  var V = { on: false, muted: false, rec: null, heard: "" };
  function voiceList() { return window.GINK_VOICES || []; }
  function vListen() {
    if (!V.on || V.muted || W.busy) return;
    if (!Rec) { voiceUiState("error", "Voice conversations need Chrome, Edge or Safari."); return; }
    V.heard = "";
    var r = new Rec(); V.rec = r; r.lang = navigator.language || "en-US"; r.interimResults = true; r.continuous = false;
    r.onresult = function (e) {
      var t = "";
      for (var i = 0; i < e.results.length; i++) t += e.results[i][0].transcript;
      voiceUiCaption(t, "");
      if (e.results[e.results.length - 1].isFinal) V.heard = t.trim();
    };
    r.onerror = function (e) {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        V.on = false; voiceUiState("error", "Allow microphone access for this page, then try again.");
      }
    };
    r.onend = function () {
      V.rec = null;
      if (!V.on || V.muted) return;
      if (V.heard) vRespond(V.heard); else setTimeout(vListen, 250);            // silence: keep listening
    };
    try { r.start(); voiceUiState("listening"); } catch (e) { setTimeout(vListen, 500); }
  }
  function vRespond(text) {
    voiceUiState("thinking");
    send(text, { voice: true }).then(function (reply) {
      if (!V.on) return;
      if (!reply) { voiceUiState("error", "Something went wrong. Say that again?"); setTimeout(vListen, 1500); return; }
      voiceUiCaption(null, plainForSpeech(reply)); voiceUiState("speaking");
      speakThen(reply, function () { if (V.on && !V.muted) vListen(); else if (V.on) voiceUiState("muted"); });
    });
  }
  function vStop() {
    V.on = false;
    if (V.rec) { try { V.rec.abort(); } catch (e) {} V.rec = null; }
    stopSpeaking();
  }

  // ---------------------------------------------------------------- sync with the desktop app
  // ---- memories (synced from the apps: "remember that ...")
  W.memories = load("gink_memories", null);
  // ---- the profile (name, what Gink calls you, work, photo): the same one as in the apps, synced both ways
  W.profile = load("gink_profile", null) || { updated: 0, payload: {}, dirty: false };
  var PROFILE_KEYS = ["full_name", "nickname", "work"];
  function applyProfile() {
    var p = W.profile.payload || {};
    PROFILE_KEYS.forEach(function (k) { if (typeof p[k] === "string") W.prefs[k] = p[k]; });
    var shown = p.full_name || p.nickname || W.name || W.email || "Gink user";
    setUser(shown, p.photo || "", (p.nickname || shown).split(/[\s@]/)[0]);
  }
  function takeProfile(docs) {
    (docs || []).forEach(function (d) {
      if (d.id !== "me" || d.deleted || !(d.updated > W.profile.updated)) return;      // newest copy wins
      W.profile = { updated: d.updated, payload: d.payload || {}, dirty: false };
      save("gink_profile", W.profile); applyProfile(); pushSettings();
    });
  }
  function profileEdit(key, value) {
    W.profile.payload = Object.assign({}, W.profile.payload, (function (o) { o[key] = String(value || "").replace(/\s+/g, " ").trim().slice(0, 120); return o; })({}));
    W.profile.updated = Date.now() / 1000; W.profile.dirty = true;
    save("gink_profile", W.profile); applyProfile();
    if (typeof sync === "function") sync();                       // send it to the other devices now
  }
  function profileNote() {
    var p = W.profile.payload || {}, bits = [];
    if (p.nickname || p.full_name) bits.push("Call the person " + (p.nickname || p.full_name) + ".");
    if (p.work) bits.push("Their work: " + p.work + " (pick examples that fit).");
    return bits.length ? "\n\n" + bits.join(" ") : "";
  }
  function takeMemories(docs) {
    var m = W.memories || {};
    (docs || []).forEach(function (d) { if (d.deleted) delete m[d.id]; else m[d.id] = { text: (d.payload || {}).text || "", created: (d.payload || {}).created || 0 }; });
    W.memories = m; save("gink_memories", m);
  }
  if (W.memories === null && W.token) {                     // first time: every memory, once (later: only changes)
    api("/sync", { since: 0, push: {} }).then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j) { takeMemories((j.changes || {}).memories); takeProfile((j.changes || {}).profile); } }).catch(function () {});
  }
  var MEM_STOP = ("a an and are as at be but by can could did do does for from had has have how i if in into is it its me my no not of on or " +
    "our so than that the their them then there these they this to was we were what when where which who why will with would you your yes " +
    "please tell about just like some any also very really want need know").split(" ");
  function memWords(t) { return (String(t || "").toLowerCase().match(/[\p{L}\p{N}_']+/gu) || []).filter(function (w) { return w.length >= 3 && MEM_STOP.indexOf(w) < 0; }); }
  function recallMemories(text) {                           // shared meaningful words, best first, at most 3
    var q = memWords(text), out = [];
    if (!q.length || !W.memories) return [];
    Object.keys(W.memories).forEach(function (id) {
      var m = W.memories[id], mine = memWords(m.text), score = 0, seen = {};
      mine.forEach(function (w) { if (!seen[w] && q.indexOf(w) >= 0) { seen[w] = 1; score += 1 + w.length / 10; } });
      if (score) out.push({ score: score, created: m.created, text: m.text });
    });
    out.sort(function (a, b) { return (b.score - a.score) || (b.created - a.created); });
    return out.slice(0, 3);
  }
  function memoryNote() {
    if (W.prefs.use_memory === false || !W.memories) return "";
    var all = Object.keys(W.memories).map(function (k) { return W.memories[k]; }).sort(function (a, b) { return a.created - b.created; }).slice(-40);
    return all.length ? "\n\nThings the user asked you to remember about them (use them when relevant, don't recite them unprompted):\n" +
                        all.map(function (m) { return "- " + m.text; }).join("\n") : "";
  }
  function sync() {
    if (!W.token || W.syncing) return;
    W.syncing = true;
    var push = Object.keys(W.dirty).map(function (id) {
      var s = W.sessions[id]; if (!s) return null;
      return { id: s.id, updated: s.updated, deleted: !!s.deleted,
               payload: { messages: s.deleted ? [] : s.messages, title: s.title || "", pinned: !!s.pinned, archived: !!s.archived } };
    }).filter(Boolean);
    var pushProfile = W.profile.dirty ? [{ id: "me", updated: W.profile.updated, deleted: false, payload: W.profile.payload }] : [];
    api("/sync", { since: W.since, push: { chats: push, profile: pushProfile } }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j) return;
      push.forEach(function (d) { delete W.dirty[d.id]; });
      if (pushProfile.length && W.profile.updated === pushProfile[0].updated) { W.profile.dirty = false; save("gink_profile", W.profile); }
      takeProfile((j.changes || {}).profile);
      var changedCurrent = false;
      takeMemories((j.changes || {}).memories);
      var news = [];
      ((j.changes || {}).chats || []).forEach(function (d) {
        var mine = W.sessions[d.id];
        if (mine && mine.updated >= d.updated) return;                          // newest copy wins
        var p = d.payload || {};
        var pm = p.messages || [];                                              // a scheduled task's new result (0.1.161)
        if (/^task-/.test(d.id) && !d.deleted && W.since && pm.length > Math.max((mine && mine.messages || []).length, 1) &&
            (pm[pm.length - 1] || {}).role === "assistant") news.push({ id: d.id, title: p.title || "Scheduled task", text: pm[pm.length - 1].content || "" });
        W.sessions[d.id] = { id: d.id, updated: d.updated, deleted: !!d.deleted, messages: p.messages || [],
                             title: p.title || "", pinned: !!p.pinned, archived: !!p.archived };
        if (d.id === W.current) changedCurrent = true;
      });
      W.since = j.now || W.since; LS.setItem("gink_since", String(W.since)); persist();
      refreshSidebar();
      if (changedCurrent && !W.busy) openSession(W.current);
      news.forEach(taskNews);
      if (W.openAfterSync) {                                                   // "Open its chat": here now
        var want = W.openAfterSync; W.openAfterSync = "";
        if (W.sessions[want] && !W.sessions[want].deleted) openSession(want);
        else ginkNotify({ id: "task-action", icon: "\u23f0", title: "Scheduled task", body: "Its chat isn\u2019t here yet \u2014 try again in a moment.", timeout: 4000, system: false });
      }
      if (news.length) loadTasks();
    }).catch(function () {}).then(function () { W.syncing = false; });
  }

  // A scheduled task's new result: a notification in the page -- and the browser's own when Gink isn't in front
  // (ginkSystemNotify, below)
  function taskNews(n) {
    if (n.id === W.current && !document.hidden) return;                     // on screen already
    var body = String(n.text || "").replace(/^\*\*\u23f0[^\n]*\n+/, "").replace(/[*#>`_]+/g, " ").replace(/\s+/g, " ").trim();
    body = body.length > 140 ? body.slice(0, 140) + "\u2026" : body;
    ginkNotify({ id: "task-" + n.id, icon: "\u23f0", title: n.title, body: body || "A new result is ready.", timeout: 12000, open: n.id,
                 actions: [{ label: "Open", emit: "select_session", value: n.id, primary: true }] });
  }
  // Every notification card also shows on the device when this tab isn't in front (0.1.162): the browser's own
  // notification (Notification Center on a Mac), if it's allowed and Settings > Notifications says so. The page's
  // ginkNotify calls this; system: false cards (quick confirmations) don't.
  window.ginkSystemNotify = function (o) {
    try {
      if (!document.hidden || W.prefs.notify_system === false || !window.Notification || Notification.permission !== "granted") return;
      var note = new Notification(o.title || "Gink", { body: o.body || "", tag: "gink-" + (o.id || o.title || "") });
      note.onclick = function () { window.focus(); if (o.open) openSession(o.open); note.close(); };
    } catch (e) {}
  };

  // ---------------------------------------------------------------- settings (web subset)
  function pushSettings(lists, extra) {
    var shown = false;                             // "Browser notifications": on when wanted AND the browser allows them
    try { shown = W.prefs.notify_system !== false && !!window.Notification && Notification.permission === "granted"; } catch (e) {}
    setSettingsState({ values: Object.assign({}, W.prefs, { model: W.model, notify_system: shown }),
                       info: Object.assign({ name: W.name, email: W.email, version: "web", plan: W.plan || "free", voices: [], models: W.models, web: true,
                                             care: !!W.care, teen: !!W.teen,
                                             wake_supported: !!(window.SpeechRecognition || window.webkitSpeechRecognition), wake_web: true,
                                             wake_status: (typeof WK !== "undefined" && WK && WK.status) || "Off" }, W.info || {}, extra || {}),
                       lists: Object.assign({ prompts: myPrompts() }, lists || {}) });
  }
  W.info = {};                                     // from /info: Gink's own policy pages, "Learn more" links
  function loadMemory() {                          // Settings > Memory: teens never keep sensitive topics
    pushSettings({}, W.info);
    api("/family").then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j) { W.teen = !!j.teen; pushSettings({}, W.info); } }).catch(function () {});
  }
  // the prompt library ("/" menu), kept in this browser
  function myPrompts() { return load("gink_prompts", []); }
  function savePrompts(list, fromServer) {
    save("gink_prompts", list); setPrompts(list);
    if (!fromServer && W.token) putPrompts(list).catch(function () {});
  }
  function putPrompts(list) {
    return fetch("/account/prompts", { method: "PUT", body: JSON.stringify({ prompts: list }),
                                       headers: { "Content-Type": "application/json", Authorization: "Bearer " + W.token } });
  }
  function syncPrompts() {                               // signed in: the account holds the list
    if (!W.token) return;
    fetch("/account/prompts", { headers: { Authorization: "Bearer " + W.token } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); }).then(function (j) {
        if (j.updated) savePrompts(j.prompts || [], true);
        else if (myPrompts().length) putPrompts(myPrompts()).catch(function () {});
      }).catch(function () {});
  }
  // signed-in devices (Settings > Account)
  function activeText(d) {
    if (d.current) return "This device";
    var ago = Date.now() / 1000 - (d.last_seen || 0);
    if (ago < 600) return "Active now";
    if (ago < 86400) return "Active today";
    var days = Math.floor(ago / 86400);
    return days === 1 ? "Last active yesterday" : "Last active " + days + " days ago";
  }
  W.twofa = {};                                    // setup in progress / codes shown once
  function loadDevices() {
    pushSettings({}, { twofa: W.twofa });
    var json = function (r) { return r.ok ? r.json() : Promise.reject(); };
    Promise.all([api("/account/sessions").then(json).catch(function () { return null; }),
                 api("/account/2fa").then(json).catch(function () { return {}; }),
                 api("/sites").then(json).catch(function () { return { sites: [] }; }),
                 api("/account/security-history").then(json).catch(function () { return { events: [] }; }),
                 api("/account/passkeys").then(json).catch(function () { return { passkeys: [] }; }),
                 api("/account/phone").then(json).catch(function () { return {}; })]).then(function (res) {
      var lists = { sessions: res[0] ? (res[0].sessions || []).map(function (d) { return Object.assign({}, d, { when: activeText(d) }); }) : [],
                    sites: (res[2].sites || []), security: (res[3].events || []), passkeys: (res[4].passkeys || []) };
      var extra = { twofa: Object.assign({}, res[1] || {}, W.twofa), phone: Object.assign({}, res[5] || {}, { pending: W.phonePending || "" }) };
      if (!res[0]) extra.sessions_error = "Your devices aren\u2019t available right now.";
      pushSettings(lists, extra);
    });
  }
  // Connected apps (Google Calendar, Gmail, Drive)
  function loadConnected() {
    pushSettings({}, {});
    api("/connected").then(function (r) { return r.ok ? r.json() : Promise.reject(); }).then(function (j) {
      pushSettings({ connected: j.services || [] }, { connected_configured: j.configured });
    }).catch(function () { pushSettings({ connected: [] }, { connected_error: "Connected apps aren\u2019t available right now." }); });
  }
  // Gink's status: the page's thin bar while something on Gink's side isn't working (checked every 5 minutes)
  function checkStatus() {
    fetch("/status").then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (j && typeof statusBar === "function") statusBar(j.status, j.message);
    }).catch(function () {});
  }
  // The policies changed since this browser said OK: the page's notice, once per change
  function checkPolicies() {
    fetch("/info").then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j) return;
      W.info = { policies: j.policies || [], memory_help_url: j.memory_help_url || "", location_help_url: j.location_help_url || "" };
      if (!j.policies_updated) return;
      var seen = ""; try { seen = LS.getItem("gink_policy_seen") || ""; } catch (e) {}
      if (j.policies_updated > seen && typeof policyNotice === "function") policyNotice(j.policies_updated, j.privacy_url, j.terms_url);
    }).catch(function () {});
  }
  // Settings > Scheduled tasks (0.1.161, server: /tasks: results in each task's own chat) and the scheduled agents
  // (/dev/schedules: files in a Genie project)
  function loadSchedules() {
    if (!W.token) return pushSettings({}, { tasks_error: "Sign in to Gink to schedule tasks." });
    var json = function (r) { return r.ok ? r.json() : Promise.reject(); };
    Promise.all([api("/tasks").then(json).catch(function () { return null; }),
                 api("/dev/schedules").then(json).catch(function () { return { data: [] }; })]).then(function (res) {
      if (!res[0]) return pushSettings({}, { tasks_error: "Scheduled tasks aren\u2019t available right now." });
      if (typeof setTasks === "function") setTasks(res[0].data || []);
      pushSettings({}, { tasks: res[0].data || [], tasks_limits: res[0].limits || {}, schedules: res[1].data || [] });
    });
  }
  function loadTasks() {                         // the chat's task cards: the tasks as they are now
    if (!W.token) { if (typeof setTasks === "function") setTasks([]); return Promise.resolve([]); }
    return api("/tasks").then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (j) { if (typeof setTasks === "function") setTasks(j.data || []); return j.data || []; })
      .catch(function () { return null; });
  }
  function taskCall(method, path, body) {
    return fetch(path, { method: method, headers: placeHeaders({ Authorization: "Bearer " + W.token, "Content-Type": "application/json" }),
                         body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "That didn\u2019t work. Please try again.");
        return j; }); });
  }
  function taskSoon() {                          // "Run now": its result in a minute or so -- look a few times
    [25000, 50000, 90000, 150000].forEach(function (ms) { setTimeout(sync, ms); });
  }
  function offerTaskNotifications() {            // once: the browser's own notification when a result arrives
    try {
      if (!window.Notification || Notification.permission !== "default" || LS.getItem("gink_task_notify_asked")) return;
      LS.setItem("gink_task_notify_asked", "1");
    } catch (e) { return; }
    ginkNotify({ id: "task-notify", icon: "\u23f0", title: "Get notified when results arrive?", timeout: 0,
                 body: "Your browser can tell you when a scheduled task has a new result, even when Gink is in another tab.",
                 actions: [{ label: "Turn on", primary: true, run: function () { try { Notification.requestPermission(); } catch (e) {} } },
                           { label: "Not now" }] });
  }
  function openTaskChat(chatId) {                // its chat is made by the server: sync, then open it
    if (W.sessions[chatId] && !W.sessions[chatId].deleted) return openSession(chatId);
    W.openAfterSync = chatId; sync();
  }
  function schCall(method, path, body, done) {
    return fetch(path, { method: method, headers: placeHeaders({ Authorization: "Bearer " + W.token, "Content-Type": "application/json" }),
                         body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || "That didn\u2019t work. Please try again.");
        if (done) settingsToast(done); loadSchedules(); }); })
      .catch(function (err) { settingsToast(err.message); });
  }
  // A workspace in healthcare mode: the Live camera shows the patient-privacy reminder (the server's rules apply anyway)
  function careFrom(j) {
    var on = !!(j && j.org && j.org.healthcare && j.status === "active");
    W.care = on;
    if (typeof setCareMode === "function") setCareMode(on);
    if (typeof peopleSetOn === "function") peopleSetOn(!!W.prefs.people_on && !on);   // never in a healthcare workspace
  }
  function checkCare() {
    api("/org").then(function (r) { return r.ok ? r.json() : null; }).then(careFrom).catch(function () {});
  }
  // Settings > Workspace (server: /org)
  function loadOrg() {
    api("/org").then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (j) { careFrom(j); pushSettings({}, { org: j }); })
      .catch(function () { pushSettings({}, { org_error: "Workspaces aren\u2019t available right now." }); });
  }
  function orgCall(method, path, body, done) {
    return fetch(path, { method: method, headers: { Authorization: "Bearer " + W.token, "Content-Type": "application/json" },
                         body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || "That didn\u2019t work. Please try again.");
        if (done) settingsToast(done); loadOrg(); }); })
      .catch(function (err) { settingsToast(err.message); });
  }
  // Settings > Parental controls (server: /family)
  function loadFamily() {
    pushSettings({}, {});
    api("/family").then(function (r) { return r.ok ? r.json() : Promise.reject(); }).then(function (j) {
      pushSettings({}, { family: j });
    }).catch(function () { pushSettings({}, { family_error: "Parental controls aren\u2019t available right now." }); });
  }
  function familyCall(path, body, done, method) {
    var req = method ? fetch(path, { method: method, headers: { Authorization: "Bearer " + W.token, "Content-Type": "application/json" },
                                     body: JSON.stringify(body) }) : api(path, body);
    return req.then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) {
      if (!r.ok) throw new Error(j.detail || "That didn\u2019t work. Please try again.");
      if (done) settingsToast(done); loadFamily(); }); })
      .catch(function (err) { settingsToast(err.message); });
  }
  function archivedList() {
    return Object.keys(W.sessions).map(function (k) { return W.sessions[k]; })
      .filter(function (s) { return s.archived && !s.deleted; }).map(function (s) { return { id: s.id, title: titleOf(s) }; });
  }
  function loadLockdown() {                              // Settings > Privacy (archived chats, shared links, Lockdown)
    pushSettings({ archived: archivedList() });
    api("/shared").then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (j) { pushSettings({ archived: archivedList(), shared: j.shared || [] }); }).catch(function () {});
    api("/account/lockdown").then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (j) { pushSettings({ archived: archivedList() }, { lockdown_on: !!j.on }); }).catch(function () {});
    api("/account/training").then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (j) { pushSettings({ archived: archivedList() }, { training: j }); }).catch(function () {});
  }
  function setTraining(genie, del, done) {                 // Settings > Privacy > Help improve Gink
    fetch("/account/training", { method: "PUT", headers: { Authorization: "Bearer " + W.token, "Content-Type": "application/json" },
                                 body: JSON.stringify({ genie: genie, "delete": del }) })
      .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) throw new Error(j.detail || "That didn\u2019t work. Please try again.");
        settingsToast(done); loadLockdown(); }); })
      .catch(function (err) { settingsToast(err.message); });
  }
  function connectApp(service) {
    var win = window.open("about:blank", "_blank");           // opened during the click, so it isn't blocked
    api("/connected/" + encodeURIComponent(service) + "/begin", {}).then(function (r) {
      return r.ok ? r.json() : errorText(r).then(function (t) { throw new Error(t); });
    }).then(function (j) {
      if (win) win.location.href = j.url; else window.location.href = j.url;
      settingsToast("Finish in the new window \u2014 Gink will notice when you\u2019re done.");
      var tries = 0, timer = setInterval(function () {
        if (++tries > 40) return clearInterval(timer);
        api("/connected").then(function (r) { return r.json(); }).then(function (j2) {
          if ((j2.services || []).some(function (s) { return s.id === service && s.connected; })) {
            clearInterval(timer); settingsToast("Connected."); loadConnected();
          }
        });
      }, 3000);
    }).catch(function (e) { if (win) win.close(); settingsToast(e.message); });
  }
  function twofaPost(path, body, then) {
    api(path, body || {}).then(function (r) {
      return r.ok ? r.json().then(then) : errorText(r).then(function (t) { settingsToast(t); });
    });
  }
  function applyAppearance() { setAppearance(W.prefs.theme, W.prefs.chat_font, W.prefs.motion); }
  // ---- settings on every device (the same list as the apps' prefs.SYNCED; a test keeps them equal)
  var SYNCED_PREFS = ["theme", "chat_font", "motion", "style_base", "style_warmth", "style_enthusiasm", "style_emoji", "style_headers",
    "reply_language", "voice_speed", "read_aloud", "speech_lang", "web_search", "use_memory", "memory_suggest", "video_suggestions",
    "notify_reminders", "agent_confirm", "send_key", "briefing_enabled", "briefing_time", "briefing_city",
    "briefing_speak", "wake_followup", "voice", "model", "genie_mode", "instructions", "effort", "memory_sensitive", "location_metadata"];
  var PREFSYNC = { pending: {}, timer: null, seen: parseFloat(LS.getItem("gink_prefs_seen") || "0") };
  function queuePrefs(key, value) {
    PREFSYNC.pending[key] = value; clearTimeout(PREFSYNC.timer);
    PREFSYNC.timer = setTimeout(function () {
      var changes = PREFSYNC.pending; PREFSYNC.pending = {};
      if (!W.token) return;
      fetch("/account/preferences", { method: "PUT", body: JSON.stringify({ prefs: changes }),
                                      headers: { "Content-Type": "application/json", Authorization: "Bearer " + W.token } })
        .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
        .then(function (j) { PREFSYNC.seen = j.updated; LS.setItem("gink_prefs_seen", String(j.updated)); })
        .catch(function () { Object.keys(changes).forEach(function (k) { if (!(k in PREFSYNC.pending)) PREFSYNC.pending[k] = changes[k]; }); });
    }, 1000);
  }
  function pullPrefs() {
    if (!W.token) return;
    fetch("/account/preferences", { headers: { Authorization: "Bearer " + W.token } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); }).then(function (j) {
        if (!j.updated || j.updated <= PREFSYNC.seen) return;
        PREFSYNC.seen = j.updated; LS.setItem("gink_prefs_seen", String(j.updated));
        var changed = false, remote = j.prefs || {};
        SYNCED_PREFS.forEach(function (k) {
          if (k in remote && k !== "model" && W.prefs[k] !== remote[k]) { W.prefs[k] = remote[k]; changed = true; }
        });
        if (changed) { save("gink_prefs", W.prefs); applyAppearance(); pushSettings(); if (window.setEffort) setEffort(W.prefs.effort); }
        if (remote.model && remote.model !== W.model && HANDLERS.model) HANDLERS.model(remote.model, true);
      }).catch(function () {});
  }
  setTimeout(function () { if (window.setEffort) setEffort(W.prefs.effort || "medium"); pullPrefs(); }, 0); setInterval(pullPrefs, 120000);

  // ---------------------------------------------------------------- downloads (export / save code)
  function download(name, text, type) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: type || "text/plain" }));
    a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  // ---------------------------------------------------------------- the events the page sends
  // ---- voice messages: hold the mic, let go to send (the page records: MediaRecorder); Gink answers out loud
  window.ginkVoiceRecorder = "page";
  function voiceMessage(v) {
    if (!v || v.action !== "done" || !v.data) return;
    if (W.busy) { if (window.lmSay) lmSay("Wait for Gink to finish, then send your voice message again."); return; }
    setStatus("Listening to your voice message\u2026");
    api("/voice/transcribe", { audio_b64: v.data, format: v.format || "webm",
                               language: W.prefs.speech_lang && W.prefs.speech_lang !== "auto" ? W.prefs.speech_lang : "" }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        setStatus("");
        if (!r.ok) throw new Error((j.error && j.error.message) || j.detail || "Gink couldn\u2019t hear that. Please try again.");
        var text = String(j.text || "").trim();
        if (!text) throw new Error("Gink didn\u2019t hear any words. Try again a little closer to the microphone.");
        W.voiceReply = true;
        var job = send(text, { voiceNote: true });
        if (typeof markVoiceMessage === "function") markVoiceMessage(v.url || "", v.secs || 0);
        return job;
      });
    }).catch(function (e) { setStatus(""); W.voiceReply = false; if (window.lmSay) lmSay(e.message || "Gink couldn\u2019t hear that."); });
  }

  var HANDLERS = {
    send: function (v) { send(String(v || "")); },
    voice_message: voiceMessage,
    publish_design: function (v) {                                       // the code viewer's Publish
      api("/sites/publish", { html: (v || {}).html || "", title: (v || {}).title || "" }).then(function (r) {
        if (!r.ok) return errorText(r).then(function (t) { cvPublished(null, t); });
        return r.json().then(function (j) { cvPublished(j.url); });
      }).catch(function () { cvPublished(null, "Couldn\u2019t reach Gink. Check your connection."); });
    },
    stop: function () { if (W.busy && W.busy.abort) W.busy.abort(); stopSpeaking(); },
    new_chat: newChat,
    temporary: function (on) { W.tempMode = !!on; setTemporary(!!on); },
    select_session: function (id) { openSession(id); },
    tasks_load: function () { loadTasks(); },                          // scheduled tasks (0.1.161): the cards
    task_create: function (v) {
      var src = String((v && v.source) || "");
      if (!W.token) return taskResult(src, null, "Sign in to Gink to schedule tasks.");
      var body = {}; ["title", "task", "every", "at", "day", "date", "source", "notify_email"].forEach(function (k) { if (v[k] !== undefined) body[k] = v[k]; });
      taskCall("POST", "/tasks", body).then(function (t) { taskResult(src, t); sync(); if (!t.existing) offerTaskNotifications(); })
        .catch(function (err) { taskResult(src, null, err.message); });
    },
    task_action: function (v) {
      if (!v || !v.id || !W.token) return;
      var id = encodeURIComponent(v.id), a = v.action;
      var call = a === "delete" ? taskCall("DELETE", "/tasks/" + id) : a === "run" ? taskCall("POST", "/tasks/" + id + "/run", {}) :
                 taskCall("PATCH", "/tasks/" + id, { enabled: a === "resume" });
      call.then(function () {
        if (a === "run") taskSoon();
        ginkNotify({ id: "task-action", icon: "\u23f0", title: "Scheduled task", timeout: 3500, system: false,
                     body: a === "delete" ? "Deleted. Its results stay in its chat." : a === "run" ? "Running now \u2014 the result will be in its chat in a minute." :
                           a === "pause" ? "Paused." : "Resumed." });
      }).catch(function (err) { ginkNotify({ id: "task-action", icon: "\u23f0", title: "Scheduled task", body: err.message, timeout: 5000, system: false }); })
        .then(loadTasks);
    },
    task_open: function (v) { if (v && v.chat_id) openTaskChat(String(v.chat_id)); },
    artifact_tab: function (v) {                    // an artifact on its own: the sealed page (/artifact/frame) gets its HTML
      if (!v || typeof v.html !== "string") return;
      var w = window.open("/artifact/frame", "_blank");
      if (!w) return;
      var html = v.html, tries = 0, timer = setInterval(function () {
        if (++tries > 40) { clearInterval(timer); return; }
        try { w.postMessage({ type: "gink-artifact", html: html }, "*"); } catch (e) {}
      }, 150);
      window.addEventListener("message", function ready(e) {
        if (e.source === w && e.data && e.data.type === "gink-artifact-ready") {
          try { w.postMessage({ type: "gink-artifact", html: html }, "*"); } catch (x) {}
          clearInterval(timer); window.removeEventListener("message", ready);
        }
      });
    },
    delete_session: function (id) {
      var s = W.sessions[id]; if (!s) return;
      s.deleted = true; s.messages = []; touch(id); if (W.current === id) newChat(); refreshSidebar(); sync();
    },
    rename_session: function (v) { var s = v && W.sessions[v.id]; if (s) { s.title = String(v.title || "").slice(0, 80); touch(s.id); refreshSidebar(); sync(); } },
    pin_session: function (v) { var s = v && W.sessions[v.id]; if (s) { s.pinned = !!v.pinned; touch(s.id); refreshSidebar(); sync(); } },
    share_session: function (id) {
      var s = W.sessions[id]; if (!s) return;
      var msgs = (s.messages || []).map(function (m) { return { role: m.role, content: m.content }; });
      api("/share", { title: titleOf(s), messages: msgs }).then(function (r) {
        return r.ok ? r.json().then(function (j) { showShareLink(j.url, j.title); })
                    : errorText(r).then(function (t) { showShareLink("", t); });
      }).catch(function () { showShareLink("", "Can\u2019t reach the Gink server."); });
    },
    archive_session: function (v) {
      var s = v && W.sessions[v.id]; if (!s) return;
      s.archived = v.archived !== false; touch(s.id);
      if (s.archived && W.current === s.id) newChat();
      refreshSidebar(); sync();
    },
    branch: function (i) {
      var s = W.sessions[W.current]; if (!s) return;
      var id = uid();
      W.sessions[id] = { id: id, messages: s.messages.slice(0, Number(i) + 1), title: titleOf(s) + " (branch)", pinned: false, deleted: false, updated: now() };
      W.dirty[id] = true; persist(); openSession(id); sync();
    },
    export_session: function (id) {
      var s = W.sessions[id]; if (!s) return;
      download(titleOf(s).replace(/[^\w\- ]+/g, "").slice(0, 50) + ".md", "# " + titleOf(s) + "\n\n" + s.messages.map(function (m) {
        return (m.role === "user" ? "**You:** " : "**Gink:** ") + m.content; }).join("\n\n"), "text/markdown");
    },
    draft: function (v) {
      if (W.current) { var d = load("gink_drafts", {}); if (v) d[W.current] = String(v); else delete d[W.current]; save("gink_drafts", d); }
      else save("gink_draft_new", String(v || ""));
    },
    read_aloud: function (v) { if (v) readAloud(String(v)); },
    dictate: dictate,
    model: function (v, fromSync) { W.model = String(v || ""); LS.setItem("gink_model", W.model); setModels(W.models, W.model);
                                    if (!fromSync && W.model) queuePrefs("model", W.model); },
    feedback: function (v) { if (v && typeof v === "object") api("/feedback", Object.assign({}, v, { model: W.model })).catch(function () {}); },
    memory_undo: function (v) {                      // "Remembered" -> Undo
      if (!v) return;
      var job = v.replaced ? api("/memory/remember", { text: v.replaced }) : api("/memory/forget", { id: v.id });
      job.then(function (r) { return r.json(); }).then(function (j) {
        var all = W.memories || {}; delete all[v.id];
        if (v.replaced && j && j.id) all[j.id] = { text: j.text, created: Date.now() / 1000 };
        W.memories = all; save("gink_memories", all);
        if (typeof ginkNotify === "function") ginkNotify({ id: "mem-auto", title: "Undone", body: "Gink won\u2019t remember that.", icon: "\u21A9\uFE0F", timeout: 2500, system: false });
      }).catch(function () {});
    },
    policy_seen: function (d) { try { LS.setItem("gink_policy_seen", String(d || "").slice(0, 20)); } catch (e) {} },
    open_url: function (u) {
      u = String(u || "");
      if (/^https?:\/\//i.test(u)) window.open(u, "_blank", "noopener");
      else if (/^(mailto|tel|sms):/i.test(u)) location.href = u;                 // email, call, text: the device's app
      else if (/^gink:\/\/pro/i.test(u)) window.open(PRICING, "_blank", "noopener");  // "Upgrade to Gink Pro"
      else if (/^gink:/i.test(u)) { setStatus(DESKTOP_ONLY); setTimeout(function () { setStatus(""); }, 3000); }
    },
    play_video: function (v) { var u = (v && (v.url || v)) || ""; if (/^https?:\/\//i.test(u)) window.open(u, "_blank", "noopener"); },
    save_code: function (v) { if (v && v.code != null) download(String(v.name || "code.txt"), String(v.code)); },
    open: function (what) { if (what === "genie") { window.open("/genie", "_blank"); return; }
      if (what === "pro") { window.open(PRICING, "_blank", "noopener"); return; }           // Settings > Plan > Upgrade
      if (what === "settings") { openSettings("general"); pushSettings(); } else { setStatus(DESKTOP_ONLY); setTimeout(function () { setStatus(""); }, 3000); } },
    menu: function (what) { HANDLERS.open(what); },
    setting: function (v) {
      if (!v || !v.key) return;
      if (v.key === "app_lock") {                     // Lock Gink: a passkey proves it works (and that it's you) first
        return passkeyCheck().then(function () {
          W.prefs.app_lock = !!v.value; save("gink_prefs", W.prefs); lockMark();
          settingsToast(v.value ? "Gink now locks in this browser. Unlock with your passkey." : "Lock Gink is off in this browser.");
        }, function (e) { settingsToast(e.message || "Not changed.", "err"); }).then(function () { pushSettings(); });
      }
      W.prefs[v.key] = v.value; save("gink_prefs", W.prefs);
      if (v.key === "people_on" && typeof peopleSetOn === "function") peopleSetOn(!!v.value && !W.care);
      if (PROFILE_KEYS.indexOf(v.key) >= 0) profileEdit(v.key, v.value);      // follows you to the apps too
      if (SYNCED_PREFS.indexOf(v.key) >= 0) queuePrefs(v.key, v.value);         // follows you to every device
      if (/^(theme|chat_font|motion)$/.test(v.key)) applyAppearance();
      if (v.key === "model") HANDLERS.model(v.value);
      if (v.key === "wake_enabled") { WK.blocked = false; if (v.value) wakeStart(); else { wakeStop(); wakeStatus("Off"); } }
      if (v.key === "notify_system" && v.value) {        // the browser asks first; a "no" there is the browser's to change
        try {
          if (window.Notification && Notification.permission === "default") {
            var asked = Notification.requestPermission(function () { pushSettings(); });      // older Safari: a callback
            if (asked && asked.then) asked.then(function () { pushSettings(); });
          }
        } catch (e) {}
        try { if (window.Notification && Notification.permission === "denied") settingsToast("Your browser blocks Gink\u2019s notifications: allow them in the site\u2019s settings (the icon by the address).", "err"); } catch (e) {}
      }
      pushSettings();
    },
    settings_action: function (v) {
      var name = v && v.name;
      if (name === "refresh") return (v.value === "account" ? loadDevices() : v.value === "connected" ? loadConnected()
                                      : v.value === "privacy" ? loadLockdown() : v.value === "family" ? loadFamily()
                                      : v.value === "memory" ? loadMemory()
                                      : v.value === "workspace" ? loadOrg() : v.value === "schedules" ? loadSchedules() : pushSettings({}, W.info));
      if (name === "memory_import") return importMemories(v.value);
      if (name === "memory_import_copy") return settingsToast("Select the prompt and copy it (Cmd/Ctrl+C).", "err");   // the browser couldn't copy
      if (name === "people_delete") {                   // People: everything kept in this browser
        if (typeof peopleDeleteAll === "function") peopleDeleteAll();
        return settingsToast("People data deleted from this browser.");
      }
      if (name === "export_server") {                  // everything on the server, as a ZIP
        settingsToast("Preparing your data\u2026");
        return fetch("/account/export.zip", { headers: placeHeaders({ Authorization: "Bearer " + W.token }) }).then(function (r) {
          if (!r.ok) return r.json().catch(function () { return {}; }).then(function (j) { throw new Error(j.detail || "Couldn\u2019t download your data."); });
          return r.blob().then(function (bl) {
            var a = document.createElement("a"); a.href = URL.createObjectURL(bl); a.download = "gink-data.zip";
            document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
            settingsToast("Your data is downloading.");
          });
        }).catch(function (err) { settingsToast(err.message); });
      }
      if (name === "tsk_add") {                         // Scheduled tasks (0.1.161)
        var tv = {}; try { tv = JSON.parse(v.value || "{}"); } catch (e) { return; }
        if (!String(tv.task || "").trim()) return settingsToast("Write the task first.");
        return taskCall("POST", "/tasks", tv).then(function () { settingsToast("Scheduled. Its results will be in its own chat."); loadSchedules(); sync(); offerTaskNotifications(); })
          .catch(function (err) { settingsToast(err.message); });
      }
      if (name === "tsk_pause" || name === "tsk_resume") {
        return taskCall("PATCH", "/tasks/" + encodeURIComponent(v.value), { enabled: name === "tsk_resume" })
          .then(function () { settingsToast(name === "tsk_pause" ? "Paused." : "Resumed."); loadSchedules(); }).catch(function (err) { settingsToast(err.message); });
      }
      if (name === "tsk_run") {
        return taskCall("POST", "/tasks/" + encodeURIComponent(v.value) + "/run", {})
          .then(function () { settingsToast("Running now \u2014 the result will be in its chat in a minute."); loadSchedules(); taskSoon(); })
          .catch(function (err) { settingsToast(err.message); });
      }
      if (name === "tsk_delete") {
        return taskCall("DELETE", "/tasks/" + encodeURIComponent(v.value)).then(function () { settingsToast("Deleted. Its results stay in its chat."); loadSchedules(); })
          .catch(function (err) { settingsToast(err.message); });
      }
      if (name === "tsk_open") { if (typeof closeSettings === "function") closeSettings(); return openTaskChat(String(v.value || "")); }
      if (name === "sch_add") {
        var sv = {}; try { sv = JSON.parse(v.value || "{}"); } catch (e) { return; }
        if (!String(sv.input || "").trim()) return settingsToast("Write the task first.");
        return schCall("POST", "/dev/schedules", { input: sv.input.trim(), every: sv.every || "daily", at: sv.at || "08:00",
                                                   notify_email: !!sv.notify_email }, "Scheduled.");
      }
      if (name === "sch_pause") return schCall("PATCH", "/dev/schedules/" + encodeURIComponent(v.value), { enabled: false }, "Paused.");
      if (name === "sch_resume") return schCall("PATCH", "/dev/schedules/" + encodeURIComponent(v.value), { enabled: true }, "Resumed.");
      if (name === "sch_delete") return schCall("DELETE", "/dev/schedules/" + encodeURIComponent(v.value), null, "Deleted.");
      if (name === "org_create") return orgCall("POST", "/org", { name: String(v.value || "").trim() }, "Workspace created.");
      if (name === "org_invite") return orgCall("POST", "/org/invite", { email: String(v.value || "").trim() }, "Invitation sent.");
      if (name === "org_accept") return orgCall("POST", "/org/respond", { accept: true }, "You joined the workspace.");
      if (name === "org_decline") return orgCall("POST", "/org/respond", { accept: false }, "Declined.");
      if (name === "org_leave") return orgCall("POST", "/org/leave", {}, "You left the workspace.");
      if (name === "org_remove") return orgCall("POST", "/org/remove", { email: v.value || "" }, "Removed.");
      if (name === "org_instructions") return orgCall("PUT", "/org/settings", { instructions: String(v.value || "") }, "Saved.");
      if (name === "org_usage") {                       // a CSV (no chats) for the admin's reports
        return fetch("/org/usage.csv?days=30", { headers: { Authorization: "Bearer " + W.token } }).then(function (r) {
          if (!r.ok) return r.json().catch(function () { return {}; }).then(function (j) { throw new Error(j.detail || "Couldn\u2019t get the usage."); });
          return r.blob().then(function (b) {
            var a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "gink-workspace-usage.csv";
            document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
            settingsToast("Usage saved as a file.");
          });
        }).catch(function (err) { settingsToast(err.message); });
      }
      if (name === "org_safety") {                       // counts only (never words): healthcare mode's safety report
        return fetch("/org/safety.csv?days=30", { headers: { Authorization: "Bearer " + W.token } }).then(function (r) {
          if (!r.ok) return r.json().catch(function () { return {}; }).then(function (j) { throw new Error(j.detail || "Couldn\u2019t get the safety report."); });
          return r.blob().then(function (b) {
            var a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = "gink-workspace-safety.csv";
            document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
            settingsToast("Safety report saved as a file.");
          });
        }).catch(function (err) { settingsToast(err.message); });
      }
      if (name === "org_delete") return orgCall("POST", "/org/delete", { confirm: String(v.value || "").trim() }, "Workspace deleted.");
      if (name === "org_set") {
        var os_ = {}; try { os_ = JSON.parse(v.value || "{}"); } catch (e) { return; }
        var ob = {}; ob[os_.key] = os_.value;
        return orgCall("PUT", "/org/settings", ob, "Saved.");
      }
      if (name === "training_on") return setTraining(true, false, "Thank you \u2014 your Gink Genie sessions will help train Gink.");
      if (name === "training_off") return setTraining(false, false, "Stopped sharing.");
      if (name === "training_delete") return setTraining(false, true, "Stopped, and deleted what you shared.");
      if (name === "family_birth_year") return familyCall("/account/age", { birth_year: String(v.value || "").trim() }, "Saved.");
      if (name === "family_invite") return familyCall("/family/invite", { teen: String(v.value || "").trim() }, "Invitation sent. It applies once they accept.");
      if (name === "family_accept") return familyCall("/family/respond", { accept: true }, "Linked.");
      if (name === "family_decline") return familyCall("/family/respond", { accept: false }, "Declined.");
      if (name === "family_unlink") return familyCall("/family/unlink", v.value ? { teen: v.value } : {}, "Unlinked.");
      if (name === "family_set") {
        var fs = {}; try { fs = JSON.parse(v.value || "{}"); } catch (e) { return; }
        var ctl = {}; ctl[fs.key] = fs.value;
        if (String(fs.key || "").indexOf("quiet") === 0 && fs.tz) ctl.tz = fs.tz;
        return familyCall("/family/controls", { teen: fs.teen, controls: ctl }, "Saved.", "PUT");
      }
      if (name === "phone_send") {
        var num = String(v.value || "").trim();
        return api("/account/phone/send", { phone: num }).then(function (r) {
          if (!r.ok) return errorText(r).then(settingsToast);
          W.phonePending = num; settingsToast("Code sent by SMS."); loadDevices();
        });
      }
      if (name === "phone_verify") {
        return api("/account/phone/verify", { phone: W.phonePending || "", code: String(v.value || "").trim() }).then(function (r) {
          if (!r.ok) return errorText(r).then(settingsToast);
          W.phonePending = ""; settingsToast("Phone number added."); loadDevices();
        });
      }
      if (name === "phone_remove") {
        return fetch("/account/phone", { method: "DELETE", headers: { Authorization: "Bearer " + W.token } }).then(function (r) {
          if (!r.ok) return errorText(r).then(settingsToast);
          settingsToast("Phone number removed."); loadDevices();
        });
      }
      if (name === "passkey_add") {
        if (!WA.supported()) return settingsToast("This browser doesn\u2019t support passkeys.");
        return api("/account/passkeys/register/begin", {}).then(function (r) { return r.ok ? r.json() : errorText(r).then(function (t) { throw new Error(t); }); })
          .then(WA.create).then(function (cred) { return api("/account/passkeys/register/finish", { credential: cred }); })
          .then(function (r) { return r.ok ? r.json() : errorText(r).then(function (t) { throw new Error(t); }); })
          .then(function () { settingsToast("Passkey added. Next time, choose \u201cSign in with a passkey\u201d."); loadDevices(); })
          .catch(function (e) { settingsToast(WA.cancelled(e) ? "Cancelled." : e.message); });
      }
      if (name === "passkey_remove" && v.value) {
        return fetch("/account/passkeys/" + encodeURIComponent(v.value), { method: "DELETE", headers: { Authorization: "Bearer " + W.token } })
          .then(function () { settingsToast("Passkey removed."); loadDevices(); });
      }
      if (name === "add_prompt") {
        var text = String(v.value || "").trim(), list = myPrompts();
        var problem = !text ? "Write the prompt first." : text.length > 2000 ? "A prompt can be up to 2000 characters."
                    : list.some(function (x) { return x.text === text; }) ? "You already have this prompt."
                    : list.length >= 50 ? "You can keep up to 50 prompts. Delete one first." : "";
        if (problem) return settingsToast(problem, "error");
        list.push({ id: uid().slice(0, 10), text: text }); savePrompts(list);
        settingsToast("Added. Type / in a message to use it."); return pushSettings();
      }
      if (name === "delete_prompt") { savePrompts(myPrompts().filter(function (x) { return x.id !== v.value; })); return pushSettings(); }
      if (name === "delete_shared" && v.value) {
        return fetch("/shared/" + encodeURIComponent(v.value), { method: "DELETE", headers: { Authorization: "Bearer " + W.token } })
          .then(function () { settingsToast("Link deleted: it no longer works."); loadLockdown(); });
      }
      if (name === "unarchive_chat" && v.value && W.sessions[v.value]) {
        W.sessions[v.value].archived = false; touch(v.value); refreshSidebar(); sync(); settingsToast("Back in Recents."); return loadLockdown();
      }
      if (name === "archive_all") {
        var n = 0;
        Object.keys(W.sessions).forEach(function (k) { var x = W.sessions[k]; if (!x.deleted && !x.archived && (x.messages || []).length) { x.archived = true; touch(k); n++; } });
        if (W.sessions[W.current] && W.sessions[W.current].archived) newChat();
        refreshSidebar(); sync(); settingsToast("Archived " + n + " chat" + (n === 1 ? "" : "s") + "."); return loadLockdown();
      }
      if (name === "lockdown_on" || name === "lockdown_off") {
        return api("/account/lockdown", { on: name === "lockdown_on" }).then(function () {
          settingsToast(name === "lockdown_on" ? "Lockdown mode is on." : "Lockdown mode is off."); loadLockdown(); });
      }
      if (name === "upgrade") { window.open(PRICING, "_blank", "noopener"); return; }
      if (name === "people_open") { if (window.closeSettings) closeSettings(); if (window.openPeople) openPeople(); return; }
      if (name === "save_instructions") {
        W.prefs.instructions = String(v.value || "").slice(0, 2000); save("gink_prefs", W.prefs);
        queuePrefs("instructions", W.prefs.instructions); pushSettings();
        return settingsToast("Instructions saved \u2014 Gink will follow them in every chat, on all your devices.");
      }
      if (name === "open_url" && v.value) return HANDLERS.open_url(v.value);
      if (name === "sync_now") { sync(); return settingsToast("Syncing your chats\u2026"); }
      if (name === "export") {                                   // chats, prompts and settings from this browser, as a file
        var data = { exported: new Date().toISOString(), email: W.email, prefs: W.prefs, prompts: myPrompts(),
                     chats: Object.keys(W.sessions).map(function (k) { return W.sessions[k]; })
                       .filter(function (c) { return !c.deleted && !c.temporary; }) };
        var a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
        a.download = "gink-export-" + new Date().toISOString().slice(0, 10) + ".json";
        document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
        return settingsToast("Your data was saved as a file.");
      }
      if (name === "delete_chats") {
        // Settings already asked "Delete all chats?" (confirmDanger)
        Object.keys(W.sessions).forEach(function (k) { var c = W.sessions[k]; if (!c.temporary) { c.deleted = true; c.messages = []; touch(k); } });
        refreshSidebar(); newChat(); sync();
        return settingsToast("All chats deleted.");
      }
      if (name === "delete_account") {
        // Settings already asked for DELETE to be typed (confirmDanger)
        return api("/account/delete", { confirm: "DELETE" }).then(function (r) {
          if (!r.ok) return errorText(r).then(function (t) { settingsToast(t, "err"); });
          ["gink_sessions", "gink_dirty", "gink_prompts", "gink_prefs", "gink_since", "gink_prefs_seen"].forEach(function (k) { LS.removeItem(k); });
          W.sessions = {}; W.dirty = {};
          signOut("Your account was deleted.");
        });
      }
      if (name === "log_out" || name === "logout") {             // end this browser's session on the server too
        return api("/auth/logout", {}, { noLogout: true }).catch(function () {}).then(function () { signOut(""); });
      }
      if (name === "revoke_session" && v.value) {
        return fetch("/account/sessions/" + encodeURIComponent(v.value), { method: "DELETE", headers: { Authorization: "Bearer " + W.token } })
          .then(function () { settingsToast("That device is signed out."); loadDevices(); });
      }
      if (name === "twofa_setup") return twofaPost("/account/2fa/setup", {}, function (j) { W.twofa = { setup: j }; loadDevices(); });
      if (name === "twofa_enable") return twofaPost("/account/2fa/enable", { code: String(v.value || "").trim() }, function (j) {
        W.twofa = { codes: j.recovery_codes || [] }; settingsToast("Two-step verification is on."); loadDevices(); });
      if (name === "twofa_disable") return twofaPost("/account/2fa/disable", { code: String(v.value || "").trim() }, function () {
        W.twofa = {}; settingsToast("Two-step verification is off."); loadDevices(); });
      if (name === "twofa_cancel" || name === "twofa_done") { W.twofa = {}; return loadDevices(); }
      if (name === "connect_app" && v.value) return connectApp(String(v.value));
      if (name === "disconnect_app" && v.value) {
        return fetch("/connected/" + encodeURIComponent(v.value), { method: "DELETE", headers: { Authorization: "Bearer " + W.token } })
          .then(function () { settingsToast("Disconnected. Gink can no longer use it."); loadConnected(); });
      }
      if (name === "delete_site" && v.value) {
        return fetch("/sites/" + encodeURIComponent(v.value), { method: "DELETE", headers: { Authorization: "Bearer " + W.token } })
          .then(function () { settingsToast("Website deleted."); loadDevices(); });
      }
      if (name === "sign_out_others") {
        return api("/account/sessions/sign-out-others", {}).then(function () { settingsToast("All your other devices are signed out."); loadDevices(); });
      }
      settingsToast(DESKTOP_ONLY);
    },
    // + menu > Camera (the page has written the mode's request into the box). Phones: the system camera, through a
    // file input with `capture`. Computers: a small window with the live picture and a Take photo button.
    camera: function () {
      function attach(dataUrl) { HANDLERS.attach_data({ name: "photo-" + new Date().toISOString().slice(11, 19).replace(/:/g, "") + ".jpg", data: dataUrl }); }
      function shrink(source, w, h) {                          // at most 1,600 px on the long side, JPEG
        var k = Math.min(1, 1600 / Math.max(w, h)), c = document.createElement("canvas");
        c.width = Math.round(w * k); c.height = Math.round(h * k);
        c.getContext("2d").drawImage(source, 0, 0, c.width, c.height);
        return c.toDataURL("image/jpeg", 0.88);
      }
      function fromFile() {                                    // phones (and the fallback everywhere)
        var inp = document.createElement("input"); inp.type = "file"; inp.accept = "image/*"; inp.setAttribute("capture", "environment");
        inp.onchange = function () {
          var f = inp.files && inp.files[0]; if (!f) return;
          var img = new Image();
          img.onload = function () { attach(shrink(img, img.naturalWidth, img.naturalHeight)); URL.revokeObjectURL(img.src); };
          img.onerror = function () { setStatus("That photo couldn\u2019t be read. Please try again."); };
          img.src = URL.createObjectURL(f);
        };
        inp.click();
      }
      var phone = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent || "");
      if (phone || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return fromFile();
      navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } }, audio: false }).then(function (stream) {
        var back = document.createElement("div"); back.id = "cam-live";
        back.style.cssText = "position:fixed;top:0;right:0;bottom:0;left:0;z-index:500;background:rgba(0,0,0,.72);display:grid;place-items:center;padding:16px";
        var box = document.createElement("div"); box.style.cssText = "background:#111;border-radius:20px;padding:12px;max-width:min(760px,96vw);box-shadow:0 30px 80px rgba(0,0,0,.5)";
        var video = document.createElement("video"); video.autoplay = true; video.playsInline = true; video.muted = true; video.srcObject = stream;
        video.style.cssText = "display:block;max-width:100%;max-height:70vh;border-radius:12px;background:#000";
        var row = document.createElement("div"); row.style.cssText = "display:flex;gap:10px;justify-content:center;margin-top:12px";
        function close() { stream.getTracks().forEach(function (t) { t.stop(); }); back.remove(); document.removeEventListener("keydown", onKey); }
        function onKey(e) { if (e.key === "Escape") close(); if (e.key === "Enter" || e.key === " ") { e.preventDefault(); snap(); } }
        function snap() { if (!video.videoWidth) return; var d = shrink(video, video.videoWidth, video.videoHeight); close(); attach(d); }
        [["Cancel", close, "background:#2b2b2e;color:#fff"], ["Take photo", snap, "background:#A8F03C;color:#10200a;font-weight:700"]].forEach(function (x) {
          var btn = document.createElement("button"); btn.type = "button"; btn.textContent = x[0]; btn.onclick = x[1];
          btn.style.cssText = "border:0;border-radius:999px;padding:11px 22px;font:inherit;font-size:15px;cursor:pointer;" + x[2];
          row.appendChild(btn);
        });
        box.appendChild(video); box.appendChild(row); back.appendChild(box); document.body.appendChild(back);
        document.addEventListener("keydown", onKey);
      }).catch(function (err) {
        if (err && (err.name === "NotAllowedError" || err.name === "SecurityError"))
          setStatus("Gink isn\u2019t allowed to use the camera. Allow it for this site in your browser, or choose a photo instead.");
        fromFile();
      });
    },
    live_ask: function (v) {                         // Live camera: what the camera sees now + the question
      if (!v || !v.data) return;
      HANDLERS.attach_data({ name: v.name || "live.jpg", data: v.data });
      send(String(v.question || "What is this?")).then(function () { if (window.liveDone) window.liveDone(); },
                                                     function () { if (window.liveDone) window.liveDone(); });
    },
    attach_data: function (v) {
      if (!v || !v.data) return;
      var name = String(v.name || "file");
      if (/^data:image\//.test(v.data)) { W.atts.push({ name: name, kind: "image", thumb: v.data, data_url: v.data }); showAtts(); return; }
      var slot = { name: name, kind: "text", loading: true }; W.atts.push(slot); showAtts();
      api("/attachments/read", { name: name, data: v.data }).then(function (r) {
        return r.ok ? r.json() : errorText(r).then(function (t) { throw new Error(t); });
      }).then(function (j) {
        slot.loading = false; slot.text = j.text; slot.note = j.note || ""; showAtts();
      }).catch(function (e) {
        var i = W.atts.indexOf(slot); if (i >= 0) W.atts.splice(i, 1); showAtts();
        setStatus((e && e.message && e.message !== "signed out") ? e.message : "Gink can't read " + name + ".");
        setTimeout(function () { setStatus(""); }, 4500);
      });
    },
    attach_video: function (v) {                    // the page took a few frames from a video (0.1.162)
      if (!v) return;
      var name = String(v.name || "video");
      if (v.error || !v.frames || !v.frames.length) {
        showAtts();
        setStatus(v.error === "slow" ? name + " took too long to open. Try a shorter clip."
                  : "Gink couldn\u2019t play " + name + " here (its format). Try an .mp4 video, or send a photo of what you want to show.");
        setTimeout(function () { setStatus(""); }, 5000);
        return;
      }
      var frames = v.frames.filter(function (f) { return f && /^data:image\/(jpeg|png|webp);base64,/.test(String(f.data || "")); }).slice(0, 5);
      W.atts.push({ name: name, kind: "video", thumb: frames[0].data, frames: frames, duration: Number(v.duration) || 0,
                    note: frames.length + " frames" + (v.duration ? " \u00b7 " + mmss(v.duration) : "") });
      showAtts();
    },
    remove_attachment: function (i) { W.atts.splice(Number(i), 1); showAtts(); },
    voice_start: function (v) {
      wakeStop();                                                   // the conversation takes the microphone
      if (v && v.voice) { W.prefs.voice = v.voice; save("gink_prefs", W.prefs); }
      V.on = true; V.muted = false; vListen();
    },
    voice_end: function () { vStop(); if (typeof wakeGlow === "function") wakeGlow("off"); setTimeout(wakeStart, 800); },   // then listen for "Hey Gink" again
    voice_mute: function (v) {
      V.muted = !!(v && v.muted);
      if (V.muted) { if (V.rec) { try { V.rec.abort(); } catch (e) {} } stopSpeaking(); voiceUiState("muted"); }
      else vListen();
    },
    voice_intro_seen: function () { W.prefs.voice_intro_seen = true; save("gink_prefs", W.prefs); setVoiceConfig({ intro_seen: true }); },
    voice_preview: function (v) {
      var key = v && v.key, p = voiceList().filter(function (x) { return x.key === key; })[0];
      speakThen("Hi, I'm " + (p ? p.name : "Gink") + ". " + (p ? p.desc : "") + ".", null, key);
    },
    voice_preview_stop: stopSpeaking
  };
  HANDLERS.file_thumb = function () {};
  // Error reports (Settings > Privacy > Send error reports): what broke and where in Gink's code -- never chats.
  var ERR = { sent: {}, n: 0 };
  function reportError(kind, message, stack) {
    if ((W.prefs || {}).send_errors === false || ERR.n >= 20) return;
    var key = kind + "|" + String(stack || "").slice(0, 300); if (ERR.sent[key]) return;
    ERR.sent[key] = 1; ERR.n++;
    try {
      fetch("/errors", { method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
        body: JSON.stringify({ kind: kind || "Error", message: String(message || "").slice(0, 300), stack: String(stack || "").slice(0, 6000),
                               platform: "web", version: (window.GINK_VERSION || "?") }) }).catch(function () {});
    } catch (e) {}
  }
  window.addEventListener("error", function (e) {
    if (!e || !e.message) return;                                   // a picture that didn't load isn't a bug
    reportError((e.error && e.error.name) || "Error", e.message, (e.error && e.error.stack) || (e.filename + ":" + e.lineno));
  });
  window.addEventListener("unhandledrejection", function (e) {
    var r = e && e.reason; if (!r || (r.message === "signed out")) return;
    reportError(r.name || "UnhandledRejection", r.message || String(r), r.stack || "");
  });
  // Age and parental controls: the one-time birth-year question; a parent can turn voice off.
  var VOICE_EVENTS = { voice_toggle: 1, voice_start: 1, dictate: 1, read_aloud: 1, voice_preview: 1, voice_message: 1 };
  function checkFamily() {
    var json = function (r) { return r.ok ? r.json() : Promise.reject(); };
    api("/account/age").then(json).then(function (a) {
      if (a.blocked) return askBirthYear("Gink is for people 13 and older.", true);
      if (a.needed) askBirthYear();
      return api("/family").then(json).then(function (f) {
        var off = ((f && f.my_controls) || {}).voice === false;
        W.voiceOff = off ? "Voice is turned off in your parental controls." : "";
        if (off) { try { stopSpeaking(); wakeStop(); } catch (e) {} }
      });
    }).catch(function () {});
  }
  HANDLERS.birth_year = function (year) {
    api("/account/age", { birth_year: String(year || "") }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (!r.ok) { var m = j.detail || "That didn\u2019t work. Please try again."; return askBirthYear(m, /13 and older/.test(m)); }
        birthYearDone(); checkFamily();
      });
    }).catch(function () { askBirthYear("Couldn\u2019t save that \u2014 check your connection and try again."); });
  };
  var LOCKED_OK = { unlock: 1, lock_signout: 1, page_visibility: 1 };
  window.ginkEmit = function (type, value) {
    if (LK.locked && !LOCKED_OK[type]) return;                 // locked: nothing behind the lock can be used
    if (VOICE_EVENTS[type] && W.voiceOff) { settingsToast(W.voiceOff); return; }
    var h = HANDLERS[type];
    if (h) { try { h(value); } catch (e) { console.error("Gink web:", type, e); } }
  };

  // ---------------------------------------------------------------- Lock Gink in this browser (a passkey)
  // Settings > Privacy > Lock Gink: the page is covered when Gink opens and after you've been away, until one of YOUR
  // passkeys says it's you (Face ID, Touch ID, Windows Hello, your phone). Shared with Gink Genie and the console in
  // this browser (web_app/lock.js reads the same gink_prefs and gink_unlocked_at).
  var LK = { locked: false, away: null, busy: false };
  function lockAfterMs() { var v = String(W.prefs.app_lock_after || "1"); return v === "launch" ? null : (parseFloat(v) || 1) * 60000; }
  function lockMark() { try { LS.setItem("gink_unlocked_at", String(Date.now())); } catch (e) {} }
  function lockLast() { try { return parseFloat(LS.getItem("gink_unlocked_at") || "0") || 0; } catch (e) { return 0; } }
  function lockNow() {
    if (LK.locked || !W.token) return;
    LK.locked = true;
    if (typeof appLock === "function") appLock(true, { label: "a passkey", message: "Use Face ID, Touch ID, Windows Hello or your phone to open Gink." });
  }
  function passkeyCheck() {                                   // one of this account's passkeys, on this device
    if (!WA.supported()) return Promise.reject(new Error("This browser doesn\u2019t support passkeys."));
    return api("/account/passkeys/verify/begin", {}).then(function (r) { return r.ok ? r.json() : errorText(r).then(function (t) { throw new Error(t); }); })
      .then(function (b) { return WA.get(b.options).then(function (cred) { return api("/account/passkeys/verify/finish", { request_id: b.request_id, credential: cred }); }); })
      .then(function (r) { if (!r.ok) return errorText(r).then(function (t) { throw new Error(t); }); })
      .catch(function (e) { throw (e && (e.name === "NotAllowedError" || e.name === "AbortError")) ? new Error("Cancelled.") : e; });
  }
  setInterval(function () { if (!LK.locked && !document.hidden && W.token) lockMark(); }, 20000);
  HANDLERS.unlock = function () {
    if (LK.busy) return;
    LK.busy = true; appLock(true, { label: "a passkey", busy: true });
    passkeyCheck().then(function () { LK.locked = false; LK.away = null; lockMark(); appLock(false); },
                        function (e) { appLock(true, { label: "a passkey", message: e.message || "Not unlocked." }); })
      .then(function () { LK.busy = false; });
  };
  HANDLERS.lock_signout = function () { LK.locked = false; if (typeof appLock === "function") appLock(false); signOut(""); };
  HANDLERS.page_visibility = function (v) {
    if (v === "hidden") { if (!LK.locked) LK.away = Date.now(); return; }
    var after = lockAfterMs();
    if (W.prefs.app_lock && after !== null && LK.away && Date.now() - LK.away >= after) lockNow();
    LK.away = null;
  };

  // ---------------------------------------------------------------- start
  function start() {
    setVoiceConfig({ voices: voiceList(), voice: W.prefs.voice || "Female (Jenny)", intro_seen: !!W.prefs.voice_intro_seen });
    var first = (W.name || W.email || "Gink").split(/[\s@]/)[0];
    setUser(W.name || W.email || "Gink user", "", first);
    if (W.profile.updated) applyProfile();                         // the synced profile: name and photo
    setTimeout(function () { if (!W.voiceOff) wakeStart(); }, 1500);   // "Hey Gink", if it's on (and voice is allowed)
    applyAppearance();
    api("/ai/usage").then(function (r) { return r.ok ? r.json() : null; }).then(function (u) { if (u) W.plan = u.plan; }).catch(function () {});
    api("/ai/openai/v1/models").then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      var ids = ((j && j.data) || []).map(function (m) { return m.id; }).filter(function (id) {
        return !/whisper|tts|guard|embed|orpheus|compound|allam|playai/i.test(id) && /^Gink /.test(niceModel(id)) && id !== "gink-search";
      });                                                       // Gink's models only (not the provider's raw list)
      W.models = ids.map(function (id) { return { id: id, name: niceModel(id), tier: "" }; });
      if (!W.model || ids.indexOf(W.model) < 0) W.model = ids[0] || "";
      setModels(W.models, W.model);
    }).catch(function () {});
    newChat(); sync();
    checkFamily();
    checkPolicies();                                 // "we've updated our privacy policy and terms", once per change
    checkStatus(); clearInterval(W.statusTimer); W.statusTimer = setInterval(checkStatus, 300000);
    checkCare();
    // Lock Gink: opened after time away -> covered until a passkey says it's you
    var lockAfter = lockAfterMs();
    if (W.prefs.app_lock && Date.now() - lockLast() > (lockAfter === null ? 60000 : lockAfter)) lockNow(); else lockMark();
    // People: faces grouped in THIS browser (IndexedDB); never uploaded
    if (typeof peopleSetOn === "function") { peopleSetOn(!!W.prefs.people_on && !W.care); peopleConfigure({ base: "/app/faces/", native: false }); }
    clearInterval(W.timer); W.timer = setInterval(sync, 60000);
  }
  document.addEventListener("DOMContentLoaded", function () {
    wireSignIn();
    applyAppearance();
    if (!W.token) return showSignIn("");
    api("/ai/usage").then(function (r) { if (r.ok) start(); }).catch(function () { start(); });
  });
})();
