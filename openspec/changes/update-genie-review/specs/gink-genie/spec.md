## ADDED Requirements

### Requirement: Genie follows age and parental controls
Genie SHALL refuse accounts under 13, apply a linked teen's quiet hours, daily message limit and "Gink Genie" switch, give every teen the stricter safety guidance, and run the safety check on linked teens' requests.

#### Scenario: Parent switched Genie off
- **WHEN** a linked teen whose parent turned Gink Genie off creates a project with a request
- **THEN** it is refused with the reason and no project is left behind

### Requirement: Partial work is never lost
When the AI service stops answering after Genie changed files, Genie SHALL keep the changes, record the request and an explanation in the project's conversation, and offer undo.

#### Scenario: Busy partway
- **WHEN** the AI service answers "busy" after Genie wrote a file
- **THEN** the file stays, and the conversation says Genie stopped partway and the changes can be undone

### Requirement: Version history fits the disk
Genie SHALL not store a new version when the project is unchanged, and SHALL keep at most 20 versions and 15 MB of versions per project, always keeping the newest.

#### Scenario: A question that changes nothing
- **WHEN** the person asks Genie something that changes no files
- **THEN** no new version is stored
