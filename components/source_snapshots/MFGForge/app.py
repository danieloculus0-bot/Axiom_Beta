from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

import click
from flask import Flask, abort, flash, g, redirect, render_template_string, request, url_for

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / 'schema.sql'


def field(name: str, label: str, required: bool = False, kind: str = 'text', source_table: str | None = None, label_column: str | None = None) -> dict[str, Any]:
    return {'name': name, 'label': label, 'required': required, 'kind': kind, 'source_table': source_table, 'label_column': label_column}


MODULES: list[dict[str, Any]] = [
    {'area':'Master Data','key':'customers','title':'Customers','table':'customers','description':'Customer master records for ERP, quality, work orders, quoting, and reporting.','fields':[field('name','Customer name',True),field('code','Customer code'),field('contact_name','Contact name'),field('email','Email',False,'email'),field('phone','Phone'),field('notes','Notes',False,'textarea')]},
    {'area':'Master Data','key':'suppliers','title':'Suppliers','table':'suppliers','description':'Supplier master records for purchasing, outside processing, approved material sourcing, material certificates, and supplier risk.','fields':[field('name','Supplier name',True),field('code','Supplier code'),field('contact_name','Contact name'),field('email','Email',False,'email'),field('phone','Phone'),field('notes','Notes',False,'textarea')]},
    {'area':'Master Data','key':'departments','title':'Departments','table':'departments','description':'Shop departments used for scheduling, PM, machine ownership, FPY, quality trends, and morale indicators.','fields':[field('name','Department name',True),field('manager_name','Manager name'),field('notes','Notes',False,'textarea')]},
    {'area':'Master Data','key':'reason-codes','title':'Reason Codes','table':'reason_codes','description':'Editable reason codes for RMAs, NCRs, DMRs, rejects, deviations, and trend reporting.','fields':[field('code','Code',True),field('label','Label',True),field('category','Category',True),field('notes','Notes',False,'textarea')]},
    {'area':'Operating Model','key':'operating-profiles','title':'Operating Profiles','table':'operating_profiles','description':'Shop operating setup profile for JIT, hybrid, or inventory-buffered planning behavior.','fields':[field('profile_name','Profile name',True),field('operating_mode','Operating mode',True),field('planning_horizon_days','Planning horizon days',False,'number'),field('target_inventory_days','Target inventory days',False,'number'),field('purchasing_review_cadence','Purchasing review cadence'),field('lead_time_strategy','Lead time strategy',False,'textarea'),field('notes','Notes',False,'textarea')]},
    {'area':'Production','key':'parts','title':'Parts','table':'parts','description':'Part master foundation for revisions, customer parts, work orders, quoting, material cert traceability, and quality history.','fields':[field('part_number','Part number',True),field('revision','Revision'),field('customer_id','Customer',False,'select','customers','name'),field('description','Description',False,'textarea'),field('notes','Notes',False,'textarea')]},
    {'area':'Production','key':'work-orders','title':'Work Orders','table':'work_orders','description':'Work order tracking for quantity, due dates, customer/part linkage, machine loading, material cert traceability, and quality history.','fields':[field('work_order_number','Work order number',True),field('part_id','Part',False,'select','parts','part_number'),field('customer_id','Customer',False,'select','customers','name'),field('quantity_ordered','Quantity ordered',False,'number'),field('due_date','Due date',False,'date'),field('notes','Notes',False,'textarea')]},
    {'area':'Production','key':'machine-assets','title':'Machine Assets','table':'machine_assets','description':'Machine and work-center assets used to expose capacity, scheduling risk, bottlenecks, and lead-time pressure.','fields':[field('machine_number','Machine number',True),field('name','Machine name',True),field('department_id','Department',False,'select','departments','name'),field('machine_type','Machine type'),field('status','Status'),field('capacity_notes','Capacity notes',False,'textarea')]},
    {'area':'Production','key':'machine-utilization','title':'Machine Utilization','table':'machine_utilization_snapshots','description':'Machine loading snapshots that can push planning and quoting lead times later when capacity is already committed.','fields':[field('machine_asset_id','Machine',False,'select','machine_assets','machine_number'),field('work_order_id','Work order',False,'select','work_orders','work_order_number'),field('period_start','Period start',True,'date'),field('period_end','Period end',True,'date'),field('committed_hours','Committed hours',False,'number'),field('available_hours','Available hours',False,'number'),field('utilization_percent','Utilization percent',False,'number'),field('risk_level','Risk level'),field('impact_notes','Impact notes',False,'textarea')]},
    {'area':'Quality','key':'quality-events','title':'Quality Events','table':'quality_events','description':'RMA, NCR, DMR, CAPA, inspection reject, and customer complaint records tied to customer, part, work order, and reason code.','fields':[field('event_type','Event type',True),field('event_number','Event number',True),field('customer_id','Customer',False,'select','customers','name'),field('part_id','Part',False,'select','parts','part_number'),field('work_order_id','Work order',False,'select','work_orders','work_order_number'),field('reason_code_id','Reason code',False,'select','reason_codes','code'),field('quantity_affected','Quantity affected',False,'number'),field('severity','Severity'),field('description','Description',True,'textarea'),field('containment','Containment',False,'textarea'),field('root_cause','Root cause',False,'textarea'),field('corrective_action','Corrective action',False,'textarea'),field('owner','Owner')]},
    {'area':'Quality','key':'deviations','title':'Deviation Requests','table':'deviations','description':'Controlled deviation requests with reason, risk assessment, approval status, and downstream quality visibility.','fields':[field('deviation_number','Deviation number',True),field('customer_id','Customer',False,'select','customers','name'),field('part_id','Part',False,'select','parts','part_number'),field('work_order_id','Work order',False,'select','work_orders','work_order_number'),field('requested_by','Requested by'),field('reason','Reason',True,'textarea'),field('proposed_disposition','Proposed disposition',False,'textarea'),field('risk_assessment','Risk assessment',False,'textarea')]},
    {'area':'Quality','key':'fpy-summaries','title':'FPY Summaries','table':'fpy_summaries','description':'First-pass yield summaries by time period, department, part, customer, and work center.','fields':[field('period_start','Period start',True,'date'),field('period_end','Period end',True,'date'),field('department_id','Department',False,'select','departments','name'),field('part_id','Part',False,'select','parts','part_number'),field('customer_id','Customer',False,'select','customers','name'),field('work_center','Work center'),field('pieces_started','Pieces started',False,'number'),field('pieces_accepted_first_pass','Pieces accepted first pass',False,'number'),field('reject_count','Reject count',False,'number'),field('rework_count','Rework count',False,'number'),field('summary_notes','Summary notes',False,'textarea')]},
    {'area':'Documents','key':'documents','title':'Documents','table':'documents','description':'Document control foundation for procedures, drawings, specs, and ERP references.','fields':[field('document_number','Document number',True),field('title','Title',True),field('revision','Revision'),field('document_type','Document type',True),field('owner','Owner'),field('storage_reference','Storage reference'),field('notes','Notes',False,'textarea')]},
    {'area':'Maintenance','key':'pm-assets','title':'PM Assets','table':'pm_assets','description':'Preventive maintenance asset register for equipment, PM frequency, and due dates.','fields':[field('asset_number','Asset number',True),field('name','Asset name',True),field('department_id','Department',False,'select','departments','name'),field('asset_type','Asset type'),field('pm_frequency','PM frequency'),field('last_pm_date','Last PM date',False,'date'),field('next_pm_date','Next PM date',False,'date'),field('notes','Notes',False,'textarea')]},
    {'area':'Morale','key':'morale-snapshots','title':'Morale Snapshots','table':'morale_snapshots','description':'Aggregate-only operational strain records tied to QCDSM risk review.','fields':[field('period_start','Period start',True,'date'),field('period_end','Period end',True,'date'),field('department_id','Department',False,'select','departments','name'),field('overtime_hours','Overtime hours',False,'number'),field('exhausted_pto_count','Exhausted PTO count',False,'number'),field('unscheduled_absence_count','Unscheduled absence count',False,'number'),field('unpaid_timeoff_count','Unpaid time off count',False,'number'),field('turnover_count','Turnover count',False,'number'),field('staffing_notes','Staffing notes',False,'textarea'),field('quality_risk_notes','Quality risk notes',False,'textarea')]},
    {'area':'Quoting','key':'materials','title':'Approved Materials','table':'materials','description':'Approved supplier and material catalog for quote material assignment, standard lengths, costs, cert traceability, and lead times.','fields':[field('material_code','Material code',True),field('description','Description',True,'textarea'),field('supplier_id','Supplier',False,'select','suppliers','name'),field('material_category','Material category'),field('stock_form','Stock form'),field('grade_spec','Grade/spec'),field('cost_per_unit','Cost per unit',False,'number'),field('cost_unit','Cost unit'),field('standard_length','Standard length'),field('lead_time_days','Lead time days',False,'number'),field('approval_status','Approval status'),field('notes','Notes',False,'textarea')]},
    {'area':'Quoting','key':'material-certificates','title':'Material Certificates','table':'material_certificates','description':'Dedicated material cert control for heat/lot traceability, supplier linkage, work-order linkage, document references, and review status.','fields':[field('certificate_number','Certificate number'),field('cert_type','Certificate type'),field('material_id','Material',False,'select','materials','material_code'),field('supplier_id','Supplier',False,'select','suppliers','name'),field('work_order_id','Work order',False,'select','work_orders','work_order_number'),field('heat_number','Heat number'),field('lot_number','Lot number'),field('purchase_order_number','Purchase order number'),field('received_date','Received date',False,'date'),field('document_date','Document date',False,'date'),field('storage_reference','Storage reference'),field('review_status','Review status'),field('reviewed_by','Reviewed by'),field('reviewer_notes','Reviewer notes',False,'textarea'),field('notes','Notes',False,'textarea')]},
    {'area':'Quoting','key':'quote-intakes','title':'Quote Intakes','table':'quote_intakes','description':'Customer drawing intake for quoting resources, requirements, due dates, and operating profile context.','fields':[field('quote_number','Quote number',True),field('customer_id','Customer',False,'select','customers','name'),field('operating_profile_id','Operating profile',False,'select','operating_profiles','profile_name'),field('drawing_reference','Drawing reference'),field('intake_status','Intake status'),field('due_date','Due date',False,'date'),field('assigned_to','Assigned to'),field('customer_requirements','Customer requirements',False,'textarea'),field('notes','Notes',False,'textarea')]},
    {'area':'Quoting','key':'pdf-bom-candidates','title':'PDF BOM Candidates','table':'pdf_bom_candidates','description':'Reviewable BOM candidate lines extracted from customer drawing PDFs before controlled use.','fields':[field('quote_intake_id','Quote intake',False,'select','quote_intakes','quote_number'),field('candidate_source','Candidate source'),field('line_text','Extracted line text',True,'textarea'),field('candidate_part_number','Candidate part number'),field('candidate_description','Candidate description',False,'textarea'),field('material_guess','Material guess'),field('quantity_guess','Quantity guess',False,'number'),field('confidence_score','Confidence score',False,'number'),field('review_status','Review status'),field('reviewer_notes','Reviewer notes',False,'textarea')]},
    {'area':'Quoting','key':'bom-reviews','title':'BOM Reviews','table':'bom_reviews','description':'Controlled BOM review gate before extracted or drafted BOM content can be used for quoting.','fields':[field('quote_intake_id','Quote intake',False,'select','quote_intakes','quote_number'),field('review_status','Review status',True),field('reviewed_by','Reviewed by'),field('review_notes','Review notes',False,'textarea'),field('approved_for_quote_at','Approved for quote at',False,'date')]},
    {'area':'Quoting','key':'quote-material-drafts','title':'Quote Material Drafts','table':'quote_material_drafts','description':'Human-reviewed material assignment drafts with cost, pieces required, standard length, and lead-time estimates.','fields':[field('quote_intake_id','Quote intake',False,'select','quote_intakes','quote_number'),field('bom_candidate_id','BOM candidate',False,'select','pdf_bom_candidates','line_text'),field('material_id','Material',False,'select','materials','material_code'),field('assignment_basis','Assignment basis',False,'textarea'),field('standard_length','Standard length'),field('pieces_required','Pieces required',False,'number'),field('estimated_material_cost','Estimated material cost',False,'number'),field('lead_time_days','Lead time days',False,'number'),field('review_status','Review status'),field('reviewer_notes','Reviewer notes',False,'textarea')]},
    {'area':'Supplier Intelligence','key':'supplier-performance','title':'Supplier Performance','table':'supplier_performance_snapshots','description':'Supplier lead-time and quality snapshots that feed quoting, purchasing risk, and company pulse calculations.','fields':[field('supplier_id','Supplier',False,'select','suppliers','name'),field('period_start','Period start',True,'date'),field('period_end','Period end',True,'date'),field('quoted_lead_time_days','Quoted lead time days',False,'number'),field('actual_average_lead_time_days','Actual average lead time days',False,'number'),field('late_delivery_count','Late delivery count',False,'number'),field('quality_issue_count','Quality issue count',False,'number'),field('risk_level','Risk level'),field('impact_notes','Impact notes',False,'textarea')]},
    {'area':'Planning','key':'planning-watchlists','title':'Planning Watchlists','table':'planning_watchlists','description':'Planning and lead-time watchlists for work orders, customers, risks, and required action.','fields':[field('work_order_id','Work order',False,'select','work_orders','work_order_number'),field('customer_id','Customer',False,'select','customers','name'),field('watch_type','Watch type',True),field('risk_level','Risk level'),field('due_date','Due date',False,'date'),field('owner','Owner'),field('signal','Signal',True,'textarea'),field('action_required','Action required',False,'textarea')]},
    {'area':'Purchasing','key':'purchasing-watchlists','title':'Purchasing Watchlists','table':'purchasing_watchlists','description':'Material and supplier purchasing watchlists for need dates, lead-time risk, and buyer action.','fields':[field('supplier_id','Supplier',False,'select','suppliers','name'),field('material_id','Material',False,'select','materials','material_code'),field('need_by_date','Need by date',False,'date'),field('quantity_needed','Quantity needed',False,'number'),field('risk_level','Risk level'),field('buyer_owner','Buyer owner'),field('signal','Signal',True,'textarea'),field('action_required','Action required',False,'textarea')]},
    {'area':'Performance','key':'operator-efficiency-baselines','title':'Operator Efficiency Baselines','table':'operator_efficiency_baselines','description':'Privacy-aware operator or group efficiency baselines for throughput, planned hours, and actual hours.','fields':[field('period_start','Period start',True,'date'),field('period_end','Period end',True,'date'),field('department_id','Department',False,'select','departments','name'),field('operator_group','Operator group'),field('baseline_type','Baseline type',True),field('planned_hours','Planned hours',False,'number'),field('actual_hours','Actual hours',False,'number'),field('throughput_count','Throughput count',False,'number'),field('privacy_notes','Privacy notes',False,'textarea')]},
    {'area':'Performance','key':'quoting-throughput-baselines','title':'Quoting Throughput Baselines','table':'quoting_throughput_baselines','description':'Quote throughput baseline snapshots for quoting load, drawing intake, BOM candidates, and cycle time.','fields':[field('period_start','Period start',True,'date'),field('period_end','Period end',True,'date'),field('customer_id','Customer',False,'select','customers','name'),field('quote_count','Quote count',False,'number'),field('drawing_intake_count','Drawing intake count',False,'number'),field('bom_candidate_count','BOM candidate count',False,'number'),field('average_cycle_days','Average cycle days',False,'number'),field('bottleneck_notes','Bottleneck notes',False,'textarea')]},
    {'area':'Dashboard','key':'dashboard-metric-snapshots','title':'Dashboard Metric Snapshots','table':'dashboard_metric_snapshots','description':'Dashboard metric snapshots for quality, delivery, purchasing, morale, quoting, FPY, and production performance.','fields':[field('metric_date','Metric date',True,'date'),field('metric_area','Metric area',True),field('metric_name','Metric name',True),field('metric_value','Metric value',False,'number'),field('metric_unit','Metric unit'),field('context_notes','Context notes',False,'textarea')]},
]
MODULE_BY_KEY = {module['key']: module for module in MODULES}
AREAS = list(dict.fromkeys(module['area'] for module in MODULES))

