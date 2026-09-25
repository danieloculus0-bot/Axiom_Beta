from __future__ import annotations
from pathlib import Path
from .db import db

EXTENSION_SCHEMA=r"""
CREATE TABLE IF NOT EXISTS quote_intakes(
  id INTEGER PRIMARY KEY AUTOINCREMENT,quote_number TEXT NOT NULL UNIQUE,customer_id INTEGER REFERENCES customers(id),
  part_id INTEGER REFERENCES parts(id),drawing_document_id INTEGER REFERENCES documents(id),due_date TEXT,status TEXT NOT NULL DEFAULT 'new',
  owner TEXT,estimated_value REAL,lead_time_days INTEGER,material_risk TEXT,capacity_risk TEXT,quality_risk TEXT,notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS planning_watchlists(
  id INTEGER PRIMARY KEY AUTOINCREMENT,job_id INTEGER REFERENCES jobs(id),customer_id INTEGER REFERENCES customers(id),
  source_module TEXT,source_event_id TEXT,risk_type TEXT NOT NULL,risk_level TEXT NOT NULL DEFAULT 'medium',due_date TEXT,owner TEXT,
  signal TEXT NOT NULL,action_required TEXT,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ezm_method_plans(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER REFERENCES jobs(id),
  part_id INTEGER REFERENCES parts(id),
  job_number TEXT NOT NULL,
  part_number TEXT NOT NULL,
  revision TEXT NOT NULL,
  customer TEXT,
  quantity REAL NOT NULL DEFAULT 0,
  required_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'DRAFT',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ezm_sources(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id INTEGER NOT NULL REFERENCES ezm_method_plans(id),
  source_type TEXT NOT NULL,
  document_number TEXT NOT NULL,
  revision TEXT,
  sheet TEXT,
  page INTEGER,
  location TEXT,
  note TEXT
);
CREATE TABLE IF NOT EXISTS ezm_operations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plan_id INTEGER NOT NULL REFERENCES ezm_method_plans(id),
  sequence INTEGER NOT NULL,
  work_center TEXT NOT NULL,
  operation TEXT NOT NULL,
  scheduled_date TEXT NOT NULL,
  instruction TEXT NOT NULL,
  inspection_requirement TEXT,
  hold_point INTEGER NOT NULL DEFAULT 0,
  controlled_operation INTEGER NOT NULL DEFAULT 0,
  UNIQUE(plan_id,sequence)
);
CREATE TABLE IF NOT EXISTS ezm_dependencies(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE TABLE IF NOT EXISTS ezm_gdt_characteristics(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
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
CREATE INDEX IF NOT EXISTS ix_ezm_method_job ON ezm_method_plans(job_id,part_id);
CREATE INDEX IF NOT EXISTS ix_ezm_dependency_need_by ON ezm_dependencies(need_by,availability);

CREATE TABLE IF NOT EXISTS purchasing_watchlists(
  id INTEGER PRIMARY KEY AUTOINCREMENT,po_id INTEGER REFERENCES purchase_orders(id),supplier_id INTEGER REFERENCES suppliers(id),
  inventory_item_id INTEGER REFERENCES inventory_items(id),source_event_id TEXT,risk_level TEXT NOT NULL DEFAULT 'medium',need_by_date TEXT,
  owner TEXT,signal TEXT NOT NULL,action_required TEXT,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS morale_pulses(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  department TEXT NOT NULL DEFAULT 'ALL',
  scheduled_headcount INTEGER NOT NULL DEFAULT 0,
  present_headcount INTEGER NOT NULL DEFAULT 0,
  overtime_hours REAL NOT NULL DEFAULT 0,
  over_50_hours_count INTEGER NOT NULL DEFAULT 0,
  exhausted_pto_count INTEGER NOT NULL DEFAULT 0,
  pto_absence_count INTEGER NOT NULL DEFAULT 0,
  sick_absence_clusters INTEGER NOT NULL DEFAULT 0,
  turnover_count INTEGER NOT NULL DEFAULT 0,
  staffing_shortage_count INTEGER NOT NULL DEFAULT 0,
  quality_risk_signal REAL NOT NULL DEFAULT 0,
  risk_score REAL NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'manual',
  notes TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_morale_pulse_period ON morale_pulses(period_end,department);

CREATE TABLE IF NOT EXISTS reward_accounts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_key TEXT NOT NULL UNIQUE,
  display_name TEXT,
  department TEXT,
  vendor_ref TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reward_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL REFERENCES reward_accounts(id),
  event_type TEXT NOT NULL,
  category TEXT NOT NULL,
  points REAL NOT NULL,
  source_module TEXT,
  source_event_id TEXT,
  reason TEXT NOT NULL,
  approved_by TEXT,
  vendor_reference TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_reward_events_account ON reward_events(account_id,created_at);

CREATE TABLE IF NOT EXISTS reward_rules(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,
  source_module TEXT,
  account_payload_key TEXT NOT NULL DEFAULT 'reward_account_id',
  payload_key TEXT,
  operator TEXT NOT NULL DEFAULT 'eq',
  payload_value TEXT,
  category TEXT NOT NULL DEFAULT 'recognition',
  points REAL NOT NULL,
  requires_approval INTEGER NOT NULL DEFAULT 1,
  period_limit_points REAL NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reward_nominations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id INTEGER NOT NULL REFERENCES reward_rules(id),
  source_event_id TEXT NOT NULL,
  account_id INTEGER NOT NULL REFERENCES reward_accounts(id),
  points REAL NOT NULL,
  category TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  reviewed_by TEXT,
  reward_event_id INTEGER REFERENCES reward_events(id),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at TEXT,
  UNIQUE(rule_id,source_event_id,account_id)
);
CREATE INDEX IF NOT EXISTS ix_reward_rules_event ON reward_rules(event_type,active);
CREATE INDEX IF NOT EXISTS ix_reward_nomination_status ON reward_nominations(status,created_at);

CREATE TABLE IF NOT EXISTS training_requirements(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  training_key TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  department TEXT,
  role TEXT,
  recurrence_days INTEGER NOT NULL DEFAULT 0,
  reward_points REAL NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS training_completions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  requirement_id INTEGER NOT NULL REFERENCES training_requirements(id),
  reward_account_id INTEGER REFERENCES reward_accounts(id),
  completed_by TEXT NOT NULL,
  verified_by TEXT NOT NULL,
  completed_on TEXT NOT NULL,
  expires_on TEXT,
  evidence_ref TEXT,
  source_event_id TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS automation_rules(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,
  source_module TEXT,
  payload_key TEXT,
  operator TEXT NOT NULL DEFAULT 'eq',
  payload_value TEXT,
  workflow_key TEXT NOT NULL,
  step_key TEXT NOT NULL,
  target_module TEXT NOT NULL,
  assigned_to TEXT,
  due_days INTEGER NOT NULL DEFAULT 0,
  enabled INTEGER NOT NULL DEFAULT 1,
  priority INTEGER NOT NULL DEFAULT 0,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS automation_rule_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_id INTEGER NOT NULL REFERENCES automation_rules(id),
  source_event_id TEXT NOT NULL,
  workflow_action_id INTEGER REFERENCES workflow_actions(id),
  status TEXT NOT NULL DEFAULT 'executed',
  detail_json TEXT NOT NULL DEFAULT '{}',
  executed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(rule_id,source_event_id)
);
CREATE INDEX IF NOT EXISTS ix_automation_rules_event ON automation_rules(event_type,enabled,priority);

CREATE TABLE IF NOT EXISTS event_delivery_receipts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  handler_key TEXT NOT NULL,
  status TEXT NOT NULL,
  error_text TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(event_id,handler_key)
);
CREATE INDEX IF NOT EXISTS ix_event_delivery_status ON event_delivery_receipts(status,created_at);

CREATE TABLE IF NOT EXISTS module_suggestions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_event_id TEXT NOT NULL,
  correlation_id TEXT,
  source_module TEXT NOT NULL,
  target_module TEXT NOT NULL,
  suggestion_key TEXT NOT NULL,
  title TEXT NOT NULL,
  rationale TEXT NOT NULL,
  recommended_action TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'normal',
  status TEXT NOT NULL DEFAULT 'open',
  entity_type TEXT,
  entity_id TEXT,
  evidence_json TEXT NOT NULL DEFAULT '{}',
  accepted_action_id INTEGER REFERENCES workflow_actions(id),
  reviewed_by TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at TEXT,
  UNIQUE(source_event_id,target_module,suggestion_key)
);
CREATE INDEX IF NOT EXISTS ix_module_suggestion_queue ON module_suggestions(status,target_module,priority,created_at);

-- ISO-Hungry reporting-to-pay backend.
-- Recognition remains the positive event ledger. Cash compensation is a separate,
-- approval-controlled layer so reported events cannot silently become payroll.
CREATE TABLE IF NOT EXISTS iso_hungry_pay_profiles(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reward_account_id INTEGER NOT NULL UNIQUE REFERENCES reward_accounts(id),
  employee_ref TEXT NOT NULL UNIQUE,
  payroll_ref TEXT,
  pay_group TEXT,
  allow_cash_awards INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active',
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_isoh_profile_group ON iso_hungry_pay_profiles(pay_group,status);

CREATE TABLE IF NOT EXISTS iso_hungry_cash_policies(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  reward_category TEXT NOT NULL DEFAULT '*',
  source_module TEXT,
  earning_code TEXT NOT NULL DEFAULT 'ISOH_BONUS',
  currency TEXT NOT NULL DEFAULT 'USD',
  dollars_per_point REAL NOT NULL DEFAULT 0,
  fixed_amount REAL NOT NULL DEFAULT 0,
  max_event_amount REAL NOT NULL DEFAULT 0,
  rolling_30d_limit REAL NOT NULL DEFAULT 0,
  requires_approval INTEGER NOT NULL DEFAULT 1,
  active INTEGER NOT NULL DEFAULT 1,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_isoh_policy_match ON iso_hungry_cash_policies(reward_category,source_module,active);

CREATE TABLE IF NOT EXISTS iso_hungry_earnings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  profile_id INTEGER NOT NULL REFERENCES iso_hungry_pay_profiles(id),
  policy_id INTEGER NOT NULL REFERENCES iso_hungry_cash_policies(id),
  reward_event_id INTEGER NOT NULL REFERENCES reward_events(id),
  source_event_id TEXT,
  points REAL NOT NULL,
  amount REAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'USD',
  earning_code TEXT NOT NULL DEFAULT 'ISOH_BONUS',
  category TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  approved_by TEXT,
  approved_at TEXT,
  rejected_by TEXT,
  rejected_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(profile_id,policy_id,reward_event_id)
);
CREATE INDEX IF NOT EXISTS ix_isoh_earning_status ON iso_hungry_earnings(status,created_at);
CREATE INDEX IF NOT EXISTS ix_isoh_earning_profile ON iso_hungry_earnings(profile_id,created_at);

CREATE TABLE IF NOT EXISTS iso_hungry_pay_batches(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_key TEXT NOT NULL UNIQUE,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  pay_group TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  currency TEXT NOT NULL DEFAULT 'USD',
  item_count INTEGER NOT NULL DEFAULT 0,
  total_amount REAL NOT NULL DEFAULT 0,
  created_by TEXT,
  approved_by TEXT,
  exported_by TEXT,
  payment_reference TEXT,
  export_sha256 TEXT,
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  approved_at TEXT,
  exported_at TEXT,
  paid_at TEXT,
  voided_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_isoh_batch_period ON iso_hungry_pay_batches(period_end,status);

CREATE TABLE IF NOT EXISTS iso_hungry_pay_batch_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL REFERENCES iso_hungry_pay_batches(id),
  earning_id INTEGER NOT NULL UNIQUE REFERENCES iso_hungry_earnings(id),
  profile_id INTEGER NOT NULL REFERENCES iso_hungry_pay_profiles(id),
  employee_ref TEXT NOT NULL,
  payroll_ref TEXT,
  pay_group TEXT,
  earning_code TEXT NOT NULL,
  currency TEXT NOT NULL,
  amount REAL NOT NULL,
  reward_event_id INTEGER NOT NULL,
  source_event_id TEXT,
  category TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_isoh_batch_items_batch ON iso_hungry_pay_batch_items(batch_id,id);

CREATE TABLE IF NOT EXISTS iso_hungry_exceptions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  reward_event_id INTEGER NOT NULL REFERENCES reward_events(id),
  reward_account_id INTEGER NOT NULL REFERENCES reward_accounts(id),
  reason_code TEXT NOT NULL,
  detail TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  resolved_by TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  resolved_at TEXT,
  UNIQUE(reward_event_id,reason_code)
);
CREATE INDEX IF NOT EXISTS ix_isoh_exception_status ON iso_hungry_exceptions(status,created_at);

"""
def init_extensions()->None:
    with db() as con:
        con.executescript(EXTENSION_SCHEMA)
        methods_schema=Path(__file__).resolve().parents[1] / "modules" / "ez_methods" / "schema.sql"
        if methods_schema.exists():
            con.executescript(methods_schema.read_text(encoding="utf-8"))
