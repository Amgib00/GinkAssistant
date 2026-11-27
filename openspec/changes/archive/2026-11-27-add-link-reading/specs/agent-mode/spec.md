## ADDED Requirements

### Requirement: Agents open links
Agents (managed agents, scheduled tasks and the apps' agent) SHALL open links with Gink's link reader -- pages, PDFs, posts and reels, as data between markers -- and only when it can't, search the web for the page. The apps' agent SHALL have read_link, off when "Search the web" is off; with the person's own Groq key the apps SHALL open links on the device.

#### Scenario: An agent opens a PDF
- **WHEN** a managed agent is asked to summarise a linked PDF
- **THEN** its read_page step returns the PDF's text
