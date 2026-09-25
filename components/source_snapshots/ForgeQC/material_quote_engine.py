import math
from datetime import datetime

from flask import request

from forgeqc_app import db, page, log, as_float, as_int


class ApprovedSupplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)
    default_lead_time_days = db.Column(db.Integer, default=7)
    notes = db.Column(db.Text)


class MaterialCatalogItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('approved_supplier.id'))
    material_key = db.Column(db.String(240), nullable=False)
    material_type = db.Column(db.String(120))
    grade = db.Column(db.String(120))
    thickness = db.Column(db.String(80))
    width = db.Column(db.Float, default=0)
    length = db.Column(db.Float, default=0)
    purchase_uom = db.Column(db.String(40), default='EA')
    unit_cost = db.Column(db.Float, default=0)
    lead_time_days = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    supplier = db.relationship('ApprovedSupplier')


class MaterialPurchaseHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey('approved_supplier.id'))
    material_key = db.Column(db.String(240), nullable=False)
    quantity = db.Column(db.Float, default=0)
    unit_cost = db.Column(db.Float, default=0)
    length = db.Column(db.Float, default=0)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    lead_time_days = db.Column(db.Integer, default=0)
    supplier = db.relationship('ApprovedSupplier')


class QuoteMaterialAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quote_id = db.Column(db.Integer, nullable=False)
    bom_line_id = db.Column(db.Integer, nullable=True)
    material_key = db.Column(db.String(240), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('approved_supplier.id'))
    catalog_item_id = db.Column(db.Integer, db.ForeignKey('material_catalog_item.id'))
    required_each_qty = db.Column(db.Float, default=0)
    quote_length = db.Column(db.Float, default=0)
    standard_length = db.Column(db.Float, default=0)
    pieces_required = db.Column(db.Integer, default=0)
    unit_cost = db.Column(db.Float, default=0)
    estimated_material_cost = db.Column(db.Float, default=0)
    lead_time_days = db.Column(db.Integer, default=0)
    confidence = db.Column(db.Float, default=0)
    status = db.Column(db.String(80), default='Draft')
    notes = db.Column(db.Text)
    supplier = db.relationship('ApprovedSupplier')
    catalog_item = db.relationship('MaterialCatalogItem')


def normalize_material(text):
    clean = ' '.join(str(text or '').lower().replace(',', ' ').split())
    replacements = {'alum': 'aluminum', 'ss': 'stainless', 'stnls': 'stainless', 'ga': 'gauge'}
    for old, new in replacements.items():
        clean = clean.replace(old, new)
    return clean.strip()


def supplier_average(material_key):
    rows = MaterialPurchaseHistory.query.filter(MaterialPurchaseHistory.material_key.ilike(f'%{material_key}%')).all()
    if not rows:
        return None
    total_qty = sum(r.quantity or 0 for r in rows) or len(rows)
    avg_cost = sum((r.unit_cost or 0) * ((r.quantity or 1)) for r in rows) / total_qty
    avg_lead = round(sum(r.lead_time_days or 0 for r in rows) / len(rows))
    common_length = max([r.length or 0 for r in rows] or [0])
    supplier_id = rows[-1].supplier_id
    return {'unit_cost': round(avg_cost, 4), 'lead_time_days': avg_lead, 'length': common_length, 'supplier_id': supplier_id}


def find_best_catalog_match(material_key):
    normalized = normalize_material(material_key)
    exact = MaterialCatalogItem.query.filter(MaterialCatalogItem.active == True, MaterialCatalogItem.material_key.ilike(normalized)).first()
    if exact:
        return exact, 0.95
    tokens = [t for t in normalized.split() if len(t) > 1]
    best = None
    best_score = 0
    for item in MaterialCatalogItem.query.filter_by(active=True).all():
        hay = normalize_material(item.material_key + ' ' + str(item.material_type or '') + ' ' + str(item.grade or '') + ' ' + str(item.thickness or ''))
        score = sum(1 for t in tokens if t in hay) / max(len(tokens), 1)
        if score > best_score:
            best = item
            best_score = score
    return best, round(best_score, 2)


