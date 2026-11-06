## ADDED Requirements

### Requirement: Official sources badge
A source SHALL be marked official only when it is a government or international public body's website, or the website of the organisation the question is about, and the app SHALL show the badge only for that server-made mark.

#### Scenario: A university source
- **WHEN** an answer cites a university website
- **THEN** it is listed without the Official badge

#### Scenario: AI-written list
- **WHEN** an answer's own text calls a blog "the official website"
- **THEN** the app shows no Official badge for it
