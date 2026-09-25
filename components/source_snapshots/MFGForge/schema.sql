CREATE TABLE IF NOT EXISTS system_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    code TEXT,
    contact_name TEXT,
    email TEXT,
    phone TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    code TEXT,
    contact_name TEXT,
    email TEXT,
    phone TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    manager_name TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reason_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    category TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operating_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name TEXT NOT NULL UNIQUE,
    operating_mode TEXT NOT NULL,
    planning_horizon_days INTEGER,
    target_inventory_days INTEGER,
    purchasing_review_cadence TEXT,
    lead_time_strategy TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_number TEXT NOT NULL UNIQUE,
    revision TEXT,
    description TEXT,
    customer_id INTEGER REFERENCES customers(id),
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_number TEXT NOT NULL UNIQUE,
    part_id INTEGER REFERENCES parts(id),
    customer_id INTEGER REFERENCES customers(id),
    quantity_ordered INTEGER,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quality_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL CHECK (event_type IN ('RMA', 'NCR', 'DMR', 'CAPA', 'INSPECTION_REJECT', 'CUSTOMER_COMPLAINT')),
    event_number TEXT NOT NULL UNIQUE,
    customer_id INTEGER REFERENCES customers(id),
    part_id INTEGER REFERENCES parts(id),
    work_order_id INTEGER REFERENCES work_orders(id),
    reason_code_id INTEGER REFERENCES reason_codes(id),
    quantity_affected INTEGER,
    severity TEXT NOT NULL DEFAULT 'unassigned',
    status TEXT NOT NULL DEFAULT 'open',
    description TEXT NOT NULL,
    containment TEXT,
    root_cause TEXT,
    corrective_action TEXT,
    owner TEXT,
    opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS deviations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deviation_number TEXT NOT NULL UNIQUE,
    customer_id INTEGER REFERENCES customers(id),
    part_id INTEGER REFERENCES parts(id),
    work_order_id INTEGER REFERENCES work_orders(id),
    requested_by TEXT,
    reason TEXT NOT NULL,
    proposed_disposition TEXT,
    risk_assessment TEXT,
    approval_status TEXT NOT NULL DEFAULT 'draft',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_number TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    revision TEXT,
    document_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    owner TEXT,
    storage_reference TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pm_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_number TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    asset_type TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    pm_frequency TEXT,
    last_pm_date TEXT,
    next_pm_date TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS morale_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    overtime_hours REAL,
    exhausted_pto_count INTEGER,
    unscheduled_absence_count INTEGER,
    unpaid_timeoff_count INTEGER,
    turnover_count INTEGER,
    staffing_notes TEXT,
    quality_risk_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_code TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    supplier_id INTEGER REFERENCES suppliers(id),
    material_category TEXT,
    stock_form TEXT,
    grade_spec TEXT,
    cost_per_unit REAL,
    cost_unit TEXT,
    standard_length TEXT,
    lead_time_days INTEGER,
    approval_status TEXT NOT NULL DEFAULT 'draft',
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS material_certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    certificate_number TEXT,
    cert_type TEXT NOT NULL DEFAULT 'material_cert',
    material_id INTEGER REFERENCES materials(id),
    supplier_id INTEGER REFERENCES suppliers(id),
    work_order_id INTEGER REFERENCES work_orders(id),
    heat_number TEXT,
    lot_number TEXT,
    purchase_order_number TEXT,
    received_date TEXT,
    document_date TEXT,
    storage_reference TEXT,
    review_status TEXT NOT NULL DEFAULT 'needs_review',
    reviewed_by TEXT,
    reviewer_notes TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS supplier_performance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER REFERENCES suppliers(id),
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    quoted_lead_time_days REAL,
    actual_average_lead_time_days REAL,
    late_delivery_count INTEGER,
    quality_issue_count INTEGER,
    risk_level TEXT NOT NULL DEFAULT 'medium',
    impact_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS machine_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_number TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    machine_type TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    capacity_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS machine_utilization_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_asset_id INTEGER REFERENCES machine_assets(id),
    work_order_id INTEGER REFERENCES work_orders(id),
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    committed_hours REAL,
    available_hours REAL,
    utilization_percent REAL,
    risk_level TEXT NOT NULL DEFAULT 'medium',
    impact_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quote_intakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_number TEXT NOT NULL UNIQUE,
    customer_id INTEGER REFERENCES customers(id),
    operating_profile_id INTEGER REFERENCES operating_profiles(id),
    drawing_reference TEXT,
    intake_status TEXT NOT NULL DEFAULT 'new',
    due_date TEXT,
    assigned_to TEXT,
    customer_requirements TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pdf_bom_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_intake_id INTEGER REFERENCES quote_intakes(id),
    candidate_source TEXT,
    line_text TEXT NOT NULL,
    candidate_part_number TEXT,
    candidate_description TEXT,
    material_guess TEXT,
    quantity_guess REAL,
    confidence_score REAL,
    review_status TEXT NOT NULL DEFAULT 'needs_review',
    reviewer_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bom_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_intake_id INTEGER REFERENCES quote_intakes(id),
    review_status TEXT NOT NULL DEFAULT 'draft',
    reviewed_by TEXT,
    review_notes TEXT,
    approved_for_quote_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quote_material_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quote_intake_id INTEGER REFERENCES quote_intakes(id),
    bom_candidate_id INTEGER REFERENCES pdf_bom_candidates(id),
    material_id INTEGER REFERENCES materials(id),
    assignment_basis TEXT,
    standard_length TEXT,
    pieces_required REAL,
    estimated_material_cost REAL,
    lead_time_days INTEGER,
    review_status TEXT NOT NULL DEFAULT 'draft',
    reviewer_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS planning_watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_order_id INTEGER REFERENCES work_orders(id),
    customer_id INTEGER REFERENCES customers(id),
    watch_type TEXT NOT NULL,
    risk_level TEXT NOT NULL DEFAULT 'medium',
    due_date TEXT,
    owner TEXT,
    signal TEXT NOT NULL,
    action_required TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchasing_watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER REFERENCES suppliers(id),
    material_id INTEGER REFERENCES materials(id),
    need_by_date TEXT,
    quantity_needed REAL,
    risk_level TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'open',
    buyer_owner TEXT,
    signal TEXT NOT NULL,
    action_required TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fpy_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    part_id INTEGER REFERENCES parts(id),
    customer_id INTEGER REFERENCES customers(id),
    work_center TEXT,
    pieces_started INTEGER,
    pieces_accepted_first_pass INTEGER,
    reject_count INTEGER,
    rework_count INTEGER,
    summary_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operator_efficiency_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    operator_group TEXT,
    baseline_type TEXT NOT NULL,
    planned_hours REAL,
    actual_hours REAL,
    throughput_count INTEGER,
    privacy_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quoting_throughput_baselines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    quote_count INTEGER,
    drawing_intake_count INTEGER,
    bom_candidate_count INTEGER,
    average_cycle_days REAL,
    bottleneck_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dashboard_metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_date TEXT NOT NULL,
    metric_area TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value REAL,
    metric_unit TEXT,
    context_notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ai_action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,
    target_table TEXT,
    target_id INTEGER,
    prompt_summary TEXT NOT NULL,
    recommendation TEXT,
    human_approval_status TEXT NOT NULL DEFAULT 'draft',
    executed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR REPLACE INTO system_meta (key, value, updated_at) VALUES ('schema_version', '0.4.0', CURRENT_TIMESTAMP);
