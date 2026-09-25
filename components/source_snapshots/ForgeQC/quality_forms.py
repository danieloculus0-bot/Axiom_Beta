from datetime import datetime
from html import escape

from flask import redirect, request

import forgeqc_app
from quality_workflow import after_quality_save, workflow_link
from forgeqc_app import (
    Customer,
    Department,
    ReasonCode,
    WorkOrder,
    as_int,
    db,
    get_or_create,
    log,
    page,
    parse_date,
)


class DeviationRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_number = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    request_date = db.Column(db.Date)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'))
    ncr_dmr_id = db.Column(db.Integer, db.ForeignKey('nonconformance_record.id'))
    part_number = db.Column(db.String(160))
    revision = db.Column(db.String(80))
    quantity_affected = db.Column(db.Integer, default=0)
    deviation_type = db.Column(db.String(120), default='Use As Is')
    requested_by = db.Column(db.String(160))
    reason = db.Column(db.Text)
    proposed_disposition = db.Column(db.Text)
    risk_level = db.Column(db.String(40), default='Medium')
    customer_approval_required = db.Column(db.Boolean, default=False)
    customer_approval_status = db.Column(db.String(80), default='Not Required')
    internal_approver = db.Column(db.String(160))
    approval_date = db.Column(db.Date)
    status = db.Column(db.String(80), default='Draft')
    final_disposition = db.Column(db.Text)
    notes = db.Column(db.Text)

    customer = db.relationship('Customer')
    work_order = db.relationship('WorkOrder')


class NonconformanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_number = db.Column(db.String(80), unique=True, nullable=False)
    record_type = db.Column(db.String(40), default='NCR')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    date_opened = db.Column(db.Date)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    reason_code_id = db.Column(db.Integer, db.ForeignKey('reason_code.id'))
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'))
    deviation_id = db.Column(db.Integer, db.ForeignKey('deviation_request.id'))
    part_number = db.Column(db.String(160))
    revision = db.Column(db.String(80))
    quantity_affected = db.Column(db.Integer, default=0)
    defect_description = db.Column(db.Text)
    containment_action = db.Column(db.Text)
    disposition = db.Column(db.String(120), default='Review Needed')
    disposition_notes = db.Column(db.Text)
    disposition_owner = db.Column(db.String(160))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(80), default='Open')
    notes = db.Column(db.Text)

    customer = db.relationship('Customer')
    department = db.relationship('Department')
    reason_code = db.relationship('ReasonCode')
    work_order = db.relationship('WorkOrder')
    deviation = db.relationship('DeviationRequest', foreign_keys=[deviation_id])


