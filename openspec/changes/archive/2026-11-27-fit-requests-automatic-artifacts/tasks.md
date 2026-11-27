## 1. Build
- [x] 1.1 services/context_fit.py: estimates, earlier versions left out, fitting by levels, Groq's refusals read, scrubbed and said plainly; the server image copies it
- [x] 1.2 Server: _fit_request (every model in order, the chosen one with more left out), limits learned from headers and refusals, 413/429 asked again, _groq_post for Gink's own loops, plain words for people and scrubbed errors for developers, gink_fit, X-Gink-Model, room to make an artifact on a short follow-up
- [x] 1.3 Apps: one copy of each artifact in the history (chat and agent), fitting when talking to Groq directly, plain-words errors (groq_worker, tool_slips, agent.AIRefused); the web app never shows a provider's message
- [x] 1.4 Automatic: ASK_PROMPT (apps and web app), DEFAULT_SYSTEM_PROMPT, ARTIFACT_PROMPT (server, apps, web app) with the new kinds and finished quality
- [x] 1.5 Question cards: the typed answer, Enter, "Other" options left out, closing one answer's cards
- [x] 1.6 Artifacts: react, chart, table and slides kinds with previews, downloads and publishing; the SDKs' kinds; `gink chat` fits long chats
- [x] 1.7 Web app: quick formatting while answers arrive and for opened chats, remembered formatting, answered cards closed, history formatted as history
- [x] 1.8 Markdown: numbered lists after bulleted ones stay apart
- [x] 1.9 Website: versioned styles and scripts, the build mark, older pages loaded fresh, a hero that is dark by itself; features, blog and developer pages

## 2. Check
- [x] 2.1 Tests: tests/test_context_fit.py, tests/test_automatic_and_artifacts.py, tests/test_ai_errors.py, the full suite on Python 3.11 and 3.13 (also as a non-root user with CI's variables)
- [x] 2.2 Real browser (Chromium): question cards, quick formatting, the four new artifact kinds, the built web app opening a chat, the website's older page loading fresh
