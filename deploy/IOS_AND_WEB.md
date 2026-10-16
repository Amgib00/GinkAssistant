# Building Gink for iOS (and the web)

## iOS -- built in the cloud
Briefcase needs **Xcode 26** (Apple's minimum for the App Store since April 2026),
and Xcode 26 needs **macOS 15 or later**. A Mac on macOS 10.15 Catalina can't
build iOS apps, so Gink builds on a GitHub-hosted Mac instead:

1. Put the project on GitHub (a private repository is fine).
2. GitHub -> **Actions** -> **iOS build** -> **Run workflow** (it also runs on every
   push to `main` that changes the app).
3. When it finishes: open the run -> **Artifacts** -> `Gink-iOS-Simulator`.

The workflow first checks that every module starts with only the iOS packages
(`tests/test_ios_startup.py`), then runs `briefcase create iOS` and
`briefcase build iOS` on macOS 26 + Xcode 26 with Python 3.13.

Costs: GitHub Actions is free for public repositories. Private repositories get
free minutes each month, and macOS minutes count 10x -- one build takes roughly
15-30 minutes.

### On a real iPhone / TestFlight / App Store (next step)
Needs the **Apple Developer Program** (99 USD a year) and signing: a
distribution certificate + provisioning profile stored as GitHub secrets, then
`briefcase package iOS`. Can be added to the workflow once you have the account.

### What works on iPhone
Chat, Gink Cloud AI, sign-in, sync, history, tasks, briefing, files, images
(server). Not yet on iPhone: voice input/output, "Hey Gink", computer control
(Mac/PC only), Live TV players.

## Web -- why Briefcase's web build isn't used
Toga's web backend is a proof of concept ("most widgets have not been
implemented"), and Gink's interface is built on the WebView widget, so
`briefcase build web` would not produce a working Gink. Libraries such as
PyAudio, Vosk and pygame also can't run in a browser.

The practical route to "Gink in the browser" is a **web version served by your
Gink server**: the chat page Gink already uses (HTML/JavaScript) talks directly
to the server's existing APIs (sign-in, AI, sync, images, voices) instead of to
Python inside the app.
