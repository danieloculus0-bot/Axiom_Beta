"""Durable local Axiom module favorites used by BEAN navigation.

Favorites are real saved module keys (not model-generated URLs).  The registry
provides current local paths, so a renamed route can be updated centrally.
This is an existing local-user workspace, not multiuser authentication.
"""
from __future__ import annotations

from .context_menu import MODULES
from .db import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS navigation_favorites(
    user_key TEXT NOT NULL,
    module_key TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(user_key, module_key)
);
"""


def init_favorites() -> None:
    with db() as con:
        con.executescript(SCHEMA)


def destinations() -> list[dict]:
    return [{"key": key, "label": label, "href": href} for key, label, href in MODULES]


def find_destinations(query: str) -> list[dict]:
    """Use real registered suite destinations, no hallucinated URLs."""
    if not isinstance(query, str) or len(query) > 160:
        raise ValueError("Invalid navigation search")
    terms = query.casefold().strip().split()
    rows = destinations()
    if not terms:
        return rows
    ranked = []
    for item in rows:
        text = (item["key"].replace("_", " ") + " " + item["label"]).casefold()
        if all(term in text for term in terms):
            ranked.append(item)
    return ranked


def list_favorites(user_key: str = "local") -> list[dict]:
    lookup = {item["key"]: item for item in destinations()}
    with db() as con:
        records = con.execute(
            "SELECT module_key FROM navigation_favorites WHERE user_key=? ORDER BY created_at, rowid",
            (user_key,),
        ).fetchall()
    return [lookup[row["module_key"]] for row in records if row["module_key"] in lookup]


def add_favorite(module_key: str, user_key: str = "local") -> dict:
    lookup = {item["key"]: item for item in destinations()}
    if module_key not in lookup:
        raise ValueError("Unknown Axiom destination")
    with db() as con:
        result = con.execute(
            "INSERT OR IGNORE INTO navigation_favorites(user_key,module_key) VALUES(?,?)",
            (user_key, module_key),
        )
        created = result.rowcount == 1
    return {"ok": True, "saved": True, "created": created, "favorite": lookup[module_key]}


def remove_favorite(module_key: str, user_key: str = "local") -> dict:
    lookup = {item["key"]: item for item in destinations()}
    if module_key not in lookup:
        raise ValueError("Unknown Axiom destination")
    with db() as con:
        result = con.execute(
            "DELETE FROM navigation_favorites WHERE user_key=? AND module_key=?",
            (user_key, module_key),
        )
    return {"ok": True, "removed": result.rowcount == 1, "module_key": module_key}
