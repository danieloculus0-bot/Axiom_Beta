import re
from datetime import datetime
from pathlib import Path

from flask import redirect, request
from werkzeug.utils import secure_filename

import capa_assistant
import material_quote_engine
import pulse_intelligence
import quality_forms
import quality_workflow
import ui_context_menu
import erp_integration
import server_features
from material_quote_engine import QuoteMaterialAssignment, resolve_material_assignment
from runtime_paths import uploads_dir
from forgeqc_app import (
    Customer,
    db,
    get_or_create,
    log,
    page,
    as_float,
    create_app as create_base_app,
)


class QuoteResource(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    quote_number = db.Column(db.String(120), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"))
    part_number = db.Column(db.String(160))
    part_description = db.Column(db.String(260))
    quote_length = db.Column(db.Float, default=0)
    drawing_filename = db.Column(db.String(260))
    drawing_path = db.Column(db.String(600))
    status = db.Column(db.String(80), default="BOM Review Needed")
    bom_upload_id = db.Column(db.Integer, db.ForeignKey("bom_upload.id"))
    notes = db.Column(db.Text)

    customer = db.relationship("Customer")


class BOMUpload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    source = db.Column(db.String(80), default="Quoting Drawing")
    source_filename = db.Column(db.String(260), nullable=False)
    stored_path = db.Column(db.String(600), nullable=False)
    extraction_status = db.Column(db.String(80), default="Extracted")
    extraction_notes = db.Column(db.Text)


class BOMLine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    upload_id = db.Column(db.Integer, db.ForeignKey("bom_upload.id"))
    item_no = db.Column(db.String(80))
    part_number = db.Column(db.String(160))
    description = db.Column(db.Text)
    material = db.Column(db.String(180))
    quantity = db.Column(db.Float, default=0)
    revision = db.Column(db.String(80))
    confidence = db.Column(db.Float, default=0)
    approved = db.Column(db.Boolean, default=False)
    raw_text = db.Column(db.Text)

    upload = db.relationship("BOMUpload")


def extract_pdf_text(path):
    try:
        import fitz
    except Exception as exc:
        return "", f"PyMuPDF unavailable: {exc}"
    try:
        chunks = []
        with fitz.open(path) as doc:
            for p in doc:
                chunks.append(p.get_text("text"))
        text = "\n".join(chunks).strip()
        if not text:
            return "", "No extractable text found. Scanned drawings will need OCR later."
        return text, ""
    except Exception as exc:
        return "", f"PDF parse failed: {exc}"


def likely_bom_line(line):
    s = re.sub(r"\s+", " ", line).strip()
    if len(s) < 6:
        return False
    if re.search(r"\b(item|qty|quantity|description|material|revision|part\s*(no|number))\b", s, re.I):
        return False
    has_item = bool(re.match(r"^\d{1,4}\s+", s))
    has_qty = bool(re.search(r"(?:^|\s)\d+(?:\.\d+)?(?:\s|$)", s))
    has_part = bool(re.search(r"[A-Z0-9]{2,}[-_/][A-Z0-9][A-Z0-9._\-\/]*", s, re.I))
    return has_qty and (has_item or has_part)


def parse_bom_candidates(text):
    rows = []
    material_markers = ["steel", "alum", "aluminum", "stainless", "brass", "copper", "plastic", "poly", "rubber", "galv", "crs", "hrs", "sheet", "plate", "tube", "angle", "flat", "bar"]
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if not likely_bom_line(line):
            continue
        tokens = line.split(" ")
        item_no = ""
        if tokens and re.fullmatch(r"\d{1,4}", tokens[0]):
            item_no = tokens.pop(0)
        quantity = 0.0
        qty_index = None
        for idx in range(len(tokens) - 1, -1, -1):
            if re.fullmatch(r"\d+(?:\.\d+)?", tokens[idx]):
                quantity = float(tokens[idx]); qty_index = idx; break
        if qty_index is not None:
            tokens.pop(qty_index)
        part_number = ""
        part_index = None
        for idx, token in enumerate(tokens):
            cleaned = token.strip(",;:()[]")
            if re.search(r"[A-Z0-9]{2,}[-_/][A-Z0-9][A-Z0-9._\-\/]*", cleaned, re.I):
                part_number = cleaned; part_index = idx; break
        if part_index is not None:
            tokens.pop(part_index)
        elif tokens:
            part_number = tokens.pop(0).strip(",;:()[]")
        revision = ""
        for idx, token in enumerate(list(tokens)):
            cleaned = token.strip(",;:()[]")
            if re.fullmatch(r"(?:REV)?[A-Z]\d*", cleaned, re.I):
                revision = cleaned; tokens.pop(idx); break
        material_words = []
        description_words = []
        for token in tokens:
            if any(marker in token.lower() for marker in material_markers):
                material_words.append(token)
            else:
                description_words.append(token)
        confidence = 0.35 + (0.15 if item_no else 0) + (0.25 if part_number else 0) + (0.15 if quantity else 0) + (0.10 if description_words else 0) + (0.10 if material_words else 0)
        rows.append({"item_no": item_no, "part_number": part_number, "description": " ".join(description_words), "material": " ".join(material_words), "quantity": quantity, "revision": revision, "confidence": min(round(confidence, 2), 0.95), "raw_text": line})
    return rows


def material_lookup_text(line):
    return " ".join(str(x or "") for x in [line.material, line.description, line.part_number]).strip()


def create_bom_from_pdf(pdf_path, source_filename, source="Quoting Drawing", quote_id=None, quote_length=0):
    text, error = extract_pdf_text(pdf_path)
    rows = parse_bom_candidates(text) if text else []
    upload = BOMUpload(source=source, source_filename=source_filename, stored_path=str(pdf_path), extraction_status="Review Needed" if rows else "No BOM Found", extraction_notes=error or f"Extracted {len(rows)} candidate BOM line(s).")
    db.session.add(upload); db.session.flush()
    assignment_count = 0
    for row in rows:
        bom_line = BOMLine(upload_id=upload.id, **row)
        db.session.add(bom_line); db.session.flush()
        if quote_id:
            key = material_lookup_text(bom_line)
            if key:
                resolve_material_assignment(quote_id=quote_id, bom_line_id=bom_line.id, material_key=key, required_qty=bom_line.quantity or 1, quote_length=quote_length or 0)
                assignment_count += 1
    if quote_id:
        upload.extraction_notes = (upload.extraction_notes or "") + f" Auto-created {assignment_count} material assignment draft(s)."
    return upload, rows


def create_app():
    ui_context_menu.install()
    quality_workflow.install_ui()
    server_features.install_ui()
    app = create_base_app()
    material_quote_engine.register(app)
    quality_forms.register(app)
    quality_workflow.register(app)
    capa_assistant.register(app)
    pulse_intelligence.register(app)
    erp_integration.register(app)
    server_features.register(app)
    upload_dir = uploads_dir() / "quote_drawings"
    upload_dir.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        db.create_all()
        quality_workflow.backfill_workflows()
        db.session.commit()
        try:
            erp_integration.process_inbox()
        except Exception as exc:
            log("ERP", "Startup inbox scan failed", str(exc)[:500])
            db.session.commit()

    @app.route("/quoting", methods=["GET", "POST"])
    def quoting_resources():
        if request.method == "POST":
            drawing = request.files.get("drawing_pdf")
            if not drawing or not drawing.filename.lower().endswith(".pdf"):
                log("Quoting", "Upload failed", "Customer drawing PDF missing"); db.session.commit(); return redirect("/quoting")
            safe_name = secure_filename(drawing.filename)
            stored = upload_dir / f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe_name}"
            drawing.save(stored)
            customer = get_or_create(Customer, request.form.get("customer"))
            quote = QuoteResource(quote_number=request.form.get("quote_number"), customer_id=customer.id if customer else None, part_number=request.form.get("part_number"), part_description=request.form.get("part_description"), quote_length=as_float(request.form.get("quote_length")), drawing_filename=safe_name, drawing_path=str(stored), notes=request.form.get("notes"))
            db.session.add(quote); db.session.flush()
            bom_upload, rows = create_bom_from_pdf(stored, safe_name, source="Quoting Resource", quote_id=quote.id, quote_length=quote.quote_length or 0)
            quote.bom_upload_id = bom_upload.id
            quote.status = "BOM Review Needed" if rows else "Drawing Saved - No BOM Found"
            material_count = QuoteMaterialAssignment.query.filter_by(quote_id=quote.id).count()
            log("Quoting", "Customer drawing entered", f"{quote.quote_number}; BOM candidates: {len(rows)}; material drafts: {material_count}")
            db.session.commit(); return redirect(f"/quoting/{quote.id}")
        records = "".join(f"<tr><td><a href='/quoting/{q.id}'>{q.quote_number}</a></td><td>{q.customer.name if q.customer else ''}</td><td>{q.part_number or ''}</td><td>{q.drawing_filename or ''}</td><td>{q.status}</td></tr>" for q in QuoteResource.query.order_by(QuoteResource.id.desc()).limit(100))
        body = f"""<div class='notice'>Entering a customer drawing automatically runs BOM extraction and creates reviewable material-cost assignments from approved catalog and purchase history.</div><section><form method='post' enctype='multipart/form-data' class='form'><label>Quote Number<input name='quote_number' required></label><label>Customer<input name='customer'></label><label>Part Number<input name='part_number'></label><label>Quote Length / Usage Length<input name='quote_length' type='number' step='0.001'></label><label class='wide'>Part Description<input name='part_description'></label><label class='wide'>Customer Drawing PDF<input type='file' name='drawing_pdf' accept='application/pdf' required></label><label class='wide'>Notes<textarea name='notes'></textarea></label><button>Save Drawing, Extract BOM, Assign Materials</button></form></section><br><section><h2>Quoting Resources</h2><table><tr><th>Quote</th><th>Customer</th><th>Part</th><th>Drawing</th><th>Status</th></tr>{records}</table></section>"""
        return page("Quoting Resources", body)

    @app.route("/quoting/<int:quote_id>")
    def quote_detail(quote_id):
        quote = QuoteResource.query.get_or_404(quote_id)
        bom_link = f"<a class='btn' href='/bom/{quote.bom_upload_id}'>Review Extracted BOM</a>" if quote.bom_upload_id else "<span class='muted'>No BOM record</span>"
        material_link = f"<a class='btn' href='/quote-materials/{quote.id}'>Review Material Assignments</a>"
        body = f"""<section><h2>{quote.quote_number}</h2><table><tr><th>Customer</th><td>{quote.customer.name if quote.customer else ''}</td></tr><tr><th>Part</th><td>{quote.part_number or ''}</td></tr><tr><th>Quote Length</th><td>{quote.quote_length or 0}</td></tr><tr><th>Drawing</th><td>{quote.drawing_filename or ''}</td></tr><tr><th>Status</th><td>{quote.status}</td></tr><tr><th>BOM</th><td>{bom_link}</td></tr><tr><th>Materials</th><td>{material_link}</td></tr></table></section>"""
        return page("Quote Detail", body)

    @app.route("/bom/<int:upload_id>", methods=["GET", "POST"])
    def bom_review(upload_id):
        upload = BOMUpload.query.get_or_404(upload_id)
        lines = BOMLine.query.filter_by(upload_id=upload.id).order_by(BOMLine.id).all()
        if request.method == "POST":
            for line in lines:
                prefix = f"line_{line.id}_"
                line.item_no = request.form.get(prefix + "item_no"); line.part_number = request.form.get(prefix + "part_number"); line.description = request.form.get(prefix + "description"); line.material = request.form.get(prefix + "material"); line.revision = request.form.get(prefix + "revision")
                try: line.quantity = float(request.form.get(prefix + "quantity") or 0)
                except ValueError: line.quantity = 0
                line.approved = request.form.get(prefix + "approved") == "on"
            upload.extraction_status = "Reviewed"; log("BOM", "Review saved", upload.source_filename); db.session.commit(); return redirect(f"/bom/{upload.id}")
        rows = ""
        for line in lines:
            checked = "checked" if line.approved else ""
            rows += f"<tr><td><input type='checkbox' name='line_{line.id}_approved' {checked}></td><td><input name='line_{line.id}_item_no' value='{line.item_no or ''}'></td><td><input name='line_{line.id}_part_number' value='{line.part_number or ''}'></td><td><input name='line_{line.id}_description' value='{line.description or ''}'></td><td><input name='line_{line.id}_material' value='{line.material or ''}'></td><td><input name='line_{line.id}_quantity' value='{line.quantity or 0}'></td><td><input name='line_{line.id}_revision' value='{line.revision or ''}'></td><td>{line.confidence}</td><td>{line.raw_text or ''}</td></tr>"
        body = f"""<div class='notice'>Review before using for quoting, purchasing, or routing. Extraction is automatic, approval is human-controlled.</div><section><h2>{upload.source_filename}</h2><p class='muted'>{upload.extraction_notes or ''}</p><form method='post'><table><tr><th>Use</th><th>Item</th><th>Part Number</th><th>Description</th><th>Material</th><th>Qty</th><th>Rev</th><th>Confidence</th><th>Raw Text</th></tr>{rows}</table><br><button>Save BOM Review</button></form></section>"""
        return page("BOM Review", body)

    return app
