"""Runs against the real login Keychain, with a throwaway service name."""

import sys

import pytest

from keep_sync import keychain
from keep_sync.keychain import KeychainError, delete_credentials, read_credentials, save_credentials

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain")


@pytest.fixture(autouse=True)
def test_service(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(keychain, "SERVICE", "keep-sync-test")
    delete_credentials()
    yield
    delete_credentials()


def test_round_trip() -> None:
    save_credentials("me@example.com", "aas_et/AB+c=d")
    assert read_credentials() == ("me@example.com", "aas_et/AB+c=d")

    save_credentials("me@example.com", "aas_et/new")
    assert read_credentials() == ("me@example.com", "aas_et/new")


def test_new_email_replaces_the_old_item() -> None:
    save_credentials("old@example.com", "aas_et/old")
    save_credentials("new@example.com", "aas_et/new")
    assert read_credentials() == ("new@example.com", "aas_et/new")
    assert delete_credentials()
    assert not delete_credentials()


def test_missing() -> None:
    with pytest.raises(KeychainError, match="keep-sync setup"):
        read_credentials()
    assert not delete_credentials()


def test_rejects_values_that_break_the_command() -> None:
    with pytest.raises(KeychainError):
        save_credentials('a"b@example.com', "t")
