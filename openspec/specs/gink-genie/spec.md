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

### Requirement: Genie remembers each project's conversation
Each finished request and Genie's answer (with its steps and changed files) SHALL be saved with the project (the last 400 messages), shown again when the project is opened on any device, and the last 6 exchanges SHALL be given to Genie with each new request; deleting the project or the account SHALL delete the conversation.

#### Scenario: A follow-up
- **WHEN** the person asked for a shop website and then asks "make the buttons green"
- **THEN** Genie receives the earlier request and its own answer before the new request

### Requirement: Undo Genie's changes
Before each request Genie SHALL save a checkpoint of the whole project (the 5 most recent are kept); an answer that changed files SHALL offer "Undo these changes", which, after confirmation, puts the project back exactly as it was before that request (files, deletions and pictures) and notes the undo in the conversation; older answers SHALL explain they are too old to undo.

#### Scenario: Undoing a change
- **WHEN** Genie changed index.html and added page2.html, and the person undoes it
- **THEN** index.html is as before and page2.html is gone

### Requirement: Diffs for updated files
When Genie updates an existing text file, its step SHALL be titled with the number of lines added and removed and SHALL open to a short diff (removed lines in red, added lines in green, with 2 lines of context); new files SHALL show their content.

#### Scenario: Changing one value
- **WHEN** Genie changes the tax line in app.js
- **THEN** the step reads "Updated app.js (+1 −1)" and shows the old line removed and the new one added

### Requirement: Live progress
While Genie works on a request, the page SHALL show its steps as they happen, refreshed about every 1.5 seconds, from progress that only the person who sent the request can see (kept for at most 30 minutes).

#### Scenario: A long request
- **WHEN** Genie writes four files over several seconds
- **THEN** the waiting message shows one step, then two, then three, before the final answer

### Requirement: Stop
While Genie works, the person SHALL be able to press Stop: a running request stops after its current step (never halfway through one), a request waiting for a command ends at once and its command result is ignored, the answer says it stopped before finishing, and the changes made so far are kept and can be undone.

#### Scenario: Stopping a long request
- **WHEN** Genie is writing four files and the person presses Stop after the first
- **THEN** Genie ends with "Stopped before finishing" having written fewer than four files

### Requirement: Plan first
A "Plan first" switch (remembered in the browser) SHALL make Genie only look at the project (list, read, search) and answer with a numbered plan, refusing any change or command even if the AI asks; the plan SHALL offer "Build this plan", which sends Genie ahead in Auto mode with the plan in its memory; only the latest plan in a conversation stays buildable.

#### Scenario: Approving a plan
- **WHEN** the person asks for a shop in Plan first mode and presses "Build this plan"
- **THEN** no file changes before the approval, and Genie builds the shop after it

### Requirement: Rename and duplicate projects
A project SHALL be renamable (1 to 60 characters) and duplicable: the copy, named "… (copy)", has exactly the same files including pictures, its own preview address and a fresh conversation, and changing it never affects the original.

#### Scenario: Trying an idea on a copy
- **WHEN** the person duplicates "Gink Shop" and changes the copy
- **THEN** "Gink Shop" keeps its files unchanged

### Requirement: Rename files and go to a file
The open file SHALL be renamable or movable to another folder (saving unsaved edits first), never overwriting an existing file, with pictures keeping a picture ending; Ctrl+P or Cmd+P SHALL open a search box that finds files by letters in order and opens the chosen one with Enter, closing with Escape.

#### Scenario: Finding a file
- **WHEN** the person presses Ctrl+P and types "abt"
- **THEN** pages/about.html is listed and Enter opens it

### Requirement: Search in the project
Ctrl+Shift+F or Cmd+Shift+F SHALL search the text of every code and text file (ignoring upper and lower case, at least 2 letters, up to 200 matches), list matches grouped by file with their line numbers, and open the chosen file with that line selected.

#### Scenario: Finding a function
- **WHEN** the person searches "addtocart"
- **THEN** every line containing addToCart is listed by file, and choosing one opens it with the line selected

### Requirement: Line numbers and cursor position
The editor SHALL show line numbers that scroll with the code and update while typing, and the cursor position as "Ln N, Col M"; both SHALL be hidden for pictures.

#### Scenario: Adding a line
- **WHEN** the person presses Enter at the end of a 30-line file
- **THEN** the numbers go to 31 and the position reads "Ln 31, Col 1"

### Requirement: Share and stop sharing
The Share window SHALL show the project's website link with Copy and Open, explaining that anyone with the link can view the website but not the code, conversation or anything editable; Stop sharing SHALL give the project a new private address so every earlier link stops working.

#### Scenario: Taking a link back
- **WHEN** the person presses Stop sharing
- **THEN** the old link answers "not found" and a new private link is shown

### Requirement: Genie on phones
On screens up to 700 px wide the workspace SHALL fit the screen without sideways scrolling: a one-row header with the project picker and a "more" menu holding every project action, and Files / Code / Genie tabs showing one panel at a time (Genie first; opening a file shows Code); larger screens keep the three panels side by side.

#### Scenario: Opening a file on a phone
- **WHEN** the person taps cart.js in the Files tab
- **THEN** the Code tab opens with cart.js and its Save button visible

### Requirement: Genie narrates and debugs itself
Genie SHALL say in one short sentence what it is doing before each group of actions (shown in its step list), and after writing or changing code SHALL run it, fix the errors it finds and run it again before answering.

#### Scenario: A bug in the first version
- **WHEN** Genie's first run fails with an error
- **THEN** a step says what it is debugging, the file is updated, and a second run succeeds before the answer

### Requirement: Studio layout
On computers Genie SHALL show a projects sidebar, a top bar with the project's name (click to rename), Share and GitHub as icons and a "more" menu with the other project actions, the conversation in the centre with a Code tab for the open file, and files and settings on the right. Phones keep their own layout.

#### Scenario: Opening a file
- **WHEN** the person clicks cart.js in the files panel
- **THEN** the Code tab opens showing cart.js, and the Genie tab brings the conversation back

### Requirement: Start screen with ideas
The start screen SHALL say "Start building with Gink Genie", offer example prompts and starter cards that glow on hover, and choosing one SHALL fill the prompt box.

#### Scenario: Choosing a starter card
- **WHEN** the person clicks the Expense tracker card
- **THEN** the prompt box holds the expense tracker idea, ready to send
