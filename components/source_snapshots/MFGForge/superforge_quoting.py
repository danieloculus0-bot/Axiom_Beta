from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import abort, flash, redirect, render_template_string, request, url_for

from app import get_db, page


DEFAULT_OPERATIONS: tuple[dict[str, Any], ...] = (
    {'sequence': 10, 'name': 'Receive Material', 'operation_type': 'material', 'default_rate': 65.0, 'setup_hours': 0.15, 'run_hours_per_piece': 0.02, 'lead_time_days': 0.5},
    {'sequence': 20, 'name': 'Hurco Mill', 'operation_type': 'machining', 'default_rate': 125.0, 'setup_hours': 0.75, 'run_hours_per_piece': 0.18, 'lead_time_days': 2.0},
    {'sequence': 30, 'name': 'Lathe', 'operation_type': 'machining', 'default_rate': 115.0, 'setup_hours': 0.65, 'run_hours_per_piece': 0.16, 'lead_time_days': 1.5},
    {'sequence': 40, 'name': 'Brushing/Deburr', 'operation_type': 'finishing', 'default_rate': 72.0, 'setup_hours': 0.20, 'run_hours_per_piece': 0.08, 'lead_time_days': 1.0},
    {'sequence': 50, 'name': 'Powder Coat', 'operation_type': 'outside_process', 'default_rate': 0.0, 'setup_hours': 0.0, 'run_hours_per_piece': 0.0, 'lead_time_days': 5.0},
    {'sequence': 60, 'name': 'Final Inspect', 'operation_type': 'quality', 'default_rate': 82.0, 'setup_hours': 0.15, 'run_hours_per_piece': 0.05, 'lead_time_days': 0.5},
    {'sequence': 70, 'name': 'Packaging', 'operation_type': 'shipping', 'default_rate': 58.0, 'setup_hours': 0.10, 'run_hours_per_piece': 0.04, 'lead_time_days': 0.5},
    {'sequence': 80, 'name': 'Shipping', 'operation_type': 'shipping', 'default_rate': 58.0, 'setup_hours': 0.10, 'run_hours_per_piece': 0.02, 'lead_time_days': 1.0},
)


