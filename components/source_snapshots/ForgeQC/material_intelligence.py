from datetime import date, datetime, timedelta
import re

from flask import redirect, request

from forgeqc_app import db, page, log, as_float, as_int
from forgeqc_quote_bom import BOMLine, QuoteResource


class ApprovedSupplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), unique=True, nullable=False)
    contact = db.Column(db.String(180))
    default_lead_time_days = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)


class MaterialCatalogItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('approved_supplier.id'))
    item_number = db.Column(db.String(140))
    material_family = db.Column(db.String(120))
    grade = db.Column(db.String(120))
    shape = db.Column(db.String(80))
    thickness_in = db.Column(db.Float)
    width_in = db.Column(db.Float)
    length_in = db.Column(db.Float)
    description = db.Column(db.String(260))
    unit_cost = db.Column(db.Float, default=0)
    cost_basis = db.Column(db.String(80), default='Each')
    lead_time_days = db.Column(db.Integer, default=0)
    approved = db.Column(db.Boolean, default=True)
    last_purchase_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    supplier = db.relationship('ApprovedSupplier')


class MaterialPurchaseHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    purchase_date = db.Column(db.Date, default=date.today)
    supplier_id = db.Column(db.Integer, db.ForeignKey('approved_supplier.id'))
    item_number = db.Column(db.String(140))
    material_family = db.Column(db.String(120))
    grade = db.Column(db.String(120))
    shape = db.Column(db.String(80))
    thickness_in = db.Column(db.Float)
    width_in = db.Column(db.Float)
    length_in = db.Column(db.Float)
    quantity_purchased = db.Column(db.Float, default=0)
    unit_cost = db.Column(db.Float, default=0)
    lead_time_days = db.Column(db.Integer, default=0)
    supplier = db.relationship('ApprovedSupplier')


class QuoteMaterialAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quote_resource_id = db.Column(db.Integer, db.ForeignKey('quote_resource.id'))
    bom_line_id = db.Column(db.Integer, db.ForeignKey('bom_line.id'))
    catalog_item_id = db.Column(db.Integer, db.ForeignKey('material_catalog_item.id'))
    supplier_id = db.Column(db.Integer, db.ForeignKey('approved_supplier.id'))
    assigned_material = db.Column(db.String(260))
    required_quantity = db.Column(db.Float, default=0)
    standard_length_in = db.Column(db.Float)
    unit_cost = db.Column(db.Float, default=0)
    estimated_material_cost = db.Column(db.Float, default=0)
    lead_time_days = db.Column(db.Integer, default=0)
    need_by_date = db.Column(db.Date)
    order_by_date = db.Column(db.Date)
    match_confidence = db.Column(db.Float, default=0)
    status = db.Column(db.String(80), default='Draft')
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    quote_resource = db.relationship('QuoteResource')
    bom_line = db.relationship('BOMLine')
    catalog_item = db.relationship('MaterialCatalogItem')
    supplier = db.relationship('ApprovedSupplier')


MATERIAL_WORDS = {
    'steel': ['steel', 'crs', 'hrs', 'a36', '1018', 'galv', 'galvanized'],
    'stainless': ['stainless', 'ss', '304', '316'],
    'aluminum': ['aluminum', 'alum', '5052', '6061'],
    'brass': ['brass'],
    'copper': ['copper'],
    'plastic': ['plastic', 'poly', 'hdpe', 'uhmw', 'abs'],
}


def normalize(text):
    return re.sub(r'[^a-z0-9.]+', ' ', (text or '').lower()).strip()


def infer_material_family(text):
    clean = normalize(text)
    for family, words in MATERIAL_WORDS.items():
        if any(word in clean.split() or word in clean for word in words):
            return family
    return ''


def infer_shape(text):
    clean = normalize(text)
    if any(x in clean for x in ['sheet', 'plate', 'flat']):
        return 'Sheet/Plate'
    if any(x in clean for x in ['tube', 'tubing', 'square tube', 'rect tube']):
        return 'Tube'
    if any(x in clean for x in ['angle']):
        return 'Angle'
    if any(x in clean for x in ['bar', 'round', 'rod']):
        return 'Bar/Rod'
    return ''


