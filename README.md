<p align="center"><img src="icons/ginkassistant-256.png" width="128" alt="Gink"></p>

<h1 align="center">Gink</h1>
<p align="center"><b>Think. Talk. Create.</b> -- an AI assistant for macOS, Windows, Linux, Android and iOS.</p>

<p align="center">
  <a href="../../actions/workflows/tests.yml"><img src="../../actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="../../actions/workflows/android.yml"><img src="../../actions/workflows/android.yml/badge.svg" alt="Android build"></a>
  <a href="../../actions/workflows/ios.yml"><img src="../../actions/workflows/ios.yml/badge.svg" alt="iOS build"></a>
</p>

Built with Python and [BeeWare](https://beeware.org) (Toga + Briefcase).

## What Gink does
- **Chat** with streaming answers, chat history that saves itself, smart titles, drafts
- **Voice**: natural voices, voice conversations, and **"Hey Gink"** (wake word detected on the device)
- **Does things**: alarms, reminders, tasks, files (PDF, Word, Excel...), images, weather,
  currency and maths; on desktop also apps, Finder, Terminal, music, volume, screenshots, notes
- **Morning briefing** that picks up where you left off
- **Sync** across devices, Gink Pro with local payment methods, light and dark themes

## Run it on your computer
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env    # then add your keys -- .env is never committed
python -m ginkassistant
```

## Build the app
Run Briefcase from this folder. Apps are built in `build/ginkassistant/<platform>/...`.
```bash
python -m briefcase create macOS && python -m briefcase build macOS && python -m briefcase run macOS
```
- **macOS 10.15 Catalina:** use Briefcase 0.3.15 (newer Briefcase makes apps that need macOS 11+);
  `requirements.txt` picks the right version.
- **Android** and **iOS** are built on GitHub (Actions tab) -- see `deploy/IOS_AND_WEB.md`.
- Check your setup any time: `python tools/check_project.py` (`--fix` repairs it).
- New icon: replace `icons/source-icon.png`, run `python tools/make_icons.py`.

## Tests
```bash
pip install -r requirements-test.txt
python -m pytest tests
```

## Gink on the web
The Gink server also serves a web version at `/app` -- on your computer,
`http://localhost:8000/app` while Gink is running. It's the app's own chat page plus a
browser bridge (`webapp/`), built with `python tools/build_web_app.py`: sign in, chat,
images, natural voices, dictation, and chats that sync with the desktop app.
Alarms, tasks and computer control stay in the app.

## Website
The site lives in `website/` (one shared layout in `tools/build_website.py`). Preview it with
`python tools/build_website.py` and open `website/_site/index.html`. It's published on GitHub
Pages automatically. To show Gink Pro prices, set them in `website/assets/pricing.js`.

## Server
Gink's AI, voices, images, sync and payments go through your own server, so no keys are
inside the app. Deploying it (Render, Docker) and its settings: `deploy/README.md`.

## License
MIT -- see `LICENSE`.
