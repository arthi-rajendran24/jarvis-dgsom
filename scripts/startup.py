"""Optional current-user login startup. No administrator/system service changes."""
import hashlib
import os
import plistlib
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape


def configure(enable, root, python):
    identity = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    label = "com.jarvis.local." + identity
    args = [str(python), str(root / "scripts/manage.py"), "launch", "--no-browser"]
    if os.name == "nt":
        name = "Jarvis-" + identity
        if enable:
            sid = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True).strip().split(",")[-1].strip('"')
            quoted = subprocess.list2cmdline(args[1:])
            xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task"><RegistrationInfo><Description>Jarvis login startup for {escape(str(root))}</Description></RegistrationInfo><Triggers><LogonTrigger><Enabled>true</Enabled><UserId>{escape(sid)}</UserId></LogonTrigger></Triggers><Principals><Principal id="Author"><UserId>{escape(sid)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals><Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><Enabled>true</Enabled></Settings><Actions Context="Author"><Exec><Command>{escape(args[0])}</Command><Arguments>{escape(quoted)}</Arguments><WorkingDirectory>{escape(str(root))}</WorkingDirectory></Exec></Actions></Task>'''
            target = root / ".runtime/startup.xml"
            target.write_text(xml, encoding="utf-16")
            subprocess.run(["schtasks.exe", "/Create", "/TN", name, "/XML", str(target), "/F"], check=True)
        else:
            existing = subprocess.run(["schtasks.exe", "/Query", "/TN", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if existing.returncode == 0:
                subprocess.run(["schtasks.exe", "/Delete", "/TN", name, "/F"], check=True)
    else:
        path = Path.home() / "Library/LaunchAgents" / (label + ".plist")
        domain = "gui/" + str(os.getuid())
        if path.exists():
            subprocess.run(["launchctl", "bootout", domain, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if enable:
            path.parent.mkdir(parents=True, exist_ok=True)
            from backend.config import DATA
            (DATA / "logs").mkdir(exist_ok=True)
            path.write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": args, "WorkingDirectory": str(root), "RunAtLoad": True, "EnvironmentVariables": {"JARVIS_DATA_DIR": str(DATA), "JARVIS_UV": os.environ.get("JARVIS_UV", str(root / ".runtime/uv/uv")), "UV_PYTHON_INSTALL_DIR": str(root / ".runtime/python"), "UV_CACHE_DIR": str(root / ".cache/uv")}, "StandardOutPath": str(DATA / "logs/startup.log"), "StandardErrorPath": str(DATA / "logs/startup.log")}))
            path.chmod(0o600)
            subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
        else:
            path.unlink(missing_ok=True)
    print("Login startup " + ("enabled" if enable else "disabled") + ". Keep this checkout in its current location.")
