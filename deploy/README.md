# Making login work on your phone

On your Mac, Gink starts its own login server automatically. A phone
can't use that one -- it needs a server it can reach over the internet
(or your Wi-Fi). Pick ONE of these.

## Option A -- Quick test on the same Wi-Fi (no hosting)

1. On the Mac, run Gink as usual (`briefcase dev`) so the server starts.
   It listens on 127.0.0.1 only, so ALSO start a copy anyone on your
   Wi-Fi can reach:
   ```bash
   cd ~/PycharmProjects/GinkAssistant/src/ginkassistant/services
   uvicorn backend_server:app --host 0.0.0.0 --port 8001
   ```
2. Find your Mac's Wi-Fi address: System Settings -> Wi-Fi -> Details
   (looks like 192.168.1.20).
3. On the phone, on the login screen tap **Server settings**, enter
   `http://192.168.1.20:8001`, tap **Save & test**. You should see
   "Connected ✓".

Only works while the Mac is on and both are on the same Wi-Fi.

## Option B -- Host it online (works anywhere)

Uses the `render.yaml` and `deploy/Dockerfile` in this project.

1. Put the project on GitHub (private repo is fine). Make sure `.env`
   is in `.gitignore` -- never upload it.
2. render.com -> New -> **Blueprint** -> choose the repo.
3. When asked, fill in:
   - `GMAIL_USER` -- the Gmail address that sends codes
   - `GMAIL_APP_PASSWORD` -- a Gmail **App Password** (Google Account ->
     Security -> 2-Step Verification -> App passwords), NOT your normal
     password
4. Wait for the deploy, then open `https://<your-service>.onrender.com/health`
   in a browser -- it should show `{"status":"ok",...}`.
5. In the app: login screen -> **Server settings** -> enter that
   https address -> **Save & test**.

Notes, honestly:
- Some free hosting tiers block outgoing email (SMTP). If `/health`
  works but codes never arrive, check the service logs; you may need a
  paid tier or a different host. Without Gmail settings the server
  prints the code in its logs instead of emailing it.
- Codes are kept in memory: run ONE instance, and a restart clears
  pending codes (just request a new one).
- Free Render services sleep when idle; the first request can take
  ~30-60 s to wake up.

## Test it locally with Docker (optional)

```bash
cd ~/PycharmProjects/GinkAssistant
docker build -f deploy/Dockerfile -t gink-server .
docker run -p 8000:8000 gink-server
curl http://127.0.0.1:8000/health
```

## Sign in with Google, Apple, Microsoft, GitHub, SSO

Password accounts and email codes work with no extra setup. Each social
button lights up in the app only once its keys are set on the server (as
environment variables, e.g. in Render -> Environment). Until then it shows
greyed out with "... sign-in isn't set up yet".

First set `GINK_PUBLIC_URL` to your server's address, e.g.
`https://gink-server.onrender.com` (for the local Mac server it's
`http://127.0.0.1:8000`). The redirect / callback URL to register with each
provider is:

    <GINK_PUBLIC_URL>/auth/<provider>/callback
    e.g. https://gink-server.onrender.com/auth/google/callback

| Button | Where to get keys | Server variables |
|---|---|---|
| Google | console.cloud.google.com -> APIs & Services -> Credentials -> OAuth client ID (type: Web application) | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Microsoft | portal.azure.com -> App registrations -> New (accounts in any org + personal) -> Certificates & secrets | `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` |
| GitHub | github.com -> Settings -> Developer settings -> OAuth Apps -> New | `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` |
| Apple | developer.apple.com (paid membership) -> Identifiers -> a **Services ID** with Sign in with Apple + a **Key** (.p8) with Sign in with Apple | `APPLE_CLIENT_ID` (the Services ID), `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` (contents of the .p8; `\n` for new lines is fine) |
| SSO | Any OpenID Connect provider (Okta, Auth0, Azure AD tenant, Keycloak, Google Workspace...) | `SSO_ISSUER` (e.g. `https://yourco.okta.com`), `SSO_CLIENT_ID`, `SSO_CLIENT_SECRET`, optional `SSO_LABEL` (button tooltip, e.g. "Acme SSO") |

Notes:
- Apple only accepts **https** callback URLs on a real domain, so Sign in
  with Apple works with the hosted server, not the local 127.0.0.1 one.
- Accounts are matched by email: signing in with Google using the same
  email as a password account opens the same account.
- Users are stored in `users.db` next to the server's secret key, or at
  `GINK_DB_PATH`. On Render's free tier the disk is wiped on redeploy --
  add a Render Disk and point `GINK_DB_PATH` at it to keep accounts.

## Optional: YouTube Data API key (better video search)

Gink finds videos without any key (YouTube's own search page, then
DuckDuckGo). A free Google key makes it more accurate and adds durations,
view counts and better live-stream search:

1. console.cloud.google.com -> pick your Gink project (the same one you used
   for Google sign-in).
2. APIs & Services -> Library -> search **YouTube Data API v3** -> Enable.
3. APIs & Services -> Credentials -> **Create credentials -> API key**.
4. Click the new key -> **API restrictions -> Restrict key -> YouTube Data API v3** -> Save.
5. Add it to `.env`:  `YOUTUBE_API_KEY=your-key-here`  and restart Gink.

The free quota is about 100 searches a day; when it runs out Gink quietly
falls back to the keyless search.

## Payments (Gink Pro)

The app detects the user's country (their saved choice, else the device's time
zone / region) and shows prices in local money with the local ways to pay.
A payment is only credited after the server checks it directly with the
provider, and only if the amount and currency match.

**Payments need the hosted server** (https). CinetPay refuses `localhost`
notification addresses, and providers must be able to reach
`<GINK_PUBLIC_URL>/billing/...`.

