"""The sync loop: apply ops, sync, write state and cache, remove op files."""

import faulthandler
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import requests
from gkeepapi import Keep
from gkeepapi.exception import APIException, LoginException, ResyncRequiredException
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from keep_sync.apply import apply_queue
from keep_sync.cache import Status, SyncError, read_cached_notes, serialize_notes, write_cache
from keep_sync.keychain import KeychainError
from keep_sync.queue import SYNC_NOW_FILE, remove_ops
from keep_sync.state import save_state

log = logging.getLogger(__name__)

POLL_SECONDS = 60
MAX_BACKOFF_SECONDS = 15 * 60
DEBOUNCE_SECONDS = 1
# gkeepapi and gpsoauth set no HTTP timeouts, and gkeepapi retries 429s forever.
# A round that runs this long is hung: exit and let launchd restart the service.
ROUND_TIMEOUT_SECONDS = 5 * 60


def classify(e: Exception) -> SyncError:
    if isinstance(e, (LoginException, KeychainError)) or (isinstance(e, APIException) and e.code == 401):
        kind = "auth"
    elif isinstance(e, requests.RequestException):
        kind = "network"
    else:
        kind = "other"
    return SyncError(kind, f"{type(e).__name__}: {e}")


def backoff_seconds(error: SyncError | None, failures: int) -> float:
    """Seconds until the next round. failures counts consecutive failed rounds, this one included."""
    if error is None:
        return POLL_SECONDS
    if error.kind == "auth":
        return MAX_BACKOFF_SECONDS
    return min(POLL_SECONDS * 2 ** (failures - 1), MAX_BACKOFF_SECONDS)


@dataclass
class Syncer:
    keep: Keep
    login: Callable[[Keep], None]
    queue_dir: Path
    cache_file: Path
    state_file: Path
    # True when the model is empty (no usable state) or Keep asked for a resync.
    # Ops are not applied until a full sync fills the model: see state.load_state.
    needs_full_sync: bool
    synced_at: datetime | None = None
    logged_in: bool = False

    def round(self) -> SyncError | None:
        attempt_at = datetime.now(UTC)
        applied: list[Path] = []
        error = None
        try:
            if not self.logged_in:
                self.login(self.keep)
                self.logged_in = True
            if self.needs_full_sync:
                self.keep.sync(resync=True)
                self.needs_full_sync = False
            applied = apply_queue(self.keep, self.queue_dir)
            self.keep.sync()
        except Exception as e:
            error = classify(e)
            log.warning("sync failed: %s", error.message, exc_info=error.kind == "other")
            if error.kind == "auth":
                # Log in again next round, so a token from a new `keep-sync setup` is picked up.
                self.logged_in = False
            if isinstance(e, ResyncRequiredException):
                self.needs_full_sync = True
        else:
            self.synced_at = attempt_at
            save_state(self.keep, self.state_file)

        # Until a full sync fills the model, it is empty or partial (resync clears it first).
        # Keep the notes from the last cache, so a failed sync never empties the list.
        notes = read_cached_notes(self.cache_file) if self.needs_full_sync else serialize_notes(self.keep)
        write_cache(self.cache_file, notes, Status(self.synced_at, attempt_at, error))
        if error is None:
            remove_ops(applied)
        return error


@dataclass(frozen=True)
class Wake:
    """op: a new op file. sync_now: the user asked for a round now. sync_now also sets op."""

    op: threading.Event = field(default_factory=threading.Event)
    sync_now: threading.Event = field(default_factory=threading.Event)


class _QueueHandler(FileSystemEventHandler):
    """Wake the loop when the extension renames a new op file into the queue or touches the sync-now file."""

    def __init__(self, queue_dir: Path, wake: Wake) -> None:
        self.queue_dir = queue_dir
        self.wake = wake

    def on_any_event(self, event: FileSystemEvent) -> None:
        path = Path(str(event.dest_path or event.src_path))
        if path.parent != self.queue_dir:
            return
        if path.name == SYNC_NOW_FILE:
            # "modified": the file was already there, for example while the service was stopped.
            if event.event_type in ("created", "modified", "moved"):
                self.wake.sync_now.set()
                self.wake.op.set()
        elif event.event_type in ("created", "moved") and path.suffix == ".json" and not path.name.startswith("."):
            self.wake.op.set()


def watch_queue(queue_dir: Path, wake: threading.Event) -> BaseObserver:
    observer = Observer()
    observer.schedule(_QueueHandler(queue_dir, wake), str(queue_dir), recursive=False)
    observer.start()
    return observer


def run_forever(syncer: Syncer, wake: threading.Event) -> None:
    failures = 0
    while True:
        wake.clear()
        # On a hang, faulthandler writes all stacks to stderr (the launchd log) and exits.
        faulthandler.dump_traceback_later(ROUND_TIMEOUT_SECONDS, exit=True)
        error = syncer.round()
        faulthandler.cancel_dump_traceback_later()

        failures = 0 if error is None else failures + 1
        delay = backoff_seconds(error, failures)
        if error is not None:
            # A new op does not cut a backoff short.
            time.sleep(delay)
        elif wake.wait(delay):
            time.sleep(DEBOUNCE_SECONDS)
