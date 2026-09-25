from __future__ import annotations

from datetime import date, datetime, timedelta
from html import escape

from flask import redirect, request

from audit_journal import model_snapshot, record_event
import forgeqc_app
from forgeqc_app import OperationClockSummary, RMA, db, log, page


class QualityWorkflowItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_type = db.Column(db.String(40), nullable=False, index=True)
    source_id = db.Column(db.Integer, nullable=False, index=True)
    case_number = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(300))
    owner_name = db.Column(db.String(160))
    owner_email = db.Column(db.String(240))
    priority = db.Column(db.String(40), default='Normal')
    workflow_status = db.Column(db.String(80), default='NEW')
    next_action = db.Column(db.Text)
    due_date = db.Column(db.Date)
    car_required = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity_at = db.Column(db.DateTime, default=datetime.utcnow)
    closed_at = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint('source_type', 'source_id', name='uq_quality_workflow_source'),
    )


class QualityWorkflowActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    workflow_id = db.Column(db.Integer, db.ForeignKey('quality_workflow_item.id'), nullable=False, index=True)
    activity_type = db.Column(db.String(80), nullable=False)
    detail = db.Column(db.Text, nullable=False)
    actor = db.Column(db.String(160))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    workflow = db.relationship('QualityWorkflowItem')


SOURCE_ALIASES = {
    'ncr': 'NCR',
    'ncr-dmr': 'NCR',
    'dmr': 'NCR',
    'rma': 'RMA',
    'deviation': 'DEVIATION',
    'dev': 'DEVIATION',
    'car': 'CAR',
    'corrective-action': 'CAR',
}


def h(value):
    return escape(str(value or ''), quote=True)


def normalize_source(value):
    clean = str(value or '').strip().lower()
    return SOURCE_ALIASES.get(clean, str(value or '').strip().upper())


def source_case_number(source_type, row):
    attrs = {
        'NCR': ('record_number',),
        'RMA': ('rma_number',),
        'DEVIATION': ('request_number',),
        'CAR': ('car_number',),
    }
    for attr in attrs.get(source_type, ()):
        value = getattr(row, attr, None)
        if value:
            return str(value)
    return f'{source_type}-{getattr(row, "id", "NEW")}'


def source_title(source_type, row):
    fields = {
        'NCR': ('defect_description', 'part_number'),
        'RMA': ('defect_description', 'part_number'),
        'DEVIATION': ('reason', 'part_number'),
        'CAR': ('problem_statement',),
    }
    values = []
    for attr in fields.get(source_type, ()):
        value = str(getattr(row, attr, '') or '').strip()
        if value:
            values.append(value)
    title = ' | '.join(values)
    return title[:300] if title else source_case_number(source_type, row)


def source_status(row):
    return str(getattr(row, 'status', '') or '').strip()


def source_due_date(source_type, row):
    due = getattr(row, 'due_date', None)
    if due:
        return due
    return None


def source_owner(source_type, row):
    if source_type == 'NCR':
        return str(getattr(row, 'disposition_owner', '') or '')
    if source_type == 'CAR':
        return str(getattr(row, 'owner', '') or '')
    if source_type == 'DEVIATION':
        return str(getattr(row, 'requested_by', '') or '')
    return ''


def default_next_action(source_type, row):
    if source_type == 'NCR':
        disposition = str(getattr(row, 'disposition', '') or 'Review Needed')
        return f'Review containment and disposition: {disposition}'
    if source_type == 'RMA':
        return 'Review customer return and define next quality action'
    if source_type == 'DEVIATION':
        return 'Complete risk review and disposition'
    if source_type == 'CAR':
        return 'Complete root cause, corrective action, and effectiveness evidence'
    return 'Define next action'


def is_source_closed(status):
    return str(status or '').strip().lower() in {'closed', 'resolved', 'cancelled', 'rejected'}


