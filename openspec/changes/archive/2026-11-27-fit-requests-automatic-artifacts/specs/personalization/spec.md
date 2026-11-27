## MODIFIED Requirements

### Requirement: Question cards and recalled memories
When Gink truly can't do a good job without something only the person knows it SHALL be able to ask 1 to 3 questions as a card with 2 to 4 tappable options each, a line to type their own answer, Skip and paging, sending all answers as the person's next message; what the person types SHALL be their answer (the send arrow lights up, Enter or the arrow sends it), and the AI's own "Other" options SHALL be left out; and before each answer the memories matching the message (shared meaningful words, at most 3) SHALL be shown as "Recalled memory" and used, in the apps and on the web (memories reach the web through sync), unless memory is turned off.

#### Scenario: Asking about exams
- **WHEN** the person saved "My exams start on 12 November" and asks "When are my exams?"
- **THEN** "Recalled memory: My exams start on 12 November" appears above the answer

#### Scenario: Typing an answer
- **WHEN** the person types "Any you choose" on a question card
- **THEN** the send arrow lights up and sending gives "My answers: ... -> Any you choose"

## ADDED Requirements

### Requirement: Gink just makes it
An open request -- "make me anything", "surprise me", "add more to it", "continue", "improve it" -- SHALL be made directly with sensible choices and one short line saying what was chosen, never answered with questions about which kind, style or colours.

#### Scenario: Make me anything
- **WHEN** someone says "make me anything"
- **THEN** Gink makes something complete and says in a line what it chose, without a question card
