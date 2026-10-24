# Developer API

## Purpose
An OpenAI-compatible API, with keys, limits, logs, batches and a console, for people building on Gink.

## Requirements

### Requirement: API keys
The system SHALL let a signed-in person create up to 10 keys (prefix gink_live_), show each key once, store only its hash, and revoke it at any time.

#### Scenario: Revoked key
- **WHEN** a revoked key is used
- **THEN** the request is refused with 401 and a message saying the key isn't valid

### Requirement: OpenAI-compatible chat
POST /v1/chat/completions SHALL accept the OpenAI request format (including stream: true and tools) and SHALL use Gink Crystal when no model is given.

#### Scenario: No model
- **WHEN** a request has messages but no model
- **THEN** it is answered with Gink Crystal (GPT-OSS 120B) instead of failing

#### Scenario: Malformed request
- **WHEN** the body has no messages list
- **THEN** the answer is 400 with a message saying what to send

### Requirement: Limits
API requests SHALL share the account's daily allowance with the apps, and each key SHALL be limited per minute (GINK_API_PER_MINUTE, default 30) with 429 and Retry-After.

#### Scenario: Per-minute limit
- **WHEN** a key makes more requests in a minute than allowed
- **THEN** it receives 429 with a Retry-After header

### Requirement: Published description
The server SHALL publish an OpenAPI 3.1 description of only the public /v1 endpoints at /v1/openapi.json, and SHALL NOT publish an automatic list of all its endpoints.

#### Scenario: Looking for internal endpoints
- **WHEN** someone opens /docs, /redoc or /openapi.json
- **THEN** they get 404, and /v1/openapi.json mentions no owner or admin endpoint

### Requirement: Request logs without contents
Every Developer API request SHALL be logged with its time, key, endpoint, model, status, duration and token counts (including for streamed answers), never its contents, and kept 30 days.

#### Scenario: Private message
- **WHEN** a request contains private text
- **THEN** the text appears nowhere in the logs or the database, while its tokens are counted

### Requirement: Developer console
/developers SHALL offer, to the signed-in person: Dashboard, Playground (with generated code), API keys, Usage per key, Metrics, Logs, Batches and Docs.

#### Scenario: Requests made with a key
- **WHEN** an app makes requests with a key created in the console
- **THEN** the Dashboard, Usage, Metrics and Logs show those requests

### Requirement: Batches
POST /v1/batches SHALL accept up to 100 chat requests (each with a unique custom_id and a body), run them in the background through the same code and limits as live requests, report progress, return results as JSONL, allow cancelling, and continue after a server restart.

#### Scenario: Mixed results
- **WHEN** a batch has two valid requests and one that fails
- **THEN** it completes with 2 completed and 1 failed, and the results file has all three

#### Scenario: Restart
- **WHEN** the server restarts while a batch is running
- **THEN** the batch resumes and finishes the remaining requests

#### Scenario: Someone else's batch
- **WHEN** another account asks for a batch's results or cancels it
- **THEN** the answer is 404

### Requirement: Device sign-in for the CLI
`gink login` SHALL sign in through the browser: the CLI shows a short code (no vowels, expiring in 10 minutes), the signed-in person sees at /device what is asking with a warning to continue only if they started it, and on approval the CLI receives a new API key exactly once; code guessing and starts SHALL be limited and approvals recorded in Security history.

#### Scenario: Someone else's code
- **WHEN** a person is asked by someone else to enter a code
- **THEN** the page tells them to choose Deny, and Deny gives the device nothing
