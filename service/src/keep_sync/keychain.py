"""Credentials in the login Keychain, through /usr/bin/security (ADR 0003)."""

import re
import subprocess

SECURITY = "/usr/bin/security"
SERVICE = "keep-sync"
NOT_FOUND = 44

_ACCOUNT_RE = re.compile(r'^\s*"acct"<blob>="(.*)"$', re.MULTILINE)


class KeychainError(Exception):
    pass


def _security(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([SECURITY, *args], input=stdin, capture_output=True, text=True, check=False)


def save_credentials(email: str, token: str) -> None:
    """Store the item and remove any old one. The token goes through stdin (`security -i`), never argv, so `ps` cannot see it."""
    for value in (email, token):
        if any(c in value for c in '"\\\n'):
            raise KeychainError("email and token must not contain quotes, backslashes, or newlines")
    # `add -U` matches on service and account, so a new email would add a second item,
    # and read_credentials (by service only) could return the old one.
    delete_credentials()
    command = f'add-generic-password -U -s {SERVICE} -a "{email}" -w "{token}" -T {SECURITY}\n'
    result = _security("-i", stdin=command)
    if result.returncode != 0 or result.stderr.strip():
        raise KeychainError(f"cannot save credentials: {result.stderr.strip()}")


def read_credentials() -> tuple[str, str]:
    """Return (email, master token)."""
    attrs = _security("find-generic-password", "-s", SERVICE)
    if attrs.returncode == NOT_FOUND:
        raise KeychainError("no credentials: run `keep-sync setup`")
    match = _ACCOUNT_RE.search(attrs.stdout)
    if attrs.returncode != 0 or match is None:
        raise KeychainError(f"cannot read credentials: {attrs.stderr.strip()}")
    token = _security("find-generic-password", "-s", SERVICE, "-w")
    if token.returncode != 0:
        raise KeychainError(f"cannot read credentials: {token.stderr.strip()}")
    return match.group(1), token.stdout.strip()


def delete_credentials() -> bool:
    """Return False if there was no item."""
    result = _security("delete-generic-password", "-s", SERVICE)
    if result.returncode not in (0, NOT_FOUND):
        raise KeychainError(f"cannot delete credentials: {result.stderr.strip()}")
    return result.returncode == 0