def ensure_workflow(source_type, row):
    source_type = normalize_source(source_type)
    if not getattr(row, 'id', None):
        db.session.flush()
    item = QualityWorkflowItem.query.filter_by(source_type=source_type, source_id=row.id).first()
    now = datetime.utcnow()
    if not item:
        source_state = source_status(row)
        item = QualityWorkflowItem(
            source_type=source_type,
            source_id=row.id,
            case_number=source_case_number(source_type, row),
            title=source_title(source_type, row),
            owner_name=source_owner(source_type, row),
            priority='High' if source_type == 'RMA' else 'Normal',
            workflow_status='CLOSED' if is_source_closed(source_state) else 'NEW',
            next_action=default_next_action(source_type, row),
            due_date=source_due_date(source_type, row),
            created_at=now,
            updated_at=now,
            last_activity_at=now,
            closed_at=now if is_source_closed(source_state) else None,
        )
        db.session.add(item)
        db.session.flush()
        record_activity(item, 'CREATED', f'Workflow created from {source_type} record.')
    else:
        item.case_number = source_case_number(source_type, row)
        item.title = source_title(source_type, row)
        item.updated_at = now
        source_state = source_status(row)
        if is_source_closed(source_state):
            item.workflow_status = 'CLOSED'
            item.closed_at = item.closed_at or now
        elif item.workflow_status == 'CLOSED':
            item.workflow_status = 'OPEN'
            item.closed_at = None
        if not item.owner_name:
            item.owner_name = source_owner(source_type, row)
        if not item.due_date:
            item.due_date = source_due_date(source_type, row)
        if not item.next_action:
            item.next_action = default_next_action(source_type, row)
    return item


def record_activity(item, activity_type, detail, actor=''):
    now = datetime.utcnow()
    db.session.add(QualityWorkflowActivity(
        workflow_id=item.id,
        activity_type=activity_type,
        detail=str(detail or '').strip() or activity_type,
        actor=str(actor or '').strip(),
        created_at=now,
    ))
    item.last_activity_at = now
    item.updated_at = now
    try:
        record_event(
            'QUALITY_WORKFLOW',
            activity_type,
            entity_type=item.source_type,
            entity_id=item.case_number,
            actor=actor,
            detail=str(detail or '').strip() or activity_type,
            data={'workflow_id': item.id, 'source_id': item.source_id, 'status': item.workflow_status, 'next_action': item.next_action},
        )
    except Exception:
        pass


def after_quality_save(source_type, row, action='Saved'):
    item = ensure_workflow(source_type, row)
    record_activity(item, 'SOURCE UPDATE', f'{action}: {source_case_number(normalize_source(source_type), row)}')
    db.session.flush()
    try:
        record_event(
            'QUALITY_RECORD',
            action,
            entity_type=normalize_source(source_type),
            entity_id=source_case_number(normalize_source(source_type), row),
            detail=f'{action} controlled quality record',
            data=model_snapshot(row),
        )
    except Exception:
        pass
    try:
        from pulse_intelligence import compute_pulse_snapshot
        compute_pulse_snapshot(30)
    except Exception as exc:
        log('Workflow', 'KPI refresh deferred', str(exc)[:500])
    return item


def backfill_workflows():
    from quality_forms import CorrectiveAction, DeviationRequest, NonconformanceRecord

    for row in NonconformanceRecord.query.all():
        ensure_workflow('NCR', row)
    for row in RMA.query.all():
        ensure_workflow('RMA', row)
    for row in DeviationRequest.query.all():
        ensure_workflow('DEVIATION', row)
    for row in CorrectiveAction.query.all():
        ensure_workflow('CAR', row)


def ppm_metrics(days=30):
    from quality_forms import NonconformanceRecord

    cutoff = date.today() - timedelta(days=days)
    clocks = OperationClockSummary.query.filter(
        OperationClockSummary.period_date != None,
        OperationClockSummary.period_date >= cutoff,
    ).all()
    tracked_units = sum(
        (row.first_pass_good_qty or 0) + (row.rework_qty or 0) + (row.scrap_qty or 0)
        for row in clocks
    )
    units = tracked_units
    denominator_source = 'Tracked production output'
    try:
        from erp_integration import ERPShipment
        shipped_units = db.session.query(db.func.sum(ERPShipment.quantity_shipped)).filter(
            ERPShipment.ship_date != None,
            ERPShipment.ship_date >= cutoff,
        ).scalar() or 0
        if shipped_units > 0:
            units = float(shipped_units)
            denominator_source = 'ERP shipped quantity'
    except Exception:
        pass
    ncr_rows = NonconformanceRecord.query.filter(
        NonconformanceRecord.date_opened != None,
        NonconformanceRecord.date_opened >= cutoff,
    ).all()
    rma_rows = RMA.query.filter(
        RMA.date_opened != None,
        RMA.date_opened >= cutoff,
    ).all()
    ncr_qty = sum(max(row.quantity_affected or 0, 0) for row in ncr_rows)
    rma_qty = sum(max(row.quantity_affected or 0, 0) for row in rma_rows)
    ncr_ppm = round((ncr_qty / units) * 1_000_000, 1) if units else 0
    rma_ppm = round((rma_qty / units) * 1_000_000, 1) if units else 0
    return {
        'days': days,
        'units': units,
        'ncr_qty': ncr_qty,
        'rma_qty': rma_qty,
        'ncr_ppm': ncr_ppm,
        'rma_ppm': rma_ppm,
        'denominator_source': denominator_source,
        'tracked_units': tracked_units,
    }


