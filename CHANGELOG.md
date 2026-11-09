# Changelog

## 0.1.142 (November 2026)

- Gink Genie fixes its own mistakes: before answering it checks that every file its pages link to really
  exists (like style.css and script.js) and creates any it forgot; after each change it checks the live
  preview and, if there are errors, fixes them by itself -- up to 3 times, then tells you. Switch it off
  in Genie's settings ("Fix preview errors")

## 0.1.141 (November 2026)

- When the privacy policy or terms change in an important way, Gink now says so once -- a short notice
  with both links in the apps, the web app, Gink Genie and the developer console -- as the policies promise

## 0.1.140 (November 2026)

- The terms of use cover today's Gink: Gink isn't medical advice (and healthcare workspaces must not hold
  patient data); who is responsible in a workspace; rules for developers using the API, agents, scheduled
  tasks and webhooks (keep keys secret, fair-use limits); and what sharing to "Help improve Gink" allows

## 0.1.139 (November 2026)

- The privacy policy now describes everything Gink does today: error reports, the "Help improve Gink"
  choice, workspaces and healthcare mode, parental controls, time zone and language, Gink Genie projects,
  agents and scheduled tasks, result emails, webhooks, phone sign-in, photos in Media Studio, and the
  complete download and deletion of your data

## 0.1.138 (November 2026)

- Deleting your account removes everything: a final sweep now clears any table that names the account,
  including ones future features add. Only anonymised payment records (kept for tax) remain

## 0.1.137 (November 2026)

- Download everything on the server (Settings > Privacy): one ZIP with your Gink Genie projects as real
  files, your websites, agent runs, scheduled tasks and every account record Gink keeps -- never your
  password, keys or tokens. Also `gink export` and export_account() / exportAccount() in the SDKs (0.3.6)

## 0.1.136 (November 2026)

- Fair use for agents: an account can have up to 3 agent runs going at once (more are refused with a
  clear message); a scheduled task that finds you busy simply tries again 5 minutes later

## 0.1.135 (November 2026)

- "Email me the result": a scheduled task can email you its answer, the files it changed and a link to
  open them, as soon as it finishes -- even with Gink closed. In Settings > Scheduled tasks, Gink Genie's
  "Run on a schedule", the developer console, the API (notify_email), both SDKs (gink-ai 0.3.5) and the
  command line (--email)

## 0.1.134 (November 2026)

- Scheduled tasks for everyone: Settings > Scheduled tasks in the Gink apps and the web app ("every
  morning at 8, write today's top news in news.md"), and "Run on a schedule" (the clock button) in any
  Gink Genie project -- the results show up in the project's conversation. The same schedules as the
  console, the API, the SDKs and the command line

## 0.1.133 (November 2026)

- Webhooks for agents: give a run or a schedule a webhook address and Gink tells your server the moment
  it finishes -- signed, so your server can check it's really Gink. In the API, the console (Agents),
  both SDKs (with verify_webhook / verifyWebhook; gink-ai 0.3.4) and the command line (--webhook)

## 0.1.132 (November 2026)

- Scheduled agents: have Gink's agent run a task every hour, day or week at your local time -- for
  example "every morning at 8, update report.md with today's news". Results wait in the workspace (and
  in Gink Genie). In the developer console (Agents > Schedule it), the API (/v1/schedules), both SDKs
  (gink-ai 0.3.3) and the command line (gink schedule add)

## 0.1.131 (November 2026)

- For the owner: paraphrase.py and translate.py label new rows "Gink (via openai/gpt-oss-120b)" -- Gink's
  name plus an honest record of which model wrote them; --label sets another label

## 0.1.130 (November 2026)

- For the owner, Gink's own model: the training data now covers the whole world -- the same actions with
  places, currencies, time zones and names from every continent (Tokyo, São Paulo, Mumbai, Cairo, yen,
  rupees, reais...), added alongside the existing examples, which stay exactly the same so your rewrites
  and translations still match. 1,343 examples (from 683)

## 0.1.129 (November 2026)

- The JavaScript SDK is on npm: `npm install gink-ai` (0.3.2). New versions are now staged by GitHub and
  go live when you approve them on npmjs.com with your phone, so nobody can publish Gink's SDK without you
- Small fixes: no more package.json warning when publishing; the SDK can't accidentally depend on itself

## 0.1.128 (November 2026)

- For the owner, GitHub: running Release with an older version number now releases the newer code
  (it includes the older changes) instead of failing; running it twice is no longer a red failure
- The JavaScript SDK's npm publishing explains the one-time first publish (npm only trusts a workflow
  for a package that already exists) and accepts an NPM_TOKEN for it

