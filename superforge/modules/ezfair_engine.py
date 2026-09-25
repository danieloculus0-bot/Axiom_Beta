"""EZ-FAIR extraction engine.

This module is the production-facing extractor used by the polished GUI and the
local runner. It is intentionally local-only and text-PDF based. It does not use
OCR and it does not upload drawings.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import fitz  # PyMuPDF

TITLE_BLOCK_DEFAULTS = {
    "two_place": 0.02,
    "three_place": 0.005,
    "angular": 2.0,
    "whole_number": 0.02,
}

DEFAULT_TOOLING = {
    "LINEAR": "CALIPER",
    "Ø": "CALIPER",
    "°": "ANGLE GAGE",
    "WELD": "VISUAL",
}

# Pull every dimension-looking value on a line, not just one word. This catches
# common misses like WIDTH 20 LENGTH 10, 1.50 X 4.00, Ø.266 THRU, and 45°.
DIMENSION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<prefix>[Ø⌀Rr]?\s*)"
    r"(?P<num>(?:\d+\.\d+|\.\d+|\d+))"
    r"(?P<suffix>\s*(?:°|º|deg\.?|DEG\.?)?)"
    r"(?![A-Za-z0-9])"
)

TOLERANCE_PATTERN = re.compile(
    r"\+\s*(?P<plus>\.?\d+(?:\.\d+)?)\s*/?\s*-\s*(?P<minus>\.?\d+(?:\.\d+)?)",
    re.I,
)
WELD_PATTERN = re.compile(r"(?:\bWELD(?:MENT|ED|ING)?\b|\bFILLET\b|\bSEAM\b|\bBEAD\b|[⌒⏊△])", re.I)
DIMENSION_CONTEXT_PATTERN = re.compile(
    r"\b(?:WIDTH|LENGTH|HEIGHT|DEPTH|DIM|SIZE|DIA|DIAMETER|RADIUS|RAD|HOLE|SLOT|THRU|TYP|PLCS?|PLACE|BEND|FLANGE|LEG|OD|ID|REF|TRUE\s+POSITION|PROFILE|FLATNESS|PERPENDICULARITY|PARALLELISM)\b|[Ø⌀°º±]",
    re.I,
)
ADMIN_OR_TITLE_PATTERN = re.compile(
    r"\b(?:DATE|DWG|DRAWING|DRAWN|CHECKED|APPROVED|REV|REVISION|SHEET|PAGE|PHONE|FAX|ZIP|SCALE|TITLE|CAGE|PART\s*NO|PART\s*NUMBER|MATERIAL|FINISH|QTY|QUANTITY|PO|PURCHASE\s*ORDER|ORDER\s*(?:NO|NUMBER|#)|INSPECTOR|ITEM\s*(?:NO|NUMBER|#)|REASON)\b",
    re.I,
)
DATE_LIKE_PATTERN = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
FRACTION_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?P<num>\d+)\s*/\s*(?P<den>\d+)(?![A-Za-z0-9])")


@dataclass
class Characteristic:
    char_number: int
    reference_location: str
    nominal: float
    lsl: float
    usl: float
    type: str
    page_index: int
    rect: tuple[float, float, float, float]
    raw_text: str = ""
    tooling: str = ""
    comments: str = ""
    actual: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "Char Number": self.char_number,
            "Reference Location": self.reference_location,
            "Requirement LSL": self.lsl,
            "Requirement Nominal": self.nominal,
            "Requirement USL": self.usl,
            "Type": self.type,
            "EZ Fabricating Actual": self.actual,
            "Tooling Used": self.tooling,
            "Comments": self.comments,
        }


@dataclass
class SkippedCandidate:
    page_index: int
    raw_text: str
    reason: str
    rect: tuple[float, float, float, float]
    context: str = ""


LAST_EXTRACTION_DEBUG: dict[str, list[SkippedCandidate]] = {"skipped": []}


def get_last_skipped_candidates() -> list[SkippedCandidate]:
    return list(LAST_EXTRACTION_DEBUG.get("skipped", []))


def classify_dimension(text: str) -> str:
    text = text or ""
    if "°" in text or "º" in text or re.search(r"\bdeg\.?\b", text, re.I):
        return "°"
    if "Ø" in text or "⌀" in text:
        return "Ø"
    if WELD_PATTERN.search(text):
        return "WELD"
    return "LINEAR"


def _decimal_places(value_text: str) -> int:
    return len(value_text.split(".", 1)[1]) if "." in value_text else 0


def calculate_tolerance_limits(nominal: float, value_text: str, dim_type: str, context: str = "") -> tuple[float, float]:
    tolerance_match = TOLERANCE_PATTERN.search(context or "")
    if tolerance_match:
        plus = float(tolerance_match.group("plus"))
        minus = float(tolerance_match.group("minus"))
        return round(nominal - minus, 6), round(nominal + plus, 6)

    if dim_type == "°":
        tol = TITLE_BLOCK_DEFAULTS["angular"]
    elif _decimal_places(value_text) >= 3:
        tol = TITLE_BLOCK_DEFAULTS["three_place"]
    elif _decimal_places(value_text) == 0:
        tol = TITLE_BLOCK_DEFAULTS["whole_number"]
    else:
        tol = TITLE_BLOCK_DEFAULTS["two_place"]
    return round(nominal - tol, 6), round(nominal + tol, 6)


def _reference_location(page: fitz.Page, rect: fitz.Rect, page_index: int) -> str:
    width, height = page.rect.width, page.rect.height
    col = min(4, max(1, int(rect.x0 / max(width / 4, 1)) + 1))
    row = min(4, max(1, int(rect.y0 / max(height / 4, 1)) + 1))
    return f"P{page_index + 1}-R{row}C{col}"


def _nearby_text(page: fitz.Page, rect: fitz.Rect, radius: float = 72) -> str:
    clip = fitz.Rect(rect.x0 - radius, rect.y0 - radius, rect.x1 + radius, rect.y1 + radius) & page.rect
    return " ".join(page.get_text("text", clip=clip).split())


def _record_skip(skipped: list[SkippedCandidate], page_index: int, raw_text: str, reason: str, rect: fitz.Rect, context: str = "") -> None:
    skipped.append(
        SkippedCandidate(
            page_index=page_index,
            raw_text=str(raw_text).strip(),
            reason=reason,
            rect=(round(rect.x0, 3), round(rect.y0, 3), round(rect.x1, 3), round(rect.y1, 3)),
            context=" ".join((context or "").split())[:240],
        )
    )


def _line_groups(page: fitz.Page) -> Iterable[tuple[str, fitz.Rect, list[tuple[Any, ...]]]]:
    groups: dict[tuple[int, int], list[tuple[Any, ...]]] = {}
    for word in page.get_text("words", sort=True):
        groups.setdefault((int(word[5]), int(word[6])), []).append(word)
    for words in groups.values():
        words = sorted(words, key=lambda w: (float(w[0]), float(w[1])))
        text = " ".join(str(w[4]).strip() for w in words if str(w[4]).strip())
        if not text:
            continue
        rect = fitz.Rect(float(words[0][0]), float(words[0][1]), float(words[0][2]), float(words[0][3]))
        for word in words[1:]:
            rect |= fitz.Rect(float(word[0]), float(word[1]), float(word[2]), float(word[3]))
        yield text, rect, words


def _iter_text_spans(page: fitz.Page) -> Iterable[tuple[str, fitz.Rect]]:
    page_dict = page.get_text("dict")
    for block in page_dict.get("blocks", []):
        for line in block.get("lines", []):
            pieces = [span.get("text", "") for span in line.get("spans", []) if span.get("text", "").strip()]
            if not pieces:
                continue
            rect: fitz.Rect | None = None
            for span in line.get("spans", []):
                if not span.get("text", "").strip():
                    continue
                span_rect = fitz.Rect(span["bbox"])
                rect = span_rect if rect is None else rect | span_rect
            if rect is not None:
                yield " ".join(" ".join(pieces).split()), rect


def _match_rect_from_words(line_text: str, line_rect: fitz.Rect, words: list[tuple[Any, ...]], match: re.Match[str]) -> fitz.Rect:
    raw = match.group(0).strip()
    number = match.group("num")
    search_values = [raw, number]
    for value in search_values:
        clean_value = value.replace(" ", "")
        for word in words:
            word_text = str(word[4]).strip().replace(" ", "")
            if clean_value and clean_value in word_text:
                return fitz.Rect(float(word[0]), float(word[1]), float(word[2]), float(word[3]))
    # Approximate by character position when PyMuPDF tokenized oddly.
    ratio0 = match.start() / max(len(line_text), 1)
    ratio1 = match.end() / max(len(line_text), 1)
    x0 = line_rect.x0 + (line_rect.width * ratio0)
    x1 = line_rect.x0 + (line_rect.width * ratio1)
    if x1 <= x0:
        x1 = x0 + 12
    return fitz.Rect(x0, line_rect.y0, x1, line_rect.y1)


def _has_decimal(value_text: str) -> bool:
    return "." in value_text


def _is_count_prefix(line_text: str, match: re.Match[str]) -> bool:
    raw = match.group(0).strip()
    value = match.group("num")
    after = line_text[match.end(): match.end() + 18]
    before = line_text[max(0, match.start() - 3): match.start()]
    if not value.isdigit():
        return False
    if re.search(r"^\s*[Xx]\s*(?:[Ø⌀Rr]|\.?\d)", after):
        return True
    if re.search(r"\b(?:PLCS?|PLACES?|TYP)\b", after, re.I):
        return True
    if before.strip().endswith("#"):
        return True
    if int(value) <= 12 and re.search(r"[Ø⌀]|\b(?:HOLE|SLOT|THRU|PLCS?|PLACES?)\b", line_text, re.I):
        return True
    return False


def _noise_reason(raw: str, value_text: str, line_text: str, nearby: str, page_rect: fitz.Rect, rect: fitz.Rect) -> str:
    raw = raw.strip()
    combined = f"{raw} {line_text} {nearby}"
    if raw.startswith(("+", "-")):
        return "explicit tolerance component, not a standalone characteristic"
    if DATE_LIKE_PATTERN.search(combined):
        return "date-like text"
    if value_text.isdigit() and 1900 <= int(value_text) <= 2099 and not DIMENSION_CONTEXT_PATTERN.search(line_text):
        return "year-like value"
    if len(re.sub(r"\D", "", raw)) >= 7:
        return "long numeric identifier"
    if ADMIN_OR_TITLE_PATTERN.search(line_text) and not DIMENSION_CONTEXT_PATTERN.search(line_text):
        return "title block / admin / non-dimensional context"
    if re.search(r"\b(?:SHEET|PAGE)\s+\d+\s+(?:OF|/)\s+\d+\b", line_text, re.I):
        return "sheet/page count"
    if value_text.isdigit() and not DIMENSION_CONTEXT_PATTERN.search(line_text):
        # Whole-number dimensions are useful, but only when the line looks like a
        # dimension line. This avoids drawing numbers, revision tables, and dates.
        if len(value_text) <= 1:
            return "single digit with no dimension context"
        if int(value_text) > 500:
            return "large whole number with no dimension context"
        # Allow likely drawing-area whole numbers even without labels; true false
        # positives still show in the review table and can be deleted.
    if classify_dimension(raw) == "LINEAR" and float(value_text) > 1000:
        return "large linear value likely not a part dimension"
    return ""


def _add_characteristic(
    characteristics: list[Characteristic],
    seen: set[tuple[int, str, str, int, int]],
    skipped: list[SkippedCandidate],
    page: fitz.Page,
    page_index: int,
    raw: str,
    value_text: str,
    rect: fitz.Rect,
    line_text: str,
    nearby: str,
    default_comment: str,
) -> None:
    raw = raw.replace("º", "°").replace("⌀", "Ø").strip()
    if raw.upper().startswith("R") and not raw.startswith("R"):
        raw = "R" + raw[1:]
    try:
        nominal = float(value_text)
    except ValueError:
        _record_skip(skipped, page_index, raw, "not numeric after parsing", rect, nearby)
        return
    if nominal <= 0:
        _record_skip(skipped, page_index, raw, "zero or negative nominal", rect, nearby)
        return
    reason = _noise_reason(raw, value_text, line_text, nearby, page.rect, rect)
    if reason:
        _record_skip(skipped, page_index, raw, reason, rect, nearby)
        return

    dim_type = classify_dimension(raw)
    if dim_type == "LINEAR" and WELD_PATTERN.search(f"{line_text} {nearby}"):
        dim_type = "WELD"
    key = (page_index, dim_type, f"{nominal:.6f}", round(rect.x0 / 5), round(rect.y0 / 5))
    if key in seen:
        _record_skip(skipped, page_index, raw, "duplicate candidate at same location", rect, nearby)
        return
    seen.add(key)
    lsl, usl = calculate_tolerance_limits(nominal, value_text, dim_type, line_text)
    characteristics.append(
        Characteristic(
            char_number=len(characteristics) + 1,
            reference_location=_reference_location(page, rect, page_index),
            nominal=nominal,
            lsl=lsl,
            usl=usl,
            type=dim_type,
            page_index=page_index,
            rect=(rect.x0, rect.y0, rect.x1, rect.y1),
            raw_text=raw,
            tooling=DEFAULT_TOOLING.get(dim_type, "CALIPER"),
            comments=default_comment,
            metadata={"source": line_text, "nearby": nearby, "drawing_name": ""},
        )
    )


def _extract_matches_from_line(
    page: fitz.Page,
    page_index: int,
    line_text: str,
    line_rect: fitz.Rect,
    words: list[tuple[Any, ...]],
    default_comment: str,
    characteristics: list[Characteristic],
    skipped: list[SkippedCandidate],
    seen: set[tuple[int, str, str, int, int]],
) -> None:
    if not line_text.strip():
        return
    for match in DIMENSION_PATTERN.finditer(line_text):
        raw = match.group(0).strip()
        value_text = match.group("num")
        if _is_count_prefix(line_text, match):
            _record_skip(skipped, page_index, raw, "quantity/count prefix, not a standalone dimension", line_rect, line_text)
            continue
        has_decimal = _has_decimal(value_text)
        has_dim_symbol = bool(match.group("prefix").strip() in {"Ø", "⌀", "R", "r"} or match.group("suffix").strip())
        has_context = bool(DIMENSION_CONTEXT_PATTERN.search(line_text))
        has_explicit_tol = bool(TOLERANCE_PATTERN.search(line_text))
        if not (has_decimal or has_dim_symbol or has_context or has_explicit_tol):
            _record_skip(skipped, page_index, raw, "no decimal or dimension context", line_rect, line_text)
            continue
        rect = _match_rect_from_words(line_text, line_rect, words, match)
        nearby = _nearby_text(page, rect)
        _add_characteristic(characteristics, seen, skipped, page, page_index, raw, value_text, rect, line_text, nearby, default_comment)

    # Fractional fabrication notes occasionally show up as 3/16 or 1/4. Keep
    # them only when the line clearly reads dimensional.
    if DIMENSION_CONTEXT_PATTERN.search(line_text):
        for match in FRACTION_PATTERN.finditer(line_text):
            numerator = int(match.group("num"))
            denominator = int(match.group("den"))
            if denominator == 0 or numerator >= denominator * 12:
                continue
            nominal = numerator / denominator
            rect = fitz.Rect(line_rect)
            raw = match.group(0)
            _add_characteristic(characteristics, seen, skipped, page, page_index, raw, f"{nominal:.4f}", rect, line_text, _nearby_text(page, rect), default_comment)


def extract_pdf_dimensions(pdf_path: str | Path) -> list[Characteristic]:
    pdf_path = Path(pdf_path)
    characteristics: list[Characteristic] = []
    skipped: list[SkippedCandidate] = []
    seen: set[tuple[int, str, str, int, int]] = set()

    with fitz.open(pdf_path) as doc:
        full_text = "\n".join(page.get_text("text") for page in doc)
        default_comment = "AFTER GALVANIZE" if re.search(r"galvani[sz]e", full_text, re.I) else ""

        for page_index, page in enumerate(doc):
            used_lines: set[tuple[int, int, int, int]] = set()
            for line_text, line_rect, words in _line_groups(page):
                used_lines.add((round(line_rect.x0), round(line_rect.y0), round(line_rect.x1), round(line_rect.y1)))
                _extract_matches_from_line(page, page_index, line_text, line_rect, words, default_comment, characteristics, skipped, seen)

            # Some CAD PDFs expose weird spans but poor word data. Use span lines
            # as a fallback, deduped by location.
            for span_text, span_rect in _iter_text_spans(page):
                span_key = (round(span_rect.x0), round(span_rect.y0), round(span_rect.x1), round(span_rect.y1))
                if span_key in used_lines:
                    continue
                _extract_matches_from_line(page, page_index, span_text, span_rect, [], default_comment, characteristics, skipped, seen)

    for idx, characteristic in enumerate(characteristics, start=1):
        characteristic.char_number = idx
        characteristic.metadata["drawing_name"] = pdf_path.stem
    LAST_EXTRACTION_DEBUG["skipped"] = skipped
    return characteristics


def _balloon_position(page: fitz.Page, rect: fitz.Rect, radius: float, occupied: list[fitz.Rect] | None = None) -> fitz.Point:
    occupied = occupied or []
    offsets = [
        (radius * 2.4, -radius * 0.4),
        (-radius * 2.4, -radius * 0.4),
        (radius * 2.2, radius * 1.8),
        (-radius * 2.2, radius * 1.8),
        (radius * 0.4, -radius * 2.4),
        (radius * 0.4, radius * 2.4),
        (radius * 3.4, 0),
        (-radius * 3.4, 0),
    ]
    anchors = [fitz.Point(rect.x1, rect.y0), fitz.Point(rect.x0, rect.y0), fitz.Point(rect.x1, rect.y1), fitz.Point(rect.x0, rect.y1)]
    for anchor in anchors:
        for dx, dy in offsets:
            point = fitz.Point(anchor.x + dx, anchor.y + dy)
            circle = fitz.Rect(point.x - radius, point.y - radius, point.x + radius, point.y + radius)
            if not page.rect.contains(circle):
                continue
            if circle.intersects(rect):
                continue
            if any(circle.intersects(existing) for existing in occupied):
                continue
            return point
    return fitz.Point(
        min(max(rect.x1 + radius, radius), page.rect.width - radius),
        min(max(rect.y0, radius), page.rect.height - radius),
    )


def add_pdf_balloons(pdf_path: str | Path, characteristics: list[Characteristic], output_path: str | Path | None = None) -> Path:
    pdf_path = Path(pdf_path)
    output_path = Path(output_path) if output_path else pdf_path.with_name(f"{pdf_path.stem}_BALLOONED.pdf")
    if output_path.resolve() == pdf_path.resolve():
        raise ValueError("Ballooned PDF output cannot overwrite the original PDF.")

    with fitz.open(pdf_path) as doc:
        occupied_by_page: dict[int, list[fitz.Rect]] = {}
        for characteristic in characteristics:
            if characteristic.page_index >= len(doc):
                continue
            page = doc[characteristic.page_index]
            rect = fitz.Rect(characteristic.rect)
            radius = 10
            occupied = occupied_by_page.setdefault(characteristic.page_index, [])
            center = _balloon_position(page, rect, radius, occupied)
            circle = fitz.Rect(center.x - radius, center.y - radius, center.x + radius, center.y + radius)
            page.draw_oval(circle, color=(1, 0, 0), fill=(1, 1, 1), width=1.1)
            page.insert_textbox(
                circle,
                str(characteristic.char_number),
                fontsize=7.5,
                fontname="helv",
                color=(1, 0, 0),
                align=fitz.TEXT_ALIGN_CENTER,
            )
            page.draw_line(fitz.Point(center.x - radius, center.y), fitz.Point(rect.x0, rect.y0), color=(1, 0, 0), width=0.55)
            occupied.append(circle + (-3, -3, 3, 3))
        doc.save(output_path, garbage=4, deflate=True)
    return output_path


def write_debug_report(
    pdf_path: str | Path,
    template_path: str | Path,
    characteristics: list[Characteristic],
    output_path: str | Path | None = None,
    skipped_candidates: list[SkippedCandidate] | None = None,
) -> Path:
    pdf_path = Path(pdf_path)
    template_path = Path(template_path)
    output_path = Path(output_path) if output_path else pdf_path.with_name("EZ_FAI_DEBUG_REPORT.txt")
    skipped_candidates = skipped_candidates if skipped_candidates is not None else get_last_skipped_candidates()

    lines = [
        "EZ FAI Builder Debug Report",
        "===========================",
        f"PDF file used: {pdf_path}",
        f"Template file used: {template_path}",
        f"Number of extracted characteristics: {len(characteristics)}",
        "",
        "Extracted characteristics:",
    ]
    if not characteristics:
        lines.append("  (none)")
    for characteristic in characteristics:
        lines.extend(
            [
                f"  Char {characteristic.char_number}",
                f"    page: {characteristic.page_index + 1}",
                f"    reference location: {characteristic.reference_location}",
                f"    raw text: {characteristic.raw_text}",
                f"    nominal: {characteristic.nominal}",
                f"    LSL: {characteristic.lsl}",
                f"    USL: {characteristic.usl}",
                f"    type: {characteristic.type}",
                f"    tooling: {characteristic.tooling}",
                f"    comments: {characteristic.comments}",
                f"    PDF coordinate: {tuple(round(v, 3) for v in characteristic.rect)}",
                f"    source: {characteristic.metadata.get('source', '')}",
            ]
        )

    lines.extend(["", "Skipped dimension candidates:"])
    if not skipped_candidates:
        lines.append("  (none)")
    for skipped in skipped_candidates:
        lines.extend(
            [
                f"  page {skipped.page_index + 1}: {skipped.raw_text}",
                f"    reason: {skipped.reason}",
                f"    PDF coordinate: {skipped.rect}",
                f"    context: {skipped.context}",
            ]
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
