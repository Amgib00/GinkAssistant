## Why

The owner asked for (1) room to grow far beyond one server's 1 GB disk, (2) problems found automatically,
and (3) seeing Gink's own Facebook, Instagram and TikTok -- without connect buttons -- plus better tools
for Gink's own models. A request for 1,186 TB reserved up front and for finding anyone's social accounts
were declined (cost; privacy and the platforms' rules) in favour of pay-by-use storage and the owner's
own accounts.

## What Changes

- services/blob_store.py: content-addressed blobs on disk or S3-compatible object storage (R2, B2, S3);
  Genie keeps contents over 8 KB there (versions and copies share them; daily clean-up). Limits grow with
  object storage (500 MB / 5,000 files per project, 100 projects; env overrides).
- Error reports: POST /errors from apps (sys/thread/asyncio hooks + caught errors) and the web app
  (window error / unhandledrejection), and the server's own crashes; grouped, scrubbed, rate-limited;
  owner dashboard "Problems in the apps"; Settings > Privacy > Send error reports.
- Owner dashboard "Social accounts": Facebook Page, Instagram, TikTok (tokens in env; TikTok renewal);
  read-only, cached 15 minutes, owner only.
- Gink's own models: build_mix.py (chat + Genie sessions, each line with its own tools, Genie share
  capped); train_unsloth.py and prepare_hosted.py use a line's own tools.

## Impact

- New spec: operations. Server, apps (error hook, one setting), web app, owner dashboard, tools.
