from __future__ import annotations

from .db import db

ORG_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS org_units(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  unit_key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  parent_unit_id INTEGER REFERENCES org_units(id),
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS org_people(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_key TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  email TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_org_people_email ON org_people(email,active);

CREATE TABLE IF NOT EXISTS org_roles(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role_key TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  unit_id INTEGER REFERENCES org_units(id),
  parent_role_id INTEGER REFERENCES org_roles(id),
  authority_level INTEGER NOT NULL DEFAULT 50,
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_org_roles_unit ON org_roles(unit_id,active);

CREATE TABLE IF NOT EXISTS org_assignments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER NOT NULL REFERENCES org_people(id),
  role_id INTEGER NOT NULL REFERENCES org_roles(id),
  is_primary INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1,
  effective_start TEXT,
  effective_end TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(person_id,role_id)
);
CREATE INDEX IF NOT EXISTS ix_org_assignments_role ON org_assignments(role_id,active,is_primary);

CREATE TABLE IF NOT EXISTS decision_protocols(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,
  source_module TEXT,
  target_module TEXT NOT NULL DEFAULT 'leadership',
  target_role_key TEXT,
  signal_type TEXT NOT NULL DEFAULT 'operational',
  title_template TEXT NOT NULL,
  rationale_template TEXT NOT NULL,
  action_template TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'normal',
  default_impact REAL NOT NULL DEFAULT 0.5,
  default_urgency REAL NOT NULL DEFAULT 0.5,
  confidence_floor REAL NOT NULL DEFAULT 0.5,
  escalation_hours INTEGER NOT NULL DEFAULT 24,
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_decision_protocol_event ON decision_protocols(event_type,source_module,active);
"""

DEFAULT_UNITS = [
    ("company", "Company", None),
    ("operations", "Operations", "company"),
    ("quality", "Quality", "company"),
    ("purchasing", "Purchasing", "operations"),
    ("hr_finance", "HR / Finance", "company"),
]

DEFAULT_ROLES = [
    ("general_manager", "General Manager", "company", None, 100),
    ("operations_manager", "Operations Manager", "operations", "general_manager", 90),
    ("quality_manager", "Quality Manager", "quality", "general_manager", 85),
    ("purchasing_manager", "Purchasing Manager", "purchasing", "operations_manager", 75),
    ("payroll_manager", "Payroll / HR Manager", "hr_finance", "general_manager", 80),
]

DEFAULT_PROTOCOLS = [
    (
        "Executive quality escalation",
        "quality.created",
        "quality",
        "leadership",
        "quality_manager",
        "quality",
        "Quality event requires leadership review",
        "A new quality record can affect customer risk, delivery, cost, or systemic process control.",
        "Review containment, recurrence risk, customer impact, and whether broader corrective action is required.",
        "high",
        0.80,
        0.75,
        0.60,
        8,
    ),
    (
        "Late purchase order escalation",
        "po.late",
        "purchase_orders",
        "leadership",
        "purchasing_manager",
        "supply",
        "Late PO threatens execution",
        "A purchased resource is late enough to threaten downstream job readiness or delivery.",
        "Confirm supplier recovery, alternate approved sources, job impact, and an executive recovery owner.",
        "high",
        0.75,
        0.85,
        0.65,
        8,
    ),
    (
        "Inventory shortage escalation",
        "inventory.shortage",
        "inventory",
        "leadership",
        "purchasing_manager",
        "supply",
        "Inventory shortage needs recovery action",
        "Available material is at or below the configured threshold and may affect scheduled work.",
        "Validate demand, approved source, need-by date, substitution constraints, and recovery action.",
        "high",
        0.70,
        0.80,
        0.65,
        12,
    ),
    (
        "Machine failure escalation",
        "pm.failed",
        "pm",
        "leadership",
        "operations_manager",
        "capacity",
        "Machine failure threatens capacity",
        "Equipment failure can propagate into job delay, overtime, subcontracting, and quality risk.",
        "Review affected jobs, alternate machines, subcontract options, recovery timing, and communication ownership.",
        "critical",
        0.90,
        0.90,
        0.70,
        4,
    ),
    (
        "Workforce risk escalation",
        "morale.pulse.recorded",
        "leadership",
        "bean",
        "operations_manager",
        "workforce",
        "Workforce risk pattern needs analysis",
        "Aggregate workforce-health signals may be interacting with quality, delivery, overtime, or staffing risk.",
        "Compare workforce, quality, delivery, and staffing trends and propose a reviewed management response.",
        "normal",
        0.60,
        0.55,
        0.55,
        24,
    ),
]


def init_org_schema() -> None:
    with db() as con:
        con.executescript(ORG_SCHEMA)
        for key, name, parent_key in DEFAULT_UNITS:
            parent_id = None
            if parent_key:
                row = con.execute("SELECT id FROM org_units WHERE unit_key=?", (parent_key,)).fetchone()
                parent_id = int(row["id"]) if row else None
            con.execute(
                """INSERT INTO org_units(unit_key,name,parent_unit_id,active)
                   VALUES(?,?,?,1)
                   ON CONFLICT(unit_key) DO UPDATE SET
                     name=excluded.name,
                     parent_unit_id=COALESCE(org_units.parent_unit_id,excluded.parent_unit_id)""",
                (key, name, parent_id),
            )

        for role_key, title, unit_key, parent_role_key, level in DEFAULT_ROLES:
            unit = con.execute("SELECT id FROM org_units WHERE unit_key=?", (unit_key,)).fetchone()
            parent_role_id = None
            if parent_role_key:
                parent = con.execute("SELECT id FROM org_roles WHERE role_key=?", (parent_role_key,)).fetchone()
                parent_role_id = int(parent["id"]) if parent else None
            con.execute(
                """INSERT INTO org_roles(role_key,title,unit_id,parent_role_id,authority_level,active)
                   VALUES(?,?,?,?,?,1)
                   ON CONFLICT(role_key) DO UPDATE SET
                     title=excluded.title,unit_id=excluded.unit_id,
                     parent_role_id=COALESCE(org_roles.parent_role_id,excluded.parent_role_id),
                     authority_level=excluded.authority_level""",
                (role_key, title, int(unit["id"]) if unit else None, parent_role_id, level),
            )

        for row in DEFAULT_PROTOCOLS:
            con.execute(
                """INSERT INTO decision_protocols(
                     name,event_type,source_module,target_module,target_role_key,signal_type,
                     title_template,rationale_template,action_template,priority,default_impact,
                     default_urgency,confidence_floor,escalation_hours,active
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
                   ON CONFLICT(name) DO NOTHING""",
                row,
            )