BASE = """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>{{ title }}</title><style>:root{color-scheme:dark;--bg:#0b1117;--panel:#111b24;--panel2:#162331;--line:#263747;--text:#e6edf3;--muted:#91a4b7;--accent:#66a3ff;--good:#77d68a;--warn:#ffd166;--bad:#ff7b72}*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;grid-template-columns:300px 1fr;background:radial-gradient(circle at top left,#16263d 0,var(--bg) 46%);color:var(--text);font-family:Inter,Segoe UI,system-ui,sans-serif}.sidebar{border-right:1px solid var(--line);background:#090f16;padding:22px;position:sticky;top:0;height:100vh;overflow:auto}.brand{display:flex;gap:14px;align-items:center;margin-bottom:24px}.mark{width:48px;height:48px;border:1px solid var(--line);border-radius:14px;display:grid;place-items:center;background:linear-gradient(145deg,#17283a,#0d1620);color:var(--accent);font-weight:900}h1,h2,h3,p{margin-top:0}h1{font-size:1.25rem;margin-bottom:2px}p,.muted,.brand p,.card p,.panel p,.hero p,.page-head p{color:var(--muted)}.nav-area{margin:18px 0 8px;color:var(--accent);font-size:.72rem;text-transform:uppercase;letter-spacing:.13em;font-weight:900}nav{display:grid;gap:7px}nav a,.button{color:var(--text);text-decoration:none;border:1px solid var(--line);background:var(--panel);border-radius:10px;padding:9px 11px;font-weight:750}nav a:hover,.button:hover,.card:hover{border-color:var(--accent)}.content{padding:32px}.hero,.page-head,.panel,.card,.qcard,.signal{border:1px solid var(--line);background:rgba(17,27,36,.9);border-radius:18px;box-shadow:0 20px 40px rgba(0,0,0,.18)}.hero,.page-head{padding:28px;margin-bottom:20px}.hero h2,.page-head h2{font-size:clamp(2rem,4vw,3.4rem);margin-bottom:10px;letter-spacing:-.04em}.eyebrow{color:var(--accent);text-transform:uppercase;letter-spacing:.12em;font-size:.78rem;font-weight:900}.grid,.qgrid,.policy,.signals{display:grid;gap:14px;margin-bottom:20px}.grid{grid-template-columns:repeat(auto-fill,minmax(270px,1fr))}.qgrid{grid-template-columns:repeat(5,minmax(0,1fr))}.policy,.signals{grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}.area-title{margin:28px 0 12px;color:var(--text);font-size:1.1rem}.qcard,.card,.panel,.signal{padding:18px}.qcard span,.count,.score{color:var(--accent);font-size:1.8rem;font-weight:900}.card{display:block;color:var(--text);text-decoration:none;min-height:150px}.card small,.badge{display:inline-block;color:var(--good);border:1px solid var(--line);border-radius:999px;padding:3px 8px;margin-bottom:10px;font-size:.72rem}.badge.warn{color:var(--warn)}.badge.bad{color:var(--bad)}.page-head{display:flex;justify-content:space-between;gap:20px;align-items:center}table{width:100%;border-collapse:collapse;font-size:.9rem}th,td{text-align:left;border-bottom:1px solid var(--line);padding:10px;vertical-align:top;max-width:340px;overflow-wrap:anywhere}th{color:var(--muted);text-transform:capitalize;font-size:.78rem}.empty{padding:38px;text-align:center;border:1px dashed var(--line);border-radius:14px}.form{display:grid;gap:16px;max-width:940px}.form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}.wide{grid-column:1/-1}label{display:grid;gap:6px;color:var(--muted);font-weight:700}label em{color:var(--accent);font-style:normal;font-size:.8rem}input,textarea,select{width:100%;border:1px solid var(--line);border-radius:10px;background:#071019;color:var(--text);padding:11px 12px;font:inherit}textarea{min-height:112px;resize:vertical}.actions{display:flex;gap:10px}.msg{border:1px solid var(--line);border-radius:10px;padding:10px 12px;background:var(--panel);margin-bottom:8px}.signal strong{display:block;margin-bottom:6px}.signal ul{margin:10px 0 0;padding-left:18px;color:var(--muted)}@media(max-width:980px){body{grid-template-columns:1fr}.sidebar{position:static;height:auto}.qgrid,.policy{grid-template-columns:1fr}.page-head{display:grid}}</style></head><body><aside class='sidebar'><div class='brand'><div class='mark'>MF</div><div><h1>MFGForge</h1><p>Manufacturing ERP</p></div></div><nav><a href='{{ url_for('dashboard') }}'>Command Center</a><a href='{{ url_for('company_pulse') }}'>Company Pulse</a>{% for area in areas %}<div class='nav-area'>{{ area }}</div>{% for nav_module in modules if nav_module.area == area %}<a href='{{ url_for('list_records', module_key=nav_module.key) }}'>{{ nav_module.title }}</a>{% endfor %}{% endfor %}<div class='nav-area'>Governance</div><a href='{{ url_for('ai_policy') }}'>AI Policy</a></nav></aside><main class='content'>{% with messages=get_flashed_messages(with_categories=true) %}{% if messages %}<section>{% for category,message in messages %}<div class='msg {{ category }}'>{{ message }}</div>{% endfor %}</section>{% endif %}{% endwith %}{{ body|safe }}</main></body></html>"""


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(SECRET_KEY=os.environ.get('MFGFORGE_SECRET_KEY', 'dev-change-me'), DATABASE=os.environ.get('MFGFORGE_DATABASE', str(Path(app.instance_path) / 'mfgforge.sqlite')))
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    register_routes(app)
    with app.app_context():
        ensure_database()
    return app


