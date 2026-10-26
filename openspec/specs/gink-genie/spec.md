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

### Requirement: Running code in the browser
The workspace SHALL run the open .py or .js file, and pytest when the project has test files, inside a sandboxed frame in the person's browser (Python via a pinned Pyodide release), never on the server; output and errors SHALL appear in a console panel, input() SHALL explain that there is no keyboard, Stop SHALL end a run at once, and runs SHALL stop after 2 minutes.

#### Scenario: Code tries to read the sign-in
- **WHEN** code being run reads Gink's localStorage
- **THEN** it gets a security error and the sign-in stays private

### Requirement: Upload to GitHub
People SHALL be able to connect GitHub separately from signing in (repository permission, the token stored encrypted and never sent to the browser or to another service), push a project to a new or existing repository (private by default) as one commit on top of the branch with files deleted in Genie removed, and disconnect, which revokes the token at GitHub; account deletion SHALL revoke it too.

#### Scenario: Pushing twice
- **WHEN** a project is pushed, a file is deleted in Genie, and it is pushed again
- **THEN** the second commit builds on the first and the deleted file is gone from the repository

### Requirement: Gink Genie app
Gink Genie SHALL also be its own app for Mac, Windows, Linux and Android (64- and 32-bit), built from the same project, opening the workspace from the Gink server with the same account and offering Home, Back, Reload and Open in browser.

#### Scenario: Server asleep
- **WHEN** the app starts while the server is waking up or offline
- **THEN** it shows "Opening Gink Genie" and then the workspace, or "Can't reach Gink" with Retry

### Requirement: Links that leave the app
The app SHALL add a "GinkGenieApp" mark to its browser identity (never replacing it) so the page opens Preview and GitHub in the same window, and SHALL open those pages in the real browser where the platform allows catching links.

#### Scenario: Connecting GitHub from the app
- **WHEN** the person connects GitHub in the app on Mac, Windows or Android
- **THEN** GitHub's page opens in their browser and the app notices the connection

### Requirement: Separate builds
Each app's builds SHALL name their app, so building Gink never builds Gink Genie and the other way round, and a release SHALL publish both apps' installers.

#### Scenario: A release
- **WHEN** a release runs
- **THEN** it publishes Gink's and Gink Genie's installers for every platform

### Requirement: Genie runs commands in the browser
Genie SHALL be able to run `python FILE`, `pytest`, `node FILE`, `ls` and `cat FILE` to check its work: the server pauses the request (for at most 15 minutes, for the same person and project, resumable once), the person's browser runs the command in the sandboxed runner, and the output and exit code go back to Genie; any other command SHALL be answered as unavailable, never run on the server.

#### Scenario: Checking its own code
- **WHEN** Genie writes main.py and asks to run `python main.py`
- **THEN** the browser runs it and Genie receives "exit code: 0" and the real output

### Requirement: Steps and files
Each answer SHALL show Genie's work as a collapsible list of steps (created, updated, read, deleted, searched, ran a command with its output and result); the "+" and drag and drop SHALL add any text or code files and unpack ZIP files automatically, telling the person what was added and what was skipped.

#### Scenario: Adding a ZIP and a picture
- **WHEN** the person adds shop.zip and logo.png
- **THEN** the ZIP's files are unpacked into the project and the picture is skipped with a note

### Requirement: Pictures in projects
Projects SHALL accept PNG, JPG, GIF, WebP and ICO pictures up to 1 MB each (checked by their content, not only their name) through "+", drag and drop or ZIP files; the preview, ZIP download and GitHub upload SHALL use the exact picture bytes, the workspace SHALL show a picture when it is opened, and Genie SHALL be able to use pictures by their path but never read or write them as text.

#### Scenario: A website with a logo
- **WHEN** the person adds logo.png and an index.html that shows it
- **THEN** the preview displays the logo
