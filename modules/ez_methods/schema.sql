PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ezm_method_plans (
    id INTEGER PRIMARY KEY,
    job_number TEXT NOT NULL,
    part_number TEXT NOT NULL,
    revision TEXT NOT NULL,
    customer TEXT,
    quantity REAL NOT NULL,
    required_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(job_number, part_number, revision)
);

CREATE TABLE IF NOT EXISTS ezm_sources (
    id INTEGER PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES ezm_method_plans(id),
    source_type TEXT NOT NULL,
    document_number TEXT NOT NULL,
    revision TEXT,
    sheet TEXT,
    page INTEGER,
    location TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS ezm_operations (
    id INTEGER PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES ezm_method_plans(id),
    sequence INTEGER NOT NULL,
    work_center TEXT NOT NULL,
    operation TEXT NOT NULL,
    scheduled_date TEXT NOT NULL,
    instruction TEXT NOT NULL,
    inspection_requirement TEXT,
    hold_point INTEGER NOT NULL DEFAULT 0,
    controlled_operation INTEGER NOT NULL DEFAULT 0,
    UNIQUE(plan_id, sequence)
);

CREATE TABLE IF NOT EXISTS ezm_dependencies (
    id INTEGER PRIMARY KEY,
    operation_id INTEGER NOT NULL REFERENCES ezm_operations(id),
    dependency_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    description TEXT NOT NULL,
    required_qty REAL NOT NULL,
    need_by TEXT NOT NULL,
    availability TEXT NOT NULL DEFAULT 'UNKNOWN',
    on_hand_qty REAL NOT NULL DEFAULT 0,
    ordered_qty REAL NOT NULL DEFAULT 0,
    promised_date TEXT,
    supplier TEXT,
    supplier_part_number TEXT,
    internal_tool_id TEXT,
    purchase_order TEXT,
    owner TEXT,
    owner_email TEXT,
    next_action TEXT,
    expedite_occurrence_id TEXT
);

CREATE TABLE IF NOT EXISTS ezm_gdt_characteristics (
    id INTEGER PRIMARY KEY,
    operation_id INTEGER NOT NULL REFERENCES ezm_operations(id),
    characteristic_key TEXT NOT NULL UNIQUE,
    control_type TEXT NOT NULL,
    tolerance REAL NOT NULL,
    material_condition TEXT NOT NULL DEFAULT 'RFS',
    datum_a TEXT,
    datum_b TEXT,
    datum_c TEXT,
    basic_dimensions_json TEXT,
    diameter_zone INTEGER NOT NULL DEFAULT 0,
    projected_tolerance_zone REAL,
    tangent_plane INTEGER NOT NULL DEFAULT 0,
    free_state INTEGER NOT NULL DEFAULT 0,
    all_around INTEGER NOT NULL DEFAULT 0,
    all_over INTEGER NOT NULL DEFAULT 0,
    inspection_method TEXT,
    gage_id TEXT,
    source_document TEXT NOT NULL,
    source_revision TEXT,
    source_sheet TEXT,
    source_location TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS ezm_events (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS ix_ezm_dependency_need_by
ON ezm_dependencies(need_by, availability);

CREATE INDEX IF NOT EXISTS ix_ezm_event_entity
ON ezm_events(entity_type, entity_id, occurred_at);