## 0.1.127 (November 2026)

- Media Studio's looks everywhere: the same Ideas (Statue, Chibi keychain, Football figurine...) and styles
  work in the apps, the web app, the API, the SDKs and the command line
- Start an image from a photo everywhere: attach one photo in the web app and ask for an image; or use
  "photo" in the API, photo= in the SDKs, --photo in the command line (use photos of people who agreed)
- For developers: GET /v1/images/ideas; image requests accept size, aspect_ratio, a style key or your own
  words, and idea + subject; `gink ideas`; gink-ai 0.3.2

## 0.1.126 (November 2026)

- Gink is international: answers fit your own country automatically -- your local time, currency, units
  and examples -- from your device's time zone and region (no location lookup). "What's the weather?"
  without a place now means where you are. This works in chat, Gink Genie, agents, the developer
  console, the command line and the SDKs (gink-ai 0.3.1)
- Examples and placeholders are no longer about one country (they follow where you are, or are neutral)

## 0.1.125 (November 2026)

- Developer console > Agents: give Gink's agent a task right in the browser (no API key needed),
  watch each step live, read the answer, see recent runs -- from the console or your API keys -- and
  open any workspace in Gink Genie with one click

## 0.1.124 (November 2026)

- The Gink SDK for JavaScript and TypeScript (npm: gink-ai): `import { Gink } from "gink-ai"`, then
  gink.interactions.create / stream (live steps) for managed agents, gink.environments for the
  workspaces, gink.chat / search / image -- with full TypeScript types. Works in Node 18+, Deno and Bun

## 0.1.123 (November 2026)

- The Gink Python SDK (in gink-ai 0.3.0): `from gink import Client`, then
  client.interactions.create(input=..., environment="remote") for a managed agent (stream=True for live
  steps), client.environments for the workspaces, client.chat / search / image. Uses the key from
  `gink login` or GINK_API_KEY

## 0.1.122 (November 2026)

- Live information everywhere: Gink Genie can now search the web (with sources) and knows today's date;
  API agents know the date and time, get live data (weather, exchange rates, prices) when asked, and
  search the web; websites use the current year
- API agents in real time: "stream": true sends each step the moment it's done
- Agents, Genie and the CLI work together: what an API agent did appears in that project's conversation
  in Gink Genie, and "gink env" lists, creates, downloads, uploads and deletes the agents' workspaces

## 0.1.121 (November 2026)

- Managed agents in the Gink API: one request runs Gink's agent in its own workspace -- it plans,
  searches the web, reads and writes files, and the workspace keeps its files for next time. Continue a
  task later, run long ones in the background, and open the same files in Gink Genie. Guide:
  /developers/agents; in the terminal: gink agent "task"

## 0.1.120 (November 2026)

- Fixed: since 0.1.111 the online server couldn't load its new file-storage part, so its health check
  failed and Render refused every new version. The server now starts again with all the newer features
- Security checks on GitHub that need no paid account: the server's Dockerfile (Hadolint) and its
  packages (pip-audit); tools/close_scanner_prs.sh closes the scanner pull requests that can only fail

## 0.1.119 (November 2026)

- Turning on object storage keeps everything: big Gink Genie files saved on the server's disk before
  are found there and moved into object storage the first time they're opened

## 0.1.118 (November 2026)

- Behind the scenes: a safety check now runs with every test, so the kind of server freeze caught last
  time can't slip in again; and a review of every server address that changes data confirmed each one
  checks who is calling (sign-in, API key, owner key or payment signature)

## 0.1.117 (November 2026)

- Workspaces: admins can download usage for the last 30 days (messages, images and songs per person
  per day, as a spreadsheet file) -- never chats
- Calmer sidebar: moving the mouse past the left edge to the icons no longer slides the sidebar over
  them; it opens when you rest on the edge for a moment

## 0.1.116 (November 2026)

- For the owner: no more "Potential merge conflicts detected" in PyCharm. After publishing, your project
  folder's Git moves to the version you just published (your files aren't touched), so PyCharm no
  longer sees every file as changed both on your Mac and on GitHub
- The publish script can no longer stop silently partway (it sometimes quit right after pushing)

