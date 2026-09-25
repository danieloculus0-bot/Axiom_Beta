from __future__ import annotations

from .db import db

FINANCE_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS finance_accounts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  account_type TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_journals(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  journal_number TEXT NOT NULL UNIQUE,
  entry_date TEXT NOT NULL,
  memo TEXT,
  reference TEXT,
  source_module TEXT,
  source_entity_type TEXT,
  source_entity_id TEXT,
  status TEXT NOT NULL DEFAULT 'posted',
  posted_by TEXT,
  posted_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_finance_journal_date ON finance_journals(entry_date,status);
CREATE INDEX IF NOT EXISTS ix_finance_journal_source ON finance_journals(source_module,source_entity_type,source_entity_id);

CREATE TABLE IF NOT EXISTS finance_journal_lines(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  journal_id INTEGER NOT NULL REFERENCES finance_journals(id),
  line_no INTEGER NOT NULL,
  account_id INTEGER NOT NULL REFERENCES finance_accounts(id),
  description TEXT,
  debit REAL NOT NULL DEFAULT 0,
  credit REAL NOT NULL DEFAULT 0,
  employee_ref TEXT,
  job_ref TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(journal_id,line_no)
);
CREATE INDEX IF NOT EXISTS ix_finance_line_account ON finance_journal_lines(account_id,journal_id);

CREATE TABLE IF NOT EXISTS payroll_employees(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_ref TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  department TEXT,
  pay_type TEXT NOT NULL DEFAULT 'hourly',
  hourly_rate REAL NOT NULL DEFAULT 0,
  annual_salary REAL NOT NULL DEFAULT 0,
  pay_periods_per_year INTEGER NOT NULL DEFAULT 52,
  overtime_multiplier REAL NOT NULL DEFAULT 1.5,
  default_payment_method TEXT NOT NULL DEFAULT 'check',
  status TEXT NOT NULL DEFAULT 'active',
  notes TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_payroll_employee_department ON payroll_employees(department,status);

CREATE TABLE IF NOT EXISTS payroll_runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_key TEXT NOT NULL UNIQUE,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  check_date TEXT NOT NULL,
  pay_group TEXT NOT NULL DEFAULT 'WEEKLY',
  status TEXT NOT NULL DEFAULT 'draft',
  gross_total REAL NOT NULL DEFAULT 0,
  tax_total REAL NOT NULL DEFAULT 0,
  deduction_total REAL NOT NULL DEFAULT 0,
  net_total REAL NOT NULL DEFAULT 0,
  journal_id INTEGER REFERENCES finance_journals(id),
  payment_journal_id INTEGER REFERENCES finance_journals(id),
  payment_reference TEXT,
  payment_method TEXT,
  created_by TEXT,
  approved_by TEXT,
  paid_by TEXT,
  approved_at TEXT,
  paid_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_payroll_run_period ON payroll_runs(period_end,status,pay_group);

CREATE TABLE IF NOT EXISTS payroll_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL REFERENCES payroll_runs(id),
  employee_id INTEGER NOT NULL REFERENCES payroll_employees(id),
  regular_hours REAL NOT NULL DEFAULT 0,
  overtime_hours REAL NOT NULL DEFAULT 0,
  regular_pay REAL NOT NULL DEFAULT 0,
  overtime_pay REAL NOT NULL DEFAULT 0,
  bonus REAL NOT NULL DEFAULT 0,
  gross_pay REAL NOT NULL DEFAULT 0,
  tax_withheld REAL NOT NULL DEFAULT 0,
  other_deductions REAL NOT NULL DEFAULT 0,
  net_pay REAL NOT NULL DEFAULT 0,
  payment_method TEXT NOT NULL DEFAULT 'check',
  payment_reference TEXT,
  notes TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(run_id,employee_id)
);
CREATE INDEX IF NOT EXISTS ix_payroll_item_run ON payroll_items(run_id,status);
CREATE INDEX IF NOT EXISTS ix_payroll_item_employee ON payroll_items(employee_id,run_id);

CREATE TABLE IF NOT EXISTS sheet_books(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  template_type TEXT NOT NULL DEFAULT 'blank',
  columns_json TEXT NOT NULL DEFAULT '[]',
  rows_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'draft',
  posted_entity_type TEXT,
  posted_entity_id TEXT,
  created_by TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_sheet_book_status ON sheet_books(status,template_type,updated_at);
"""

def init_finance_schema() -> None:
    with db() as con:
        con.executescript(FINANCE_SCHEMA)
