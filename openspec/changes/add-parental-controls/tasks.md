## 1. Decide
- [x] 1.1 Minimum age 13, birth year at sign-up, safety notices at launch, all controls
- [ ] 1.2 Legal review for the countries Gink serves

## 2. Build
- [x] 2.1 Server: birth year (sign-up, /account/age once), under-13 blocked; linked accounts (invite,
      accept/decline, unlink + notice), controls enforced on the server (chat, images, voice, websites,
      connected apps, web search, quiet hours, daily limit); stricter safety for every teen; safety
      notices (classifier, one per kind per day, email + list, none for harm at home)
- [x] 2.2 Sign-up birth year (apps + web), the one-time question for accounts without one,
      Settings > Parental controls (parent and teen views, notices); voice off also on the device
- [x] 2.3 Server tests (tests/test_parental_controls.py)
- [x] 2.4 Browser check of the panel (parent, invited teen, linked teen, no birth year), the age dialog
      and the sign-up year (tests/test_parental_controls_app.py: the Settings actions against a real server)
- [x] 2.6 Every AI feature, not just chat: Genie (0.1.101); websites, images, web search get quiet hours, the
      teen limit (websites) and teen safety + checks (websites) (0.1.102); tests/test_family_everywhere.py lists
      every AI endpoint and checks under-13 and quiet hours on each
- [ ] 2.5 On devices: a parent and a teen account end to end (invite, accept, a control, a notice email)