def text_match_score(bom_line, catalog):
    text = normalize(' '.join([bom_line.material or '', bom_line.description or '', bom_line.part_number or '', bom_line.raw_text or '']))
    score = 0.0
    family = infer_material_family(text)
    shape = infer_shape(text)
    if catalog.material_family and family and catalog.material_family.lower() == family:
        score += 0.35
    if catalog.shape and shape and catalog.shape.lower() == shape.lower():
        score += 0.20
    if catalog.grade and catalog.grade.lower() in text:
        score += 0.20
    if catalog.item_number and catalog.item_number.lower() in text:
        score += 0.20
    if catalog.description:
        words = [w for w in normalize(catalog.description).split() if len(w) > 2]
        common = sum(1 for w in words if w in text)
        score += min(common * 0.04, 0.20)
    if catalog.approved:
        score += 0.05
    return round(min(score, 0.98), 2)


def best_catalog_match(bom_line):
    best = None
    best_score = 0.0
    for item in MaterialCatalogItem.query.filter_by(approved=True).all():
        score = text_match_score(bom_line, item)
        if score > best_score:
            best = item
            best_score = score
    return best, best_score


def preferred_standard_length(catalog_item):
    if not catalog_item:
        return None
    history = MaterialPurchaseHistory.query.filter_by(
        material_family=catalog_item.material_family,
        grade=catalog_item.grade,
        shape=catalog_item.shape,
        thickness_in=catalog_item.thickness_in,
        width_in=catalog_item.width_in,
    ).order_by(MaterialPurchaseHistory.purchase_date.desc()).limit(25).all()
    lengths = {}
    for row in history:
        if row.length_in:
            lengths[row.length_in] = lengths.get(row.length_in, 0) + (row.quantity_purchased or 1)
    if lengths:
        return sorted(lengths.items(), key=lambda x: x[1], reverse=True)[0][0]
    return catalog_item.length_in


def calculate_assignment(quote_resource, bom_line, need_by_date=None):
    catalog, confidence = best_catalog_match(bom_line)
    qty = bom_line.quantity or 0
    if not catalog:
        return QuoteMaterialAssignment(
            quote_resource_id=quote_resource.id,
            bom_line_id=bom_line.id,
            assigned_material=bom_line.material or bom_line.description or bom_line.part_number,
            required_quantity=qty,
            match_confidence=0,
            status='Needs Material Review',
            notes='No approved supplier catalog match found.',
        )

    lead_time = catalog.lead_time_days or (catalog.supplier.default_lead_time_days if catalog.supplier else 0) or 0
    order_by = need_by_date - timedelta(days=lead_time) if need_by_date else None
    cost = round(qty * (catalog.unit_cost or 0), 2)
    standard_length = preferred_standard_length(catalog)
    return QuoteMaterialAssignment(
        quote_resource_id=quote_resource.id,
        bom_line_id=bom_line.id,
        catalog_item_id=catalog.id,
        supplier_id=catalog.supplier_id,
        assigned_material=catalog.description or catalog.item_number,
        required_quantity=qty,
        standard_length_in=standard_length,
        unit_cost=catalog.unit_cost or 0,
        estimated_material_cost=cost,
        lead_time_days=lead_time,
        need_by_date=need_by_date,
        order_by_date=order_by,
        match_confidence=confidence,
        status='Auto Assigned' if confidence >= 0.55 else 'Needs Material Review',
        notes='Matched from approved supplier catalog and prior standard-length purchase history.',
    )


def auto_assign_quote_materials(quote_resource, need_by_date=None):
    if not quote_resource or not quote_resource.bom_upload_id:
        return 0
    existing = QuoteMaterialAssignment.query.filter_by(quote_resource_id=quote_resource.id).count()
    if existing:
        return existing
    count = 0
    for line in BOMLine.query.filter_by(upload_id=quote_resource.bom_upload_id).all():
        assignment = calculate_assignment(quote_resource, line, need_by_date)
        db.session.add(assignment)
        count += 1
    return count


def supplier_options(selected=None):
    html = "<option value=''></option>"
    for s in ApprovedSupplier.query.filter_by(active=True).order_by(ApprovedSupplier.name):
        sel = ' selected' if selected == s.id else ''
        html += f"<option value='{s.id}'{sel}>{s.name}</option>"
    return html


