## ADDED Requirements

### Requirement: Linked parent and teen accounts
A parent SHALL be able to invite a teen (13 to 17) to link accounts, the teen SHALL accept before anything applies, either SHALL be able to unlink, and the parent SHALL be told when a teen unlinks.

#### Scenario: Teen unlinks
- **WHEN** a teen unlinks their account
- **THEN** the controls stop applying and the parent receives a notice

### Requirement: Controls enforced by the server
For a linked teen, the server SHALL enforce the parent's choices (quiet hours, voice, image making, web search, websites, connected apps, a daily message limit) on every device, and SHALL always apply stricter content safety.

#### Scenario: Quiet hours
- **WHEN** a linked teen sends a message during quiet hours
- **THEN** it is refused with a message saying when Gink is available again

### Requirement: Teens keep their privacy
Parents SHALL never see a teen's chats.

#### Scenario: Parent view
- **WHEN** a parent opens Settings > Parental controls
- **THEN** they see the controls and usage totals, but no chat contents
