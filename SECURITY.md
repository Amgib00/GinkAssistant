# Security Policy

## Supported versions
| Version | Supported |
| ------- | --------- |
| 0.1.x (main) | :white_check_mark: |

## Reporting a vulnerability
**Please don't report security problems in public issues.** Use GitHub's private reporting:
the repository's **Security** tab -> **Report a vulnerability**. Include what you found, how to
reproduce it, and what could happen if it were exploited.

You'll get an acknowledgement within **48 hours**. Please give us time to release a fix
before talking about it publicly.

## How Gink keeps secrets out of the app and this repository
- API keys (Groq, Google Gemini, payments, sign-in) live **only on the Gink server**, as
  environment variables -- never in the app or in this repository. The app sends a session
  token, not keys.
- Local settings go in `.env`, which `.gitignore` blocks from being committed.
- Chat history is stored on your device; protect your computer and phone with a password.
- "Hey Gink" listens for the wake word **on the device**; no audio leaves it before the wake word.

If a key is ever committed by mistake, **revoke it with the provider straight away** --
deleting it from the code isn't enough, because git history and copies keep it.
