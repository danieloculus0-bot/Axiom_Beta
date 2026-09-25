from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class IntelligenceSignal:
    area: str
    title: str
    severity: str
    score: int
    source_tables: tuple[str, ...]
    summary: str
    recommendation: str
    workflow_key: str | None = None


@dataclass(frozen=True)
class WorkflowDefinition:
    key: str
    title: str
    area: str
    purpose: str
    trigger: str
    steps: tuple[str, ...]
    required_review: str
    output: str
    source_tables: tuple[str, ...]
    target_tables: tuple[str, ...]


def scalar(db, sql: str, args: tuple[Any, ...] = ()) -> float:
    row = db.execute(sql, args).fetchone()
    if not row:
        return 0
    value = row[0]
    return 0 if value is None else value


def rows(db, sql: str, args: tuple[Any, ...] = ()) -> list[Any]:
    return list(db.execute(sql, args).fetchall())


def severity_from_score(score: int) -> str:
    if score >= 75:
        return 'critical'
    if score >= 45:
        return 'high'
    if score >= 20:
        return 'watch'
    return 'normal'


def build_interaction_signals(db) -> list[IntelligenceSignal]:
    signals: list[IntelligenceSignal] = []

    supplier_delay = float(scalar(db, """
        SELECT AVG(actual_average_lead_time_days - quoted_lead_time_days)
        FROM supplier_performance_snapshots
        WHERE actual_average_lead_time_days IS NOT NULL
          AND quoted_lead_time_days IS NOT NULL
    """))
    supplier_high_risk = int(scalar(db, "SELECT COUNT(*) FROM supplier_performance_snapshots WHERE risk_level IN ('high','critical')"))
    supplier_score = min(100, supplier_high_risk * 22 + max(0, int(supplier_delay)) * 8)
    signals.append(IntelligenceSignal(
        area='Supplier to Quoting',
        title='Supplier lead-time drift should affect quote promises',
        severity=severity_from_score(supplier_score),
        score=supplier_score,
        source_tables=('supplier_performance_snapshots', 'materials', 'quote_material_drafts', 'purchasing_watchlists'),
        summary=f'Supplier snapshots show {supplier_high_risk} high-risk supplier records and an average lead-time drift of {supplier_delay:.1f} days.',
        recommendation='When drafting quote materials, compare supplier actual lead time against quoted lead time and push quote lead-time assumptions later when supplier drift is positive.',
        workflow_key='quote-lead-time-review',
    ))

    machine_util = float(scalar(db, "SELECT AVG(utilization_percent) FROM machine_utilization_snapshots WHERE utilization_percent IS NOT NULL"))
    machine_risks = int(scalar(db, "SELECT COUNT(*) FROM machine_utilization_snapshots WHERE risk_level IN ('high','critical') OR utilization_percent >= 90"))
    machine_score = min(100, machine_risks * 25 + max(0, int(machine_util - 75)) * 3)
    signals.append(IntelligenceSignal(
        area='Machine Capacity to Planning',
        title='Machine loading should affect work-order and quote dates',
        severity=severity_from_score(machine_score),
        score=machine_score,
        source_tables=('machine_assets', 'machine_utilization_snapshots', 'work_orders', 'planning_watchlists', 'quote_intakes'),
        summary=f'Machine utilization averages {machine_util:.1f}% with {machine_risks} high-risk capacity records.',
        recommendation='When utilization is high, flag affected work centers and add planning watchlist items before accepting aggressive ship dates.',
        workflow_key='capacity-risk-review',
    ))

    cert_holds = int(scalar(db, "SELECT COUNT(*) FROM material_certificates WHERE review_status IN ('needs_review','draft','hold')"))
    cert_score = min(100, cert_holds * 18)
    signals.append(IntelligenceSignal(
        area='Material Certs to Quality',
        title='Unreviewed certs should block quiet material confidence',
        severity=severity_from_score(cert_score),
        score=cert_score,
        source_tables=('material_certificates', 'materials', 'work_orders', 'quality_events'),
        summary=f'{cert_holds} material certificate records need review or are on hold.',
        recommendation='Use cert review status as a traceability gate before relying on material records for shipment, quality response, or customer documentation.',
        workflow_key='material-cert-review',
    ))

    bom_review = int(scalar(db, "SELECT COUNT(*) FROM pdf_bom_candidates WHERE review_status IN ('needs_review','draft')"))
    quote_drafts = int(scalar(db, "SELECT COUNT(*) FROM quote_material_drafts WHERE review_status IN ('draft','needs_review')"))
    quote_score = min(100, bom_review * 10 + quote_drafts * 12)
    signals.append(IntelligenceSignal(
        area='Drawing Intake to Quote',
        title='BOM extraction must stay review-gated before quote use',
        severity=severity_from_score(quote_score),
        score=quote_score,
        source_tables=('quote_intakes', 'pdf_bom_candidates', 'bom_reviews', 'quote_material_drafts', 'materials'),
        summary=f'{bom_review} BOM candidates and {quote_drafts} material draft records need review.',
        recommendation='Keep extracted BOM lines and material assignments as drafts until reviewed, then use approved rows to drive quote costing and lead-time assumptions.',
        workflow_key='bom-to-quote-review',
    ))

    open_quality = int(scalar(db, "SELECT COUNT(*) FROM quality_events WHERE status != 'closed'"))
    open_deviations = int(scalar(db, "SELECT COUNT(*) FROM deviations WHERE status != 'closed'"))
    fpy = float(scalar(db, "SELECT 100.0 * SUM(pieces_accepted_first_pass) / NULLIF(SUM(pieces_started),0) FROM fpy_summaries"))
    quality_score = min(100, open_quality * 12 + open_deviations * 10 + (0 if fpy == 0 or fpy >= 95 else int(95 - fpy) * 4))
    signals.append(IntelligenceSignal(
        area='Quality to Production',
        title='Quality load should influence planning and customer risk',
        severity=severity_from_score(quality_score),
        score=quality_score,
        source_tables=('quality_events', 'deviations', 'fpy_summaries', 'parts', 'customers', 'work_orders'),
        summary=f'{open_quality} open quality events, {open_deviations} open deviations, and FPY currently calculated at {fpy:.1f}% where data exists.',
        recommendation='Use open quality load, deviation status, and FPY weakness to flag customer, part, and work-order risk before committing dates.',
        workflow_key='quality-risk-review',
    ))

    morale_strain = int(scalar(db, """
        SELECT COALESCE(SUM(exhausted_pto_count),0)
             + COALESCE(SUM(unscheduled_absence_count),0)
             + COALESCE(SUM(unpaid_timeoff_count),0)
             + COALESCE(SUM(turnover_count),0)
        FROM morale_snapshots
    """))
    morale_score = min(100, morale_strain * 8)
    signals.append(IntelligenceSignal(
        area='Morale to QCDSM',
        title='Staffing strain should be treated as operational risk',
        severity=severity_from_score(morale_score),
        score=morale_score,
        source_tables=('morale_snapshots', 'departments', 'quality_events', 'fpy_summaries', 'planning_watchlists'),
        summary=f'Aggregate morale/staffing strain count is {morale_strain}.',
        recommendation='Use department-level strain as an explanatory signal for quality misses, late work, rework, and planning risk without exposing employee-level private data.',
        workflow_key='morale-risk-review',
    ))

    return sorted(signals, key=lambda item: item.score, reverse=True)


