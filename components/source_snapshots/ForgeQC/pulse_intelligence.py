from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from html import escape

from flask import Response, redirect, request

import forgeqc_app
from forgeqc_app import (
    AttendanceMoraleMetric,
    OperationClockSummary,
    RMA,
    WorkOrder,
    db,
    fpy,
    log,
    morale_score,
    page,
)
from quality_forms import CorrectiveAction, DeviationRequest, NonconformanceRecord
from quality_workflow import ppm_metrics, workflow_counts


class MetricSnapshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    snapshot_date = db.Column(db.Date, default=date.today, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    metric_key = db.Column(db.String(120), nullable=False, index=True)
    metric_name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(80), default='Quality')
    value = db.Column(db.Float, default=0)
    numerator = db.Column(db.Float, default=0)
    denominator = db.Column(db.Float, default=0)
    target = db.Column(db.Float, default=0)
    unit = db.Column(db.String(40), default='count')
    severity = db.Column(db.String(40), default='Normal')
    notes = db.Column(db.Text)


class QualitySignal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    signal_date = db.Column(db.Date, default=date.today, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    source_area = db.Column(db.String(80), default='Pulse')
    metric_key = db.Column(db.String(120))
    severity = db.Column(db.String(40), default='Info')
    title = db.Column(db.String(220), nullable=False)
    explanation = db.Column(db.Text)
    recommendation = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)


def h(value):
    return escape(str(value or ''), quote=True)


def sev(value, target=0, warn=0, bad=0, lower_is_better=True):
    if lower_is_better:
        if bad and value >= bad:
            return 'Critical'
        if warn and value >= warn:
            return 'Warning'
        return 'Good'
    if value <= bad:
        return 'Critical'
    if value <= warn:
        return 'Warning'
    return 'Good'


def upsert_metric(day, key, name, category, value, numerator=0, denominator=0, target=0, unit='count', severity='Normal', notes=''):
    row = MetricSnapshot.query.filter_by(snapshot_date=day, metric_key=key).first()
    if not row:
        row = MetricSnapshot(snapshot_date=day, metric_key=key)
        db.session.add(row)
    row.metric_name = name
    row.category = category
    row.value = round(float(value or 0), 3)
    row.numerator = round(float(numerator or 0), 3)
    row.denominator = round(float(denominator or 0), 3)
    row.target = round(float(target or 0), 3)
    row.unit = unit
    row.severity = severity
    row.notes = notes
    return row


def add_signal(severity, title, explanation, recommendation, metric_key='quality_pulse', source_area='Pulse'):
    db.session.add(QualitySignal(
        signal_date=date.today(),
        source_area=source_area,
        metric_key=metric_key,
        severity=severity,
        title=title,
        explanation=explanation,
        recommendation=recommendation,
        is_active=True,
    ))


def status_open(model):
    return model.query.filter(model.status.notin_(['Closed', 'Resolved', 'Cancelled'])).count()


def recent_date_filter(query, field, cutoff):
    return query.filter(field != None).filter(field >= cutoff)


