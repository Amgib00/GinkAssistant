"""
Keeps chats, Workspace items (tasks / reminders / events) and memories in
step across your devices through your Gink server's /sync endpoint.

* Runs while you're signed in: once at start, every SYNC_INTERVAL seconds,
  and a few seconds after anything changes locally.
* Sends everything changed since the last successful sync, receives
  everything other devices changed. Newest change wins; deletions sync.
* Never blocks the UI and never loses local data when offline -- changes
  just wait for the next successful sync.

State (server clock of the last sync, local time of the last push) is kept
per account in sync_state.json, so switching accounts starts fresh.
"""

import asyncio
import json
import time
from typing import Callable, Optional

import httpx

SYNC_INTERVAL = 60
DEBOUNCE = 4


class SyncService:
    def __init__(self, state_path, base_url_fn: Callable[[], str], token_fn: Callable[[], Optional[str]],
                 email: str, history, items, memory, on_status: Optional[Callable[[str], None]] = None,
                 on_remote_change: Optional[Callable[[dict], None]] = None):
        self.state_path = state_path
        self.base_url_fn = base_url_fn
        self.token_fn = token_fn
        self.email = (email or "").lower()
        self.sources = {"chats": history, "items": items, "memories": memory}
        self.profile = None             # set after creation: services/profile.py ProfileStore
        self.on_status = on_status or (lambda s: None)
        self.on_remote_change = on_remote_change or (lambda counts: None)
        self._running = False
        self._kick = None
        self._busy = False
        self.last_ok: Optional[float] = None
        self.last_error: str = ""

    # -- state -------------------------------------------------------------
    def _load(self) -> dict:
        try:
            data = json.loads(self.state_path.read_text())
            return data.get(self.email, {})
        except Exception:
            return {}

    def _save(self, state: dict):
        try:
            data = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        except Exception:
            data = {}
        data[self.email] = state
        try:
            self.state_path.write_text(json.dumps(data))
        except Exception:
            pass

    # -- one round ---------------------------------------------------------
    async def sync_once(self) -> bool:
        token = self.token_fn()
        if not token or self._busy:
            return False
        self._busy = True
        try:
            state = self._load()
            pushed_at = time.time()
            last_push = float(state.get("last_push", 0))
            if self.profile is not None:
                self.sources["profile"] = self.profile
            push = {k: src.changes_since(last_push) for k, src in self.sources.items() if src is not None}
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.post(f"{self.base_url_fn().rstrip('/')}/sync",
                                         json={"since": state.get("since", 0), "push": push},
                                         headers={"Authorization": f"Bearer {token}"})
            if resp.status_code == 401:
                self.last_error = "Sign in again to sync"
                self.on_status(self.last_error)
                return False
            if resp.status_code == 404:
                self.last_error = "This server doesn't support sync yet"
                self.on_status(self.last_error)
                return False
            resp.raise_for_status()
            data = resp.json()
            counts = {}
            for kind, docs in (data.get("changes") or {}).items():
                src = self.sources.get(kind)
                if src is not None and docs:
                    counts[kind] = src.apply_remote(docs)
            # Anything changed locally while the request was in flight has
            # updated > pushed_at, so it still goes out next round.
            self._save({"since": data.get("now", 0), "last_push": pushed_at})
            self.last_ok, self.last_error = time.time(), ""
            self.on_status("Synced")
            if any(counts.values()):
                self.on_remote_change(counts)
            return True
        except Exception as exc:
            self.last_error = "Offline \u2014 will sync later"
            self.on_status(self.last_error)
            return False
        finally:
            self._busy = False

    # -- background loop ---------------------------------------------------
    def changed(self):
        """Call after a local change: syncs a few seconds later."""
        if self._kick is not None and not self._kick.is_set():
            self._kick.set()

    async def run(self):
        self._running = True
        self._kick = asyncio.Event()
        await self.sync_once()
        while self._running:
            try:
                await asyncio.wait_for(self._kick.wait(), timeout=SYNC_INTERVAL)
                await asyncio.sleep(DEBOUNCE)          # gather a burst of edits
            except asyncio.TimeoutError:
                pass
            self._kick.clear()
            if self._running:
                await self.sync_once()

    def stop(self):
        self._running = False
        if self._kick is not None:
            self._kick.set()
