"""'What's new' after an update: the changelog sections newer than the version the person last saw.
The app ships resources/CHANGELOG.md (a copy of the project's CHANGELOG.md; a test keeps them equal)."""
import os
import re

HEADING = re.compile(r"^## (\d+(?:\.\d+)+)\b.*$", re.M)


def _key(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0"))


def sections(text: str) -> list:
    """[(version, [point, ...]), ...] newest first; each '- ' point joined into one paragraph."""
    out = []
    marks = list(HEADING.finditer(text))
    for i, m in enumerate(marks):
        body = text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)]
        points, cur = [], None
        for line in body.splitlines():
            if line.startswith("- "):
                cur = line[2:].strip(); points.append(cur)
            elif line.startswith(" ") and points and line.strip():
                points[-1] = points[-1] + " " + line.strip()
            elif line.strip() and not line.startswith(" "):
                cur = None                         # sub-headings like "New abilities:" are skipped
        if points:
            out.append((m.group(1), points))
    return out


def since(text: str, last_seen: str, current: str, limit: int = 3) -> list:
    """The sections newer than last_seen, up to the current version (newest first, at most `limit`)."""
    return [(v, p) for v, p in sections(text) if _key(last_seen) < _key(v) <= _key(current)][:limit]


def changelog_text() -> str:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "CHANGELOG.md")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""
