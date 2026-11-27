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

### Requirement: Real-time information in answers
Every chat request through the server SHALL include the current date and time; when the newest message asks for live data (weather, time in a place, currency, crypto prices, air quality, sunrise and sunset, prayer times), the server SHALL fetch it with a short time limit and give it to the model, time-stamped.

#### Scenario: Weather through the API
- **WHEN** a developer's request asks "What's the weather in Dakar today?"
- **THEN** the model receives Dakar's current weather and today's date before answering

### Requirement: Developers control live data
Without a place the server SHALL tell the model to ask for one, and developers SHALL be able to turn the fetching off with "gink_live": false, which is never sent on to the AI service.

#### Scenario: Turning it off
- **WHEN** a request sets "gink_live": false
- **THEN** nothing is fetched, the date is still included, and the setting is removed before the AI service

### Requirement: Scheduled agents
Developers and console users SHALL be able to schedule an agent task hourly, daily or weekly at a time in a time zone; each due run SHALL start an ordinary interaction in the schedule's environment, and schedules SHALL be pausable, runnable on demand and deletable.

#### Scenario: Every morning
- **WHEN** a schedule says daily at 08:00 in Europe/Berlin
- **THEN** at 08:00 Berlin time an interaction runs in its workspace and the next run is the following morning

#### Scenario: Paused
- **WHEN** a schedule is paused
- **THEN** it doesn't run until it's resumed

### Requirement: Signed webhooks
Interactions and schedules SHALL accept a webhook_url (https, public internet addresses only); when a run ends Gink SHALL POST the interaction to it, signed with the account's webhook secret in the Gink-Signature header, retrying a few times, without delaying the API's answer.

#### Scenario: A finished scheduled run
- **WHEN** a schedule with a webhook_url finishes a run
- **THEN** the URL receives {"type": "interaction.completed", "data": ...} with a signature the SDKs can verify

### Requirement: Scheduled tasks in the API
The API SHALL offer `/v1/tasks` to create, list, read (with the latest results), change, pause, resume, run (optionally waiting for the result) and delete scheduled tasks for the key's account, with the same limits as the apps; both SDKs (`tasks`) and the CLI (`gink tasks`) SHALL use it.

#### Scenario: Run and wait
- **WHEN** a developer runs a task with wait true
- **THEN** the answer has the task, its status and the result's text

### Requirement: Chat options that work like Gink's apps
Chat requests SHALL accept `gink_tasks` (a schedule block for later or repeated requests), `gink_artifacts` (finished things in titled blocks), `gink_code` (GitHub repositories read) and `gink_web: "auto"` (linked pages read and the web searched when needed); the SDKs SHALL read schedule blocks (`schedules_in` / `schedulesIn`) and artifacts (`artifacts()` with kind, file name and version).

#### Scenario: Saving artifacts
- **WHEN** `gink --save-artifacts site "make a landing page"` runs
- **THEN** the page is saved in the site folder under a file name from its title

### Requirement: Tool slips are asked again
When a model calls a tool it wasn't given, calls one that isn't in the request's list, or writes a broken call, the server SHALL ask again by itself (without tools as plain text when none were given, with a note when they were, then on another model) before answering -- for chat completions, streamed or not, managed agents and scheduled tasks; developers still get any other error in the OpenAI format.

#### Scenario: Tool choice is none
- **WHEN** the AI provider answers "Tool choice is none, but model called a tool"
- **THEN** the caller gets an answer, not that error

### Requirement: Videos in the SDKs
The SDKs SHALL send a video the way the apps do: up to five frames in order, after a sentence that says what they are and when they were taken (`watch()`, `video_parts()` / `videoParts()`, `videoFrames()` in a browser), and the CLI SHALL take the frames with ffmpeg (`gink watch`).

#### Scenario: A clip from the command line
- **WHEN** someone runs `gink watch clip.mp4 "what happens?"` with ffmpeg installed
- **THEN** a few frames go to Gink in order and the answer is streamed

### Requirement: Fitting to the model's limits
A chat completion SHALL fit the model's limit by shrinking only the room for the answer, or go to another model that takes it (saying which in X-Gink-Model); with "gink_fit": true, older messages and earlier versions of an artifact MAY be left out like in Gink's apps. When the AI service refuses, the developer SHALL get its error with its status but without Gink's own account details, and a 413 SHALL mention "gink_fit". The SDKs SHALL know the artifact kinds react, chart, table and slides.

#### Scenario: A long conversation
- **WHEN** a developer sends a conversation larger than the model's limit with "gink_fit": true
- **THEN** the answer comes, with the oldest turns left out

#### Scenario: A refusal
- **WHEN** the AI service refuses a request as too large
- **THEN** the error says so with the limit, and has no organization id or upgrade link

### Requirement: Links in the API
`POST /v1/links/read` ({"url"}, {"urls"} up to three, or {"text"}; "look" and "listen" false to skip pictures or audio) SHALL return each link's site, kind, title, author, date, length, counts, caption, words, what its picture shows, what's said in it and why not, with "for_ai", the note Gink's chat gives the AI. The Python and JavaScript SDKs and the CLI (`gink read URL`) SHALL use it, and "gink_web": "auto" SHALL open links in chat the same way.

#### Scenario: A reel through the API
- **WHEN** a developer reads https://www.facebook.com/reel/2322629778521786 with client.read_link
- **THEN** they get kind "reel", the site "Facebook" and what could be seen of it

#### Scenario: Too many links
- **WHEN** a developer sends four links at once
- **THEN** the answer is a 400 "too_many_links"
