"""
Async port of voice_app.py's WorldNewsEngineWorker -- fetches a handful of
world headlines from a couple of RSS feeds and returns a short summary plus
the raw headline/link list. Pure XML-over-HTTP, no platform-specific
dependencies, so this one should work the same on every Briefcase target.
"""

import xml.etree.ElementTree as ET
from typing import List, Tuple

import httpx

NEWS_SOURCES = [
    "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
]


async def fetch_world_news() -> Tuple[str, List[dict]]:
    """Returns (summary_text, headlines). Raises RuntimeError if every
    source fails, same as the original emitting error_occurred."""
    headlines: List[dict] = []
    failures: List[str] = []

    async with httpx.AsyncClient(timeout=5, headers={"User-Agent": "Mozilla/5.0"}) as client:
        for feed_url in NEWS_SOURCES:
            if len(headlines) >= 5:
                break
            try:
                resp = await client.get(feed_url)
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:3]:
                    title_el = item.find("title")
                    link_el = item.find("link")
                    title = title_el.text if title_el is not None and title_el.text else "Untitled"
                    link = link_el.text if link_el is not None and link_el.text else ""
                    headlines.append({"title": title, "link": link})
            except Exception as e:
                failures.append(f"{feed_url}: {e}")
                continue

    if not headlines:
        detail = "; ".join(failures) if failures else "no sources returned results."
        raise RuntimeError(f"Failed to fetch live global news: {detail}")

    summary_text = "Here are top breaking stories from around the world:\n"
    for idx, h in enumerate(headlines[:5], 1):
        summary_text += f"{idx}. {h['title']}\n"

    return summary_text, headlines[:5]
