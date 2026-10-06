"""Jarvis's cross-platform installer and lifecycle CLI (stdlib-only bootstrap)."""
import argparse
import contextlib
import hashlib
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import assets
from scripts.downloads import download, safe_extract

RUNTIME = ROOT / ".runtime"
CACHE = ROOT / ".cache"
STATE = RUNTIME / "installation.json"
URL = "http://127.0.0.1:8000"
WIN = os.name == "nt"
PY = ROOT / ".venv" / ("Scripts/python.exe" if WIN else "bin/python")


def run(args, **kwargs):
    print("Running " + Path(str(args[0])).name + " " + " ".join(map(str, args[1:3])), flush=True)
    return subprocess.run(list(map(str, args)), cwd=ROOT, check=True, **kwargs)


def read_state():
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def write_state(values):
    RUNTIME.mkdir(exist_ok=True)
    current = read_state() | values
    temp = STATE.with_suffix(".tmp")
    temp.write_text(json.dumps(current, indent=2))
    temp.replace(STATE)


@contextlib.contextmanager
def installation_lock():
    RUNTIME.mkdir(exist_ok=True)
    with (RUNTIME / "setup.lock").open("a+b") as stream:
        stream.seek(0)
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        try:
            if WIN:
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError("Another Jarvis setup is running. Wait for it to finish.") from None
        try:
            yield
        finally:
            if WIN:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def platform_key(system=None, machine=None):
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    architecture = {"arm64": "arm64", "aarch64": "arm64", "amd64": "x64", "x86_64": "x64"}.get(machine)
    key = f"{system}-{architecture}"
    if key not in assets.NODE:
        raise RuntimeError(f"Unsupported platform: {system} {machine}. Use macOS 14+ (Intel/Apple Silicon) or Windows 10 22H2+/11 x64.")
    return key


def preflight():
    key = platform_key()
    if key.startswith("darwin") and int(platform.mac_ver()[0].split(".")[0]) < 14:
        raise RuntimeError("macOS 14 or later is required.")
    if WIN and sys.getwindowsversion().build < 19045:
        raise RuntimeError("Windows 10 22H2 or Windows 11 is required.")
    free = shutil.disk_usage(ROOT).free / 2**30
    ram = memory_gb()
    print(f"Platform: {key}. RAM: {ram:.1f} GB. Available disk: {free:.1f} GB. Recommended RAM: 8 GB or more.")
    if ram and ram < 4:
        raise RuntimeError("This machine has less than 4 GB RAM. Use a machine with at least 4 GB (8 GB recommended) for the local voice/model stack.")
    # Repeated launches need less disk than a clean installation.
    minimum = .5 if PY.exists() and (ROOT / "dist/index.html").exists() else 6
    if free < minimum:
        raise RuntimeError(f"Free at least {minimum:g} GB before continuing (8 GB recommended for a fresh installation).")
    return key


def memory_gb():
    if WIN:
        import ctypes
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), *[(name, ctypes.c_ulonglong) for name in ("total_phys", "avail_phys", "total_page", "avail_page", "total_virtual", "avail_virtual", "avail_extended")]]
        info = MemoryStatus()
        info.length = ctypes.sizeof(info)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
            raise RuntimeError("Windows could not report memory availability. Run doctor and check system health.")
        return info.total_phys / 2**30
    return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)) / 2**30


def request(url, body=None, timeout=3):
    data = None if body is None else json.dumps(body).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}), timeout=timeout) as response:
        return json.load(response)


def health():
    try:
        data = request(URL + "/api/health")
        return data if data.get("application") == "jarvis-local" else None
    except (OSError, ValueError):
        return None


def occupied(port):
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def node_runtime(key, force=False):
    if not force:
        existing = shutil.which("node")
        if existing:
            try:
                version = subprocess.check_output([existing, "--version"], text=True).strip()
                if int(version.lstrip("v").split(".")[0]) in (22, 24):
                    node = Path(existing).resolve()
                    candidates = [node.parent / "node_modules/npm/bin/npm-cli.js", node.parent.parent / "lib/node_modules/npm/bin/npm-cli.js"]
                    npm = next((p for p in candidates if p.exists()), None)
                    if npm:
                        return node, npm
            except (OSError, ValueError, subprocess.CalledProcessError):
                pass
    suffix, checksum = assets.NODE[key]
    folder = RUNTIME / ("node-" + assets.NODE_VERSION + "-" + key)
    filename = "node-v" + assets.NODE_VERSION + "-" + suffix
    base = folder / filename.removesuffix(".tar.gz").removesuffix(".zip")
    node = base / ("node.exe" if WIN else "bin/node")
    npm = base / ("node_modules/npm/bin/npm-cli.js" if WIN else "lib/node_modules/npm/bin/npm-cli.js")
    if force or not node.exists() or not npm.exists():
        artifact = download("https://nodejs.org/dist/v" + assets.NODE_VERSION + "/" + filename, CACHE / "downloads" / filename, checksum)
        if folder.exists():
            shutil.rmtree(folder)
        safe_extract(artifact, folder)
    return node, npm


