## ADDED Requirements

### Requirement: Workspaces
An adult SHALL be able to create a workspace and invite Gink accounts; invited people SHALL join only after accepting; admins SHALL see members and their message counts for today but never their chats; Gink SHALL follow the workspace's instructions for its active members.

#### Scenario: An invitation
- **WHEN** an admin invites a colleague
- **THEN** nothing applies to the colleague until they accept in Settings > Workspace

### Requirement: Healthcare mode keeps patient data out
In a workspace in healthcare mode, Gink SHALL refuse requests in chat, Genie and websites that look like they contain a patient's identifying details, and SHALL not diagnose or decide treatment for a specific patient.

#### Scenario: A patient's name
- **WHEN** a member asks "Summarise the notes for patient Mamadou Diallo"
- **THEN** Gink refuses and explains the workspace must not be used with patient data

#### Scenario: General work
- **WHEN** a member asks for a night-shift rota
- **THEN** Gink helps as usual