def register_material_intelligence(app):
    with app.app_context():
        db.create_all()

    @app.route('/materials', methods=['GET', 'POST'])
    def materials():
        if request.method == 'POST':
            supplier = ApprovedSupplier.query.get(as_int(request.form.get('supplier_id'), None))
            if not supplier and request.form.get('supplier_name'):
                supplier = ApprovedSupplier(name=request.form.get('supplier_name'), default_lead_time_days=as_int(request.form.get('lead_time_days')))
                db.session.add(supplier)
                db.session.flush()
            item = MaterialCatalogItem(
                supplier_id=supplier.id if supplier else None,
                item_number=request.form.get('item_number'),
                material_family=request.form.get('material_family'),
                grade=request.form.get('grade'),
                shape=request.form.get('shape'),
                thickness_in=as_float(request.form.get('thickness_in'), None),
                width_in=as_float(request.form.get('width_in'), None),
                length_in=as_float(request.form.get('length_in'), None),
                description=request.form.get('description'),
                unit_cost=as_float(request.form.get('unit_cost')),
                cost_basis=request.form.get('cost_basis') or 'Each',
                lead_time_days=as_int(request.form.get('lead_time_days')),
                approved=True,
            )
            db.session.add(item)
            log('Materials', 'Catalog item saved', item.description or item.item_number or '')
            db.session.commit()
            return redirect('/materials')

        rows = ''.join(
            f"<tr><td>{m.supplier.name if m.supplier else ''}</td><td>{m.item_number or ''}</td><td>{m.material_family or ''}</td><td>{m.grade or ''}</td><td>{m.shape or ''}</td><td>{m.thickness_in or ''}</td><td>{m.width_in or ''}</td><td>{m.length_in or ''}</td><td>${m.unit_cost or 0:.2f}</td><td>{m.lead_time_days}</td></tr>"
            for m in MaterialCatalogItem.query.order_by(MaterialCatalogItem.id.desc()).limit(300)
        )
        body = f"""
        <div class='notice'>Approved supplier catalogs are local runtime data. Use this to teach quoting what material costs, lead times, and standard stock lengths are real.</div>
        <section><form method='post' class='form'>
        <label>Existing Supplier<select name='supplier_id'>{supplier_options()}</select></label>
        <label>Or New Supplier<input name='supplier_name'></label>
        <label>Item Number<input name='item_number'></label>
        <label>Material Family<input name='material_family' placeholder='steel, stainless, aluminum'></label>
        <label>Grade<input name='grade' placeholder='A36, 304, 5052, 6061'></label>
        <label>Shape<input name='shape' placeholder='Sheet/Plate, Tube, Bar/Rod'></label>
        <label>Thickness In<input name='thickness_in' type='number' step='0.0001'></label>
        <label>Width In<input name='width_in' type='number' step='0.001'></label>
        <label>Length In<input name='length_in' type='number' step='0.001'></label>
        <label>Unit Cost<input name='unit_cost' type='number' step='0.01'></label>
        <label>Cost Basis<select name='cost_basis'><option>Each</option><option>Sheet</option><option>Stick</option><option>Foot</option><option>Pound</option></select></label>
        <label>Lead Time Days<input name='lead_time_days' type='number'></label>
        <label class='wide'>Description<input name='description'></label>
        <button>Save Approved Material</button>
        </form></section><br>
        <section><h2>Approved Material Catalog</h2><table><tr><th>Supplier</th><th>Item</th><th>Family</th><th>Grade</th><th>Shape</th><th>Thick</th><th>Width</th><th>Length</th><th>Cost</th><th>Lead</th></tr>{rows}</table></section>
        """
        return page('Approved Material Catalog', body)

    @app.route('/materials/purchases', methods=['GET', 'POST'])
    def material_purchases():
        if request.method == 'POST':
            supplier = ApprovedSupplier.query.get(as_int(request.form.get('supplier_id'), None))
            row = MaterialPurchaseHistory(
                purchase_date=datetime.strptime(request.form.get('purchase_date'), '%Y-%m-%d').date() if request.form.get('purchase_date') else date.today(),
                supplier_id=supplier.id if supplier else None,
                item_number=request.form.get('item_number'),
                material_family=request.form.get('material_family'),
                grade=request.form.get('grade'),
                shape=request.form.get('shape'),
                thickness_in=as_float(request.form.get('thickness_in'), None),
                width_in=as_float(request.form.get('width_in'), None),
                length_in=as_float(request.form.get('length_in'), None),
                quantity_purchased=as_float(request.form.get('quantity_purchased')),
                unit_cost=as_float(request.form.get('unit_cost')),
                lead_time_days=as_int(request.form.get('lead_time_days')),
            )
            db.session.add(row)
            log('Materials', 'Purchase history saved', row.item_number or '')
            db.session.commit()
            return redirect('/materials/purchases')

        rows = ''.join(
            f"<tr><td>{p.purchase_date}</td><td>{p.supplier.name if p.supplier else ''}</td><td>{p.item_number or ''}</td><td>{p.material_family or ''}</td><td>{p.grade or ''}</td><td>{p.shape or ''}</td><td>{p.length_in or ''}</td><td>{p.quantity_purchased or 0}</td><td>${p.unit_cost or 0:.2f}</td><td>{p.lead_time_days}</td></tr>"
            for p in MaterialPurchaseHistory.query.order_by(MaterialPurchaseHistory.purchase_date.desc()).limit(300)
        )
        body = f"""
        <div class='notice'>Prior purchases teach quoting preferred standard stock lengths and actual supplier behavior.</div>
        <section><form method='post' class='form'>
        <label>Date<input name='purchase_date' type='date'></label>
        <label>Supplier<select name='supplier_id'>{supplier_options()}</select></label>
        <label>Item Number<input name='item_number'></label>
        <label>Material Family<input name='material_family'></label>
        <label>Grade<input name='grade'></label>
        <label>Shape<input name='shape'></label>
        <label>Thickness In<input name='thickness_in' type='number' step='0.0001'></label>
        <label>Width In<input name='width_in' type='number' step='0.001'></label>
        <label>Length In<input name='length_in' type='number' step='0.001'></label>
        <label>Qty Purchased<input name='quantity_purchased' type='number' step='0.01'></label>
        <label>Unit Cost<input name='unit_cost' type='number' step='0.01'></label>
        <label>Lead Time Days<input name='lead_time_days' type='number'></label>
        <button>Save Purchase History</button>
        </form></section><br>
        <section><h2>Purchase History</h2><table><tr><th>Date</th><th>Supplier</th><th>Item</th><th>Family</th><th>Grade</th><th>Shape</th><th>Length</th><th>Qty</th><th>Cost</th><th>Lead</th></tr>{rows}</table></section>
        """
        return page('Material Purchase History', body)

    @app.route('/quoting/<int:quote_id>/materials', methods=['GET', 'POST'])
    def quote_materials(quote_id):
        quote = QuoteResource.query.get_or_404(quote_id)
        if request.method == 'POST':
            need_by = datetime.strptime(request.form.get('need_by_date'), '%Y-%m-%d').date() if request.form.get('need_by_date') else None
            existing = QuoteMaterialAssignment.query.filter_by(quote_resource_id=quote.id).all()
            for row in existing:
                db.session.delete(row)
            db.session.flush()
            count = auto_assign_quote_materials(quote, need_by)
            log('Quote', 'Material intelligence assigned', f'{quote.quote_number}; {count} lines')
            db.session.commit()
            return redirect(f'/quoting/{quote.id}/materials')

        rows = ''.join(
            f"<tr><td>{a.bom_line.item_no if a.bom_line else ''}</td><td>{a.bom_line.part_number if a.bom_line else ''}</td><td>{a.assigned_material or ''}</td><td>{a.supplier.name if a.supplier else ''}</td><td>{a.required_quantity or 0}</td><td>{a.standard_length_in or ''}</td><td>${a.unit_cost or 0:.2f}</td><td>${a.estimated_material_cost or 0:.2f}</td><td>{a.lead_time_days}</td><td>{a.order_by_date or ''}</td><td>{a.match_confidence}</td><td>{a.status}</td></tr>"
            for a in QuoteMaterialAssignment.query.filter_by(quote_resource_id=quote.id).order_by(QuoteMaterialAssignment.id)
        )
        total = sum(a.estimated_material_cost or 0 for a in QuoteMaterialAssignment.query.filter_by(quote_resource_id=quote.id).all())
        body = f"""
        <div class='notice'>Material assignments are generated from approved supplier catalogs and previous purchase standard lengths. Review before quote release.</div>
        <section><h2>{quote.quote_number} Material Quote</h2>
        <form method='post' class='toolbar'><label>Need By Date<input name='need_by_date' type='date'></label><button>Recalculate Material Assignments</button></form>
        <p><b>Total Estimated Material Cost:</b> ${total:.2f}</p>
        <table><tr><th>Item</th><th>BOM Part</th><th>Assigned Material</th><th>Supplier</th><th>Req Qty</th><th>Std Length</th><th>Unit Cost</th><th>Est Cost</th><th>Lead Days</th><th>Order By</th><th>Match</th><th>Status</th></tr>{rows}</table></section>
        """
        return page('Quote Material Intelligence', body)
