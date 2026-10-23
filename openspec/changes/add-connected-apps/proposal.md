## Why

People ask Gink about things that live in their other apps -- "what's on my calendar tomorrow?",
"did Awa email me back?", "find the budget spreadsheet". Today Gink can't see any of it, so it
answers in general terms or asks them to copy and paste. Connected Apps lets a person link an
account, with clear permission, so Gink can read (and, with approval, act on) that information.

## What Changes

- Settings > Connected Apps: connect and disconnect Google (Calendar, Gmail, Drive), one at a
  time, each showing exactly what Gink can do with it.
- New agent tools that read from a connected app: upcoming events, recent or searched emails,
  Drive file search. Writing actions (create an event, draft or send an email) go through the
  existing agent-mode approvals and are always asked about.
- The server keeps each connection's tokens encrypted, refreshes them, and forgets them on
  disconnect or account deletion.

Out of scope for this change: Microsoft 365, WhatsApp, Slack and other services; background
syncing or notifications; any feature that stores email or calendar contents on the server.

Platforms: server (OAuth, token storage, tool endpoints), web app, macOS, Windows, Linux,
Android (64-bit and 32-bit) -- through the server, so no new app libraries.

## Impact

- New spec: connected-apps.
- Affects: agent-mode (new tools, always-ask writing actions), accounts-security (deletion also
  removes connections), developer-api (unchanged: connections are never exposed to API keys).
- Google requires an OAuth consent screen review for Gmail scopes before public use; until then
  only test users can connect Gmail.