def number(value: Any, default: float = 0.0) -> float:
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def ensure_operations_schema() -> None:
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS quote_blueprint_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_intake_id INTEGER REFERENCES quote_intakes(id),
            part_number TEXT,
            revision TEXT,
            extracted_length REAL,
            extracted_width REAL,
            extracted_height REAL,
            extracted_weight REAL,
            dimension_unit TEXT NOT NULL DEFAULT 'in',
            weight_unit TEXT NOT NULL DEFAULT 'lb',
            material_guess TEXT,
            thickness_guess TEXT,
            blueprint_source TEXT,
            detected_features TEXT,
            extraction_notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS quote_operation_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sequence INTEGER NOT NULL,
            name TEXT NOT NULL UNIQUE,
            operation_type TEXT NOT NULL,
            default_rate REAL NOT NULL DEFAULT 0,
            default_setup_hours REAL NOT NULL DEFAULT 0,
            default_run_hours_per_piece REAL NOT NULL DEFAULT 0,
            default_lead_time_days REAL NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS quote_operation_estimates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_intake_id INTEGER REFERENCES quote_intakes(id),
            template_id INTEGER REFERENCES quote_operation_templates(id),
            sequence INTEGER NOT NULL,
            operation_name TEXT NOT NULL,
            operation_type TEXT NOT NULL,
            include_operation INTEGER NOT NULL DEFAULT 0,
            quantity REAL NOT NULL DEFAULT 1,
            hourly_rate REAL NOT NULL DEFAULT 0,
            setup_hours REAL NOT NULL DEFAULT 0,
            run_hours_per_piece REAL NOT NULL DEFAULT 0,
            outside_process_cost REAL NOT NULL DEFAULT 0,
            material_or_consumable_cost REAL NOT NULL DEFAULT 0,
            burden_percent REAL NOT NULL DEFAULT 18,
            estimated_cost REAL NOT NULL DEFAULT 0,
            estimated_lead_time_days REAL NOT NULL DEFAULT 0,
            basis_notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS quote_feature_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_intake_id INTEGER REFERENCES quote_intakes(id),
            feature_type TEXT NOT NULL,
            feature_value TEXT,
            occurrence_count REAL NOT NULL DEFAULT 1,
            tooling_cost_per_event REAL NOT NULL DEFAULT 0,
            estimated_tool_life_events REAL NOT NULL DEFAULT 1,
            cycle_time_minutes_per_event REAL NOT NULL DEFAULT 0,
            hourly_rate REAL NOT NULL DEFAULT 0,
            estimated_cost REAL NOT NULL DEFAULT 0,
            basis_notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS quote_rollups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_intake_id INTEGER NOT NULL UNIQUE REFERENCES quote_intakes(id),
            operation_cost REAL NOT NULL DEFAULT 0,
            feature_cost REAL NOT NULL DEFAULT 0,
            material_cost REAL NOT NULL DEFAULT 0,
            outside_process_cost REAL NOT NULL DEFAULT 0,
            total_estimated_cost REAL NOT NULL DEFAULT 0,
            suggested_sell_price REAL NOT NULL DEFAULT 0,
            target_margin_percent REAL NOT NULL DEFAULT 35,
            total_lead_time_days REAL NOT NULL DEFAULT 0,
            risk_notes TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    existing_templates = db.execute('SELECT COUNT(*) FROM quote_operation_templates').fetchone()[0]
    if existing_templates == 0:
        for op in DEFAULT_OPERATIONS:
            db.execute(
                """
                INSERT INTO quote_operation_templates
                (sequence, name, operation_type, default_rate, default_setup_hours, default_run_hours_per_piece, default_lead_time_days, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    op['sequence'],
                    op['name'],
                    op['operation_type'],
                    op['default_rate'],
                    op['setup_hours'],
                    op['run_hours_per_piece'],
                    op['lead_time_days'],
                    'System starter operation. Edit rates/times to match the shop.',
                ),
            )
    db.commit()


def quote_options() -> list[Any]:
    ensure_operations_schema()
    return list(get_db().execute('SELECT id, quote_number FROM quote_intakes ORDER BY quote_number LIMIT 500').fetchall())


def get_quote(quote_id: int) -> Any:
    row = get_db().execute('SELECT * FROM quote_intakes WHERE id = ?', (quote_id,)).fetchone()
    if row is None:
        abort(404)
    return row


def calculate_operation_cost(quantity: float, hourly_rate: float, setup_hours: float, run_hours_per_piece: float, outside_cost: float, consumable_cost: float, burden_percent: float) -> float:
    labor = hourly_rate * (setup_hours + (run_hours_per_piece * quantity))
    direct = labor + outside_cost + consumable_cost
    return round(direct * (1 + burden_percent / 100), 2)


def calculate_feature_cost(occurrences: float, tooling_cost: float, tool_life: float, cycle_minutes: float, hourly_rate: float) -> float:
    tool_life = tool_life if tool_life > 0 else 1
    tooling = occurrences * (tooling_cost / tool_life)
    labor = (occurrences * cycle_minutes / 60) * hourly_rate
    return round(tooling + labor, 2)


def rebuild_rollup(quote_id: int, target_margin_percent: float = 35.0) -> dict[str, float]:
    db = get_db()
    operation_cost = number(db.execute('SELECT SUM(estimated_cost) FROM quote_operation_estimates WHERE quote_intake_id = ? AND include_operation = 1', (quote_id,)).fetchone()[0])
    outside_cost = number(db.execute('SELECT SUM(outside_process_cost) FROM quote_operation_estimates WHERE quote_intake_id = ? AND include_operation = 1', (quote_id,)).fetchone()[0])
    material_cost = number(db.execute('SELECT SUM(material_or_consumable_cost) FROM quote_operation_estimates WHERE quote_intake_id = ? AND include_operation = 1', (quote_id,)).fetchone()[0])
    feature_cost = number(db.execute('SELECT SUM(estimated_cost) FROM quote_feature_costs WHERE quote_intake_id = ?', (quote_id,)).fetchone()[0])
    lead_time = number(db.execute('SELECT SUM(estimated_lead_time_days) FROM quote_operation_estimates WHERE quote_intake_id = ? AND include_operation = 1', (quote_id,)).fetchone()[0])
    total = round(operation_cost + feature_cost, 2)
    margin_factor = max(0.01, 1 - (target_margin_percent / 100))
    sell_price = round(total / margin_factor, 2) if total else 0
    db.execute(
        """
        INSERT INTO quote_rollups
        (quote_intake_id, operation_cost, feature_cost, material_cost, outside_process_cost, total_estimated_cost, suggested_sell_price, target_margin_percent, total_lead_time_days, risk_notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(quote_intake_id) DO UPDATE SET
            operation_cost=excluded.operation_cost,
            feature_cost=excluded.feature_cost,
            material_cost=excluded.material_cost,
            outside_process_cost=excluded.outside_process_cost,
            total_estimated_cost=excluded.total_estimated_cost,
            suggested_sell_price=excluded.suggested_sell_price,
            target_margin_percent=excluded.target_margin_percent,
            total_lead_time_days=excluded.total_lead_time_days,
            risk_notes=excluded.risk_notes,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            quote_id,
            operation_cost,
            feature_cost,
            material_cost,
            outside_cost,
            total,
            sell_price,
            target_margin_percent,
            lead_time,
            'Review supplier lead-time, machine capacity, special features, coating/vendor lead time, and inspection burden before release.',
        ),
    )
    db.commit()
    return {'operation_cost': operation_cost, 'feature_cost': feature_cost, 'material_cost': material_cost, 'outside_cost': outside_cost, 'total': total, 'sell_price': sell_price, 'lead_time': lead_time}


