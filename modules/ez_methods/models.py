from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


class DependencyKind(StrEnum):
    MATERIAL = "MATERIAL"
    TOOL = "TOOL"
    GAGE = "GAGE"
    FIXTURE = "FIXTURE"
    PURCHASED_COMPONENT = "PURCHASED_COMPONENT"
    CONSUMABLE = "CONSUMABLE"
    OUTSIDE_PROCESS = "OUTSIDE_PROCESS"
    DOCUMENT = "DOCUMENT"
    PROGRAM = "PROGRAM"


class AvailabilityState(StrEnum):
    UNKNOWN = "UNKNOWN"
    ON_HAND = "ON_HAND"
    REQUESTED = "REQUESTED"
    PO_PENDING = "PO_PENDING"
    ORDERED = "ORDERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIAL = "PARTIAL"
    RECEIVED = "RECEIVED"
    BLOCKED = "BLOCKED"


class PurchaseState(StrEnum):
    NEW = "NEW"
    REQUESTED = "REQUESTED"
    PO_PENDING = "PO_PENDING"
    ORDERED = "ORDERED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIAL = "PARTIAL"
    RECEIVED = "RECEIVED"
    CLOSED = "CLOSED"
    BLOCKED = "BLOCKED"


class MaterialCondition(StrEnum):
    RFS = "RFS"
    MMC = "MMC"
    LMC = "LMC"


class GDTControl(StrEnum):
    STRAIGHTNESS = "STRAIGHTNESS"
    FLATNESS = "FLATNESS"
    CIRCULARITY = "CIRCULARITY"
    CYLINDRICITY = "CYLINDRICITY"
    PROFILE_LINE = "PROFILE_OF_A_LINE"
    PROFILE_SURFACE = "PROFILE_OF_A_SURFACE"
    ANGULARITY = "ANGULARITY"
    PERPENDICULARITY = "PERPENDICULARITY"
    PARALLELISM = "PARALLELISM"
    POSITION = "POSITION"
    CIRCULAR_RUNOUT = "CIRCULAR_RUNOUT"
    TOTAL_RUNOUT = "TOTAL_RUNOUT"
    CONCENTRICITY_LEGACY = "CONCENTRICITY_LEGACY"
    SYMMETRY_LEGACY = "SYMMETRY_LEGACY"


@dataclass(slots=True)
class SourceReference:
    source_type: str
    document_number: str
    revision: str = ""
    sheet: str = ""
    page: int | None = None
    location: str = ""
    note: str = ""

    def label(self) -> str:
        bits = [self.document_number]
        if self.revision:
            bits.append(f"Rev {self.revision}")
        if self.sheet:
            bits.append(f"Sht {self.sheet}")
        return " ".join(bits)


@dataclass(slots=True)
class GDTCharacteristic:
    characteristic_id: str
    control: GDTControl
    tolerance: float
    source: SourceReference
    datum_references: tuple[str, ...] = ()
    material_condition: MaterialCondition = MaterialCondition.RFS
    basic_dimensions: tuple[str, ...] = ()
    diameter_zone: bool = False
    projected_tolerance_zone: float | None = None
    tangent_plane: bool = False
    free_state: bool = False
    all_around: bool = False
    all_over: bool = False
    inspection_method: str = ""
    gage_id: str = ""
    notes: str = ""


@dataclass(slots=True)
class OperationDependency:
    dependency_id: str
    kind: DependencyKind
    description: str
    required_qty: float
    need_by: date
    availability: AvailabilityState = AvailabilityState.UNKNOWN
    on_hand_qty: float = 0.0
    ordered_qty: float = 0.0
    promised_date: date | None = None
    supplier: str = ""
    supplier_part_number: str = ""
    internal_tool_id: str = ""
    purchase_order: str = ""
    owner: str = ""
    owner_email: str = ""
    next_action: str = ""
    source: SourceReference | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RoutingOperation:
    sequence: int
    work_center: str
    operation: str
    scheduled_date: date
    instruction: str
    source_references: list[SourceReference] = field(default_factory=list)
    dependencies: list[OperationDependency] = field(default_factory=list)
    characteristics: list[GDTCharacteristic] = field(default_factory=list)
    hold_point: bool = False
    controlled_operation: bool = False
    inspection_requirement: str = ""
    completion_fields: tuple[str, ...] = (
        "operator",
        "completed_at",
        "accepted_qty",
        "rejected_qty",
    )
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MethodPlan:
    job_number: str
    part_number: str
    revision: str
    customer: str
    quantity: float
    required_date: date
    operations: list[RoutingOperation] = field(default_factory=list)
    source_references: list[SourceReference] = field(default_factory=list)
    po_requirements: list[str] = field(default_factory=list)
    drawing_requirements: list[str] = field(default_factory=list)
    planning_notes: list[str] = field(default_factory=list)
