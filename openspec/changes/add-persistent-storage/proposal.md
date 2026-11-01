## Why

On Render's free plan the server has no disk, so every restart or new publish erased every
account, synced chat and payment. Gink can't have real users until accounts survive.

## What Changes

- render.yaml: Starter plan with a 1 GB disk at /var/data, and GINK_DB_PATH=/var/data/gink.db.
- The server checks at startup that the database really is on a mounted disk. /health reports
  "storage" (disk, temporary or local); a missing disk is logged, shown on the owner dashboard and
  emailed to GINK_ALERT_EMAIL.
- SQLite runs in write-ahead-log mode and waits up to 10 seconds for another write, so a stop in the
  middle of a write can't damage the database.
- Owner backup: GET /admin/backup (GINK_ADMIN_KEY) returns a consistent copy of the database;
  tools/backup_db.py downloads it.

Out of scope: moving to Postgres, more than one server instance (a Render disk allows only one),
automatic off-site backups, restoring a backup through the API (restore is a documented manual step).

Platforms: server only. The apps and web app are unchanged; they keep using the same server.

## Impact

- New spec: server-storage.
- Cost: Render Starter plan plus the disk (paid monthly by the owner).
- A server with a disk can't do zero-downtime deploys: each publish has a few seconds offline.
