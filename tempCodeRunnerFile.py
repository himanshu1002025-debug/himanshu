"""
Family Care — Flask application.

Full app: home, auth, picker, dashboard, doctors, share report, sensor intake,
transparency page, phone accelerometer, and simulated wearable integration.
"""

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from datetime import datetime
import random
import socket
import threading
import secrets

from db import query_one, query_all, execute, init_db
from anomaly import analyze_day, is_anomaly, METRICS, COMBINED_THRESHOLD

app = Flask(__name__)
app.secret_key = 'dev-only-change-me-before-deploying'

init_db()


# ============================================================
# Utility: detect LAN IP
# ============================================================

def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()


# ============================================================
# Wearable device columns (auto-migration)
# ============================================================

def _ensure_device_columns():
    existing = {r['name'] for r in query_all("PRAGMA table_info(devices)")}
    migrations = [
        ('brand',       'TEXT'),
        ('connectedAt', 'TEXT'),
        ('lastReading', 'INTEGER'),
        ('active',      'INTEGER DEFAULT 0'),
    ]
    for col, typ in migrations:
        if col not in existing:
            try:
                execute(f"ALTER TABLE devices ADD COLUMN {col} {typ}")
            except Exception:
                pass

    try:
        execute("UPDATE devices SET active = 0 WHERE active = 1 AND brand IS NOT NULL")
    except Exception:
        pass

_ensure_device_columns()


# ============================================================
# Background wearable worker
# ============================================================

_wearable_threads = {}


def _wearable_worker(device_id, elderly_id, stop_event):
    last = 100
    while not stop_event.is_set():
        delta = random.randint(-10, 10)
        last = max(75, min(130, last + delta))

        values = {
            'wakeUpTime': 7,
            'mealsEaten': 3,
            'movementCount': last,
            'sleepHours': 7.0,
            'timesWokenAtNight': 1,
        }
        try:
            _upsert_day(elderly_id, values)
            execute(
                'UPDATE devices SET lastReading = ? WHERE id = ?',
                (last, device_id)
            )
        except Exception:
            pass

        stop_event.wait(30)


def _start_wearable(device_id, elderly_id):
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_wearable_worker,
        args=(device_id, elderly_id, stop_event),
        daemon=True
    )
    thread.start()
    _wearable_threads[device_id] = {'thread': thread, 'stop': stop_event}


def _stop_wearable(device_id):
    entry = _wearable_threads.pop(device_id, None)
    if entry:
        entry['stop'].set()


# ============================================================
# Auth helpers
# ============================================================

def current_user_id():
    return session.get('user_id')


def login_required():
    if not current_user_id():
        flash('Please log in first.', 'error')
        return redirect(url_for('login'))
    return None


def user_can_see(user_id, elderly_id):
    row = query_one(
        'SELECT 1 as ok FROM user_elderly_access WHERE userId = ? AND elderlyId = ?',
        (user_id, elderly_id)
    )
    return row is not None


# ============================================================
# Home + auth
# ============================================================

