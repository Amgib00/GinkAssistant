## Why

Managed agents ran only when asked. Many useful agents are routine: a morning brief, a weekly report, a page
kept current. The owner asked for every feature across the whole suite.

## What Changes

- agent_schedules (hourly at :MM, daily or weekly at HH:MM in a time zone; the device's by default); a runner loop
  starts due schedules every minute as ordinary background interactions (same limits, rules and Genie record).
- API (/v1/schedules) and console (/dev/schedules): create, list, pause/resume (PATCH enabled), run now, delete;
  at most 10 per account (GINK_SCHEDULE_MAX).
- Console Agents page: "Schedule it" and a Scheduled table. Python SDK client.schedules, JS SDK gink.schedules (+
  types), CLI `gink schedule add|list|run|pause|resume|rm`. SDKs 0.3.3.

## Impact

- Modified spec: developer-api. Server, console, SDKs, CLI.
