"""
Settings window and account menu, drawn inside the chat page.

* Account menu: click your name in the sidebar (or the avatar in the rail):
  Settings, Usage, Reply language, Get help, Upgrade plan, About, Log out.
* Settings window: section list on the left with search, rows on the right.
  Cmd/Ctrl + , opens it; Esc closes it.

The page only DRAWS settings. Python (main_screen.py) owns the values:
  Python -> page:  setSettingsState({values, info, lists, ...}), settingsToast(text, kind),
                   setAppearance(theme, font, motion), openSettings(panel)
  page -> Python:  ginkEmit("setting", {key, value}), ginkEmit("settings_action", {name, value})
Every row maps to something Gink really does -- no decorative switches.

Kept as raw strings (r\"\"\") so JavaScript backslashes need no escaping.
"""

ICONS = {
    "general": '<path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "account": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "privacy": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "billing": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h3"/>',
    "usage": '<path d="M12 21a9 9 0 1 1 9-9"/><path d="M12 12l4-4"/><circle cx="12" cy="12" r="1.2"/>',
    "capabilities": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
    "memory": '<path d="M12 4a4 4 0 0 0-4 4v1a3 3 0 0 0-2 5 3 3 0 0 0 3 5h6a3 3 0 0 0 3-5 3 3 0 0 0-2-5V8a4 4 0 0 0-4-4z"/><path d="M12 4v16"/>',
    "storage": '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    "personalization": '<path d="M12 3l1.9 5.8H20l-4.9 3.6 1.9 5.8L12 14.6l-5 3.6 1.9-5.8L4 8.8h6.1z"/>',
    "location": '<path d="M12 21s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/>',
    "connected": '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    "briefing": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "sync": '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8"/><path d="M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.3 4.9L20 16"/><path d="M20 20v-4h-4"/>',
    "advanced": '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14"/><circle cx="12" cy="17.2" r=".6"/>',
    "about": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.8" r=".6"/>',
    "voice": '<path d="M4 10v4M8 7v10M12 4v16M16 7v10M20 10v4"/>',
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2.5"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
    "language": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 2.5 15.3 0 18M12 3c-2.5 2.7-2.5 15.3 0 18"/>',
    "upgrade": '<circle cx="12" cy="12" r="9"/><path d="M12 16V8M8.5 11.5L12 8l3.5 3.5"/>',
    "logout": '<path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 17l-5-5 5-5M5 12h11"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
}