@app.route('/')
def home():
    return render_template('home.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()

    if not username or not password:
        flash('Please enter both username and password.', 'error')
        return redirect(url_for('login'))

    user = query_one(
        'SELECT * FROM users WHERE username = ? AND password = ?',
        (username, password)
    )
    if not user:
        flash('Incorrect username or password.', 'error')
        return redirect(url_for('login'))

    session['user_id'] = user['id']
    session['username'] = user['username']
    flash(f"Welcome back, {user['username']}!", 'success')
    return redirect(url_for('picker'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')

    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()

    if len(username) < 3 or len(password) < 3:
        flash('Username and password must be at least 3 characters.', 'error')
        return redirect(url_for('signup'))

    if query_one('SELECT id FROM users WHERE username = ?', (username,)):
        flash('That username is already taken.', 'error')
        return redirect(url_for('signup'))

    user_id = execute(
        'INSERT INTO users (username, password) VALUES (?, ?)',
        (username, password)
    )
    session['user_id'] = user_id
    session['username'] = username
    flash('Account created. Add a family member to monitor.', 'success')
    return redirect(url_for('picker'))


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'success')
    return redirect(url_for('home'))


# ============================================================
# Picker
# ============================================================

@app.route('/picker')
def picker():
    guard = login_required()
    if guard:
        return guard

    people = query_all("""
        SELECT elderly_people.id, elderly_people.name
        FROM elderly_people
        JOIN user_elderly_access ON elderly_people.id = user_elderly_access.elderlyId
        WHERE user_elderly_access.userId = ?
        ORDER BY elderly_people.name ASC
    """, (current_user_id(),))

    return render_template('picker.html', people=people)


@app.route('/add-elderly', methods=['POST'])
def add_elderly():
    guard = login_required()
    if guard:
        return guard

    name = (request.form.get('name') or '').strip()
    if len(name) < 2:
        flash('Name must be at least 2 characters.', 'error')
        return redirect(url_for('picker'))

    elderly_id = execute('INSERT INTO elderly_people (name) VALUES (?)', (name,))
    execute(
        'INSERT INTO user_elderly_access (userId, elderlyId) VALUES (?, ?)',
        (current_user_id(), elderly_id)
    )
    flash(f'Added {name} to your family list.', 'success')
    return redirect(url_for('picker'))


# ============================================================
# Dashboard
# ============================================================

def compute_alerts(elderly_id):
    logs = query_all(
        'SELECT * FROM logs WHERE elderlyId = ? ORDER BY id ASC',
        (elderly_id,)
    )

    results = []
    for i, log in enumerate(logs):
        base = {
            'id': log['id'],
            'day': log['day'],
            'date': log['date'],
            'movementCount': log['movementCount'],
            'sleepHours': log['sleepHours'],
            'timesWokenAtNight': log['timesWokenAtNight'],
            'mealsEaten': log['mealsEaten'],
        }
        if i < 7:
            base.update({
                'flagged': False,
                'status': 'building baseline',
                'reasons': [],
                'score': 0.0,
            })
        else:
            window = logs[i - 7:i]
            analysis = analyze_day(log, window)
            base.update({
                'flagged': analysis['flagged'],
                'status': 'unusual' if analysis['flagged'] else 'normal',
                'reasons': analysis['reasons'],
                'score': analysis['score'],
            })
        results.append(base)

    return results


@app.route('/dashboard/<int:elderly_id>')
def dashboard(elderly_id):
    guard = login_required()
    if guard:
        return guard

    if not user_can_see(current_user_id(), elderly_id):
        abort(403)

    person = query_one('SELECT * FROM elderly_people WHERE id = ?', (elderly_id,))
    if not person:
        abort(404)

    alerts = compute_alerts(elderly_id)

    unusual_count = sum(1 for a in alerts if a['status'] == 'unusual')
    total = len(alerts)
    avg_activity = round(sum(a['movementCount'] for a in alerts) / total) if total else 0
    avg_sleep = round(sum(a['sleepHours'] for a in alerts) / total, 1) if total else 0.0
    initial = person['name'][0].upper() if person['name'] else '?'

    return render_template(
        'dashboard.html',
        elderly_id=elderly_id,
        person_name=person['name'],
        initial=initial,
        alerts=alerts,
        unusual_count=unusual_count,
        avg_activity=avg_activity,
        avg_sleep=avg_sleep,
    )


# ============================================================
# Transparency
# ============================================================

METRIC_LABELS = {
    'movementCount':     'Activity level',
    'sleepHours':        'Sleep hours',
    'timesWokenAtNight': 'Times woken at night',
    'mealsEaten':        'Meals eaten',
}


def _metric_breakdown(today_log, window):
    rows = []
    for metric, cfg in METRICS.items():
        values = [r[metric] for r in window if r.get(metric) is not None]
        if len(values) < 2:
            continue

        mean = sum(values) / len(values)
        sq_diffs = [(v - mean) ** 2 for v in values]
        variance = sum(sq_diffs) / len(sq_diffs)
        std_dev = variance ** 0.5
        effective = max(std_dev, cfg['floor'])
        today_value = today_log[metric]
        z = abs(today_value - mean) / effective

        rows.append({
            'metric': metric,
            'label': METRIC_LABELS.get(metric, metric),
            'window_values': [round(v, 1) for v in values],
            'mean': round(mean, 2),
            'std_dev': round(std_dev, 3),
            'floor': cfg['floor'],
            'effective_sd': round(effective, 3),
            'today': today_value,
            'z': round(z, 2),
            'weight': cfg['weight'],
            'severe': cfg['severe'],
            'triggered_severe': z >= cfg['severe'],
            'contribution': round(cfg['weight'] * z, 2),
        })
    return rows


def _build_example(logs, person_name):
    if len(logs) < 8:
        return None

    picked = None
    for i in range(len(logs) - 1, 6, -1):
        window = logs[i - 7:i]
        analysis = analyze_day(logs[i], window)
        if analysis['flagged']:
            picked = (logs[i], window, analysis)
            break

    if not picked:
        i = len(logs) - 1
        window = logs[i - 7:i]
        analysis = analyze_day(logs[i], window)
        picked = (logs[i], window, analysis)

    today_log, window, analysis = picked
    return {
        'day_label': today_log.get('date') or f"Day {today_log['day']}",
        'metrics': _metric_breakdown(today_log, window),
        'combined_score': analysis['score'],
        'flagged': analysis['flagged'],
        'reasons': analysis['reasons'],
        'reasons_labels': [METRIC_LABELS.get(r, r) for r in analysis['reasons']],
        'baseline_days': len(window),
        'person_name': person_name,
    }


def _config_rows():
    return [
        {
            'label': METRIC_LABELS[m],
            'floor': cfg['floor'],
            'weight': cfg['weight'],
            'severe': cfg['severe'],
        }
        for m, cfg in METRICS.items()
    ]


SAMPLE_LOGS = [
    {'id': 1, 'day': 1, 'date': '2026-09-01', 'movementCount': 105, 'sleepHours': 7.0, 'timesWokenAtNight': 1, 'mealsEaten': 3},
    {'id': 2, 'day': 2, 'date': '2026-09-02', 'movementCount':  98, 'sleepHours': 7.5, 'timesWokenAtNight': 0, 'mealsEaten': 3},
    {'id': 3, 'day': 3, 'date': '2026-09-03', 'movementCount': 110, 'sleepHours': 6.5, 'timesWokenAtNight': 1, 'mealsEaten': 2},
    {'id': 4, 'day': 4, 'date': '2026-09-04', 'movementCount':  95, 'sleepHours': 7.0, 'timesWokenAtNight': 1, 'mealsEaten': 3},
    {'id': 5, 'day': 5, 'date': '2026-09-05', 'movementCount': 102, 'sleepHours': 6.5, 'timesWokenAtNight': 2, 'mealsEaten': 3},
    {'id': 6, 'day': 6, 'date': '2026-09-06', 'movementCount': 108, 'sleepHours': 7.0, 'timesWokenAtNight': 0, 'mealsEaten': 2},
    {'id': 7, 'day': 7, 'date': '2026-09-07', 'movementCount': 100, 'sleepHours': 7.0, 'timesWokenAtNight': 1, 'mealsEaten': 3},
    {'id': 8, 'day': 8, 'date': '2026-09-08', 'movementCount':  15, 'sleepHours': 3.0, 'timesWokenAtNight': 5, 'mealsEaten': 0},
]


@app.route('/how-it-works')
def how_it_works_public():
    example = _build_example(SAMPLE_LOGS, 'the sample patient')
    return render_template(
        'how_it_works.html',
        elderly_id=None,
        person_name='a sample patient',
        config_rows=_config_rows(),
        combined_threshold=COMBINED_THRESHOLD,
        example=example,
        total_days=len(SAMPLE_LOGS),
        is_public=True,
    )


@app.route('/how-it-works/<int:elderly_id>')
def how_it_works(elderly_id):
    guard = login_required()
    if guard:
        return guard

    if not user_can_see(current_user_id(), elderly_id):
        abort(403)

    person = query_one('SELECT * FROM elderly_people WHERE id = ?', (elderly_id,))
    if not person:
        abort(404)

    logs = query_all('SELECT * FROM logs WHERE elderlyId = ? ORDER BY id ASC', (elderly_id,))
    example = _build_example(logs, person['name'])

    return render_template(
        'how_it_works.html',
        elderly_id=elderly_id,
        person_name=person['name'],
        config_rows=_config_rows(),
        combined_threshold=COMBINED_THRESHOLD,
        example=example,
        total_days=len(logs),
        is_public=False,
    )


# ============================================================
# Phone accelerometer
# ============================================================

@app.route('/connect-sensor')
def connect_sensor():
    lan_ip = get_lan_ip()
    lan_url = f"http://{lan_ip}:4000/connect-sensor"

    devices = query_all("""
        SELECT devices.apiKey, elderly_people.name AS personName
        FROM devices
        JOIN elderly_people ON elderly_people.id = devices.elderlyId
        WHERE devices.brand IS NULL
        ORDER BY elderly_people.name ASC
    """)

    return render_template('connect_sensor.html', lan_url=lan_url, devices=devices)


@app.route('/api/device-info/<api_key>')
def device_info(api_key):
    device = query_one("""
        SELECT devices.apiKey, elderly_people.name AS personName
        FROM devices
        JOIN elderly_people ON elderly_people.id = devices.elderlyId
        WHERE devices.apiKey = ?
    """, (api_key,))
    if not device:
        return {'error': 'Unknown API key'}, 404
    return device


# ============================================================
# Wearable integration
# ============================================================

@app.route('/connect-wearable')
def connect_wearable():
    guard = login_required()
    if guard:
        return guard

    people = query_all("""
        SELECT elderly_people.id, elderly_people.name
        FROM elderly_people
        JOIN user_elderly_access ON elderly_people.id = user_elderly_access.elderlyId
        WHERE user_elderly_access.userId = ?
        ORDER BY elderly_people.name ASC
    """, (current_user_id(),))

    return render_template('connect_wearable.html', elderly_people=people)


@app.route('/api/connect-wearable', methods=['POST'])
def api_connect_wearable():
    guard = login_required()
    if guard:
        return guard

    body = request.get_json(silent=True) or {}
    brand = (body.get('brand') or '').strip()
    elderly_id = body.get('elderlyId')

    allowed_brands = ['Fitbit', 'Apple Watch', 'Garmin']
    if brand not in allowed_brands:
        return {'error': 'Unsupported wearable brand'}, 400

    try:
        elderly_id = int(elderly_id)
    except (ValueError, TypeError):
        return {'error': 'Invalid person selected'}, 400

    if not user_can_see(current_user_id(), elderly_id):
        return {'error': 'You do not have access to that person'}, 403

    api_key = f"wearable-{brand.lower().replace(' ', '-')}-{secrets.token_hex(6)}"
    connected_at = datetime.now().isoformat()

    device_id = execute("""
        INSERT INTO devices (apiKey, elderlyId, brand, connectedAt, active)
        VALUES (?, ?, ?, ?, 1)
    """, (api_key, elderly_id, brand, connected_at))

    _start_wearable(device_id, elderly_id)

    return {
        'success': True,
        'deviceId': device_id,
        'apiKey': api_key,
        'brand': brand,
        'connectedAt': connected_at,
    }


@app.route('/api/connected-wearables')
def api_connected_wearables():
    guard = login_required()
    if guard:
        return guard

    rows = query_all("""
        SELECT devices.id, devices.brand, devices.apiKey, devices.connectedAt,
               devices.lastReading, devices.active,
               elderly_people.id AS elderlyId, elderly_people.name AS personName
        FROM devices
        JOIN elderly_people ON elderly_people.id = devices.elderlyId
        WHERE devices.brand IS NOT NULL
          AND devices.elderlyId IN (
              SELECT elderlyId FROM user_elderly_access WHERE userId = ?
          )
        ORDER BY devices.active DESC, devices.connectedAt DESC
    """, (current_user_id(),))

    return {'wearables': rows}


@app.route('/api/disconnect-wearable/<int:device_id>', methods=['POST'])
def api_disconnect_wearable(device_id):
    guard = login_required()
    if guard:
        return guard

    device = query_one('SELECT * FROM devices WHERE id = ?', (device_id,))
    if not device:
        return {'error': 'Wearable not found'}, 404

    if not user_can_see(current_user_id(), device['elderlyId']):
        return {'error': 'Not authorised'}, 403

    _stop_wearable(device_id)
    execute('UPDATE devices SET active = 0 WHERE id = ?', (device_id,))

    return {'success': True}


# ============================================================
# Add / edit / delete days
# ============================================================

def _validate_day_form(form):
    errors = []
    values = {}
    fields = [
        ('wakeUpTime',        'Wake-up hour',    0,   23),
        ('mealsEaten',        'Meals eaten',     0,   5),
        ('movementCount',     'Activity level',  0,   100000),
        ('sleepHours',        'Sleep hours',     0,   24),
        ('timesWokenAtNight', 'Times woken',     0,   20),
    ]
    for key, label, lo, hi in fields:
        raw = (form.get(key) or '').strip()
        try:
            num = float(raw) if key == 'sleepHours' else int(raw)
        except (ValueError, TypeError):
            errors.append(f'{label} must be a number.')
            continue
        if not (lo <= num <= hi):
            errors.append(f'{label} must be between {lo} and {hi}.')
        values[key] = num
    return errors, values


def _upsert_day(elderly_id, values):
    today = datetime.now().strftime('%Y-%m-%d')
    existing = query_one(
        'SELECT id FROM logs WHERE elderlyId = ? AND date = ?',
        (elderly_id, today)
    )

    if existing:
        execute("""
            UPDATE logs
            SET wakeUpTime = ?, mealsEaten = ?, movementCount = ?,
                sleepHours = ?, timesWokenAtNight = ?, medicineTaken = 1
            WHERE id = ?
        """, (
            values['wakeUpTime'], values['mealsEaten'], values['movementCount'],
            values['sleepHours'], values['timesWokenAtNight'],
            existing['id']
        ))
        return 'updated'
    else:
        count_row = query_one(
            'SELECT COUNT(*) as c FROM logs WHERE elderlyId = ?',
            (elderly_id,)
        )
        next_day = (count_row['c'] or 0) + 1
        execute("""
            INSERT INTO logs
                (elderlyId, day, date, wakeUpTime, mealsEaten,
                 movementCount, sleepHours, timesWokenAtNight, medicineTaken)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            elderly_id, next_day, today,
            values['wakeUpTime'], values['mealsEaten'], values['movementCount'],
            values['sleepHours'], values['timesWokenAtNight']
        ))
        return 'created'


@app.route('/add-day/<int:elderly_id>', methods=['POST'])
def add_day(elderly_id):
    guard = login_required()
    if guard:
        return guard

    if not user_can_see(current_user_id(), elderly_id):
        abort(403)

    errors, values = _validate_day_form(request.form)
    if errors:
        flash(' '.join(errors), 'error')
        return redirect(url_for('dashboard', elderly_id=elderly_id))

    action = _upsert_day(elderly_id, values)
    flash(
        "Today's entry was updated." if action == 'updated'
        else 'Day logged successfully.',
        'success'
    )
    return redirect(url_for('dashboard', elderly_id=elderly_id))


@app.route('/edit-day/<int:elderly_id>/<int:day_id>', methods=['GET', 'POST'])
def edit_day(elderly_id, day_id):
    guard = login_required()
    if guard:
        return guard

    if not user_can_see(current_user_id(), elderly_id):
        abort(403)

    entry = query_one(
        'SELECT * FROM logs WHERE id = ? AND elderlyId = ?',
        (day_id, elderly_id)
    )
    if not entry:
        abort(404)

    person = query_one('SELECT * FROM elderly_people WHERE id = ?', (elderly_id,))

    if request.method == 'GET':
        return render_template(
            'edit_day.html',
            elderly_id=elderly_id,
            person_name=person['name'],
            entry=entry
        )

    errors, values = _validate_day_form(request.form)
    if errors:
        flash(' '.join(errors), 'error')
        return redirect(url_for('edit_day', elderly_id=elderly_id, day_id=day_id))

    execute("""
        UPDATE logs
        SET wakeUpTime = ?, mealsEaten = ?, movementCount = ?,
            sleepHours = ?, timesWokenAtNight = ?
        WHERE id = ?
    """, (
        values['wakeUpTime'], values['mealsEaten'], values['movementCount'],
        values['sleepHours'], values['timesWokenAtNight'], day_id
    ))
    flash('Day updated.', 'success')
    return redirect(url_for('dashboard', elderly_id=elderly_id))


@app.route('/delete-day/<int:elderly_id>/<int:day_id>', methods=['POST'])
def delete_day(elderly_id, day_id):
    guard = login_required()
    if guard:
        return guard

    if not user_can_see(current_user_id(), elderly_id):
        abort(403)

    execute('DELETE FROM logs WHERE id = ?', (day_id,))
    flash('Day removed.', 'success')
    return redirect(url_for('dashboard', elderly_id=elderly_id))


# ============================================================
# Doctors + Share Report
# ============================================================

@app.route('/doctors/<int:elderly_id>')
def doctors(elderly_id):
    guard = login_required()
    if guard:
        return guard

    if not user_can_see(current_user_id(), elderly_id):
        abort(403)

    person = query_one('SELECT * FROM elderly_people WHERE id = ?', (elderly_id,))
    if not person:
        abort(404)

    all_doctors = query_all('SELECT * FROM doctors ORDER BY name ASC')

    shares = query_all("""
        SELECT report_shares.id, report_shares.sharedAt, report_shares.summary,
               doctors.name AS doctorName, doctors.specialty,
               doctors.hospital, doctors.email
        FROM report_shares
        JOIN doctors ON doctors.id = report_shares.doctorId
        WHERE report_shares.elderlyId = ?
        ORDER BY report_shares.id DESC
    """, (elderly_id,))

    return render_template(
        'doctors.html',
        elderly_id=elderly_id,
        person_name=person['name'],
        doctors=all_doctors,
        shares=shares
    )


@app.route('/add-doctor', methods=['POST'])
def add_doctor():
    guard = login_required()
    if guard:
        return guard

    elderly_id = request.form.get('elderly_id')

    name = (request.form.get('name') or '').strip()
    specialty = (request.form.get('specialty') or '').strip()
    hospital = (request.form.get('hospital') or '').strip()
    email = (request.form.get('email') or '').strip()
    years_raw = (request.form.get('experience_years') or '').strip()

    errors = []
    if len(name) < 3:
        errors.append('Doctor name must be at least 3 characters.')
    if len(specialty) < 3:
        errors.append('Specialty must be at least 3 characters.')
    try:
        years = int(years_raw)
        if not (0 <= years <= 80):
            errors.append('Years of experience must be between 0 and 80.')
    except (ValueError, TypeError):
        errors.append('Years of experience must be a whole number.')

    if errors:
        flash(' '.join(errors), 'error')
        return redirect(url_for('doctors', elderly_id=elderly_id))

    execute("""
        INSERT INTO doctors (name, specialty, hospital, email, experience_years)
        VALUES (?, ?, ?, ?, ?)
    """, (name, specialty, hospital, email, years))
    flash(f'Added {name} to the doctors list.', 'success')
    return redirect(url_for('doctors', elderly_id=elderly_id))


def _build_summary(elderly_id):
    person = query_one('SELECT name FROM elderly_people WHERE id = ?', (elderly_id,))
    logs = query_all('SELECT * FROM logs WHERE elderlyId = ? ORDER BY id ASC', (elderly_id,))
    if not person or not logs:
        return None

    unusual_count = 0
    for i in range(7, len(logs)):
        window = logs[i - 7:i]
        if is_anomaly(logs[i], window):
            unusual_count += 1

    avg_sleep = round(sum(l['sleepHours'] for l in logs) / len(logs), 1)
    avg_activity = round(sum(l['movementCount'] for l in logs) / len(logs))
    recent = logs[-5:]

    lines = [
        f"Patient: {person['name']}",
        f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Days tracked: {len(logs)}",
        f"Unusual days detected: {unusual_count}",
        f"Average sleep: {avg_sleep} hours",
        f"Average activity level: {avg_activity}",
        "",
        "Most recent 5 days:",
    ]
    for r in recent:
        label = r.get('date') or f"Day {r['day']}"
        lines.append(
            f"  {label} — Activity: {r['movementCount']}, "
            f"Sleep: {r['sleepHours']}h, Woke: {r['timesWokenAtNight']}x"
        )
    lines.extend([
        "",
        "Note: this summary was generated automatically by the Family Care monitoring system.",
        "It is not a medical diagnosis — please review alongside the patient history."
    ])
    return "\n".join(lines)


@app.route('/share-report/<int:elderly_id>/<int:doctor_id>', methods=['GET', 'POST'])
def share_report(elderly_id, doctor_id):
    guard = login_required()
    if guard:
        return guard

    if not user_can_see(current_user_id(), elderly_id):
        abort(403)

    person = query_one('SELECT * FROM elderly_people WHERE id = ?', (elderly_id,))
    doctor = query_one('SELECT * FROM doctors WHERE id = ?', (doctor_id,))
    if not person or not doctor:
        abort(404)

    summary = _build_summary(elderly_id)
    if not summary:
        flash('No data to share yet for this person.', 'error')
        return redirect(url_for('doctors', elderly_id=elderly_id))

    if request.method == 'GET':
        return render_template(
            'share_preview.html',
            elderly_id=elderly_id,
            person_name=person['name'],
            doctor=doctor,
            summary=summary
        )

    shared_at = datetime.now().isoformat()
    execute("""
        INSERT INTO report_shares (elderlyId, doctorId, sharedAt, summary)
        VALUES (?, ?, ?, ?)
    """, (elderly_id, doctor_id, shared_at, summary))

    flash(f'Report shared with {doctor["name"]}.', 'success')
    return redirect(url_for('doctors', elderly_id=elderly_id))


# ============================================================
# IoT sensor intake
# ============================================================

@app.route('/api/sensor-data', methods=['POST'])
def sensor_data():
    body = request.get_json(silent=True) or {}
    device = query_one('SELECT * FROM devices WHERE apiKey = ?', (body.get('apiKey'),))
    if not device:
        return {'error': 'Unknown or invalid device API key'}, 401

    try:
        movement = int(body.get('movementReading', 0))
    except (ValueError, TypeError):
        return {'error': 'Invalid movement reading'}, 400

    if not (0 <= movement <= 100000):
        return {'error': 'Invalid movement reading'}, 400

    values = {
        'wakeUpTime': random.randint(6, 8),
        'mealsEaten': random.randint(2, 3),
        'movementCount': movement,
        'sleepHours': random.randint(6, 8),
        'timesWokenAtNight': random.randint(0, 2),
    }
    action = _upsert_day(device['elderlyId'], values)
    return {
        'success': True,
        'elderlyId': device['elderlyId'],
        'action': action
    }


# ============================================================
# Entry point
# ============================================================

if __name__ == '__main__':
    print('Family Care (Flask) running on http://localhost:4000')
    print(f'Phone-accessible URL: http://{get_lan_ip()}:4000')
    app.run(host='0.0.0.0', port=4000, debug=False, threaded=True)