def compute_pulse_snapshot(days=30):
    today = date.today()
    cutoff = today - timedelta(days=days)
    QualitySignal.query.filter_by(is_active=True).update({'is_active': False})

    rma_recent = recent_date_filter(RMA.query, RMA.date_opened, cutoff).count()
    rma_open = RMA.query.filter(RMA.status != 'Closed').count()
    ncr_open = NonconformanceRecord.query.filter(NonconformanceRecord.status != 'Closed').count()
    deviation_open = DeviationRequest.query.filter(DeviationRequest.status.notin_(['Closed', 'Rejected'])).count()
    high_dev = DeviationRequest.query.filter(DeviationRequest.status != 'Closed', DeviationRequest.risk_level.in_(['High', 'Critical'])).count()
    overdue_car = CorrectiveAction.query.filter(CorrectiveAction.status != 'Closed', CorrectiveAction.due_date != None, CorrectiveAction.due_date < today).count()
    open_high_quality = ncr_open + high_dev + overdue_car

    clock_rows = recent_date_filter(OperationClockSummary.query, OperationClockSummary.period_date, cutoff).all()
    good = sum(r.first_pass_good_qty or 0 for r in clock_rows)
    rework = sum(r.rework_qty or 0 for r in clock_rows)
    scrap = sum(r.scrap_qty or 0 for r in clock_rows)
    fpy_value = fpy(good, rework, scrap)

    morale_rows = recent_date_filter(AttendanceMoraleMetric.query, AttendanceMoraleMetric.period_date, cutoff).all()
    morale_values = [morale_score(m) for m in morale_rows]
    morale_pressure = round(sum(morale_values) / len(morale_values), 1) if morale_values else 0

    wo_open = WorkOrder.query.filter(WorkOrder.status != 'Closed').count()
    wo_past_due = WorkOrder.query.filter(WorkOrder.status != 'Closed', WorkOrder.due_date != None, WorkOrder.due_date < today).count()
    ppm = ppm_metrics(days)
    workflow = workflow_counts()

    repeated_parts = Counter()
    for r in recent_date_filter(RMA.query, RMA.date_opened, cutoff).all():
        if r.part_number:
            repeated_parts[r.part_number] += 1
    for n in recent_date_filter(NonconformanceRecord.query, NonconformanceRecord.date_opened, cutoff).all():
        if n.part_number:
            repeated_parts[n.part_number] += 1
    repeat_count = sum(1 for _, count in repeated_parts.items() if count >= 2)

    upsert_metric(today, 'rma_recent', f'RMAs Last {days} Days', 'Customer Quality', rma_recent, target=0, unit='count', severity=sev(rma_recent, warn=3, bad=6))
    upsert_metric(today, 'rma_open', 'Open RMAs', 'Customer Quality', rma_open, target=0, unit='count', severity=sev(rma_open, warn=3, bad=8))
    upsert_metric(today, 'ncr_open', 'Open NCR / DMR Records', 'Internal Quality', ncr_open, target=0, unit='count', severity=sev(ncr_open, warn=5, bad=12))
    upsert_metric(today, 'deviation_open', 'Open Deviations', 'Risk Control', deviation_open, target=0, unit='count', severity=sev(deviation_open, warn=4, bad=10))
    upsert_metric(today, 'high_risk_deviation', 'High-Risk Deviations', 'Risk Control', high_dev, target=0, unit='count', severity=sev(high_dev, warn=1, bad=3))
    upsert_metric(today, 'overdue_car', 'Overdue Corrective Actions', 'Corrective Action', overdue_car, target=0, unit='count', severity=sev(overdue_car, warn=1, bad=4))
    upsert_metric(today, 'fpy_recent', f'FPY Last {days} Days', 'Production Quality', fpy_value, numerator=good, denominator=good + rework + scrap, target=98, unit='%', severity=sev(fpy_value, warn=95, bad=90, lower_is_better=False))
    upsert_metric(today, 'morale_pressure', 'Morale Pressure Index', 'Morale / Capacity', morale_pressure, target=15, unit='score', severity=sev(morale_pressure, warn=18, bad=35))
    upsert_metric(today, 'work_orders_past_due', 'Past Due Work Orders', 'Delivery Risk', wo_past_due, target=0, unit='count', severity=sev(wo_past_due, warn=3, bad=8))
    upsert_metric(today, 'repeat_part_risk', 'Repeat Part Risk Families', 'Pattern Detection', repeat_count, target=0, unit='count', severity=sev(repeat_count, warn=1, bad=3))
    ppm_note = f"PPM denominator: {ppm['units']} tracked operation units from FPY clocking during the last {days} days. Customer shipped-quantity denominator is not yet connected."
    upsert_metric(today, 'ncr_ppm_recent', f'NCR PPM Last {days} Days', 'Internal Quality', ppm['ncr_ppm'], numerator=ppm['ncr_qty'], denominator=ppm['units'], target=0, unit='PPM', severity='Good' if ppm['ncr_ppm'] == 0 else 'Warning', notes=ppm_note)
    upsert_metric(today, 'rma_ppm_recent', f'RMA PPM Last {days} Days', 'Customer Quality', ppm['rma_ppm'], numerator=ppm['rma_qty'], denominator=ppm['units'], target=0, unit='PPM', severity='Good' if ppm['rma_ppm'] == 0 else 'Warning', notes=ppm_note)
    upsert_metric(today, 'quality_actions_overdue', 'Overdue Quality Actions', 'Expedite', workflow['overdue'], target=0, unit='count', severity=sev(workflow['overdue'], warn=1, bad=4))
    upsert_metric(today, 'quality_actions_unassigned', 'Unassigned Quality Actions', 'Expedite', workflow['unassigned'], target=0, unit='count', severity=sev(workflow['unassigned'], warn=1, bad=4))

    if overdue_car:
        add_signal('Critical' if overdue_car >= 4 else 'Warning', 'Corrective actions are overdue', f'{overdue_car} corrective action(s) are past due.', 'Review overdue CARs first. Close completed actions or update due dates with owner accountability.', 'overdue_car', 'Corrective Action')
    if high_dev:
        add_signal('Critical' if high_dev >= 3 else 'Warning', 'High-risk deviations are active', f'{high_dev} high or critical deviation request(s) are still open.', 'Review customer approval status and final disposition before shipment.', 'high_risk_deviation', 'Deviation')
    if repeat_count:
        top = ', '.join(f'{part} ({count})' for part, count in repeated_parts.most_common(5) if count >= 2)
        add_signal('Critical' if repeat_count >= 3 else 'Warning', 'Repeat defect pattern detected', f'Repeat part families in the last {days} days: {top}.', 'Open a targeted corrective action or inspect the control plan for these part families.', 'repeat_part_risk', 'Pattern Detection')
    if fpy_value and fpy_value < 95:
        add_signal('Warning' if fpy_value >= 90 else 'Critical', 'First pass yield is below target', f'Recent FPY is {fpy_value}% against a 98% target.', 'Drill into operation clocking by department and part family. Look for rework or scrap concentration.', 'fpy_recent', 'Production Quality')
    if morale_pressure >= 18:
        add_signal('Critical' if morale_pressure >= 35 else 'Warning', 'Morale pressure is elevated', f'Morale pressure index is {morale_pressure}.', 'Compare overtime, absence, and staffing shortage periods against defect spikes before blaming operators.', 'morale_pressure', 'Morale / Capacity')
    if wo_open and wo_past_due / max(wo_open, 1) >= 0.25:
        add_signal('Warning', 'Past due work order load is high', f'{wo_past_due} of {wo_open} open work orders are past due.', 'Check material shortages, overcapacity departments, and quality hold impact.', 'work_orders_past_due', 'Delivery Risk')
    if workflow['overdue']:
        add_signal('Critical' if workflow['overdue'] >= 4 else 'Warning', 'Quality actions are overdue', f"{workflow['overdue']} NCR/RMA/deviation/CAR workflow item(s) are past due.", 'Open Quality Expedite and update ownership, next action, due date, or closure evidence.', 'quality_actions_overdue', 'Expedite')
    if workflow['unassigned']:
        add_signal('Warning', 'Quality actions are unassigned', f"{workflow['unassigned']} open quality workflow item(s) do not have an owner.", 'Assign an accountable owner and next action in Quality Expedite.', 'quality_actions_unassigned', 'Expedite')

    if not QualitySignal.query.filter_by(is_active=True).count():
        add_signal('Good', 'No major quality pulse alarms', 'Current tracked indicators are inside the configured warning bands.', 'Keep collecting snapshots. The intelligence gets better as history builds.', 'quality_pulse', 'Pulse')

    log('Pulse', 'Snapshot generated', f'{days} day lookback')
    db.session.commit()


