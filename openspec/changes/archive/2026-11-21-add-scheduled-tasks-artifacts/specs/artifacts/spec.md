## ADDED Requirements

### Requirement: Finished things as artifacts
When Gink makes something complete -- a web page or small app, an SVG image, a Mermaid diagram, a document to keep, or a code file -- it SHALL come as one titled block that the chat shows as a card; opening the card SHALL show it beside the chat with a live preview where it applies, its code, copy and download. Short snippets and commands SHALL stay ordinary code blocks.

#### Scenario: A timer page
- **WHEN** someone asks for a pomodoro timer page
- **THEN** the answer shows a "Pomodoro timer" card and the page opens beside the chat, working

### Requirement: Versions
A later block with the same title SHALL be the next version of the same artifact, and the viewer SHALL let the person go back to earlier versions.

#### Scenario: Make it dark
- **WHEN** the person asks for changes and Gink writes the whole page again with the same title
- **THEN** the card says version 2 and the viewer can switch between versions 1 and 2

### Requirement: Sealed previews on the web
In the web app, a page artifact SHALL run in a sealed frame on its own terms (no access to the person's account or storage), also when opened in a tab of its own.

#### Scenario: A page that reads storage
- **WHEN** an artifact's script tries to use the web app's storage
- **THEN** it can't, and the rest of the page still runs
