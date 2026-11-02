## ADDED Requirements

### Requirement: Own model behind a switch
The server SHALL serve Gink's own model from an OpenAI-style provider only when GINK_OWN_BASE, GINK_OWN_KEY and GINK_OWN_MODEL are set, under the name GINK_OWN_NAME (default gink-1), and while GINK_OWN_TESTERS is set, only to those accounts.

#### Scenario: Testing before launch
- **WHEN** GINK_OWN_TESTERS lists the owner and another account asks for gink-1
- **THEN** that account is told the model isn't available and doesn't see it in the model list

### Requirement: No silent substitution
When the own model's provider fails, the server SHALL return the error instead of answering with a different model.

#### Scenario: Provider down
- **WHEN** the own model's provider answers 503
- **THEN** the person gets an error, not an answer from another model

### Requirement: Ship only when measured
A new own model SHALL be launched only when tools/gink_model/gate.py passes against the current baseline on the held-out examples and a person has reviewed its answers.

#### Scenario: Worse at one action
- **WHEN** the candidate is better overall but clearly worse at one action
- **THEN** gate.py says "not yet" and names the action
