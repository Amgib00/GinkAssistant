## ADDED Requirements

### Requirement: Long chats keep working
A chat SHALL never fail because it has grown long: earlier versions of an artifact SHALL not be sent again (the newest stays), and every request SHALL fit the AI model's limit -- less room for the answer, then older turns left out, keeping the newest version of every artifact and the last turns as long as possible -- or go to a model that takes more; the model's real limits SHALL be learned from the AI service's own answers.

#### Scenario: A page made three times
- **WHEN** a chat that made a page three times asks for one more section
- **THEN** only the newest version of the page goes along and the answer comes, from a model that takes it if needed

### Requirement: Plain words when the AI refuses
When the AI service still refuses a request, or is busy, the person SHALL see plain words -- the chat is too long, or Gink's AI is busy and when to try again -- never the service's own message or Gink's account details.

#### Scenario: Busy everywhere
- **WHEN** every model has used up this minute
- **THEN** the person reads that Gink's AI is busy and when to try again, without an organization id or an upgrade link

### Requirement: Opened chats on the web are readable at once
In the web app, an answer SHALL be formatted as it arrives and an opened chat SHALL show its answers formatted at once (no raw Markdown, no artifact code), then with the server's formatting; a question card answered by the next message SHALL show closed with its answer; a chat opened again SHALL show formatted without waiting; and an opened chat SHALL never make its scheduled task again.

#### Scenario: Opening a chat with a question card
- **WHEN** the person opens a chat where Gink asked a question and they answered it
- **THEN** the card shows their answer, closed, and the artifact that followed shows as its card
