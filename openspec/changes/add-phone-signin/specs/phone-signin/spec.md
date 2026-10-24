## ADDED Requirements

### Requirement: Phone sign-in
The system SHALL let people sign up and sign in with a phone number and a 6-digit SMS code, with the same limits, cryptographic codes and two-step gate as email codes, and SHALL stop sending SMS when the owner's budget cap is reached.

#### Scenario: Signing in with a phone
- **WHEN** a person enters their phone number and the code they received
- **THEN** they are signed in, or asked for their authenticator code when two-step verification is on

#### Scenario: Budget reached
- **WHEN** the month's SMS budget is used
- **THEN** phone codes pause with a message suggesting email or a passkey
