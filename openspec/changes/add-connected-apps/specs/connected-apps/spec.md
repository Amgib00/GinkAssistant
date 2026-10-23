## ADDED Requirements

### Requirement: Connecting an app
The system SHALL let a signed-in person connect and disconnect Google Calendar, Gmail and Drive separately, asking only for that service's scopes, and SHALL show what Gink can do with each.

#### Scenario: Connecting Calendar only
- **WHEN** a person connects Google Calendar
- **THEN** Google asks only for calendar permissions, and Gmail and Drive stay disconnected

#### Scenario: Disconnecting
- **WHEN** the person disconnects a service
- **THEN** its tokens are deleted from the server and revoked at Google

### Requirement: Reading connected data
The agent SHALL be able to read upcoming calendar events, search emails and search Drive files of connected services to answer the person, and the server SHALL NOT store the contents it reads.

#### Scenario: Calendar question
- **WHEN** a person with Calendar connected asks "what's on my calendar tomorrow?"
- **THEN** Gink answers from their events

#### Scenario: Not connected
- **WHEN** the service isn't connected
- **THEN** Gink says so and how to connect it, instead of guessing

### Requirement: Writing needs approval
Creating events, creating email drafts and sending emails SHALL always require the person's approval through agent mode, whatever the "Ask before sensitive actions" setting.

#### Scenario: Sending an email
- **WHEN** Gink is about to send an email
- **THEN** it shows the recipient, subject and text and sends only after Allow

### Requirement: Connections are protected
Refresh tokens SHALL be stored encrypted, SHALL never be returned to any client or API key, and SHALL be deleted with the account.

#### Scenario: Account deleted
- **WHEN** the account is deleted
- **THEN** all its connections are deleted and revoked
