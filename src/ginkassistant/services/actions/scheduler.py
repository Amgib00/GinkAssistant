"""Background loop that fires due reminders / alarms / timers inside Gink.

Items already handed to the OS (Android Clock, macOS Reminders, Windows Task
Scheduler, systemd) are only marked as fired here — the OS rings them, so they
aren't rung twice. Everything else gets a system notification (desktop) and
the on_due callback, which the UI uses to show a dialog / chat line / speak.
"""
import asyncio
from datetime import datetime
from typing import Awaitable, Callable, Optional

from .notify import notify
from .task_store import Item, TaskStore


class ReminderScheduler:
    def __init__(self, store: TaskStore, on_due: Optional[Callable[[Item], Awaitable[None]]] = None,
                 interval: float = 5.0):
        self.notifications_enabled = lambda: True     # Settings -> Notifications
        self.store = store
        self.on_due = on_due
        self.interval = interval
        self._task = None
        self._running = False

    def start(self, loop=None):
        if self._running:
            return
        self._running = True
        loop = loop or asyncio.get_event_loop()
        self._task = loop.create_task(self._run())

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    async def tick(self, now: Optional[datetime] = None):
        for item in self.store.due_items(now or datetime.now()):
            self.store.mark_fired(item.id)
            if item.kind == "task" and item.parent_id is None and not item.due:
                continue
            if not item.system_scheduled:
                if self.notifications_enabled():
                    notify(item.title, _body(item), loud=item.kind in ("alarm", "timer"))
            if self.on_due:
                try:
                    await self.on_due(item)
                except Exception as e:
                    print(f"[Gink scheduler] on_due failed: {e}")

    async def _run(self):
        while self._running:
            try:
                await self.tick()
            except Exception as e:
                print(f"[Gink scheduler] {e}")
            await asyncio.sleep(self.interval)


def _body(item: Item) -> str:
    return {"alarm": "⏰ Alarm", "timer": "⏲ Time's up", "reminder": "🔔 Reminder",
            "event": "📅 Starting now", "task": "✅ Task due"}.get(item.kind, "Gink")
