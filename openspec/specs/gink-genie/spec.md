# Gink Genie

## Purpose
A coding workspace where Gink builds and changes whole multi-file projects with the person, previews web projects safely, and lets them download or upload projects.

## Requirements

### Requirement: Build and change projects with AI
Genie SHALL build a project from a description and change existing projects on request, using file tools (list, read, write, delete, search) in a loop of at most 24 steps per request, and SHALL report which files it created, changed or deleted; each request SHALL count toward the daily allowance.

#### Scenario: Building from an idea
- **WHEN** the person asks for "a school app with a student list"
- **THEN** Genie writes the project's files and lists them in its reply

### Requirement: Files stay inside the project
Paths SHALL be relative and plain (no "..", no absolute paths, at most 8 folders deep), files at most 300 KB, projects at most 200 files and 3 MB, and 30 projects per account; refusals SHALL be explained to the AI so it can correct itself.

#### Scenario: Escaping the project
- **WHEN** the AI tries to write "../../etc/passwd"
- **THEN** nothing is written and the AI is told the path isn't valid

### Requirement: Safe previews
Web projects SHALL be previewed at a secret address, served with a sandbox (no allow-same-origin) so they can run their own scripts and styles but cannot read Gink's sign-ins, and cannot submit forms anywhere.

#### Scenario: A preview tries to read the sign-in
- **WHEN** a previewed project reads localStorage
- **THEN** it gets a security error

### Requirement: Workspace
The /genie page SHALL offer the person's projects, a file list with folders, an editor (Tab, Ctrl/Cmd+S, unsaved marker), Genie's chat for each project kept while the page is open, Preview, Download ZIP and Upload ZIP (text files imported; node_modules, .git and binary files skipped); only the owner SHALL see a project, and deleting the account deletes them.

#### Scenario: After Genie answers
- **WHEN** Genie changes files
- **THEN** the chat keeps every message and the open file reloads without asking about unsaved changes
