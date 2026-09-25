#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${AXIOM_INSTALL_PREFIX:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
APP_DIR="$PREFIX/share/axiom"
DESKTOP_DIR="$PREFIX/share/applications"

mkdir -p "$BIN_DIR" "$APP_DIR" "$DESKTOP_DIR"
install -m 0755 "$HERE/Axiom" "$APP_DIR/Axiom"
ln -sf "$APP_DIR/Axiom" "$BIN_DIR/axiom"

sed -e "s|@@EXEC@@|$APP_DIR/Axiom|g" -e "s|@@PATH@@|$APP_DIR|g" "$HERE/axiom.desktop" > "$DESKTOP_DIR/axiom.desktop"

echo "Axiom installed."
echo "Command: $BIN_DIR/axiom"
echo "Desktop entry: $DESKTOP_DIR/axiom.desktop"
echo "Operational data is stored separately and is not deleted by uninstall."
