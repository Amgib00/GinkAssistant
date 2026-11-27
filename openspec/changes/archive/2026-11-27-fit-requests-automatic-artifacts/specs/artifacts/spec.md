## MODIFIED Requirements

### Requirement: Finished things as artifacts
When Gink makes something complete -- a web page or small app, a React component, a chart, a table of data, slides, an SVG image, a Mermaid diagram, a document to keep, or a code file -- it SHALL come as one titled block that the chat shows as a card; opening the card SHALL show it beside the chat with a live preview where it applies, its code, copy and download, and Gink SHALL never tell the person to save it into a file themselves. Short snippets and commands SHALL stay ordinary code blocks.

#### Scenario: A timer page
- **WHEN** someone asks for a pomodoro timer page
- **THEN** the answer shows a "Pomodoro timer" card and the page opens beside the chat, working

## ADDED Requirements

### Requirement: React, charts, tables and slides
A React component (jsx or tsx) SHALL preview as a working app (its React imports provided, Tailwind classes styled); a chart (Chart.js settings) SHALL be drawn; a table (CSV) SHALL show with headings that sort it, numbers as numbers; slides (Markdown split by ---) SHALL be presented one at a time with arrows, a swipe or full screen.

#### Scenario: A budget table
- **WHEN** Gink makes a budget as a CSV table and the person taps the cost heading
- **THEN** the rows sort by cost, 120 before 450 before 1,200

### Requirement: Libraries and downloads of the new kinds
The preview libraries SHALL be exact versions, loaded only inside the sealed preview; without the internet the preview SHALL say so. A chart or slides SHALL download as a page that opens anywhere, a table as its CSV.

#### Scenario: Offline
- **WHEN** a React artifact is opened without the internet
- **THEN** the preview says it needs the internet, and the code is still there to read and download

### Requirement: Finished quality
An artifact SHALL be complete and ready to use: real content (no placeholders), working on a phone and in dark mode; a new version SHALL keep everything that was there unless the person asked to remove it.

#### Scenario: Add more to it
- **WHEN** the person asks to add a section to a page
- **THEN** the new version has the new section and everything the page had before
