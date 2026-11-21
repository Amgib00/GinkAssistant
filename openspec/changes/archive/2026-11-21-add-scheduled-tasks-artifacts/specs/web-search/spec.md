## ADDED Requirements

### Requirement: Reading the pages people share
When a message in the apps or the web app links to web pages, Gink's server SHALL read them itself (at most two, public addresses only, checked again after connecting and on every redirect) and the answer SHALL come from their text, which is given to the AI as data, never as instructions; a page that can't be read SHALL be said so.

#### Scenario: A pricing page
- **WHEN** someone asks "how much is Pro?" with a link to a pricing page
- **THEN** the answer uses the page's text and names the page

#### Scenario: A private address
- **WHEN** a link points to a private or local address, or redirects there
- **THEN** nothing is fetched from it and the answer says the page couldn't be read

### Requirement: Searching by itself
When an answer needs today's facts, the apps and the web app SHALL search the web without being asked, unless the person turned web search off.

#### Scenario: Today's news
- **WHEN** someone asks what happened today in their city
- **THEN** Gink searches and the answer lists its sources
