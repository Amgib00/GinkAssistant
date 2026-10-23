## 1. Server

- [ ] 1.1 connections table; seal refresh tokens; delete on disconnect and with the account
- [ ] 1.2 OAuth connect/disconnect per service with incremental scopes; reuse the sign-in callback handling
- [ ] 1.3 /connected/google/calendar/upcoming, /connected/google/gmail/search, /connected/google/drive/search
- [ ] 1.4 Writing actions: create event, create email draft, send email (always approval-gated)
- [ ] 1.5 Tests with Google simulated: scopes, refresh, revoked grant, deletion, no contents stored

## 2. Apps and web app

- [ ] 2.1 Settings > Connected Apps (apps + web): connect, what Gink can do, disconnect
- [ ] 2.2 Agent tools calendar_upcoming, email_search, drive_search, create_event, draft_email, send_email
- [ ] 2.3 Tests: tools through the agent, approvals for writing actions

## 3. Checks

- [ ] 3.1 Real-browser check of connecting and asking "what's on my calendar tomorrow?"
- [ ] 3.2 On-device check on the TECNO (32-bit Android)
- [ ] 3.3 Full tests on Python 3.12 and 3.10; openspec validate --all --strict
