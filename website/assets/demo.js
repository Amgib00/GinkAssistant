// The website demo: runs entirely in the browser. Maths, time and date are real;
// other requests get the answer Gink gives in the app, marked as a demo.
// Everything typed is shown as TEXT (textContent), never as HTML.
(function () {
  var log = document.getElementById("demo-log"), form = document.getElementById("demo-form"),
      input = document.getElementById("demo-input"), mic = document.getElementById("demo-mic"),
      glow = document.querySelector(".glow-edge");
  if (!log || !form) return;

  function add(kind, text, chip) {
    var row = document.createElement("div");
    if (kind === "you") {
      row.className = "say"; row.textContent = text;
    } else {
      row.className = "reply";
      var img = document.createElement("img"); img.src = "assets/icon-64.png"; img.alt = "";
      var body = document.createElement("div");
      var p = document.createElement("p"); p.textContent = text; body.appendChild(p);
      if (chip) { var c = document.createElement("span"); c.className = "chip"; c.textContent = chip; body.appendChild(c); }
      row.appendChild(img); row.appendChild(body);
    }
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
    return row;
  }

  // ---- real maths: numbers, + - x × * / ^ ( ) and "% of" ----
  function calc(text) {
    var t = text.toLowerCase().replace(/,/g, "").replace(/what(?:'s| is)|calculate|equals?|\?|=/g, " ").trim();
    var pct = t.match(/^(-?\d+(?:\.\d+)?)\s*%\s*of\s*(-?\d+(?:\.\d+)?)$/);
    if (pct) return fmt(parseFloat(pct[1]) / 100 * parseFloat(pct[2]), pct[1] + "% of " + pct[2]);
    var expr = t.replace(/×|x/g, "*").replace(/÷/g, "/").replace(/\s+/g, "");
    if (!/^[\d.+\-*/^()]+$/.test(expr) || !/\d/.test(expr) || !/[+\-*/^]/.test(expr)) return null;
    var pos = 0;
    function num() {
      if (expr[pos] === "(") { pos++; var v = add_(); pos++; return v; }
      if (expr[pos] === "-") { pos++; return -num(); }
      var m = expr.slice(pos).match(/^\d+(?:\.\d+)?/); if (!m) throw 0; pos += m[0].length; return parseFloat(m[0]);
    }
    function pow() { var v = num(); while (expr[pos] === "^") { pos++; v = Math.pow(v, num()); } return v; }
    function mul() { var v = pow(); while ("*/".indexOf(expr[pos]) >= 0 && expr[pos]) { var o = expr[pos++], r = pow(); v = o === "*" ? v * r : v / r; } return v; }
    function add_() { var v = mul(); while ("+-".indexOf(expr[pos]) >= 0 && expr[pos]) { var o = expr[pos++], r = mul(); v = o === "+" ? v + r : v - r; } return v; }
    try { var v = add_(); if (pos !== expr.length || !isFinite(v)) return null;
      return fmt(v, text.replace(/what(?:'s| is)|calculate|equals?|\?|=/gi, " ").replace(/\s+/g, " ").trim()); } catch (e) { return null; }
  }
  function fmt(v, label) {
    var n = Math.round(v * 1e6) / 1e6;
    return label + " = " + n.toLocaleString(undefined, { maximumFractionDigits: 6 });
  }

  var RULES = [
    [/hey gink/, function () {
      if (glow) { glow.classList.add("on"); setTimeout(function () { glow.classList.remove("on"); }, 2600); }
      return ["That's how you wake me in the app: the edges of the screen glow and I'm listening. Nothing leaves your device until you say it."]; }],
    [/^(hi|hello|hey)( gink)?\b|good (morning|afternoon|evening)/, function () {
      var h = new Date().getHours();
      return ["Good " + (h < 12 ? "morning" : h < 18 ? "afternoon" : "evening") + "! What can I do for you?"]; }],
    [/what(?:'s| is) the time|what time is it|^time$/, function () {
      return ["It's " + new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) + "."]; }],
    [/what(?:'s| is) the date|what day is it|today'?s date/, function () {
      return ["Today is " + new Date().toLocaleDateString([], { weekday: "long", day: "numeric", month: "long", year: "numeric" }) + "."]; }],
    [/(wake me|set an? alarm|alarm (for|at))/, function (t) {
      var m = t.match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/); var when = m ? m[0] : "7:00";
      return ["Done \u2014 your alarm is set for " + when + ". I'll wake you up then.", "Alarm \u00b7 " + when]; }],
    [/remind me/, function (t) {
      return ["Got it. I'll remind you" + (t.match(/ (in|at|tomorrow|tonight).*/) ? t.match(/ (in|at|tomorrow|tonight).*/)[0] : " at the right time") + ".", "Reminder saved"]; }],
    [/\b(pdf|word|excel|spreadsheet|document|file)\b/, function () {
      return ["Here's your file. Tap it to open, or save it anywhere.", "\ud83d\udcc4 Your file \u00b7 Open \u00b7 Save as"]; }],
    [/(create|make|draw|generate) (an? )?(image|picture|photo|logo)|image of/, function () {
      return ["In the app, a soft green glow appears while Gink paints your picture, then it shows up right here in the chat."]; }],
    [/brief|morning|what('?s| is) (on )?(my )?(day|today)/, function () {
      return ["Morning! It's a good day to finish your revision plan \u2014 you're 3 of 4 steps in. Today: study group at 16:00. Weather and the top story are below.", "Morning briefing"]; }],
    [/weather/, function () { return ["In the app I check the live forecast for your city (no account needed for the weather service)."]; }],
    [/(volume|music|next song|pause|play)/, function () { return ["On your Mac or PC I can change the volume and control Spotify or Apple Music \u2014 try it in the app."]; }],
    [/(battery|disk|storage)/, function () { return ["On a computer I can tell you your battery, Wi-Fi and free space instantly."]; }],
    [/(open|launch) /, function (t) { return ["Opening " + t.replace(/.*(open|launch) /, "").trim() + " \u2014 in the app, Gink opens apps, folders and websites for you."]; }],
    [/(joke|funny)/, function () { return ["Why did the snowflake join the band? It had the coolest beats."]; }],
    [/(price|cost|pro|free)/, function () { return ["Gink is free to start: 30 messages a day. Gink Pro gives you 500, more images and natural voice. See the Pricing page."]; }],
    [/(who are you|what can you do|help)/, function () { return ["I'm Gink. I chat, talk out loud, set alarms and reminders, make files and images, brief you in the morning, and on a computer I can open apps and control music. Try one of the buttons below."]; }],
  ];

  function answer(text) {
    var t = text.toLowerCase().trim();
    var c = calc(text); if (c) return [c];
    for (var i = 0; i < RULES.length; i++) if (RULES[i][0].test(t)) return RULES[i][1](t);
    return ["This demo knows a few things; the real Gink answers anything. Try a sum like \u201c15% of 80000\u201d, \u201cwake me up at 6:30\u201d or \u201cHey Gink\u201d."];
  }

  function speak(text) {
    if (!("speechSynthesis" in window) || !speakReplies) return;
    try { speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(text)); } catch (e) {}
  }
  var speakReplies = false;

  function send(text) {
    text = (text || "").trim(); if (!text) return;
    add("you", text);
    var typing = add("gink", "\u2026"); typing.querySelector("p").className = "typing";
    setTimeout(function () {
      typing.remove();
      var a = answer(text);
      add("gink", a[0], a[1]);
      speak(a[0]);
    }, 450);
  }

  form.addEventListener("submit", function (e) { e.preventDefault(); send(input.value); input.value = ""; input.focus(); });
  document.querySelectorAll("[data-try]").forEach(function (b) {
    b.addEventListener("click", function () { send(b.getAttribute("data-try")); });
  });

  var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Rec) { mic.disabled = true; mic.title = "Speaking needs Chrome, Edge or Safari"; mic.setAttribute("aria-label", "Speaking isn't available in this browser"); }
  else {
    var rec = new Rec(); rec.lang = navigator.language || "en-US"; rec.interimResults = false;
    mic.addEventListener("click", function () {
      speakReplies = true;
      try { rec.start(); mic.classList.add("listening"); } catch (e) {}
    });
    rec.onresult = function (e) { send(e.results[0][0].transcript); };
    rec.onend = function () { mic.classList.remove("listening"); };
    rec.onerror = function (e) {
      mic.classList.remove("listening");
      if (e.error === "not-allowed") add("gink", "To talk to me here, allow microphone access for this page in your browser.");
    };
  }
  add("gink", "Hi, I'm Gink. Type or tap the microphone \u2014 this demo runs in your browser.");
})();
