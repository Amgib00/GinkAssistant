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
