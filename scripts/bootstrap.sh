#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$(uname -s)" != Darwin ]; then echo 'Use Windows .cmd or macOS .command; this launcher supports macOS only.'; exit 1; fi
case "$(uname -m)" in
  arm64) ARCH=aarch64; SHA=3993249d8f51deaf34cfce037e57e294e82267ff1f9dc45b7983a17afaf065b4 ;;
  x86_64) ARCH=x86_64; SHA=d7647571fb17a5107d4d23cc190418039c157fd7361ddb59bc6f8127a49e3eac ;;
  *) echo 'Unsupported Mac architecture.'; exit 1 ;;
esac
if [ "$(sw_vers -productVersion | cut -d. -f1)" -lt 14 ]; then echo 'Jarvis requires macOS 14 or later.'; exit 1; fi
mkdir -p .runtime/uv .cache/downloads
UV="$PWD/.runtime/uv/uv"
if [ ! -x "$UV" ] || ! "$UV" --version | grep -q '^uv 0.10.6'; then
  ARCHIVE="$PWD/.cache/downloads/uv-$ARCH.tar.gz"
  if [ ! -f "$ARCHIVE" ] || [ "$(shasum -a 256 "$ARCHIVE" | cut -d' ' -f1)" != "$SHA" ]; then
    echo 'Installing the pinned Jarvis bootstrap runtime…'
    curl --fail --location --retry 3 --connect-timeout 30 --progress-bar "https://github.com/astral-sh/uv/releases/download/0.10.6/uv-$ARCH-apple-darwin.tar.gz" -o "$ARCHIVE.part"
    [ "$(shasum -a 256 "$ARCHIVE.part" | cut -d' ' -f1)" = "$SHA" ] || { rm -f "$ARCHIVE.part"; echo 'UV checksum mismatch. Try again.'; exit 1; }
    mv "$ARCHIVE.part" "$ARCHIVE"
  fi
  tar -xzf "$ARCHIVE" --strip-components=1 -C .runtime/uv
fi
export UV_PYTHON_INSTALL_DIR="$PWD/.runtime/python"
export UV_PYTHON_BIN_DIR="$PWD/.runtime/bin"
export UV_CACHE_DIR="$PWD/.cache/uv"
export JARVIS_UV="$UV"
export UV_PYTHON_PREFERENCE=only-managed
"$UV" python install --no-bin --no-registry --install-dir "$UV_PYTHON_INSTALL_DIR" 3.11.14
BOOTSTRAP_PYTHON=$("$UV" python find --managed-python --system 3.11.14)
exec "$BOOTSTRAP_PYTHON" scripts/manage.py "$@"