def resolve_material_assignment(quote_id, bom_line_id, material_key, required_qty=1, quote_length=0):
    key = normalize_material(material_key)
    catalog, confidence = find_best_catalog_match(key)
    history = supplier_average(key)

    supplier_id = None
    catalog_id = None
    standard_length = 0
    unit_cost = 0
    lead_time = 0

    if catalog:
        supplier_id = catalog.supplier_id
        catalog_id = catalog.id
        standard_length = catalog.length or 0
        unit_cost = catalog.unit_cost or 0
        lead_time = catalog.lead_time_days or (catalog.supplier.default_lead_time_days if catalog.supplier else 0)
    elif history:
        supplier_id = history['supplier_id']
        standard_length = history['length']
        unit_cost = history['unit_cost']
        lead_time = history['lead_time_days']
        confidence = max(confidence, 0.65)

    if not standard_length:
        standard_length = quote_length or 1
    pieces = math.ceil((required_qty or 0) * max(quote_length or 1, 1) / max(standard_length, 1))
    estimated_cost = round(pieces * unit_cost, 2)
    status = 'Resolved' if supplier_id and unit_cost else 'Needs Review'

    row = QuoteMaterialAssignment(
        quote_id=quote_id,
        bom_line_id=bom_line_id,
        material_key=key,
        supplier_id=supplier_id,
        catalog_item_id=catalog_id,
        required_each_qty=required_qty or 0,
        quote_length=quote_length or 0,
        standard_length=standard_length,
        pieces_required=pieces,
        unit_cost=unit_cost,
        estimated_material_cost=estimated_cost,
        lead_time_days=lead_time,
        confidence=confidence,
        status=status,
        notes='Auto-assigned from approved catalog or purchase history. Review before quote release.',
    )
    db.session.add(row)
    return row


def register(app):
    @app.route('/materials', methods=['GET', 'POST'])
    def materials():
        if request.method == 'POST':
            supplier_name = request.form.get('supplier')
            supplier = ApprovedSupplier.query.filter(db.func.lower(ApprovedSupplier.name) == supplier_name.lower()).first() if supplier_name else None
            if not supplier and supplier_name:
                supplier = ApprovedSupplier(name=supplier_name, default_lead_time_days=as_int(request.form.get('lead_time_days'), 7))
                db.session.add(supplier)
                db.session.flush()
            item = MaterialCatalogItem(
                supplier_id=supplier.id if supplier else None,
                material_key=normalize_material(request.form.get('material_key')),
                material_type=request.form.get('material_type'),
                grade=request.form.get('grade'),
                thickness=request.form.get('thickness'),
                width=as_float(request.form.get('width')),
                length=as_float(request.form.get('length')),
                purchase_uom=request.form.get('purchase_uom') or 'EA',
                unit_cost=as_float(request.form.get('unit_cost')),
                lead_time_days=as_int(request.form.get('lead_time_days')),
            )
            db.session.add(item)
            log('Material', 'Catalog item saved', item.material_key)
            db.session.commit()
            return app.response_class('', status=302, headers={'Location': '/materials'})

        rows = ''.join(
            f"<tr><td>{i.material_key}</td><td>{i.supplier.name if i.supplier else ''}</td><td>{i.length}</td><td>{i.unit_cost}</td><td>{i.lead_time_days}</td></tr>"
            for i in MaterialCatalogItem.query.order_by(MaterialCatalogItem.material_key).limit(300)
        )
        body = f"""
        <section><h2>Approved Supplier Catalog</h2><form method='post' class='form'>
        <label>Supplier<input name='supplier'></label><label>Material Key<input name='material_key' required></label><label>Material Type<input name='material_type'></label>
        <label>Grade<input name='grade'></label><label>Thickness<input name='thickness'></label><label>Width<input name='width' type='number' step='0.001'></label>
        <label>Standard Length<input name='length' type='number' step='0.001'></label><label>UOM<input name='purchase_uom' value='EA'></label><label>Unit Cost<input name='unit_cost' type='number' step='0.0001'></label>
        <label>Lead Time Days<input name='lead_time_days' type='number'></label><button>Save Catalog Item</button></form></section><br>
        <section><table><tr><th>Material</th><th>Supplier</th><th>Std Length</th><th>Unit Cost</th><th>Lead Time</th></tr>{rows}</table></section>
        """
        return page('Approved Material Catalogs', body)

    @app.route('/quote-materials/<int:quote_id>')
    def quote_materials(quote_id):
        rows = ''.join(
            f"<tr><td>{a.material_key}</td><td>{a.supplier.name if a.supplier else ''}</td><td>{a.required_each_qty}</td><td>{a.quote_length}</td><td>{a.standard_length}</td><td>{a.pieces_required}</td><td>{a.unit_cost}</td><td>{a.estimated_material_cost}</td><td>{a.lead_time_days}</td><td>{a.confidence}</td><td>{a.status}</td></tr>"
            for a in QuoteMaterialAssignment.query.filter_by(quote_id=quote_id).order_by(QuoteMaterialAssignment.id)
        )
        return page('Quote Material Assignments', f"<section><table><tr><th>Material</th><th>Supplier</th><th>Qty</th><th>Quote Length</th><th>Std Length</th><th>Pieces</th><th>Unit Cost</th><th>Est Cost</th><th>Lead Time</th><th>Confidence</th><th>Status</th></tr>{rows}</table></section>")
