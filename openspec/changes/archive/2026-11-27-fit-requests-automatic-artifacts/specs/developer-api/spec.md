## ADDED Requirements

### Requirement: Fitting to the model's limits
A chat completion SHALL fit the model's limit by shrinking only the room for the answer, or go to another model that takes it (saying which in X-Gink-Model); with "gink_fit": true, older messages and earlier versions of an artifact MAY be left out like in Gink's apps. When the AI service refuses, the developer SHALL get its error with its status but without Gink's own account details, and a 413 SHALL mention "gink_fit". The SDKs SHALL know the artifact kinds react, chart, table and slides.

#### Scenario: A long conversation
- **WHEN** a developer sends a conversation larger than the model's limit with "gink_fit": true
- **THEN** the answer comes, with the oldest turns left out

#### Scenario: A refusal
- **WHEN** the AI service refuses a request as too large
- **THEN** the error says so with the limit, and has no organization id or upgrade link