def get_db() -> sqlite3.Connection:
    if 'db' not in g:
        from flask import current_app
        database_path = Path(current_app.config['DATABASE'])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(database_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db


def close_db(error: Exception | None = None) -> None:
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = get_db()
    db.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))
    db.commit()


def ensure_database() -> None:
    existing = get_db().execute("SELECT name FROM sqlite_master WHERE type='table' AND name='system_meta'").fetchone()
    if existing is None:
        init_db()


@click.command('init-db')
def init_db_command() -> None:
    init_db()
    click.echo('Initialized MFGForge database.')


def scalar(sql: str, args: tuple[Any, ...] = ()) -> float:
    row = get_db().execute(sql, args).fetchone()
    value = row[0] if row else 0
    return 0 if value is None else value


def table_count(table_name: str) -> int:
    return int(scalar(f'SELECT COUNT(*) FROM {table_name}'))


def insert_record(table_name: str, values: dict[str, Any]) -> int:
    columns = ', '.join(values.keys())
    placeholders = ', '.join('?' for _ in values)
    cursor = get_db().execute(f'INSERT INTO {table_name} ({columns}) VALUES ({placeholders})', list(values.values()))
    get_db().commit()
    return int(cursor.lastrowid)


def get_select_options(module: dict[str, Any]) -> dict[str, list[sqlite3.Row]]:
    options: dict[str, list[sqlite3.Row]] = {}
    for item in module['fields']:
        if item['kind'] != 'select':
            continue
        rows = get_db().execute(f"SELECT id, {item['label_column']} AS label FROM {item['source_table']} ORDER BY {item['label_column']} LIMIT 500").fetchall()
        options[item['name']] = rows
    return options


