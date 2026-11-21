## 1. Build
- [x] 1.1 Server: _tool_slip / _after_slip / _without_tools, the event-by-event relay, _groq_post for Gink's own loops (agents, tasks, Sites, search, Genie), the hand-off tool and `use_tools`
- [x] 1.2 Apps: services/tool_slips.py, the brain's stream errors and UseTools, main_screen always finishing the reply row, the agent's retries and last plain-text word
- [x] 1.3 Automatic tools: X-Gink-Actions, device trouble detection, device_check focus (camera, microphone)
- [x] 1.4 Notifications: services/system_notify.py (UserNotifications from the built app, osascript, Windows, Linux, Android), the chat's mirrored cards, Settings (setting and test), the web app's browser notifications
- [x] 1.5 Videos: frames on the chat page, attachments.video_attachment / picture_parts, the web app, the SDKs (watch, video_parts / videoParts, videoFrames) and `gink watch`; Gink's logo in about_gink
- [x] 1.6 GitHub: dependency minimums, the requirements check, pull-requests.yml + pull-request-triage.yml, tests.yml, tests/conftest.py, tools/close_fixed_alert_prs.py

## 2. Check
- [x] 2.1 Tests: tests/test_tool_slips.py, tests/test_automatic_tools.py, tests/test_device_notifications.py, tests/test_video_attachments.py, the full suite on Python 3.11 and 3.13 (also as a non-root user with CI's variables)
- [x] 2.2 Real browser (Chromium): video frames from a dropped clip and a broken one, the chat page's scripts
