"""
Family Care — Flask application.

Full app: home, auth, picker, dashboard, doctors, share report, sensor intake.
"""

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, abort
)
from datetime import datetime
import random

from db import query_one, query_all, execute, init_db
from anomaly import is_anomaly

app = Flask(__name__)
app.secret_key = 'dev-only-change-me-before-deploying'

init_db()


# ============================================================
# Auth helpers
# ============================================================

def current_user_id():
    return session.get('user_id')


def login_required():
    """Return a redirect if not logged in, else None."""
    if not current_user_id():
        flash('Please log in first.', 'error')
        return redirect(url_for('login'))
    return None


def user_can_see(user_id, elderly_id):
    """Confirm a user has access to a given elderly person."""
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
    """Return the alerts list for a given elderly person."""
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
        }
        if i < 7:
            base.update({'flagged': False, 'status': 'building baseline'})
        else:
            window = [logs[j]['movementCount'] for j in range(i - 7, i)]
            flagged = is_anomaly(log['movementCount'], window)
            base.update({
                'flagged': flagged,
                'status': 'unusual' if flagged else 'normal'
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
# Add / delete days
# ============================================================

def _validate_day_form(form):
    """Return (errors list, values dict)."""
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
        raw = form.get(key, '').strip()
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
    """Insert today's log, or update it if one already exists for today."""
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


def _build_summary(elderly_id):
    """Generate a plain-text activity summary for a patient."""
    person = query_one('SELECT name FROM elderly_people WHERE id = ?', (elderly_id,))
    logs = query_all('SELECT * FROM logs WHERE elderlyId = ? ORDER BY id ASC', (elderly_id,))
    if not person or not logs:
        return None

    unusual_count = 0
    for i in range(7, len(logs)):
        window = [logs[j]['movementCount'] for j in range(i - 7, i)]
        if is_anomaly(logs[i]['movementCount'], window):
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
# IoT sensor intake (device-authenticated, JSON API)
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
    app.run(host='0.0.0.0', port=4000, debug=False)