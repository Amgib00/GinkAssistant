## MODIFIED Requirements

### Requirement: Lockdown mode
When the person turns on Lockdown mode, the server SHALL refuse web search they ask for, connected apps and images from web addresses for that account on every device and API path, with a message saying how to turn it off, while normal chat keeps working: Gink SHALL not search by itself and SHALL not open links.

#### Scenario: Web search in Lockdown mode
- **WHEN** someone asks for a web search while Lockdown mode is on
- **THEN** it is refused with "Lockdown mode is on, so Gink doesn't use web search"

#### Scenario: A question Gink would search for by itself
- **WHEN** a question that would need today's facts is asked while Lockdown mode is on
- **THEN** Gink answers without searching, and opens no links in it
