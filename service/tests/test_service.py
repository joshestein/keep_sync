import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from gkeepapi import Keep
from gkeepapi.exception import APIException, LoginException, ResyncRequiredException

from keep_sync.cache import SyncError
from keep_sync.keychain import KeychainError
from keep_sync.queue import list_op_files
from keep_sync.service import MAX_BACKOFF_SECONDS, POLL_SECONDS, Syncer, _QueueHandler, backoff_seconds, classify

from .conftest import NOTE_ID, WriteOp


class FakeServer:
    """Stands in for Keep.sync. Records each call and raises the queued errors in order."""

    def __init__(self) -> None:
        self.calls: list[bool] = []
        self.errors: list[Exception | None] = []

    def sync(self, resync: bool = False) -> None:
        self.calls.append(resync)
        if self.errors and (error := self.errors.pop(0)) is not None:
            raise error


@pytest.fixture
def server(keep: Keep, monkeypatch: pytest.MonkeyPatch) -> FakeServer:
    fake = FakeServer()
    monkeypatch.setattr(keep, "sync", fake.sync)
    return fake


@pytest.fixture
def logins() -> list[Keep]:
    return []


@pytest.fixture
def make_syncer(keep: Keep, queue_dir: Path, tmp_path: Path, logins: list[Keep]):
    def make(needs_full_sync: bool = False) -> Syncer:
        return Syncer(
            keep=keep,
            login=logins.append,
            queue_dir=queue_dir,
            cache_file=tmp_path / "cache.json",
            state_file=tmp_path / "state.json",
            needs_full_sync=needs_full_sync,
        )

    return make


def read_cache(syncer: Syncer) -> dict:
    return json.loads(syncer.cache_file.read_text())


def test_success_writes_state_and_cache_then_removes_ops(
    make_syncer, server: FakeServer, queue_dir: Path, write_op: WriteOp
) -> None:
    syncer = make_syncer()
    write_op("create", text="milk")

    assert syncer.round() is None

    assert server.calls == [False]
    assert syncer.state_file.exists()
    cache = read_cache(syncer)
    assert cache["error"] is None
    assert cache["synced_at"] == cache["last_attempt_at"]
    assert [n["id"] for n in cache["notes"]] == [NOTE_ID]
    assert list_op_files(queue_dir) == []


def test_failed_sync_keeps_ops_and_reports_error(
    make_syncer, server: FakeServer, queue_dir: Path, write_op: WriteOp
) -> None:
    syncer = make_syncer()
    path = write_op("create", text="milk")
    server.errors = [requests.ConnectionError("offline")]

    error = syncer.round()

    assert error is not None and error.kind == "network"
    assert list_op_files(queue_dir) == [path]
    assert not syncer.state_file.exists()
    cache = read_cache(syncer)
    assert cache["error"]["kind"] == "network"
    assert cache["synced_at"] is None
    # The cache comes from the model, which already has the op.
    assert [n["id"] for n in cache["notes"]] == [NOTE_ID]


def test_retry_after_failure_applies_the_op_once(
    make_syncer, keep: Keep, server: FakeServer, queue_dir: Path, write_op: WriteOp
) -> None:
    syncer = make_syncer()
    write_op("create", text="milk")
    server.errors = [requests.ConnectionError("offline")]
    syncer.round()

    assert syncer.round() is None
    assert len(keep.all()) == 1
    assert list_op_files(queue_dir) == []


def test_empty_model_syncs_fully_before_applying_ops(
    make_syncer, server: FakeServer, queue_dir: Path, write_op: WriteOp
) -> None:
    syncer = make_syncer(needs_full_sync=True)
    path = write_op("delete")
    server.errors = [requests.ConnectionError("offline")]

    syncer.round()

    assert server.calls == [True]
    assert list_op_files(queue_dir) == [path]
    assert syncer.needs_full_sync

    assert syncer.round() is None
    assert server.calls == [True, True, False]
    assert not syncer.needs_full_sync


def test_resync_required_does_a_full_sync_next_round(
    make_syncer, keep: Keep, server: FakeServer, write_op: WriteOp
) -> None:
    syncer = make_syncer()
    write_op("create", text="milk")
    server.errors = [ResyncRequiredException("Full resync required")]
    syncer.round()
    assert syncer.needs_full_sync

    syncer.round()

    assert server.calls == [False, True, False]
    assert keep.get(NOTE_ID) is not None


def test_auth_error_logs_in_again(make_syncer, server: FakeServer, logins: list[Keep]) -> None:
    syncer = make_syncer()
    server.errors = [LoginException("BadAuthentication")]
    assert syncer.round() == SyncError("auth", "LoginException: BadAuthentication")
    syncer.round()
    assert len(logins) == 2


def test_login_failure_applies_nothing(make_syncer, server: FakeServer, queue_dir: Path, write_op: WriteOp) -> None:
    def fail(_: Keep) -> None:
        raise KeychainError("no credentials")

    syncer = make_syncer()
    syncer.login = fail
    path = write_op("create", text="milk")

    assert syncer.round() == SyncError("auth", "KeychainError: no credentials")
    assert server.calls == []
    assert list_op_files(queue_dir) == [path]
    assert read_cache(syncer)["notes"] == []


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (LoginException("x"), "auth"),
        (KeychainError("x"), "auth"),
        (APIException(401, "x"), "auth"),
        (requests.Timeout("x"), "network"),
        (requests.ConnectionError("x"), "network"),
        (APIException(500, "x"), "other"),
        (ValueError("x"), "other"),
    ],
)
def test_classify(error: Exception, kind: str) -> None:
    assert classify(error).kind == kind


def test_backoff() -> None:
    network = SyncError("network", "")
    assert backoff_seconds(None, 0) == POLL_SECONDS
    assert [backoff_seconds(network, n) for n in (1, 2, 3, 4, 5)] == [60, 120, 240, 480, MAX_BACKOFF_SECONDS]
    assert backoff_seconds(SyncError("auth", ""), 1) == MAX_BACKOFF_SECONDS


@pytest.mark.parametrize(
    ("event_type", "src", "dest", "wakes"),
    [
        ("moved", ".1-a.json.tmp", "1-a.json", True),
        ("created", "1-a.json", "", True),
        ("created", ".1-a.json.tmp", "", False),
        ("deleted", "1-a.json", "", False),
        ("moved", "1-a.json", "failed/1-a.json", False),
    ],
)
def test_queue_handler_wakes_only_on_new_ops(
    queue_dir: Path, event_type: str, src: str, dest: str, wakes: bool
) -> None:
    wake = threading.Event()
    event = SimpleNamespace(
        event_type=event_type, src_path=str(queue_dir / src), dest_path=str(queue_dir / dest) if dest else ""
    )
    _QueueHandler(queue_dir, wake).on_any_event(event)  # pyright: ignore[reportArgumentType]
    assert wake.is_set() == wakes