def build_company_pulse() -> dict[str, Any]:
    open_quality = int(scalar("SELECT COUNT(*) FROM quality_events WHERE status != 'closed'"))
    open_deviations = int(scalar("SELECT COUNT(*) FROM deviations WHERE status != 'closed'"))
    certs_needing_review = int(scalar("SELECT COUNT(*) FROM material_certificates WHERE review_status IN ('needs_review','draft','hold')"))
    bom_needing_review = int(scalar("SELECT COUNT(*) FROM pdf_bom_candidates WHERE review_status IN ('needs_review','draft')"))
    quote_drafts = int(scalar("SELECT COUNT(*) FROM quote_material_drafts WHERE review_status IN ('draft','needs_review')"))
    purchasing_risks = int(scalar("SELECT COUNT(*) FROM purchasing_watchlists WHERE status != 'closed' AND risk_level IN ('high','critical')"))
    planning_risks = int(scalar("SELECT COUNT(*) FROM planning_watchlists WHERE status != 'closed' AND risk_level IN ('high','critical')"))
    supplier_risks = int(scalar("SELECT COUNT(*) FROM supplier_performance_snapshots WHERE risk_level IN ('high','critical')"))
    machine_risks = int(scalar("SELECT COUNT(*) FROM machine_utilization_snapshots WHERE risk_level IN ('high','critical') OR utilization_percent >= 90"))
    avg_supplier_delay = float(scalar("SELECT AVG(actual_average_lead_time_days - quoted_lead_time_days) FROM supplier_performance_snapshots WHERE actual_average_lead_time_days IS NOT NULL AND quoted_lead_time_days IS NOT NULL"))
    avg_machine_utilization = float(scalar("SELECT AVG(utilization_percent) FROM machine_utilization_snapshots WHERE utilization_percent IS NOT NULL"))
    morale_strain = int(scalar("SELECT COALESCE(SUM(exhausted_pto_count),0)+COALESCE(SUM(unscheduled_absence_count),0)+COALESCE(SUM(unpaid_timeoff_count),0)+COALESCE(SUM(turnover_count),0) FROM morale_snapshots"))
    fpy_rows = int(scalar("SELECT COUNT(*) FROM fpy_summaries"))
    fpy_percent = float(scalar("SELECT 100.0 * SUM(pieces_accepted_first_pass) / NULLIF(SUM(pieces_started),0) FROM fpy_summaries")) if fpy_rows else 0
    risk_score = min(100, open_quality*8 + open_deviations*7 + certs_needing_review*4 + bom_needing_review*3 + quote_drafts*3 + purchasing_risks*10 + planning_risks*10 + supplier_risks*8 + machine_risks*8 + max(0, int(avg_supplier_delay))*3 + morale_strain*2)
    if risk_score >= 70:
        status = 'Critical operational pressure'
        badge = 'bad'
    elif risk_score >= 35:
        status = 'Watch closely'
        badge = 'warn'
    else:
        status = 'Stable with normal controls'
        badge = 'good'
    return {
        'risk_score': risk_score,
        'status': status,
        'badge': badge,
        'signals': [
            {'title':'Quality load','badge':'bad' if open_quality else 'good','value':open_quality,'unit':'open quality events','details':[f'{open_deviations} open deviations', 'RMA/NCR/DMR/CAPA remain tied to customers, parts, work orders, and reason codes.']},
            {'title':'Material cert control','badge':'bad' if certs_needing_review else 'good','value':certs_needing_review,'unit':'certs needing review','details':['Heat, lot, supplier, material, work order, and storage references are tracked.', 'Unreviewed certs should block quiet confidence in material traceability.']},
            {'title':'Quote and BOM gate','badge':'warn' if bom_needing_review or quote_drafts else 'good','value':bom_needing_review + quote_drafts,'unit':'quote review items','details':[f'{bom_needing_review} PDF BOM candidates need review', f'{quote_drafts} material assignment drafts need review']},
            {'title':'Supplier lead-time pressure','badge':'bad' if supplier_risks else ('warn' if avg_supplier_delay > 0 else 'good'),'value':round(avg_supplier_delay,1),'unit':'avg days over quoted lead time','details':[f'{supplier_risks} high/critical supplier snapshots', 'Supplier lateness should feed material assignment and quote lead-time assumptions.']},
            {'title':'Machine capacity pressure','badge':'bad' if machine_risks else ('warn' if avg_machine_utilization >= 80 else 'good'),'value':round(avg_machine_utilization,1),'unit':'avg utilization percent','details':[f'{machine_risks} machine capacity risk signals', 'High utilization should push promised lead times later unless capacity is freed.']},
            {'title':'Morale and staffing strain','badge':'warn' if morale_strain else 'good','value':morale_strain,'unit':'aggregate strain count','details':['Uses department-level aggregate indicators only.', 'Overtime, PTO exhaustion, absence, unpaid time off, and turnover are operational risk inputs.']},
            {'title':'First-pass yield','badge':'warn' if fpy_rows and fpy_percent < 95 else 'good','value':round(fpy_percent,1),'unit':'percent FPY','details':[f'{fpy_rows} FPY summary rows', 'FPY should trend by department, part, customer, and work center.']},
            {'title':'Planning and purchasing watchlists','badge':'bad' if planning_risks or purchasing_risks else 'good','value':planning_risks + purchasing_risks,'unit':'high-risk watchlist items','details':[f'{planning_risks} high-risk planning items', f'{purchasing_risks} high-risk purchasing items']},
        ]
    }


