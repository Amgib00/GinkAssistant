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
    token: LS.getItem("gink_token") || "", email: LS.getItem("gink_email") || "", name: LS.getItem("gink_name") || "",
    model: LS.getItem("gink_model") || "", models: [],
    sessions: load("gink_sessions", {}), dirty: load("gink_dirty", {}), since: parseFloat(LS.getItem("gink_since") || "0"),
    prefs: load("gink_prefs", { theme: "system", chat_font: "sans", motion: "system", read_aloud: false, voice: "Female (Jenny)", reply_language: "auto" }),
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
  function errorText(r) {
    return r.json().then(function (j) {
      return (j.error && (j.error.message || j.error)) || j.detail || ("Something went wrong (" + r.status + ").");
    }).catch(function () { return "Something went wrong (" + r.status + ")."; });
  }

  // ---------------------------------------------------------------- sign in
  var $ = function (id) { return document.getElementById(id); };
  function showSignIn(message) {
    $("web-signin").classList.add("open");
    $("ws-err").textContent = message || "";
    setTimeout(function () { ($("ws-login").hidden ? $("ws-semail") : $("ws-email")).focus(); }, 30);
  }
  function tab(which) {
    $("ws-tab-login").setAttribute("aria-selected", which === "login" ? "true" : "false");
    $("ws-tab-signup").setAttribute("aria-selected", which === "signup" ? "true" : "false");
    $("ws-login").hidden = which !== "login"; $("ws-signup").hidden = which !== "signup"; $("ws-code").hidden = true;
    $("ws-err").textContent = "";
  }
  function busyForm(form, on) { var b = form.querySelector(".ws-go"); if (b) b.disabled = on; }
  function signedIn(res) {
    W.token = res.token; W.email = res.email || W.email; W.name = res.name || W.name || "";
    LS.setItem("gink_token", W.token); LS.setItem("gink_email", W.email); LS.setItem("gink_name", W.name);
    $("web-signin").classList.remove("open");
    start();
  }
  function wireSignIn() {
    socialButtons();
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
      var started = Date.now();
      return new Promise(function (resolve, reject) {
        (function check() {
          if (Date.now() - started > 5 * 60 * 1000) return reject(new Error("Sign-in timed out. Try again."));
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
    W.token = ""; LS.removeItem("gink_token");
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
      .filter(function (s) { return !s.deleted && (s.messages || []).length; })
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
    var GINK = { "openai/gpt-oss-20b": "Gink Flake \u00b7 Free \u00b7 GPT-OSS",            // Gink's names
                 "openai/gpt-oss-120b": "Gink Crystal \u00b7 Free \u00b7 GPT-OSS",
                 "qwen/qwen3.6-27b": "Gink Prism \u00b7 Free \u00b7 Qwen",
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
  function systemPrompt() {
    var lang = W.prefs.reply_language && W.prefs.reply_language !== "auto" ? " Always answer in this language: " + W.prefs.reply_language + "." : "";
    var who = W.name ? " The user's name is " + W.name.split(" ")[0] + "." : "";
    return "You are Gink, a warm, capable AI assistant. Answer clearly and helpfully, using Markdown for structure when it helps. " +
           "It is now " + new Date().toLocaleString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric",
           hour: "2-digit", minute: "2-digit" }) + " in the user's time zone (" +
           (Intl.DateTimeFormat().resolvedOptions().timeZone || "unknown") + "). Use this for any question about the time or date." +
           who + lang +
           " You're running in a web browser: you can't set alarms, reminders or tasks or control the user's computer here; " +
           "if asked, say that the Gink app can do it.";
  }
  var IMAGE_RE = /^\s*(please\s+)?(create|make|draw|generate|paint|design)\s+(me\s+)?(an?\s+)?(image|picture|photo|drawing|illustration|logo|poster)\b/i;

  function send(text) {
    text = (text || "").trim();
    if (!text || W.busy) return;
    if (!W.current) {
      W.current = uid();
      W.sessions[W.current] = { id: W.current, messages: [], title: "", pinned: false, deleted: false, updated: now() };
      save("gink_draft_new", "");
    }
    var s = W.sessions[W.current];
    hideWelcome(); addUserMessage(text);
    s.messages.push({ role: "user", content: text, ts: stamp() }); touch(s.id); refreshSidebar();
    var drafts = load("gink_drafts", {}); delete drafts[s.id]; save("gink_drafts", drafts);
    var aid = "a" + uid().slice(0, 12);
    addAssistantMessage(aid, "Thinking\u2026");
    setComposerBusy(true);
    (IMAGE_RE.test(text) ? makeImage(text, aid) : chat(s, aid)).then(function (reply) {
      if (reply) { s.messages.push({ role: "assistant", content: reply, ts: stamp() }); touch(s.id); }
    }).then(function () {
      W.busy = null; setComposerBusy(false); refreshSidebar(); sync();
    });
  }

  function chat(s, aid) {
    var ctrl = new AbortController(); W.busy = ctrl;
    var history = s.messages.slice(-24).map(function (m) { return { role: m.role, content: m.content }; });
    var body = { model: W.model || undefined, stream: true, messages: [{ role: "system", content: systemPrompt() }].concat(history) };
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
              var d = JSON.parse(data), piece = d.choices && d.choices[0] && d.choices[0].delta && d.choices[0].delta.content;
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
  function readAloud(text) {
    if (audio) { audio.pause(); audio = null; }
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    var plain = String(text).replace(/```[\s\S]*?```/g, " ").replace(/[*_#>`|]/g, "").slice(0, 1400);
    api("/voice/speak", { text: plain, persona: W.prefs.voice || "Female (Jenny)" }).then(function (r) {
      if (!r.ok) throw new Error("voice");
      return r.json();
    }).then(function (j) {
      audio = new Audio("data:" + (j.mime_type || "audio/wav") + ";base64," + j.audio_b64);
      setSpeaking(true); audio.onended = function () { setSpeaking(false); }; audio.play();
    }).catch(function () {
      if ("speechSynthesis" in window) {                        // the browser's own voice instead
        var u = new SpeechSynthesisUtterance(plain); u.onend = function () { setSpeaking(false); };
        setSpeaking(true); speechSynthesis.speak(u);
      }
    });
  }
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
  // full voice conversations are an app feature for now
  window.voiceButton = function () { setStatus("Voice conversations are in the Gink app. Here, use the microphone to dictate."); setTimeout(function () { setStatus(""); }, 3500); };

  // ---------------------------------------------------------------- sync with the desktop app
  function sync() {
    if (!W.token || W.syncing) return;
    W.syncing = true;
    var push = Object.keys(W.dirty).map(function (id) {
      var s = W.sessions[id]; if (!s) return null;
      return { id: s.id, updated: s.updated, deleted: !!s.deleted,
               payload: { messages: s.deleted ? [] : s.messages, title: s.title || "", pinned: !!s.pinned } };
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
                             title: p.title || "", pinned: !!p.pinned };
        if (d.id === W.current) changedCurrent = true;
      });
      W.since = j.now || W.since; LS.setItem("gink_since", String(W.since)); persist();
      refreshSidebar();
      if (changedCurrent && !W.busy) openSession(W.current);
    }).catch(function () {}).then(function () { W.syncing = false; });
  }

  // ---------------------------------------------------------------- settings (web subset)
  function pushSettings() {
    setSettingsState({ values: Object.assign({}, W.prefs, { model: W.model }),
                       info: { name: W.name, email: W.email, version: "web", plan: W.plan || "free", voices: [], models: W.models, web: true },
                       lists: {} });
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
      if (name === "refresh") return pushSettings();
      if (name === "log_out" || name === "logout") return signOut("");
      settingsToast(DESKTOP_ONLY);
    },
    attach_data: function () { setStatus("Attachments are in the Gink app for now."); setTimeout(function () { setStatus(""); }, 3000); }
  };
  ["voice_start", "voice_end", "voice_mute", "voice_preview", "voice_preview_stop", "voice_intro_seen", "remove_attachment", "file_thumb"].forEach(function (k) {
    HANDLERS[k] = function () {};
  });
  window.ginkEmit = function (type, value) {
    var h = HANDLERS[type];
    if (h) { try { h(value); } catch (e) { console.error("Gink web:", type, e); } }
  };

  // ---------------------------------------------------------------- start
  function start() {
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
