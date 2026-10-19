"""
Login screen -- one HTML page (inside a Toga WebView) with a soft,
"neumorphic" card in Gink's colours:

  * Log in with email + password (show/hide, Remember me, Forgot password?)
  * Create account (name, email, password with strength meter, confirm,
    terms) -> 6-digit email verification
  * Forgot password -> code -> new password
  * "Email me a sign-in code" (the original passwordless login)
  * Continue with Google / Apple / Microsoft / GitHub / SSO -- opens your
    browser, then Gink signs you in automatically when you finish there.
    Buttons for providers the server hasn't been set up for are greyed
    out and say so (see deploy/README.md for the keys each one needs).

The server address isn't shown on this screen any more. It's in
Settings -> Login server, and here it's a hidden option: tap the logo 5
times (needed on a phone that hasn't been pointed at a server yet).

Like the chat page, the page can't call Python directly (Toga's WebView
has no JS->Python bridge), so it queues events and Python polls them.
"""

import asyncio
import json
import secrets

import toga
from toga.style import Pack
from toga.style.pack import COLUMN

from .branding import LOGO_SPINNER_DATA_URI
from .theme import css_vars
from ..services import server_config
from ..services.api_client import ApiClient, ApiError, TwoFactorRequired
from ..services.paths import data_dir

SESSION_FILE = "session.json"


def _session_path(app: toga.App):
    return data_dir(app) / SESSION_FILE


def _save_session(app: toga.App, token: str, email: str):
    with open(_session_path(app), "w") as f:
        json.dump({"token": token, "email": email}, f)


def load_saved_session(app: toga.App):
    path = _session_path(app)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if data.get("token") and data.get("email"):
            return data
    except Exception:
        pass
    return None


def clear_saved_session(app: toga.App):
    """For a "Log out" action -- nothing in the app could actually clear
    a stored session before this existed."""
    path = _session_path(app)
    if path.exists():
        path.unlink(missing_ok=True)