def page(title: str, body: str) -> str:
    return render_template_string(BASE, title=title, modules=MODULES, areas=AREAS, body=body)


def register_routes(app: Flask) -> None:
    @app.get('/')
    def dashboard() -> str:
        counts = {module['key']: table_count(module['table']) for module in MODULES}
        pulse = build_company_pulse()
        body = render_template_string("""<section class='hero'><p class='eyebrow'>QCDSM ERP Foundation</p><h2>Manufacturing command center</h2><p>MFGForge connects quality, quoting, planning, purchasing, production, maintenance, documents, materials, machines, suppliers, and morale signals into one controlled manufacturing system.</p><p><a class='button' href='{{ url_for('company_pulse') }}'>Open Company Pulse</a></p></section><section class='qgrid'><article class='qcard'><span>Q</span><strong>Quality</strong><p>RMA, NCR, DMR, CAPA, FPY, deviations, certs, and reason-code trends.</p></article><article class='qcard'><span>C</span><strong>Cost</strong><p>Materials, quote drafts, supplier drift, throughput baselines, and machine utilization.</p></article><article class='qcard'><span>D</span><strong>Delivery</strong><p>Work orders, planning watchlists, lead-time risk, supplier risk, and purchasing constraints.</p></article><article class='qcard'><span>S</span><strong>Safety</strong><p>Controlled records, review gates, traceability, and audit-ready approvals.</p></article><article class='qcard'><span>M</span><strong>Morale</strong><p>Aggregate department strain indicators tied to operational risk.</p></article></section><section class='panel'><p class='eyebrow'>Current pulse</p><h3>{{ pulse.status }}</h3><p><span class='score'>{{ pulse.risk_score }}</span> / 100 compiled operational risk score from quality, certs, quoting, supplier, machine, planning, purchasing, FPY, and morale signals.</p></section>{% for area in areas %}<h2 class='area-title'>{{ area }}</h2><section class='grid'>{% for module in modules if module.area == area %}<a class='card' href='{{ url_for('list_records', module_key=module.key) }}'><small>{{ module.area }}</small><span class='count'>{{ counts[module.key] }}</span><h3>{{ module.title }}</h3><p>{{ module.description }}</p></a>{% endfor %}</section>{% endfor %}""", modules=MODULES, areas=AREAS, counts=counts, pulse=pulse)
        return page('MFGForge Command Center', body)

    @app.get('/company-pulse')
    def company_pulse() -> str:
        pulse = build_company_pulse()
        body = render_template_string("""<section class='page-head'><div><p class='eyebrow'>Company Pulse</p><h2>Manufacturing X-ray</h2><p>Cross-module operational intelligence compiled from live ERP records. This is the first logic layer: it does not guess from thin air, it reads the company record graph and exposes pressure points.</p></div><span class='badge {{ pulse.badge }}'>{{ pulse.status }}</span></section><section class='panel'><h3>Compiled risk score</h3><p><span class='score'>{{ pulse.risk_score }}</span> / 100</p><p>The score increases when open quality events, deviations, unreviewed material certs, unreviewed BOM/quote drafts, supplier lateness, high machine utilization, planning/purchasing risks, FPY weakness, or aggregate morale strain rise.</p></section><section class='signals'>{% for signal in pulse.signals %}<article class='signal'><span class='badge {{ signal.badge }}'>{{ signal.badge }}</span><strong>{{ signal.title }}</strong><p><span class='score'>{{ signal.value }}</span> {{ signal.unit }}</p><ul>{% for item in signal.details %}<li>{{ item }}</li>{% endfor %}</ul></article>{% endfor %}</section>""", pulse=pulse)
        return page('Company Pulse | MFGForge', body)

    @app.get('/records/<module_key>')
    def list_records(module_key: str) -> str:
        if module_key not in MODULE_BY_KEY:
            abort(404)
        module = MODULE_BY_KEY[module_key]
        rows = get_db().execute(f"SELECT * FROM {module['table']} ORDER BY id DESC LIMIT 100").fetchall()
        body = render_template_string("""<section class='page-head'><div><p class='eyebrow'>{{ module.area }} records</p><h2>{{ module.title }}</h2><p>{{ module.description }}</p></div><a class='button' href='{{ url_for('create_record', module_key=module.key) }}'>New Record</a></section><section class='panel'>{% if rows %}<table><thead><tr>{% for key in rows[0].keys() %}<th>{{ key.replace('_',' ') }}</th>{% endfor %}</tr></thead><tbody>{% for row in rows %}<tr>{% for key in row.keys() %}<td>{{ row[key] }}</td>{% endfor %}</tr>{% endfor %}</tbody></table>{% else %}<div class='empty'><h3>No records yet.</h3><p>This module is ready for real records. No fake demo data has been inserted.</p></div>{% endif %}</section>""", module=module, rows=rows)
        return page(f"{module['title']} | MFGForge", body)

    @app.route('/records/<module_key>/new', methods=('GET', 'POST'))
    def create_record(module_key: str) -> str:
        if module_key not in MODULE_BY_KEY:
            abort(404)
        module = MODULE_BY_KEY[module_key]
        select_options = get_select_options(module)
        if request.method == 'POST':
            values: dict[str, Any] = {}
            errors: list[str] = []
            for item in module['fields']:
                value = request.form.get(item['name'], '').strip()
                if item['required'] and not value:
                    errors.append(f"{item['label']} is required.")
                if value:
                    values[item['name']] = int(value) if item['kind'] == 'select' else value
            if module['table'] == 'quality_events' and 'severity' not in values:
                values['severity'] = 'unassigned'
            if errors:
                for error in errors:
                    flash(error, 'error')
            else:
                insert_record(module['table'], values)
                flash(f"{module['title']} record created.", 'success')
                return redirect(url_for('list_records', module_key=module['key']))
        body = render_template_string("""<section class='page-head'><div><p class='eyebrow'>Create {{ module.area }} record</p><h2>New {{ module.title }}</h2><p>{{ module.description }}</p></div></section><form class='panel form' method='post'><div class='form-grid'>{% for item in module.fields %}<label class='{% if item.kind == 'textarea' %}wide{% endif %}'><span>{{ item.label }}{% if item.required %} <em>required</em>{% endif %}</span>{% if item.kind == 'textarea' %}<textarea name='{{ item.name }}' {% if item.required %}required{% endif %}></textarea>{% elif item.kind == 'select' %}<select name='{{ item.name }}'><option value=''>No linked record</option>{% for option in select_options[item.name] %}<option value='{{ option.id }}'>{{ option.label }}</option>{% endfor %}</select>{% else %}<input type='{{ item.kind }}' name='{{ item.name }}' {% if item.required %}required{% endif %}>{% endif %}</label>{% endfor %}</div><div class='actions'><button class='button' type='submit'>Save record</button><a class='button' href='{{ url_for('list_records', module_key=module.key) }}'>Cancel</a></div></form>""", module=module, select_options=select_options)
        return page(f"New {module['title']} | MFGForge", body)

    @app.get('/ai-policy')
    def ai_policy() -> str:
        body = """<section class='page-head'><div><p class='eyebrow'>Human-in-the-loop</p><h2>AI acts like GPS, not a self-driving car.</h2><p>AI assistance may analyze, draft, summarize, and recommend. Business-critical execution requires human approval and audit logging.</p></div></section><section class='policy'><article class='panel'><h3>Allowed assistance</h3><p>Summarize trends, draft quality language, flag risks, explain records, suggest next actions, extract BOM candidates for review, compile pulse metrics, and prepare reports from approved data.</p></article><article class='panel'><h3>Approval required</h3><p>Closing quality records, changing inventory, releasing jobs, approving deviations, approving BOM reviews, approving material certs, assigning quote materials, or sending external communications.</p></article><article class='panel'><h3>Audit path</h3><p>Read-only analysis, draft recommendation, human approval, logged execution, and traceable review history.</p></article></section>"""
        return page('AI Policy | MFGForge', body)


if __name__ == '__main__':
    create_app().run(debug=True)