def register_operation_quoting_routes(app) -> None:
    @app.get('/quote-ops')
    def quote_ops_home() -> str:
        ensure_operations_schema()
        quotes = quote_options()
        rollups = get_db().execute(
            """
            SELECT qi.id, qi.quote_number, qi.drawing_reference, qi.intake_status,
                   qr.total_estimated_cost, qr.suggested_sell_price, qr.total_lead_time_days
            FROM quote_intakes qi
            LEFT JOIN quote_rollups qr ON qr.quote_intake_id = qi.id
            ORDER BY qi.id DESC
            LIMIT 100
            """
        ).fetchall()
        body = render_template_string(
            """
            <section class='page-head'>
                <div>
                    <p class='eyebrow'>Operations Quoting</p>
                    <h2>Quote the route, not the fairy tale</h2>
                    <p>Build quotes from material receipt, machines, finishing, inspection, packaging, shipping, blueprint dimensions, and special feature/tooling events.</p>
                </div>
                <a class='button' href='{{ url_for('quote_ops_new') }}'>New Operations Quote</a>
            </section>
            <section class='panel'>
                <h3>Existing quote rollups</h3>
                {% if rollups %}
                <table><thead><tr><th>Quote</th><th>Drawing</th><th>Status</th><th>Cost</th><th>Suggested sell</th><th>Lead time</th><th></th></tr></thead><tbody>
                {% for row in rollups %}
                <tr><td>{{ row.quote_number }}</td><td>{{ row.drawing_reference or '' }}</td><td>{{ row.intake_status }}</td><td>${{ '%.2f'|format(row.total_estimated_cost or 0) }}</td><td>${{ '%.2f'|format(row.suggested_sell_price or 0) }}</td><td>{{ '%.1f'|format(row.total_lead_time_days or 0) }} days</td><td><a class='button' href='{{ url_for('quote_ops_detail', quote_id=row.id) }}'>Open</a></td></tr>
                {% endfor %}
                </tbody></table>
                {% else %}
                <div class='empty'><h3>No operations quotes yet.</h3><p>Create a quote intake first, then build the route here.</p></div>
                {% endif %}
            </section>
            """,
            quotes=quotes,
            rollups=rollups,
        )
        return page('Operations Quoting | SuperForge', body)

    @app.route('/quote-ops/new', methods=('GET', 'POST'))
    def quote_ops_new() -> str:
        ensure_operations_schema()
        if request.method == 'POST':
            quote_id = int(request.form['quote_intake_id'])
            quantity = number(request.form.get('quantity'), 1)
            length = number(request.form.get('extracted_length'))
            width = number(request.form.get('extracted_width'))
            height = number(request.form.get('extracted_height'))
            weight = number(request.form.get('extracted_weight'))
            db = get_db()
            db.execute(
                """
                INSERT INTO quote_blueprint_facts
                (quote_intake_id, part_number, revision, extracted_length, extracted_width, extracted_height, extracted_weight, material_guess, thickness_guess, blueprint_source, detected_features, extraction_notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id,
                    request.form.get('part_number', '').strip(),
                    request.form.get('revision', '').strip(),
                    length,
                    width,
                    height,
                    weight,
                    request.form.get('material_guess', '').strip(),
                    request.form.get('thickness_guess', '').strip(),
                    request.form.get('blueprint_source', '').strip(),
                    request.form.get('detected_features', '').strip(),
                    request.form.get('extraction_notes', '').strip(),
                ),
            )
            templates = db.execute('SELECT * FROM quote_operation_templates WHERE active = 1 ORDER BY sequence').fetchall()
            for template in templates:
                key = f'op_{template["id"]}'
                include = 1 if request.form.get(key) == 'on' else 0
                hourly_rate = number(request.form.get(f'rate_{template["id"]}'), template['default_rate'])
                setup_hours = number(request.form.get(f'setup_{template["id"]}'), template['default_setup_hours'])
                run_hours = number(request.form.get(f'run_{template["id"]}'), template['default_run_hours_per_piece'])
                outside_cost = number(request.form.get(f'outside_{template["id"]}'))
                consumable_cost = number(request.form.get(f'consumable_{template["id"]}'))
                burden = number(request.form.get(f'burden_{template["id"]}'), 18)
                lead_time = number(request.form.get(f'lead_{template["id"]}'), template['default_lead_time_days'])
                estimated = calculate_operation_cost(quantity, hourly_rate, setup_hours, run_hours, outside_cost, consumable_cost, burden) if include else 0
                db.execute(
                    """
                    INSERT INTO quote_operation_estimates
                    (quote_intake_id, template_id, sequence, operation_name, operation_type, include_operation, quantity, hourly_rate, setup_hours, run_hours_per_piece, outside_process_cost, material_or_consumable_cost, burden_percent, estimated_cost, estimated_lead_time_days, basis_notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (quote_id, template['id'], template['sequence'], template['name'], template['operation_type'], include, quantity, hourly_rate, setup_hours, run_hours, outside_cost, consumable_cost, burden, estimated, lead_time if include else 0, request.form.get(f'notes_{template["id"]}', '').strip()),
                )
            feature_type = request.form.get('feature_type', '').strip()
            if feature_type:
                occurrences = number(request.form.get('occurrence_count'), 1)
                tooling_cost = number(request.form.get('tooling_cost_per_event'))
                tool_life = number(request.form.get('estimated_tool_life_events'), 1)
                cycle_minutes = number(request.form.get('cycle_time_minutes_per_event'))
                feature_rate = number(request.form.get('feature_hourly_rate'), 125)
                feature_cost = calculate_feature_cost(occurrences, tooling_cost, tool_life, cycle_minutes, feature_rate)
                db.execute(
                    """
                    INSERT INTO quote_feature_costs
                    (quote_intake_id, feature_type, feature_value, occurrence_count, tooling_cost_per_event, estimated_tool_life_events, cycle_time_minutes_per_event, hourly_rate, estimated_cost, basis_notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (quote_id, feature_type, request.form.get('feature_value', '').strip(), occurrences, tooling_cost, tool_life, cycle_minutes, feature_rate, feature_cost, request.form.get('feature_basis_notes', '').strip()),
                )
            rebuild_rollup(quote_id, number(request.form.get('target_margin_percent'), 35))
            flash('Operations quote built from route, blueprint facts, and feature/tooling cost events.', 'success')
            return redirect(url_for('quote_ops_detail', quote_id=quote_id))

        quotes = quote_options()
        templates = get_db().execute('SELECT * FROM quote_operation_templates WHERE active = 1 ORDER BY sequence').fetchall()
        body = render_template_string(
            """
            <section class='page-head'><div><p class='eyebrow'>New Operations Quote</p><h2>Build the manufacturing route</h2><p>Select the quote intake, enter extracted blueprint facts, check the route steps, and add special feature/tooling events like a 3/16 radius.</p></div></section>
            {% if not quotes %}<section class='panel'><h3>Create a quote intake first.</h3><p>Go to Quote Intakes and create the quote number/customer/drawing reference before building the operation estimate.</p><p><a class='button' href='{{ url_for('create_record', module_key='quote-intakes') }}'>Create Quote Intake</a></p></section>{% else %}
            <form class='panel form' method='post'>
                <div class='form-grid'>
                    <label><span>Quote intake <em>required</em></span><select name='quote_intake_id' required>{% for quote in quotes %}<option value='{{ quote.id }}'>{{ quote.quote_number }}</option>{% endfor %}</select></label>
                    <label><span>Quantity</span><input type='number' step='0.01' name='quantity' value='1'></label>
                    <label><span>Part number</span><input name='part_number'></label>
                    <label><span>Revision</span><input name='revision'></label>
                    <label><span>Length</span><input type='number' step='0.001' name='extracted_length'></label>
                    <label><span>Width</span><input type='number' step='0.001' name='extracted_width'></label>
                    <label><span>Height</span><input type='number' step='0.001' name='extracted_height'></label>
                    <label><span>Weight</span><input type='number' step='0.001' name='extracted_weight'></label>
                    <label><span>Material guess</span><input name='material_guess'></label>
                    <label><span>Thickness guess</span><input name='thickness_guess'></label>
                    <label class='wide'><span>Blueprint source / drawing reference</span><input name='blueprint_source'></label>
                    <label class='wide'><span>Detected blueprint features</span><textarea name='detected_features' placeholder='Example: 3/16 radius x 4, powder coat, tapped holes, tight tolerance, weldment notes'></textarea></label>
                    <label class='wide'><span>Extraction notes</span><textarea name='extraction_notes'></textarea></label>
                </div>
                <section class='panel'>
                    <h3>Route checklist</h3>
                    <table><thead><tr><th>Use</th><th>Operation</th><th>Rate</th><th>Setup hrs</th><th>Run hrs/pc</th><th>Outside cost</th><th>Consumable/material</th><th>Burden %</th><th>Lead days</th></tr></thead><tbody>
                    {% for op in templates %}
                    <tr>
                        <td><input type='checkbox' name='op_{{ op.id }}' {% if op.name in ['Receive Material','Hurco Mill','Brushing/Deburr','Final Inspect','Packaging','Shipping'] %}checked{% endif %}></td>
                        <td>{{ op.sequence }} - {{ op.name }}</td>
                        <td><input type='number' step='0.01' name='rate_{{ op.id }}' value='{{ op.default_rate }}'></td>
                        <td><input type='number' step='0.01' name='setup_{{ op.id }}' value='{{ op.default_setup_hours }}'></td>
                        <td><input type='number' step='0.001' name='run_{{ op.id }}' value='{{ op.default_run_hours_per_piece }}'></td>
                        <td><input type='number' step='0.01' name='outside_{{ op.id }}' value='0'></td>
                        <td><input type='number' step='0.01' name='consumable_{{ op.id }}' value='0'></td>
                        <td><input type='number' step='0.01' name='burden_{{ op.id }}' value='18'></td>
                        <td><input type='number' step='0.01' name='lead_{{ op.id }}' value='{{ op.default_lead_time_days }}'></td>
                    </tr>
                    <tr><td colspan='9'><input name='notes_{{ op.id }}' placeholder='Basis notes for {{ op.name }}'></td></tr>
                    {% endfor %}
                    </tbody></table>
                </section>
                <section class='panel'>
                    <h3>Special feature/tooling event</h3>
                    <p>Use this for things like a 3/16 radius, specialty cutter wear, extra deburr burden, tapped hole pattern, tight tolerance, fixture need, or coating requirement.</p>
                    <div class='form-grid'>
                        <label><span>Feature type</span><input name='feature_type' placeholder='Radius'></label>
                        <label><span>Feature value</span><input name='feature_value' placeholder='3/16 in radius'></label>
                        <label><span>Occurrence count</span><input type='number' step='0.01' name='occurrence_count' value='1'></label>
                        <label><span>Tooling cost per event/tool</span><input type='number' step='0.01' name='tooling_cost_per_event' value='0'></label>
                        <label><span>Estimated tool life events</span><input type='number' step='0.01' name='estimated_tool_life_events' value='1'></label>
                        <label><span>Cycle minutes per event</span><input type='number' step='0.01' name='cycle_time_minutes_per_event' value='0'></label>
                        <label><span>Hourly rate</span><input type='number' step='0.01' name='feature_hourly_rate' value='125'></label>
                        <label><span>Target margin %</span><input type='number' step='0.01' name='target_margin_percent' value='35'></label>
                        <label class='wide'><span>Feature basis notes</span><textarea name='feature_basis_notes'></textarea></label>
                    </div>
                </section>
                <div class='actions'><button class='button' type='submit'>Build Operations Quote</button><a class='button' href='{{ url_for('quote_ops_home') }}'>Cancel</a></div>
            </form>{% endif %}
            """,
            quotes=quotes,
            templates=templates,
        )
        return page('New Operations Quote | SuperForge', body)

    @app.get('/quote-ops/<int:quote_id>')
    def quote_ops_detail(quote_id: int) -> str:
        ensure_operations_schema()
        quote = get_quote(quote_id)
        rebuild_rollup(quote_id)
        facts = get_db().execute('SELECT * FROM quote_blueprint_facts WHERE quote_intake_id = ? ORDER BY id DESC LIMIT 1', (quote_id,)).fetchone()
        operations = get_db().execute('SELECT * FROM quote_operation_estimates WHERE quote_intake_id = ? ORDER BY sequence, id', (quote_id,)).fetchall()
        features = get_db().execute('SELECT * FROM quote_feature_costs WHERE quote_intake_id = ? ORDER BY id', (quote_id,)).fetchall()
        rollup = get_db().execute('SELECT * FROM quote_rollups WHERE quote_intake_id = ?', (quote_id,)).fetchone()
        body = render_template_string(
            """
            <section class='page-head'><div><p class='eyebrow'>Operations Quote</p><h2>{{ quote.quote_number }}</h2><p>{{ quote.drawing_reference or 'No drawing reference entered' }}</p></div><a class='button' href='{{ url_for('quote_ops_new') }}'>Build Another</a></section>
            <section class='qgrid'>
                <article class='qcard'><span>${{ '%.2f'|format(rollup.total_estimated_cost or 0) }}</span><strong>Estimated cost</strong><p>Operations plus feature/tooling events.</p></article>
                <article class='qcard'><span>${{ '%.2f'|format(rollup.suggested_sell_price or 0) }}</span><strong>Suggested sell</strong><p>Based on target margin.</p></article>
                <article class='qcard'><span>{{ '%.1f'|format(rollup.total_lead_time_days or 0) }}</span><strong>Lead days</strong><p>Route lead-time stack.</p></article>
                <article class='qcard'><span>${{ '%.2f'|format(rollup.feature_cost or 0) }}</span><strong>Feature cost</strong><p>Radius/tooling/tolerance events.</p></article>
                <article class='qcard'><span>${{ '%.2f'|format(rollup.outside_process_cost or 0) }}</span><strong>Outside process</strong><p>Powder coat/vendor operations.</p></article>
            </section>
            <section class='panel'><h3>Blueprint facts</h3>{% if facts %}<table><tr><th>Part</th><td>{{ facts.part_number }}</td><th>Rev</th><td>{{ facts.revision }}</td></tr><tr><th>L x W x H</th><td colspan='3'>{{ facts.extracted_length }} x {{ facts.extracted_width }} x {{ facts.extracted_height }} {{ facts.dimension_unit }}</td></tr><tr><th>Weight</th><td>{{ facts.extracted_weight }} {{ facts.weight_unit }}</td><th>Material</th><td>{{ facts.material_guess }}</td></tr><tr><th>Features</th><td colspan='3'>{{ facts.detected_features }}</td></tr></table>{% else %}<p>No blueprint facts recorded yet.</p>{% endif %}</section>
            <section class='panel'><h3>Operation route</h3>{% if operations %}<table><thead><tr><th>Use</th><th>Seq</th><th>Operation</th><th>Qty</th><th>Rate</th><th>Setup</th><th>Run/pc</th><th>Outside</th><th>Consumable</th><th>Cost</th><th>Lead</th></tr></thead><tbody>{% for op in operations %}<tr><td>{{ 'Check' if op.include_operation else '' }}</td><td>{{ op.sequence }}</td><td>{{ op.operation_name }}</td><td>{{ op.quantity }}</td><td>${{ '%.2f'|format(op.hourly_rate) }}</td><td>{{ op.setup_hours }}</td><td>{{ op.run_hours_per_piece }}</td><td>${{ '%.2f'|format(op.outside_process_cost) }}</td><td>${{ '%.2f'|format(op.material_or_consumable_cost) }}</td><td>${{ '%.2f'|format(op.estimated_cost) }}</td><td>{{ op.estimated_lead_time_days }}</td></tr>{% endfor %}</tbody></table>{% else %}<p>No operation route built yet.</p>{% endif %}</section>
            <section class='panel'><h3>Feature/tooling events</h3>{% if features %}<table><thead><tr><th>Feature</th><th>Value</th><th>Count</th><th>Tooling</th><th>Tool life</th><th>Cycle min</th><th>Cost</th><th>Basis</th></tr></thead><tbody>{% for feature in features %}<tr><td>{{ feature.feature_type }}</td><td>{{ feature.feature_value }}</td><td>{{ feature.occurrence_count }}</td><td>${{ '%.2f'|format(feature.tooling_cost_per_event) }}</td><td>{{ feature.estimated_tool_life_events }}</td><td>{{ feature.cycle_time_minutes_per_event }}</td><td>${{ '%.2f'|format(feature.estimated_cost) }}</td><td>{{ feature.basis_notes }}</td></tr>{% endfor %}</tbody></table>{% else %}<p>No feature/tooling events recorded.</p>{% endif %}</section>
            <section class='panel'><h3>Quote intelligence</h3><p>{{ rollup.risk_notes }}</p><p>Next layer should compare this quote route against previous actuals by operation, supplier lead time, machine utilization, coating/vendor risk, and FPY trends for similar parts.</p></section>
            """,
            quote=quote,
            facts=facts,
            operations=operations,
            features=features,
            rollup=rollup,
        )
        return page(f'{quote["quote_number"]} Operations Quote | SuperForge', body)
