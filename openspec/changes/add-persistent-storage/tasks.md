## 1. Build
- [x] 1.1 render.yaml: Starter plan, disk at /var/data, GINK_DB_PATH=/var/data/gink.db
- [x] 1.2 Server: _storage_status() (disk / temporary / local) in /health and the owner dashboard; a missing disk is a dashboard problem and an alert
- [x] 1.3 SQLite write-ahead log and a 10-second wait for busy writes
- [x] 1.4 GET /admin/backup (owner only) and tools/backup_db.py
- [x] 1.5 Tests: tests/test_server_storage.py (local, no GINK_DB_PATH on Render, no disk mounted, disk mounted, startup problem, WAL, backup owner-only, backup contents)

## 2. Owner, in Render
- [ ] 2.1 Upgrade gink-server to Starter and add the disk (Blueprint sync, or by hand in the dashboard)
- [ ] 2.2 Check https://gink-server.onrender.com/health shows "storage": "disk"
- [ ] 2.3 Sign up, publish again, and confirm the account is still there
- [ ] 2.4 Download a first backup with tools/backup_db.py
