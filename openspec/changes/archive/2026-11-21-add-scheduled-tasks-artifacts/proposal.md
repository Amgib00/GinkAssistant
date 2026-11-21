## Why

The owner asked for "Automatic Artifacts, Schedule, gink should automatic work with its codebase, automatic use the
internet, high abilities, upgrade the website, login ... add premium". Gink answered and then stopped: it couldn't do
anything later or on a repeat, finished pages and documents were long code blocks in the middle of a chat, a pasted
link was guessed at rather than read, it couldn't see a GitHub repository or the code on the person's computer, and
every answer had the same room and thought whatever the question. The sign-in page was plain and said nothing about
what Gink or Gink Pro can do.

## What Changes

- Scheduled tasks for everyone: `/tasks` (session) and `/v1/tasks` (API key). The server runs a task at its local
  time -- once, hourly (Pro), daily, weekdays, weekly or monthly -- with web search and page reading, and writes the
  result into the task's own synced chat (and an email if asked). Made from a chat (```schedule blocks become cards;
  the apps' agent gets `schedule_task`), Settings > Scheduled tasks and the sidebar, the SDKs and the CLI. Free 3,
  Pro 25. Agent schedules (Genie) can run on weekdays.
- Artifacts: titled fenced blocks become cards that open in a viewer (live preview, code, versions, copy, download,
  a sealed tab on the web); `gink_artifacts` for developers; `artifacts()` in both SDKs; `--save-artifacts`.
- The web by itself: pages linked in a question are read by the server (public addresses only) and the web is
  searched when the answer needs it; `gink_web: "auto"` for developers.
- Code: GitHub repositories (and Gink's own source) read by the server; on computers, the agent maps projects,
  searches code and runs the project's own tests, linter or build.
- Higher abilities: more room for things being built, more reasoning for hard questions.
- A premium sign-in on the web and in the apps, with Gink Pro; the website, features, pricing, developers and blog.

## Out of scope

- Push notifications to phones while the app is closed (results arrive with the next sync and by email).
- Running arbitrary commands from the AI; private GitHub repositories; editing GitHub repositories.
- A new paid tier: Free and Pro stay as they are, with Pro's task limits.

## Impact

- Platforms: apps (macOS incl. Catalina, Windows, Linux, Android, iOS -- code tools on computers only), web app,
  server, Genie, API, SDKs (0.3.16), CLI, website.
- Server: new table chat_tasks; the schedules loop also runs tasks; `/artifact/frame`; Mermaid and Lexend served
  from deploy/vendor; GITHUB_TOKEN recommended.
