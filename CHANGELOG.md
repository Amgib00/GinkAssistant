# Changelog

## 0.1.5 (October 2026)

- Gink in your terminal: `pip install gink-ai`, then `gink "question"`, a chat (`gink`), piped files,
  web search (`-s`) and images (`--image`), with your Developer API key
- The Developer API has its own OpenAPI description (/v1/openapi.json); requests without a model
  use Gink Crystal
- Security: the server no longer publishes an automatic list of all its endpoints (/docs)

## 0.1.4 (October 2026)

- Android: voice works -- speak to Gink (the mic button and voice conversations), hear answers in
  the natural Gink voices (the phone's own voice when offline), and say "Hey Gink" while Gink is
  open (Settings > Voice). Say it in one go -- "Hey Gink, what's the weather?" -- and Gink answers

## 0.1.3 (October 2026)

- Agent mode: Gink carries out multi-step tasks and shows each step as it goes, and asks before
  sensitive actions (sending messages, calls, deleting, locking or sleeping the computer).
  Settings > Capabilities > "Ask before sensitive actions"
- Security: Settings > Account lists your signed-in devices; sign out any of them, or all
  others at once (they're refused immediately). "Log out" now ends the session on the server.
  The server also tells browsers to use HTTPS only, and checks who issued Google, Microsoft and
  Apple sign-ins
- Two-step verification: Settings > Account. After your password (or email code, or Google,
  GitHub, Microsoft, Apple -- and after a password reset), Gink asks for a code from an
  authenticator app. 10 one-time recovery codes. The authenticator key is stored encrypted
- Languages: Gink answers in the language you write in (it used to drift into English), and voice
  understands any language: Settings > Voice > Language > "Automatic" (the new default) uses
  Whisper on your server, which detects the language itself
- Offline song recognition works: it can learn songs and recognise them (it never could before)
- Security updates: newer anyio and cryptography (Apple Silicon); the app no longer ships pytest
- Email works on Render's free plan: codes are sent through Brevo's web API (Render blocks
  email ports there). The owner dashboard can send a test email and shows why one failed
- Settings > Location: see your area, detect your approximate location, and turn location off
  completely (Gink then asks when it needs a place)

## 0.1.2 (October 2026)

- Android: Gink now asks for the microphone (voice, "Hey Gink") and can set alarms
- When Gink can't reach its server, it says why and what to do (for example, check the
  phone's date and time, or Wi-Fi and mobile data)

## 0.1.1 (October 2026)

- A 32-bit Android edition for phones such as TECNO POP and itel
- Gink can search the web and shows its sources
- Photos work again (Groq retired the previous photo model)
- Update notices: Gink tells you when a new version is out
- Windows and Linux installers
- Clearer sign-in on the web when the sign-in window is closed

## 0.1.0 (October 2026)

The first public beta of Gink.

- Chat with streaming answers, chat history that saves itself, smart titles and drafts
- Voice: natural voices, voice conversations, and "Hey Gink" detected on the device
- Actions: alarms, timers, reminders, tasks, files (PDF, Word, Excel...), images, weather,
  currency and maths; on computers also apps, folders, music, volume and screenshots
- Web search with sources, and a morning briefing that picks up where you left off
- Sync across devices; sign in with email, Google, GitHub, Microsoft or Apple
- Gink on the web, the Gink Developer API, and Claude models with Gink Pro
- Apps for Mac, Windows, Linux and Android