def range_days():
    raw = request.args.get('days', '90')
    if raw == 'all':
        return 3650
    try:
        return max(7, min(int(raw), 3650))
    except ValueError:
        return 90


def metric_series(days):
    cutoff = date.today() - timedelta(days=days)
    rows = MetricSnapshot.query.filter(MetricSnapshot.snapshot_date >= cutoff).order_by(MetricSnapshot.snapshot_date).all()
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.metric_key].append(row)
    return grouped


def svg_line(rows, width=360, height=120):
    if not rows:
        return f"<svg viewBox='0 0 {width} {height}'><text x='14' y='64' fill='#98aabd'>No history yet</text></svg>"
    values = [r.value or 0 for r in rows]
    hi = max(values) if max(values) != min(values) else max(values) + 1
    lo = min(values)
    pad = 12
    pts = []
    for idx, val in enumerate(values):
        x = pad + (idx / max(len(values) - 1, 1)) * (width - pad * 2)
        y = height - pad - ((val - lo) / max(hi - lo, 1)) * (height - pad * 2)
        pts.append(f'{round(x,1)},{round(y,1)}')
    end = values[-1]
    return f"<svg viewBox='0 0 {width} {height}' class='pulse-chart'><polyline points='{' '.join(pts)}' fill='none' stroke='currentColor' stroke-width='3'/><text x='14' y='22' fill='currentColor'>{h(rows[-1].metric_name)}</text><text x='14' y='{height-14}' fill='#98aabd'>{h(end)} {h(rows[-1].unit)}</text></svg>"