_LOGIN_HTML = r"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root { __THEME__ --soft: #EDF0E9; --soft-dark: #D3D9CC; --soft-light: #FFFFFF; }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; }
  body {
    font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; color: var(--text-main);
    background: var(--soft); display: flex; align-items: center; justify-content: center;
    overflow: hidden; -webkit-font-smoothing: antialiased;
  }
  /* floating soft bubbles in the background */
  .bubble {
    position: fixed; border-radius: 50%; background: var(--soft); z-index: 0;
    box-shadow: 14px 14px 30px var(--soft-dark), -14px -14px 30px var(--soft-light);
    animation: float 14s ease-in-out infinite;
  }
  .b1 { width: 170px; height: 170px; top: 8%; left: 7%; }
  .b2 { width: 90px; height: 90px; top: 64%; left: 14%; animation-delay: -4s; animation-duration: 11s; }
  .b3 { width: 240px; height: 240px; bottom: -70px; right: 6%; animation-delay: -7s; animation-duration: 17s; }
  .b4 { width: 60px; height: 60px; top: 14%; right: 18%; animation-delay: -2s; animation-duration: 9s; }
  .b5 { width: 120px; height: 120px; top: 38%; right: 4%; animation-delay: -9s; }
  .glow {
    position: fixed; width: 620px; height: 620px; border-radius: 50%; z-index: 0;
    background: radial-gradient(circle, rgba(168,240,60,0.22), rgba(168,240,60,0) 65%);
    animation: drift 16s ease-in-out infinite alternate;
  }
  @keyframes float { 0%,100% { transform: translate(0,0); } 50% { transform: translate(12px,-22px); } }
  @keyframes drift { from { transform: translate(-30%, -20%); } to { transform: translate(25%, 18%); } }

  .card {
    position: relative; z-index: 2; width: 392px; max-width: calc(100vw - 32px);
    max-height: calc(100vh - 32px); overflow-y: auto; scrollbar-width: none;
    background: var(--soft); border-radius: 34px; padding: 30px 30px 24px;
    box-shadow: 22px 22px 48px var(--soft-dark), -22px -22px 48px var(--soft-light);
    animation: card-in 0.6s cubic-bezier(0.22, 1, 0.36, 1);
  }
  .card::-webkit-scrollbar { display: none; }
  @keyframes card-in { from { opacity: 0; transform: translateY(18px) scale(0.98); } to { opacity: 1; transform: none; } }
  .card.shake { animation: shake 0.42s; }
  @keyframes shake { 20%,60% { transform: translateX(-7px); } 40%,80% { transform: translateX(7px); } }

  .badge {
    width: 74px; height: 74px; border-radius: 50%; margin: 0 auto 14px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; background: var(--soft);
    box-shadow: 8px 8px 18px var(--soft-dark), -8px -8px 18px var(--soft-light);
  }
  .badge img { width: 46px; height: 46px; transition: transform 0.6s; }
  .badge:active img { transform: rotate(60deg); }
  body.busy .badge img, .spin img { animation: spin 1.4s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  .view { display: none; }
  .view.active { display: block; animation: view-in 0.38s cubic-bezier(0.22, 1, 0.36, 1); }
  @keyframes view-in { from { opacity: 0; transform: translateX(14px); } to { opacity: 1; transform: none; } }
  h1 { margin: 0; text-align: center; font-size: 24px; font-weight: 700; letter-spacing: -0.01em; }
  .sub { margin: 6px 0 20px; text-align: center; color: var(--text-muted); font-size: 13.5px; line-height: 1.45; }
  .sub b { color: var(--text-main); }

  .field { position: relative; margin-bottom: 14px; }
  .field input {
    width: 100%; border: none; outline: none; font: inherit; font-size: 15px; color: var(--text-main);
    background: var(--soft); border-radius: 14px; padding: 14px 16px;
    box-shadow: inset 5px 5px 10px var(--soft-dark), inset -5px -5px 10px var(--soft-light);
    transition: box-shadow 0.2s;
  }
  .field input:focus { box-shadow: inset 5px 5px 10px var(--soft-dark), inset -5px -5px 10px var(--soft-light), 0 0 0 2px var(--accent); }
  .field input::placeholder { color: #98A094; }
  .field.pw input { padding-right: 46px; }
  .eye {
    position: absolute; right: 10px; top: 50%; transform: translateY(-50%); border: none; background: none;
    color: var(--text-muted); cursor: pointer; width: 32px; height: 32px; padding: 0;
    display: flex; align-items: center; justify-content: center; border-radius: 8px;
  }
  .eye svg { width: 19px; height: 19px; }
  .eye:hover { color: var(--text-main); }

  .meter { height: 5px; border-radius: 3px; background: var(--soft-dark); margin: -6px 2px 6px; overflow: hidden; }
  .meter i { display: block; height: 100%; width: 0; border-radius: 3px; transition: width 0.3s, background 0.3s; }
  .meter-label { font-size: 11.5px; color: var(--text-muted); margin: 0 2px 12px; min-height: 14px; }

  .row-between { display: flex; align-items: center; justify-content: space-between; margin: 2px 2px 18px; font-size: 13px; }
  .check { display: flex; align-items: center; cursor: pointer; color: var(--text-muted); user-select: none; }
  .check input { display: none; }
  .check .box {
    width: 18px; height: 18px; border-radius: 6px; margin-right: 8px; background: var(--soft); flex: none;
    box-shadow: inset 2px 2px 4px var(--soft-dark), inset -2px -2px 4px var(--soft-light);
    display: flex; align-items: center; justify-content: center; color: #fff; font-size: 12px; transition: background 0.2s;
  }
  .check input:checked + .box { background: var(--accent); box-shadow: none; }
  .check input:checked + .box::after { content: "\2713"; }
  .check a, .link { color: var(--accent); text-decoration: none; cursor: pointer; font-weight: 500; }
  .link:hover, .check a:hover { text-decoration: underline; }

  .btn {
    width: 100%; border: none; cursor: pointer; font: inherit; font-size: 15.5px; font-weight: 600;
    color: #fff; border-radius: 14px; padding: 14px; position: relative; overflow: hidden;
    background: linear-gradient(135deg, #5DA312, var(--accent));
    box-shadow: 6px 6px 14px rgba(63,130,18,0.30), -6px -6px 14px var(--soft-light);
    transition: transform 0.12s, filter 0.2s;
  }
  .btn:hover { filter: brightness(1.06); }
  .btn:active { transform: scale(0.985); }
  .btn:disabled { filter: grayscale(0.4) brightness(0.95); cursor: default; }
  .btn .dots { display: none; }
  .btn.loading .label { visibility: hidden; }
  .btn.loading .dots { display: flex; position: absolute; top: 0; right: 0; bottom: 0; left: 0; align-items: center; justify-content: center; }
  .dots span { width: 7px; height: 7px; margin: 0 3px; border-radius: 50%; background: #fff; animation: dot 1s infinite; }
  .dots span:nth-child(2) { animation-delay: 0.15s; } .dots span:nth-child(3) { animation-delay: 0.3s; }
  @keyframes dot { 0%,80%,100% { opacity: 0.3; transform: scale(0.8); } 40% { opacity: 1; transform: scale(1); } }
  .btn.ghost {
    color: var(--text-main); background: var(--soft); font-weight: 500;
    box-shadow: 6px 6px 14px var(--soft-dark), -6px -6px 14px var(--soft-light);
  }

  .divider { display: flex; align-items: center; margin: 20px 0 14px; color: var(--text-muted); font-size: 12px; }
  .divider::before, .divider::after { content: ""; flex: 1; height: 1px; background: var(--soft-dark); }
  .divider span { padding: 0 10px; }
  .socials { display: flex; justify-content: center; }
  .soc {
    width: 50px; height: 50px; border-radius: 15px; border: none; cursor: pointer; margin: 0 6px;
    background: var(--soft); display: flex; align-items: center; justify-content: center; position: relative;
    box-shadow: 5px 5px 12px var(--soft-dark), -5px -5px 12px var(--soft-light); transition: transform 0.15s, box-shadow 0.15s;
  }
  .soc svg { width: 22px; height: 22px; }
  .soc:hover { transform: translateY(-2px); }
  .soc:active { box-shadow: inset 4px 4px 8px var(--soft-dark), inset -4px -4px 8px var(--soft-light); transform: none; }
  .soc.off { opacity: 0.38; }
  .soc .tip {
    position: absolute; bottom: 58px; left: 50%; transform: translateX(-50%); white-space: nowrap;
    background: var(--text-main); color: #fff; font-size: 11.5px; padding: 5px 8px; border-radius: 7px;
    opacity: 0; pointer-events: none; transition: opacity 0.15s;
  }
  .soc:hover .tip { opacity: 1; }
  .alt { text-align: center; margin-top: 14px; font-size: 13px; }

  .foot { display: flex; align-items: center; justify-content: center; margin-top: 18px; font-size: 13px; color: var(--text-muted); }
  .plus {
    width: 40px; height: 40px; margin-left: 10px; border-radius: 50%; border: none; cursor: pointer;
    background: var(--soft); color: var(--accent); font-size: 22px; line-height: 1;
    box-shadow: 5px 5px 12px var(--soft-dark), -5px -5px 12px var(--soft-light);
    display: flex; align-items: center; justify-content: center; transition: transform 0.2s;
  }
  .plus:hover { transform: rotate(90deg); }

  .codes { display: flex; justify-content: space-between; margin: 4px 0 16px; }
  .codes input {
    width: 46px; height: 54px; text-align: center; font: inherit; font-size: 22px; font-weight: 600;
    border: none; outline: none; border-radius: 13px; background: var(--soft); color: var(--text-main);
    box-shadow: inset 4px 4px 9px var(--soft-dark), inset -4px -4px 9px var(--soft-light); caret-color: var(--accent);
  }
  .codes input:focus { box-shadow: inset 4px 4px 9px var(--soft-dark), inset -4px -4px 9px var(--soft-light), 0 0 0 2px var(--accent); }
  .resend { text-align: center; margin-top: 14px; font-size: 13px; color: var(--text-muted); }

  .msg { min-height: 18px; margin: -4px 2px 12px; font-size: 13px; text-align: center; }
  .msg.err { color: var(--danger); }
  .msg.ok { color: var(--accent); }
  .back { display: inline-flex; align-items: center; color: var(--text-muted); font-size: 13px; cursor: pointer; margin-bottom: 6px; }
  .back:hover { color: var(--text-main); }
  .wait { text-align: center; }
  .wait .spin { width: 64px; height: 64px; margin: 6px auto 14px; }
  .wait .spin img { width: 64px; height: 64px; }
  @media (max-width: 420px) { .card { padding: 24px 20px 20px; border-radius: 28px; } .codes input { width: 40px; height: 50px; } .soc { margin: 0 4px; } }
  @media (prefers-reduced-motion: reduce) { .bubble, .glow { animation: none; } }
</style></head>
<body>
  <div class="glow"></div>
  <div class="bubble b1"></div><div class="bubble b2"></div><div class="bubble b3"></div>
  <div class="bubble b4"></div><div class="bubble b5"></div>

  <div class="card" id="card">
    <div class="badge" id="badge" title="Gink"><img src="__LOGO__" alt="Gink"></div>

    <!-- LOG IN -->
    <div class="view" id="v-login">
      <h1>Welcome back</h1>
      <p class="sub">Log in to continue your journey with Gink</p>
      <div class="field"><input id="l-email" type="email" placeholder="Email address" autocomplete="username"></div>
      <div class="field pw"><input id="l-pass" type="password" placeholder="Password" autocomplete="current-password">
        <button class="eye" data-eye="l-pass" title="Show password">__EYE__</button></div>
      <div class="row-between">
        <label class="check"><input type="checkbox" id="l-remember" checked><span class="box"></span>Remember me</label>
        <a class="link" data-go="forgot">Forgot password?</a>
      </div>
      <div class="msg" id="m-login"></div>
      <button class="btn" id="b-login" data-primary><span class="label">Log in</span><span class="dots"><span></span><span></span><span></span></span></button>
      <div class="divider"><span>or continue with</span></div>
      <div class="socials">__SOCIALS__</div>
      <div class="alt"><a class="link" data-go="otp">Email me a sign-in code instead</a></div>
      <div class="foot">Don't have an account?<button class="plus" data-go="signup" title="Create account">+</button></div>
    </div>

    <!-- SIGN UP -->
    <div class="view" id="v-signup">
      <h1>Create your account</h1>
      <p class="sub">It takes less than a minute</p>
      <div class="field"><input id="s-name" placeholder="Your name" autocomplete="name"></div>
      <div class="field"><input id="s-email" type="email" placeholder="Email address" autocomplete="email"></div>
      <div class="field pw"><input id="s-pass" type="password" placeholder="Password (8+ characters)" autocomplete="new-password">
        <button class="eye" data-eye="s-pass" title="Show password">__EYE__</button></div>
      <div class="meter"><i id="meter"></i></div><div class="meter-label" id="meter-label"></div>
      <div class="field pw"><input id="s-pass2" type="password" placeholder="Confirm password" autocomplete="new-password"></div>
      <div class="row-between">
        <label class="check"><input type="checkbox" id="s-terms"><span class="box"></span>I agree to the Terms &amp; Privacy Policy</label>
      </div>
      <div class="msg" id="m-signup"></div>
      <button class="btn" id="b-signup" data-primary><span class="label">Create account</span><span class="dots"><span></span><span></span><span></span></span></button>
      <div class="divider"><span>or sign up with</span></div>
      <div class="socials">__SOCIALS__</div>
      <div class="foot">Already have an account? <a class="link" data-go="login" style="margin-left:6px">Log in</a></div>
    </div>

    <!-- VERIFY CODE (sign-up or email-code login) -->
    <div class="view" id="v-verify">
      <a class="back" data-go="back">&larr;&nbsp; Back</a>
      <h1>Check your email</h1>
      <p class="sub">We sent a 6-digit code to <b id="v-email"></b></p>
      <div class="codes" id="codes-verify"></div>
      <div class="msg" id="m-verify"></div>
      <button class="btn" id="b-verify" data-primary><span class="label">Verify</span><span class="dots"><span></span><span></span><span></span></span></button>
      <div class="resend" id="resend-verify"></div>
    </div>

    <!-- TWO-STEP SIGN-IN -->
    <div class="view" id="v-twofa">
      <a class="back" data-go="login">&larr;&nbsp; Back to log in</a>
      <h1>Two-step verification</h1>
      <p class="sub" id="tf-sub">Enter the 6-digit code from your authenticator app</p>
      <div class="codes" id="codes-twofa"></div>
      <div class="field" id="tf-recovery-wrap" hidden><input id="tf-recovery" type="text" autocomplete="one-time-code" placeholder="Recovery code, e.g. a1b2-c3d4" aria-label="Recovery code"></div>
      <div class="msg" id="m-twofa"></div>
      <button class="btn" id="b-twofa" data-primary><span class="label">Continue</span><span class="dots"><span></span><span></span><span></span></span></button>
      <a class="resend" id="tf-switch" href="#" role="button">Use a recovery code instead</a>
    </div>

    <!-- FORGOT -->
    <div class="view" id="v-forgot">
      <a class="back" data-go="login">&larr;&nbsp; Back to log in</a>
      <h1>Reset your password</h1>
      <p class="sub">Enter your email and we'll send you a reset code</p>
      <div class="field"><input id="f-email" type="email" placeholder="Email address" autocomplete="email"></div>
      <div class="msg" id="m-forgot"></div>
      <button class="btn" id="b-forgot" data-primary><span class="label">Send reset code</span><span class="dots"><span></span><span></span><span></span></span></button>
    </div>

    <!-- RESET -->
    <div class="view" id="v-reset">
      <a class="back" data-go="forgot">&larr;&nbsp; Back</a>
      <h1>Choose a new password</h1>
      <p class="sub">Enter the code we sent to <b id="r-email"></b></p>
      <div class="codes" id="codes-reset"></div>
      <div class="field pw"><input id="r-pass" type="password" placeholder="New password" autocomplete="new-password">
        <button class="eye" data-eye="r-pass" title="Show password">__EYE__</button></div>
      <div class="field pw"><input id="r-pass2" type="password" placeholder="Confirm new password" autocomplete="new-password"></div>
      <div class="msg" id="m-reset"></div>
      <button class="btn" id="b-reset" data-primary><span class="label">Reset &amp; log in</span><span class="dots"><span></span><span></span><span></span></span></button>
    </div>

    <!-- EMAIL CODE LOGIN -->
    <div class="view" id="v-otp">
      <a class="back" data-go="login">&larr;&nbsp; Back to log in</a>
      <h1>Sign in with a code</h1>
      <p class="sub">No password needed &mdash; we'll email you a one-time code</p>
      <div class="field"><input id="o-email" type="email" placeholder="Email address" autocomplete="email"></div>
      <div class="row-between">
        <label class="check"><input type="checkbox" id="o-remember" checked><span class="box"></span>Remember me</label>
      </div>
      <div class="msg" id="m-otp"></div>
      <button class="btn" id="b-otp" data-primary><span class="label">Send code</span><span class="dots"><span></span><span></span><span></span></span></button>
    </div>

    <!-- WAITING FOR BROWSER SIGN-IN -->
    <div class="view" id="v-oauth">
      <div class="wait">
        <div class="spin"><img src="__LOGO__" alt=""></div>
        <h1 id="oauth-title">Continue in your browser</h1>
        <p class="sub" id="oauth-sub">Finish signing in there &mdash; Gink will log you in automatically.</p>
        <div class="msg" id="m-oauth"></div>
        <button class="btn ghost" id="b-oauth-again">Open the sign-in page again</button>
        <div class="alt"><a class="link" id="b-oauth-cancel">Cancel</a></div>
      </div>
    </div>

    <!-- HIDDEN: SERVER ADDRESS (tap the logo 5 times) -->
    <div class="view" id="v-server">
      <a class="back" data-go="login">&larr;&nbsp; Back to log in</a>
      <h1>Login server</h1>
      <p class="sub">Only needed on a phone: your hosted server or your computer's Wi-Fi address (http://192.168.1.20:8001)</p>
      <div class="field"><input id="srv" placeholder="Server address" autocomplete="off"></div>
      <div class="msg" id="m-server"></div>
      <button class="btn" id="b-server" data-primary><span class="label">Save &amp; test</span><span class="dots"><span></span><span></span><span></span></span></button>
    </div>
  </div>

<script>
  // Fallbacks for older web engines (some older Android phones)
  if (window.NodeList && !NodeList.prototype.forEach) NodeList.prototype.forEach = Array.prototype.forEach;
  if (window.Element && !Element.prototype.matches) Element.prototype.matches = Element.prototype.webkitMatchesSelector || Element.prototype.msMatchesSelector;
  if (window.Element && !Element.prototype.closest) Element.prototype.closest = function (sel) {
    var el = this; while (el && el.nodeType === 1) { if (el.matches(sel)) return el; el = el.parentElement; } return null;
  };
  var ginkEvents = [];
  function ginkEmit(type, value) { ginkEvents.push({type: type, value: value === undefined ? null : value}); }
  function ginkTake() { var out = JSON.stringify(ginkEvents); ginkEvents = []; return out; }
  function $(id) { return document.getElementById(id); }

  var current = 'login', history_ = [], resendTimer = null;
  function show(view, data) {
    data = data || {};
    if (view !== current) history_.push(current);
    document.querySelectorAll('.view').forEach(function (v) { v.classList.remove('active'); });
    $('v-' + view).classList.add('active'); current = view;
    document.querySelectorAll('.msg').forEach(function (m) { m.textContent = ''; m.className = 'msg'; });
    if (data.email) { ['v-email', 'r-email'].forEach(function (id) { $(id).textContent = data.email; }); }
    if (data.title) $('oauth-title').textContent = data.title;
    if (data.info) info(data.info);
    if (view === 'verify' || view === 'reset') { buildCodes(view === 'verify' ? 'codes-verify' : 'codes-reset'); startResend(); }
    if (view === 'twofa') { buildCodes('codes-twofa'); setRecovery(false); }
    setTimeout(function () { var f = $('v-' + view).querySelector('input'); if (f) f.focus(); }, 60);
  }
  var recoveryMode = false;
  function setRecovery(on) {
    recoveryMode = on;
    $('codes-twofa').hidden = on; $('tf-recovery-wrap').hidden = !on;
    $('tf-sub').textContent = on ? 'Enter one of the recovery codes you saved when you turned on two-step verification'
                                 : 'Enter the 6-digit code from your authenticator app';
    $('tf-switch').textContent = on ? 'Use my authenticator app instead' : 'Use a recovery code instead';
    setTimeout(function () { (on ? $('tf-recovery') : $('codes-twofa').querySelector('input')).focus(); }, 30);
  }
  document.addEventListener('click', function (e) {
    if (e.target && e.target.id === 'tf-switch') { e.preventDefault(); setRecovery(!recoveryMode); }
  });
  function msgEl() { return $('m-' + current); }
  function error(text) {
    var m = msgEl(); if (m) { m.textContent = text; m.className = 'msg err'; }
    var c = $('card'); c.classList.remove('shake'); void c.offsetWidth; c.classList.add('shake');
    busy(false);
  }
  function info(text) { var m = msgEl(); if (m) { m.textContent = text; m.className = 'msg ok'; } }
  function busy(on) {
    document.body.classList.toggle('busy', on);
    document.querySelectorAll('.btn[data-primary]').forEach(function (b) { b.classList.toggle('loading', on); b.disabled = on; });
  }
  function setProviders(map) {
    document.querySelectorAll('.soc').forEach(function (b) {
      var p = map[b.getAttribute('data-provider')];
      var on = !!(p && p.enabled);
      b.classList.toggle('off', !on);
      if (p && p.label) b.setAttribute('data-label', p.label);
      b.querySelector('.tip').textContent = on ? ('Continue with ' + (p.label || '')) : ((p && p.label || b.getAttribute('data-label')) + ' sign-in isn\u2019t set up yet');
    });
  }
  function setServer(url) { $('srv').value = url || ''; }

  // 6 code boxes: auto-advance, backspace, paste a whole code
  function buildCodes(id) {
    var box = $(id); box.innerHTML = '';
    for (var i = 0; i < 6; i++) {
      var inp = document.createElement('input');
      inp.setAttribute('inputmode', 'numeric'); inp.setAttribute('maxlength', '1'); inp.setAttribute('autocomplete', 'one-time-code');
      box.appendChild(inp);
    }
    var ins = box.querySelectorAll('input');
    ins.forEach(function (inp, i) {
      inp.addEventListener('input', function () {
        var digits = inp.value.replace(/\D/g, '');
        if (digits.length > 1) { fillCode(ins, digits); return; }
        inp.value = digits;
        if (digits && i < 5) ins[i + 1].focus();
        if (codeOf(ins).length === 6 && id === 'codes-verify') submit();
      });
      inp.addEventListener('keydown', function (e) { if (e.key === 'Backspace' && !inp.value && i > 0) ins[i - 1].focus(); });
      inp.addEventListener('paste', function (e) {
        var t = (e.clipboardData || window.clipboardData).getData('text'); e.preventDefault(); fillCode(ins, t.replace(/\D/g, ''));
      });
    });
  }
  function fillCode(ins, digits) {
    for (var i = 0; i < 6; i++) ins[i].value = digits.charAt(i) || '';
    ins[Math.min(digits.length, 5)].focus();
  }
  function codeOf(ins) { return Array.prototype.map.call(ins, function (x) { return x.value; }).join(''); }
  function startResend() {
    var el = $(current === 'reset' ? 'm-reset' : 'resend-verify');
    if (current === 'reset') return;
    var left = 30; clearInterval(resendTimer);
    function tick() {
      if (left > 0) { el.innerHTML = 'Didn\u2019t get it? Resend in ' + left + 's'; left--; }
      else { clearInterval(resendTimer); el.innerHTML = 'Didn\u2019t get it? <a class="link" id="do-resend">Resend code</a>'; }
    }
    tick(); resendTimer = setInterval(tick, 1000);
  }

  function strength(p) {
    var s = 0; if (p.length >= 8) s++; if (p.length >= 12) s++;
    if (/[a-z]/.test(p) && /[A-Z]/.test(p)) s++; if (/\d/.test(p)) s++; if (/[^A-Za-z0-9]/.test(p)) s++;
    return Math.min(s, 4);
  }
  function emailOk(e) { return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e); }

  function submit() {
    if (document.body.classList.contains('busy')) return;
    var e, p;
    if (current === 'login') {
      e = $('l-email').value.trim(); p = $('l-pass').value;
      if (!emailOk(e)) return error('Enter a valid email address.');
      if (!p) return error('Enter your password.');
      busy(true); ginkEmit('login', {email: e, password: p, remember: $('l-remember').checked});
    } else if (current === 'signup') {
      var n = $('s-name').value.trim(); e = $('s-email').value.trim(); p = $('s-pass').value;
      if (!n) return error('Tell us your name.');
      if (!emailOk(e)) return error('Enter a valid email address.');
      if (p.length < 8) return error('Use at least 8 characters for your password.');
      if (p !== $('s-pass2').value) return error('The passwords don\u2019t match.');
      if (!$('s-terms').checked) return error('Please accept the Terms & Privacy Policy.');
      busy(true); ginkEmit('signup', {name: n, email: e, password: p, remember: true});
    } else if (current === 'twofa') {
      var tc = recoveryMode ? $('tf-recovery').value.trim() : codeOf($('codes-twofa').querySelectorAll('input'));
      if (!recoveryMode && tc.length !== 6) return error('Enter all 6 digits.');
      if (recoveryMode && tc.replace(/[^a-z0-9]/gi, '').length < 8) return error('Enter one of your recovery codes.');
      busy(true); ginkEmit('twofa', {code: tc});
    } else if (current === 'verify') {
      var c = codeOf($('codes-verify').querySelectorAll('input'));
      if (c.length !== 6) return error('Enter all 6 digits.');
      busy(true); ginkEmit('verify', {code: c});
    } else if (current === 'forgot') {
      e = $('f-email').value.trim(); if (!emailOk(e)) return error('Enter a valid email address.');
      busy(true); ginkEmit('forgot', {email: e});
    } else if (current === 'reset') {
      var rc = codeOf($('codes-reset').querySelectorAll('input')); p = $('r-pass').value;
      if (rc.length !== 6) return error('Enter the 6-digit code.');
      if (p.length < 8) return error('Use at least 8 characters.');
      if (p !== $('r-pass2').value) return error('The passwords don\u2019t match.');
      busy(true); ginkEmit('reset', {code: rc, password: p});
    } else if (current === 'otp') {
      e = $('o-email').value.trim(); if (!emailOk(e)) return error('Enter a valid email address.');
      busy(true); ginkEmit('otp_send', {email: e, remember: $('o-remember').checked});
    } else if (current === 'server') {
      busy(true); ginkEmit('server_save', {url: $('srv').value.trim()});
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    show('login'); history_ = [];
    document.querySelectorAll('[data-primary]').forEach(function (b) { b.addEventListener('click', submit); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); submit(); } });
    document.addEventListener('click', function (e) {
      var go = e.target.closest('[data-go]');
      if (go) {
        e.preventDefault(); var to = go.getAttribute('data-go');
        if (to === 'back') to = history_.pop() || 'login';
        if (to === 'forgot' && $('l-email').value) $('f-email').value = $('l-email').value;
        if (to === 'otp' && $('l-email').value) $('o-email').value = $('l-email').value;
        busy(false); show(to); return;
      }
      var eye = e.target.closest('[data-eye]');
      if (eye) {
        var inp = $(eye.getAttribute('data-eye')); var showing = inp.type === 'text';
        inp.type = showing ? 'password' : 'text'; eye.innerHTML = showing ? EYE : EYE_OFF; return;
      }
      var soc = e.target.closest('.soc');
      if (soc) {
        if (soc.classList.contains('off')) { error(soc.querySelector('.tip').textContent + '.'); return; }
        ginkEmit('oauth', soc.getAttribute('data-provider')); return;
      }
      if (e.target.id === 'do-resend') { ginkEmit('resend'); return; }
    });
    $('s-pass').addEventListener('input', function () {
      var s = strength(this.value), colors = ['#C93B32', '#E0812A', '#D9B526', '#7BBF22', '#3F8212'];
      var names = ['Too weak', 'Weak', 'Okay', 'Strong', 'Very strong'];
      $('meter').style.width = this.value ? ((s + 1) * 20) + '%' : '0'; $('meter').style.background = colors[s];
      $('meter-label').textContent = this.value ? names[s] : '';
    });
    $('b-oauth-again').addEventListener('click', function () { ginkEmit('oauth_again'); });
    $('b-oauth-cancel').addEventListener('click', function () { ginkEmit('oauth_cancel'); show('login'); });
    var taps = 0, tapTimer = null;
    $('badge').addEventListener('click', function () {
      taps++; clearTimeout(tapTimer); tapTimer = setTimeout(function () { taps = 0; }, 1500);
      if (taps >= 5) { taps = 0; ginkEmit('server_open'); show('server'); }
    });
    ginkEmit('ready');
  });
  var EYE = '__EYE_JS__', EYE_OFF = '__EYE_OFF_JS__';
</script>
</body></html>"""

_EYE = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>')
_EYE_OFF = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
            'stroke-linejoin="round"><path d="M3 3l18 18M10.6 5.1A10.4 10.4 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.1 3.9'
            'M6.6 6.6A17 17 0 0 0 2 12s3.5 7 10 7a9.7 9.7 0 0 0 5.4-1.6M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>')

_SOCIAL_ICONS = {
    "google": ('<svg viewBox="0 0 48 48"><path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z"/>'
               '<path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z"/>'
               '<path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"/>'
               '<path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z"/></svg>'),
    "apple": ('<svg viewBox="0 0 24 24"><path fill="#111" d="M16.4 12.6c0-2.6 2.1-3.8 2.2-3.9-1.2-1.8-3.1-2-3.7-2-1.6-.2-3.1.9-3.9.9-.8 0-2-.9-3.4-.9-1.7 0-3.3 1-4.2 2.6-1.8 3.1-.5 7.7 1.3 10.2.9 1.2 1.9 2.6 3.2 2.6 1.3-.1 1.8-.8 3.3-.8s2 .8 3.4.8c1.4 0 2.3-1.3 3.1-2.5 1-1.4 1.4-2.8 1.4-2.9 0 0-2.6-1-2.7-4.1zM13.9 5.1c.7-.9 1.2-2 1.1-3.2-1 0-2.3.7-3 1.6-.7.8-1.2 2-1.1 3.1 1.1.1 2.3-.6 3-1.5z"/></svg>'),
    "microsoft": ('<svg viewBox="0 0 24 24"><rect x="2" y="2" width="9.5" height="9.5" fill="#F25022"/><rect x="12.5" y="2" width="9.5" height="9.5" fill="#7FBA00"/>'
                  '<rect x="2" y="12.5" width="9.5" height="9.5" fill="#00A4EF"/><rect x="12.5" y="12.5" width="9.5" height="9.5" fill="#FFB900"/></svg>'),
    "github": ('<svg viewBox="0 0 24 24"><path fill="#111" d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A11.5 11.5 0 0 0 23.5 12C23.5 5.7 18.3.5 12 .5z"/></svg>'),
    "sso": ('<svg viewBox="0 0 24 24" fill="none" stroke="#3F8212" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">'
            '<circle cx="8" cy="15" r="4"/><path d="M10.8 12.2 20 3M16 7l3 3M18 5l2 2"/></svg>'),
}
_SOCIAL_LABELS = {"google": "Google", "apple": "Apple", "microsoft": "Microsoft", "github": "GitHub", "sso": "SSO"}


def _login_page_html() -> str:
    socials = "".join(
        f'<button class="soc off" data-provider="{p}" data-label="{_SOCIAL_LABELS[p]}" title="">'
        f'{svg}<span class="tip">{_SOCIAL_LABELS[p]}</span></button>'
        for p, svg in _SOCIAL_ICONS.items()
    )
    return (_LOGIN_HTML.replace("__THEME__", css_vars()).replace("__LOGO__", LOGO_SPINNER_DATA_URI)
            .replace("__SOCIALS__", socials).replace("__EYE_JS__", _EYE.replace("'", "\\'"))
            .replace("__EYE_OFF_JS__", _EYE_OFF.replace("'", "\\'")).replace("__EYE__", _EYE))


def _open_in_browser(app, url: str) -> bool:
    try:
        res = app.task_runner.device.open_url(url)
        if getattr(res, "ok", False):
            return True
    except Exception:
        pass
    try:
        import webbrowser
        return webbrowser.open(url)
    except Exception:
        return False


class LoginController:
    """Runs the login page: polls its events, calls the server, answers."""

    def __init__(self, app: toga.App, on_success):
        self.app = app
        self.on_success = on_success
        self.web_view = toga.WebView(style=Pack(flex=1))
        self.web_view.set_content("https://gink.local/login", _login_page_html())
        self.pending = {"email": "", "mode": "", "remember": True}
        self.oauth = {"state": None, "provider": None}
        self.token = object()
        app._login_screen_token = self.token

    @property
    def api(self) -> ApiClient:
        return ApiClient(self.app.state.base_url)

    async def js(self, script: str):
        try:
            await asyncio.wait_for(self.web_view.evaluate_javascript(script), timeout=3)
        except Exception:
            pass

    async def call(self, fn: str, *args):
        await self.js(f"{fn}({', '.join(json.dumps(a) for a in args)})")

    async def poll(self) -> list:
        try:
            raw = await asyncio.wait_for(self.web_view.evaluate_javascript("ginkTake()"), timeout=2)
            data = json.loads(raw) if isinstance(raw, str) and raw else (raw or [])
            if isinstance(data, str):
                data = json.loads(data)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def alive(self) -> bool:
        return getattr(self.app, "_login_screen_token", None) is self.token

    async def run(self):
        await asyncio.sleep(0.4)
        while self.alive():
            for event in await self.poll():
                asyncio.create_task(self.handle(event))
            await asyncio.sleep(0.15)

    async def ask_second_step(self, need, remember: bool):
        """Two-step sign-in is on: ask for the authenticator code (any sign-in method lands here)."""
        self.pending.update(ticket=need.ticket, twofa_remember=remember)
        self.oauth["state"] = None                       # stops any Google/GitHub polling (the screen stays alive)
        await self.call("busy", False)
        await self.call("show", "twofa", {"email": need.email})

    def finish(self, session, remember: bool):
        self.app.session_token = session.token          # sync uses it even when not remembered
        # Name from Google / GitHub / Microsoft / Apple / SSO or the sign-up form
        # -> Settings -> Account (Full name + what Gink calls you), if still empty.
        if getattr(session, "name", ""):
            try:
                from ..services.profile import ProfileStore, profile_path
                ProfileStore(profile_path(self.app, session.email)).seed_from_signin(session.name)
            except Exception:
                pass                                      # never block signing in
        if remember:
            _save_session(self.app, session.token, session.email)
        self.app._login_screen_token = None          # stop polling
        self.oauth["state"] = None
        self.on_success(session.email)

    async def handle(self, event: dict):
        kind, v = event.get("type"), event.get("value") or {}
        try:
            if kind == "ready":
                await self.call("setServer", server_config.saved_url(self.app) or "")
                await self.call("setProviders", await self.api.providers())
            elif kind == "login":
                session = await self.api.login(v["email"], v["password"])
                self.finish(session, bool(v.get("remember", True)))
            elif kind == "signup":
                await self.api.register(v["name"], v["email"], v["password"])
                self.pending.update(email=v["email"], mode="signup", remember=True,
                                    name=v["name"], password=v["password"])
                await self.call("busy", False)
                await self.call("show", "verify", {"email": v["email"]})
            elif kind == "otp_send":
                await self.api.send_otp(v["email"])
                self.pending.update(email=v["email"], mode="otp", remember=bool(v.get("remember", True)))
                await self.call("busy", False)
                await self.call("show", "verify", {"email": v["email"]})
            elif kind == "verify":
                if self.pending["mode"] == "signup":
                    session = await self.api.verify_register(self.pending["email"], v["code"])
                else:
                    session = await self.api.verify_otp(self.pending["email"], v["code"])
                self.finish(session, self.pending["remember"])
            elif kind == "resend":
                if self.pending["mode"] == "signup":
                    await self.api.register(self.pending.get("name", ""), self.pending["email"],
                                            self.pending.get("password", ""))
                else:
                    await self.api.send_otp(self.pending["email"])
                await self.call("info", "New code sent.")
                await self.js("startResend()")
            elif kind == "forgot":
                await self.api.forgot_password(v["email"])
                self.pending.update(email=v["email"], mode="reset")
                await self.call("busy", False)
                await self.call("show", "reset", {"email": v["email"],
                                                  "info": "If that email has an account, a code is on its way."})
            elif kind == "reset":
                session = await self.api.reset_password(self.pending["email"], v["code"], v["password"])
                self.finish(session, True)
            elif kind == "twofa" and self.pending.get("ticket"):              # the authenticator code
                session = await self.api.verify_2fa(self.pending["ticket"], str(v.get("code", "")))
                self.pending.pop("ticket", None)
                self.finish(session, self.pending.get("twofa_remember", True))
            elif kind == "oauth":
                await self.start_oauth(str(event.get("value")))
            elif kind == "oauth_again" and self.oauth["state"]:
                _open_in_browser(self.app, self.api.oauth_start_url(self.oauth["provider"], self.oauth["state"]))
            elif kind == "oauth_cancel":
                self.oauth["state"] = None
            elif kind == "server_save":
                server_config.save_url(self.app, v.get("url", ""))
                self.app.state.base_url = server_config.resolve_base_url(self.app)
                ok, msg = await server_config.check_server(self.app.state.base_url)
                await self.call("busy", False)
                await self.call("info" if ok else "error", f"{msg} ({self.app.state.base_url})")
                if ok:
                    await self.call("setProviders", await self.api.providers())
        except TwoFactorRequired as need:
            await self.ask_second_step(need, bool(v.get("remember", self.pending.get("remember", True))))
        except ApiError as exc:
            await self.call("error", str(exc))
        except KeyError:
            await self.call("error", "Something was missing \u2014 please try again.")
        except Exception as exc:
            import httpx
            if isinstance(exc, httpx.TimeoutException):
                await self.call("error", server_config.WAKING_UP)
            elif isinstance(exc, httpx.HTTPError):
                from ..services.api_client import unreachable
                await self.call("error", str(unreachable(exc)))       # says why, and what to do
            else:
                await self.call("error", f"Something went wrong ({type(exc).__name__}: {str(exc)[:120]}). Please try again.")

    async def start_oauth(self, provider: str):
        label = {"google": "Google", "apple": "Apple", "microsoft": "Microsoft", "github": "GitHub"}.get(provider, "SSO")
        state = secrets.token_urlsafe(24)
        self.oauth.update(state=state, provider=provider)
        await self.call("show", "oauth", {"title": f"Continue with {label}"})
        try:
            await self.api.oauth_begin(provider, state)     # register the ticket first
        except ApiError as exc:
            self.oauth["state"] = None
            await self.call("show", "login")
            await self.call("error", str(exc))
            return
        if not _open_in_browser(self.app, self.api.oauth_start_url(provider, state)):
            await self.call("error", "Couldn't open your browser.")
            return
        deadline = asyncio.get_event_loop().time() + 300
        while self.oauth["state"] == state and self.alive():
            if asyncio.get_event_loop().time() > deadline:
                await self.call("error", "Sign-in timed out. Try again.")
                self.oauth["state"] = None
                return
            try:
                session = await self.api.oauth_poll(state)
            except TwoFactorRequired as need:                 # Google/GitHub... was right; now the code
                await self.ask_second_step(need, True)
                return
            except ApiError as exc:
                self.oauth["state"] = None
                await self.call("show", "login")
                await self.call("error", str(exc))
                return
            if session is not None:
                self.finish(session, True)
                return
            await asyncio.sleep(1.5)


def build_login_screen(app: toga.App, on_success):
    controller = LoginController(app, on_success)
    try:
        asyncio.get_event_loop().create_task(controller.run())
    except RuntimeError:
        pass
    box = toga.Box(style=Pack(direction=COLUMN, flex=1), children=[controller.web_view])
    box._login_controller = controller          # for tests
    return box