def ollama_executable(key, force=False):
    if not force and shutil.which("ollama"):
        return Path(shutil.which("ollama")).resolve()
    filename, checksum = assets.OLLAMA[key]
    folder = RUNTIME / ("ollama-" + assets.OLLAMA_VERSION)
    candidates = list(folder.rglob("ollama.exe" if WIN else "ollama")) if folder.exists() else []
    if force or not candidates:
        artifact = download("https://github.com/ollama/ollama/releases/download/v" + assets.OLLAMA_VERSION + "/" + filename, CACHE / "downloads" / filename, checksum)
        if folder.exists():
            shutil.rmtree(folder)
        safe_extract(artifact, folder)
        candidates = list(folder.rglob("ollama.exe" if WIN else "ollama"))
    executable = next((p for p in candidates if p.is_file()), None)
    if not executable:
        raise RuntimeError("Ollama archive did not contain the expected executable. Run repair.")
    if not WIN:
        executable.chmod(executable.stat().st_mode | 0o700)
    return executable


def spawn(args, logfile, env=None):
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with logfile.open("ab") as log:
        kwargs = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if WIN else {"start_new_session": True}
        return subprocess.Popen(list(map(str, args)), cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, **kwargs)


def ensure_ollama(key, model, force=False):
    try:
        request("http://127.0.0.1:11434/api/tags")
    except (OSError, ValueError):
        if occupied(11434):
            raise RuntimeError("Port 11434 is occupied by a service that does not respond as Ollama.")
        exe = ollama_executable(key, force)
        from backend.config import DATA
        env = os.environ | {"OLLAMA_HOST": "127.0.0.1:11434"}
        if exe.is_relative_to(RUNTIME):
            env["OLLAMA_MODELS"] = str(DATA / "ollama-models")
        child = spawn([exe, "serve"], DATA / "logs/ollama.log", env)
        write_state({"ollama": {"pid": child.pid, "executable": str(exe)}})
        for _ in range(90):
            if child.poll() is not None:
                raise RuntimeError("Ollama exited. See the Ollama log path in doctor; on Windows install Microsoft's x64 Visual C++ runtime if DLLs are missing.")
            try:
                request("http://127.0.0.1:11434/api/tags")
                break
            except (OSError, ValueError):
                time.sleep(1)
        else:
            raise RuntimeError("Ollama did not become ready within 90 seconds. Run doctor.")
    tags = request("http://127.0.0.1:11434/api/tags")
    from backend.config import load, save
    config = load()
    names = [m["name"] for m in tags.get("models", []) if not any(s in m["name"].lower() for s in ("embed", "nomic"))]
    wanted = model or (config["model"] if config["provider"] == "ollama" else "") or (names[0] if names else assets.STARTER_MODEL)
    if config["provider"] == "openai" and not model:
        return
    if wanted not in names:
        print(f"Installing starter/selected LLM: {wanted}. Ollama verifies model layer digests. See THIRD_PARTY.md for licenses.", flush=True)
        req = urllib.request.Request("http://127.0.0.1:11434/api/pull", data=json.dumps({"model": wanted, "stream": True}).encode(), headers={"Content-Type": "application/json"})
        last = time.monotonic()
        with urllib.request.urlopen(req, timeout=600) as response:
            for line in response:
                item = json.loads(line)
                if item.get("error"):
                    raise RuntimeError("Ollama model download failed. Check model name, connection, and free disk, then retry.")
                if time.monotonic() - last > 2 or item.get("status") == "success":
                    print(item.get("status", "Downloading") + (f" {100 * item.get('completed', 0) / item['total']:.0f}%" if item.get("total") else ""), flush=True)
                    last = time.monotonic()
        names = [m["name"] for m in request("http://127.0.0.1:11434/api/tags").get("models", [])]
        if wanted not in names:
            raise RuntimeError("Ollama did not report the downloaded model. Run doctor.")
    if model or not config["model"]:
        save({"provider": "ollama", "model": wanted})


