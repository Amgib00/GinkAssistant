## ADDED Requirements

### Requirement: Minimum age
Gink SHALL be for people 13 and older: the birth year SHALL be asked at sign-up (or once later), set only once, and an account under 13 SHALL not be created, or, if one exists, SHALL not be able to use Gink.

#### Scenario: Under 13 at sign-up
- **WHEN** someone signs up with a birth year that makes them 12
- **THEN** the account is refused and nothing is kept

### Requirement: Safety notices
For a linked teen, when a message clearly shows a serious current risk to the teen's safety (self-harm, danger from another person, or a plan to hurt someone), the parent SHALL receive a notice naming only the kind of risk, at most once per kind per day; no notice SHALL be sent about harm at home; the teen SHALL be able to see that a notice was sent.

#### Scenario: Self-harm
- **WHEN** a linked teen writes that they want to hurt themselves
- **THEN** the parent is emailed and sees a notice saying so, without the teen's words

#### Scenario: Harm at home
- **WHEN** a linked teen writes that a parent hurts them
- **THEN** no notice is sent to the parent

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
