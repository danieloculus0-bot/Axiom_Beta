from datetime import datetime
from html import escape

from flask import redirect, request

import forgeqc_app
from forgeqc_app import as_int, db, log, page
from quality_forms import CorrectiveAction, DeviationRequest, NonconformanceRecord, next_form_number


class FiveWhyAnalysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    analysis_number = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(80), default='Draft')
    source_type = db.Column(db.String(80), default='Internal')
    car_id = db.Column(db.Integer, db.ForeignKey('corrective_action.id'))
    ncr_dmr_id = db.Column(db.Integer, db.ForeignKey('nonconformance_record.id'))
    deviation_id = db.Column(db.Integer, db.ForeignKey('deviation_request.id'))
    problem_statement = db.Column(db.Text)
    why_1 = db.Column(db.Text)
    why_2 = db.Column(db.Text)
    why_3 = db.Column(db.Text)
    why_4 = db.Column(db.Text)
    why_5 = db.Column(db.Text)
    final_root_cause = db.Column(db.Text)
    root_cause_category = db.Column(db.String(120))
    suggested_category = db.Column(db.String(120))
    containment_suggestion = db.Column(db.Text)
    corrective_action_suggestion = db.Column(db.Text)
    preventive_action_suggestion = db.Column(db.Text)
    effectiveness_check_suggestion = db.Column(db.Text)
    logic_notes = db.Column(db.Text)
    notes = db.Column(db.Text)

    car = db.relationship('CorrectiveAction')
    ncr_dmr = db.relationship('NonconformanceRecord')
    deviation = db.relationship('DeviationRequest')


def h(value):
    return escape(str(value or ''), quote=True)


def selected(value, expected):
    return 'selected' if str(value or '') == str(expected or '') else ''


def text_blob(row):
    return ' '.join(str(x or '') for x in [row.problem_statement, row.why_1, row.why_2, row.why_3, row.why_4, row.why_5, row.final_root_cause]).lower()


RULES = [
    {
        'category': 'Document Control / Drawing Clarity',
        'terms': ['drawing', 'print', 'revision', 'rev', 'spec', 'watermark', 'reference', 'pdf', 'wrong document', 'outdated'],
        'containment': 'Verify the active drawing/specification revision for affected jobs, quarantine questionable product, and confirm whether shipped product used the correct revision.',
        'corrective': 'Create or correct the controlled internal drawing/work instruction, remove uncontrolled reference documents from the workflow, and require revision verification before release.',
        'preventive': 'Add revision-control checks to order entry, traveler release, and first-article setup so obsolete or reference-only documents cannot drive production.',
        'effectiveness': 'Audit the next three jobs for this customer/part family and confirm the controlled revision matches the traveler, inspection plan, and shop packet.',
    },
    {
        'category': 'Process Control / Missing Step',
        'terms': ['missing', 'missed', 'forgot', 'omitted', 'skip', 'skipped', 'not installed', 'left off', 'no check', 'pem', 'hardware'],
        'containment': 'Inspect all affected WIP, finished goods, and staged shipments for the missing feature or step before release.',
        'corrective': 'Add a defined verification point, visual aid, checklist item, or poka-yoke so the step cannot be easily missed.',
        'preventive': 'Tie the critical step to first-part inspection, in-process verification, or operator signoff based on risk and repeat history.',
        'effectiveness': 'Review the next five lots for recurrence and confirm the verification point was completed with evidence.',
    },
    {
        'category': 'Inspection / Gauge Control',
        'terms': ['inspection', 'inspected', 'gage', 'gauge', 'measurement', 'measured', 'calibration', 'calibrated', 'dimension', 'tolerance'],
        'containment': 'Confirm measurement method, gauge status, and inspection results for affected product. Reinspect using a known-good calibrated gauge.',
        'corrective': 'Clarify the inspection method, gauge requirement, sample frequency, and acceptance criteria in the inspection plan.',
        'preventive': 'Add expired-gauge blocking, inspection-plan review, or first-article verification for critical characteristics.',
        'effectiveness': 'Compare follow-up inspection records against the updated plan and verify no repeat escapes for the same characteristic.',
    },
    {
        'category': 'Training / Workmanship Standard',
        'terms': ['training', 'trained', 'new operator', 'operator', 'workmanship', 'understood', 'knowledge', 'skill'],
        'containment': 'Verify current operators understand the requirement and inspect recent output from the same process or work center.',
        'corrective': 'Create focused retraining tied to the actual defect, with signoff and objective evidence of understanding.',
        'preventive': 'Update onboarding, visual standards, and layered checks so the requirement is learned before production release.',
        'effectiveness': 'Observe the process after retraining and verify sustained conforming output over multiple jobs or shifts.',
    },
    {
        'category': 'Equipment / Tooling Condition',
        'terms': ['machine', 'tool', 'fixture', 'wear', 'worn', 'maintenance', 'setup', 'program', 'laser', 'brake', 'machining'],
        'containment': 'Hold affected parts from the same setup, tool, fixture, or machine until setup condition is verified.',
        'corrective': 'Correct the fixture/tool/program/setup issue and record the verified setup condition before restarting production.',
        'preventive': 'Add PM, setup verification, tool-life tracking, or fixture validation for the failure mode.',
        'effectiveness': 'Track first-pass results from the corrected setup and compare against prior defect trend for the same process.',
    },
    {
        'category': 'Supplier / Purchased Product',
        'terms': ['supplier', 'vendor', 'purchase', 'purchased', 'material', 'cert', 'certificate', 'wrong material', 'mcmaster'],
        'containment': 'Quarantine affected purchased material/product, verify certs and labels, and inspect remaining supplier lots.',
        'corrective': 'Issue supplier corrective action or update receiving inspection requirements for the affected supplier/material family.',
        'preventive': 'Add supplier scorecard monitoring, approved supplier controls, and incoming verification based on risk and history.',
        'effectiveness': 'Review the next three receipts from the supplier for the same issue and verify no repeat nonconformance.',
    },
    {
        'category': 'Packaging / Shipping Protection',
        'terms': ['shipping', 'packaging', 'packaged', 'damage', 'forklift', 'carrier', 'freight', 'pallet', 'box'],
        'containment': 'Inspect staged and recently shipped product for similar shipping or handling damage and verify packaging adequacy.',
        'corrective': 'Update packaging method, handling instruction, palletization, or carrier/customer handoff requirement.',
        'preventive': 'Add packaging validation, photo evidence, or shipping checklist for high-risk products and routes.',
        'effectiveness': 'Track damage claims and customer feedback for the next shipment cycle using the updated packaging method.',
    },
    {
        'category': 'Capacity / Planning Pressure',
        'terms': ['rush', 'hot', 'late', 'overtime', 'short staffed', 'shortage', 'capacity', 'expedite', 'schedule'],
        'containment': 'Review rushed or expedited jobs for skipped checks, incomplete documentation, and open quality holds before shipment.',
        'corrective': 'Define minimum quality gates that cannot be bypassed during schedule pressure or expedite conditions.',
        'preventive': 'Add quality-risk review to hot-job release and monitor overtime/capacity pressure against defect trends.',
        'effectiveness': 'Compare defect rate for expedited jobs before and after the new quality gate rule.',
    },
]


