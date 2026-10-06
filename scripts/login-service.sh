#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
case "${1:-}" in
  install) exec /bin/bash scripts/bootstrap.sh startup enable ;;
  uninstall) exec /bin/bash scripts/bootstrap.sh startup disable ;;
  *) echo 'Use login-service.sh install or uninstall.'; exit 1 ;;
esac
