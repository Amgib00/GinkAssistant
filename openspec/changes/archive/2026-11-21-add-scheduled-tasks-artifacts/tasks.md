## 1. Build
- [x] 1.1 Server: chat_tasks, next-run times in the person's time zone, the task runner (search, pages, limits, family and workspace rules, retry), results into synced chats and email, `/tasks` and `/v1/tasks`, OpenAPI
- [x] 1.2 Chats: SCHEDULE_PROMPT (apps, web app, server), task cards, the apps' agent `schedule_task`, quick reminders on a repeat left to the AI, notifications when results arrive (apps and web app)
- [x] 1.3 Settings > Scheduled tasks (and the sidebar), Genie and console agent schedules on weekdays
- [x] 1.4 Artifacts: titled blocks, cards, the viewer (preview, code, document, versions), Mermaid, the sealed frame and new tab
- [x] 1.5 The web and code: services/web_reader.py, services/code_reader.py, actions/codebase.py, higher abilities
- [x] 1.6 Sign-in (web and apps) with Gink Pro; about_gink; website, features, pricing, developers, blog
- [x] 1.7 SDKs 0.3.16 (tasks, artifacts, schedules_in / schedulesIn) and the CLI (gink tasks, --save-artifacts, --schedule, --no-auto)

## 2. Check
- [x] 2.1 Tests: tests/test_scheduled_tasks.py, tests/test_artifacts.py, tests/test_codebase_and_web.py
- [x] 2.2 Real browser (Chromium): task cards (new, reopened, paused, failed; light, dark, phone), Settings > Scheduled tasks, artifacts in dark mode, the sealed tab against a running server, the sign-in pages (web and apps, light, dark, phone), the website section
