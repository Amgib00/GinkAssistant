## ADDED Requirements

### Requirement: Links in the API
`POST /v1/links/read` ({"url"}, {"urls"} up to three, or {"text"}; "look" and "listen" false to skip pictures or audio) SHALL return each link's site, kind, title, author, date, length, counts, caption, words, what its picture shows, what's said in it and why not, with "for_ai", the note Gink's chat gives the AI. The Python and JavaScript SDKs and the CLI (`gink read URL`) SHALL use it, and "gink_web": "auto" SHALL open links in chat the same way.

#### Scenario: A reel through the API
- **WHEN** a developer reads https://www.facebook.com/reel/2322629778521786 with client.read_link
- **THEN** they get kind "reel", the site "Facebook" and what could be seen of it

#### Scenario: Too many links
- **WHEN** a developer sends four links at once
- **THEN** the answer is a 400 "too_many_links"