def icon(name: str, size: int = 18) -> str:
    return (f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" stroke="currentColor" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


SETTINGS_CSS = r"""
  /* ---------- appearance: dark theme, fonts, reduced motion ---------- */
  html.theme-dark, body.theme-dark {
    --bg: #161917; --surface: #1C201D; --elevated: #252A26; --border: #333A35; --hover: #2D332E;
    --text-main: #E6EBE3; --text-muted: #9AA398; --accent: #8FD14A; --accent-dim: #7BBF22;
    --accent-soft: #24331A; --on-accent: #0F1410; --sidebar: #131614; --danger: #FF7A6E;
    color-scheme: dark;
  }
  body.theme-dark #composer-wrap { background: linear-gradient(to bottom, rgba(22,25,23,0), var(--bg) 22px); }
  body.theme-dark.home #composer-wrap { background: transparent; }
  body.theme-dark #cin::placeholder { color: #7D857B; }
  body.theme-dark .vcard:hover, body.theme-dark #composer { box-shadow: none; }
  body.font-serif #feed { font-family: "New York", "Iowan Old Style", Georgia, "Times New Roman", serif; }
  body.font-mono #feed { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 14px; }
  body.reduced-motion *, body.reduced-motion *::before, body.reduced-motion *::after {
    animation: none !important; transition: none !important;
  }

  /* ---------- account menu ---------- */
  .side-foot { cursor: pointer; border-radius: 0; }
  .side-foot:hover .who #who { text-decoration: underline; text-decoration-color: var(--border); }
  #acct-menu {
    position: fixed; left: 12px; bottom: 64px; width: 248px; z-index: 45;
    background: var(--bg); border: 1px solid var(--border); border-radius: 14px; padding: 6px;
    box-shadow: 0 12px 34px rgba(0,0,0,0.16); display: none;
  }
  #acct-menu.open { display: block; animation: pop-in 0.14s ease-out; }
  #acct-menu .email { padding: 8px 10px 6px; font-size: 12.5px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #acct-menu button {
    display: flex; align-items: center; width: 100%; border: none; background: transparent; font: inherit;
    font-size: 14px; color: var(--text-main); padding: 8px 10px; border-radius: 9px; cursor: pointer; text-align: left;
  }
  #acct-menu button:hover { background: var(--elevated); }
  #acct-menu button svg { margin-right: 11px; color: var(--text-muted); flex: none; }
  #acct-menu .kbd { margin-left: auto; color: var(--text-muted); font-size: 12px; }
  #acct-menu .sep { height: 1px; background: var(--border); margin: 6px 4px; }

  /* ---------- settings window ---------- */
  #settings-back {
    position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 48; background: rgba(15,18,16,0.32);
    display: none; align-items: center; justify-content: center; padding: 18px;
  }
  #settings-back.open { display: flex; animation: fade-in 0.15s ease-out; }
  .settings {
    width: 100%; max-width: 1000px; height: 100%; max-height: 740px; display: flex; overflow: hidden;
    background: var(--bg); border-radius: 18px; box-shadow: 0 24px 70px rgba(0,0,0,0.28);
    animation: pop-in 0.18s cubic-bezier(0.22, 1, 0.36, 1);
  }
  .s-nav { width: 220px; flex: none; border-right: 1px solid var(--border); padding: 14px 10px; overflow-y: auto; background: var(--sidebar); }
  .s-search { display: flex; align-items: center; border: 1px solid var(--border); border-radius: 10px; padding: 0 10px; margin-bottom: 12px; background: var(--bg); }
  .s-search svg { color: var(--text-muted); flex: none; }
  .s-search input { border: none; outline: none; background: transparent; font: inherit; font-size: 14px; color: var(--text-main); padding: 8px; width: 100%; }
  .s-group { font-size: 12px; color: var(--text-muted); padding: 10px 10px 4px; }
  .s-nav button {
    display: flex; align-items: center; width: 100%; border: none; background: transparent; font: inherit; font-size: 14px;
    color: var(--text-main); padding: 7px 10px; border-radius: 9px; cursor: pointer; text-align: left; margin-bottom: 1px;
  }
  .s-nav button svg { margin-right: 11px; color: var(--text-muted); flex: none; }
  .s-nav button:hover { background: var(--elevated); }
  .s-nav button.active { background: var(--hover, var(--elevated)); font-weight: 500; }
  .s-main { flex: 1; overflow-y: auto; position: relative; padding: 18px 30px 40px; }
  .s-close {
    position: sticky; top: 0; float: right; margin-right: -12px; width: 32px; height: 32px; border-radius: 8px;
    border: none; background: var(--bg); color: var(--text-muted); cursor: pointer; display: flex; align-items: center; justify-content: center; z-index: 2;
  }
  .s-close:hover { background: var(--elevated); color: var(--text-main); }
  .s-section h3 { font-size: 16px; font-weight: 600; margin: 26px 0 6px; }
  .s-section:first-child h3 { margin-top: 32px; }
  .s-row { display: flex; align-items: center; padding: 14px 0; border-bottom: 1px solid var(--border); min-height: 30px; }
  .s-row:last-child { border-bottom: none; }
  .s-row .lab { flex: 1; min-width: 0; padding-right: 18px; }
  .s-row .lab b { font-weight: 500; font-size: 14.5px; display: block; }
  .s-row .lab span { color: var(--text-muted); font-size: 13px; display: block; margin-top: 3px; line-height: 1.4; }
  .s-row .ctl { flex: none; display: flex; align-items: center; }
  .s-row.stack { display: block; }
  .s-row.stack .ctl { margin-top: 10px; }
  .s-row.hit { background: var(--accent-soft); border-radius: 8px; padding-left: 8px; padding-right: 8px; }
  /* switch */
  .sw { position: relative; width: 40px; height: 24px; flex: none; }
  .sw input { opacity: 0; width: 0; height: 0; position: absolute; }
  .sw i { position: absolute; top: 0; right: 0; bottom: 0; left: 0; background: #C9CFC6; border-radius: 999px; cursor: pointer; transition: background 0.18s; }
  .sw i::after { content: ""; position: absolute; width: 18px; height: 18px; left: 3px; top: 3px; border-radius: 50%; background: #fff; transition: transform 0.18s; box-shadow: 0 1px 2px rgba(0,0,0,0.2); }
  .sw input:checked + i { background: #2F7DE1; }
  body.theme-dark .sw i { background: #4A524C; }
  body.theme-dark .sw input:checked + i { background: #2F7DE1; }     /* ON must still look on in dark mode */
  .sw input:checked + i::after { transform: translateX(16px); }
  .sw input:disabled + i { opacity: 0.45; cursor: default; }
  /* segmented */
  .seg { display: flex; background: var(--elevated); border-radius: 10px; padding: 3px; }
  .seg button { border: none; background: transparent; font: inherit; font-size: 13.5px; color: var(--text-muted); padding: 5px 12px; border-radius: 8px; cursor: pointer; display: flex; align-items: center; }
  .seg button.on { background: var(--bg); color: var(--text-main); box-shadow: 0 1px 3px rgba(0,0,0,0.12); }
  .seg.icons button { padding: 5px 8px; }
  /* select */
  .s-select { font: inherit; font-size: 14px; color: var(--text-main); background: transparent; border: none; padding: 4px 22px 4px 8px; border-radius: 8px; cursor: pointer; -webkit-appearance: none; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23889086' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 4px center; }
  .s-select:hover { background-color: var(--elevated); }
  .s-select option { color: #1C211D; }
  .s-input { font: inherit; font-size: 14px; color: var(--text-main); background: var(--bg); border: 1px solid var(--border); border-radius: 9px; padding: 7px 10px; width: 230px; outline: none; }
  .s-input:focus { border-color: var(--accent); }
  .s-btn { font: inherit; font-size: 13.5px; border-radius: 999px; padding: 7px 15px; cursor: pointer; border: 1px solid var(--border); background: var(--bg); color: var(--text-main); margin-left: 8px; white-space: nowrap; }
  .s-btn:hover { background: var(--elevated); }
  .s-btn.primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); font-weight: 500; }
  .s-btn.danger { color: #fff; background: #E5251B; border-color: #E5251B; }
  .s-btn.danger-ghost { color: var(--danger); }
  .s-btn:disabled { opacity: 0.5; cursor: default; }
  .s-note { color: var(--text-muted); font-size: 13px; line-height: 1.5; padding: 10px 0; }
  .s-list { width: 100%; }
  .s-item { display: flex; align-items: center; padding: 9px 0; border-bottom: 1px solid var(--border); font-size: 14px; }
  .s-item:last-child { border-bottom: none; }
  .s-item .t { flex: 1; min-width: 0; }
  .s-item .m { color: var(--text-muted); font-size: 12.5px; margin-left: 10px; white-space: nowrap; }
  .meter2 { width: 100%; height: 10px; border-radius: 999px; background: var(--elevated); overflow: hidden; margin: 6px 0 4px; }
  .meter2 i { display: block; height: 100%; border-radius: 999px; background: var(--accent); transition: width 0.4s; }
  .meter2.high i { background: #E0812A; } .meter2.full i { background: var(--danger); }
  .badge { display: inline-block; font-size: 12px; font-weight: 600; padding: 2px 9px; border-radius: 999px; background: var(--elevated); color: var(--text-muted); margin-left: 8px; }
  .badge.pro { background: var(--accent-soft); color: var(--accent); }
  kbd.kbd { display: inline-block; min-width: 26px; text-align: center; font: 600 12.5px -apple-system, 'Segoe UI', Roboto, sans-serif;
    color: var(--text-main); background: var(--elevated); border: 1px solid var(--border); border-bottom-width: 2px;
    border-radius: 7px; padding: 3px 8px; }
  .kplus { color: var(--text-muted); margin: 0 5px; font-size: 12px; }
  .avatar-lg { width: 44px; height: 44px; border-radius: 50%; background: var(--elevated); display: inline-flex; align-items: center; justify-content: center;
    font-weight: 600; font-size: 15px; color: var(--text-main); margin-left: 12px; overflow: hidden; flex: none; }
  .avatar-lg img { width: 100%; height: 100%; object-fit: cover; }
  .s-textarea { width: 100%; min-height: 96px; font: inherit; font-size: 14px; color: var(--text-main); background: var(--bg);
    border: 1px solid var(--border); border-radius: 12px; padding: 10px 12px; outline: none; resize: vertical; line-height: 1.5; }
  .s-textarea:focus { border-color: var(--accent); }
  #lang-back { position: fixed; top: 0; right: 0; bottom: 0; left: 0; z-index: 55; background: rgba(15,18,16,0.32); display: none; align-items: center; justify-content: center; padding: 18px; }
  #lang-back.open { display: flex; }
  .lang-box { width: 100%; max-width: 760px; max-height: 80vh; background: var(--bg); border-radius: 18px; box-shadow: 0 24px 70px rgba(0,0,0,0.28); display: flex; flex-direction: column; overflow: hidden; }
  .lang-head { display: flex; align-items: center; padding: 20px 22px 12px; flex: none; }
  .lang-head h2 { flex: 1; margin: 0; font-size: 21px; }
  .lang-search { margin: 0 22px 12px; display: flex; align-items: center; border: 1.5px solid #2F7DE1; border-radius: 10px; padding: 0 10px; flex: none; min-height: 42px; }
  .lang-search input { border: none; outline: none; background: transparent; font: inherit; font-size: 15px; color: var(--text-main); padding: 9px 8px; width: 100%; }
  .lang-grid { overflow-y: auto; padding: 0 16px 18px; display: -webkit-flex; display: flex; -webkit-flex-wrap: wrap; flex-wrap: wrap; align-content: flex-start; flex: 1 1 auto; min-height: 0; }
  .lang-grid button { text-align: left; border: none; background: transparent; border-radius: 10px; padding: 9px 12px; cursor: pointer; font: inherit; color: var(--text-main); display: flex; align-items: center; width: 33.33%; margin: 0; }
  .lang-grid button:hover { background: var(--elevated); }
  .lang-grid button.sel { background: #E5EEFB; }
  body.theme-dark .lang-grid button.sel { background: #22324A; }
  .lang-grid .ln { flex: 1; min-width: 0; }
  .lang-grid b { display: block; color: var(--text-main); font-weight: 600; font-size: 14.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .lang-grid span { display: block; font-size: 12.5px; color: var(--text-muted); margin-top: 2px; }
  .lang-grid .ck { color: #2F7DE1; margin-left: 6px; flex: none; }
  @media (max-width: 700px) { .lang-grid button { width: 50%; } }
  #s-toast { position: fixed; left: 50%; bottom: 28px; transform: translateX(-50%); z-index: 60; background: #1C211D; color: #fff;
    padding: 9px 16px; border-radius: 10px; font-size: 13.5px; opacity: 0; pointer-events: none; transition: opacity 0.2s; max-width: 80vw; }
  #s-toast.show { opacity: 1; }
  #s-toast.err { background: #B4261C; }
  .s-empty { color: var(--text-muted); font-size: 14px; padding: 20px 0; }
  @media (max-width: 700px) {
    #settings-back { padding: 0; }
    .settings { border-radius: 0; max-height: none; flex-direction: column; }
    .s-nav { width: auto; border-right: none; border-bottom: 1px solid var(--border); display: flex; overflow-x: auto; padding: 8px; }
    .s-nav .s-search, .s-nav .s-group { display: none; }
    .s-nav button { width: auto; white-space: nowrap; }
    .s-main { padding: 6px 16px 40px; }
    .s-row { flex-wrap: wrap; } .s-row .ctl { margin-top: 8px; }
  }
"""

SETTINGS_HTML = r"""
  <div id="acct-menu" role="menu">
    <div class="email" id="am-email"></div>
    <button data-am="settings">__I_general__Settings<span class="kbd" id="am-kbd">Ctrl ,</span></button>
    <button data-am="usage">__I_usage__Usage</button>
    <button data-am="language">__I_language__Reply language</button>
    <button data-am="help">__I_help__Get help</button>
    <div class="sep"></div>
    <button data-am="upgrade">__I_upgrade__Upgrade plan</button>
    <button data-am="about">__I_about__About Gink</button>
    <div class="sep"></div>
    <button data-am="logout">__I_logout__Log out</button>
  </div>
  <div id="settings-back">
    <div class="settings" role="dialog" aria-modal="true" aria-label="Settings">
      <nav class="s-nav" id="s-nav">
        <div class="s-search">__I_search__<input id="s-q" placeholder="Search" autocomplete="off"></div>
      </nav>
      <div class="s-main" id="s-main">
        <button class="s-close" id="s-close" title="Close">__I_close__</button>
        <div id="s-body"></div>
      </div>
    </div>
  </div>
  <div id="s-toast"></div>
  <div id="lang-back"><div class="lang-box" role="dialog" aria-label="Choose your language">
    <div class="lang-head"><h2>Choose your language</h2><button class="s-close" id="lang-close" style="position:static;margin:0">__I_close__</button></div>
    <div class="lang-search">__I_search__<input id="lang-q" placeholder="Search languages" autocomplete="off"></div>
    <div class="lang-grid" id="lang-grid"></div>
  </div></div>
"""

SETTINGS_JS = r"""
  // ======================= settings window & account menu =======================
  var S = {values: {}, info: {}, lists: {}, open: false, panel: 'general'};
  var SICON = __SICONS__;
  var LANGS = [['auto','Same as my message'],['en','English'],['fr','Fran\u00e7ais'],['wo','Wolof (experimental)'],
               ['kri','Krio (experimental)'],['ar','\u0627\u0644\u0639\u0631\u0628\u064a\u0629'],['pt','Portugu\u00eas'],['es','Espa\u00f1ol']];

  // Each panel: sections of rows. Row types: seg, select, toggle, input, button, info, html.
  function PANELS() {
    var v = S.values, info = S.info, L = S.lists;
    var pro = info.plan === 'pro';
    return [
      {id: 'general', group: 'Settings', title: 'General', sections: [
        {title: 'Appearance', rows: [
          {type: 'seg', key: 'theme', label: 'Theme', icons: true, options: [['system', SICON.monitor, 'Match system'], ['light', SICON.sun, 'Light'], ['dark', SICON.moon, 'Dark']]},
          {type: 'select', key: 'chat_font', label: 'Chat font', options: [['sans', 'System'], ['serif', 'Serif'], ['mono', 'Monospace']]},
          {type: 'seg', key: 'motion', label: 'Motion', desc: 'Reduce animation in streaming responses and other interface elements.', options: [['system', 'System'], ['reduced', 'Reduced']]}]},
        {title: 'Language', rows: [
          {type: 'lang', label: 'Reply language', desc: 'The language Gink answers in. Answers are best in widely used languages; ones marked experimental may contain mistakes.'}]},
        {title: 'Notifications', rows: [
          {type: 'toggle', key: 'notify_reminders', label: 'Reminders and alarms', desc: 'Show a system notification when a reminder, alarm or timer is due.'},
          {type: 'toggle', key: 'briefing_enabled', label: 'Morning briefing', desc: 'Get your daily briefing automatically at your briefing time.'}]}]},
      {id: 'voice', group: 'Settings', title: 'Voice', sections: [
        {title: '', rows: [{type: 'voicecar'}]},
        {title: 'Voice settings', rows: [
          {type: 'select', key: 'speech_lang', label: 'Language', desc: 'The language you speak to Gink in. Speech recognition needs one language \u2014 it can\u2019t detect it automatically.',
           options: (info.speech_langs || [['en-US', 'English (United States)']])},
          {type: 'select', key: 'voice_speed', label: 'Speed', options: [['slow', 'Slow'], ['normal', 'Normal'], ['fast', 'Fast']]},
          {type: 'toggle', key: 'read_aloud', label: 'Read replies aloud', desc: 'Speak answers to typed messages too. Voice conversations are always spoken.'},
          {apps: true, type: 'button', label: 'Natural voice', desc: 'Check that the human-sounding voice works. If it doesn\u2019t, Gink uses a standard voice and this tells you why.', action: 'test_voice', text: 'Test'}]},
        {title: 'Hey Gink', rows: [
          {type: 'toggle', key: 'wake_enabled', label: 'Listen for \u201cHey Gink\u201d', disabled: info.wake_supported === false,
           desc: 'Say \u201cHey Gink\u201d to ask something hands-free. Listening for it happens entirely on this computer \u2014 nothing is sent anywhere until you say it.' +
                 (info.wake_supported === false ? ' (Not available on this device yet.)' : '')},
          {type: 'info', label: 'Status', value: info.wake_status || 'Off'},
          {type: 'toggle', key: 'wake_followup', label: 'Keep listening for a follow-up', desc: 'After answering, Gink listens a few more seconds so you can carry on without saying \u201cHey Gink\u201d again.'},
          {type: 'toggle', key: 'wake_front', label: 'Bring Gink to the front', desc: 'Show the Gink window when you wake it.'}]},
        {title: 'Privacy', rows: [{type: 'note', text: 'To understand you, your speech is sent to Google\u2019s speech service and turned into text. Voice conversations are saved like any chat, and you can delete them at any time.'}]}]},
      {id: 'keyboard', group: 'Settings', title: 'Keyboard', sections: [
        {title: 'Typing', rows: [
          {type: 'seg', key: 'send_key', label: 'Send messages with', desc: KB_SEND_DESC(v.send_key),
           options: [['enter', 'Enter'], ['mod', MODKEY + ' + Enter']]},
          {type: 'toggle', key: 'single_keys', label: 'Single-key shortcuts', desc: 'Use / to jump to the message box, and Space to mute during voice conversations. Turn off if they get in your way.'}]},
        {title: 'Shortcuts', rows: SHORTCUTS().map(function (sc) { return {type: 'html', label: sc[0], html: sc[1].map(function (key) { return '<kbd class="kbd">' + esc(key) + '</kbd>'; }).join('<span class="kplus">+</span>')}; })}]},
      {id: 'account', group: 'Settings', title: 'Account', sections: [
        {title: 'Profile', rows: [
          {apps: true, type: 'photo', label: 'Profile photo', desc: 'PNG, JPEG or WebP, up to 10 MB.'},
          {type: 'text', key: 'full_name', label: 'Full name', placeholder: 'Your full name'},
          {type: 'text', key: 'nickname', label: 'What should Gink call you?', placeholder: 'e.g. Ibrahim'},
          {type: 'select', key: 'work', label: 'What best describes your work?', desc: 'Gink uses this to pick examples that fit you.',
           options: (info.work_options || ['']).map(function (w) { return [w, w || 'Select']; })}]},
        {title: 'Account', rows: [
          {type: 'info', label: 'Email', value: info.email || ''},
          {type: 'html', label: 'Plan', html: pro ? '<span class="badge pro">Gink Pro</span>' : '<span class="badge">Free</span>'},
          {type: 'button', label: 'Log out', desc: 'Sign out of Gink on this device.', action: 'logout', text: 'Log out'}]},
        {title: 'Phone number', rows: phoneRows(info.phone || {})},
        {title: 'Passkeys', rows: [
          {type: 'note', text: 'Sign in with your fingerprint, face or device PIN instead of a password. Passkeys only work on the real Gink site, so they can\u2019t be phished.'},
          {type: 'list', items: (L.passkeys || []).map(function (k) {
            return {t: k.name || 'Passkey', m: 'Added ' + new Date(k.created * 1000).toLocaleDateString() + (k.last_used ? ' \u00b7 last used ' + new Date(k.last_used * 1000).toLocaleDateString() : ''),
                    button: {text: 'Remove', action: 'passkey_remove', value: k.id}}; }),
           empty: 'No passkeys yet.'},
          info.web ? {type: 'button', label: 'Add a passkey', desc: 'Your browser or phone will ask for your fingerprint, face or PIN.', action: 'passkey_add', text: 'Add', style: 'plain'}
                   : {type: 'note', text: 'Add passkeys in Gink on the web (sign in at your Gink server\u2019s /app in a browser). Passkeys work in browsers; the apps keep their usual sign-in.'}]},
        {title: 'Two-step verification', rows: twofaRows(info.twofa || {})},
        {title: 'Your websites', rows: [
          {type: 'list', items: (L.sites || []).map(function (w) {
            return {t: w.title, m: w.url + ' \u00b7 ' + (w.views || 0) + (w.views === 1 ? ' view' : ' views'),
                    button: {text: 'Delete', action: 'delete_site', value: w.id}}; }),
           empty: 'No websites yet. Ask Gink: \u201cmake me a website for my business\u201d.'}]},
        {title: 'Signed-in devices', rows: [
          {type: 'list', items: (L.sessions || []).map(function (d) {
            return {t: d.device, m: d.when, button: d.current ? null : {text: 'Log out', action: 'revoke_session', value: d.id}}; }),
           empty: info.sessions_error || 'Loading your devices\u2026'}].concat(
          (L.sessions || []).length > 1 ? [{type: 'button', label: 'Log out of all other devices', desc: 'If you lost a phone or used a shared computer, this signs you out everywhere except here.',
                                            action: 'sign_out_others', text: 'Log out others', style: 'danger-ghost'}] : [])},
        {title: 'Security history', rows: [
          {type: 'list', items: (L.security || []).map(function (e) {
            return {t: e.text, m: new Date(e.ts * 1000).toLocaleString() + (e.device ? ' \u00b7 ' + e.device : '')}; }),
           empty: 'Sign-ins and security changes will appear here.'}]},
        {title: 'Delete account', rows: [
          {type: 'button', label: 'Delete your account', desc: 'Permanently deletes your account and everything synced to it. Payment records are kept for accounting, without your name or email. This can\u2019t be undone.', action: 'delete_account', text: 'Delete account', style: 'danger-ghost'}]}]},
      {id: 'privacy', group: 'Settings', title: 'Privacy', sections: [
        {title: 'Your data', rows: [
          {apps: true, type: 'toggle', key: 'use_memory', label: 'Use memories in answers', desc: 'When off, Gink ignores what you asked it to remember (they stay saved \u2014 manage them under Memory).'},
          {type: 'button', label: 'Export my data', desc: 'Save your chats, Workspace, memories and settings as a file.', action: 'export', text: 'Export'},
          {type: 'button', label: 'Delete all chats', desc: 'Removes every conversation from this device and your other devices.', action: 'delete_chats', text: 'Delete all', style: 'danger-ghost'}]},
        {title: 'Archived chats', rows: [
          {type: 'list', items: (L.archived || []).map(function (c) {
            return {t: c.title || 'Untitled chat', m: '', button: {text: 'Unarchive', action: 'unarchive_chat', value: c.id, style: 'plain'}}; }),
           empty: 'No archived chats. Archive one from its \u22ef menu in the sidebar.'},
          {type: 'button', label: 'Archive all chats', desc: 'Moves every chat out of Recents. Nothing is deleted.', action: 'archive_all', text: 'Archive all'}]},
        {title: 'Shared links', rows: [
          {type: 'list', items: (L.shared || []).map(function (x) {
            return {t: x.title, m: x.url + ' \u00b7 ' + (x.views || 0) + (x.views === 1 ? ' view' : ' views'),
                    button: {text: 'Delete', action: 'delete_shared', value: x.id}}; }),
           empty: 'No shared links. Share a chat from its \u22ef menu in the sidebar.'}]},
        {title: 'Your chats and AI training', rows: [
          {type: 'note', text: 'Gink never uses your chats, files or voice to train AI models, and doesn\u2019t use tracking or advertising cookies.'}]},
        {title: 'Lockdown mode', rows: [
          {type: 'note', text: 'Protects you from hidden instructions in web pages and emails (prompt injection) by turning off everything that brings outside content into Gink: web search, connected apps, and images from web addresses. Your server enforces it on every device.'},
          info.lockdown_on === undefined ? {type: 'note', text: 'Sign in to use Lockdown mode.'} :
          {type: 'button', label: info.lockdown_on ? 'Lockdown mode is on' : 'Lockdown mode is off', desc: info.lockdown_on ? 'Web search and connected apps are off.' : 'Turn it on if you handle sensitive information.',
           action: info.lockdown_on ? 'lockdown_off' : 'lockdown_on', text: info.lockdown_on ? 'Turn off' : 'Turn on', style: info.lockdown_on ? '' : 'danger-ghost'}]},
        {title: 'Policies', rows: (info.privacy_url || info.terms_url) ? [
          info.privacy_url ? {type: 'button', label: 'Privacy policy', action: 'open_url', value: info.privacy_url, text: 'Open'} : null,
          info.terms_url ? {type: 'button', label: 'Terms of service', action: 'open_url', value: info.terms_url, text: 'Open'} : null].filter(Boolean)
          : [{type: 'note', text: 'Your server hasn\u2019t published a privacy policy link yet (GINK_PRIVACY_URL).'}]}]},
      {id: 'billing', group: 'Settings', title: 'Billing', sections: [
        {title: 'Plan', rows: [
          {type: 'html', label: pro ? 'Gink Pro' : 'Free plan', desc: pro ? ('Active until ' + (info.pro_until_text || '')) : 'Upgrade for more messages, photo and file analysis, and premium voices.',
           html: '<button class="s-btn primary" data-act="upgrade">' + (pro ? 'Add more time' : 'Upgrade') + '</button>'}]},
        {title: 'Payment history', rows: [{type: 'list', items: (L.payments || []).map(function (p) {
            return {t: (p.plan_label || p.plan) + ' \u00b7 ' + p.method_label, m: p.display + ' \u00b7 ' + p.date + ' \u00b7 ' + p.status_label}; }),
          empty: L.payments_error || 'No payments yet.'}]}]},
      {id: 'usage', group: 'Settings', title: 'Usage', sections: [
        {title: 'Today', rows: info.usage ? [
          {type: 'meter', label: info.usage.used + ' of ' + info.usage.limit + ' messages used', used: info.usage.used, limit: info.usage.limit,
           desc: 'Resets ' + (info.usage.resets_text || 'at midnight (UTC)') + '. One request counts once, even when Gink needs several steps.'},
          pro ? null : {type: 'html', label: 'Need more?', desc: 'Gink Pro raises your daily limit.', html: '<button class="s-btn primary" data-act="upgrade">Upgrade</button>'}].filter(Boolean)
          : [{type: 'note', text: info.usage_error || 'Usage is shown when you\u2019re connected to your Gink server.'}]}]},
      {id: 'capabilities', group: 'Settings', title: 'Capabilities', sections: [
        {title: 'AI', rows: [
          {type: 'select', key: 'model', label: 'Model', desc: 'Faster models answer quicker; deeper ones reason more.', options: (info.models || []).map(function (m) { return [m.id, m.name + (m.tier ? ' \u2014 ' + m.tier : '')]; })},
          {type: 'toggle', key: 'web_search', label: 'Search the web', desc: 'Let Gink look things up online for current facts.'},
          {type: 'toggle', key: 'agent_confirm', label: 'Ask before sensitive actions', desc: 'Gink asks before it sends a message, makes a call, deletes something, or locks or sleeps your computer as part of a longer task.'},
          {type: 'toggle', key: 'video_suggestions', label: 'Suggest videos', desc: 'Add YouTube guides to how-to answers.'}]}]},
      {id: 'memory', group: 'Settings', title: 'Memory', sections: [
        {title: 'Instructions for Gink', rows: [
          {type: 'textarea', key: 'instructions', label: 'Gink will keep these in mind in every chat, on all your devices.',
           placeholder: 'e.g. Keep answers short. When I learn something new, analogies help me. I study medicine in Dakar.',
           action: 'save_instructions', text: 'Save'}]},
        {title: 'What Gink remembers', rows: [{apps: true, type: 'list', items: (L.memories || []).map(function (m) {
            return {t: m.text, button: {text: 'Forget', action: 'forget_memory', value: m.uid}}; }),
          empty: 'Nothing yet. Say \u201cremember that my exams start on 12 November\u201d in the chat.'}].concat(
          (L.memories || []).length ? [{apps: true, type: 'button', label: 'Forget everything', action: 'forget_all', text: 'Forget all', style: 'danger-ghost'}] : [])}]},
      {id: 'personalization', group: 'Settings', title: 'Personalization', sections: [
        {title: 'Prompt library', rows: [
          {type: 'note', text: 'Type / at the start of a message to pick a prompt. Gink includes some; add your own here.'},
          {type: 'input', key: 'new_prompt', label: 'New prompt', placeholder: 'e.g. Reply to this customer politely and briefly:', action: 'add_prompt', text: 'Add'},
          {type: 'list', items: (L.prompts || []).map(function (x) {
            return {t: x.text.split('\n')[0].slice(0, 80), m: x.text.length > 80 ? x.text.length + ' characters' : '',
                    button: {text: 'Delete', action: 'delete_prompt', value: x.id}}; }),
           empty: 'No prompts of your own yet.'}]},
        {title: 'Style and tone', rows: [
          {type: 'note', text: 'Choose how Gink writes to you. This doesn\u2019t change what Gink can do.'},
          {type: 'select', key: 'style_base', label: 'Base style and tone', options: [['default', 'Default'], ['professional', 'Professional'], ['friendly', 'Friendly'], ['concise', 'Concise'], ['candid', 'Candid'], ['playful', 'Playful']]},
          {type: 'select', key: 'style_warmth', label: 'Warmth', options: [['less', 'Less'], ['default', 'Default'], ['more', 'More']]},
          {type: 'select', key: 'style_enthusiasm', label: 'Enthusiasm', options: [['less', 'Less'], ['default', 'Default'], ['more', 'More']]},
          {type: 'select', key: 'style_emoji', label: 'Emoji', options: [['less', 'Less'], ['default', 'Default'], ['more', 'More']]},
          {type: 'select', key: 'style_headers', label: 'Headers and lists', options: [['less', 'Less'], ['default', 'Default'], ['more', 'More']]}]}]},
      {id: 'storage', group: 'Settings', title: 'Storage', sections: info.web ? [
        {title: 'Storage', rows: [{type: 'note', text: 'Gink on the web keeps your chats in this browser and syncs them to your account. To free space, archive or delete chats in Settings > Privacy.'}]}] : [
        {title: 'Storage', rows: [
          {type: 'meter', label: (info.storage ? info.storage.total : '\u2026') + ' used by Gink on this device', used: info.storage ? info.storage.pct : 0, limit: 100,
           desc: info.storage ? info.storage.free + ' free on this device' : ''}]},
        {title: 'Manage storage', rows: info.storage ? [
          {type: 'info', label: 'Chats', value: info.storage.parts.chats},
          {type: 'button', label: 'Images', desc: info.storage.parts.images + ' \u00b7 ' + info.storage.counts.images + ' images Gink made', action: 'free_storage', value: 'images', text: 'Delete', style: 'danger-ghost'},
          {type: 'button', label: 'Files', desc: info.storage.parts.files + ' \u00b7 ' + info.storage.counts.files + ' files Gink made (PDF, Word, Excel\u2026)', action: 'free_storage', value: 'files', text: 'Delete', style: 'danger-ghost'},
          {type: 'button', label: 'Offline AI model', desc: info.storage.parts.offline_ai + ' \u00b7 downloads again if you use offline mode', action: 'free_storage', value: 'offline_ai', text: 'Remove', style: 'danger-ghost'},
          {type: 'button', label: '\u201cHey Gink\u201d speech model', desc: info.storage.parts.wake_model + ' \u00b7 downloads again when \u201cHey Gink\u201d is on', action: 'free_storage', value: 'wake_model', text: 'Remove', style: 'danger-ghost'},
          {type: 'button', label: 'Song recognition data', desc: info.storage.parts.songs, action: 'free_storage', value: 'songs', text: 'Remove', style: 'danger-ghost'}] : []}]},
      {id: 'connected', group: 'Settings', title: 'Connected apps', sections: [
        {title: 'Connected apps', rows: [
          {type: 'note', text: 'Let Gink use your Google apps to answer and help. Each one is connected separately; Gink asks before it adds an event or writes or sends an email, and never keeps what it reads.'},
          {type: 'list', items: (L.connected || []).map(function (a) {
            return {t: a.label + (a.connected ? ' \u00b7 connected' : ''), m: a.can,
                    button: a.connected ? {text: 'Disconnect', action: 'disconnect_app', value: a.id}
                                        : {text: 'Connect', action: 'connect_app', value: a.id, style: 'plain'}}; }),
           empty: info.connected_error || 'Loading\u2026'}]}]},
      {id: 'location', group: 'Settings', title: 'Location', sections: [
        {title: 'Your location', rows: [
          {type: 'info', label: 'Your area', value: info.location_text || ''},
          {apps: true, type: 'input', key: 'city', label: 'City', desc: 'Used for weather, air quality, sunrise and sunset, prayer times and your briefing. Leave empty to use an approximate location from your connection.',
           placeholder: 'e.g. Dakar', action: 'save_city', text: 'Save'},
          {apps: true, type: 'button', label: 'Use my approximate location', desc: 'Estimate your city from your internet connection.', action: 'detect_location', text: 'Detect'},
          {type: 'toggle', key: 'use_location', label: 'Use location in answers', desc: 'When off, Gink doesn\u2019t use your city or estimate where you are \u2014 it asks when it needs a place.'}]},
        {title: 'About this location', rows: [
          {type: 'note', text: 'Your general area is estimated from your IP address. An IP address is assigned to your device by your internet provider, and it\u2019s needed to connect to websites and online services. Gink doesn\u2019t keep a history of your location.'}]}]},
      {id: 'briefing', group: 'Settings', title: 'Morning briefing', sections: [
        {title: 'Daily briefing', rows: [
          {type: 'toggle', key: 'briefing_enabled', label: 'Brief me every morning', desc: 'Weather, today\u2019s plans, open tasks and a headline.'},
          {apps: true, type: 'input', key: 'briefing_time', label: 'Time', desc: '24-hour time, e.g. 07:30.', placeholder: '07:30', action: 'save_briefing_time', text: 'Save', narrow: true},
          {type: 'toggle', key: 'briefing_speak', label: 'Read it aloud'},
          {type: 'toggle', key: 'briefing_projects', label: 'Pick up where you left off', desc: 'Add tasks in progress, recent conversations and files you were editing, with a nudge to continue or finish them. File names stay on this computer.'},
          {apps: true, type: 'button', label: 'Try it now', action: 'brief_now', text: 'Brief me'}]}]},
      {id: 'sync', group: 'Settings', title: 'Sync', sections: [
        {title: 'Your devices', rows: [
          {type: 'info', label: 'Status', value: info.sync_status || '\u2014', desc: 'Chats, Workspace and memories follow your account. Alarms stay on each device.'},
          {type: 'button', label: 'Sync now', action: 'sync_now', text: 'Sync now'}]}]},
      {id: 'advanced', group: 'More', title: 'Advanced', sections: [
        {title: 'Connection', rows: [
          {apps: true, type: 'input', key: 'server_url', label: 'Login server', desc: 'Only change this if you know your Gink server\u2019s address. Empty = default.', placeholder: info.default_server || '', action: 'save_server', text: 'Save & test'}]},
        {title: 'Startup', rows: [
          {type: 'toggle', key: 'launch_at_login', label: 'Open Gink when I log in', disabled: !info.launch_supported,
           desc: info.launch_supported ? 'Start Gink automatically on this computer.' : 'Available in the installed Mac app.'}]}]},
      {id: 'help', group: 'More', title: 'Help', sections: [
        {title: 'Things to try', rows: [{type: 'note', text: '\u201cWake me up at 6:30\u201d \u00b7 \u201cRemind me to call Mom at 5\u201d \u00b7 \u201cWhat\u2019s the weather tomorrow?\u201d \u00b7 \u201c100 dollars to CFA\u201d \u00b7 \u201cHow do I change a tyre?\u201d \u00b7 \u201cBrief me\u201d \u00b7 paste a screenshot and ask about it.'}]},
        {title: 'Contact', rows: info.support_email || info.help_url ? [
          info.help_url ? {type: 'button', label: 'Help centre', action: 'open_url', value: info.help_url, text: 'Open'} : null,
          info.support_email ? {type: 'button', label: 'Email support', desc: info.support_email, action: 'open_url', value: 'mailto:' + info.support_email, text: 'Email'} : null].filter(Boolean)
          : [{type: 'note', text: 'Support contact isn\u2019t set on your server yet (GINK_SUPPORT_EMAIL).'}]}]},
      {id: 'about', group: 'More', title: 'About', sections: [
        {title: 'Gink Assistant', rows: [
          {type: 'info', label: 'Version', value: info.version || ''},
          {type: 'info', label: 'Build', value: info.build || '', desc: 'When this copy of Gink was last updated \u2014 handy for checking you\u2019re running the latest version.'},
          {type: 'info', label: 'Server', value: info.server || ''}]}]}
    ];
  }

  var MODKEY = /Mac|iPhone|iPad/.test(navigator.platform || '') ? '\u2318' : 'Ctrl';
  function KB_SEND_DESC(v) { return v === 'mod' ? 'Enter adds a new line; ' + MODKEY + ' + Enter sends.' : 'Shift + Enter adds a new line.'; }
  function SHORTCUTS() {
    return [['New chat', [MODKEY, 'Shift', 'O']], ['Search chats', [MODKEY, 'K']], ['Open Settings', [MODKEY, ',']],
            ['Start a voice conversation', [MODKEY, 'Shift', 'V']], ['Copy the last reply', [MODKEY, 'Shift', 'C']],
            ['Show or hide the sidebar', [MODKEY, '.']], ['Stop the answer', ['Esc']], ['Jump to the message box', ['/']],
            ['Mute during voice', ['Space']], ['End a voice conversation', ['Esc']]];
  }
  function esc(t) { var d = document.createElement('div'); d.textContent = t == null ? '' : String(t); return d.innerHTML; }
  function phoneRows(p) {
    if (p.phone) {
      return [{type: 'info', label: 'Phone number', value: p.phone},
              p.phone_only ? {type: 'note', text: 'Your account signs in with this number.'}
                           : {type: 'button', label: 'Remove this number', desc: 'You can still sign in with your email.', action: 'phone_remove', text: 'Remove', style: 'danger-ghost'}];
    }
    if (!p.enabled) return [{type: 'note', text: 'Signing in with a phone number isn\u2019t set up on this server yet.'}];
    var rows = [{type: 'input', key: 'phone_new', label: 'Add a phone number', desc: 'With its country code. We\u2019ll text you a code to confirm it.', placeholder: '+221 77 123 45 67', action: 'phone_send', text: 'Send code'}];
    if (p.pending) rows.push({type: 'input', key: 'phone_code', label: 'Code sent to ' + p.pending, placeholder: '123456', action: 'phone_verify', text: 'Confirm'});
    return rows;
  }
  function twofaRows(t) {
    if (t.codes && t.codes.length) {                       // shown once, right after turning it on
      return [{type: 'note', text: 'Two-step verification is on. Save these recovery codes somewhere safe \u2014 each one signs you in once if you lose your phone. They won\u2019t be shown again.'},
              {type: 'html', label: 'Recovery codes', html: '<div style="font-family:ui-monospace,Menlo,monospace;font-size:14px;line-height:1.9">' +
                 t.codes.map(esc).join('<br>') + '</div>'},
              {type: 'button', label: 'I\u2019ve saved them', action: 'twofa_done', text: 'Done'}];
    }
    if (t.setup) {
      var qr = /^data:image\/svg\+xml;base64,[A-Za-z0-9+\/=]+$/.test(t.setup.qr || '') ? t.setup.qr : '';
      return [{type: 'note', text: '1. Open an authenticator app (Google Authenticator, Microsoft Authenticator, Authy\u2026) and scan this code.'},
              {type: 'html', label: 'Scan with your app', html: (qr ? '<img src="' + qr + '" alt="QR code for your authenticator app" width="170" height="170" style="border-radius:8px;background:#fff">' : '') +
                 '<div style="margin-top:6px;font-size:12px;color:var(--text-muted)">Can\u2019t scan? Enter this key:<br><b style="font-family:ui-monospace,Menlo,monospace;letter-spacing:1px">' + esc(t.setup.secret) + '</b></div>'},
              {type: 'input', key: 'twofa_code', label: '2. Enter the 6-digit code it shows', placeholder: '123456', action: 'twofa_enable', text: 'Turn on'},
              {type: 'button', label: 'Cancel', action: 'twofa_cancel', text: 'Cancel', style: 'ghost'}];
    }
    if (t.enabled) {
      return [{type: 'info', label: 'Status', value: 'On \u2014 signing in needs a code from your authenticator app' + (t.recovery_left != null ? ' (' + t.recovery_left + ' recovery codes left)' : '')},
              {type: 'input', key: 'twofa_off', label: 'Turn off', desc: 'Enter a current code from your app, or a recovery code.', placeholder: 'Code', action: 'twofa_disable', text: 'Turn off', style: 'danger-ghost'}];
    }
    return [{type: 'button', label: 'Turn on two-step verification', desc: 'After your password, Gink asks for a code from an authenticator app on your phone. Someone who learns your password still can\u2019t get in.',
             action: 'twofa_setup', text: 'Turn on'}];
  }

  function rowHtml(r, pid) {
    var v = S.values, ctl = '', lab = '<div class="lab"><b>' + esc(r.label || '') + '</b>' + (r.desc ? '<span>' + esc(r.desc) + '</span>' : '') + '</div>';
    if (r.type === 'note') return '<div class="s-note">' + esc(r.text) + '</div>';
    if (r.type === 'toggle') {
      ctl = '<label class="sw"><input type="checkbox" data-key="' + r.key + '"' + (v[r.key] ? ' checked' : '') + (r.disabled ? ' disabled' : '') + '><i></i></label>';
    } else if (r.type === 'seg') {
      ctl = '<div class="seg' + (r.icons ? ' icons' : '') + '">' + r.options.map(function (o) {
        return '<button data-key="' + r.key + '" data-value="' + o[0] + '" class="' + (v[r.key] === o[0] ? 'on' : '') + '" title="' + esc(o[2] || o[1]) + '">' + (r.icons ? o[1] : esc(o[1])) + '</button>'; }).join('') + '</div>';
    } else if (r.type === 'select') {
      ctl = '<select class="s-select" data-key="' + r.key + '">' + r.options.map(function (o) {
        return '<option value="' + esc(o[0]) + '"' + (String(v[r.key]) === String(o[0]) ? ' selected' : '') + '>' + esc(o[1]) + '</option>'; }).join('') + '</select>';
    } else if (r.type === 'input') {
      ctl = '<input class="s-input" data-input="' + r.key + '" value="' + esc(v[r.key] || '') + '" placeholder="' + esc(r.placeholder || '') + '"' + (r.narrow ? ' style="width:90px"' : '') + '>' +
            '<button class="s-btn" data-act="' + r.action + '" data-from="' + r.key + '">' + esc(r.text) + '</button>';
    } else if (r.type === 'button') {
      ctl = '<button class="s-btn ' + (r.style || '') + '" data-act="' + r.action + '"' + (r.value ? ' data-value="' + esc(r.value) + '"' : '') + '>' + esc(r.text) + '</button>';
    } else if (r.type === 'info') {
      ctl = '<span style="color:var(--text-muted);font-size:14px;max-width:420px;text-align:right">' + esc(r.value) + '</span>';
    } else if (r.type === 'voicecar') {
      return '<div class="s-row stack" style="border-bottom:none;padding-top:4px"><div id="s-voicecar" style="width:100%"></div></div>';
    } else if (r.type === 'photo') {
      var ph = S.info.photo, nm = (S.values.full_name || S.info.name || S.info.email || '?').trim();
      var initials = nm.split(/\s+/).map(function (w) { return w.charAt(0); }).join('').slice(0, 2).toUpperCase();
      ctl = '<input type="file" id="photo-file" accept="image/png,image/jpeg,image/webp" style="display:none">' +
            (ph ? '<button class="s-btn danger-ghost" data-act="remove_photo">Remove</button>' : '') +
            '<button class="s-btn" id="photo-pick">' + (ph ? 'Change' : 'Upload') + '</button>' +
            '<span class="avatar-lg">' + (ph ? '<img src="' + ph + '" alt="">' : esc(initials)) + '</span>';
    } else if (r.type === 'text') {
      ctl = '<input class="s-input" data-key="' + r.key + '" value="' + esc(v[r.key] || '') + '" placeholder="' + esc(r.placeholder || '') + '" maxlength="120">';
    } else if (r.type === 'textarea') {
      return '<div class="s-row stack"><div class="lab"><span>' + esc(r.label) + '</span></div><div class="ctl" style="display:block">' +
             '<textarea class="s-textarea" data-input="' + r.key + '" maxlength="3000" placeholder="' + esc(r.placeholder || '') + '">' + esc(v[r.key] || '') + '</textarea>' +
             '<div style="text-align:right;margin-top:8px"><button class="s-btn primary" data-act="' + r.action + '" data-from="' + r.key + '">' + esc(r.text) + '</button></div></div></div>';
    } else if (r.type === 'lang') {
      ctl = '<span style="font-size:14px;margin-right:4px">' + esc(S.info.language_label || 'Same as my message') + '</span>' +
            '<button class="s-btn" id="lang-open">Change</button>';
    } else if (r.type === 'html') {
      ctl = r.html;
    } else if (r.type === 'meter') {
      var pct = r.limit ? Math.min(100, Math.round(100 * r.used / r.limit)) : 0;
      return '<div class="s-row stack"><div class="lab"><b>' + esc(r.label) + '</b></div><div class="meter2 ' + (pct >= 100 ? 'full' : pct >= 80 ? 'high' : '') +
             '"><i style="width:' + pct + '%"></i></div><div class="lab"><span>' + esc(r.desc || '') + '</span></div></div>';
    } else if (r.type === 'list') {
      if (!r.items.length) return '<div class="s-empty">' + esc(r.empty || '') + '</div>';
      return '<div class="s-list">' + r.items.map(function (it) {
        return '<div class="s-item"><div class="t">' + esc(it.t) + '</div>' + (it.m ? '<div class="m">' + esc(it.m) + '</div>' : '') +
               (it.button ? '<button class="s-btn ' + (it.button.style === 'plain' ? '' : 'danger-ghost') + '" data-act="' + it.button.action + '" data-value="' + esc(it.button.value) + '">' + esc(it.button.text) + '</button>' : '') + '</div>'; }).join('') + '</div>';
    }
    return '<div class="s-row" data-search="' + esc(((r.label || '') + ' ' + (r.desc || '')).toLowerCase()) + '">' + lab + '<div class="ctl">' + ctl + '</div></div>';
  }

  function renderSettings() {
    var panels = PANELS(), q = (document.getElementById('s-q').value || '').trim().toLowerCase();
    var nav = document.getElementById('s-nav');
    Array.prototype.slice.call(nav.querySelectorAll('button, .s-group')).forEach(function (n) { n.parentNode.removeChild(n); });
    var group = '';
    panels.forEach(function (p) {
      if (p.group !== group) { group = p.group; var g = document.createElement('div'); g.className = 's-group'; g.textContent = group; nav.appendChild(g); }
      var b = document.createElement('button'); b.setAttribute('data-panel', p.id);
      b.className = (!q && S.panel === p.id) ? 'active' : '';
      b.innerHTML = (SICON[p.id] || SICON.general) + esc(p.title); nav.appendChild(b);
    });
    var html = '';
    if (S.info && S.info.web) panels.forEach(function (p) {   // rows marked apps: only in the Gink apps, never on the web
      p.sections = p.sections.map(function (sec) {
        return Object.assign({}, sec, {rows: (sec.rows || []).filter(function (r) { return r && !r.apps; })}); })
        .filter(function (sec) { return sec.rows.length; });
    });
    if (q) {                               // search across every panel
      panels.forEach(function (p) {
        var hits = [];
        p.sections.forEach(function (sec) { sec.rows.forEach(function (r) {
          var hay = ((r.label || '') + ' ' + (r.desc || '') + ' ' + sec.title + ' ' + p.title).toLowerCase();
          if (hay.indexOf(q) >= 0 && r.type !== 'note' && r.type !== 'list') hits.push(rowHtml(r, p.id)); }); });
        if (hits.length) html += '<div class="s-section"><h3>' + esc(p.title) + '</h3>' + hits.join('') + '</div>';
      });
      if (!html) html = '<div class="s-empty" style="padding-top:40px">No settings match \u201c' + esc(q) + '\u201d.</div>';
    } else {
      var p = panels.filter(function (x) { return x.id === S.panel; })[0] || panels[0];
      p.sections.forEach(function (sec) {
        html += '<div class="s-section">' + (sec.title ? '<h3>' + esc(sec.title) + '</h3>' : '') + sec.rows.map(function (r) { return rowHtml(r, p.id); }).join('') + '</div>';
      });
    }
    document.getElementById('s-body').innerHTML = html;
    var vc = document.getElementById('s-voicecar');
    if (vc && typeof voiceCarousel === 'function') {
      voiceCarousel(vc, S.values.voice || VC.voice, function (key) {
        S.values.voice = key; VC.voice = key; ginkEmit('setting', {key: 'voice', value: key}); ginkEmit('voice_preview', {key: key});
      }, 170);
    }
  }

  function openSettings(panel) {
    if (panel) S.panel = panel;
    S.open = true;
    closeAcctMenu();
    document.getElementById('settings-back').classList.add('open');
    renderSettings();
    ginkEmit('settings_action', {name: 'refresh', value: S.panel});
  }
  function closeSettings() { S.open = false; document.getElementById('settings-back').classList.remove('open'); document.getElementById('s-q').value = ''; }
  function setSettingsState(st) {
    ['values', 'info', 'lists'].forEach(function (k) { if (st[k]) { for (var x in st[k]) S[k][x] = st[k][x]; } });
    if (S.info.email) document.getElementById('am-email').textContent = S.info.email;
    if (S.open) {
      var a = document.activeElement, keep = a && a.getAttribute && a.getAttribute('data-input');
      var val = keep ? a.value : null;
      renderSettings();
      if (keep) { var el = document.querySelector('[data-input="' + keep + '"]'); if (el) { el.value = val; el.focus(); } }
    }
  }
  var toastTimer = null;
  function settingsToast(text, kind) {
    var t = document.getElementById('s-toast'); t.textContent = text; t.className = 'show' + (kind === 'err' ? ' err' : '');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.className = ''; }, kind === 'err' ? 7000 : 3200);
  }
  var darkQuery = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  var appearance = {theme: 'system', font: 'sans', motion: 'system'};
  function setAppearance(theme, font, motion) {
    appearance = {theme: theme || 'system', font: font || 'sans', motion: motion || 'system'};
    var dark = appearance.theme === 'dark' || (appearance.theme === 'system' && darkQuery && darkQuery.matches);
    document.body.classList.toggle('theme-dark', !!dark);
    document.documentElement.classList.toggle('theme-dark', !!dark);   // <html> paints below short pages
    document.body.classList.toggle('font-serif', appearance.font === 'serif');
    document.body.classList.toggle('font-mono', appearance.font === 'mono');
    var reduced = appearance.motion === 'reduced' || (appearance.motion === 'system' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    document.body.classList.toggle('reduced-motion', !!reduced);
  }
  if (darkQuery && darkQuery.addEventListener) darkQuery.addEventListener('change', function () { setAppearance(appearance.theme, appearance.font, appearance.motion); });

  function closeAcctMenu() { var m = document.getElementById('acct-menu'); if (m) m.classList.remove('open'); }
  function toggleAcctMenu(anchor) {
    var m = document.getElementById('acct-menu'), r = anchor.getBoundingClientRect();
    if (m.classList.contains('open')) { closeAcctMenu(); return; }
    m.style.left = Math.max(8, Math.min(r.left, window.innerWidth - 260)) + 'px';
    m.style.bottom = (window.innerHeight - r.top + 6) + 'px';
    m.classList.add('open');
  }

  document.addEventListener('DOMContentLoaded', function () {
    var mac = /Mac|iPhone|iPad/.test(navigator.platform || '');
    document.getElementById('am-kbd').textContent = mac ? '\u2318 ,' : 'Ctrl ,';
    // account menu from the sidebar footer (gear still opens Settings directly) and the rail avatar
    document.querySelector('.side-foot').addEventListener('click', function (e) {
      if (e.target.closest('#gear')) return;
      e.stopPropagation(); toggleAcctMenu(this);
    });
    var ra = document.getElementById('rail-avatar');
    if (ra) ra.addEventListener('click', function (e) { e.stopPropagation(); toggleAcctMenu(this); }, true);
    document.getElementById('acct-menu').addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return;
      e.stopPropagation(); closeAcctMenu();
      var what = b.getAttribute('data-am');
      if (what === 'settings') openSettings('general');
      else if (what === 'usage') openSettings('usage');
      else if (what === 'language') { openSettings('general'); openLangPicker(); }
      else if (what === 'help') openSettings('help');
      else if (what === 'about') openSettings('about');
      else if (what === 'upgrade') ginkEmit('open', 'pro');
      else if (what === 'logout') ginkEmit('settings_action', {name: 'logout'});
    });
    document.addEventListener('click', function (e) { if (!e.target.closest('#acct-menu')) closeAcctMenu(); });
    document.getElementById('s-close').addEventListener('click', closeSettings);
    document.getElementById('settings-back').addEventListener('click', function (e) { if (e.target.id === 'settings-back') closeSettings(); });
    document.getElementById('s-q').addEventListener('input', renderSettings);
    document.getElementById('s-nav').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-panel]'); if (!b) return;
      document.getElementById('s-q').value = ''; S.panel = b.getAttribute('data-panel'); renderSettings();
      document.getElementById('s-main').scrollTop = 0;
      ginkEmit('settings_action', {name: 'refresh', value: S.panel});
    });
    var body = document.getElementById('s-body');
    body.addEventListener('change', function (e) {
      var t = e.target, key = t.getAttribute('data-key'); if (!key) return;
      var val = t.type === 'checkbox' ? t.checked : t.value;
      S.values[key] = val;
      if (key === 'theme' || key === 'chat_font' || key === 'motion') setAppearance(S.values.theme, S.values.chat_font, S.values.motion);
      ginkEmit('setting', {key: key, value: val});
    });
    body.addEventListener('click', function (e) {
      var seg = e.target.closest('.seg button');
      if (seg) {
        var key = seg.getAttribute('data-key'), val = seg.getAttribute('data-value');
        S.values[key] = val; setAppearance(S.values.theme, S.values.chat_font, S.values.motion);
        ginkEmit('setting', {key: key, value: val}); renderSettings(); return;
      }
      var b = e.target.closest('[data-act]'); if (!b) return;
      var name = b.getAttribute('data-act'), from = b.getAttribute('data-from'), value = b.getAttribute('data-value');
      if (from) { var inp = document.querySelector('[data-input="' + from + '"]'); value = inp ? inp.value : ''; }
      if (name === 'upgrade') { closeSettings(); ginkEmit('open', 'pro'); return; }
      if (name === 'delete_account') { confirmDanger('Delete your account?', 'Your account and everything synced to it will be permanently deleted. Type DELETE to confirm.', 'DELETE', function () { ginkEmit('settings_action', {name: 'delete_account'}); }); return; }
      if (name === 'delete_chats') { confirmDanger('Delete all chats?', 'Every conversation will be removed from this device and your other devices.', null, function () { ginkEmit('settings_action', {name: 'delete_chats'}); }); return; }
      if (name === 'forget_all') { confirmDanger('Forget everything?', 'Gink will forget everything you asked it to remember.', null, function () { ginkEmit('settings_action', {name: 'forget_all'}); }); return; }
      ginkEmit('settings_action', {name: name, value: value});
    });
    body.addEventListener('keydown', function (e) {
      var t = e.target; if (e.key !== 'Enter' || !t.getAttribute('data-input')) return;
      e.preventDefault(); var btn = document.querySelector('[data-from="' + t.getAttribute('data-input') + '"]'); if (btn) btn.click();
    });
    document.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === ',') { e.preventDefault(); openSettings(); }
      if (e.key === 'Escape' && S.open && !document.getElementById('modal-back').classList.contains('open')) closeSettings();
    });
  });

  // ---- profile photo ----
  document.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('#photo-pick')) { e.preventDefault(); document.getElementById('photo-file').click(); }
  });
  document.addEventListener('change', function (e) {
    if (!e.target || e.target.id !== 'photo-file' || !e.target.files || !e.target.files[0]) return;
    var f = e.target.files[0];
    if (!/^image\/(png|jpeg|webp)$/.test(f.type)) { settingsToast('Use a PNG, JPEG or WebP photo.', 'err'); return; }
    if (f.size > 10 * 1024 * 1024) { settingsToast('That photo is over 10 MB.', 'err'); return; }
    var r = new FileReader();
    r.onload = function () { ginkEmit('settings_action', {name: 'set_photo', value: r.result}); };
    r.readAsDataURL(f);
  });

  // ---- language picker ----
  function renderLangs() {
    var q = (document.getElementById('lang-q').value || '').trim().toLowerCase(), cur = S.values.reply_language || 'auto';
    var list = (S.info.languages || []).filter(function (l) { return !q || (l[1] + ' ' + l[2] + ' ' + l[0]).toLowerCase().indexOf(q) >= 0; });
    document.getElementById('lang-grid').innerHTML = list.length ? list.map(function (l) {
      return '<button data-lang="' + esc(l[0]) + '" class="' + (l[0] === cur ? 'sel' : '') + '"><span class="ln"><b>' + esc(l[1]) + '</b><span>' +
        esc(l[2]) + (l[3] ? ' \u00b7 experimental' : '') + '</span></span>' + (l[0] === cur ? '<span class="ck">\u2713</span>' : '') + '</button>'; }).join('')
      : '<div class="s-empty" style="grid-column:1/-1">No language matches \u201c' + esc(q) + '\u201d.</div>';
  }
  function openLangPicker() {
    document.getElementById('lang-q').value = ''; renderLangs();
    document.getElementById('lang-back').classList.add('open');
    setTimeout(function () { document.getElementById('lang-q').focus(); var s = document.querySelector('#lang-grid .sel'); if (s && s.scrollIntoView) s.scrollIntoView({block: 'center'}); }, 30);
  }
  function closeLangPicker() { document.getElementById('lang-back').classList.remove('open'); }
  document.addEventListener('click', function (e) {
    if (!e.target.closest) return;
    if (e.target.closest('#lang-open')) { e.preventDefault(); openLangPicker(); return; }
    if (e.target.closest('#lang-close') || e.target.id === 'lang-back') { closeLangPicker(); return; }
    var b = e.target.closest('#lang-grid button[data-lang]'); if (!b) return;
    var code = b.getAttribute('data-lang'), l = (S.info.languages || []).filter(function (x) { return x[0] === code; })[0];
    S.values.reply_language = code; if (l) S.info.language_label = l[1] + (l[3] ? ' \u00b7 experimental' : '');
    ginkEmit('setting', {key: 'reply_language', value: code}); closeLangPicker(); if (S.open) renderSettings();
  });
  document.addEventListener('input', function (e) { if (e.target && e.target.id === 'lang-q') renderLangs(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && document.getElementById('lang-back').classList.contains('open')) { e.stopPropagation(); closeLangPicker(); } }, true);

  // a reusable confirm dialog (re-uses the delete-chat modal)
  function confirmDanger(title, text, typeWord, onOk) {
    var back = document.getElementById('modal-back'), modal = back.querySelector('.modal');
    var old = modal.innerHTML;
    modal.innerHTML = '<h3></h3><p class="sub" style="font-size:14.5px;color:var(--text-main)"></p>' +
      (typeWord ? '<input class="s-input" id="cd-word" style="width:100%;margin-top:8px" autocomplete="off">' : '') +
      '<div class="actions"><button class="pill ghost" id="cd-cancel">Cancel</button><button class="pill danger" id="cd-ok">Delete</button></div>';
    modal.querySelector('h3').textContent = title; modal.querySelector('p').textContent = text;
    var ok = modal.querySelector('#cd-ok');
    if (typeWord) { ok.disabled = true; ok.style.opacity = 0.5;
      modal.querySelector('#cd-word').addEventListener('input', function () { var good = this.value.trim() === typeWord; ok.disabled = !good; ok.style.opacity = good ? 1 : 0.5; }); }
    function done() { back.classList.remove('open'); modal.innerHTML = old; rebindDeleteModal(); }
    modal.querySelector('#cd-cancel').addEventListener('click', done);
    ok.addEventListener('click', function () { if (ok.disabled) return; done(); onOk(); });
    back.classList.add('open');
    setTimeout(function () { var w = modal.querySelector('#cd-word') || modal.querySelector('#cd-cancel'); if (w) w.focus(); }, 30);
  }
  function rebindDeleteModal() {
    var c = document.getElementById('del-cancel'), o = document.getElementById('del-ok');
    if (c) c.addEventListener('click', closeDelete);
    if (o) o.addEventListener('click', function () {
      if (deleteFor) { ginkEmit('delete_session', deleteFor); sessions = sessions.filter(function (s) { return s.id !== deleteFor; }); renderRecents(); }
      closeDelete();
    });
  }
"""


def inject(page: str) -> str:
    """Adds the settings window + account menu to the chat page template."""
    import json as _json
    html = SETTINGS_HTML
    for name in ICONS:
        html = html.replace(f"__I_{name}__", icon(name))
    sicons = {k: icon(k) for k in ICONS}
    js = SETTINGS_JS.replace("__SICONS__", _json.dumps(sicons))
    # the page is already built (placeholders filled), so append to its style block
    assert "</style>" in page
    page = page.replace("</style>", SETTINGS_CSS + "</style>", 1)
    page = page.replace("<script>", html + "\n<script>", 1)
    i = page.rindex("</script>")
    return page[:i] + js + page[i:]
