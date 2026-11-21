## Why

A review of Gink Genie found four problems: age and parental controls (added in 0.1.96) didn't apply to
Genie's AI; when the AI service stopped answering partway, files were already changed but the request
vanished from the conversation; every request stored a full copy of the project for version history
even when nothing changed (up to 60 MB per project on a 1 GB disk); and a refused new project (daily
limit, AI error) left an empty project behind.

## What Changes

- Genie follows age and parental controls like chat: under-13 accounts are refused; quiet hours and the
  daily message limit apply; teens get the stricter safety guidance; linked teens' requests get the same
  safety check; a new "Gink Genie" switch in Settings > Parental controls turns it off.
- If the AI stops answering after Genie changed files, the changes are kept and the reply says so (with
  undo); with nothing changed it's an error to retry; "busy" (HTTP 429) is said plainly.
- Version history: no new copy when the project hasn't changed; at most 15 MB per project (newest first,
  20 versions at most, the newest always kept).
- Creating a project whose first request is refused before anything is written removes the empty project.

Reviewed and fine: path checks, preview sandbox (CSP sandbox without same-origin, no form posts, framed
only by Gink), the page renders AI text with textContent (no HTML injection).

## Impact

- Modified spec: gink-genie. Server and the Settings panel (one more switch).
