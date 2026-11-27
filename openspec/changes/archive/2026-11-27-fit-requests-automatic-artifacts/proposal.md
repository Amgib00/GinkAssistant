## Why

The owner's four recordings showed: typing an answer on a question card ("Any you choose") left the send arrow
greyed out, so it could never be sent, and the AI's own "Other (type your own)" showed beside the card's own line;
"make me anything" got a card asking which kind of thing, then three more questions, and "add more to it" another
card; a long chat that made a page three times ended in "The AI service couldn't answer (error 413: Request too large
for model ... in organization org_... Limit 8000, Requested 17295)" -- and a 429 with the same account details; the
web app showed an opened chat as **raw** text first and its answered cards open and blank; the AI told him to "save
the snippet as index.html"; and the website looked half-styled. He asked to fix them, make Gink automatic, fix every
platform, add more and better artifacts, and do all the usual steps.

## What Changes

- Question cards: what's typed is the answer (the arrow lights up; the arrow or Enter sends it); the AI's "Other"
  options are left out (every card has its own line); duplicate options once.
- Automatic: open requests ("make me anything", "add more to it", "continue") are made with sensible choices and one
  line saying what was chosen; question cards only for what only the person knows; never "save it as a file".
- Fitting requests: earlier versions of an artifact never go along; every request to Groq fits the model's limit
  (less room for the answer, then older turns), or goes to a model that takes more; limits are learned from Groq's
  own answers; a refusal is asked again smaller or elsewhere; people get plain words, developers Groq's message
  without Gink's account details, and `"gink_fit": true` to let Gink fit their own conversations.
- More artifacts: React components, charts, tables (CSV) and slides, each with a live preview; finished quality.
- The web app: answers formatted as they arrive, an opened chat readable at once and its answered cards closed.
- The website: a page the browser kept from before is loaded fresh; versioned styles and scripts per build.

## Out of scope

- Editing an artifact by sending only its changes (a patch) instead of a whole new version.
- Previews with libraries other than React, Tailwind and Chart.js; running Python artifacts.
- Changing Groq's limits themselves (a paid plan is set with GINK_TPM_LIMITS).

## Platforms

Server, macOS (Catalina too), Windows, Linux, Android, iOS, the web app, Gink Genie, the API and managed agents, the
CLI and both SDKs (gink-ai 0.3.18), and the website.
