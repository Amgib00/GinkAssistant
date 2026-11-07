## Why

The owner wants hospitals (and other organisations) to use Gink. Patient data would need agreements
with every AI provider, an agreed data location, audit logs and clinician sign-off -- so the first step
is a workspace for work WITHOUT patient data, with a healthcare mode that keeps it out.

## What Changes

- Workspaces: an adult creates one; admins invite people by Gink account; members accept first; one
  workspace per person; admins see names and today's message counts (never chats), set instructions
  Gink follows for everyone, add admins, remove people, delete the workspace (typing its name).
- Healthcare mode: rules for the AI (no diagnosis or treatment decisions for a specific patient; clinical
  decisions belong to qualified staff; follow emergency procedures) and a guard that refuses messages
  that look like a patient's details (name after "patient", record numbers, dates of birth, phones) --
  in chat, Genie and websites.
- Settings > Workspace in the apps and the web app.

Out of scope: patient data (option 2), single sign-on, billing per workspace, audit logs.

## Impact

- New spec: workspaces. Server, Settings panel.
