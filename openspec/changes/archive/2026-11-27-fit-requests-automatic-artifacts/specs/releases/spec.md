## ADDED Requirements

### Requirement: The website is always whole
Every build of the website SHALL name its styles and scripts with that build's version and mark each page with it; a page the browser kept from an earlier build SHALL be loaded fresh once, so the site never shows half-styled.

#### Scenario: A tab brought back
- **WHEN** a browser shows a page it kept from before a new build
- **THEN** the page loads fresh with the new build, once
