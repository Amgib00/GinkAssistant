## 1. Build
- [x] 1.1 services/link_kinds.py: the sites and kinds, previews (Open Graph, JSON-LD, oEmbed, Bluesky), the shield, the AI's note, the chat's working words; copied into the server image
- [x] 1.2 services/web_reader.py: one safe way out (public addresses, redirects and peer checked, sizes by type, honest User-Agent), official previews at once, pictures looked at and audio heard through the server, PDFs and Word files, a 10-minute cache
- [x] 1.3 Server: links opened for every chat (and the previous message's for a short follow-up), the vision model and Whisper, an allowance per person, lockdown and parental controls, POST /links/read and /v1/links/read; automatic search skipped in lockdown
- [x] 1.4 Agents: read_page opens with the reader first (managed agents, scheduled tasks, Genie); Genie opens a request's links first; the apps' agent gets read_link (off with "Search the web"); own-key apps open links on the device
- [x] 1.5 Clients: "Looking at the reel..." in the apps and the web app (the same words), a link's own words aren't a search; Gink knows it opens links (both copies)
- [x] 1.6 SDKs and CLI: client.links.read / read_link, gink.links.read / readLink with types, gink read URL ["question"]; READMEs, website (features, developers, blog), changelog

## 2. Check
- [x] 2.1 Tests: tests/test_links_seen_and_read.py (a simulated internet), updated reader tests, the full suite on Python 3.11 and 3.13 (also as a non-root user with CI's variables)
- [x] 2.2 Real browser (Chromium): the web app's working words for a link while the answer comes
