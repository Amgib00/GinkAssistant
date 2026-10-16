"""
Pack(), but drops any kwarg whose value is None instead of passing it
through. Newer Toga/Travertino versions (confirmed against the user's
installed version) reject an explicit None for a style property with
ValueError -- "Python `None` cannot be used as a style property value" --
where older versions silently treated it as "leave this unset". The
natural way to write a conditional style ("tinted if X, plain
otherwise") is `background_color=COLOR if x else None`; this makes that
pattern keep working instead of auditing every call site for it.
"""

from toga.style import Pack


def pack(**kwargs) -> Pack:
    return Pack(**{k: v for k, v in kwargs.items() if v is not None})