def workflow_counts():
    today = date.today()
    stale_cutoff = datetime.utcnow() - timedelta(days=7)
    open_query = QualityWorkflowItem.query.filter(QualityWorkflowItem.workflow_status != 'CLOSED')
    return {
        'open': open_query.count(),
        'overdue': open_query.filter(QualityWorkflowItem.due_date != None, QualityWorkflowItem.due_date < today).count(),
        'unassigned': open_query.filter(
            (QualityWorkflowItem.owner_name == None) | (QualityWorkflowItem.owner_name == '')
        ).count(),
        'stale': open_query.filter(QualityWorkflowItem.last_activity_at < stale_cutoff).count(),
    }


def source_record(source_type, source_id):
    source_type = normalize_source(source_type)
    if source_type == 'RMA':
        return RMA.query.get_or_404(source_id)
    from quality_forms import CorrectiveAction, DeviationRequest, NonconformanceRecord
    model = {
        'NCR': NonconformanceRecord,
        'DEVIATION': DeviationRequest,
        'CAR': CorrectiveAction,
    }.get(source_type)
    if not model:
        raise LookupError(f'Unknown workflow source: {source_type}')
    return model.query.get_or_404(source_id)


def linked_car_for_ncr(ncr_id):
    from quality_forms import CorrectiveAction
    return CorrectiveAction.query.filter_by(ncr_dmr_id=ncr_id).order_by(CorrectiveAction.id).first()


def car_recommendation(ncr):
    from quality_forms import NonconformanceRecord

    if linked_car_for_ncr(ncr.id):
        return 'Linked CAR already exists.'
    cutoff = date.today() - timedelta(days=90)
    q = NonconformanceRecord.query.filter(
        NonconformanceRecord.id != ncr.id,
        NonconformanceRecord.date_opened != None,
        NonconformanceRecord.date_opened >= cutoff,
    )
    repeat = False
    if ncr.part_number:
        repeat = q.filter(NonconformanceRecord.part_number == ncr.part_number).count() > 0
    if not repeat and ncr.reason_code_id:
        repeat = q.filter(NonconformanceRecord.reason_code_id == ncr.reason_code_id).count() > 0
    if repeat:
        return 'CAR suggested: repeat part or reason code found in the last 90 days.'
    if (ncr.quantity_affected or 0) >= 5:
        return 'CAR suggested: affected quantity is 5 or greater.'
    return 'CAR is available if investigation shows systemic or repeat risk.'


def create_car_from_ncr(ncr, actor=''):
    from quality_forms import CorrectiveAction, next_form_number

    existing = linked_car_for_ncr(ncr.id)
    if existing:
        return existing, False
    ncr_workflow = ensure_workflow('NCR', ncr)
    car = CorrectiveAction(
        car_number=next_form_number(CorrectiveAction, 'car_number', 'CAR'),
        date_opened=date.today(),
        source_type='NCR / DMR',
        ncr_dmr_id=ncr.id,
        owner=ncr_workflow.owner_name or ncr.disposition_owner,
        problem_statement=ncr.defect_description,
        containment_action=ncr.containment_action,
        due_date=ncr_workflow.due_date or ncr.due_date or (date.today() + timedelta(days=14)),
        status='Open',
        notes=f'Created from {ncr.record_number}.',
    )
    db.session.add(car)
    db.session.flush()
    car_workflow = ensure_workflow('CAR', car)
    car_workflow.priority = ncr_workflow.priority or 'Normal'
    car_workflow.next_action = 'Complete root cause analysis and define corrective action.'
    record_activity(ncr_workflow, 'CAR CREATED', f'{car.car_number} created from this nonconformance.', actor)
    record_activity(car_workflow, 'SOURCE LINK', f'Created from {ncr.record_number}.', actor)
    return car, True


