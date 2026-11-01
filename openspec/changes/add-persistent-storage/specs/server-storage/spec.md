## ADDED Requirements

### Requirement: Accounts survive restarts
On Render, the server SHALL keep its database (accounts, synced chats, payments, keys) on a mounted disk named by GINK_DB_PATH, so that restarts and new publishes keep every account.

#### Scenario: Publishing a new version
- **WHEN** the owner publishes a new version and the server restarts
- **THEN** people sign in with their existing accounts and see their synced chats

### Requirement: Storage status
The server SHALL report where its data lives as "disk", "temporary" or "local" in /health (without the file path) and on the owner dashboard, and SHALL treat a Render server without GINK_DB_PATH, or without a disk mounted at that path, as "temporary": logged at startup, listed as a problem on the owner dashboard and sent as an owner alert when alerts are set up.

#### Scenario: Disk missing
- **WHEN** the server starts on Render with GINK_DB_PATH set but no disk mounted there
- **THEN** /health shows "storage": "temporary" and the owner dashboard warns that accounts will be erased

#### Scenario: Disk present
- **WHEN** the disk is mounted and writable
- **THEN** /health shows "storage": "disk" and the dashboard shows no storage warning

### Requirement: Owner backup
The server SHALL let only the owner (GINK_ADMIN_KEY, with the existing lockout after wrong keys) download a consistent copy of the whole database, made with SQLite's backup while the server keeps running.

#### Scenario: Downloading a backup
- **WHEN** the owner runs tools/backup_db.py with the right key
- **THEN** a gink-backup-<date>.db file is saved that opens in SQLite and contains every account

#### Scenario: Wrong key
- **WHEN** anyone asks for /admin/backup without the right key
- **THEN** the server refuses with 403 and sends no data
