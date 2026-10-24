/* Gink on the web -- the "bridge".
   The desktop app's chat page sends events (ginkEmit) to Python. On the web, this
   script handles them in the browser and talks ONLY to the Gink server that served
   the page (sign-in, AI, formatting, sync, images, voices).
   Chats are stored in the same format the desktop app syncs, so they appear on both. */
(function () {
  "use strict";
  var LS = window.localStorage;
  function load(k, d) { try { var v = JSON.parse(LS.getItem(k)); return v == null ? d : v; } catch (e) { return d; } }
  function save(k, v) { try { LS.setItem(k, JSON.stringify(v)); } catch (e) {} }

  var W = {
    // "Remember me" off keeps the sign-in in sessionStorage (until the browser closes): read both
    token: LS.getItem("gink_token") || sessionStorage.getItem("gink_token") || "",
    email: LS.getItem("gink_email") || sessionStorage.getItem("gink_email") || "",
    name: LS.getItem("gink_name") || sessionStorage.getItem("gink_name") || "",
    model: LS.getItem("gink_model") || "", models: [],
    sessions: load("gink_sessions", {}), dirty: load("gink_dirty", {}), since: parseFloat(LS.getItem("gink_since") || "0"),
    prefs: Object.assign({ theme: "system", chat_font: "sans", motion: "system", read_aloud: false, voice: "Female (Jenny)", reply_language: "auto",
                           style_base: "default", style_warmth: "default", style_enthusiasm: "default", style_emoji: "default", style_headers: "default" },
                         load("gink_prefs", {})),      // defaults first, so new settings show their real value
    current: null, busy: null, pendingCode: null, syncing: false
  };
  var DESKTOP_ONLY = "That\u2019s available in the Gink app on your computer or phone.";

  // ---------------------------------------------------------------- server
  function api(path, body, opts) {
    opts = opts || {};
    var h = { "Content-Type": "application/json" };
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
      return (j.error && (j.error.message || j.error)) || j.detail || ("Something went wrong (" + r.status + ").");
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
  function persist() { save("gink_sessions", W.sessions); save("gink_dirty", W.dirty); }
  function touch(id) { var s = W.sessions[id]; if (!s) return; s.updated = now(); W.dirty[id] = true; persist(); }
  function titleOf(s) {
    if (s.title) return s.title;
    var first = (s.messages || []).filter(function (m) { return m.role === "user"; })[0];
    return first ? first.content.replace(/\s+/g, " ").slice(0, 60) : "New chat";
  }
  function refreshSidebar() {
    var list = Object.keys(W.sessions).map(function (k) { return W.sessions[k]; })
      .filter(function (s) { return !s.deleted && !s.archived && (s.messages || []).length; })
      .sort(function (a, b) { return (b.pinned - a.pinned) || (b.updated - a.updated); })
      .map(function (s) { return { id: s.id, title: titleOf(s), current: s.id === W.current, pinned: !!s.pinned }; });
    setSessions(list);
  }
  function newChat() {
    W.current = null; clearFeed();
    var first = (W.name || W.email || "").split(/[\s@]/)[0];
    showWelcome(first ? "Hi " + first + ", what\u2019s on your mind?" : "Hi, what\u2019s on your mind?", "");
    setComposerText(load("gink_draft_new", "") || "");
    refreshSidebar();
  }
  function openSession(id) {
    var s = W.sessions[id]; if (!s || s.deleted) return newChat();
    W.current = id; clearFeed(); hideWelcome();
    var msgs = s.messages || [], answers = [];
    msgs.forEach(function (m, i) {
      if (m.role === "user") addUserMessage(m.content);
      else { var aid = "w" + i + "-" + uid().slice(0, 8); addAssistantMessage(aid); answers.push([aid, m.content]); }
    });
    if (answers.length) {
      api("/render", { items: answers.map(function (a) { return a[1]; }) }).then(function (r) { return r.json(); }).then(function (j) {
        answers.forEach(function (a, i) { finalizeMessage(a[0], j.html[i]); });
      }).catch(function () { answers.forEach(function (a) { setPlainText(a[0], a[1]); }); });
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
           " When you have web search results, use them and keep the facts accurate." +
           " You're running in a web browser: you can't set alarms, reminders or tasks or control the user's computer here; " +
           "if asked, say that the Gink app can do it." +
           (voice ? " You're in a live voice conversation: reply in one to three short, natural spoken sentences, " +
                    "with no lists, headings, code, links or emojis." : "");
  }
  // questions that need the internet search the web on their own, whatever model is picked
  var WEB_RE = /\b(search|look up|google|find out|latest|news|headlines|today'?s|this week|right now|currently|price of|cost of|how much (is|are|does)|exchange rate|who won|score|results? of|release date|weather|recherche|cherche|actualit\u00e9s?|derni\u00e8res? nouvelles|prix d|aujourd'hui|cette semaine)\b/i;
  var IMAGE_RE = /^\s*(please\s+)?(create|make|draw|generate|paint|design)\s+(me\s+)?(an?\s+)?(image|picture|photo|drawing|illustration|logo|poster)\b/i;

  // ---- attachments: photos stay in the browser; documents are read by the server
  W.atts = [];
  function chipOf(a) { return { name: a.name, kind: a.kind, thumb: a.thumb || "", note: a.note || "", loading: !!a.loading }; }
  function showAtts() { setAttachments(W.atts.map(chipOf)); }
  function historyText(msg, atts) {             // synced history keeps file NAMES, never contents
    return atts.length ? (msg ? msg + "\n\n" : "") + "\uD83D\uDCCE " + atts.map(function (a) { return a.name; }).join(", ") : msg;
  }
  function buildContent(msg, atts) {             // what the AI receives (same format as the desktop app)
    var docs = atts.filter(function (a) { return a.kind === "text"; }), imgs = atts.filter(function (a) { return a.kind === "image"; });
    var t = msg;
    if (docs.length) {
      t = docs.map(function (a) {
        return '<attached_file name="' + a.name.replace(/"/g, "'") + '"' + (a.note ? " (" + a.note + ")" : "") + ">\n" + a.text + "\n</attached_file>";
      }).join("\n\n") + "\n\n" + (msg || "Please read the attached file(s) and summarise the important points.");
    }
    if (!imgs.length) return t;
    return [{ type: "text", text: t || "What's in this picture?" }].concat(imgs.map(function (a) {
      return { type: "image_url", image_url: { url: a.data_url } };
    }));
  }

  function send(text, opts) {
    opts = opts || {};
    text = (text || "").trim();
    var atts = opts.voice ? [] : W.atts.slice();
    if ((!text && !atts.length) || W.busy) return Promise.resolve("");
    if (atts.some(function (a) { return a.loading; })) {
      setStatus("Wait a moment: a file is still loading."); setTimeout(function () { setStatus(""); }, 3000);
      return Promise.resolve("");
    }
    if (!W.current) {
      W.current = uid();
      W.sessions[W.current] = { id: W.current, messages: [], title: "", pinned: false, deleted: false, updated: now() };
      save("gink_draft_new", "");
    }
    var s = W.sessions[W.current];
    hideWelcome(); addUserMessage(text, atts.map(chipOf));
    s.messages.push({ role: "user", content: historyText(text, atts), ts: stamp() }); touch(s.id); refreshSidebar();
    var content = buildContent(text, atts);
    W.atts = []; showAtts();
    var drafts = load("gink_drafts", {}); delete drafts[s.id]; save("gink_drafts", drafts);
    var aid = "a" + uid().slice(0, 12);
    addAssistantMessage(aid, "Thinking\u2026");
    setComposerBusy(true);
    var web = !atts.length && (W.model === "gink-search" || WEB_RE.test(text));
    if (web) setSpinLabel(aid, "Searching the web\u2026");
    var job = SITE_EDIT_RE.test(text) && !atts.length ? makeSite(text, aid, true)
            : SITE_RE.test(text) && !atts.length ? makeSite(text, aid, false)
            : IMAGE_RE.test(text) && !atts.length ? makeImage(text, aid) : chat(s, aid, { voice: opts.voice, last: content, web: web });
    return job.then(function (reply) {
      if (reply) { s.messages.push({ role: "assistant", content: reply, ts: stamp() }); touch(s.id); }
      W.busy = null; setComposerBusy(false); refreshSidebar(); sync();
      return reply;
    });
  }

  function chat(s, aid, opts) {
    opts = opts || {};
    var ctrl = new AbortController(); W.busy = ctrl;
    var history = s.messages.slice(-24).map(function (m) { return { role: m.role, content: m.content }; });
    if (opts.last !== undefined && history.length) history[history.length - 1].content = opts.last;   // files + photos
    var body = { model: W.model || undefined, stream: true, messages: [{ role: "system", content: systemPrompt(opts.voice) }].concat(history) };
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
              if (d.error) { text += (text ? "\n\n" : "") + (d.error.message || "The AI service had a problem."); setPlainText(aid, text); return; }
              var piece = d.choices && d.choices[0] && d.choices[0].delta && d.choices[0].delta.content;
              if (piece) { text += piece; setPlainText(aid, narrow(text)); }
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
      finalizeMessage(aid, j.html);
      if (W.prefs.read_aloud) readAloud(text);
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
  function makeSite(text, aid, editing) {
    W.busy = { abort: function () {} };
    setSpinLabel(aid, editing ? "Updating your website\u2026" : "Building your website\u2026 (about a minute)");
    var go = editing
      ? api("/sites").then(function (r) { return r.json(); }).then(function (j) {
          if (!j.sites || !j.sites.length) throw new Error("You don\u2019t have a website yet \u2014 ask me to make one.");
          return api("/sites/" + encodeURIComponent(j.sites[0].id) + "/edit", { instruction: text });
        })
      : api("/sites", { prompt: text });
    return go.then(function (r) {
      if (!r.ok) return errorText(r).then(function (t) { setPlainText(aid, t); return ""; });
      return r.json().then(function (j) {
        finalizeMessage(aid, siteLink(j, editing ? "Updated:" : "Your website is live:"));
        return (editing ? "Updated your website: " : "Your website is live: ") + j.title + " " + j.url;
      });
    }).catch(function (e) { setPlainText(aid, (e && e.message && e.message !== "signed out") ? e.message : "Can't reach the Gink server."); return ""; });
  }

  function makeImage(prompt, aid) {
    W.busy = { abort: function () {} };
    setSpinLabel(aid, "Creating your image\u2026");
    return api("/media/image", { prompt: prompt, aspect_ratio: "1:1" }).then(function (r) {
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
  function sync() {
    if (!W.token || W.syncing) return;
    W.syncing = true;
    var push = Object.keys(W.dirty).map(function (id) {
      var s = W.sessions[id]; if (!s) return null;
      return { id: s.id, updated: s.updated, deleted: !!s.deleted,
               payload: { messages: s.deleted ? [] : s.messages, title: s.title || "", pinned: !!s.pinned, archived: !!s.archived } };
    }).filter(Boolean);
    api("/sync", { since: W.since, push: { chats: push } }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j) return;
      push.forEach(function (d) { delete W.dirty[d.id]; });
      var changedCurrent = false;
      ((j.changes || {}).chats || []).forEach(function (d) {
        var mine = W.sessions[d.id];
        if (mine && mine.updated >= d.updated) return;                          // newest copy wins
        var p = d.payload || {};
        W.sessions[d.id] = { id: d.id, updated: d.updated, deleted: !!d.deleted, messages: p.messages || [],
                             title: p.title || "", pinned: !!p.pinned, archived: !!p.archived };
        if (d.id === W.current) changedCurrent = true;
      });
      W.since = j.now || W.since; LS.setItem("gink_since", String(W.since)); persist();
      refreshSidebar();
      if (changedCurrent && !W.busy) openSession(W.current);
    }).catch(function () {}).then(function () { W.syncing = false; });
  }

  // ---------------------------------------------------------------- settings (web subset)
  function pushSettings(lists, extra) {
    setSettingsState({ values: Object.assign({}, W.prefs, { model: W.model }),
                       info: Object.assign({ name: W.name, email: W.email, version: "web", plan: W.plan || "free", voices: [], models: W.models, web: true }, extra || {}),
                       lists: lists || {} });
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
                 api("/account/passkeys").then(json).catch(function () { return { passkeys: [] }; })]).then(function (res) {
      var lists = { sessions: res[0] ? (res[0].sessions || []).map(function (d) { return Object.assign({}, d, { when: activeText(d) }); }) : [],
                    sites: (res[2].sites || []), security: (res[3].events || []), passkeys: (res[4].passkeys || []) };
      var extra = { twofa: Object.assign({}, res[1] || {}, W.twofa) };
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
  function archivedList() {
    return Object.keys(W.sessions).map(function (k) { return W.sessions[k]; })
      .filter(function (s) { return s.archived && !s.deleted; }).map(function (s) { return { id: s.id, title: titleOf(s) }; });
  }
  function loadLockdown() {                              // Settings > Privacy (archived chats + Lockdown mode)
    pushSettings({ archived: archivedList() });
    api("/account/lockdown").then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (j) { pushSettings({ archived: archivedList() }, { lockdown_on: !!j.on }); }).catch(function () {});
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

  // ---------------------------------------------------------------- downloads (export / save code)
  function download(name, text, type) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: type || "text/plain" }));
    a.download = name; document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  // ---------------------------------------------------------------- the events the page sends
  var HANDLERS = {
    send: function (v) { send(String(v || "")); },
    stop: function () { if (W.busy && W.busy.abort) W.busy.abort(); stopSpeaking(); },
    new_chat: newChat,
    select_session: function (id) { openSession(id); },
    delete_session: function (id) {
      var s = W.sessions[id]; if (!s) return;
      s.deleted = true; s.messages = []; touch(id); if (W.current === id) newChat(); refreshSidebar(); sync();
    },
    rename_session: function (v) { var s = v && W.sessions[v.id]; if (s) { s.title = String(v.title || "").slice(0, 80); touch(s.id); refreshSidebar(); sync(); } },
    pin_session: function (v) { var s = v && W.sessions[v.id]; if (s) { s.pinned = !!v.pinned; touch(s.id); refreshSidebar(); sync(); } },
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
    model: function (v) { W.model = String(v || ""); LS.setItem("gink_model", W.model); setModels(W.models, W.model); },
    feedback: function (v) { if (v && typeof v === "object") api("/feedback", Object.assign({}, v, { model: W.model })).catch(function () {}); },
    open_url: function (u) {
      u = String(u || "");
      if (/^https?:\/\//i.test(u)) window.open(u, "_blank", "noopener");
      else if (/^gink:/i.test(u)) { setStatus(DESKTOP_ONLY); setTimeout(function () { setStatus(""); }, 3000); }
    },
    play_video: function (v) { var u = (v && (v.url || v)) || ""; if (/^https?:\/\//i.test(u)) window.open(u, "_blank", "noopener"); },
    save_code: function (v) { if (v && v.code != null) download(String(v.name || "code.txt"), String(v.code)); },
    open: function (what) { if (what === "settings") { openSettings("general"); pushSettings(); } else { setStatus(DESKTOP_ONLY); setTimeout(function () { setStatus(""); }, 3000); } },
    menu: function (what) { HANDLERS.open(what); },
    setting: function (v) {
      if (!v || !v.key) return;
      W.prefs[v.key] = v.value; save("gink_prefs", W.prefs);
      if (/^(theme|chat_font|motion)$/.test(v.key)) applyAppearance();
      if (v.key === "model") HANDLERS.model(v.value);
      pushSettings();
    },
    settings_action: function (v) {
      var name = v && v.name;
      if (name === "refresh") return (v.value === "account" ? loadDevices() : v.value === "connected" ? loadConnected()
                                      : v.value === "privacy" ? loadLockdown() : pushSettings());
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
    remove_attachment: function (i) { W.atts.splice(Number(i), 1); showAtts(); },
    voice_start: function (v) {
      if (v && v.voice) { W.prefs.voice = v.voice; save("gink_prefs", W.prefs); }
      V.on = true; V.muted = false; vListen();
    },
    voice_end: vStop,
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
  window.ginkEmit = function (type, value) {
    var h = HANDLERS[type];
    if (h) { try { h(value); } catch (e) { console.error("Gink web:", type, e); } }
  };

  // ---------------------------------------------------------------- start
  function start() {
    setVoiceConfig({ voices: voiceList(), voice: W.prefs.voice || "Female (Jenny)", intro_seen: !!W.prefs.voice_intro_seen });
    var first = (W.name || W.email || "Gink").split(/[\s@]/)[0];
    setUser(W.name || W.email || "Gink user", "", first);
    applyAppearance();
    api("/ai/usage").then(function (r) { return r.ok ? r.json() : null; }).then(function (u) { if (u) W.plan = u.plan; }).catch(function () {});
    api("/ai/openai/v1/models").then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      var ids = ((j && j.data) || []).map(function (m) { return m.id; }).filter(function (id) { return !/whisper|tts|guard|embed|orpheus|compound|allam|playai/i.test(id); });   // chat models only
      W.models = ids.map(function (id) { return { id: id, name: niceModel(id), tier: "" }; });
      if (!W.model || ids.indexOf(W.model) < 0) W.model = ids[0] || "";
      setModels(W.models, W.model);
    }).catch(function () {});
    newChat(); sync();
    clearInterval(W.timer); W.timer = setInterval(sync, 60000);
  }
  document.addEventListener("DOMContentLoaded", function () {
    wireSignIn();
    applyAppearance();
    if (!W.token) return showSignIn("");
    api("/ai/usage").then(function (r) { if (r.ok) start(); }).catch(function () { start(); });
  });
})();
