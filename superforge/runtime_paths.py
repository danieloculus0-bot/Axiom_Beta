from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Axiom"
LEGACY_APP_NAME = "SuperForge"


def _has_legacy_data(root: Path) -> bool:
    return (root / "superforge.db").exists() or (root / "audit" / "superforge_audit.jsonl").exists()


def data_root() -> Path:
    override = os.environ.get("AXIOM_DATA_DIR") or os.environ.get("SUPERFORGE_DATA_DIR")
    if override:
        root = Path(override).expanduser().resolve()
    elif os.name == "nt":
        base = Path(os.environ.get("PROGRAMDATA") or r"C:\ProgramData")
        axiom_root = base / APP_NAME
        legacy_root = base / LEGACY_APP_NAME
        root = axiom_root if axiom_root.exists() or not _has_legacy_data(legacy_root) else legacy_root
    else:
        axiom_root = Path.home() / ".axiom"
        legacy_root = Path.home() / ".superforge"
        root = axiom_root if axiom_root.exists() or not _has_legacy_data(legacy_root) else legacy_root
    root.mkdir(parents=True, exist_ok=True)
    return root


def database_path() -> Path:
    root = data_root()
    legacy = root / "superforge.db"
    return legacy if legacy.exists() and not (root / "axiom.db").exists() else root / "axiom.db"


def audit_dir() -> Path:
    path = data_root() / "audit"
    path.mkdir(parents=True, exist_ok=True)
    return path


def audit_journal_path() -> Path:
    root = audit_dir()
    legacy = root / "superforge_audit.jsonl"
    return legacy if legacy.exists() and not (root / "axiom_audit.jsonl").exists() else root / "axiom_audit.jsonl"


def attachments_dir() -> Path:
    path = data_root() / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path


def integration_dir() -> Path:
    path = data_root() / "integrations"
    path.mkdir(parents=True, exist_ok=True)
    return path
