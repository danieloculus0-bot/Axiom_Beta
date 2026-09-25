from datetime import date

from modules.ez_methods.engine import evaluate_dependency, evaluate_operation_readiness
from modules.ez_methods.models import (
    AvailabilityState,
    DependencyKind,
    OperationDependency,
    RoutingOperation,
    SourceReference,
)


def test_fastenal_tap_is_blocked_when_promised_after_operation():
    source = SourceReference("DRAWING", "33344455", sheet="2")
    tap = OperationDependency(
        dependency_id="TOOL-FASTENAL-12345678",
        kind=DependencyKind.TOOL,
        description="Fastenal PN 12345678 5/16-18 tap",
        required_qty=1,
        ordered_qty=1,
        need_by=date(2026, 10, 3),
        promised_date=date(2026, 10, 4),
        availability=AvailabilityState.ACKNOWLEDGED,
        supplier="Fastenal",
        supplier_part_number="12345678",
        source=source,
    )
    result = evaluate_dependency(tap, as_of=date(2026, 9, 24))
    assert result["status"] == "BLOCKED"
    assert result["days_margin"] == -1


def test_material_and_tap_both_gate_operation_readiness():
    source = SourceReference("DRAWING", "33344455", sheet="2")
    material = OperationDependency(
        dependency_id="MAT-A36-7GA",
        kind=DependencyKind.MATERIAL,
        description="A36 7ga sheet",
        required_qty=1,
        on_hand_qty=1,
        need_by=date(2026, 10, 3),
        availability=AvailabilityState.ON_HAND,
        source=source,
    )
    tap = OperationDependency(
        dependency_id="TOOL-FASTENAL-12345678",
        kind=DependencyKind.TOOL,
        description="Fastenal PN 12345678 5/16-18 tap",
        required_qty=1,
        ordered_qty=1,
        need_by=date(2026, 10, 3),
        promised_date=date(2026, 10, 2),
        availability=AvailabilityState.ACKNOWLEDGED,
        supplier="Fastenal",
        supplier_part_number="12345678",
        source=source,
    )
    op = RoutingOperation(
        sequence=50,
        work_center="MACHINING",
        operation="DRILL / TAP",
        scheduled_date=date(2026, 10, 3),
        instruction="Using Fastenal PN 12345678 tap, tap (7) 5/16-18 holes as shown on DWG 33344455 Sht 2.",
        dependencies=[material, tap],
    )
    result = evaluate_operation_readiness(op, as_of=date(2026, 9, 24))
    assert result["status"] == "PLANNED"
    assert not result["blockers"]