def source_link(item):
    if item.source_type == 'NCR':
        return f'/ncr-dmr/{item.source_id}'
    if item.source_type == 'DEVIATION':
        return f'/deviations/{item.source_id}'
    if item.source_type == 'CAR':
        return f'/corrective-actions/{item.source_id}'
    if item.source_type == 'RMA':
        return '/rma'
    return '#'


def workflow_link(source_type, source_id, label='Workflow'):
    return f"<a class='btn' href='/expedite/{h(normalize_source(source_type).lower())}/{int(source_id)}'>{h(label)}</a>"


def install_ui():
    if "href='/expedite'" not in forgeqc_app.BASE:
        forgeqc_app.BASE = forgeqc_app.BASE.replace(
            "<a href='/'>Dashboard</a>",
            "<a href='/'>Dashboard</a><a href='/expedite'>Expedite</a>",
        )
    if 'chatgpt-assistant-toggle' not in forgeqc_app.BASE:
        forgeqc_app.CSS += r"""
        .wf-state{display:inline-flex;border:1px solid #35506a;background:#152638;border-radius:999px;padding:3px 8px;font-size:12px;font-weight:700}
        .wf-overdue{font-weight:800;text-decoration:underline;text-decoration-color:#4ea1d8;text-underline-offset:3px}
        .wf-note{display:flex;gap:6px;min-width:260px}.wf-note input{margin:0;min-width:170px}.wf-note button{padding:8px 10px}
        .ai-toggle{position:fixed;right:18px;bottom:18px;z-index:10020;border-radius:999px;padding:11px 15px}
        .ai-sidebar{position:fixed;z-index:10010;top:0;right:-390px;width:370px;max-width:92vw;height:100vh;background:#08131d;border-left:1px solid #32465a;box-shadow:-18px 0 55px rgba(0,0,0,.45);padding:18px;transition:right .18s ease;overflow:auto}
        .ai-sidebar.open{right:0}.ai-sidebar h2{margin:0 0 8px}.ai-sidebar textarea{min-height:180px}.ai-sidebar .ai-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.ai-sidebar .ai-note{font-size:12px;color:#98aabd;margin-top:10px}.ai-close{float:right;background:transparent;border-color:#32465a;box-shadow:none}
        """
        assistant = r"""
        <button id="chatgpt-assistant-toggle" class="ai-toggle" type="button">ChatGPT Assistant</button>
        <aside id="chatgpt-assistant" class="ai-sidebar" aria-hidden="true">
          <button id="chatgpt-assistant-close" class="ai-close" type="button">Close</button>
          <h2>ChatGPT Assistant</h2>
          <p class="muted">Build a quality-context prompt from the page, copy it, then open your existing ChatGPT session. No API key is used.</p>
          <label>Task
            <select id="chatgpt-task">
              <option value="quality">Analyze this quality record</option>
              <option value="ncr">NCR containment / disposition review</option>
              <option value="car">Draft CAR / 5-Why support</option>
              <option value="kpi">KPI / PPM interpretation</option>
              <option value="audit">Audit-readiness review</option>
            </select>
          </label>
          <label style="margin-top:10px">Prompt
            <textarea id="chatgpt-prompt"></textarea>
          </label>
          <div class="ai-actions">
            <button id="chatgpt-build" type="button">Refresh Context</button>
            <button id="chatgpt-copy-open" type="button">Copy + Open ChatGPT</button>
            <button id="chatgpt-copy" type="button">Copy Only</button>
          </div>
          <p class="ai-note">ForgeQC does not read your ChatGPT replies automatically. Paste the copied prompt into ChatGPT, then put approved conclusions back into the controlled quality record.</p>
        </aside>
        <script>
        (function(){
          const panel=document.getElementById('chatgpt-assistant');
          const promptBox=document.getElementById('chatgpt-prompt');
          const task=document.getElementById('chatgpt-task');
          function fieldContext(){
            const rows=[];
            document.querySelectorAll('input,select,textarea').forEach(el=>{
              if(el.id==='chatgpt-prompt' || el.type==='password' || el.type==='file' || el.type==='hidden') return;
              let value='';
              if(el.type==='checkbox' || el.type==='radio'){ if(!el.checked) return; value=el.value || 'checked'; }
              else value=el.value || '';
              if(!value) return;
              const label=el.closest('label');
              const name=(label ? label.childNodes[0].textContent.trim() : '') || el.name || el.id || 'Field';
              rows.push(name+': '+value);
            });
            return rows.join('\n');
          }
          function buildPrompt(){
            const tasks={
              quality:'Analyze this manufacturing quality record. Identify missing facts, containment gaps, likely systemic causes, disposition risks, CAR implications, and KPI/PPM implications. Do not invent facts. Separate observations from recommendations.',
              ncr:'Review this NCR/DMR as a quality engineer. Check problem definition, containment, affected quantity, disposition, ownership, repeat-risk, whether a CAR should be opened, and what evidence is needed before closure.',
              car:'Help develop a defensible corrective action from this record. Strengthen the problem statement, guide a 5-Why chain toward a controllable system cause, propose containment/corrective/preventive actions, and define an effectiveness check. Avoid operator-blame as a root cause.',
              kpi:'Interpret the quality/KPI context on this page. Explain PPM, FPY, NCR/RMA trends, overdue actions, repeat patterns, and which underlying records should be investigated. Do not claim causation without evidence.',
              audit:'Review this page for audit readiness. Identify incomplete traceability, missing objective evidence, ownership/due-date gaps, closure risks, and records an auditor would likely ask to see.'
            };
            const visible=(document.querySelector('main')?.innerText || '').slice(0,5000);
            promptBox.value=tasks[task.value]+'\n\nForgeQC page: '+document.title+'\nPath: '+location.pathname+'\n\nEntered fields:\n'+fieldContext()+'\n\nVisible record context:\n'+visible;
          }
          async function copyPrompt(){
            buildPrompt();
            await navigator.clipboard.writeText(promptBox.value);
          }
          document.getElementById('chatgpt-assistant-toggle').addEventListener('click',()=>{panel.classList.add('open');panel.setAttribute('aria-hidden','false');buildPrompt();});
          document.getElementById('chatgpt-assistant-close').addEventListener('click',()=>{panel.classList.remove('open');panel.setAttribute('aria-hidden','true');});
          document.getElementById('chatgpt-build').addEventListener('click',buildPrompt);
          task.addEventListener('change',buildPrompt);
          document.getElementById('chatgpt-copy').addEventListener('click',copyPrompt);
          document.getElementById('chatgpt-copy-open').addEventListener('click',async()=>{await copyPrompt();window.open('https://chatgpt.com/','_blank','noopener');});
        })();
        </script>
        """
        forgeqc_app.BASE = forgeqc_app.BASE.replace('</body>', assistant + '</body>')


