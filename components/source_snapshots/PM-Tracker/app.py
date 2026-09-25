import csv, io, json, os
from datetime import date, datetime, timedelta
from flask import Flask, Response, redirect, request, url_for

app = Flask(__name__)
DATA_FILE = 'pm_data.json'
SETTINGS_FILE = 'pm_settings.json'
CSV_DIR = 'data'

MACHINES = ['Machine ID','Machine Name','Department','Location','Manufacturer','Model','Serial Number','Asset Tag','Install Year','Criticality','Notes','Active (Y/N)']
TASKS = ['Task ID','Machine ID','Task Name','Task Description','Frequency Unit (Days/Weeks/Months)','Frequency Value','Responsible Role','Estimated Minutes','Safety Notes','Active (Y/N)']
LOGS = ['Completion ID','Machine ID','Task ID','Completed By','Completion Date','Completion Time','Notes','Pass/Fail']


def clean(v):
    return '' if v is None else str(v).strip()


def blank():
    return {'Machines': [], 'PM_Tasks': [], 'Completion_Log': []}


def default_settings():
    return {'host': '127.0.0.1', 'port': 5055}


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, encoding='utf-8') as f:
                settings = json.load(f)
            host = clean(settings.get('host')) or default_settings()['host']
            port = int(settings.get('port') or default_settings()['port'])
            if port < 1 or port > 65535:
                port = default_settings()['port']
            return {'host': host, 'port': port}
        except Exception:
            pass
    return default_settings()


def save_settings(host, port):
    settings = {'host': clean(host) or default_settings()['host'], 'port': int(port)}
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)
    return settings


def load_csv(name, fields):
    path = os.path.join(CSV_DIR, name + '.csv')
    if not os.path.exists(path):
        return []
    with open(path, newline='', encoding='utf-8') as f:
        return [{field: clean(row.get(field, '')) for field in fields} for row in csv.DictReader(f)]


def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding='utf-8') as f:
            return json.load(f)
    data = blank()
    data['Machines'] = load_csv('Machines', MACHINES)
    data['PM_Tasks'] = load_csv('PM_Tasks', TASKS)
    data['Completion_Log'] = load_csv('Completion_Log', LOGS)
    save(data)
    return data


def save(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)


def active(row):
    return clean(row.get('Active (Y/N)', 'Y')).upper() != 'N'


def find(rows, key, value):
    for row in rows:
        if clean(row.get(key)) == value:
            return row
    return None


def last_done(data, task_id):
    rows = [r for r in data['Completion_Log'] if clean(r.get('Task ID')) == task_id]
    return sorted(rows, key=lambda r: (clean(r.get('Completion Date')), clean(r.get('Completion Time'))), reverse=True)[0] if rows else None


def next_due(data, task):
    last = last_done(data, clean(task.get('Task ID')))
    if not last:
        return 'No completion logged'
    try:
        done = datetime.strptime(clean(last.get('Completion Date')), '%Y-%m-%d').date()
        value = int(float(clean(task.get('Frequency Value')) or 0))
    except Exception:
        return 'Unknown'
    unit = clean(task.get('Frequency Unit (Days/Weeks/Months)')).lower()
    if unit.startswith('week'):
        done += timedelta(weeks=value)
    elif unit.startswith('month'):
        done += timedelta(days=30 * value)
    else:
        done += timedelta(days=value)
    return done.isoformat()


def log_id(data):
    nums = []
    for row in data['Completion_Log']:
        raw = clean(row.get('Completion ID'))
        if raw.startswith('LOG-'):
            try:
                nums.append(int(raw.split('-', 1)[1]))
            except ValueError:
                pass
    return f'LOG-{(max(nums) if nums else 0) + 1:04d}'


