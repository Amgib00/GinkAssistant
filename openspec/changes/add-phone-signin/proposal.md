## Why

Many people in West Africa use a phone number more than an email address. "Continue with phone" (a
code by SMS) would make signing up easier for them.

## What Changes

- Sign up and sign in with a phone number and a 6-digit SMS code, on the web and in the apps.
- Settings > Account: add or change a phone number (verified by SMS).
- The same protections as email codes: limits per number, codes that can't be guessed, two-step
  verification still required when it's on.

Out of scope: voice calls, WhatsApp codes, phone numbers as the only recovery method.

Platforms: server, web sign-in page, all apps (through the server).

## Impact

- New spec: phone-signin. Affects accounts-security (codes, limits, two-step gate).

## Decision needed (owner)

1. Provider: Twilio Verify, Africa's Talking or Termii (all charge per SMS; prices vary by country
   and change, so compare current prices for Senegal, Sierra Leone, Nigeria and Ghana).
2. Budget: a monthly spending cap, and a daily limit of SMS codes per number and per country.
3. SIM-swap risk: SMS is weaker than an authenticator app or a passkey. Recommended: phone sign-in
   allowed, but two-step verification and passkeys stay the strong options.
