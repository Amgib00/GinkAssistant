## ADDED Requirements

### Requirement: Genie opens links
Links in a Genie request SHALL be opened before Genie starts (each shown as a step), and Genie SHALL be able to open a link itself while it works, in plan mode too; not when parental controls or Lockdown mode turn the web off.

#### Scenario: A site to look like another
- **WHEN** someone asks Genie to "make my bakery's site look like https://..."
- **THEN** Genie opens the page first and builds from what it says