def page(title, body):
    settings = load_settings()
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>{title}</title><style>
body{{font-family:Arial,sans-serif;background:#0f172a;color:#e5e7eb;margin:0}}header{{background:#020617;padding:16px 24px;border-bottom:1px solid #334155}}main{{max-width:1200px;margin:auto;padding:24px}}a{{color:#38bdf8}}nav a{{margin-left:14px}}.card{{background:#1f2937;border:1px solid #334155;border-radius:12px;padding:16px;margin:0 0 16px}}table{{width:100%;border-collapse:collapse}}td,th{{border-bottom:1px solid #334155;padding:9px;text-align:left;vertical-align:top}}th,.muted{{color:#94a3b8}}input,select,textarea{{width:100%;padding:9px;border-radius:7px;border:1px solid #334155;background:#020617;color:#e5e7eb}}textarea{{min-height:70px}}label{{display:block;margin:8px 0;color:#94a3b8}}button,.btn{{background:#38bdf8;color:#00111f;border:0;border-radius:8px;padding:10px 14px;font-weight:700;text-decoration:none}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}.right{{float:right;color:#94a3b8;font-size:13px}}
</style></head><body><header><b><a href="/">PM Tracker</a></b><span class="right">Host {settings['host']} | Port {settings['port']}</span><nav><a href="/machines/new">Add Machine</a><a href="/tasks/new">Add Task</a><a href="/completions">Completions</a><a href="/settings">Host/Port</a></nav></header><main>{body}</main></body></html>'''


@app.route('/')
def home():
    data = load()
    machines = [m for m in data['Machines'] if active(m)]
    tasks = [t for t in data['PM_Tasks'] if active(t)]
    rows = ''.join(f"<tr><td><a href='/machine/{m['Machine ID']}'>{m['Machine Name']}</a></td><td>{m['Machine ID']}</td><td>{m['Department']}</td><td>{m['Location']}</td><td>{m['Criticality']}</td></tr>" for m in machines)
    return page('PM Tracker', f"<h1>Preventive Maintenance Tracker</h1><div class='grid'><div class='card'><h2>{len(machines)}</h2><p>Active machines</p></div><div class='card'><h2>{len(tasks)}</h2><p>Active PM tasks</p></div><div class='card'><h2>{len(data['Completion_Log'])}</h2><p>Completion records</p></div></div><div class='card'><h2>Machines</h2><table><tr><th>Machine</th><th>ID</th><th>Department</th><th>Location</th><th>Criticality</th></tr>{rows}</table></div>")


@app.route('/settings', methods=['GET','POST'])
def settings():
    current = load_settings()
    msg = ''
    if request.method == 'POST':
        try:
            new = save_settings(request.form.get('host'), request.form.get('port'))
            msg = f"<p class='muted'>Saved. Restart the app for server binding changes to take effect. New setting: {new['host']} port {new['port']}.</p>"
            current = new
        except Exception as exc:
            msg = f"<p class='muted'>Could not save settings: {exc}</p>"
    body = f"<h1>Host and Port</h1><div class='card'><form method='post'><div class='grid'><label>Host<input name='host' value='{current['host']}'></label><label>Port<input name='port' type='number' min='1' max='65535' value='{current['port']}'></label></div><button>Save Host/Port</button></form>{msg}<p class='muted'>Use 127.0.0.1 for local-only access. Use 0.0.0.0 only when you intentionally want LAN access.</p></div>"
    return page('Host and Port', body)


@app.route('/machine/<machine_id>')
def machine(machine_id):
    data = load()
    machine_row = find(data['Machines'], 'Machine ID', machine_id)
    if not machine_row:
        return page('Not found', '<div class="card">Machine not found.</div>')
    rows = ''
    for task in [t for t in data['PM_Tasks'] if clean(t.get('Machine ID')) == machine_id and active(t)]:
        rows += f"<tr><td>{task['Task Name']}<br><span class='muted'>{task['Task ID']}</span></td><td>{task['Task Description']}</td><td>Every {task['Frequency Value']} {task['Frequency Unit (Days/Weeks/Months)']}</td><td>{task['Responsible Role']}</td><td>{next_due(data, task)}</td><td><a href='/complete/{task['Task ID']}'>Log completion</a></td></tr>"
    body = f"<h1>{machine_row['Machine Name']}</h1><div class='card'><p><b>ID:</b> {machine_row['Machine ID']} | <b>Department:</b> {machine_row['Department']} | <b>Location:</b> {machine_row['Location']} | <b>Criticality:</b> {machine_row['Criticality']}</p><p><b>Manufacturer:</b> {machine_row['Manufacturer']} | <b>Model:</b> {machine_row['Model']} | <b>Serial:</b> {machine_row['Serial Number']} | <b>Asset:</b> {machine_row['Asset Tag']}</p><p>{machine_row['Notes']}</p></div><div class='card'><h2>PM Tasks</h2><table><tr><th>Task</th><th>Description</th><th>Frequency</th><th>Role</th><th>Next Due</th><th></th></tr>{rows}</table></div><p><a class='btn' href='/tasks/new?machine_id={machine_id}'>Add Task</a></p>"
    return page(machine_row['Machine Name'], body)


@app.route('/machines/new', methods=['GET','POST'])
def add_machine():
    data = load()
    if request.method == 'POST':
        row = {field: clean(request.form.get(field, '')) for field in MACHINES}
        row['Active (Y/N)'] = row['Active (Y/N)'] or 'Y'
        if row['Machine ID'] and row['Machine Name']:
            data['Machines'].append(row)
            save(data)
            return redirect(url_for('machine', machine_id=row['Machine ID']))
    fields = ''.join(f"<label>{field}<input name='{field}' value='Y'></label>" if field == 'Active (Y/N)' else f"<label>{field}<input name='{field}'></label>" for field in MACHINES)
    return page('Add Machine', f"<h1>Add Machine</h1><div class='card'><form method='post'><div class='grid'>{fields}</div><button>Save Machine</button></form></div>")


@app.route('/tasks/new', methods=['GET','POST'])
def add_task():
    data = load()
    selected = clean(request.args.get('machine_id'))
    if request.method == 'POST':
        row = {field: clean(request.form.get(field, '')) for field in TASKS}
        row['Active (Y/N)'] = row['Active (Y/N)'] or 'Y'
        if row['Task ID'] and row['Machine ID'] and row['Task Name']:
            data['PM_Tasks'].append(row)
            save(data)
            return redirect(url_for('machine', machine_id=row['Machine ID']))
    options = ''.join(f"<option value='{m['Machine ID']}' {'selected' if m['Machine ID'] == selected else ''}>{m['Machine ID']} - {m['Machine Name']}</option>" for m in data['Machines'] if active(m))
    body = f"<h1>Add PM Task</h1><div class='card'><form method='post'><div class='grid'><label>Task ID<input name='Task ID'></label><label>Machine<select name='Machine ID'>{options}</select></label><label>Task Name<input name='Task Name'></label><label>Frequency Unit<select name='Frequency Unit (Days/Weeks/Months)'><option>Days</option><option>Weeks</option><option>Months</option></select></label><label>Frequency Value<input name='Frequency Value' type='number' value='1'></label><label>Responsible Role<input name='Responsible Role'></label><label>Estimated Minutes<input name='Estimated Minutes' type='number'></label><label>Active (Y/N)<input name='Active (Y/N)' value='Y'></label></div><label>Task Description<textarea name='Task Description'></textarea></label><label>Safety Notes<textarea name='Safety Notes'></textarea></label><button>Save Task</button></form></div>"
    return page('Add Task', body)


@app.route('/complete/<task_id>', methods=['GET','POST'])
def complete(task_id):
    data = load()
    task = find(data['PM_Tasks'], 'Task ID', task_id)
    if not task:
        return page('Not found', '<div class="card">Task not found.</div>')
    if request.method == 'POST':
        now = datetime.now()
        row = {'Completion ID': log_id(data), 'Machine ID': task['Machine ID'], 'Task ID': task['Task ID'], 'Completed By': clean(request.form.get('Completed By')), 'Completion Date': clean(request.form.get('Completion Date')) or now.date().isoformat(), 'Completion Time': clean(request.form.get('Completion Time')) or now.strftime('%H:%M'), 'Notes': clean(request.form.get('Notes')), 'Pass/Fail': clean(request.form.get('Pass/Fail')) or 'Pass'}
        data['Completion_Log'].append(row)
        save(data)
        return redirect(url_for('machine', machine_id=task['Machine ID']))
    body = f"<h1>Log Completion</h1><div class='card'><p>{task['Task Name']} | {task['Task ID']}</p><form method='post'><div class='grid'><label>Completed By<input name='Completed By' required></label><label>Date<input type='date' name='Completion Date' value='{date.today().isoformat()}'></label><label>Time<input type='time' name='Completion Time' value='{datetime.now().strftime('%H:%M')}'></label><label>Pass/Fail<select name='Pass/Fail'><option>Pass</option><option>Fail</option></select></label></div><label>Notes<textarea name='Notes'></textarea></label><button>Save Completion</button></form></div>"
    return page('Log Completion', body)


@app.route('/completions')
def completions():
    data = load()
    rows = ''.join(f"<tr><td>{r['Completion ID']}</td><td>{r['Completion Date']}</td><td>{r['Completion Time']}</td><td>{r['Machine ID']}</td><td>{r['Task ID']}</td><td>{r['Completed By']}</td><td>{r['Pass/Fail']}</td><td>{r['Notes']}</td></tr>" for r in reversed(data['Completion_Log']))
    return page('Completions', f"<h1>Completion Log</h1><div class='card'><table><tr><th>ID</th><th>Date</th><th>Time</th><th>Machine</th><th>Task</th><th>By</th><th>Result</th><th>Notes</th></tr>{rows}</table></div>")


@app.route('/export/<table>.csv')
def export_csv(table):
    fields = {'Machines': MACHINES, 'PM_Tasks': TASKS, 'Completion_Log': LOGS}.get(table)
    if not fields:
        return Response('Unknown table', status=404)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(load()[table])
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={table}.csv'})


if __name__ == '__main__':
    settings = load_settings()
    print(f"PM Tracker starting on host {settings['host']} port {settings['port']}")
    app.run(debug=True, host=settings['host'], port=settings['port'])
