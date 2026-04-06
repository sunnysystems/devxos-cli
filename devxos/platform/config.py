"""DevXOS CLI config — stored in ~/.devxos/config.json."""

import json
import os

CONFIG_DIR = os.path.expanduser("~/.devxos")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def _ensure_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config() -> dict:
    """Load config from ~/.devxos/config.json. Returns empty dict if missing."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_config(config: dict) -> None:
    """Save config to ~/.devxos/config.json."""
    _ensure_dir()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def get_auth() -> tuple[str, str] | None:
    """Return (server_url, token) or None if not configured."""
    config = load_config()
    server = config.get("server_url")
    token = config.get("token")
    if server and token:
        return server, token
    return None