def setup(args):
    key = preflight()
    if WIN:
        ensure_windows_runtime()
    uv = os.environ.get("JARVIS_UV") or str(RUNTIME / "uv" / ("uv.exe" if WIN else "uv"))
    if not Path(uv).exists():
        uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("Run Start Jarvis.command / Start Jarvis.cmd to install the bootstrap runtime.")
    env = os.environ | {"UV_CACHE_DIR": str(CACHE / "uv"), "UV_PYTHON_INSTALL_DIR": str(RUNTIME / "python")}
    force = args.command == "repair"
    lock_hash = hashlib.sha256((ROOT / "uv.lock").read_bytes() + (ROOT / "pyproject.toml").read_bytes()).hexdigest()
    state = read_state()
    if force or not PY.exists() or state.get("python_lock") != lock_hash:
        run([uv, "sync", "--frozen", "--python", assets.PYTHON_VERSION, "--reinstall" if force else "--no-progress"], env=env)
        write_state({"python_lock": lock_hash})
    node, npm = node_runtime(key, force or args.portable)
    npm_env = os.environ | {"PATH": str(node.parent) + os.pathsep + os.environ.get("PATH", ""), "npm_config_cache": str(CACHE / "npm")}
    js_hash = hashlib.sha256((ROOT / "package-lock.json").read_bytes()).hexdigest()
    if force or not (ROOT / "node_modules/.package-lock.json").exists() or state.get("node_lock") != js_hash:
        run([node, npm, "ci", "--no-audit", "--no-fund"], env=npm_env)
        write_state({"node_lock": js_hash})
    source = [ROOT / "package-lock.json", ROOT / "index.html", ROOT / "vite.config.ts", ROOT / "tsconfig.json", *sorted((ROOT / "src").rglob("*"))]
    build_hash = hashlib.sha256(b"".join(p.read_bytes() for p in source if p.is_file())).hexdigest()
    if force or not (ROOT / "dist/index.html").exists() or state.get("build") != build_hash:
        run([node, npm, "run", "build"], env=npm_env)
        write_state({"build": build_hash})
    if not args.skip_voice:
        # Always run in the locked application environment, never bootstrap Python.
        run([PY, "-m", "scripts.prepare_voice"])
    if not args.skip_ollama:
        ensure_ollama(key, args.model, force or args.portable)
    write_state({"root": str(ROOT), "platform": key, "node": str(node), "installed": True})
    print("Setup complete. Your credentials and microphone access are configured in the first-run screen.", flush=True)


def ensure_windows_runtime():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            if winreg.QueryValueEx(key, "Installed")[0] == 1 and winreg.QueryValueEx(key, "Minor")[0] >= 40:
                return
    except OSError:
        pass
    installer = download(assets.VC_URL, CACHE / "downloads/VC_redist.x64.exe", assets.VC_SHA)
    print("Installing Microsoft's x64 Visual C++ runtime. Windows may ask for administrator consent.", flush=True)
    try:
        result = subprocess.run([str(installer), "/install", "/passive", "/norestart"])
        code = result.returncode
    except OSError as exc:
        if getattr(exc, "winerror", None) != 740:
            raise
        # Pass the path through an environment variable, avoiding shell interpolation.
        env = os.environ | {"JARVIS_VC_INSTALLER": str(installer)}
        command = "$p = Start-Process -FilePath $env:JARVIS_VC_INSTALLER -ArgumentList '/install','/passive','/norestart' -Verb RunAs -Wait -PassThru; exit $p.ExitCode"
        code = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], env=env).returncode
    if code not in (0, 1638, 3010):
        raise RuntimeError("Microsoft's runtime installer did not complete. Allow its Windows consent prompt, then rerun setup.")
    if code == 3010:
        raise RuntimeError("Microsoft's runtime requires a Windows restart. Restart, then launch Jarvis again.")


