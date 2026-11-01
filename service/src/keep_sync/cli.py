import argparse
import getpass
import json
import logging
import shutil
import sys
import uuid
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import gpsoauth
from gkeepapi import Keep

from keep_sync import launchd
from keep_sync.keychain import delete_credentials, read_credentials, save_credentials
from keep_sync.paths import APP_DIR, CACHE_FILE, LAUNCHD_LOG_FILE, LOG_FILE, QUEUE_DIR, STATE_FILE
from keep_sync.queue import list_op_files
from keep_sync.service import Syncer, Wake, run_forever, watch_queue
from keep_sync.state import load_state

log = logging.getLogger(__name__)


def _device_id() -> str:
    # The same device id that gkeepapi uses by default.
    return f"{uuid.getnode():x}"


def _login(keep: Keep) -> None:
    email, token = read_credentials()
    keep.authenticate(email, token, sync=False, device_id=_device_id())


def setup(_: argparse.Namespace) -> None:
    email = input("Google account email: ").strip()
    print("Paste the oauth_token cookie from accounts.google.com/EmbeddedSetup (see README). Input is hidden.")
    oauth_token = getpass.getpass("oauth_token: ").strip()

    result = gpsoauth.exchange_token(email, oauth_token, _device_id())
    token = result.get("Token")
    if not token:
        # Print only the error: the rest of the response holds session tokens.
        sys.exit(f"Token exchange failed: {result.get('Error', 'no token in response')}. Get a new cookie and retry.")

    Keep().authenticate(email, token, sync=False, device_id=_device_id())
    save_credentials(email, token)
    print("Master token validated and saved to Keychain.")

    launchd.install([str(Path(sys.prefix) / "bin" / "keep-sync"), "run"], LAUNCHD_LOG_FILE)
    print(f"Service installed ({launchd.PLIST_FILE}). Log: {LOG_FILE}")


def run(_: argparse.Namespace) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    keep = Keep()
    restored = load_state(keep, STATE_FILE)
    syncer = Syncer(
        keep=keep,
        login=_login,
        queue_dir=QUEUE_DIR,
        cache_file=CACHE_FILE,
        state_file=STATE_FILE,
        needs_full_sync=not restored,
        # state.json is written only after a successful sync.
        synced_at=datetime.fromtimestamp(STATE_FILE.stat().st_mtime, UTC) if restored else None,
    )
    wake = Wake()
    watch_queue(QUEUE_DIR, wake)
    log.info("started (state %s)", "restored" if restored else "missing: full sync first")
    run_forever(syncer, wake)


def status(_: argparse.Namespace) -> None:
    print(f"agent:    {'loaded' if launchd.is_loaded() else 'not loaded'}")
    try:
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("cache:    none")
    else:
        error = cache["error"]
        print(f"synced:   {cache['synced_at'] or 'never'}")
        print(f"attempt:  {cache['last_attempt_at']}")
        print(f"error:    {f'{error['kind']}: {error['message']}' if error else 'none'}")
        print(f"notes:    {len(cache['notes'])}")
    print(f"queued:   {len(list_op_files(QUEUE_DIR)) if QUEUE_DIR.exists() else 0}")
    failed = QUEUE_DIR / "failed"
    print(f"failed:   {len(list_op_files(failed)) if failed.exists() else 0}")


def uninstall(args: argparse.Namespace) -> None:
    launchd.uninstall()
    print("Service removed.")
    if not args.purge:
        return
    queued = len(list_op_files(QUEUE_DIR)) if QUEUE_DIR.exists() else 0
    if queued and input(f"{queued} ops are not synced and will be lost. Type 'yes' to continue: ") != "yes":
        sys.exit("Stopped. The Keychain item and data are kept.")
    delete_credentials()
    shutil.rmtree(APP_DIR, ignore_errors=True)
    print("Keychain item and data removed.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="keep-sync", description="Sync Google Keep to local files for Raycast.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("setup", help="get a master token, save it to Keychain, install the service").set_defaults(fn=setup)
    commands.add_parser("run", help="run the sync loop (launchd runs this)").set_defaults(fn=run)
    commands.add_parser("status", help="show sync status").set_defaults(fn=status)
    remove = commands.add_parser("uninstall", help="remove the service")
    remove.add_argument("--purge", action="store_true", help="also delete the Keychain item and all local data")
    remove.set_defaults(fn=uninstall)
    args = parser.parse_args()
    args.fn(args)