def analyze(row):
    blob = text_blob(row)
    scored = []
    for rule in RULES:
        score = sum(1 for term in rule['terms'] if term in blob)
        if score:
            scored.append((score, rule))
    rule = sorted(scored, key=lambda x: x[0], reverse=True)[0][1] if scored else {
        'category': 'General System Control',
        'containment': 'Contain affected product, define the known risk, and verify whether any product has escaped.',
        'corrective': 'Correct the failed system condition rather than assigning blame to a person. Define owner, due date, and objective evidence.',
        'preventive': 'Add a control that prevents recurrence or makes the failure visible before shipment.',
        'effectiveness': 'Verify the issue does not recur over a defined sample of future jobs, lots, or time period.',
    }
    whys = [row.why_1, row.why_2, row.why_3, row.why_4, row.why_5]
    complete = sum(1 for why in whys if str(why or '').strip())
    flags = []
    if not row.problem_statement or len(row.problem_statement.strip()) < 20:
        flags.append('Problem statement is thin. Include what failed, where found, quantity/risk, and requirement not met.')
    if complete < 5:
        flags.append(f'Only {complete} Why level(s) completed. Continue until the answer points to a controllable system cause.')
    if any(term in blob for term in ['careless', 'lazy', 'operator error', 'human error', 'forgot']):
        flags.append('Watch the blame trap. Convert people-blame language into system controls, training evidence, mistake-proofing, or verification gaps.')
    if row.final_root_cause and len(row.final_root_cause.strip()) < 25:
        flags.append('Final root cause may be too short to audit. State the failed control and why the system allowed it.')
    if not flags:
        flags.append('Logic check passed for a draft. Verify evidence before closure.')
    row.suggested_category = rule['category']
    row.root_cause_category = row.root_cause_category or rule['category']
    row.containment_suggestion = rule['containment']
    row.corrective_action_suggestion = rule['corrective']
    row.preventive_action_suggestion = rule['preventive']
    row.effectiveness_check_suggestion = rule['effectiveness']
    row.logic_notes = '\n'.join(flags)


