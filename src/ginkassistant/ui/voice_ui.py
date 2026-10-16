"""
Voice conversations, ChatGPT-Voice style, drawn inside the chat page.

  waveform button (empty message box) ->
    first time:  "Meet Voice" intro -> voice picker -> conversation
    afterwards:  conversation straight away (change the voice in Settings -> Voice)

* The orb is drawn in the chosen voice's colours and animates by STATE:
  listening (slow breathe), thinking (swirl), speaking (pulses with the
  playback level), muted (still). The microphone level is only known after
  you finish a sentence, so it doesn't pretend to follow your voice live.
* Captions show what Gink heard and the start of its reply.
* Mute pauses listening; End (or Esc) stops everything. Space toggles mute.

Python -> page: setVoiceConfig({intro_seen, voice, voices}), voiceUiState(state, text),
                voiceUiCaption(you, gink), voiceUiLevel(0..1)
page -> Python: voice_intro_seen, voice_preview {key}, voice_start {voice}, voice_mute {muted}, voice_end
"""

CSS = r"""
  /* ---------- the orb (shared by intro, picker, conversation, Settings) ---------- */
  .vorb { position: relative; border-radius: 50%; overflow: hidden; flex: none;
    background: radial-gradient(circle at 32% 26%, var(--c3) 0%, var(--c2) 52%, var(--c1) 100%);
    box-shadow: 0 22px 60px -24px var(--c1); transition: transform 0.12s ease-out; }
  .vorb::before { content: ""; position: absolute; top: -30%; left: -30%; right: -30%; bottom: -30%;
    background: conic-gradient(from 0deg, rgba(255,255,255,0), var(--c3) 22%, rgba(255,255,255,0) 48%, var(--c2) 74%, rgba(255,255,255,0));
    filter: blur(18px); opacity: 0.75; animation: vorb-spin 12s linear infinite; }
  .vorb::after { content: ""; position: absolute; left: 6%; right: 6%; top: 38%; height: 32%; border-radius: 50%;
    background: rgba(255,255,255,0.78); filter: blur(16px); animation: vorb-drift 7s ease-in-out infinite; }
  @keyframes vorb-spin { to { transform: rotate(360deg); } }
  @keyframes vorb-drift { 0%, 100% { transform: translate(-6%, -4%) scale(1); } 50% { transform: translate(6%, 6%) scale(1.08); } }
  .vorb.listening { animation: vorb-breathe 2.6s ease-in-out infinite; }
  .vorb.thinking::before { animation-duration: 2.4s; }
  .vorb.thinking::after { animation-duration: 2.2s; }
  .vorb.muted { filter: saturate(0.25); }
  .vorb.muted::before, .vorb.muted::after { animation-play-state: paused; }
  @keyframes vorb-breathe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.045); } }
  body.reduced-motion .vorb, body.reduced-motion .vorb::before, body.reduced-motion .vorb::after { animation: none !important; }

  /* ---------- dialogs: intro + picker ---------- */
  #vdlg-back { position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 70; background: rgba(15,18,16,0.32);
    display: none; align-items: center; justify-content: center; padding: 18px; }
  #vdlg-back.open { display: flex; }
  .vdlg { position: relative; width: 100%; max-width: 400px; background: var(--bg); border-radius: 24px; padding: 34px 30px 26px;
    box-shadow: 0 24px 70px rgba(0,0,0,0.28); display: flex; flex-direction: column; align-items: center; animation: pop-in 0.18s ease-out; }
  .vdlg .vx { position: absolute; top: 14px; right: 14px; width: 32px; height: 32px; border: none; background: none; border-radius: 8px;
    color: var(--text-main); cursor: pointer; font-size: 20px; line-height: 1; }
  .vdlg .vx:hover { background: var(--elevated); }
  .vdlg h2 { font-size: 26px; margin: 22px 0 18px; }
  .vdlg .vrow { display: flex; align-items: flex-start; text-align: left; width: 100%; margin-bottom: 16px; font-size: 15px; line-height: 1.45; }
  .vdlg .vrow svg { flex: none; margin: 2px 14px 0 0; color: var(--text-muted); }
  .vbtn { width: 100%; border: none; border-radius: 999px; background: #121412; color: #fff; font: inherit; font-size: 15px;
    font-weight: 600; padding: 13px; cursor: pointer; margin-top: 10px; }
  body.theme-dark .vbtn { background: #EDEFEA; color: #121412; }
  .vbtn:hover { opacity: 0.9; }
  /* carousel */
  .vcar { display: flex; flex-direction: column; align-items: center; width: 100%; }
  .vcar .vname { font-size: 22px; font-weight: 700; margin-top: 18px; }
  .vcar .vnav { display: flex; align-items: center; justify-content: space-between; width: 100%; max-width: 300px; margin-top: 4px; }
  .vcar .vnav button { border: none; background: none; color: var(--text-muted); font-size: 26px; cursor: pointer; width: 34px; height: 34px; border-radius: 8px; }
  .vcar .vnav button:hover { background: var(--elevated); color: var(--text-main); }
  .vcar .vdesc { color: var(--text-muted); font-size: 14.5px; text-align: center; flex: 1; }
  .vcar .vdots { display: flex; margin: 14px 0 6px; }
  .vcar .vdots i { width: 7px; height: 7px; border-radius: 50%; background: var(--border); margin: 0 5px; cursor: pointer; }
  .vcar .vdots i.on { background: var(--text-main); }

  /* ---------- the conversation screen ---------- */
  #voice-ui { position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 65; background: var(--bg); display: none;
    flex-direction: column; align-items: center; justify-content: center; padding: 24px; }
  #voice-ui.open { display: flex; animation: fade-in 0.2s ease-out; }
  #voice-ui .vstage { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; width: 100%; }
  #voice-ui .vstate { margin-top: 30px; font-size: 16px; color: var(--text-muted); min-height: 22px; }
  #voice-ui .vcap { margin-top: 18px; max-width: 560px; text-align: center; min-height: 66px; }
  #voice-ui .vcap .you { color: var(--text-muted); font-size: 14.5px; }
  #voice-ui .vcap .gink { color: var(--text-main); font-size: 16px; margin-top: 8px; line-height: 1.45;
    max-height: 4.4em; overflow: hidden; }
  #voice-ui .vctl { display: flex; align-items: center; justify-content: center; padding-bottom: 18px; }
  #voice-ui .vctl button { width: 58px; height: 58px; border-radius: 50%; border: none; margin: 0 14px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; background: var(--elevated); color: var(--text-main); }
  #voice-ui .vctl button:hover { filter: brightness(0.96); }
  #voice-ui .vctl #v-mute.on { background: #FCE4E2; color: #C42B1C; }
  #voice-ui .vctl #v-end { background: #121412; color: #fff; }
  body.theme-dark #voice-ui .vctl #v-end { background: #EDEFEA; color: #121412; }
  #voice-ui .vhint { font-size: 12px; color: var(--text-muted); margin-top: 6px; text-align: center; }
"""

