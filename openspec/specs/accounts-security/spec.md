# Accounts and security

## Purpose
How people sign in, stay signed in, protect their account and leave it.

## Requirements

### Requirement: Session-bound sign-in tokens
Every sign-in SHALL create a server-side session (with the device's name) and a token bound to it; the server SHALL refuse a token whose session was ended, immediately.

#### Scenario: A device is signed out from another one
- **WHEN** the person signs out "Gink for Mac" from Settings > Account > Signed-in devices on another device
- **THEN** the Mac app's next request is refused with "You were signed out on this device. Sign in again."
- **AND** the person's other devices keep working

#### Scenario: Log out really ends the session
- **WHEN** the person taps Log out in an app or the web app
- **THEN** the session is ended on the server, not only forgotten on the device

### Requirement: Sign out all other devices
The system SHALL let a person end every session except the current one, including tokens issued before sessions existed.

#### Scenario: Lost phone
- **WHEN** the person chooses "Log out of all other devices"
- **THEN** every other session and every older token is refused
- **AND** the current device stays signed in

### Requirement: Two-step verification
When two-step verification is on, every way of signing in (password, email code, sign-up confirmation, password reset, Google, GitHub, Microsoft, Apple) SHALL require a current authenticator code (TOTP, RFC 6238) or an unused recovery code before a token is issued.

#### Scenario: Password alone is not enough
- **WHEN** a person with two-step verification signs in with the right password
- **THEN** they receive a 5-minute ticket, not a token
- **AND** a token is issued only after a valid code is sent with the ticket

#### Scenario: Password reset can't skip it
- **WHEN** a person resets their password with an email code
- **THEN** the authenticator code is still required

#### Scenario: Codes can't be replayed or guessed
- **WHEN** a code that was already used is sent again, or five wrong codes are sent with one ticket
- **THEN** the code is refused, and after five wrong codes the ticket stops working

#### Scenario: Recovery codes
- **WHEN** the person turns on two-step verification
- **THEN** ten recovery codes are shown once, each works one time, and dashes, spaces and case are ignored

### Requirement: Secrets at rest
The authenticator secret SHALL be stored encrypted, and recovery codes and API keys SHALL be stored only as hashes.

#### Scenario: Reading the database
- **WHEN** someone reads the server database
- **THEN** they can't read any authenticator secret, recovery code or API key from it

### Requirement: Password guessing is limited
The server SHALL lock an account's password sign-in for 15 minutes after repeated wrong passwords, and lock owner tools for 10 minutes after 10 wrong admin keys from one address.

#### Scenario: Repeated wrong passwords
- **WHEN** someone keeps trying wrong passwords for one account
- **THEN** sign-in is refused for 15 minutes with a message suggesting a password reset

### Requirement: Third-party sign-in checks
For Google, Microsoft and Apple, the server SHALL check the ID token's audience, expiry and issuer.

#### Scenario: Token from an unexpected issuer
- **WHEN** an ID token's issuer is not the provider's (for example accounts.google.com.evil.example)
- **THEN** the sign-in is refused

### Requirement: Account deletion
Deleting an account SHALL require typing DELETE and SHALL remove the account and everything linked to it: chats sync, usage, API keys, sessions, two-step data, websites, API request logs and batches.

#### Scenario: Deleted account
- **WHEN** the person confirms with DELETE
- **THEN** their websites stop being served and their tokens stop working

### Requirement: Code emails can't flood an inbox
Sign-up, password-reset and email sign-in codes SHALL be limited per email address (a 30-second cooldown and at most 6 an hour), applied before looking up the account, and SHALL be generated with a cryptographic random generator.

#### Scenario: Repeated requests
- **WHEN** someone requests codes for one address again and again
- **THEN** a second code within 30 seconds is refused with how long to wait, and the seventh within an hour is refused

#### Scenario: Probing for accounts
- **WHEN** the same requests are made for an address without an account
- **THEN** the answers are exactly the same as for an existing account

### Requirement: Email sign-in only for existing accounts
An email sign-in code SHALL only sign in an existing account; for an unknown address the server SHALL answer as if a code was sent, send no code, and instead email at most one note every 10 minutes pointing to sign-up.

#### Scenario: Unknown address
- **WHEN** someone asks for a sign-in code for an address with no Gink account
- **THEN** no code exists to sign in with, and the inbox receives a note about creating an account

### Requirement: Security history
The server SHALL record, with time and device, sign-ins, wrong passwords on an existing account, password resets, two-step verification changes, devices signed out, API keys created or revoked, apps connected or disconnected and Lockdown mode changes; it SHALL show the person their last 50 events, keep them 180 days and delete them with the account.

#### Scenario: Someone tried a password
- **WHEN** a wrong password is entered for the account
- **THEN** "Wrong password entered" appears in Settings > Account > Security history with the device

### Requirement: Lockdown mode
When the person turns on Lockdown mode, the server SHALL refuse web search, connected apps and images from web addresses for that account on every device and API path, with a message saying how to turn it off, while normal chat keeps working.

#### Scenario: Web search in Lockdown mode
- **WHEN** a question would search the web while Lockdown mode is on
- **THEN** it is refused with "Lockdown mode is on, so Gink doesn't use web search"

### Requirement: Passkeys
People SHALL be able to add passkeys in a browser (Settings > Account > Passkeys), see and remove them in the apps and the web, and sign in with one on the sign-in page without typing anything; registration and sign-in SHALL require user verification (fingerprint, face or PIN), be bound to the site's own address, use one-time challenges, and check the signature counter. A passkey sign-in SHALL count as two factors and not ask for the authenticator code.

#### Scenario: Signing in with a passkey
- **WHEN** a person with a passkey chooses "Sign in with a passkey" and unlocks it
- **THEN** they are signed in without typing an email, a password or a code

#### Scenario: Removed passkey
- **WHEN** a passkey removed in Settings is used
- **THEN** sign-in is refused with "That passkey isn't linked to a Gink account"
