"""
The one fix for the storage-location bug found in roughly a dozen places
across the real codebase (config.py, database.py, history.py, logger.py,
file_manager.py, media_engine.py, notes_tool.py, profile.py, utils.py,
shazam.py, and both abandoned core/paths.py + utils/paths.py attempts):
every one of them computed a path relative to __file__ or the current
working directory, or checked for PyInstaller markers Briefcase never
sets. None of that is reliably writable once the app is actually packaged.

Toga already solves this correctly: `app.paths` gives an OS-appropriate,
writable directory for each kind of data, on every platform Briefcase
targets. Everything in this rebuild that needs to persist something goes
through here instead of inventing its own path logic.
"""

import toga


def data_dir(app: toga.App):
    """Databases, session files, generated media -- anything the app owns
    and manages itself."""
    app.paths.data.mkdir(parents=True, exist_ok=True)
    return app.paths.data


def config_dir(app: toga.App):
    """User-editable settings."""
    app.paths.config.mkdir(parents=True, exist_ok=True)
    return app.paths.config


def cache_dir(app: toga.App):
    """Anything disposable -- safe to delete, rebuilt on demand."""
    app.paths.cache.mkdir(parents=True, exist_ok=True)
    return app.paths.cache


def logs_dir(app: toga.App):
    app.paths.logs.mkdir(parents=True, exist_ok=True)
    return app.paths.logs
