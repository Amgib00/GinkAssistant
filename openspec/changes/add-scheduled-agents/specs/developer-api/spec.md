## ADDED Requirements

### Requirement: Scheduled agents
Developers and console users SHALL be able to schedule an agent task hourly, daily or weekly at a time in a time zone; each due run SHALL start an ordinary interaction in the schedule's environment, and schedules SHALL be pausable, runnable on demand and deletable.

#### Scenario: Every morning
- **WHEN** a schedule says daily at 08:00 in Europe/Berlin
- **THEN** at 08:00 Berlin time an interaction runs in its workspace and the next run is the following morning

#### Scenario: Paused
- **WHEN** a schedule is paused
- **THEN** it doesn't run until it's resumed

### Requirement: Signed webhooks
Interactions and schedules SHALL accept a webhook_url (https, public internet addresses only); when a run ends Gink SHALL POST the interaction to it, signed with the account's webhook secret in the Gink-Signature header, retrying a few times, without delaying the API's answer.

#### Scenario: A finished scheduled run
- **WHEN** a schedule with a webhook_url finishes a run
- **THEN** the URL receives {"type": "interaction.completed", "data": ...} with a signature the SDKs can verify
