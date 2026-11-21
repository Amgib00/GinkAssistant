## Why

The owner showed three problems: asking "can you run some check for why my camera is not working" ended in
"[error] Tool choice is none, but model called a tool" under a spinner that never stopped; a photo of Gink's own icon
was called "the Snowflake logo", and videos couldn't be attached at all; and Gink's notifications ("Privacy policy and
terms updated") only showed inside the window, never in the Mac's Notification Center. He asked for the fix, for the
tools to be automatic, for notifications to go to the Mac, "and all" -- including the GitHub checks that kept failing
(Dependabot's pull requests, "Bad credentials" in the pull request automation, GitHub's coming `pull_request_target`
restriction).

## What Changes

- Tool slips (a model calling a tool it wasn't given, calling one that isn't in the list, or writing a broken call)
  are asked again by the server -- as plain text, then on another model -- before the answer or inside a streamed one,
  for chat completions, managed agents, scheduled tasks, Sites, search and Genie. The apps do the same for their own
  calls, and an answer always ends in plain words: never a raw error, never a spinner left behind.
- Automatic tools: the apps' chats let the AI hand a request to Gink's own tools (a hand-off tool, or a slip, becomes
  `use_tools`); the agent runs it in the same reply. Device trouble ("my camera isn't working") goes to the tools, and
  the device check can focus on the camera or the microphone.
- Notifications on the device: every notification card also goes to Notification Center on a Mac (Gink's own, from
  the built app), Windows, Linux, Android and iPhone -- a banner when Gink isn't in front, quietly in the Mac's list
  while it is; the web app uses the browser's notifications. A setting and a test.
- Videos: the chat page takes a few frames in order and they go to the AI as pictures with a sentence saying what they
  are (apps, web app, SDKs, CLI). Gink knows its own logo.
- GitHub: Dependabot's newer minimums pass the requirements check (and are taken), the pull request automation moves
  to `pull_request` + `workflow_run`, the project step only warns, tests never reach the internet, and a tool closes
  Copilot Autofix pull requests whose alert is already fixed.

## Out of scope

- Notifications while a phone app is fully closed (they arrive with the next sync); notification action buttons.
- Sending the video itself, its sound, or more than five pictures per question.
- Closing pull requests or dismissing alerts from here: the tool runs with the owner's own `gh` login.

## Platforms

Server, macOS (Catalina too), Windows, Linux, Android, iOS, the web app, Gink Genie, the API and managed agents, the
CLI and both SDKs (gink-ai 0.3.17).