## 0.1.115 (November 2026)

- Code clean-up: the warnings PyCharm showed that were real problems are fixed (unused imports and
  variables, a test helper borrowed the wrong way), and the website builder works with Python 3.11 again.
  GitHub now checks this on every push, so new ones are caught straight away

## 0.1.114 (November 2026)

- Media Studio: "Use a photo" -- start from your own photo (choose one, paste it or drop it in) with an
  idea like Statue, Elven or Football figurine, and Gink keeps the person recognisable. Photos are made
  smaller first and are never kept on the server. Use photos of yourself, or of people who agreed

## 0.1.113 (November 2026)

- Workspaces, for hospitals, schools and businesses (Settings > Workspace): invite your team by their
  Gink account; admins see who's in it and today's message counts -- never chats -- and can give Gink
  instructions for everyone (for example "Answer in French")
- Healthcare mode for hospitals and clinics: Gink helps staff with rotas, letters, policies, training
  and general medical information, never diagnoses or decides a patient's treatment, and refuses
  messages that look like a patient's details -- in chat, Gink Genie and websites

## 0.1.112 (November 2026)

- "Hey Gink" or just "Gink": say "Gink, what time is it?" and Gink wakes, on computers, Android and
  the web app, with the same glow everywhere (turn "Gink" alone off in Settings > Voice)
- Media Studio: new Ideas -- Zen, Claw machine, Chibi keychain, Elven, Sitcom, 8-bit game, Football
  figurine, Landscape, Statue, Underwater, Cozy room -- each fills in a prompt you can change. Video is gone
- The model lists show only Gink's models (Crystal, Flake, Prism...), not old provider models

## 0.1.111 (November 2026)

- Room to grow: big files can live in object storage (Cloudflare R2, Backblaze B2, S3...), paid by
  use, so Gink isn't limited by one server's disk; Gink Genie projects then hold up to 500 MB and
  5,000 files; versions and copies of big files take almost no space
- Problems are found automatically: when something breaks, the app tells Gink's team what went wrong
  and where in Gink's code -- never your chats or files. Switch it off in Settings > Privacy
- For the owner: the dashboard shows problems from all apps, and Gink's own Facebook, Instagram and
  TikTok (followers and latest posts); tools to train one model on both chat and Genie's coding work

## 0.1.110 (November 2026)

- Gink Genie works on real repositories: paste a GitHub link to open it (public, or private with
  GitHub connected); Genie can find files by name, search with patterns, read long files in numbered
  parts and change one exact piece of a file; projects can hold 600 files (6 MB) with deeper folders
- Fixed the "Official" source badge: it now means a government or international public body, or the
  organisation's own website -- not universities or news -- and only Gink's own check can show it

## 0.1.109 (November 2026)

- Settings > Privacy > Help improve Gink: adults can choose to share their Gink Genie sessions to help
  train Gink's own coding model. It's off unless you switch it on; keys and passwords are removed and
  private files (like .env) are never shared; you can stop, or stop and delete what you shared

## 0.1.108 (November 2026)

- Updates reach people only when you choose: every release is now a test build on GitHub (you can
  download and try it), and the apps' "new version" offer and the website's download buttons keep
  the last release made for users. Release for users with for_users=true, or promote a tested build

## 0.1.107 (November 2026)

- For the owner, data for Gink's own model: translate.py teaches Gink's actions in 37 more languages
  (22 widely used ones; 15 African languages as drafts for native speakers); paraphrase.py now waits
  out Groq's rate limit by itself, drops rewrites that turn "remember" into "remind", and
  --recheck applies new checks to rows you already have