### CinetPay -- Wave, Orange Money, Free Money, MTN, Moov, cards (West & Central Africa)
1. Open a merchant account at cinetpay.com (they verify your business documents).
2. Back-office -> Integration: copy your **API key** and **Site ID**.
3. Set the notification URL there to `<GINK_PUBLIC_URL>/billing/notify/cinetpay`.
4. Server variables:
   `CINETPAY_API_KEY`, `CINETPAY_SITE_ID`, `CINETPAY_CURRENCIES=XOF`
   (only the currencies YOUR account is allowed -- an account opened in
   Senegal is XOF only).

### Paystack -- Nigeria, Ghana, Kenya, South Africa (optional)
Needs a business registered in one of Paystack's countries.
`PAYSTACK_SECRET_KEY`, `PAYSTACK_CURRENCIES=NGN` (or the ones your account has).
Dashboard -> Settings -> API Keys & Webhooks -> webhook URL:
`<GINK_PUBLIC_URL>/billing/webhook/paystack`.

### Prices
Set your own (the built-in ones are placeholders):

    GINK_PRICES={"XOF": {"pro_1m": 3000, "pro_3m": 8000, "pro_12m": 30000}, "USD": {"pro_1m": 5}}

XOF/XAF amounts must be multiples of 5 (CinetPay rule).

### Things to decide before launch
- **Google Play:** Google requires its own billing for digital subscriptions
  bought inside Android apps from the Play Store, and Senegal isn't a supported
  merchant location for Play payments. Check Google Play's current Payments
  policy (and with an accountant where to register the business) before
  publishing a paid Android app on Play.
- **Regional prices can be chosen by anyone** who picks a different country and
  pays by card. That's normal for regional pricing; keep the gap reasonable.
- Pro is **prepaid** (1 / 3 / 12 months, no automatic renewal) because mobile
  money can't be charged automatically.

## Gink Cloud AI (required for real users)

The app never contains an AI key. It sends chat to `<server>/ai/...` with the
user's sign-in token; the server holds the key, applies the plan's limits
and passes the request to Groq.

Server variables:
- `GROQ_API_KEY` -- from console.groq.com. Keep it ONLY on the server.
- `GINK_FREE_DAILY` (default 30) and `GINK_PRO_DAILY` (default 500) --
  messages per day, reset at midnight UTC. One request that needs several
  AI steps (the action agent) counts as one message.
- Free: answers up to 1,024 tokens, no photo analysis. Pro: 4,096, photos.

Testing on your Mac: your `.env` key is used directly for development. To
test exactly what users get, run `GINK_CLOUD_AI=1 python -m ginkassistant`.

## App info shown in Settings
- `GINK_SUPPORT_EMAIL` -- "Email support" in Settings -> Help.
- `GINK_PRIVACY_URL`, `GINK_TERMS_URL` -- links in Settings -> Privacy. Google Play
  and the App Store require a privacy policy for apps that handle accounts,
  voice and location, so publish one before launch.
- `GINK_HELP_URL` -- optional help-centre link.

## Account deletion
Settings -> Account -> Delete account (the user types DELETE) calls
`POST /account/delete`: the account, synced chats/Workspace/memories and usage
are deleted; payment records are kept for accounting with the email replaced by
an anonymous id; existing sign-in tokens stop working immediately. App stores
require in-app account deletion.

## Images (Media Studio and "create an image of...")

Images are made by your server with Google's Nano Banana models -- the app
never contains a Google key.
- `GEMINI_API_KEY` -- from aistudio.google.com/apikey (image output is paid
  per picture, so set a budget in Google's billing settings).
- `GINK_IMAGE_MODEL` -- default `gemini-nano-banana-2.1`. Google retires image
  models often (Imagen 3 Nov 2025, Imagen 4 Aug 2026); check
  ai.google.dev/gemini-api/docs/deprecations and change this when needed.
- `GINK_FREE_IMAGES` (default 3) / `GINK_PRO_IMAGES` (default 50) per day.
  Failed or refused requests don't count.
- Video is off for now: Google's Veo models shut down on 22 Oct 2026
  (replacement: Gemini Omni Flash); Media Studio says "coming soon".

## Natural voices (voice conversations and read-aloud)

Gink's voices are made by your server with Google Gemini TTS -- the same
`GEMINI_API_KEY` as images (no key in the app).
- `GINK_TTS_MODEL` -- default `gemini-3.8-flash-lite-tts` (Google's model for
  real-time voice agents). `gemini-3.8-flash-tts` sounds even richer but is
  slower and costs more.
- `GINK_FREE_VOICE_CHARS` (default 15 000 characters a day, about 15 minutes of
  speech) / `GINK_PRO_VOICE_CHARS` (200 000). After that Gink switches to its
  standard voice for the day -- it never goes silent. Failed calls aren't counted.
- Nigerian, Kenyan, British and French voices are picked from Google's voice
  library by region (cached for a day), falling back to built-in voices.

## "Hey Gink" wake word (desktop app)

Off by default; users switch it on in Settings -> Voice -> Hey Gink.
Listening for the wake word happens on the device -- no audio leaves it until
"Hey Gink" is heard.
- Default engine: Vosk (free, Apache-2.0). The small English model (~40 MB) is
  downloaded once, on first use, to the app's data folder.
- Better accuracy: Picovoice Porcupine. Make a "Hey Gink" keyword in
  console.picovoice.ai, then set PICOVOICE_ACCESS_KEY and GINK_WAKEWORD_FILE
  (path to the .ppn) and `pip install pvporcupine`. Free for personal use;
  commercial use needs a Picovoice licence.
- Phones: not yet (needs a background service on Android).
