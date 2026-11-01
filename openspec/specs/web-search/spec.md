# Web search

## Purpose
Answers that need current information come from the live web, cleanly written, with their sources, within a daily allowance.

## Requirements

### Requirement: Searching the web
Requests with model gink-search, or flagged gink_web by the apps, SHALL run on GPT-OSS with Groq's browser_search tool, with reasoning effort low.

#### Scenario: A question that needs the internet
- **WHEN** a person asks for "the latest news in Senegal" in the web app
- **THEN** the request is sent as a web search

### Requirement: Clean answers with sources
Citation marks such as 【2†L6-L10】 SHALL be removed, also when split across streamed pieces, and a Sources list SHALL be added from the pages the search used.

#### Scenario: A mark split across two pieces
- **WHEN** a streamed answer contains "2026 【1" in one piece and "†L3-L5】." in the next
- **THEN** the person sees "2026." with no mark and no stray space

### Requirement: Daily search allowance
Web searches SHALL be limited per day (GINK_FREE_SEARCH_DAILY, default 10; GINK_PRO_SEARCH_DAILY, default 100), counting one search per question.

#### Scenario: Allowance used up
- **WHEN** the day's searches are used up
- **THEN** search requests get 429 with a clear message, and normal chat still works

### Requirement: Another model answers when one can't
When the AI provider refuses a request because the model is at its limit, overloaded or unavailable, the server SHALL try up to 3 other available models (best first; searching requests only other GPT-OSS models; requests with photos none), removing settings the other model doesn't support, and SHALL say which model answered; other refusals SHALL return their reason at once.

#### Scenario: The main model is at its daily limit
- **WHEN** GPT-OSS 120B answers "rate limit reached"
- **THEN** the answer comes from GPT-OSS 20B and the response names it

### Requirement: Gink searches by itself
In the apps and on the web, messages that need current or factual information from the web SHALL be searched automatically, except writing, coding and translating requests (unless they ask to search) and questions live data answers; "gink_web": false turns it off, developer API keys decide for themselves, and over the daily search allowance the answer comes without searching.

#### Scenario: A question about a country's president
- **WHEN** someone asks "Who is the president of Ghana?" without choosing Gink Search
- **THEN** Gink searches the web before answering

### Requirement: Official sources first
Searches SHALL prefer official and primary sources (government sites, the organisation's own website, official documentation), and official sources SHALL be listed first and marked official.

#### Scenario: Ranking sources
- **WHEN** a search returns a news site and a government site
- **THEN** the government site is listed first, marked official

### Requirement: Sources button
An answer's sources SHALL appear as a Sources button in its row of actions (the sites' initials and a count), opening the list with each source's title, site and an Official badge where it applies.

#### Scenario: Opening the sources
- **WHEN** the person clicks "2 sources" under an answer
- **THEN** the list opens with the official source first
