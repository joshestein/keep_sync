from pathlib import Path

APP_DIR = Path.home() / "Library" / "Application Support" / "keep-sync"
QUEUE_DIR = APP_DIR / "queue"
CACHE_FILE = APP_DIR / "cache.json"
STATE_FILE = APP_DIR / "state.json"
LOG_FILE = Path.home() / "Library" / "Logs" / "keep-sync.log"
