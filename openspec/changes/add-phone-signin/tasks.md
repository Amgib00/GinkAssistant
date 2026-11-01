## 1. Decide
- [ ] 1.1 Choose the SMS provider(s) and a monthly budget cap (both are built in and can run together; for
      Senegal / Sierra Leone it has to be Twilio; cap = GINK_SMS_MONTHLY_LIMIT, default 500)

## 2. Build
- [x] 2.1 Server: phone numbers on accounts, SMS codes through the provider, limits per number + a monthly SMS cap
- [ ] 2.1b Optional: daily limits per country (if one country sees abuse)
- [x] 2.2 Sign-in page: "Continue with phone"; Settings > Account: add / change phone
- [x] 2.2b The apps' sign-in screen too (login_screen.py: number -> code -> name for a new number); phone-only
      accounts show their number, not the internal address
- [x] 2.2c Route by country: Africa's Talking where it delivers (not Senegal / Sierra Leone), Twilio elsewhere;
      a clear "use your email" when no provider reaches the number (GINK_AT_COUNTRIES to extend)
- [x] 2.3 Tests with the provider simulated; browser check
- [ ] 2.4 Real SMS to a real phone (the TECNO) once the provider account is set up
