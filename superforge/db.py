from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from .runtime_paths import database_path

SCHEMA = r"""
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS system_meta(
  key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,code TEXT,contact TEXT,email TEXT,phone TEXT,
  status TEXT NOT NULL DEFAULT 'active',notes TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS suppliers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,code TEXT,contact TEXT,email TEXT,phone TEXT,
  status TEXT NOT NULL DEFAULT 'active',notes TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS parts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,part_number TEXT NOT NULL UNIQUE,revision TEXT,description TEXT,
  customer_id INTEGER REFERENCES customers(id),status TEXT NOT NULL DEFAULT 'active',notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,job_number TEXT NOT NULL UNIQUE,part_id INTEGER REFERENCES parts(id),
  customer_id INTEGER REFERENCES customers(id),sales_order TEXT,quantity INTEGER,due_date TEXT,status TEXT NOT NULL DEFAULT 'open',
  current_operation TEXT,priority TEXT DEFAULT 'normal',notes TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS purchase_orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT,po_number TEXT NOT NULL UNIQUE,supplier_id INTEGER REFERENCES suppliers(id),
  job_id INTEGER REFERENCES jobs(id),status TEXT NOT NULL DEFAULT 'open',order_date TEXT,required_date TEXT,expected_date TEXT,
  received_date TEXT,total_value REAL,notes TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS inventory_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,item_number TEXT NOT NULL UNIQUE,description TEXT,material_spec TEXT,location TEXT,
  on_hand REAL NOT NULL DEFAULT 0,allocated REAL NOT NULL DEFAULT 0,reorder_point REAL NOT NULL DEFAULT 0,
  supplier_id INTEGER REFERENCES suppliers(id),status TEXT NOT NULL DEFAULT 'active',notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS inventory_transactions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,item_id INTEGER NOT NULL REFERENCES inventory_items(id),job_id INTEGER REFERENCES jobs(id),
  po_id INTEGER REFERENCES purchase_orders(id),txn_type TEXT NOT NULL,quantity REAL NOT NULL,reference TEXT,actor TEXT,notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS clocking_errors(
  id INTEGER PRIMARY KEY AUTOINCREMENT,employee_ref TEXT,job_id INTEGER REFERENCES jobs(id),operation TEXT,error_type TEXT NOT NULL,
  reported_by TEXT,status TEXT NOT NULL DEFAULT 'open',description TEXT NOT NULL,correction TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS machines(
  id INTEGER PRIMARY KEY AUTOINCREMENT,machine_number TEXT NOT NULL UNIQUE,name TEXT NOT NULL,department TEXT,location TEXT,
  criticality TEXT,status TEXT NOT NULL DEFAULT 'active',manufacturer TEXT,model TEXT,serial_number TEXT,notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pm_tasks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,machine_id INTEGER NOT NULL REFERENCES machines(id),task_name TEXT NOT NULL,description TEXT,
  frequency_days INTEGER NOT NULL DEFAULT 30,responsible_role TEXT,safety_notes TEXT,active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS pm_completions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,machine_id INTEGER NOT NULL REFERENCES machines(id),task_id INTEGER NOT NULL REFERENCES pm_tasks(id),
  completed_by TEXT NOT NULL,completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,result TEXT NOT NULL DEFAULT 'pass',notes TEXT
);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY AUTOINCREMENT,document_number TEXT,title TEXT NOT NULL,revision TEXT,document_type TEXT,status TEXT NOT NULL DEFAULT 'draft',
  part_id INTEGER REFERENCES parts(id),job_id INTEGER REFERENCES jobs(id),storage_reference TEXT,sha256 TEXT,notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS document_versions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,document_id INTEGER NOT NULL REFERENCES documents(id),version_number INTEGER NOT NULL,
  revision TEXT,storage_reference TEXT NOT NULL,sha256 TEXT NOT NULL,created_by TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(document_id,version_number)
);
CREATE TABLE IF NOT EXISTS quality_records(
  id INTEGER PRIMARY KEY AUTOINCREMENT,record_type TEXT NOT NULL,record_number TEXT NOT NULL UNIQUE,
  customer_id INTEGER REFERENCES customers(id),supplier_id INTEGER REFERENCES suppliers(id),part_id INTEGER REFERENCES parts(id),
  job_id INTEGER REFERENCES jobs(id),po_id INTEGER REFERENCES purchase_orders(id),machine_id INTEGER REFERENCES machines(id),
  severity TEXT NOT NULL DEFAULT 'unassigned',status TEXT NOT NULL DEFAULT 'open',quantity_affected INTEGER NOT NULL DEFAULT 0,
  quantity_shipped INTEGER NOT NULL DEFAULT 0,description TEXT NOT NULL,containment TEXT,disposition TEXT,root_cause TEXT,
  corrective_action TEXT,preventive_action TEXT,effectiveness TEXT,owner TEXT,due_date TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,closed_at TEXT
);
CREATE TABLE IF NOT EXISTS quality_links(
  id INTEGER PRIMARY KEY AUTOINCREMENT,quality_record_id INTEGER NOT NULL REFERENCES quality_records(id),linked_module TEXT NOT NULL,
  linked_entity_type TEXT NOT NULL,linked_entity_id TEXT NOT NULL,relationship TEXT NOT NULL DEFAULT 'related',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS corrective_actions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,car_number TEXT NOT NULL UNIQUE,quality_record_id INTEGER REFERENCES quality_records(id),
  problem_statement TEXT NOT NULL,why1 TEXT,why2 TEXT,why3 TEXT,why4 TEXT,why5 TEXT,root_cause TEXT,corrective_action TEXT,
  preventive_action TEXT,owner TEXT,root_cause_due TEXT,action_due TEXT,status TEXT NOT NULL DEFAULT 'open',effectiveness_check TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,closed_at TEXT
);
CREATE TABLE IF NOT EXISTS inspections(
  id INTEGER PRIMARY KEY AUTOINCREMENT,inspection_number TEXT NOT NULL UNIQUE,job_id INTEGER REFERENCES jobs(id),part_id INTEGER REFERENCES parts(id),
  quality_record_id INTEGER REFERENCES quality_records(id),inspection_type TEXT NOT NULL,result TEXT,status TEXT NOT NULL DEFAULT 'open',
  inspector TEXT,notes TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT
);
CREATE TABLE IF NOT EXISTS fai_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,fai_number TEXT NOT NULL UNIQUE,job_id INTEGER REFERENCES jobs(id),part_id INTEGER REFERENCES parts(id),
  drawing_document_id INTEGER REFERENCES documents(id),drawing_revision TEXT,status TEXT NOT NULL DEFAULT 'draft',
  characteristic_count INTEGER NOT NULL DEFAULT 0,pass_count INTEGER NOT NULL DEFAULT 0,fail_count INTEGER NOT NULL DEFAULT 0,
  ballooned_pdf TEXT,fai_workbook TEXT,created_by TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT
);
CREATE TABLE IF NOT EXISTS fai_characteristics(
  id INTEGER PRIMARY KEY AUTOINCREMENT,fai_run_id INTEGER NOT NULL REFERENCES fai_runs(id),char_number INTEGER NOT NULL,
  reference_location TEXT,raw_text TEXT,nominal REAL,lsl REAL,usl REAL,actual REAL,characteristic_type TEXT,tooling TEXT,
  result TEXT,notes TEXT,source_metadata TEXT,UNIQUE(fai_run_id,char_number)
);
CREATE TABLE IF NOT EXISTS ppap_packages(
  id INTEGER PRIMARY KEY AUTOINCREMENT,ppap_number TEXT NOT NULL UNIQUE,customer_id INTEGER REFERENCES customers(id),part_id INTEGER REFERENCES parts(id),
  level INTEGER NOT NULL DEFAULT 3,status TEXT NOT NULL DEFAULT 'draft',owner TEXT,submission_date TEXT,approval_date TEXT,notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS kpi_snapshots(
  id INTEGER PRIMARY KEY AUTOINCREMENT,metric_date TEXT NOT NULL,metric_name TEXT NOT NULL,metric_scope TEXT,scope_id TEXT,
  value REAL,unit TEXT,target REAL,status TEXT,source_event_id TEXT,notes TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS event_ledger(
  id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT NOT NULL UNIQUE,parent_event_id TEXT,correlation_id TEXT,event_type TEXT NOT NULL,
  source_module TEXT NOT NULL,target_module TEXT,entity_type TEXT,entity_id TEXT,actor TEXT,reason TEXT,payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'recorded',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_event_ledger_corr ON event_ledger(correlation_id);
CREATE INDEX IF NOT EXISTS ix_event_ledger_entity ON event_ledger(entity_type,entity_id);
CREATE TABLE IF NOT EXISTS workflow_actions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT,workflow_key TEXT NOT NULL,step_key TEXT NOT NULL,source_module TEXT,target_module TEXT,
  entity_type TEXT,entity_id TEXT,assigned_to TEXT,status TEXT NOT NULL DEFAULT 'open',due_date TEXT,input_json TEXT,output_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT
);
CREATE TABLE IF NOT EXISTS learning_observations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,signal_key TEXT NOT NULL,context_json TEXT NOT NULL,outcome TEXT,confidence REAL NOT NULL DEFAULT 0.5,
  source_event_id TEXT,human_rating REAL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS learning_proposals(
  id INTEGER PRIMARY KEY AUTOINCREMENT,proposal_id TEXT NOT NULL UNIQUE,title TEXT NOT NULL,problem_statement TEXT NOT NULL,
  proposed_change TEXT NOT NULL,target_module TEXT NOT NULL,evidence_json TEXT NOT NULL,validation_plan TEXT NOT NULL,rollback_plan TEXT NOT NULL,
  risk_level TEXT NOT NULL DEFAULT 'medium',status TEXT NOT NULL DEFAULT 'proposed',execution_permission TEXT NOT NULL DEFAULT 'proposal_only',
  reviewed_by TEXT,review_notes TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS erp_connections(
  id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,erp_type TEXT NOT NULL DEFAULT 'generic',adapter_type TEXT NOT NULL,
  direction TEXT NOT NULL DEFAULT 'bidirectional',enabled INTEGER NOT NULL DEFAULT 1,config_json TEXT NOT NULL DEFAULT '{}',
  credentials_ref TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS erp_mappings(
  id INTEGER PRIMARY KEY AUTOINCREMENT,connection_id INTEGER NOT NULL REFERENCES erp_connections(id),entity_type TEXT NOT NULL,
  external_field TEXT NOT NULL,internal_field TEXT NOT NULL,transform TEXT,direction TEXT NOT NULL DEFAULT 'in',
  required INTEGER NOT NULL DEFAULT 0,UNIQUE(connection_id,entity_type,external_field,direction)
);
CREATE TABLE IF NOT EXISTS external_refs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,connection_id INTEGER NOT NULL REFERENCES erp_connections(id),entity_type TEXT NOT NULL,
  internal_id TEXT NOT NULL,external_id TEXT NOT NULL,last_seen_at TEXT,last_payload_hash TEXT,
  UNIQUE(connection_id,entity_type,external_id)
);
CREATE TABLE IF NOT EXISTS integration_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,connection_id INTEGER REFERENCES erp_connections(id),run_id TEXT NOT NULL UNIQUE,
  direction TEXT NOT NULL,entity_type TEXT,status TEXT NOT NULL DEFAULT 'running',source_reference TEXT,read_count INTEGER NOT NULL DEFAULT 0,
  applied_count INTEGER NOT NULL DEFAULT 0,skipped_count INTEGER NOT NULL DEFAULT 0,error_count INTEGER NOT NULL DEFAULT 0,
  started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT,summary_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS integration_outbox(
  id INTEGER PRIMARY KEY AUTOINCREMENT,connection_id INTEGER REFERENCES erp_connections(id),event_id TEXT,entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,operation TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,sent_at TEXT
);
CREATE TABLE IF NOT EXISTS sync_conflicts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,connection_id INTEGER REFERENCES erp_connections(id),entity_type TEXT NOT NULL,external_id TEXT,
  internal_id TEXT,conflict_type TEXT NOT NULL,external_json TEXT,internal_json TEXT,status TEXT NOT NULL DEFAULT 'open',
  resolution TEXT,resolved_by TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS user_preferences(
  user_key TEXT PRIMARY KEY,theme_mode TEXT NOT NULL DEFAULT 'dark',accent TEXT NOT NULL DEFAULT '#1F6FBC',
  compact_mode INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR REPLACE INTO system_meta(key,value,updated_at) VALUES('schema_version','1.0.0-unified',CURRENT_TIMESTAMP);
"""

def connect() -> sqlite3.Connection:
    con=sqlite3.connect(database_path(),timeout=30)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con

def init_db() -> None:
    con=connect()
    try:
        con.executescript(SCHEMA)
        con.commit()
    finally:
        con.close()

@contextmanager
def db():
    con=connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