HTML = r"""
  <div id="vdlg-back"><div class="vdlg" id="vdlg"></div></div>
  <div id="voice-ui" role="dialog" aria-label="Voice conversation">
    <div class="vstage">
      <div class="vorb" id="v-orb" style="width:220px;height:220px"></div>
      <div class="vstate" id="v-state">Connecting…</div>
      <div class="vcap"><div class="you" id="v-you"></div><div class="gink" id="v-gink"></div></div>
    </div>
    <div>
      <div class="vctl">
        <button id="v-mute" title="Mute (Space)" aria-label="Mute">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/><path class="slash" d="M4 4l16 16" style="display:none"/></svg>
        </button>
        <button id="v-end" title="End (Esc)" aria-label="End voice conversation">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
        </button>
      </div>
      <div class="vhint">Space to mute · Esc to end</div>
    </div>
  </div>
"""

JS = r"""
  // ======================= voice conversation =======================
  // keyboard preferences (Settings -> Keyboard); Python sends them with setKeyboardPrefs()
  var KB = {send_mod: false, single_keys: true};
  function setKeyboardPrefs(p) { for (var k in p) KB[k] = p[k]; }
  var VC = {intro_seen: false, voice: '', voices: [], open: false, muted: false, pick: 0};
  function setVoiceConfig(cfg) { for (var k in cfg) VC[k] = cfg[k]; if (S && S.open) renderSettings(); }
  function voiceIndex(key) { for (var i = 0; i < VC.voices.length; i++) if (VC.voices[i].key === key) return i; return 0; }
  function paintOrb(el, v) {
    if (!el || !v) return;
    el.style.setProperty('--c1', v.colors[0]); el.style.setProperty('--c2', v.colors[1]); el.style.setProperty('--c3', v.colors[2]);
  }
  // a carousel inside `host`; onPick(key) when the voice changes
  function voiceCarousel(host, startKey, onPick, size) {
    var idx = voiceIndex(startKey);
    function draw() {
      var v = VC.voices[idx] || {name: '', desc: '', colors: ['#7B61FF', '#C9C2FF', '#EEF0FF']};
      host.innerHTML = '<div class="vcar"><div class="vorb" style="width:' + size + 'px;height:' + size + 'px"></div>' +
        '<div class="vname"></div><div class="vnav"><button data-v="-1" aria-label="Previous voice">\u2039</button><div class="vdesc"></div>' +
        '<button data-v="1" aria-label="Next voice">\u203a</button></div><div class="vdots">' +
        VC.voices.map(function (_, i) { return '<i data-i="' + i + '" class="' + (i === idx ? 'on' : '') + '"></i>'; }).join('') + '</div></div>';
      paintOrb(host.querySelector('.vorb'), v);
      host.querySelector('.vname').textContent = v.name; host.querySelector('.vdesc').textContent = v.desc;
    }
    host.onclick = function (e) {
      var b = e.target.closest('[data-v]'), d = e.target.closest('[data-i]');
      if (!b && !d) return;
      e.stopPropagation();
      var n = VC.voices.length;
      idx = b ? (idx + (+b.getAttribute('data-v')) + n) % n : +d.getAttribute('data-i');
      draw(); onPick(VC.voices[idx].key);
    };
    draw();
    return function () { return VC.voices[idx] ? VC.voices[idx].key : startKey; };
  }

  function openVoiceDialog(html) { var d = document.getElementById('vdlg'); d.innerHTML = html; document.getElementById('vdlg-back').classList.add('open'); return d; }
  function closeVoiceDialog() { document.getElementById('vdlg-back').classList.remove('open'); document.getElementById('vdlg').innerHTML = ''; }

  function showVoiceIntro() {
    var d = openVoiceDialog('<button class="vx" aria-label="Close">\u00d7</button><div class="vorb" style="width:110px;height:110px"></div><h2>Meet Voice</h2>' +
      '<div class="vrow"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/></svg>' +
      '<span>Say what\u2019s on your mind. Gink listens, answers out loud, and keeps the conversation going.</span></div>' +
      '<div class="vrow"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.8" r=".6"/></svg>' +
      '<span>To understand you, your speech is sent to Google\u2019s speech service and turned into text. The conversation is saved like any chat \u2014 you can delete it at any time.</span></div>' +
      '<button class="vbtn" id="v-continue">Continue</button>');
    paintOrb(d.querySelector('.vorb'), VC.voices[voiceIndex(VC.voice)]);
    d.querySelector('.vx').onclick = closeVoiceDialog;
    d.querySelector('#v-continue').onclick = function () { VC.intro_seen = true; ginkEmit('voice_intro_seen'); showVoicePicker(); };
  }
  function showVoicePicker() {
    var d = openVoiceDialog('<button class="vx" aria-label="Close">\u00d7</button><div id="v-car" style="width:100%"></div><button class="vbtn" id="v-go">Start Voice</button>');
    var current = voiceCarousel(d.querySelector('#v-car'), VC.voice, function (key) { ginkEmit('voice_preview', {key: key}); }, 150);
    d.querySelector('.vx').onclick = function () { ginkEmit('voice_preview_stop'); closeVoiceDialog(); };
    d.querySelector('#v-go').onclick = function () { var k = current(); closeVoiceDialog(); startVoice(k); };
  }
  function startVoice(key) {
    VC.voice = key || VC.voice; VC.open = true; VC.muted = false;
    paintOrb(document.getElementById('v-orb'), VC.voices[voiceIndex(VC.voice)]);
    document.getElementById('v-you').textContent = ''; document.getElementById('v-gink').textContent = '';
    setMuteButton(false); voiceUiState('connecting');
    document.getElementById('voice-ui').classList.add('open');
    ginkEmit('voice_start', {voice: VC.voice});
  }
  function endVoice() {
    if (!VC.open) return;
    VC.open = false; document.getElementById('voice-ui').classList.remove('open'); ginkEmit('voice_end');
  }
  function setMuteButton(on) {
    var b = document.getElementById('v-mute'); b.classList.toggle('on', on);
    b.querySelector('.slash').style.display = on ? '' : 'none'; b.title = on ? 'Unmute (Space)' : 'Mute (Space)';
  }
  var V_LABELS = {connecting: 'Connecting\u2026', listening: 'Listening\u2026', thinking: 'Thinking\u2026', speaking: '', muted: 'Muted \u2014 tap the mic to talk', error: ''};
  function voiceUiState(state, text) {
    var orb = document.getElementById('v-orb'); if (!orb) return;
    if (VC.muted && state === 'listening') state = 'muted';
    orb.className = 'vorb ' + state; if (state !== 'speaking') orb.style.transform = '';
    document.getElementById('v-state').textContent = text || V_LABELS[state] || '';
  }
  function voiceUiCaption(you, gink) {
    if (you != null) document.getElementById('v-you').textContent = you ? '\u201c' + you + '\u201d' : '';
    if (gink != null) document.getElementById('v-gink').textContent = gink || '';
  }
  function voiceUiLevel(x) {
    var orb = document.getElementById('v-orb');
    if (orb && orb.classList.contains('speaking')) orb.style.transform = 'scale(' + (1 + Math.min(1, Math.max(0, x)) * 0.09) + ')';
  }
  document.addEventListener('DOMContentLoaded', function () {
    document.getElementById('v-end').addEventListener('click', endVoice);
    document.getElementById('v-mute').addEventListener('click', function () {
      VC.muted = !VC.muted; setMuteButton(VC.muted); ginkEmit('voice_mute', {muted: VC.muted});
      voiceUiState(VC.muted ? 'muted' : 'listening');
    });
    document.getElementById('vdlg-back').addEventListener('click', function (e) { if (e.target.id === 'vdlg-back') { ginkEmit('voice_preview_stop'); closeVoiceDialog(); } });
    document.addEventListener('keydown', function (e) {
      if (!VC.open) return;
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); endVoice(); }
      else if (e.key === ' ' && KB.single_keys) { e.preventDefault(); document.getElementById('v-mute').click(); }
    }, true);
  });
  // the composer's waveform button
  function voiceButton() {
    if (VC.open) return;
    if (!VC.intro_seen) showVoiceIntro(); else startVoice(VC.voice);
  }
"""


def inject(page: str) -> str:
    i = page.index("</style>")
    page = page[:i] + CSS + page[i:]
    page = page.replace("<script>", HTML + "\n<script>", 1)
    i = page.rindex("</script>")
    return page[:i] + JS + page[i:]