def car_options(selected_id=None):
    opts = "<option value=''></option>"
    for row in CorrectiveAction.query.order_by(CorrectiveAction.car_number):
        label = f'{row.car_number} | {row.status} | {row.owner or ""}'
        opts += f"<option value='{row.id}' {selected(selected_id, row.id)}>{h(label)}</option>"
    return opts


def ncr_options(selected_id=None):
    opts = "<option value=''></option>"
    for row in NonconformanceRecord.query.order_by(NonconformanceRecord.record_number):
        label = f'{row.record_number} | {row.record_type} | {row.part_number or ""}'
        opts += f"<option value='{row.id}' {selected(selected_id, row.id)}>{h(label)}</option>"
    return opts


def deviation_options(selected_id=None):
    opts = "<option value=''></option>"
    for row in DeviationRequest.query.order_by(DeviationRequest.request_number):
        label = f'{row.request_number} | {row.status} | {row.part_number or ""}'
        opts += f"<option value='{row.id}' {selected(selected_id, row.id)}>{h(label)}</option>"
    return opts


def apply_form(row):
    row.analysis_number = request.form.get('analysis_number') or row.analysis_number
    row.status = request.form.get('status') or 'Draft'
    row.source_type = request.form.get('source_type') or 'Internal'
    row.car_id = as_int(request.form.get('car_id'), None)
    row.ncr_dmr_id = as_int(request.form.get('ncr_dmr_id'), None)
    row.deviation_id = as_int(request.form.get('deviation_id'), None)
    row.problem_statement = request.form.get('problem_statement')
    row.why_1 = request.form.get('why_1')
    row.why_2 = request.form.get('why_2')
    row.why_3 = request.form.get('why_3')
    row.why_4 = request.form.get('why_4')
    row.why_5 = request.form.get('why_5')
    row.final_root_cause = request.form.get('final_root_cause')
    row.root_cause_category = request.form.get('root_cause_category')
    row.notes = request.form.get('notes')
    analyze(row)


def five_why_form(row):
    body = f"""
    <div class='notice'>Controlled 5-Why helper. It suggests likely root-cause categories and action language, but humans still approve the real corrective action. Good, because software with an ego is how bullshit escapes get immortalized.</div>
    <section><form method='post' class='form'>
    <label>Analysis Number<input name='analysis_number' value='{h(row.analysis_number)}' required></label>
    <label>Status<select name='status'><option {selected(row.status,'Draft')}>Draft</option><option {selected(row.status,'In Review')}>In Review</option><option {selected(row.status,'Approved')}>Approved</option><option {selected(row.status,'Closed')}>Closed</option></select></label>
    <label>Source Type<select name='source_type'><option {selected(row.source_type,'Internal')}>Internal</option><option {selected(row.source_type,'RMA')}>RMA</option><option {selected(row.source_type,'NCR / DMR')}>NCR / DMR</option><option {selected(row.source_type,'Deviation')}>Deviation</option><option {selected(row.source_type,'Audit')}>Audit</option><option {selected(row.source_type,'Customer')}>Customer</option></select></label>
    <label>Linked Corrective Action<select name='car_id'>{car_options(row.car_id)}</select></label>
    <label>Linked NCR / DMR<select name='ncr_dmr_id'>{ncr_options(row.ncr_dmr_id)}</select></label>
    <label>Linked Deviation<select name='deviation_id'>{deviation_options(row.deviation_id)}</select></label>
    <label class='wide'>Problem Statement<textarea name='problem_statement'>{h(row.problem_statement)}</textarea></label>
    <label class='wide'>Why 1<textarea name='why_1'>{h(row.why_1)}</textarea></label>
    <label class='wide'>Why 2<textarea name='why_2'>{h(row.why_2)}</textarea></label>
    <label class='wide'>Why 3<textarea name='why_3'>{h(row.why_3)}</textarea></label>
    <label class='wide'>Why 4<textarea name='why_4'>{h(row.why_4)}</textarea></label>
    <label class='wide'>Why 5<textarea name='why_5'>{h(row.why_5)}</textarea></label>
    <label class='wide'>Final Root Cause<textarea name='final_root_cause'>{h(row.final_root_cause)}</textarea></label>
    <label>Root Cause Category<input name='root_cause_category' value='{h(row.root_cause_category)}'></label>
    <label class='wide'>Notes<textarea name='notes'>{h(row.notes)}</textarea></label>
    <div class='wide'><button name='action' value='analyze'>Analyze + Save</button> <button name='action' value='save'>Save</button> <a class='btn' href='/five-whys'>Back</a></div>
    </form></section>
    <br><section><h2>Assistant Suggestions</h2><table><tr><th>Area</th><th>Suggestion</th></tr>
    <tr><td>Suggested Category</td><td>{h(row.suggested_category)}</td></tr>
    <tr><td>Logic Notes</td><td><pre>{h(row.logic_notes)}</pre></td></tr>
    <tr><td>Containment</td><td>{h(row.containment_suggestion)}</td></tr>
    <tr><td>Corrective Action</td><td>{h(row.corrective_action_suggestion)}</td></tr>
    <tr><td>Preventive Action</td><td>{h(row.preventive_action_suggestion)}</td></tr>
    <tr><td>Effectiveness Check</td><td>{h(row.effectiveness_check_suggestion)}</td></tr>
    </table></section>
    """
    return page('5-Why / CAPA Assistant', body)


