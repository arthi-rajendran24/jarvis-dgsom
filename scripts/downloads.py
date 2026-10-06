"""Atomic checked downloads and traversal-safe extraction, using only the stdlib."""
import hashlib
import os
import stat
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download(url, destination, checksum):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and digest(destination) == checksum:
        return destination
    part = destination.with_name(destination.name + ".part")
    for attempt in range(3):
        try:
            print(f"Downloading {destination.name} (attempt {attempt + 1}/3)", flush=True)
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis-Setup/1.1"})
            with urllib.request.urlopen(req, timeout=120) as response, part.open("wb") as stream:
                total = int(response.headers.get("Content-Length", 0))
                count, last = 0, time.monotonic()
                while block := response.read(1024 * 1024):
                    stream.write(block)
                    count += len(block)
                    if time.monotonic() - last > 2:
                        print(f"  {count // 1048576} MB" + (f" / {total // 1048576} MB" if total else ""), flush=True)
                        last = time.monotonic()
            if digest(part) != checksum:
                raise ValueError(f"Checksum mismatch for {destination.name}")
            part.replace(destination)
            return destination
        except Exception:
            part.unlink(missing_ok=True)
            if attempt == 2:
                raise RuntimeError(f"Could not verify/download {destination.name}. Check internet, disk space, and proxy settings; retry the launcher.") from None
            time.sleep(attempt + 1)


def safe_extract(archive, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    def check(name):
        if "\\" in name or ":" in name:
            raise ValueError("Unsafe archive member")
        target = (destination / name).resolve()
        if not target.is_relative_to(destination):
            raise ValueError("Archive path escapes destination")
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                check(member.filename)
                if stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("Archive symlink is not allowed")
            source.extractall(destination)
    else:
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                check(member.name)
                # Official Node archives contain relative links inside the package.
                if member.issym():
                    check(str(Path(member.name).parent / member.linkname))
                elif member.islnk():
                    check(member.linkname)
                elif not (member.isfile() or member.isdir()):
                    raise ValueError("Unsupported archive member")
            source.extractall(destination, filter="data")
