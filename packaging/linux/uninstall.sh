#!/usr/bin/env bash
set -euo pipefail

PREFIX="${AXIOM_INSTALL_PREFIX:-$HOME/.local}"
rm -f "$PREFIX/bin/axiom"
rm -f "$PREFIX/share/applications/axiom.desktop"
rm -rf "$PREFIX/share/axiom"

if [[ "${1:-}" == "--purge-data" ]]; then
  rm -rf "${AXIOM_DATA_DIR:-$HOME/.axiom}"
  echo "Axiom application and operational data removed."
else
  echo "Axiom application removed. Operational data preserved."
  echo "Use --purge-data only if you intentionally want to delete local Axiom data."
fi
