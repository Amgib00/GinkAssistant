"""Gink task & device-action system.

Everything Gink can *do* (not just say) lives here:
alarms, timers, reminders, tasks with AI-planned steps, opening apps,
messages, calls, calendar events and live web lookups.

Public entry points:
    TaskStore        - on-device SQLite storage for tasks/reminders/alarms
    DeviceActions    - per-platform implementations (Android/iOS/macOS/Windows/Linux)
    ToolRunner       - executes tool calls and records results in the store
    TaskAgent        - Groq tool-calling agent that analyses a request and acts
    ReminderScheduler- background loop that rings due reminders/alarms
"""
from .platform_info import current_platform, is_desktop, is_mobile
from .task_store import TaskStore, Item
from .device import DeviceActions, ActionResult
from .tools import ToolRunner, TOOL_SPECS
from .agent import TaskAgent, AgentReply, looks_like_action
from .scheduler import ReminderScheduler

__all__ = [
    "current_platform", "is_desktop", "is_mobile",
    "TaskStore", "Item", "DeviceActions", "ActionResult",
    "ToolRunner", "TOOL_SPECS", "TaskAgent", "AgentReply",
    "looks_like_action", "ReminderScheduler",
]
