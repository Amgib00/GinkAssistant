## Why

Teenagers may use Gink. Parents need simple tools to keep it appropriate, and teens deserve privacy
and safety at the same time.

## What Changes

- Linked accounts: a parent invites a teen (13-17); both accept. Either can unlink, and the parent is told.
- Parent controls: quiet hours, turning off voice, image making, web search, websites and connected
  apps, and a daily message limit.
- Stricter content safety for linked teen accounts, always on.
- Safety notices: if a teen's chat shows a serious risk to their safety, the parent may be notified
  -- without chat contents.
- Teens' privacy: parents never see chats.

Out of scope: accounts for children under 13 (not allowed), reading teens' chats, location tracking.

## Impact

- New spec: parental-controls. Affects accounts, Settings, the AI's instructions for teen accounts,
  Lockdown-like server enforcement.

## Decisions (owner, November 2026)

1. Minimum age 13. The birth year is asked at sign-up (email and phone), and once later for accounts
   that don't have one (older accounts, Google/Apple/... sign-ups). It can't be changed afterwards.
2. Safety notices to parents are included at launch: self-harm, danger from another person (an
   adult asking for photos, secrecy, meeting; threats), plans to hurt someone. Never harm at home
   (the parent could be the danger). One per kind per day, never the words, and the teen sees that
   one was sent. Teens are told about notices before they accept a link.
3. All controls at once: quiet hours, a daily message limit, voice, images, web search, websites,
   connected apps.
4. Still open: legal review for the countries Gink serves (children's privacy laws differ).
