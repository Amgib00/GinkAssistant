# Changelog

## 0.1.30 (October 2026)

- Gink Genie: the lamp now faces right, and the whole genie (with its smoky tail) rises from the
  "Describe a task" box instead of a round picture

## 0.1.29 (October 2026)

- Temporary chats: press Temporary on the new-chat screen for a chat that isn't saved, isn't
  synced, doesn't appear in Recents, and is gone when you leave it
- Fixed the shared-link window's colours in dark mode

## 0.1.28 (October 2026)

- Gink Genie's new lamp icon (in the menu and as the app icon: a lime lamp, like Gink's snowflake)
- The genie comes alive: it rises out of magic smoke, floats, sparkles, talks when you point at it,
  leans in while you type, and works its magic while building (it stays still if you turn off
  animations in your system settings)

## 0.1.27 (October 2026)

- Share a chat: choose Share link in a chat's menu to get a read-only link anyone can open (a
  snapshot: later messages aren't added). Manage and delete links in Settings > Privacy > Shared links

## 0.1.26 (October 2026)

- Gink Genie is now also its own app for Mac, Windows, Linux and Android (including 32-bit phones),
  with the lamp icon: download it next to Gink. It signs in with your Gink account

## 0.1.25 (October 2026)

- Gink Genie has its own look: a lamp in the sidebar and header, and the genie sitting on the
  "Describe a task" box, whose + button uploads a project

## 0.1.24 (October 2026)

- Gink Genie uploads to GitHub: connect GitHub once, then push a project to a new or existing
  repository (private by default) as a commit -- push again after changes and it adds a new commit

## 0.1.23 (October 2026)

- Gink Genie runs your code: press Run on a Python or JavaScript file, or Run tests (pytest), and
  see the output below the editor. It runs safely inside your browser, never on the server

## 0.1.22 (October 2026)

- Gink Genie (sidebar > Gink Genie): describe an app, website, game or script and Genie builds the
  whole project, file by file. Keep changing it together in the chat, edit files yourself, preview
  web projects, download them as a ZIP, or upload your own project for Genie to work on

## 0.1.21 (October 2026)

- Web app: after Gink builds your website, follow-ups like "good, add more to it" or "make it blue"
  now update that website (Gink used to answer that it couldn't edit it)

## 0.1.20 (October 2026)

- Web app: opening an older chat could show its answers stuck on "Thinking..." when the server was
  slow to respond. Answers now appear straight away, and get their formatting when the server answers

## 0.1.19 (October 2026)

New abilities (ask Gink in a chat):
- A money book: "I sold 3 bags of rice for 45,000 CFA", "I spent 5,000 on fuel", "how much did I
  spend this month?" -- totals by category, every currency kept separate, kept on your device
- Invoices as PDF: "make an invoice for Awa: 2 dresses at 15,000 each"
- Loan calculator, splitting a bill (with tip), converting units (km/miles, kg/lb, °C/°F,
  hectares/acres, litres/gallons...), strong passwords, coin / dice / random picks
- QR codes for links, phone numbers and Wi-Fi

## 0.1.18 (October 2026)

- New support address: gink@ginkaisupport.com (website, privacy policy, terms, account deletion
  and Settings > Help)

## 0.1.17 (October 2026)

- Continue with phone: sign up and sign in with a phone number and an SMS code (on the web
  sign-in page), and add a phone number to your account in Settings > Account. Works with
  Africa's Talking or Twilio; the owner dashboard shows this month's SMS against a monthly cap

## 0.1.16 (October 2026)

- gink CLI 0.2.1: when you're not signed in it simply says "Run: gink login" (which signs you in
  through your browser). Publishing the CLI checks PyPI first and explains if the version is taken

## 0.1.15 (October 2026)

- Releases are more reliable: publishing works when the update commands are pasted all at once,
  releases run one at a time, and the release reads its version from the code

## 0.1.14 (October 2026)

- "gink login" signs in through your browser: approve a short code at /device and the CLI gets
  its own key (gink CLI 0.2.0; "gink login --key" still lets you paste a key)

## 0.1.13 (October 2026)

- Passkeys: sign in on the web with your fingerprint, face or device PIN -- no password, and
  phishing-proof. Add them in Settings > Account > Passkeys (in a browser); see and remove them
  in the apps too

## 0.1.12 (October 2026)

- Archive chats (from a chat's menu, or "Archive all" in Settings > Privacy): they leave Recents,
  sync to your other devices, and come back with Unarchive
- Settings > Storage: what Gink keeps on this device (chats, images, files, offline AI, "Hey Gink"
  model, song data) and freeing space
- Usage limits say when they reset in your own time, and the web app tells you when you can send
  messages again

## 0.1.11 (October 2026)

- Settings > Personalization: choose Gink's style (professional, friendly, concise, candid, playful)
  and how much warmth, enthusiasm, emoji, headers and lists it uses
- Settings > Account > Security history: sign-ins, wrong passwords, two-step changes, signed-out
  devices, API keys and connected apps, with the device
- Settings > Privacy > Lockdown mode: protection against hidden instructions in web pages and
  emails -- turns off web search, connected apps and images from web addresses, on every device
- Settings > Privacy states plainly: Gink never trains AI on your chats and uses no tracking cookies

## 0.1.10 (October 2026)

Security fixes from an audit of every server route:
- Email sign-in codes only sign in existing accounts (an unknown address used to get an
  account-less sign-in); such addresses get a note about creating an account instead
- Code emails (sign-up, password reset, email sign-in) are limited per address: no flooding
  anyone's inbox. Sign-in codes now use a cryptographic random generator
- Checked: every route that should need a sign-in does, and payment notifications can't be faked

## 0.1.9 (October 2026)

- A full sign-in page for the web (/login, /signup, /forgot): log in, create an account (with
  password rules as you type), confirm your email, forgot password, "email me a sign-in code",
  two-step verification, Google / GitHub / Microsoft / Apple, Remember me, and back to where you were
- Security fix: signing in with an emailed code now asks for your two-step code and shows up in
  Signed-in devices (it skipped both before)

## 0.1.8 (October 2026)

- Connected apps (Settings > Connected apps): connect Google Calendar, Gmail and Google Drive, one
  at a time. Ask "what's on my calendar tomorrow?", "did Awa email me about the budget?" or "find my
  budget spreadsheet". Gink always asks before adding an event or writing or sending an email, never
  keeps what it reads, and disconnecting removes its access at Google too

## 0.1.7 (October 2026)

- The Gink Developer Console (/developers): Dashboard, Playground (with ready-to-copy code),
  API keys, Usage per key, Metrics (requests, errors, response times, tokens, models), Logs
  (never the contents of requests), Batches and Docs
- Batch API: up to 100 chat requests at once (POST /v1/batches), processed in the background,
  results as JSONL; batches carry on after a server restart

## 0.1.6 (October 2026)

- Websites: "make me a website for my bakery" -> Gink builds it and gives you a link to share;
  "change my website: ..." updates it. Settings > Account > Your websites. Pages are sandboxed
  (they can't touch Gink sign-ins or send data anywhere), have no password fields, and show
  "Made with Gink"

## 0.1.5 (October 2026)

(Not released on its own -- these changes reached everyone in 0.1.6.)

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
