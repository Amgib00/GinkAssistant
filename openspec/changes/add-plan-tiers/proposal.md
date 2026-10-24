## Why

Gink has Free and Pro. Heavy users and teams need more, and Gink needs plans that cover its costs
(Groq, Gemini, Claude, Render, email).

## What Changes

- Plans: Free, Pro, Max (much higher limits), and Team (several people, one bill, shared admin).
- Each plan sets: daily messages, web searches, images, voice minutes, Claude access, API requests.
- A pricing page comparing plans (like the screenshots), and upgrading / downgrading in Settings > Billing.
- Team: invite by email, roles (owner, member), central billing.

Out of scope: Enterprise (single sign-on, audit exports), usage-based billing.

## Impact

- New spec: plan-tiers. Affects billing (Paystack / CinetPay), usage limits, the developer console.

## Decision needed (owner)

1. Prices per plan, per month and per year (and in which currencies: USD, XOF, NGN, SLE...).
2. Limits per plan (the owner dashboard's cost estimator helps check each plan covers its costs).
3. Whether to start with Max only, or Max and Team together.