def launch(args):
    current = health()
    if current:
        if current.get("root") != str(ROOT):
            raise RuntimeError("A different Jarvis checkout is already running on port 8000. Stop it before starting this one.")
        print("Jarvis is already running at " + URL)
        if not args.no_browser:
            webbrowser.open(URL)
        return
    if occupied(8000):
        raise RuntimeError("Port 8000 is occupied. Stop that service or the older Jarvis process; this launcher will not terminate it.")
    setup(args)
    from backend.config import DATA
    instance = str(uuid.uuid4())
    child = spawn([PY, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"], DATA / "logs/backend.log", os.environ | {"JARVIS_INSTANCE_ID": instance})
    write_state({"backend": {"pid": child.pid, "instance": instance}})
    for _ in range(120):
        if child.poll() is not None:
            raise RuntimeError("Jarvis exited before becoming ready. Run doctor and inspect the backend log.")
        current = health()
        if current and current.get("instance") == instance and (args.skip_voice or (current["voice"]["tts"] and current["voice"]["stt"])):
            # Windows venv's python.exe can be a redirector with a different PID
            # from the interpreter serving HTTP. Record the proven instance's PID.
            write_state({"backend": {"pid": current["pid"], "instance": instance}})
            print("Jarvis is ready at " + URL)
            if not args.no_browser:
                webbrowser.open(URL)
            return
        time.sleep(1)
    raise RuntimeError("Jarvis did not become ready within 120 seconds. Run doctor.")


def owns_process(pid, executable):
    # PID reuse must never make us stop someone else's service.
    try:
        if WIN:
            command = "$p = Get-CimInstance Win32_Process -Filter 'ProcessId=" + str(int(pid)) + "'; if ($p) { $p.ExecutablePath }"
            result = subprocess.check_output(["powershell.exe", "-NoProfile", "-Command", command], text=True).strip()
            return os.path.normcase(result) == os.path.normcase(str(Path(executable).resolve()))
        result = subprocess.check_output(["ps", "-p", str(int(pid)), "-o", "command="], text=True).strip()
        return result == str(executable) + " serve"
    except (ValueError, OSError, subprocess.CalledProcessError):
        return False


def stop():
    state = read_state()
    current = health()
    backend = state.get("backend", {})
    if current and current.get("instance") == backend.get("instance") and current.get("pid") == backend.get("pid") and current.get("root") == str(ROOT):
        os.kill(backend["pid"], signal.SIGTERM)
        for _ in range(30):
            if not health():
                break
            time.sleep(.3)
        else:
            raise RuntimeError("Jarvis is still shutting down. Wait, then retry stop.")
    elif current:
        raise RuntimeError("The running Jarvis was not started by this launcher. Stop it from its own terminal.")
    child = state.get("ollama", {})
    if child and owns_process(child["pid"], child["executable"]):
        os.kill(child["pid"], signal.SIGTERM)
    write_state({"backend": {}, "ollama": {}})
    print("Stopped processes owned by this Jarvis installation.")


def doctor():
    from backend.config import DATA, load
    c = load()
    report = {"platform": platform_key(), "root": str(ROOT), "data_directory": str(DATA), "logs": str(DATA / "logs"), "python_environment": PY.exists(), "frontend_built": (ROOT / "dist/index.html").exists(), "disk_free_gb": round(shutil.disk_usage(ROOT).free / 2**30, 1), "backend": bool(health()), "port_8000_in_use": occupied(8000), "ollama_port_in_use": occupied(11434), "provider": c["provider"], "selected_model": c["model"], "openai_configured": bool(c["openai_key"]), "gmail_authorized": bool(c["google_tokens"]), "telegram_configured": bool(c["telegram_token"]), "desktop_requested": c["desktop_voice"]}
    print(json.dumps(report, indent=2))
    print("Secrets are excluded. Share this report, not settings.json or raw logs.")


def startup(enable):
    from scripts.startup import configure
    if enable and not read_state().get("installed"):
        raise RuntimeError("Complete setup before enabling login startup.")
    configure(enable, ROOT, sys.executable)


def uninstall():
    startup(False)
    stop()
    for name in (".venv", "node_modules", "dist", ".cache"):
        path = ROOT / name
        if path.is_symlink():
            path.unlink()
        elif path.exists():
            shutil.rmtree(path)
    # Keep the executing bootstrap Python until this process exits. Remove its
    # sibling runtimes; a future launch can reinstall everything idempotently.
    for path in RUNTIME.iterdir():
        if path.name in ("python", "uv", "setup.lock"):
            continue
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    print("App dependencies removed; small bootstrap runtimes and your data/models preserved. Delete the checkout and the data directory shown by doctor to remove them fully. External Ollama installations/models are untouched.")


def main():
    parser = argparse.ArgumentParser(description="Install and launch Jarvis on Windows/macOS.")
    parser.add_argument("command", nargs="?", choices=["launch", "setup", "doctor", "status", "stop", "repair", "startup", "uninstall"], default="launch")
    parser.add_argument("startup_action", nargs="?", choices=["enable", "disable"])
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--model", help="Ollama model to install/select; defaults to an existing model or qwen3:0.6b")
    parser.add_argument("--skip-voice", action="store_true", help="Developer/CI only: do not prepare voice assets")
    parser.add_argument("--skip-ollama", action="store_true", help="OpenAI-only/developer setup: skip local LLM installation")
    parser.add_argument("--portable", action="store_true", help="Exercise bundled Node/Ollama download paths instead of existing executables")
    args = parser.parse_args()
    os.chdir(ROOT)
    if os.name != "nt":
        os.umask(0o077)
    try:
        with installation_lock():
            if args.command == "launch":
                launch(args)
            elif args.command in ("setup", "repair"):
                if args.command == "repair" and health():
                    raise RuntimeError("Stop Jarvis before repairing its dependencies.")
                setup(args)
            elif args.command in ("doctor", "status"):
                doctor()
            elif args.command == "stop":
                stop()
            elif args.command == "startup":
                if not args.startup_action:
                    parser.error("startup requires enable or disable")
                startup(args.startup_action == "enable")
            else:
                uninstall()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        # External commands/logs may contain URLs; avoid printing arbitrary exception text.
        print("Jarvis: " + (str(exc) if isinstance(exc, RuntimeError) else f"Setup failed ({type(exc).__name__}). Run doctor; see README."), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
