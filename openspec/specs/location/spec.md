# Location

## Purpose
Local answers (weather, briefing) without surprises.

## Requirements

### Requirement: Location settings
Settings > Location SHALL show the area in use (set by the person, or estimated from the IP address), let the person set a city or detect their approximate one, and offer "Use location in answers".

#### Scenario: Location turned off
- **WHEN** "Use location in answers" is off
- **THEN** Gink uses no city and makes no IP-based estimate, and asks when it needs a place