def detail_body(item, row):
    today = date.today()
    overdue = item.due_date and item.due_date < today and item.workflow_status != 'CLOSED'
    activities = ''.join(
        f"<div class='notice'><b>{h(a.activity_type)}</b> <span class='muted'>{h(a.created_at)} {h(a.actor)}</span><br>{h(a.detail)}</div>"
        for a in QualityWorkflowActivity.query.filter_by(workflow_id=item.id).order_by(QualityWorkflowActivity.id.desc()).limit(100)
    ) or "<p class='muted'>No activity yet.</p>"
    priority_options = ''.join(
        f"<option {'selected' if item.priority == value else ''}>{value}</option>"
        for value in ['Low', 'Normal', 'High', 'Critical']
    )
    status_options = ''.join(
        f"<option {'selected' if item.workflow_status == value else ''}>{value}</option>"
        for value in ['NEW', 'ASSIGNMENT REQUIRED', 'OPEN', 'INVESTIGATING', 'AWAITING INTERNAL ACTION', 'AWAITING CUSTOMER', 'CORRECTIVE ACTION OPEN', 'READY TO CLOSE', 'CLOSED']
    )
    car_html = ''
    if item.source_type == 'NCR':
        existing = linked_car_for_ncr(row.id)
        if existing:
            car_html = f"<div class='notice'><b>Linked CAR:</b> <a href='/corrective-actions/{existing.id}'>{h(existing.car_number)}</a></div>"
        else:
            car_html = f"""<div class='notice'><b>{h(car_recommendation(row))}</b><form method='post' action='/expedite/ncr/{row.id}/create-car' style='margin-top:8px'><button>Create CAR From NCR</button></form></div>"""
    return f"""
    <div class='toolbar'><a class='btn' href='/expedite'>Back to Expedite</a><a class='btn' href='{h(source_link(item))}'>Open Source Record</a></div>
    {car_html}
    <section><form method='post' class='form'>
      <label>Case<input value='{h(item.case_number)}' disabled></label>
      <label>Source<input value='{h(item.source_type)}' disabled></label>
      <label>Workflow Status<select name='workflow_status'>{status_options}</select></label>
      <label>Owner Name<input name='owner_name' value='{h(item.owner_name)}'></label>
      <label>Owner Email<input type='email' name='owner_email' value='{h(item.owner_email)}'></label>
      <label>Priority<select name='priority'>{priority_options}</select></label>
      <label>Due Date<input type='date' name='due_date' value='{h(item.due_date.isoformat() if item.due_date else "")}'></label>
      <label><input type='checkbox' name='car_required' value='1' {'checked' if item.car_required else ''}> CAR Required</label>
      <label class='wide'>Next Action<textarea name='next_action'>{h(item.next_action)}</textarea></label>
      <label class='wide'>Progress Note<textarea name='progress_note'></textarea></label>
      <div class='wide'><button>Save Workflow</button></div>
    </form></section>
    <br><section><h2>{'OVERDUE - ' if overdue else ''}{h(item.title)}</h2><p class='muted'>Last activity: {h(item.last_activity_at)}</p></section>
    <br><section><h2>Activity History</h2>{activities}</section>
    """


