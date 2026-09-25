from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "SuperForge"

def data_root() -> Path:
    override = os.environ.get("SUPERFORGE_DATA_DIR")
    if override:
        root = Path(override).expanduser().resolve()
    elif os.name == "nt":
        root = Path(os.environ.get("PROGRAMDATA") or r"C:\\ProgramData") / APP_NAME
    else:
        root = Path.home() / ".superforge"
    root.mkdir(parents=True, exist_ok=True)
    return root

def database_path() -> Path:
    return data_root() / "superforge.db"

def audit_dir() -> Path:
    path = data_root() / "audit"
    path.mkdir(parents=True, exist_ok=True)
    return path

def audit_journal_path() -> Path:
    return audit_dir() / "superforge_audit.jsonl"

def attachments_dir() -> Path:
    path = data_root() / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path

def integration_dir() -> Path:
    path = data_root() / "integrations"
    path.mkdir(parents=True, exist_ok=True)
    return path