def build_workflow_definitions() -> list[WorkflowDefinition]:
    return [
        WorkflowDefinition(
            key='quote-lead-time-review',
            title='Quote Lead-Time Review',
            area='Quoting',
            purpose='Prevent quotes from promising impossible lead times when supplier performance or material availability has drifted.',
            trigger='A quote intake or quote material draft references a material with supplier lead-time risk.',
            steps=(
                'Review the quote intake due date and operating profile.',
                'Review selected material, approved supplier, standard length, and catalog lead time.',
                'Compare supplier quoted lead time against supplier actual average lead time.',
                'Check purchasing watchlists for the same supplier or material.',
                'Adjust the quote material draft lead-time estimate or flag it for buyer review.',
                'Keep the assignment in draft status until human review confirms the promise date.',
            ),
            required_review='Estimator or purchasing review before quote release.',
            output='Reviewed quote material draft with realistic lead-time notes.',
            source_tables=('quote_intakes', 'quote_material_drafts', 'materials', 'suppliers', 'supplier_performance_snapshots', 'purchasing_watchlists'),
            target_tables=('quote_material_drafts', 'dashboard_metric_snapshots'),
        ),
        WorkflowDefinition(
            key='capacity-risk-review',
            title='Capacity Risk Review',
            area='Planning',
            purpose='Expose machine/work-center overload before it turns into late delivery or quote failure.',
            trigger='Machine utilization is high, critical, or assigned to conflicting work.',
            steps=(
                'Review active work orders tied to the loaded machine or work center.',
                'Compare committed hours against available hours.',
                'Check due dates and customer priority.',
                'Create or update a planning watchlist item when capacity threatens delivery.',
                'Push quote or work-order assumptions later unless capacity is freed.',
            ),
            required_review='Planner or operations review before delivery date commitment.',
            output='Planning watchlist signal or revised lead-time assumption.',
            source_tables=('machine_assets', 'machine_utilization_snapshots', 'work_orders', 'quote_intakes'),
            target_tables=('planning_watchlists', 'dashboard_metric_snapshots'),
        ),
        WorkflowDefinition(
            key='material-cert-review',
            title='Material Certificate Review',
            area='Quality',
            purpose='Keep material traceability controlled before shipment, customer documentation, or quality response.',
            trigger='A material cert is uploaded or entered with needs_review, draft, or hold status.',
            steps=(
                'Confirm material, supplier, heat number, lot number, PO, and work-order linkage.',
                'Confirm certificate storage reference is present and readable.',
                'Review cert against material catalog requirements and customer requirements where applicable.',
                'Mark cert reviewed or keep it on hold with reviewer notes.',
                'Escalate to quality event or purchasing watchlist if the cert does not support the material claim.',
            ),
            required_review='Quality or authorized material reviewer approval.',
            output='Reviewed material certificate record with traceability references.',
            source_tables=('material_certificates', 'materials', 'suppliers', 'work_orders'),
            target_tables=('material_certificates', 'quality_events', 'purchasing_watchlists'),
        ),
        WorkflowDefinition(
            key='bom-to-quote-review',
            title='BOM to Quote Review',
            area='Quoting',
            purpose='Turn drawing/PDF BOM extraction into controlled quote inputs without silently trusting machine-extracted text.',
            trigger='PDF BOM candidates or quote material drafts are waiting for review.',
            steps=(
                'Review customer drawing reference and extracted BOM candidate line text.',
                'Confirm candidate part number, material guess, and quantity guess.',
                'Link to approved material catalog where confidence is acceptable.',
                'Create or revise quote material drafts with pieces, cost, standard length, and lead time.',
                'Complete BOM review before using the draft in a customer quote.',
            ),
            required_review='Estimator or engineering review before quote use.',
            output='Reviewed BOM and quote material draft records.',
            source_tables=('quote_intakes', 'pdf_bom_candidates', 'bom_reviews', 'materials'),
            target_tables=('bom_reviews', 'quote_material_drafts', 'dashboard_metric_snapshots'),
        ),
        WorkflowDefinition(
            key='quality-risk-review',
            title='Quality Risk Review',
            area='Quality',
            purpose='Connect RMAs, NCRs, DMRs, deviations, and FPY to customer, part, and work-order planning risk.',
            trigger='Open quality load, weak FPY, or open deviation status creates delivery/customer risk.',
            steps=(
                'Review open quality events and deviations by customer, part, and work order.',
                'Review FPY summaries for the same department, part, customer, or work center.',
                'Identify whether current work orders or quote intakes repeat the same risk pattern.',
                'Create planning or dashboard metric signals where quality load threatens delivery or cost.',
            ),
            required_review='Quality and operations review before customer-facing commitment changes.',
            output='Quality-informed planning or customer risk signal.',
            source_tables=('quality_events', 'deviations', 'fpy_summaries', 'parts', 'customers', 'work_orders'),
            target_tables=('planning_watchlists', 'dashboard_metric_snapshots'),
        ),
        WorkflowDefinition(
            key='morale-risk-review',
            title='Morale Risk Review',
            area='QCDSM',
            purpose='Treat aggregate staffing strain as an operational risk input without exposing private employee-level details.',
            trigger='Department-level overtime, PTO exhaustion, absence, unpaid time off, or turnover indicators rise.',
            steps=(
                'Review morale snapshot by department and period.',
                'Compare strain notes against quality events, FPY, planning watchlists, and machine utilization.',
                'Use aggregate signal as context for risk review, not as employee-level discipline data.',
                'Create dashboard metric snapshots when department strain may affect QCDSM performance.',
            ),
            required_review='Management or quality review using aggregate-only data.',
            output='Privacy-safe operational risk context for dashboard and management review.',
            source_tables=('morale_snapshots', 'departments', 'quality_events', 'fpy_summaries', 'planning_watchlists'),
            target_tables=('dashboard_metric_snapshots',),
        ),
    ]


def workflow_by_key(key: str) -> WorkflowDefinition | None:
    for workflow in build_workflow_definitions():
        if workflow.key == key:
            return workflow
    return None


def summarize_workflow_coverage(workflows: Iterable[WorkflowDefinition]) -> dict[str, int]:
    coverage: dict[str, int] = {}
    for workflow in workflows:
        for table in workflow.source_tables + workflow.target_tables:
            coverage[table] = coverage.get(table, 0) + 1
    return dict(sorted(coverage.items()))