class CorrectiveAction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    car_number = db.Column(db.String(80), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    date_opened = db.Column(db.Date)
    source_type = db.Column(db.String(80), default='Internal')
    ncr_dmr_id = db.Column(db.Integer, db.ForeignKey('nonconformance_record.id'))
    deviation_id = db.Column(db.Integer, db.ForeignKey('deviation_request.id'))
    owner = db.Column(db.String(160))
    problem_statement = db.Column(db.Text)
    containment_action = db.Column(db.Text)
    root_cause = db.Column(db.Text)
    corrective_action = db.Column(db.Text)
    preventive_action = db.Column(db.Text)
    due_date = db.Column(db.Date)
    completed_date = db.Column(db.Date)
    effectiveness_check = db.Column(db.Text)
    status = db.Column(db.String(80), default='Open')
    notes = db.Column(db.Text)

    ncr_dmr = db.relationship('NonconformanceRecord')
    deviation = db.relationship('DeviationRequest')


def h(value):
    return escape(str(value or ''), quote=True)


def d(value):
    return value.isoformat() if value else ''


def selected(value, expected):
    return 'selected' if str(value or '') == str(expected or '') else ''


def checked(value):
    return 'checked' if value else ''


def next_form_number(model, field, prefix):
    year = datetime.utcnow().year
    count = model.query.filter(getattr(model, field).like(f'{prefix}-{year}-%')).count() + 1
    return f'{prefix}-{year}-{count:04d}'


def customer_options(selected_id=None):
    opts = "<option value=''></option>"
    for row in Customer.query.filter_by(active=True).order_by(Customer.name):
        opts += f"<option value='{row.id}' {selected(selected_id, row.id)}>{h(row.name)}</option>"
    return opts


def department_options(selected_id=None):
    opts = "<option value=''></option>"
    for row in Department.query.filter_by(active=True).order_by(Department.name):
        opts += f"<option value='{row.id}' {selected(selected_id, row.id)}>{h(row.name)}</option>"
    return opts


def reason_options(selected_id=None):
    opts = "<option value=''></option>"
    for row in ReasonCode.query.filter_by(active=True).order_by(ReasonCode.name):
        opts += f"<option value='{row.id}' {selected(selected_id, row.id)}>{h(row.name)}</option>"
    return opts


def work_order_options(selected_id=None):
    opts = "<option value=''></option>"
    for row in WorkOrder.query.order_by(WorkOrder.work_order_number):
        opts += f"<option value='{row.id}' {selected(selected_id, row.id)}>{h(row.work_order_number)} | {h(row.part_number)}</option>"
    return opts


def deviation_options(selected_id=None):
    opts = "<option value=''></option>"
    for row in DeviationRequest.query.order_by(DeviationRequest.request_number):
        label = f'{row.request_number} | {row.part_number or ""}'
        opts += f"<option value='{row.id}' {selected(selected_id, row.id)}>{h(label)}</option>"
    return opts


def ncr_options(selected_id=None):
    opts = "<option value=''></option>"
    for row in NonconformanceRecord.query.order_by(NonconformanceRecord.record_number):
        label = f'{row.record_number} | {row.record_type} | {row.part_number or ""}'
        opts += f"<option value='{row.id}' {selected(selected_id, row.id)}>{h(label)}</option>"
    return opts


def install_nav():
    if "/quality-forms" not in forgeqc_app.BASE:
        forgeqc_app.BASE = forgeqc_app.BASE.replace("<a href='/rma'>RMA</a>", "<a href='/rma'>RMA</a><a href='/quality-forms'>Quality Forms</a>")


def deviation_form(row):
    body = f"""
    <section><form method='post' class='form'>
    <label>Deviation Number<input name='request_number' value='{h(row.request_number)}' required></label>
    <label>Request Date<input name='request_date' type='date' value='{d(row.request_date)}'></label>
    <label>Status<select name='status'><option {selected(row.status,'Draft')}>Draft</option><option {selected(row.status,'Submitted')}>Submitted</option><option {selected(row.status,'Approved')}>Approved</option><option {selected(row.status,'Rejected')}>Rejected</option><option {selected(row.status,'Closed')}>Closed</option></select></label>
    <label>Customer<select name='customer_id'>{customer_options(row.customer_id)}</select></label>
    <label>Work Order<select name='work_order_id'>{work_order_options(row.work_order_id)}</select></label>
    <label>Linked NCR / DMR<select name='ncr_dmr_id'>{ncr_options(row.ncr_dmr_id)}</select></label>
    <label>Part Number<input name='part_number' value='{h(row.part_number)}'></label>
    <label>Revision<input name='revision' value='{h(row.revision)}'></label>
    <label>Quantity Affected<input name='quantity_affected' type='number' value='{row.quantity_affected or 0}'></label>
    <label>Deviation Type<select name='deviation_type'><option {selected(row.deviation_type,'Use As Is')}>Use As Is</option><option {selected(row.deviation_type,'Temporary Process Change')}>Temporary Process Change</option><option {selected(row.deviation_type,'Print / Spec Deviation')}>Print / Spec Deviation</option><option {selected(row.deviation_type,'Material Substitution')}>Material Substitution</option><option {selected(row.deviation_type,'Other')}>Other</option></select></label>
    <label>Risk Level<select name='risk_level'><option {selected(row.risk_level,'Low')}>Low</option><option {selected(row.risk_level,'Medium')}>Medium</option><option {selected(row.risk_level,'High')}>High</option><option {selected(row.risk_level,'Critical')}>Critical</option></select></label>
    <label>Customer Approval Status<select name='customer_approval_status'><option {selected(row.customer_approval_status,'Not Required')}>Not Required</option><option {selected(row.customer_approval_status,'Required')}>Required</option><option {selected(row.customer_approval_status,'Submitted')}>Submitted</option><option {selected(row.customer_approval_status,'Approved')}>Approved</option><option {selected(row.customer_approval_status,'Rejected')}>Rejected</option></select></label>
    <label><input type='checkbox' name='customer_approval_required' {checked(row.customer_approval_required)}> Customer Approval Required</label>
    <label>Requested By<input name='requested_by' value='{h(row.requested_by)}'></label>
    <label>Internal Approver<input name='internal_approver' value='{h(row.internal_approver)}'></label>
    <label>Approval Date<input name='approval_date' type='date' value='{d(row.approval_date)}'></label>
    <label class='wide'>Reason / Request<textarea name='reason'>{h(row.reason)}</textarea></label>
    <label class='wide'>Proposed Disposition<textarea name='proposed_disposition'>{h(row.proposed_disposition)}</textarea></label>
    <label class='wide'>Final Disposition<textarea name='final_disposition'>{h(row.final_disposition)}</textarea></label>
    <label class='wide'>Notes<textarea name='notes'>{h(row.notes)}</textarea></label>
    <div class='wide'><button>Save Deviation Request</button> <a class='btn' href='/deviations'>Back</a></div>
    </form></section>
    """
    if getattr(row, 'id', None):
        body += f"<div class='toolbar'>{workflow_link('DEVIATION', row.id, 'Open Expedite Workflow')}</div>"
    return page('Deviation Request', body)


def apply_deviation(row):
    row.request_number = request.form.get('request_number') or row.request_number
    row.request_date = parse_date(request.form.get('request_date'))
    row.customer_id = as_int(request.form.get('customer_id'), None)
    row.work_order_id = as_int(request.form.get('work_order_id'), None)
    row.ncr_dmr_id = as_int(request.form.get('ncr_dmr_id'), None)
    row.part_number = request.form.get('part_number')
    row.revision = request.form.get('revision')
    row.quantity_affected = as_int(request.form.get('quantity_affected'))
    row.deviation_type = request.form.get('deviation_type') or 'Use As Is'
    row.requested_by = request.form.get('requested_by')
    row.reason = request.form.get('reason')
    row.proposed_disposition = request.form.get('proposed_disposition')
    row.risk_level = request.form.get('risk_level') or 'Medium'
    row.customer_approval_required = request.form.get('customer_approval_required') == 'on'
    row.customer_approval_status = request.form.get('customer_approval_status') or 'Not Required'
    row.internal_approver = request.form.get('internal_approver')
    row.approval_date = parse_date(request.form.get('approval_date'))
    row.status = request.form.get('status') or 'Draft'
    row.final_disposition = request.form.get('final_disposition')
    row.notes = request.form.get('notes')


def ncr_form(row):
    body = f"""
    <section><form method='post' class='form'>
    <label>Record Number<input name='record_number' value='{h(row.record_number)}' required></label>
    <label>Type<select name='record_type'><option {selected(row.record_type,'NCR')}>NCR</option><option {selected(row.record_type,'DMR')}>DMR</option></select></label>
    <label>Date Opened<input name='date_opened' type='date' value='{d(row.date_opened)}'></label>
    <label>Status<select name='status'><option {selected(row.status,'Open')}>Open</option><option {selected(row.status,'Contained')}>Contained</option><option {selected(row.status,'Dispositioned')}>Dispositioned</option><option {selected(row.status,'Closed')}>Closed</option></select></label>
    <label>Customer<select name='customer_id'>{customer_options(row.customer_id)}</select></label>
    <label>Department<select name='department_id'>{department_options(row.department_id)}</select></label>
    <label>Reason Code<select name='reason_code_id'>{reason_options(row.reason_code_id)}</select></label>
    <label>Work Order<select name='work_order_id'>{work_order_options(row.work_order_id)}</select></label>
    <label>Linked Deviation<select name='deviation_id'>{deviation_options(row.deviation_id)}</select></label>
    <label>Part Number<input name='part_number' value='{h(row.part_number)}'></label>
    <label>Revision<input name='revision' value='{h(row.revision)}'></label>
    <label>Quantity Affected<input name='quantity_affected' type='number' value='{row.quantity_affected or 0}'></label>
    <label>Disposition<select name='disposition'><option {selected(row.disposition,'Review Needed')}>Review Needed</option><option {selected(row.disposition,'Use As Is')}>Use As Is</option><option {selected(row.disposition,'Rework')}>Rework</option><option {selected(row.disposition,'Scrap')}>Scrap</option><option {selected(row.disposition,'Return To Vendor')}>Return To Vendor</option><option {selected(row.disposition,'Customer Approval Required')}>Customer Approval Required</option></select></label>
    <label>Disposition Owner<input name='disposition_owner' value='{h(row.disposition_owner)}'></label>
    <label>Due Date<input name='due_date' type='date' value='{d(row.due_date)}'></label>
    <label class='wide'>Defect / Nonconformance Description<textarea name='defect_description'>{h(row.defect_description)}</textarea></label>
    <label class='wide'>Containment Action<textarea name='containment_action'>{h(row.containment_action)}</textarea></label>
    <label class='wide'>Disposition Notes<textarea name='disposition_notes'>{h(row.disposition_notes)}</textarea></label>
    <label class='wide'>Notes<textarea name='notes'>{h(row.notes)}</textarea></label>
    <div class='wide'><button>Save NCR / DMR</button> <a class='btn' href='/ncr-dmr'>Back</a></div>
    </form></section>
    """
    if getattr(row, 'id', None):
        body += f"<div class='toolbar'>{workflow_link('NCR', row.id, 'Open Expedite Workflow')}</div>"
    return page('NCR / DMR', body)


def apply_ncr(row):
    row.record_number = request.form.get('record_number') or row.record_number
    row.record_type = request.form.get('record_type') or 'NCR'
    row.date_opened = parse_date(request.form.get('date_opened'))
    row.customer_id = as_int(request.form.get('customer_id'), None)
    row.department_id = as_int(request.form.get('department_id'), None)
    row.reason_code_id = as_int(request.form.get('reason_code_id'), None)
    row.work_order_id = as_int(request.form.get('work_order_id'), None)
    row.deviation_id = as_int(request.form.get('deviation_id'), None)
    row.part_number = request.form.get('part_number')
    row.revision = request.form.get('revision')
    row.quantity_affected = as_int(request.form.get('quantity_affected'))
    row.defect_description = request.form.get('defect_description')
    row.containment_action = request.form.get('containment_action')
    row.disposition = request.form.get('disposition') or 'Review Needed'
    row.disposition_notes = request.form.get('disposition_notes')
    row.disposition_owner = request.form.get('disposition_owner')
    row.due_date = parse_date(request.form.get('due_date'))
    row.status = request.form.get('status') or 'Open'
    row.notes = request.form.get('notes')


def capa_form(row):
    body = f"""
    <section><form method='post' class='form'>
    <label>CAR Number<input name='car_number' value='{h(row.car_number)}' required></label>
    <label>Date Opened<input name='date_opened' type='date' value='{d(row.date_opened)}'></label>
    <label>Status<select name='status'><option {selected(row.status,'Open')}>Open</option><option {selected(row.status,'In Progress')}>In Progress</option><option {selected(row.status,'Effectiveness Review')}>Effectiveness Review</option><option {selected(row.status,'Closed')}>Closed</option></select></label>
    <label>Source Type<select name='source_type'><option {selected(row.source_type,'Internal')}>Internal</option><option {selected(row.source_type,'RMA')}>RMA</option><option {selected(row.source_type,'NCR / DMR')}>NCR / DMR</option><option {selected(row.source_type,'Deviation')}>Deviation</option><option {selected(row.source_type,'Audit')}>Audit</option><option {selected(row.source_type,'Customer')}>Customer</option></select></label>
    <label>Linked NCR / DMR<select name='ncr_dmr_id'>{ncr_options(row.ncr_dmr_id)}</select></label>
    <label>Linked Deviation<select name='deviation_id'>{deviation_options(row.deviation_id)}</select></label>
    <label>Owner<input name='owner' value='{h(row.owner)}'></label>
    <label>Due Date<input name='due_date' type='date' value='{d(row.due_date)}'></label>
    <label>Completed Date<input name='completed_date' type='date' value='{d(row.completed_date)}'></label>
    <label class='wide'>Problem Statement<textarea name='problem_statement'>{h(row.problem_statement)}</textarea></label>
    <label class='wide'>Containment Action<textarea name='containment_action'>{h(row.containment_action)}</textarea></label>
    <label class='wide'>Root Cause<textarea name='root_cause'>{h(row.root_cause)}</textarea></label>
    <label class='wide'>Corrective Action<textarea name='corrective_action'>{h(row.corrective_action)}</textarea></label>
    <label class='wide'>Preventive Action<textarea name='preventive_action'>{h(row.preventive_action)}</textarea></label>
    <label class='wide'>Effectiveness Check<textarea name='effectiveness_check'>{h(row.effectiveness_check)}</textarea></label>
    <label class='wide'>Notes<textarea name='notes'>{h(row.notes)}</textarea></label>
    <div class='wide'><button>Save Corrective Action</button> <a class='btn' href='/corrective-actions'>Back</a></div>
    </form></section>
    """
    if getattr(row, 'id', None):
        body += f"<div class='toolbar'>{workflow_link('CAR', row.id, 'Open Expedite Workflow')}</div>"
    return page('Corrective Action', body)


def apply_capa(row):
    row.car_number = request.form.get('car_number') or row.car_number
    row.date_opened = parse_date(request.form.get('date_opened'))
    row.source_type = request.form.get('source_type') or 'Internal'
    row.ncr_dmr_id = as_int(request.form.get('ncr_dmr_id'), None)
    row.deviation_id = as_int(request.form.get('deviation_id'), None)
    row.owner = request.form.get('owner')
    row.problem_statement = request.form.get('problem_statement')
    row.containment_action = request.form.get('containment_action')
    row.root_cause = request.form.get('root_cause')
    row.corrective_action = request.form.get('corrective_action')
    row.preventive_action = request.form.get('preventive_action')
    row.due_date = parse_date(request.form.get('due_date'))
    row.completed_date = parse_date(request.form.get('completed_date'))
    row.effectiveness_check = request.form.get('effectiveness_check')
    row.status = request.form.get('status') or 'Open'
    row.notes = request.form.get('notes')


def register(app):
    install_nav()

    @app.route('/quality-forms')
    def quality_forms_home():
        cards = ''.join([
            f"<div class='card'><span>Deviation Requests</span><b>{DeviationRequest.query.count()}</b><a class='btn' href='/deviations'>Open</a></div>",
            f"<div class='card'><span>NCR / DMR Records</span><b>{NonconformanceRecord.query.count()}</b><a class='btn' href='/ncr-dmr'>Open</a></div>",
            f"<div class='card'><span>Corrective Actions</span><b>{CorrectiveAction.query.count()}</b><a class='btn' href='/corrective-actions'>Open</a></div>",
        ])
        return page('Quality Forms', f"<div class='notice'>Fillable controlled quality records for deviations, NCR/DMR handling, disposition, and corrective action tracking.</div><div class='cards'>{cards}</div>")

    @app.route('/deviations', methods=['GET', 'POST'])
    def deviations():
        if request.method == 'POST':
            row = DeviationRequest(request_number=request.form.get('request_number') or next_form_number(DeviationRequest, 'request_number', 'DEV'))
            apply_deviation(row)
            db.session.add(row); db.session.flush(); after_quality_save('DEVIATION', row, 'Saved'); log('Deviation', 'Saved', row.request_number); db.session.commit()
            return redirect(f'/deviations/{row.id}')
        blank = DeviationRequest(request_number=next_form_number(DeviationRequest, 'request_number', 'DEV'))
        rows = ''.join(f"<tr><td><a href='/deviations/{r.id}'>{h(r.request_number)}</a></td><td>{h(r.status)}</td><td>{h(r.customer.name if r.customer else '')}</td><td>{h(r.part_number)}</td><td>{h(r.deviation_type)}</td><td>{h(r.risk_level)}</td></tr>" for r in DeviationRequest.query.order_by(DeviationRequest.id.desc()).limit(200))
        return page('Deviation Requests', deviation_form(blank).split('<main><h1>Deviation Request</h1>', 1)[-1].rsplit('</main>', 1)[0] + f"<br><section><h2>Deviation Log</h2><table><tr><th>Number</th><th>Status</th><th>Customer</th><th>Part</th><th>Type</th><th>Risk</th></tr>{rows}</table></section>")

    @app.route('/deviations/<int:row_id>', methods=['GET', 'POST'])
    def deviation_detail(row_id):
        row = DeviationRequest.query.get_or_404(row_id)
        if request.method == 'POST':
            apply_deviation(row); after_quality_save('DEVIATION', row, 'Updated'); log('Deviation', 'Updated', row.request_number); db.session.commit(); return redirect(f'/deviations/{row.id}')
        return deviation_form(row)

    @app.route('/ncr-dmr', methods=['GET', 'POST'])
    def ncr_dmr():
        if request.method == 'POST':
            prefix = 'DMR' if request.form.get('record_type') == 'DMR' else 'NCR'
            row = NonconformanceRecord(record_number=request.form.get('record_number') or next_form_number(NonconformanceRecord, 'record_number', prefix))
            apply_ncr(row)
            db.session.add(row); db.session.flush(); after_quality_save('NCR', row, 'Saved'); log('NCR/DMR', 'Saved', row.record_number); db.session.commit()
            return redirect(f'/ncr-dmr/{row.id}')
        blank = NonconformanceRecord(record_number=next_form_number(NonconformanceRecord, 'record_number', 'NCR'))
        rows = ''.join(f"<tr><td><a href='/ncr-dmr/{r.id}'>{h(r.record_number)}</a></td><td>{h(r.record_type)}</td><td>{h(r.status)}</td><td>{h(r.department.name if r.department else '')}</td><td>{h(r.part_number)}</td><td>{h(r.disposition)}</td></tr>" for r in NonconformanceRecord.query.order_by(NonconformanceRecord.id.desc()).limit(200))
        return page('NCR / DMR Records', ncr_form(blank).split('<main><h1>NCR / DMR</h1>', 1)[-1].rsplit('</main>', 1)[0] + f"<br><section><h2>NCR / DMR Log</h2><table><tr><th>Number</th><th>Type</th><th>Status</th><th>Department</th><th>Part</th><th>Disposition</th></tr>{rows}</table></section>")

    @app.route('/ncr-dmr/<int:row_id>', methods=['GET', 'POST'])
    def ncr_dmr_detail(row_id):
        row = NonconformanceRecord.query.get_or_404(row_id)
        if request.method == 'POST':
            apply_ncr(row); after_quality_save('NCR', row, 'Updated'); log('NCR/DMR', 'Updated', row.record_number); db.session.commit(); return redirect(f'/ncr-dmr/{row.id}')
        return ncr_form(row)

    @app.route('/corrective-actions', methods=['GET', 'POST'])
    def corrective_actions():
        if request.method == 'POST':
            row = CorrectiveAction(car_number=request.form.get('car_number') or next_form_number(CorrectiveAction, 'car_number', 'CAR'))
            apply_capa(row)
            db.session.add(row); db.session.flush(); after_quality_save('CAR', row, 'Saved'); log('CorrectiveAction', 'Saved', row.car_number); db.session.commit()
            return redirect(f'/corrective-actions/{row.id}')
        blank = CorrectiveAction(car_number=next_form_number(CorrectiveAction, 'car_number', 'CAR'))
        rows = ''.join(f"<tr><td><a href='/corrective-actions/{r.id}'>{h(r.car_number)}</a></td><td>{h(r.status)}</td><td>{h(r.source_type)}</td><td>{h(r.owner)}</td><td>{h(r.due_date)}</td></tr>" for r in CorrectiveAction.query.order_by(CorrectiveAction.id.desc()).limit(200))
        return page('Corrective Actions', capa_form(blank).split('<main><h1>Corrective Action</h1>', 1)[-1].rsplit('</main>', 1)[0] + f"<br><section><h2>Corrective Action Log</h2><table><tr><th>CAR</th><th>Status</th><th>Source</th><th>Owner</th><th>Due</th></tr>{rows}</table></section>")

    @app.route('/corrective-actions/<int:row_id>', methods=['GET', 'POST'])
    def corrective_action_detail(row_id):
        row = CorrectiveAction.query.get_or_404(row_id)
        if request.method == 'POST':
            apply_capa(row); after_quality_save('CAR', row, 'Updated'); log('CorrectiveAction', 'Updated', row.car_number); db.session.commit(); return redirect(f'/corrective-actions/{row.id}')
        return capa_form(row)
