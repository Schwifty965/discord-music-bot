from dataclasses import dataclass
from typing import Optional


@dataclass
class Song:
    title: str
    artist: str
    url: str
    webpage_url: str
    duration: Optional[int] = None
    thumbnail: Optional[str] = None


class MusicQueue:
    def __init__(self):
        self._queue: list[Song] = []

    def add(self, song: Song):
        self._queue.append(song)

    def get_next(self) -> Optional[Song]:
        if not self._queue:
            return None

        return self._queue.pop(0)

    def clear(self):
        self._queue.clear()

    def skip(self) -> Optional[Song]:
        return self.get_next()

    def peek(self) -> Optional[Song]:
        if not self._queue:
            return None

        return self._queue[0]

    def all(self) -> list[Song]:
        return list(self._queue)

    def __len__(self):
        return len(self._queue)

    def is_empty(self):
        return len(self._queue) == 0