- Your dataset files (paraphrases.csv, translations.csv, examples_general.csv, languages/*.csv) are no
  longer in update packages, so unzipping an update can't overwrite them; publishing sends yours

## 0.1.106 (November 2026)

- For the owner: paraphrase.py and evaluate.py identify themselves properly, so Groq's firewall no
  longer refuses them (HTTP 403); if a refusal still happens, the provider's own words are shown

## 0.1.105 (November 2026)

- For the owner: paraphrase.py says which key it used (only its first and last 4 characters) and
  Groq's own reason when it refuses; --ask-key ignores a key saved in the Terminal and asks instead

## 0.1.104 (November 2026)

- For the owner: paraphrase.py and evaluate.py work with Python from python.org on a Mac (they failed
  with CERTIFICATE_VERIFY_FAILED); a placeholder key like "..." is ignored and the real key is asked
  for, hidden; a refused key or Groq's rate limit is explained in plain words

## 0.1.103 (November 2026)

- Gink Genie's small icons (taskbar, Finder lists, iPhone Settings) are drawn bolder and larger, so
  the lamp stays clear at 16-32 pixels

## 0.1.102 (November 2026)

- Parental controls now cover every way Gink makes something: quiet hours also pause making
  websites and images and searching the web; websites count toward a teen's daily limit and get the
  same stricter safety and safety checks as chat

## 0.1.101 (November 2026)

- Gink Genie follows age and parental controls like chat: quiet hours, the daily limit and stricter
  safety for teens; parents get a "Gink Genie" switch in Settings > Parental controls
- Gink Genie: if the AI stops answering partway, the changes it already made are kept and it says so
  (you can undo them) -- before, the files changed but the request disappeared from the chat
- Gink Genie's version history takes far less space (no copy when nothing changed, a size limit per
  project), and a project whose first request was refused no longer leaves an empty project behind

## 0.1.100 (November 2026)

- When your Gink server offers Gink's own model to your account, it appears in the model picker
  (More models)
- Computers' offline mode: the server can choose the offline model (for example Gink's own), which
  is downloaded once and replaces the old one; offline answers now use the model's own chat format,
  so they read better

## 0.1.99 (November 2026)

- For the owner, growing the data for Gink's own model: `paraphrase.py` asks GPT-OSS for more ways to
  say each request and throws out any rewrite that changes a time, number, day, name or currency;
  `examples_general.csv` is a sheet for people to write and approve everyday, safety and honesty
  examples; the held-out test examples now stay the same as the data grows, so scores stay comparable;
  `validate.py` shows how far the data is from the plan's targets

## 0.1.98 (November 2026)

- Fixed: parental safety notices could never be sent -- the check used an AI model that Groq retired
  in August. It now uses one Groq still offers
- For the owner: the plan and tools for Gink's own AI model (tools/gink_model): a free first training
  run in Google Colab, training a bigger one on a hosted service, and a test it must pass before launch.
  The server can already serve it to chosen testers only

## 0.1.97 (November 2026)

- Settings > Parental controls: parents link a teen by email or phone, then set quiet hours, a
  daily message limit, and switch voice, images, web search, websites and connected apps on or off.
  Teens see the invitation (with what it means, including safety notices) and can accept, decline
  or unlink. Parents see safety notices; teens see when one was sent
- Signing up asks the year you were born (Gink is for 13+); accounts without one are asked once
- When a parent turns voice off, the teen's device stops listening and speaking too
- Sign-in screens: an old error disappears when you try again

## 0.1.96 (November 2026)

- Gink is for people 13 and older. Signing up can now include your birth year (the sign-up screens
  ask for it in the next version); under-13s can't create an account
- Teens (13-17) always get stricter content safety
- Parental controls, on the server: a parent can link a teen's account (the teen accepts first) and
  set quiet hours, a daily message limit, and turn off voice, images, web search, websites and
  connected apps -- on every device. Parents never see chats. If a linked teen's message shows a
  serious risk to their safety, the parent gets a short notice (never the words). The screens to
  use all this come in the next version

## 0.1.95 (November 2026)

- "Continue with phone" in the apps too: sign in or create an account with your phone number and a
  code by SMS (the web page already had it). Phone-only accounts show their number in Settings
- Phone codes go through a provider that reaches your country: Africa's Talking where it delivers,
  Twilio everywhere else (including Senegal and Sierra Leone). If none can, Gink says to use email

## 0.1.94 (November 2026)

- Sharper small icons: at 32 pixels and under (Finder lists, the Windows taskbar, iPhone
  Settings) Gink's snowflake is now drawn bolder and simpler instead of blurring into a green smudge
- Running Gink from source (`pip install -r requirements.txt`) now installs exactly what the built
  apps use on every computer, including Apple Silicon Macs

## 0.1.93 (November 2026)

- For older Intel Macs: Gink for macOS 10.15 Catalina can now be built on GitHub (Actions >
  "Mac app (Catalina)"), and every file in it is checked to open on Catalina before it's packaged

## 0.1.92 (November 2026)

- Fixed: on a slow phone, a message you sent (or a tap) could vanish when the screen answered Gink
  late. Every tap and message is now delivered once, and only once, on every screen

## 0.1.91 (November 2026)

- Android: "Identify a song" works. Gink records about 8 seconds and your Gink server asks Shazam;
  the recording is deleted straight away
- "Identify a song" pauses "Hey Gink" while it listens, and says why when it can't (microphone
  permission off, not signed in, today's limit reached) instead of "Couldn't recognise a song"

## 0.1.90 (November 2026)

- Android: "Hey Gink" can keep listening when Gink isn't on screen. Switch on Settings > Voice >
  "Keep listening in the background" (off by default). Android shows a notification and its
  microphone indicator while it listens, and it uses more battery. Gink answers out loud
- Android: the Hey Gink description now says honestly that it uses the phone's speech recognizer
  (on the phone with the offline language pack, otherwise the phone's online speech service)

## 0.1.89 (November 2026)

- "Hey Gink" status, on computers and Android: a small chip beside the + button always shows
  whether Gink is listening for its name -- green when it's waiting, grey while Gink uses the mic,
  and red with the reason when it can't listen (click it for Voice settings)
- Fixed: on Android, Settings said "Off" when "Hey Gink" had stopped because the microphone
  permission was off. It now says why

## 0.1.88 (November 2026)

- Accounts are kept: the online server now stores accounts, synced chats and payments on a disk
  that survives restarts and new versions (Render Starter plan). Before, every update erased them
- /health and the owner dashboard show where accounts are stored, and warn (and email the owner)
  if the disk is missing
- For the owner: tools/backup_db.py downloads a copy of the whole database

## 0.1.87 (November 2026)

- Fixed: on computers, Google sign-in said it "isn't set up" and sign-up codes never arrived. The
  computer apps used their own built-in server, without the online server's settings and accounts.
  Every platform now uses the online server (one account everywhere); the built-in one is still in
  Settings > Advanced > Login server, and only runs when chosen

## 0.1.86 (November 2026)

- Fixed: when a sign-up or sign-in code couldn't be emailed, Gink said it was sent and nothing came.
  Now it says so (and you can try again at once), and the owner dashboard shows the exact reason
- Security: sign-in codes are no longer written to the server's logs when email fails

## 0.1.85 (November 2026)

- For developers on macOS 10.15: tools/check_project.py explains that Mac apps for this macOS are
  built from a Python 3.11 environment (Briefcase 0.3.15 can't build with Python 3.12)

## 0.1.84 (November 2026)

- Gink Genie: Version history keeps the last 20 versions of your project, compares any of them with
  now and goes back to one; going back (and Undo) can always be undone

## 0.1.83 (November 2026)

- Gink Genie sees when your website breaks: errors in the Preview appear in a bar, and "Ask Genie to fix"
  sends them to Genie to fix the code

## 0.1.82 (November 2026)

- "Hey Gink" works in the web app (and so on iPhone, in Safari), with an honest note that browsers
  listen through their own speech service
- "Hey Gink" on computers keeps working when one microphone library is missing: it switches to another
- Your profile (name, what Gink calls you, work, photo) is the same on the web as in the apps
- Security: the song database and news feeds can no longer be used to attack Gink
- Gink now needs Python 3.11 or newer (3.10 reached its end of life)

## 0.1.81 (November 2026)

- When Gink searches the web, the spinner says "Searching the web..." (automatic searches included)

## 0.1.80 (October 2026)

- Gink searches the web by itself when your question needs current information (news, prices,
  results, who holds a position...), preferring official sources
- Sources: a button under each answer shows where it comes from, official sources first

## 0.1.79 (October 2026)

- When something breaks, you see it: the server records every crash and error, the owner dashboard
  shows a red "new problems" badge (also in the tab's title) and can send computer notifications,
  and with GINK_ALERT_EMAIL set the server emails you (at most once every 15 minutes)

## 0.1.78 (October 2026)

- The owner dashboard fits on one screen: the key figures in one row and the charts side by side,
  with payments, costs, email and limits in a Tools window, so there's no long list to scroll

## 0.1.77 (October 2026)

- The owner dashboard has a new look ("Glow"): glowing figures on deep navy, a donut of the models in
  use, a requests area chart, usage bars, a messages and AI-calls chart and a helpful-answers gauge

## 0.1.76 (October 2026)

- Owner dashboard: a "Right now" section: people online in the last 5 minutes, requests in the last
  hour minute by minute, and which models are answering

## 0.1.75 (October 2026)

- Owner dashboard: refreshes by itself every 30 seconds (with an on/off switch), no longer signs you
  out when a refresh fails, shows changes since yesterday, and a new Server health section

## 0.1.74 (October 2026)

- Real-time answers through the Gink API and on the web: today's date always, and live weather,
  time, currency, crypto prices, air quality, sunrise and sunset and prayer times when you ask for them

## 0.1.73 (October 2026)

- On GitHub: tidying and triaging pull requests works with every version of the gh tool (gh pr edit
  failed on GitHub's retired classic Projects)

## 0.1.72 (October 2026)

- For the owner: tools/tidy_pull_requests.py gives every existing pull request (open and closed) its
  labels and assignee, and open ones the next-release milestone

## 0.1.71 (October 2026)

- Newer versions of the server's building blocks (FastAPI 0.162 and 11 others), tested in full
- For developers: the GitHub test run now also checks the release and pull-request workflows

## 0.1.70 (October 2026)

- On GitHub: the pull-request tools are up to date (labeler 7, add-to-project 2)

## 0.1.69 (October 2026)

- On GitHub: only collaborators can open pull requests, and every pull request is labelled, assigned,
  put in the next-release milestone and sent for review automatically

## 0.1.68 (October 2026)

- For developers: the server's startup uses FastAPI's current method (the old one is being removed),
  so the server keeps starting with future FastAPI versions

## 0.1.67 (October 2026)

- For developers: the passkey package's helper (cbor2) now installs on Intel Macs without Rust

## 0.1.66 (October 2026)

- For developers: everything installs on Intel Macs (the passkey package needed a newer encryption
  package than Intel Macs can have)

## 0.1.65 (October 2026)

- Fixed: asking Gink to open a folder by name (like "GinkAssistant") could open the wrong one
- For developers: the tests now pass on a Mac too (they no longer read your .env, and handle older
  macOS, git and bash)

## 0.1.64 (October 2026)

- For developers: requirements.txt and requirements-test.txt can now be installed together (they
  disagreed about numpy)

## 0.1.63 (October 2026)

- Fixed: the in-app viewer (videos, web pages) always shows its close button, with a short title
- Fixed: connecting Google apps in Settings showed "Error 400: redirect_uri_mismatch"
- Skeleton screens: pages in the viewer and lists in Settings show placeholders while they load

## 0.1.62 (October 2026)

- Gink Genie shows what it built: a new website opens in Preview by itself, and answers that change
  a page have a "See it in Preview" button

## 0.1.61 (October 2026)

- Gink Genie on phones has the Preview tab too, next to Files, Code and Genie

## 0.1.60 (October 2026)

- Gink Genie: a Preview tab shows your website or app running right next to the code, and
  refreshes by itself when files change

## 0.1.59 (October 2026)

- Gink Genie has a new look: your projects in a sidebar, a cleaner top bar (Share and GitHub as
  icons, everything else in the menu), the conversation in the centre with a Code tab, and a start
  screen with ideas to build

## 0.1.58 (October 2026)

- Publish a design: press Publish in the code viewer to put a page or graphic Gink made online,
  with a link to share

## 0.1.57 (October 2026)

- Designs: when Gink writes a web page or a graphic (HTML, SVG), the code viewer shows it rendered
  (Preview) next to its code

## 0.1.56 (October 2026)

- A code viewer: long code opens in a panel beside the chat, with the file's name, Copy or
  Download, Expand and line numbers (press Open on any long code block)

## 0.1.55 (October 2026)

- "Play Floating (Genom Världar - English Version)": Gink plays the exact song (YouTube on computers,
  your music app on Android, or Spotify if you ask), and understands "close Safari" too
- A new model menu: point at the model to see it, choose the Effort (Low to Max), and pick
  Gink Crystal, Gink Flake or Gink Prism
- The greeting uses your name (never your email) and changes each time
- Pictures you attach show inside the message box

## 0.1.54 (October 2026)

- Gink can ask you questions with tap-to-answer choices (and "Something else") when it needs your
  preferences, for example to plan a trip
- Gink recalls your memories automatically: the ones that match your message show as "Recalled
  memory" above the answer, in the apps and now on the web too
- Gink Genie tells you what it's doing at each step, and runs, debugs and fixes its own code before
  answering

## 0.1.53 (October 2026)

- Opening a chat from the sidebar now glides smoothly to its end, with the Gink snowflake spinning
  at the latest answer, and no more "Thinking..." flicker while it loads
- No "Gink" title in the window's title bar

## 0.1.52 (October 2026)

- Fixed on the web: Upgrade (in Settings and in the daily-limit message) now opens the plans page;
  Delete account, Export my data, Delete all chats and Sync now work; email and phone links in
  answers open; settings that only exist in the apps are no longer shown on the web
- Your instructions for Gink now really apply on all your devices, the web included
- Settings buttons never do nothing silently: if something isn't available, Gink says so

## 0.1.51 (October 2026)

- When an AI model is at its daily limit, busy or unavailable, Gink automatically answers with
  another model instead of failing

## 0.1.50 (October 2026)

- When the AI service refuses a message, Gink now says why (for example that its limit is reached
  for now) instead of "The AI service had a problem", and the server records the reason in its logs

## 0.1.49 (October 2026)

- After an update, Gink shows what's new, once, so you don't miss improvements

## 0.1.48 (October 2026)

- Gink Genie works properly on phones: Files, Code and Genie tabs, and all project actions in the
  menu, instead of a crowded screen that scrolled sideways

## 0.1.47 (October 2026)

- Gink Genie: Share a project's website with a link, and Stop sharing to make every old link stop
  working

## 0.1.46 (October 2026)

- Fixed "Hey Gink": the Mac app never asked for the microphone (a settings name Briefcase ignores),
  so it heard nothing; on Android it switched itself off after a few everyday recognizer hiccups
  and never worked on phones without offline speech. Now it keeps listening on every device
- Your settings follow you: theme, font, style, language, voice, model, Genie's Plan first and more
  change on every device you're signed in on
- The model you pick in the apps is remembered after restarting

## 0.1.45 (October 2026)

- Gink Genie's editor shows line numbers and where your cursor is (Ln, Col)

## 0.1.44 (October 2026)

- Gink Genie: search the whole project with Ctrl+Shift+F (Cmd+Shift+F on Mac) and jump straight to
  the line you need

## 0.1.43 (October 2026)

- Gink's description: "Your AI assistant for work, study and everyday life"

## 0.1.42 (October 2026)

- Gink Genie: rename or move files (Rename next to Delete file), and press Ctrl+P (Cmd+P on Mac)
  to jump to any file by typing part of its name

## 0.1.41 (October 2026)

- Gink Genie: rename a project, or duplicate it to try an idea on a copy (the original stays as it is)

## 0.1.40 (October 2026)

- Gink Genie's Plan first mode: Genie looks at your project and proposes a numbered plan without
  changing anything; press Build this plan when you're happy with it

## 0.1.39 (October 2026)

- Gink Genie has a Stop button while it works: it stops after its current step and keeps (and lets
  you undo) what it already changed

## 0.1.38 (October 2026)

- Gink Genie shows its work live: each step (files created, changed, commands run) appears while
  Genie is still working, instead of all at the end

## 0.1.37 (October 2026)

- Gink Genie shows exactly what it changed: "Updated app.js (+3 -2)" opens to the changed lines,
  removed in red and added in green

## 0.1.36 (October 2026)

- Gink Genie: "Undo these changes" under an answer puts the project back exactly as it was before
  that request (the last 5 requests can be undone)

## 0.1.35 (October 2026)

- Gink Genie remembers: each project keeps its conversation (with every step), on all your devices,
  and Genie keeps your recent requests in mind, so follow-ups like "now do the same for the cart" work

## 0.1.34 (October 2026)

- Gink Genie projects can include pictures (PNG, JPG, GIF, WebP, ICO): add logos and photos with
  + or drag and drop, see them in the workspace and the preview, and they go into ZIP downloads
  and GitHub too

## 0.1.33 (October 2026)

- Gink Genie runs commands to check its work (python, pytest, node, ls, cat), safely in your
  browser, and shows every step like a work log: files created and changed, commands with output
- A new-project screen in the style of Claude Code, with the genie on the message box
- Add files with + or drag and drop: ZIPs are unpacked automatically (the Upload ZIP button is gone)

## 0.1.32 (October 2026)

- Your prompts (the / menu) now sync: add or delete one on any device, signed in, and it's the same
  everywhere

## 0.1.31 (October 2026)

- Prompt library: type / at the start of a message to pick a prompt (Summarize, Fix grammar,
  Translate, Explain simply, Write an email...). Save your own in Settings > Personalization

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
