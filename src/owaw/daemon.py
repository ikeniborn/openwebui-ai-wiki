"""inotify watcher + debounce. The Debouncer is timer-free for tests (flush_now)."""
from __future__ import annotations

import threading
from collections.abc import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class Debouncer:
    """Collect a unique set of items; fire on_flush after delay_ms of quiet, or flush_now()."""

    def __init__(self, delay_ms: int, on_flush: Callable[[set], None]):
        self._delay = delay_ms / 1000.0
        self._on_flush = on_flush
        self._pending: set = set()
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def add(self, item) -> None:
        with self._lock:
            self._pending.add(item)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self.flush_now)
            self._timer.daemon = True
            self._timer.start()

    def flush_now(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            items, self._pending = self._pending, set()
        if items:
            self._on_flush(items)


class _Handler(FileSystemEventHandler):
    def __init__(self, debouncer: Debouncer):
        self._deb = debouncer

    def on_any_event(self, event):
        if not event.is_directory:
            self._deb.add(event.src_path)


def watch(domain, debounce_ms: int, on_change: Callable[[set], None]) -> Observer:
    """Start observing a domain's source paths. Returns a started Observer (caller joins/stops)."""
    debouncer = Debouncer(debounce_ms, on_change)
    observer = Observer()
    handler = _Handler(debouncer)
    for root in domain.source_paths:
        observer.schedule(handler, root, recursive=True)
    observer.start()
    return observer


def watch_paths(paths: list[str], debounce_ms: int, on_change: Callable[[set], None]) -> Observer:
    """Observe arbitrary directories (recursive). Returns a started Observer (caller stops/joins)."""
    debouncer = Debouncer(debounce_ms, on_change)
    observer = Observer()
    handler = _Handler(debouncer)
    for root in paths:
        observer.schedule(handler, root, recursive=True)
    observer.start()
    return observer
