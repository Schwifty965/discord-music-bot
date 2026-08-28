import asyncio
from typing import Optional

import yt_dlp


YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}


async def search_youtube(query: str) -> Optional[dict]:
    """
    Search YouTube and return the first matching result.
    """

    loop = asyncio.get_running_loop()

    def _search():
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            result = ydl.extract_info(
                f"ytsearch1:{query}",
                download=False,
            )

            if not result:
                return None

            entries = result.get("entries")

            if not entries:
                return None

            info = entries[0]

            return {
                "title": info.get("title", "Unknown"),
                "artist": info.get("artist") or info.get("uploader", "Unknown"),
                "url": info.get("url"),
                "webpage_url": info.get("webpage_url"),
                "duration": info.get("duration"),
                "thumbnail": info.get("thumbnail"),
            }

    return await loop.run_in_executor(None, _search)


async def get_youtube(url: str) -> Optional[dict]:
    """
    Get information from a YouTube URL.
    """

    loop = asyncio.get_running_loop()

    def _extract():
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            info = ydl.extract_info(
                url,
                download=False,
            )

            if not info:
                return None

            return {
                "title": info.get("title", "Unknown"),
                "artist": info.get("artist") or info.get("uploader", "Unknown"),
                "url": info.get("url"),
                "webpage_url": info.get("webpage_url", url),
                "duration": info.get("duration"),
                "thumbnail": info.get("thumbnail"),
            }

    return await loop.run_in_executor(None, _extract)