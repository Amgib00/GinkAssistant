## ADDED Requirements

### Requirement: Plans with their own limits
The system SHALL offer Free, Pro, Max and Team plans, each with configured daily limits (messages, searches, images, voice, Claude, API) and prices, and SHALL apply a plan's limits as soon as it is paid.

#### Scenario: Upgrading to Max
- **WHEN** a Pro user pays for Max
- **THEN** their Max limits apply immediately, and Settings > Billing shows Max

### Requirement: Teams
A Team owner SHALL be able to invite people by email, remove them, and pay for everyone in one bill; members SHALL get the Team limits and keep their chats private from the owner.

#### Scenario: Member privacy
- **WHEN** a Team owner looks at their team
- **THEN** they see members and usage, but never members' chats
