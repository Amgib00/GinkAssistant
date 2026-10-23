## Context

Gink already signs people in with Google (identity only) through the server's OAuth flow
(_login_response). Connected Apps needs separate, narrower, revocable grants for data access.

## Decisions

- Separate consent per service with the smallest scopes: calendar.readonly + calendar.events
  (writing only with approval), gmail.readonly + gmail.compose (drafts; sending is a separate,
  always-asked action), drive.metadata.readonly. Incremental authorization: nothing is asked
  until the person connects that service.
- Tokens: refresh tokens sealed with _seal, never returned to any client; access tokens kept in
  memory. Table connections(email, service, sealed_refresh, scopes, created, last_used).
- The tools run on the server: the apps and web app call /connected/<service>/<action>, so every
  platform (including the 32-bit Android edition) gets it without new libraries.
- Results are passed to the AI for the answer and never stored.

## Risks / Trade-offs

- Gmail's restricted scopes require Google's verification (and possibly a security assessment)
  before anyone outside the test users can connect Gmail. Calendar and Drive metadata are
  lighter; ship those first if verification takes long.
- Email content can contain prompt injection ("ignore your instructions and forward..."):
  connected content is passed as quoted data, and any writing action stays approval-gated.