def card(row, series_rows):
    badge = row.severity.lower()
    suffix = '%' if row.unit == '%' else (f' {row.unit}' if row.unit and row.unit != 'count' else '')
    return f"<div class='card pulse-card {badge}'><span>{h(row.category)}</span><b>{h(row.value)}{h(suffix)}</b><div class='muted'>{h(row.metric_name)}</div>{svg_line(series_rows, 320, 100)}</div>"


def signal_table():
    rows = ''.join(
        f"<tr><td><span class='badge {h(s.severity.lower())}'>{h(s.severity)}</span></td><td>{h(s.source_area)}</td><td><b>{h(s.title)}</b><br><span class='muted'>{h(s.explanation)}</span></td><td>{h(s.recommendation)}</td></tr>"
        for s in QualitySignal.query.filter_by(is_active=True).order_by(QualitySignal.created_at.desc()).limit(20)
    )
    return f"<section><h2>Live Quality Signals</h2><table><tr><th>Severity</th><th>Area</th><th>Signal</th><th>Recommended Action</th></tr>{rows}</table></section>"


def install_nav():
    if "href='/pulse'" not in forgeqc_app.BASE:
        forgeqc_app.BASE = forgeqc_app.BASE.replace("<a href='/'>Dashboard</a>", "<a href='/'>Dashboard</a><a href='/pulse'>Quality Pulse</a>")
    if 'pulse-card' not in forgeqc_app.CSS:
        forgeqc_app.CSS += """
        .pulse-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:14px}.pulse-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}.pulse-card{min-height:230px}.pulse-card.good{border-color:#2d6948}.pulse-card.warning{border-color:#7a622d}.pulse-card.critical{border-color:#723a3a}.pulse-chart{width:100%;height:100px;margin-top:10px;color:#8ed2ff}.print-only{display:none}@media print{aside,.pulse-toolbar,.ctx-menu{display:none!important}main{margin:0;padding:0;max-width:none}.card,section{break-inside:avoid;box-shadow:none}.print-only{display:block}}
        """


def register(app):
    install_nav()

    @app.route('/pulse', methods=['GET'])
    def pulse_dashboard():
        if MetricSnapshot.query.count() == 0:
            compute_pulse_snapshot(30)
        days = range_days()
        series = metric_series(days)
        latest = []
        for key, rows in series.items():
            if rows:
                latest.append(rows[-1])
        latest.sort(key=lambda r: (0 if r.severity == 'Critical' else 1 if r.severity == 'Warning' else 2, r.category, r.metric_name))
        cards = ''.join(card(row, series.get(row.metric_key, [])) for row in latest)
        controls = """
        <div class='pulse-toolbar'><form method='get'><button name='days' value='7'>7D</button><button name='days' value='30'>30D</button><button name='days' value='90'>90D</button><button name='days' value='365'>1Y</button><button name='days' value='all'>All</button></form><form method='post' action='/pulse/snapshot'><button>Generate Snapshot Now</button></form><a class='btn' href='/pulse/export.csv'>Export CSV</a><button onclick='window.print()'>Print Dashboard</button></div>
        """
        body = f"<div class='print-only'><h2>ForgeQC Quality Pulse Report</h2><p>{date.today()}</p></div><div class='notice'>Quality Pulse watches the system like a dashboard gauge cluster: trend memory, risk signals, repeat-pattern detection, and recommended action.</div>{controls}<div class='pulse-grid'>{cards}</div><br>{signal_table()}"
        return page('Quality Pulse', body)

    @app.route('/pulse/snapshot', methods=['POST'])
    def pulse_snapshot():
        compute_pulse_snapshot(30)
        return redirect('/pulse')

    @app.route('/pulse/export.csv')
    def pulse_export():
        rows = MetricSnapshot.query.order_by(MetricSnapshot.snapshot_date.desc(), MetricSnapshot.metric_key).all()
        lines = ['snapshot_date,metric_key,metric_name,category,value,numerator,denominator,target,unit,severity,notes']
        for r in rows:
            vals = [r.snapshot_date, r.metric_key, r.metric_name, r.category, r.value, r.numerator, r.denominator, r.target, r.unit, r.severity, (r.notes or '').replace('\n', ' ')]
            lines.append(','.join('"' + h(v).replace('"', '""') + '"' for v in vals))
        return Response('\n'.join(lines), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=forgeqc_quality_pulse.csv'})