def register(app):
    install_ui()

    @app.route('/expedite')
    def expedite_dashboard():
        backfill_workflows()
        db.session.commit()
        counts = workflow_counts()
        ppm = ppm_metrics(30)
        cards = ''.join([
            f"<div class='card'><span>Open Quality Actions</span><b>{counts['open']}</b></div>",
            f"<div class='card'><span>Overdue</span><b>{counts['overdue']}</b></div>",
            f"<div class='card'><span>Unassigned</span><b>{counts['unassigned']}</b></div>",
            f"<div class='card'><span>Stale 7+ Days</span><b>{counts['stale']}</b></div>",
            f"<div class='card'><span>NCR PPM 30D</span><b>{ppm['ncr_ppm']}</b></div>",
            f"<div class='card'><span>RMA PPM 30D</span><b>{ppm['rma_ppm']}</b></div>",
        ])
        today = date.today()
        rows = ''
        query = QualityWorkflowItem.query.order_by(QualityWorkflowItem.due_date, QualityWorkflowItem.updated_at.desc()).all()
        for item in query:
            latest = QualityWorkflowActivity.query.filter_by(workflow_id=item.id).order_by(QualityWorkflowActivity.id.desc()).first()
            due_class = 'wf-overdue' if item.due_date and item.due_date < today and item.workflow_status != 'CLOSED' else ''
            rows += f"""<tr>
              <td><a href='/expedite/{h(item.source_type.lower())}/{item.source_id}'>{h(item.case_number)}</a></td>
              <td>{h(item.source_type)}</td><td>{h(item.priority)}</td><td>{h(item.owner_name or 'UNASSIGNED')}</td>
              <td class='{due_class}'>{h(item.due_date)}</td><td><span class='wf-state'>{h(item.workflow_status)}</span></td>
              <td>{h(item.next_action)}</td><td>{h(latest.detail if latest else '')}</td>
              <td><form class='wf-note' method='post' action='/expedite/{h(item.source_type.lower())}/{item.source_id}/note'><input name='note' placeholder='Progress note'><button>Add</button></form></td>
            </tr>"""
        note = "PPM denominator is tracked operation output from FPY clocking. Use shipped quantity as the customer PPM denominator when that data source is added."
        body = f"""<div class='notice'>EZ Expedite-style quality action control across NCRs, RMAs, deviations, and CARs. {h(note)}</div>
        <div class='cards'>{cards}</div><br>
        <div class='toolbar'><form method='post' action='/expedite/snapshot'><button>Refresh KPI Snapshot</button></form><a class='btn' href='/pulse'>Open Quality Pulse</a></div>
        <section><table><tr><th>Case</th><th>Type</th><th>Priority</th><th>Owner</th><th>Due</th><th>Status</th><th>Next Action</th><th>Latest Activity</th><th>Progress</th></tr>{rows}</table></section>"""
        return page('Quality Expedite', body)

    @app.route('/expedite/<source_type>/<int:source_id>', methods=['GET', 'POST'])
    def expedite_detail(source_type, source_id):
        source_type = normalize_source(source_type)
        row = source_record(source_type, source_id)
        item = ensure_workflow(source_type, row)
        if request.method == 'POST':
            old_owner = item.owner_name or ''
            item.owner_name = request.form.get('owner_name')
            item.owner_email = request.form.get('owner_email')
            item.priority = request.form.get('priority') or 'Normal'
            item.workflow_status = request.form.get('workflow_status') or 'OPEN'
            item.next_action = request.form.get('next_action')
            raw_due = request.form.get('due_date')
            item.due_date = datetime.strptime(raw_due, '%Y-%m-%d').date() if raw_due else None
            item.car_required = request.form.get('car_required') == '1'
            item.updated_at = datetime.utcnow()
            item.closed_at = datetime.utcnow() if item.workflow_status == 'CLOSED' else None
            if old_owner != (item.owner_name or ''):
                record_activity(item, 'OWNER', f'Owner changed from {old_owner or "UNASSIGNED"} to {item.owner_name or "UNASSIGNED"}.')
            note = request.form.get('progress_note')
            if note:
                record_activity(item, 'PROGRESS', note, item.owner_name or '')
            record_activity(item, 'WORKFLOW UPDATE', f'Status {item.workflow_status}; next action: {item.next_action or "not set"}', item.owner_name or '')
            if item.source_type == 'NCR' and item.car_required:
                car, created = create_car_from_ncr(row, item.owner_name or '')
                if created:
                    item.workflow_status = 'CORRECTIVE ACTION OPEN'
                    item.next_action = f'Complete {car.car_number} and verify effectiveness.'
            db.session.commit()
            try:
                from pulse_intelligence import compute_pulse_snapshot
                compute_pulse_snapshot(30)
            except Exception as exc:
                log('Workflow', 'KPI refresh deferred', str(exc)[:500])
                db.session.commit()
            return redirect(f'/expedite/{item.source_type.lower()}/{item.source_id}')
        return page(f'Expedite {item.case_number}', detail_body(item, row))

    @app.route('/expedite/<source_type>/<int:source_id>/note', methods=['POST'])
    def expedite_note(source_type, source_id):
        source_type = normalize_source(source_type)
        row = source_record(source_type, source_id)
        item = ensure_workflow(source_type, row)
        note = str(request.form.get('note') or '').strip()
        if note:
            record_activity(item, 'PROGRESS', note, item.owner_name or '')
            db.session.commit()
        return redirect('/expedite')

    @app.route('/expedite/ncr/<int:ncr_id>/create-car', methods=['POST'])
    def expedite_create_car(ncr_id):
        from quality_forms import NonconformanceRecord
        ncr = NonconformanceRecord.query.get_or_404(ncr_id)
        car, _created = create_car_from_ncr(ncr)
        ncr_item = ensure_workflow('NCR', ncr)
        ncr_item.car_required = True
        ncr_item.workflow_status = 'CORRECTIVE ACTION OPEN'
        ncr_item.next_action = f'Complete {car.car_number} and verify effectiveness.'
        db.session.commit()
        try:
            from pulse_intelligence import compute_pulse_snapshot
            compute_pulse_snapshot(30)
        except Exception:
            pass
        return redirect(f'/corrective-actions/{car.id}')

    @app.route('/expedite/snapshot', methods=['POST'])
    def expedite_snapshot():
        from pulse_intelligence import compute_pulse_snapshot
        compute_pulse_snapshot(30)
        return redirect('/expedite')
