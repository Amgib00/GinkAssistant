## ADDED Requirements

### Requirement: Scheduled agents
Developers and console users SHALL be able to schedule an agent task hourly, daily or weekly at a time in a time zone; each due run SHALL start an ordinary interaction in the schedule's environment, and schedules SHALL be pausable, runnable on demand and deletable.

#### Scenario: Every morning
- **WHEN** a schedule says daily at 08:00 in Europe/Berlin
- **THEN** at 08:00 Berlin time an interaction runs in its workspace and the next run is the following morning

#### Scenario: Paused
- **WHEN** a schedule is paused
- **THEN** it doesn't run until it's resumed
