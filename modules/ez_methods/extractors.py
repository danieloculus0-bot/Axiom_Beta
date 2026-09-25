from __future__ import annotations

import re
from typing import Any

from .models import GDTCharacteristic, GDTControl, MaterialCondition, SourceReference


GDT_MAP = {
    "STRAIGHTNESS": GDTControl.STRAIGHTNESS,
    "FLATNESS": GDTControl.FLATNESS,
    "CIRCULARITY": GDTControl.CIRCULARITY,
    "CYLINDRICITY": GDTControl.CYLINDRICITY,
    "PROFILE": GDTControl.PROFILE_SURFACE,
    "PROFILE_OF_A_LINE": GDTControl.PROFILE_LINE,
    "PROFILE_OF_A_SURFACE": GDTControl.PROFILE_SURFACE,
    "ANGULARITY": GDTControl.ANGULARITY,
    "PERPENDICULARITY": GDTControl.PERPENDICULARITY,
    "PARALLELISM": GDTControl.PARALLELISM,
    "POSITION": GDTControl.POSITION,
    "TRUE_POSITION": GDTControl.POSITION,
    "RUNOUT": GDTControl.CIRCULAR_RUNOUT,
    "CIRCULAR_RUNOUT": GDTControl.CIRCULAR_RUNOUT,
    "TOTAL_RUNOUT": GDTControl.TOTAL_RUNOUT,
    "CONCENTRICITY": GDTControl.CONCENTRICITY_LEGACY,
    "SYMMETRY": GDTControl.SYMMETRY_LEGACY,
}

PO_KEYWORDS = {
    "FAI": ("FAI", "FIRST ARTICLE"),
    "PPAP": ("PPAP",),
    "MATERIAL_CERT": ("MATERIAL CERT", "MTR", "CMTR", "MILL CERT"),
    "TRACEABILITY": ("TRACEABILITY", "HEAT LOT", "HEAT/LOT", "LOT TRACE"),
    "COUNTRY_OF_ORIGIN": ("COUNTRY OF ORIGIN", "COO"),
    "SOURCE_INSPECTION": ("SOURCE INSPECTION", "CUSTOMER INSPECTION"),
    "SPECIAL_PROCESS": ("SPECIAL PROCESS", "NADCAP"),
    "PACKAGING": ("PACKAGING", "PACKING", "LABEL"),
    "CERT_OF_CONFORMANCE": ("CERTIFICATE OF CONFORMANCE", "CERT OF CONFORMANCE", "COC"),
    "NO_SUBSTITUTION": ("NO SUBSTITUTION", "NO SUBSTITUTIONS"),
}


def _blob(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(k) or "")
        for k in ("type", "raw_text", "comments", "source", "nearby")
    ).upper()


def _control_from_row(row: dict[str, Any]) -> GDTControl:
    text = _blob(row).replace("GD&T:", " ").replace(" ", "_")
    for key, control in GDT_MAP.items():
        if key in text:
            return control
    raise ValueError(f"Unsupported GD&T control in EZ FAIR row: {row!r}")


def _material_condition(text: str) -> MaterialCondition:
    upper = text.upper()
    if " MMC" in f" {upper}" or "MAXIMUM MATERIAL" in upper:
        return MaterialCondition.MMC
    if " LMC" in f" {upper}" or "LEAST MATERIAL" in upper:
        return MaterialCondition.LMC
    return MaterialCondition.RFS


def _datums(text: str) -> tuple[str, ...]:
    candidates = re.findall(r"(?:DATUMS?\s*[:=]?\s*|\|)([A-Z])(?:\||\s|$)", text.upper())
    deduped=[]
    for d in candidates:
        if d not in deduped:
            deduped.append(d)
    return tuple(deduped[:3])


def import_ez_fair_gdt(
    row: dict[str, Any],
    source: SourceReference,
    characteristic_id: str,
) -> GDTCharacteristic:
    """Convert an EZ FAIR characteristic into the richer EZ Methods GD&T record."""
    text = _blob(row)
    tolerance = float(
        row.get("tolerance")
        or row.get("Requirement USL")
        or row.get("usl")
        or row.get("nominal")
        or 0
    )
    return GDTCharacteristic(
        characteristic_id=characteristic_id,
        control=_control_from_row(row),
        tolerance=tolerance,
        source=source,
        datum_references=_datums(text),
        material_condition=_material_condition(text),
        diameter_zone=("Ø" in text or "DIAMETER ZONE" in text),
        tangent_plane=("TANGENT PLANE" in text),
        free_state=("FREE STATE" in text),
        all_around=("ALL AROUND" in text),
        all_over=("ALL OVER" in text),
        inspection_method=str(row.get("tooling") or row.get("Tooling Used") or "CMM / SURFACE PLATE"),
        gage_id=str(row.get("gage_id") or ""),
        notes=str(row.get("comments") or row.get("Comments") or ""),
    )


def extract_po_requirements(po_text: str) -> list[dict[str, str]]:
    """Extract high-value PO clauses without inventing acceptance criteria."""
    results=[]
    lines=[re.sub(r"\s+", " ", line).strip() for line in po_text.splitlines() if line.strip()]
    for line_no, line in enumerate(lines, start=1):
        upper=line.upper()
        for kind, phrases in PO_KEYWORDS.items():
            if any(p in upper for p in phrases):
                results.append({
                    "kind": kind,
                    "source": "CUSTOMER_PO",
                    "line": str(line_no),
                    "text": line,
                    "review_status": "REVIEW_REQUIRED",
                })
                break
    return results


def thread_method_instruction(
    supplier: str,
    supplier_part_number: str,
    hole_count: int,
    thread_size: str,
    drawing_number: str,
    sheet: str,
) -> str:
    return (
        f"Using {supplier} PN {supplier_part_number} tap, tap ({hole_count}) "
        f"{thread_size} holes as shown on DWG {drawing_number} Sht {sheet}."
    )
