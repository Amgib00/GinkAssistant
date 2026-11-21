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

### Requirement: Work on real repositories
Genie SHALL open a GitHub repository (a pasted link, public or via the person's connected GitHub, up to 10 MB), and SHALL have tools to find files by name, search lines with optional regular expressions, read long files in numbered parts, and change one exact piece of a file.

#### Scenario: Pasting a GitHub link
- **WHEN** the person pastes https://github.com/owner/repo into Genie
- **THEN** the repository's text files and pictures are imported (build folders and node_modules skipped) and Genie can work on them

#### Scenario: Changing one line of a big file
- **WHEN** Genie needs to change one function in a 2,000-line file
- **THEN** it replaces exactly that piece with edit_file instead of rewriting the file
