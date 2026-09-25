"""Offline extraction enhancements for EZ FAIR.

This module intentionally wraps the existing extractor instead of replacing it.
It adds:
- OCR fallback for scanned or flattened PDFs
- Saved title-block tolerance settings and bottom-right auto-detection
- Basic GD&T feature-control-frame recognition
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import fitz

from . import ezfair_engine as base

try:
    import pytesseract
    from PIL import Image
except ImportError:  # Optional at import time; explained clearly when OCR is needed.
    pytesseract = None
    Image = None

from ..runtime_paths import data_root

SETTINGS_PATH = data_root() / "ezfair_settings.json"


@dataclass
class ExtractionSettings:
    two_place: float = 0.02
    three_place: float = 0.005
    angular: float = 2.0
    auto_detect_title_block: bool = True
    enable_ocr_fallback: bool = True
    ocr_dpi: int = 300

    @classmethod
    def load(cls) -> "ExtractionSettings":
        if not SETTINGS_PATH.exists():
            return cls()
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            allowed = {field for field in cls.__dataclass_fields__}
            return cls(**{key: value for key, value in data.items() if key in allowed})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        SETTINGS_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


# Common Unicode symbols plus frequent CAD-font substitutions seen after PDF extraction.
GDT_SYMBOLS = {
    "⌖": "POSITION",
    "⏥": "FLATNESS",
    "∥": "PARALLELISM",
    "⌒": "PROFILE",
    "○": "CIRCULARITY",
    "◎": "CONCENTRICITY",
    "⌭": "CYLINDRICITY",
    "⟂": "PERPENDICULARITY",
    "∠": "ANGULARITY",
    "—": "STRAIGHTNESS",
}
GDT_WORD_PATTERN = re.compile(
    r"\b(TRUE\s+POSITION|POSITION|FLATNESS|PARALLELISM|PROFILE(?:\s+OF\s+(?:A\s+)?(?:LINE|SURFACE))?|"
    r"PERPENDICULARITY|ANGULARITY|STRAIGHTNESS|CIRCULARITY|CYLINDRICITY|CONCENTRICITY|RUNOUT)\b",
    re.I,
)
GDT_TOL_PATTERN = re.compile(r"(?:[Ø⌀]\s*)?(?P<tol>(?:\d+\.\d+|\.\d+))")
DATUM_PATTERN = re.compile(r"(?:^|[|\s])([A-Z])(?:[|\s]|$)")

# Title-block forms such as .XX ±.02, X.XX +/-.02, ANGLES ±2°.
TITLE_TOL_PATTERNS = {
    "three_place": [
        re.compile(r"(?:\.XXX|X\.XXX|3\s*PLACE\w*)\s*(?:=|:)?\s*(?:±|\+/-)\s*(\.?(?:\d+\.\d+|\d+))", re.I),
    ],
    "two_place": [
        re.compile(r"(?:\.XX|X\.XX|2\s*PLACE\w*)\s*(?:=|:)?\s*(?:±|\+/-)\s*(\.?(?:\d+\.\d+|\d+))", re.I),
    ],
    "angular": [
        re.compile(r"(?:ANGLE\w*|ANGULAR)\s*(?:=|:)?\s*(?:±|\+/-)\s*(\d+(?:\.\d+)?)", re.I),
    ],
}


def _apply_settings(settings: ExtractionSettings) -> None:
    base.TITLE_BLOCK_DEFAULTS.update(
        two_place=float(settings.two_place),
        three_place=float(settings.three_place),
        angular=float(settings.angular),
    )


def _page_ocr_words(page: fitz.Page, dpi: int) -> list[tuple[Any, ...]]:
    if pytesseract is None or Image is None:
        raise RuntimeError(
            "This PDF has no extractable vector text. Install pytesseract and Pillow, "
            "and install the offline Tesseract OCR engine, then retry."
        )
    scale = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT, config="--psm 11")
    words: list[tuple[Any, ...]] = []
    for index, text in enumerate(data.get("text", [])):
        text = str(text).strip()
        confidence = float(data["conf"][index]) if str(data["conf"][index]).strip() not in {"", "-1"} else -1
        if not text or confidence < 35:
            continue
        x = float(data["left"][index]) / scale
        y = float(data["top"][index]) / scale
        w = float(data["width"][index]) / scale
        h = float(data["height"][index]) / scale
        block = int(data.get("block_num", [0])[index])
        line = int(data.get("line_num", [0])[index])
        word = int(data.get("word_num", [index])[index])
        words.append((x, y, x + w, y + h, text, block, line, word))
    return words


def _ocr_nearby(words: list[tuple[Any, ...]], rect: fitz.Rect, radius: float = 72) -> str:
    clip = fitz.Rect(rect.x0 - radius, rect.y0 - radius, rect.x1 + radius, rect.y1 + radius)
    return " ".join(str(word[4]) for word in words if clip.intersects(base._word_rect(word)))


def _extract_from_ocr(pdf_path: Path, settings: ExtractionSettings) -> list[base.Characteristic]:
    characteristics: list[base.Characteristic] = []
    skipped: list[base.SkippedCandidate] = []
    seen: set[tuple[int, str, str, int, int]] = set()
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            words = _page_ocr_words(page, settings.ocr_dpi)
            for word_index, _word in enumerate(words):
                candidate_text, candidate_rect = base._dimension_candidate_from_words(words, word_index)
                candidate_text = candidate_text.replace("O", "0") if re.search(r"\d", candidate_text) else candidate_text
                if not base._looks_like_numeric_candidate(candidate_text):
                    continue
                nearby = _ocr_nearby(words, candidate_rect)
                line_text = base._line_text_for_word(words, word_index)
                reason = base._noise_reason(candidate_text, nearby)
                if reason:
                    base._record_skip(skipped, page_index, candidate_text, reason, candidate_rect, nearby)
                    continue
                match = base.DIMENSION_PATTERN.search(candidate_text)
                if not match:
                    continue
                raw = match.group(0).strip().replace("º", "°")
                number_text = match.group("num")
                try:
                    nominal = float(number_text)
                except ValueError:
                    continue
                if nominal <= 0:
                    continue
                dim_type = base.classify_dimension(raw)
                if dim_type == "LINEAR" and base.WELD_PATTERN.search(nearby):
                    dim_type = "WELD"
                key = (page_index, raw, dim_type, round(candidate_rect.x0 / 6), round(candidate_rect.y0 / 6))
                if key in seen:
                    continue
                seen.add(key)
                lsl, usl = base.calculate_tolerance_limits(nominal, number_text, dim_type, line_text)
                characteristics.append(base.Characteristic(
                    char_number=len(characteristics) + 1,
                    reference_location=base._reference_location(page, candidate_rect, page_index),
                    nominal=nominal,
                    lsl=lsl,
                    usl=usl,
                    type=dim_type,
                    page_index=page_index,
                    rect=(candidate_rect.x0, candidate_rect.y0, candidate_rect.x1, candidate_rect.y1),
                    raw_text=raw,
                    tooling=base.DEFAULT_TOOLING.get(dim_type, ""),
                    metadata={"source": line_text or candidate_text, "nearby": nearby, "drawing_name": pdf_path.stem, "extraction": "OCR"},
                ))
    base.LAST_EXTRACTION_DEBUG["skipped"] = skipped
    return characteristics


def detect_title_block_defaults(pdf_path: str | Path, settings: ExtractionSettings) -> dict[str, float]:
    detected: dict[str, float] = {}
    with fitz.open(pdf_path) as doc:
        for page in doc:
            clip = fitz.Rect(page.rect.width * 0.55, page.rect.height * 0.55, page.rect.width, page.rect.height)
            text = page.get_text("text", clip=clip)
            if not text.strip() and settings.enable_ocr_fallback and pytesseract is not None and Image is not None:
                words = _page_ocr_words(page, settings.ocr_dpi)
                text = " ".join(str(word[4]) for word in words if clip.intersects(base._word_rect(word)))
            normalized = text.replace("＋", "+").replace("−", "-")
            for key, patterns in TITLE_TOL_PATTERNS.items():
                if key in detected:
                    continue
                for pattern in patterns:
                    match = pattern.search(normalized)
                    if match:
                        detected[key] = float(match.group(1))
                        break
    return detected


def _gdt_name(text: str) -> str | None:
    for symbol, name in GDT_SYMBOLS.items():
        if symbol in text:
            return name
    word = GDT_WORD_PATTERN.search(text)
    if word:
        return re.sub(r"\s+", "_", word.group(1).upper())
    return None


def extract_gdt_characteristics(pdf_path: str | Path, start_number: int, settings: ExtractionSettings) -> list[base.Characteristic]:
    results: list[base.Characteristic] = []
    with fitz.open(pdf_path) as doc:
        for page_index, page in enumerate(doc):
            spans = list(base._iter_text_spans(page))
            if not spans and settings.enable_ocr_fallback and pytesseract is not None and Image is not None:
                ocr_words = _page_ocr_words(page, settings.ocr_dpi)
                spans = [{"text": word[4], "bbox": word[:4]} for word in ocr_words]
            for span in spans:
                text = str(span.get("text", "")).strip()
                name = _gdt_name(text)
                if not name:
                    continue
                rect = fitz.Rect(span["bbox"])
                nearby = base._nearby_text(page, rect, radius=120) or text
                tolerance_match = GDT_TOL_PATTERN.search(nearby)
                if not tolerance_match:
                    continue
                tolerance = float(tolerance_match.group("tol"))
                datums = DATUM_PATTERN.findall(nearby)
                datum_note = f" Datums: {'-'.join(datums[:3])}" if datums else ""
                results.append(base.Characteristic(
                    char_number=start_number + len(results),
                    reference_location=base._reference_location(page, rect, page_index),
                    nominal=tolerance,
                    lsl=0.0,
                    usl=tolerance,
                    type=f"GD&T: {name}",
                    page_index=page_index,
                    rect=(rect.x0, rect.y0, rect.x1, rect.y1),
                    raw_text=nearby[:160],
                    tooling="CMM / SURFACE PLATE",
                    comments=f"Feature control frame tolerance.{datum_note}".strip(),
                    metadata={"source": text, "nearby": nearby, "drawing_name": Path(pdf_path).stem, "extraction": "GD&T"},
                ))
    return results


def extract_pdf_dimensions_enhanced(pdf_path: str | Path, settings: ExtractionSettings | None = None) -> list[base.Characteristic]:
    settings = settings or ExtractionSettings.load()
    if settings.auto_detect_title_block:
        detected = detect_title_block_defaults(pdf_path, settings)
        for key, value in detected.items():
            setattr(settings, key, value)
    _apply_settings(settings)

    characteristics = base.extract_pdf_dimensions(pdf_path)
    vector_count = len(characteristics)
    if vector_count == 0 and settings.enable_ocr_fallback:
        characteristics = _extract_from_ocr(Path(pdf_path), settings)

    gdt = extract_gdt_characteristics(pdf_path, len(characteristics) + 1, settings)
    characteristics.extend(gdt)
    for index, characteristic in enumerate(characteristics, start=1):
        characteristic.char_number = index
        characteristic.metadata.setdefault("title_block_defaults", {
            "two_place": settings.two_place,
            "three_place": settings.three_place,
            "angular": settings.angular,
        })
        characteristic.metadata.setdefault("vector_characteristics", vector_count)
    return characteristics
