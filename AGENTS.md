# Working on Gink (for AI coding assistants and developers)

Gink uses **OpenSpec** (spec-driven development). Before changing behaviour:

1. Read `openspec/config.yaml` (constraints you can't infer from the code) and the relevant
   `openspec/specs/<capability>/spec.md` (what Gink must do; every requirement has scenarios).
2. For new features or behaviour changes, propose first: `openspec/changes/<verb-led-id>/` with
   `proposal.md` (why, what changes, out of scope, platforms), `tasks.md`, optional `design.md`,
   and delta specs (`## ADDED|MODIFIED|REMOVED Requirements`, each with `#### Scenario:`).
   Example in progress: `openspec/changes/add-connected-apps/`.
3. Implement the tasks, then archive the change so its specs merge into `openspec/specs/`.

Validate with `npx @fission-ai/openspec@1.14.3 validate --all --strict` (GitHub runs it too).

## Code
- App: `src/ginkassistant` (Toga UI in `ui/`, logic in `services/`); server:
  `services/backend_server.py` (FastAPI); web app: `webapp/` (built by `tools/build_web_app.py`);
  CLI: `cli/`; website: `website/` (built by `tools/build_website.py`).
- Tests: `python -m pytest tests` -- must pass on Python 3.12 and 3.10. UI changes also get a
  real-browser check (Playwright), Android changes a check on a 32-bit phone.
- Publishing: `bash tools/publish_to_github.sh` (only files in `tools/MANIFEST.txt`, secret scan).
- Read `INTEGRATION.md` for the history of decisions, and `CHANGELOG.md` for what users got.
