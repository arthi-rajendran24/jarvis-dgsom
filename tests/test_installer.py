import hashlib
import io
import json
import os
import tarfile
import zipfile
from pathlib import Path

import pytest
from scripts import manage
from scripts.downloads import download, safe_extract
from backend import config


def test_supported_platforms_and_explicit_arm_windows_rejection():
    assert manage.platform_key("Darwin", "arm64") == "darwin-arm64"
    assert manage.platform_key("Darwin", "x86_64") == "darwin-x64"
    assert manage.platform_key("Windows", "AMD64") == "windows-x64"
    with pytest.raises(RuntimeError, match="Unsupported"):
        manage.platform_key("Windows", "ARM64")


@pytest.mark.parametrize("name", ["../settings.json", "/tmp/escape", "C:/escape", "..\\escape"])
def test_zip_cannot_escape_installation(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr(name, "untrusted")
    with pytest.raises(ValueError):
        safe_extract(archive, tmp_path / "installation")


def test_tar_link_cannot_escape_installation(tmp_path):
    archive = tmp_path / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../outside"
        tar.addfile(member)
    with pytest.raises(ValueError):
        safe_extract(archive, tmp_path / "installation")


def test_download_repairs_corruption_and_reuses_verified_cache(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_bytes(b"verified model")
    target = tmp_path / "cached"
    target.write_bytes(b"corrupt")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    download(source.as_uri(), target, checksum)
    assert target.read_bytes() == source.read_bytes()
    source.unlink()
    # Must not hit the network/source on the second invocation.
    download(source.as_uri(), target, checksum)


def test_failed_checksum_never_replaces_previous_asset(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.downloads.time.sleep", lambda _: None)
    source = tmp_path / "source"
    source.write_bytes(b"wrong")
    target = tmp_path / "cached"
    target.write_bytes(b"old")
    with pytest.raises(RuntimeError, match="verify/download"):
        download(source.as_uri(), target, "0" * 64)
    assert target.read_bytes() == b"old"
    assert not target.with_name("cached.part").exists()


def test_stop_refuses_foreign_instance_even_if_pid_matches(monkeypatch):
    monkeypatch.setattr(manage, "read_state", lambda: {"backend": {"pid": 111, "instance": "ours"}})
    monkeypatch.setattr(manage, "health", lambda: {"pid": 111, "instance": "foreign", "root": str(manage.ROOT)})
    monkeypatch.setattr(manage.os, "kill", lambda *_: pytest.fail("must not kill foreign process"))
    with pytest.raises(RuntimeError, match="not started by this launcher"):
        manage.stop()


def test_launcher_refuses_foreign_service_on_port(monkeypatch):
    monkeypatch.setattr(manage, "health", lambda: None)
    monkeypatch.setattr(manage, "occupied", lambda _: True)
    monkeypatch.setattr(manage, "setup", lambda _: pytest.fail("must not mutate installation"))
    with pytest.raises(RuntimeError, match="Port 8000"):
        manage.launch(type("Args", (), {"no_browser": True})())


def test_atomic_config_preserves_existing_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FILE", tmp_path / "settings.json")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config.save({"openai_key": "fake-secret", "model": "custom-model"})
    config.save({"display_name": "Coworker", "setup_complete": True})
    assert config.load()["openai_key"] == "fake-secret"
    assert config.load()["model"] == "custom-model"
    assert config.load()["setup_complete"]
    assert not list(tmp_path.glob("*.tmp"))


def test_windows_private_directory_acl():
    if os.name != "nt":
        pytest.skip("NTFS ACL check runs on Windows CI")
    import subprocess
    permissions = subprocess.check_output(["icacls", str(config.DATA)], text=True)
    # No broad inherited grants are permitted on the credentials directory.
    assert "(I)" not in permissions
    assert "Everyone:" not in permissions
    assert "BUILTIN\\Users:" not in permissions
