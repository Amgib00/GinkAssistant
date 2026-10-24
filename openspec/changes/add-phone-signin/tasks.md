## 1. Decide
- [ ] 1.1 Choose the SMS provider and a monthly budget cap (both Africa's Talking and Twilio are built in; cap = GINK_SMS_MONTHLY_LIMIT, default 500)

## 2. Build
- [x] 2.1 Server: phone numbers on accounts, SMS codes through the provider, limits per number + a monthly SMS cap
- [ ] 2.1b Optional: daily limits per country (if one country sees abuse)
- [x] 2.2 Sign-in page: "Continue with phone"; Settings > Account: add / change phone
- [x] 2.3 Tests with the provider simulated; browser check
- [ ] 2.4 Real SMS to a real phone (the TECNO) once the provider account is set up
