## ADDED Requirements

### Requirement: Managed agents
The Developer API SHALL run Gink's agent from one request (POST /v1/interactions) in an environment whose files persist across interactions, and SHALL return the agent's answer, its steps and the files it changed.

#### Scenario: A new environment
- **WHEN** a developer sends input with environment "remote"
- **THEN** a new environment is created, the agent works in it, and the response names it and the files changed

#### Scenario: Continuing
- **WHEN** a developer sends previous_interaction_id
- **THEN** the agent continues the same conversation in the same environment

### Requirement: Environments
The Developer API SHALL let developers create, list, read, upload to and delete environments, which are the same projects Gink Genie shows.

#### Scenario: Uploading data
- **WHEN** a developer PUTs a file into an environment and then asks the agent about it
- **THEN** the agent can read that file
