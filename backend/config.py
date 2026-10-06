import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
def data_directory():
    if os.getenv("JARVIS_DATA_DIR"):
        return Path(os.environ["JARVIS_DATA_DIR"]).expanduser().resolve()
    if (ROOT / ".data/settings.json").exists():
        return ROOT / ".data"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "Jarvis"
    return Path.home() / "Library/Application Support/Jarvis"


DATA = data_directory()
DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
if os.name == "nt":
    # POSIX chmod cannot protect Windows secrets; restrict the NTFS ACL.
    sid = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True).strip().split(",")[-1].strip('"')
    subprocess.run(["icacls", str(DATA), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"], check=True, stdout=subprocess.DEVNULL)
else:
    os.chmod(DATA, 0o700)
FILE = DATA / "settings.json"
DEFAULTS = {"display_name": "", "setup_complete": False, "provider": "ollama", "model": "", "voice": "bm_george", "speed": 1.0, "openai_key": "", "google_client_id": "", "google_client_secret": "", "google_tokens": {}, "telegram_token": "", "telegram_chat_id": "", "telegram_gateway": False, "desktop_voice": False}
_lock = threading.RLock()


def load():
    with _lock:
        values = json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else {}
    return DEFAULTS | values | ({"openai_key": os.environ["OPENAI_API_KEY"]} if os.getenv("OPENAI_API_KEY") else {})


def save(changes):
    with _lock:
        config = load() | changes
        fd, name = tempfile.mkstemp(dir=FILE.parent, suffix=".tmp")
        tmp = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(config, f)
            tmp.replace(FILE)
        finally:
            tmp.unlink(missing_ok=True)
        return config
