from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

SCHEMA = r"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS occurrence_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL DEFAULT 'EXP',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS occurrences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number TEXT NOT NULL UNIQUE,
    occurrence_type_id INTEGER NOT NULL REFERENCES occurrence_types(id),
    title TEXT NOT NULL,
    description TEXT,
    source TEXT,
    customer TEXT,
    supplier TEXT,
    part_number TEXT,
    revision TEXT,
    work_order TEXT,
    sales_order TEXT,
    purchase_order TEXT,
    department TEXT,
    work_center TEXT,
    owner_name TEXT,
    owner_email TEXT,
    priority TEXT NOT NULL DEFAULT 'Normal',
    status TEXT NOT NULL DEFAULT 'NEW',
    next_action TEXT,
    due_date TEXT,
    created_date TEXT,
    closed_date TEXT,
    last_activity_at TEXT,
    source_email_id TEXT,
    source_email_web_link TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_occurrences_status ON occurrences(status);
CREATE INDEX IF NOT EXISTS idx_occurrences_owner ON occurrences(owner_email);
CREATE INDEX IF NOT EXISTS idx_occurrences_due ON occurrences(due_date);
CREATE INDEX IF NOT EXISTS idx_occurrences_type ON occurrences(occurrence_type_id);

CREATE TABLE IF NOT EXISTS rma_details (
    occurrence_id INTEGER PRIMARY KEY REFERENCES occurrences(id) ON DELETE CASCADE,
    rma_number TEXT,
    quality_no TEXT,
    customer_ncr TEXT,
    part_description TEXT,
    qty_authorized REAL,
    qty_received REAL,
    receive_date TEXT,
    rejection_type TEXT,
    discrepancy TEXT,
    containment_required INTEGER NOT NULL DEFAULT 0,
    containment_complete INTEGER NOT NULL DEFAULT 0,
    corrective_action_required INTEGER NOT NULL DEFAULT 0,
    corrective_action_complete INTEGER NOT NULL DEFAULT 0,
    disposition_one TEXT,
    disposition_two TEXT,
    disposition_three TEXT,
    disposition_complete INTEGER NOT NULL DEFAULT 0,
    reject_type TEXT,
    qty_returned REAL,
    customer_complaint INTEGER NOT NULL DEFAULT 0,
    total_rework_cost REAL NOT NULL DEFAULT 0,
    scrap_cost REAL NOT NULL DEFAULT 0,
    freight_cost REAL NOT NULL DEFAULT 0,
    outside_processing_cost REAL NOT NULL DEFAULT 0,
    recovery_requested REAL NOT NULL DEFAULT 0,
    recovery_received REAL NOT NULL DEFAULT 0,
    recovery_status TEXT NOT NULL DEFAULT 'NOT REQUIRED',
    recovery_owner TEXT,
    credit_memo_number TEXT,
    debit_memo_number TEXT,
    sales_comment TEXT,
    customer_discrepancy TEXT,
    rma_stage TEXT NOT NULL DEFAULT 'INTAKE',
    csr_name TEXT,
    defect_type TEXT,
    contact_name TEXT,
    contact_phone TEXT,
    received_from_customer TEXT,
    hold_area_confirmed INTEGER NOT NULL DEFAULT 0,
    product_reviewed INTEGER NOT NULL DEFAULT 0,
    work_order_required TEXT,
    work_order_issued TEXT,
    final_quality_result TEXT,
    approved_to_ship TEXT,
    ready_to_ship TEXT,
    shipped_to_customer INTEGER NOT NULL DEFAULT 0,
    returned_to_customer_date TEXT
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_id INTEGER NOT NULL REFERENCES occurrences(id) ON DELETE CASCADE,
    activity_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    actor TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activities_occurrence ON activities(occurrence_id, created_at);

CREATE TABLE IF NOT EXISTS occurrence_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_id INTEGER NOT NULL REFERENCES occurrences(id) ON DELETE CASCADE,
    message_id TEXT NOT NULL UNIQUE,
    subject TEXT,
    sender_name TEXT,
    sender_email TEXT,
    received_at TEXT,
    web_link TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_field_defs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_type_id INTEGER NOT NULL REFERENCES occurrence_types(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    label TEXT NOT NULL,
    field_type TEXT NOT NULL DEFAULT 'text',
    required INTEGER NOT NULL DEFAULT 0,
    options_text TEXT,
    sort_order INTEGER NOT NULL DEFAULT 100,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(occurrence_type_id, name)
);

CREATE TABLE IF NOT EXISTS custom_field_values (
    occurrence_id INTEGER NOT NULL REFERENCES occurrences(id) ON DELETE CASCADE,
    field_def_id INTEGER NOT NULL REFERENCES custom_field_defs(id) ON DELETE CASCADE,
    value_text TEXT,
    PRIMARY KEY(occurrence_id, field_def_id)
);

CREATE TABLE IF NOT EXISTS checklist_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_type_id INTEGER NOT NULL REFERENCES occurrence_types(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    required INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 100,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS checklist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_id INTEGER NOT NULL REFERENCES occurrences(id) ON DELETE CASCADE,
    template_id INTEGER REFERENCES checklist_templates(id) ON DELETE SET NULL,
    label TEXT NOT NULL,
    required INTEGER NOT NULL DEFAULT 1,
    completed INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT,
    completed_by TEXT,
    UNIQUE(occurrence_id, template_id)
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_id INTEGER NOT NULL REFERENCES occurrences(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    uploaded_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS external_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_id INTEGER NOT NULL REFERENCES occurrences(id) ON DELETE CASCADE,
    system_name TEXT NOT NULL,
    entity_type TEXT,
    external_id TEXT NOT NULL,
    external_url TEXT,
    note TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(system_name, entity_type, external_id, occurrence_id)
);
CREATE INDEX IF NOT EXISTS idx_external_refs_lookup ON external_refs(system_name, entity_type, external_id);

CREATE TABLE IF NOT EXISTS external_connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'flat_file',
    base_url TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurrence_id INTEGER NOT NULL REFERENCES occurrences(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    due_date_snapshot TEXT,
    recipient TEXT,
    sent_at TEXT NOT NULL,
    detail TEXT,
    UNIQUE(occurrence_id, channel, rule_key, due_date_snapshot, recipient)
);

CREATE TABLE IF NOT EXISTS digest_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient TEXT NOT NULL,
    digest_type TEXT NOT NULL,
    digest_date TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    item_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(recipient, digest_type, digest_date)
);
"""


def utcnow() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def init_db(db_path: str | Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.executescript(SCHEMA)
        columns = {row[1] for row in con.execute("PRAGMA table_info(rma_details)").fetchall()}
        rma_migrations = {
            "rma_number": "TEXT",
            "rma_stage": "TEXT NOT NULL DEFAULT 'INTAKE'",
            "csr_name": "TEXT",
            "defect_type": "TEXT",
            "contact_name": "TEXT",
            "contact_phone": "TEXT",
            "received_from_customer": "TEXT",
            "hold_area_confirmed": "INTEGER NOT NULL DEFAULT 0",
            "product_reviewed": "INTEGER NOT NULL DEFAULT 0",
            "work_order_required": "TEXT",
            "work_order_issued": "TEXT",
            "final_quality_result": "TEXT",
            "approved_to_ship": "TEXT",
            "ready_to_ship": "TEXT",
            "shipped_to_customer": "INTEGER NOT NULL DEFAULT 0",
            "returned_to_customer_date": "TEXT",
        }
        for column, definition in rma_migrations.items():
            if column not in columns:
                con.execute(f"ALTER TABLE rma_details ADD COLUMN {column} {definition}")
        con.execute(
            """UPDATE rma_details
               SET rma_number=quality_no
               WHERE (rma_number IS NULL OR rma_number='') AND quality_no IS NOT NULL AND quality_no!=''"""
        )
        con.execute(
            """CREATE UNIQUE INDEX IF NOT EXISTS idx_rma_number_unique
               ON rma_details(rma_number) WHERE rma_number IS NOT NULL AND rma_number != ''"""
        )
        now = utcnow()
        con.execute(
            "INSERT OR IGNORE INTO occurrence_types(name, prefix, active, created_at) VALUES(?,?,1,?)",
            ("RMA", "RMA", now),
        )
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('setup_complete','0')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('m365_tenant','organizations')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('m365_client_secret','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('public_base_url','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('multi_user_mode','1')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('listen_host','127.0.0.1')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('listen_port','5050')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('expediter_interval_minutes','30')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('theme_mode','dark')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('theme_accent','#1F6FBC')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('theme_accent_strong','#0B3A75')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('theme_background','#090B0E')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('theme_panel','#11161C')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('theme_card','#171E26')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('theme_text','#F4F7FB')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('theme_muted','#9BA8B7')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_csr_name','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_csr_email','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_csr_name_2','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_csr_email_2','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_shipping_name','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_shipping_email','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_shipping_name_2','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_shipping_email_2','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_quality_name','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_quality_email','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_quality_name_2','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_role_quality_email_2','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_cc_quality','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_cc_operations','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_cc_customer_service','')")
        con.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rma_cc_design','')")
        con.commit()


@contextmanager
def connect(db_path: str | Path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def get_setting(con: sqlite3.Connection, key: str, default: str = "") -> str:
    row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row and row[0] is not None else default


def set_setting(con: sqlite3.Connection, key: str, value: str) -> None:
    con.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def next_case_number(con: sqlite3.Connection, type_id: int) -> str:
    row = con.execute("SELECT prefix FROM occurrence_types WHERE id=?", (type_id,)).fetchone()
    prefix = (row[0] if row else "EXP").strip().upper() or "EXP"
    year = datetime.now().year
    like = f"{prefix}-{year}-%"
    existing = con.execute(
        "SELECT case_number FROM occurrences WHERE case_number LIKE ? ORDER BY id DESC LIMIT 1000",
        (like,),
    ).fetchall()
    highest = 0
    for item in existing:
        try:
            highest = max(highest, int(str(item[0]).rsplit("-", 1)[1]))
        except (ValueError, IndexError):
            pass
    return f"{prefix}-{year}-{highest + 1:04d}"


def log_activity(
    con: sqlite3.Connection,
    occurrence_id: int,
    activity_type: str,
    detail: str,
    actor: str = "",
) -> None:
    now = utcnow()
    con.execute(
        "INSERT INTO activities(occurrence_id,activity_type,detail,actor,created_at) VALUES(?,?,?,?,?)",
        (occurrence_id, activity_type, detail, actor, now),
    )
    con.execute(
        "UPDATE occurrences SET last_activity_at=?, updated_at=? WHERE id=?",
        (now, now, occurrence_id),
    )


def ensure_checklist_items(con: sqlite3.Connection, occurrence_id: int, type_id: int) -> None:
    templates = con.execute(
        "SELECT id,label,required FROM checklist_templates WHERE occurrence_type_id=? AND active=1 ORDER BY sort_order,id",
        (type_id,),
    ).fetchall()
    for item in templates:
        con.execute(
            """INSERT OR IGNORE INTO checklist_items(occurrence_id,template_id,label,required)
               VALUES(?,?,?,?)""",
            (occurrence_id, item["id"], item["label"], item["required"]),
        )


def set_custom_value(con: sqlite3.Connection, occurrence_id: int, field_def_id: int, value: str) -> None:
    con.execute(
        """INSERT INTO custom_field_values(occurrence_id,field_def_id,value_text)
           VALUES(?,?,?)
           ON CONFLICT(occurrence_id,field_def_id) DO UPDATE SET value_text=excluded.value_text""",
        (occurrence_id, field_def_id, value),
    )


def generic_close_blockers(con: sqlite3.Connection, occurrence_id: int) -> list[str]:
    blockers: list[str] = []
    row = con.execute(
        "SELECT owner_name,owner_email,next_action FROM occurrences WHERE id=?",
        (occurrence_id,),
    ).fetchone()
    if not row:
        return ["Occurrence not found."]
    if not (row["owner_name"] or row["owner_email"]):
        blockers.append("No owner is assigned.")
    incomplete = con.execute(
        "SELECT label FROM checklist_items WHERE occurrence_id=? AND required=1 AND completed=0 ORDER BY id",
        (occurrence_id,),
    ).fetchall()
    blockers.extend(f"Required checklist item incomplete: {x['label']}" for x in incomplete)
    required_fields = con.execute(
        """SELECT d.label,COALESCE(v.value_text,'') value
           FROM occurrences o
           JOIN custom_field_defs d ON d.occurrence_type_id=o.occurrence_type_id AND d.required=1 AND d.active=1
           LEFT JOIN custom_field_values v ON v.field_def_id=d.id AND v.occurrence_id=o.id
           WHERE o.id=?""",
        (occurrence_id,),
    ).fetchall()
    blockers.extend(f"Required field is blank: {x['label']}" for x in required_fields if not str(x["value"] or "").strip())
    return blockers
