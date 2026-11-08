## Why

The owner wants Gink's API to offer managed agents like Google's (Managed Agents in the Gemini API): one
API call runs a hosted agent in a remote environment whose files persist across sessions.

## What Changes

- POST /v1/interactions (agent "gink-agent"): runs Gink Genie's agent (file tools without run_command, plus
  web search) in an environment; returns output_text, steps, files_changed; previous_interaction_id
  continues a conversation; background + GET /v1/interactions/{id}; cancel; max_steps 1-30.
- Environments = Gink Genie projects: /v1/environments (create, list, get, delete) and files (PUT/GET);
  a version is saved before every interaction (Genie's Undo works).
- Limits and rules: one message per interaction (steps count as calls), age/parental/workspace/lockdown rules;
  running interactions are marked failed after a server restart.
- No code execution on the server (needs a sandboxed computer per environment; not this server).
- /developers/agents guide page (Gink's own design); console Docs link; `gink agent "task"` in the CLI.

## Impact

- Modified spec: developer-api. Server, console, CLI.