def install_nav():
    if "href='/five-whys'" not in forgeqc_app.BASE:
        forgeqc_app.BASE = forgeqc_app.BASE.replace("<a href='/quality-forms'>Quality Forms</a>", "<a href='/quality-forms'>Quality Forms</a><a href='/five-whys'>5-Why Assistant</a>")
    if 'pre{white-space:pre-wrap' not in forgeqc_app.CSS:
        forgeqc_app.CSS += "pre{white-space:pre-wrap;margin:0;color:#d7e5f2;font-family:Segoe UI,Arial,sans-serif}.logic-panel td:first-child{width:190px}"


def register(app):
    install_nav()

    @app.route('/capa-assistant')
    def capa_assistant_home():
        open_cars = CorrectiveAction.query.filter(CorrectiveAction.status != 'Closed').count()
        open_why = FiveWhyAnalysis.query.filter(FiveWhyAnalysis.status != 'Closed').count()
        weak = FiveWhyAnalysis.query.filter((FiveWhyAnalysis.logic_notes == None) | (FiveWhyAnalysis.logic_notes.like('%Only%'))).count()
        cards = ''.join([
            f"<div class='card'><span>Open Corrective Actions</span><b>{open_cars}</b><a class='btn' href='/corrective-actions'>Open CARs</a></div>",
            f"<div class='card'><span>Open 5-Why Analyses</span><b>{open_why}</b><a class='btn' href='/five-whys'>Open 5-Whys</a></div>",
            f"<div class='card'><span>Drafts Needing Logic Review</span><b>{weak}</b><a class='btn' href='/five-whys'>Review</a></div>",
        ])
        return page('CAPA Assistant', f"<div class='notice'>CAPA Assistant watches corrective-action quality: thin problem statements, incomplete Why chains, blame traps, and missing effectiveness logic.</div><div class='cards'>{cards}</div>")

    @app.route('/five-whys', methods=['GET', 'POST'])
    def five_whys():
        if request.method == 'POST':
            row = FiveWhyAnalysis(analysis_number=request.form.get('analysis_number') or next_form_number(FiveWhyAnalysis, 'analysis_number', 'WHY'))
            apply_form(row)
            db.session.add(row); log('5Why', 'Saved', row.analysis_number); db.session.commit()
            return redirect(f'/five-whys/{row.id}')
        blank = FiveWhyAnalysis(analysis_number=next_form_number(FiveWhyAnalysis, 'analysis_number', 'WHY'))
        analyze(blank)
        rows = ''.join(
            f"<tr><td><a href='/five-whys/{r.id}'>{h(r.analysis_number)}</a></td><td>{h(r.status)}</td><td>{h(r.source_type)}</td><td>{h(r.suggested_category)}</td><td>{h((r.problem_statement or '')[:110])}</td></tr>"
            for r in FiveWhyAnalysis.query.order_by(FiveWhyAnalysis.id.desc()).limit(200)
        )
        return page('5-Why Analyses', five_why_form(blank).split('<main><h1>5-Why / CAPA Assistant</h1>', 1)[-1].rsplit('</main>', 1)[0] + f"<br><section><h2>5-Why Log</h2><table><tr><th>Number</th><th>Status</th><th>Source</th><th>Suggested Category</th><th>Problem</th></tr>{rows}</table></section>")

    @app.route('/five-whys/<int:row_id>', methods=['GET', 'POST'])
    def five_why_detail(row_id):
        row = FiveWhyAnalysis.query.get_or_404(row_id)
        if request.method == 'POST':
            apply_form(row)
            log('5Why', 'Updated', row.analysis_number)
            db.session.commit()
            return redirect(f'/five-whys/{row.id}')
        analyze(row)
        return five_why_form(row)
