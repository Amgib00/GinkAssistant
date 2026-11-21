## ADDED Requirements

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
